"""Both endpoints own authority, versions and events; links grant no scope."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Select, String, and_, cast, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from altvia import identity, project_registry, tickets, work_items, work_queries
from altvia.models import (
    ActivityEvent,
    Client,
    Project,
    ProjectMember,
    RoleBinding,
    Team,
    Ticket,
    TicketQueue,
    TicketWorkItem,
    WorkItem,
)
from altvia.ticket_work_schemas import TicketWorkChoicesQuery
from altvia.work_schemas import WorkFilters


@dataclass(frozen=True)
class ReviewedLinkVersions:
    ticket: int
    work_item: int


@dataclass(frozen=True)
class TicketWorkPair:
    ticket: Ticket
    ticket_access: tickets.Access
    work_item: WorkItem
    work_access: work_items.Access


def scoped_pair(
    db: Session, actor_id: UUID, ticket_id: UUID, work_item_id: UUID, *, write: bool = False
) -> TicketWorkPair:
    ticket, ticket_access = tickets.scoped_ticket(db, actor_id, ticket_id)
    work, work_access = work_items.scoped_work(db, actor_id, work_item_id)
    if write:
        tickets.require_update(ticket, ticket_access, actor_id)
        work_items.require_update(work, work_access, actor_id)
        ticket, ticket_access = tickets.scoped_ticket(db, actor_id, ticket_id, write=True)
        # The initial scope read populated this identity map. Expire columns AND
        # collections before the native graph-then-row locking read; stale
        # assignments must never survive a writer that held the graph first.
        db.expire(work)
        db.expire(work_access.project)
        work, work_access = work_items.scoped_work(db, actor_id, work_item_id, write=True)
        tickets.require_update(ticket, ticket_access, actor_id)
        work_items.require_update(work, work_access, actor_id)
    if ticket.client_id != work_access.project.client_id:
        raise identity.IdentityError(409, "ticket_work_client_mismatch")
    return TicketWorkPair(ticket, ticket_access, work, work_access)


def change_link(
    db: Session,
    actor_id: UUID,
    pair: TicketWorkPair,
    *,
    linked: bool,
    now: datetime,
    correlation_id: str,
    origin: identity.AutomationOrigin | None = None,
) -> bool:
    ticket, work = pair.ticket, pair.work_item
    existing = db.get(TicketWorkItem, (ticket.id, work.id))
    if (existing is not None) == linked:
        return False
    tickets.require_active(pair.ticket_access, ticket)
    work_items.require_active(db, pair.work_access)
    if linked:
        db.add(
            TicketWorkItem(
                ticket_id=ticket.id,
                work_item_id=work.id,
                client_id=ticket.client_id,
                queue_id=ticket.queue_id,
                project_id=work.project_id,
                relation_type="related",
                created_by=actor_id,
                created_at=now,
            )
        )
    else:
        db.delete(existing)
    tickets.advance(ticket, now=now)
    work_items.advance(work)
    details = {
        "ticket_id": str(ticket.id),
        "work_item_id": str(work.id),
        "client_id": str(ticket.client_id),
        "queue_id": str(ticket.queue_id),
        "project_id": str(work.project_id),
        "relation_type": "related",
    }
    action = "linked" if linked else "unlinked"
    identity.record_event(
        db,
        actor_id,
        ticket.id,
        "ticket.work_" + action,
        now,
        correlation_id,
        ticket.version,
        aggregate_type="ticket",
        details=details,
        origin=origin,
    )
    identity.record_event(
        db,
        actor_id,
        work.id,
        "work_item.ticket_" + action,
        now,
        correlation_id,
        work.version,
        aggregate_type="work_item",
        details=details,
        origin=origin,
    )
    return True


def _work_rows(actor_id: UUID) -> Select[Any]:
    projects = project_registry.visible_projects(actor_id).subquery()
    contributor = (
        select(RoleBinding.id)
        .join(
            ProjectMember,
            and_(
                ProjectMember.project_id == RoleBinding.project_id,
                ProjectMember.user_id == RoleBinding.user_id,
            ),
        )
        .where(
            RoleBinding.user_id == actor_id,
            RoleBinding.scope_kind == "project",
            RoleBinding.project_id == WorkItem.project_id,
            RoleBinding.role_name == "agent",
        )
        .correlate(WorkItem)
        .exists()
    )
    can_change = and_(
        or_(projects.c.can_manage, and_(contributor, work_queries.involved(actor_id))),
        projects.c.active,
        Team.active,
        or_(projects.c.client_id.is_(None), Client.active),
    )
    return (
        select(
            WorkItem.id.label("work_item_id"),
            WorkItem.project_id,
            projects.c.name.label("project_name"),
            WorkItem.title,
            WorkItem.status,
            WorkItem.priority,
            WorkItem.version,
            projects.c.client_id,
            can_change.label("can_change"),
        )
        .join(projects, projects.c.id == WorkItem.project_id)
        .join(Team, Team.id == projects.c.team_id)
        .outerjoin(Client, Client.id == projects.c.client_id)
    )


def _ticket_rows(actor_id: UUID) -> Select[Any]:
    can_change = and_(
        or_(
            RoleBinding.role_name == "operations_manager",
            and_(RoleBinding.role_name == "agent", Ticket.assignee_id == actor_id),
        ),
        Client.active,
        TicketQueue.active,
        Team.active,
        Ticket.status != "closed",
    )
    return (
        tickets.visible(actor_id)
        .join(Client, Client.id == Ticket.client_id)
        .with_only_columns(
            Ticket.id.label("ticket_id"),
            cast(Ticket.number, String).label("number"),
            Ticket.subject,
            Ticket.status,
            Ticket.priority,
            Ticket.version,
            Ticket.client_id,
            Ticket.queue_id,
            can_change.label("can_change"),
        )
    )


def linked_work_query(actor_id: UUID, ticket_id: UUID) -> Select[Any]:
    work = _work_rows(actor_id).subquery()
    ticket = _ticket_rows(actor_id).subquery()
    return (
        select(
            *(
                work.c[key]
                for key in (
                    "work_item_id",
                    "project_id",
                    "project_name",
                    "title",
                    "status",
                    "priority",
                    "version",
                )
            ),
            and_(work.c.can_change, ticket.c.can_change).label("can_unlink"),
        )
        .join(TicketWorkItem, TicketWorkItem.work_item_id == work.c.work_item_id)
        .join(
            ticket,
            and_(
                ticket.c.ticket_id == TicketWorkItem.ticket_id,
                ticket.c.client_id == work.c.client_id,
            ),
        )
        .where(ticket.c.ticket_id == ticket_id)
    )


def linked_ticket_query(actor_id: UUID, work_item_id: UUID) -> Select[Any]:
    work = _work_rows(actor_id).subquery()
    ticket = _ticket_rows(actor_id).subquery()
    return (
        select(
            *(
                ticket.c[key]
                for key in ("ticket_id", "number", "subject", "status", "priority", "version")
            ),
            and_(work.c.can_change, ticket.c.can_change).label("can_unlink"),
        )
        .join(TicketWorkItem, TicketWorkItem.ticket_id == ticket.c.ticket_id)
        .join(
            work,
            and_(
                work.c.work_item_id == TicketWorkItem.work_item_id,
                work.c.client_id == ticket.c.client_id,
            ),
        )
        .where(work.c.work_item_id == work_item_id)
    )


def work_choices_query(
    actor_id: UUID, ticket: Ticket, filters: TicketWorkChoicesQuery
) -> Select[Any]:
    query = work_queries.filtered(_work_rows(actor_id), WorkFilters(q=filters.q))
    if filters.project_id is not None:
        query = query.where(WorkItem.project_id == filters.project_id)
    query = query.where(
        ~select(TicketWorkItem.ticket_id)
        .where(TicketWorkItem.ticket_id == ticket.id, TicketWorkItem.work_item_id == WorkItem.id)
        .correlate(WorkItem)
        .exists()
    )
    work = query.subquery()
    return select(
        *(
            work.c[key]
            for key in (
                "work_item_id",
                "project_id",
                "project_name",
                "title",
                "status",
                "priority",
                "version",
            )
        )
    ).where(work.c.client_id == ticket.client_id, work.c.can_change)


def link_activity_clause(
    actor_id: UUID, resource_type: Literal["ticket", "work_item"]
) -> ColumnElement[bool]:
    # Compare typed current IDs as strings; JSON values are never cast to UUID.
    # History depends on current endpoint context, never on a surviving live link.
    ticket = (
        tickets.visible(actor_id)
        .with_only_columns(Ticket.id, Ticket.client_id, Ticket.queue_id)
        .subquery()
    )
    projects = (
        project_registry.visible_projects(actor_id)
        .with_only_columns(Project.id, Project.client_id)
        .subquery()
    )
    details = ActivityEvent.details
    valid = (
        select(WorkItem.id)
        .join(projects, projects.c.id == WorkItem.project_id)
        .join(ticket, ticket.c.client_id == projects.c.client_id)
        .where(
            cast(ticket.c.id, String) == details["ticket_id"].astext,
            cast(WorkItem.id, String) == details["work_item_id"].astext,
            cast(ticket.c.client_id, String) == details["client_id"].astext,
            cast(ticket.c.queue_id, String) == details["queue_id"].astext,
            cast(projects.c.id, String) == details["project_id"].astext,
            details["relation_type"].astext == "related",
            (ticket.c.id if resource_type == "ticket" else WorkItem.id)
            == ActivityEvent.resource_id,
        )
        .correlate(ActivityEvent)
        .exists()
    )
    events = {
        "ticket.work_linked",
        "ticket.work_unlinked",
        "work_item.ticket_linked",
        "work_item.ticket_unlinked",
    }
    return or_(ActivityEvent.event_type.not_in(events), valid)
