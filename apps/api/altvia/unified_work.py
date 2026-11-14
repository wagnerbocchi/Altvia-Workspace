"""Personal eligibility and full-set suppression precede keyset pagination."""

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from typing import cast as type_cast
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    String,
    case,
    cast,
    false,
    func,
    literal,
    null,
    select,
    tuple_,
    union_all,
)
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by
from sqlalchemy.dialects.postgresql import UUID as SQLUUID
from sqlalchemy.orm import Session

from altvia import identity, project_registry, tickets, work_queries
from altvia.deadlines import due_value
from altvia.models import Ticket, TicketQueue, TicketWorkItem, WorkItem
from altvia.ticket_schemas import TicketFilters
from altvia.unified_work_schemas import (
    Kind,
    LinkedTicketBadge,
    UnifiedTicket,
    UnifiedWorkFilters,
    UnifiedWorkItem,
    UnifiedWorkPage,
)
from altvia.work_schemas import WorkFilters

PRIORITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass(frozen=True)
class UnifiedCursor:
    priority_rank: int
    created_at: datetime
    identifier: UUID
    kind: Kind


def scope(actor_id: UUID, filters: UnifiedWorkFilters) -> str:
    values = filters.model_dump(mode="json", exclude={"limit", "cursor"}, exclude_none=True)
    raw = json.dumps([str(actor_id), values], sort_keys=True, separators=(",", ":"))
    return "unified-work:" + hashlib.sha256(raw.encode()).hexdigest()


def cursor(value: str | None, bound_scope: str) -> UnifiedCursor | None:
    if value is None:
        return None
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Invalid encoding")
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        version, current_scope, rank, stamp, identifier, kind = raw.decode("ascii").split("|")
        instant = datetime.fromisoformat(stamp)
        if (
            version != "v1"
            or current_scope != bound_scope
            or rank not in {"0", "1", "2", "3"}
            or instant.tzinfo is None
            or kind not in {"ticket", "work_item"}
        ):
            raise ValueError("Invalid cursor")
        return UnifiedCursor(
            int(rank), instant.astimezone(UTC), UUID(identifier), type_cast(Kind, kind)
        )
    except (ValueError, UnicodeError):
        raise identity.IdentityError(422, "invalid_cursor") from None


def _next_cursor(bound_scope: str, row: Any) -> str:
    stamp = row.created_at.astimezone(UTC).isoformat()
    raw = f"v1|{bound_scope}|{row.priority_rank}|{stamp}|{row.id}|{row.kind}"
    return base64.urlsafe_b64encode(raw.encode("ascii")).decode("ascii").rstrip("=")


def _eligible(actor_id: UUID, filters: UnifiedWorkFilters) -> Any:
    projects = project_registry.visible_projects(actor_id).subquery("personal_projects")
    works = (
        select(
            literal("work_item").label("kind"),
            WorkItem.id,
            WorkItem.title,
            WorkItem.priority,
            WorkItem.status,
            WorkItem.created_at,
            WorkItem.project_id,
            projects.c.name.label("project_name"),
            WorkItem.work_type,
            WorkItem.due_at,
            WorkItem.due_precision,
            WorkItem.due_date_local,
            WorkItem.due_timezone,
            cast(null(), BigInteger).label("number"),
            cast(null(), SQLUUID).label("client_id"),
            cast(null(), SQLUUID).label("queue_id"),
            cast(null(), String).label("queue_name"),
        )
        .join(projects, projects.c.id == WorkItem.project_id)
        .where(work_queries.involved(actor_id))
    )
    works = work_queries.filtered(
        works, WorkFilters(status=filters.work_status, priority=filters.priority, q=filters.q)
    )
    for key in ("client_id", "team_id"):
        value = getattr(filters, key)
        if value is not None:
            works = works.where(projects.c[key] == value)
    if filters.kind == "ticket":
        works = works.where(false())
    eligible_work = works.cte("eligible_personal_work")
    ticket_rows = tickets.visible(actor_id).with_only_columns(
        literal("ticket").label("kind"),
        Ticket.id,
        Ticket.subject.label("title"),
        Ticket.priority,
        Ticket.status,
        Ticket.created_at,
        cast(null(), SQLUUID).label("project_id"),
        cast(null(), String).label("project_name"),
        cast(null(), String).label("work_type"),
        cast(null(), DateTime(timezone=True)).label("due_at"),
        cast(null(), String).label("due_precision"),
        cast(null(), Date).label("due_date_local"),
        cast(null(), String).label("due_timezone"),
        Ticket.number,
        Ticket.client_id,
        Ticket.queue_id,
        TicketQueue.name.label("queue_name"),
    )
    ticket_rows = tickets.filtered(
        ticket_rows,
        TicketFilters(
            assignee_id=actor_id,
            status=filters.ticket_status,
            priority=filters.priority,
            client_id=filters.client_id,
            q=filters.q,
        ),
    )
    if filters.team_id is not None:
        ticket_rows = ticket_rows.where(TicketQueue.team_id == filters.team_id)
    if filters.kind == "work_item":
        ticket_rows = ticket_rows.where(false())
    represented = (
        select(TicketWorkItem.work_item_id)
        .where(
            TicketWorkItem.ticket_id == Ticket.id,
            TicketWorkItem.work_item_id.in_(select(eligible_work.c.id)),
        )
        .exists()
    )
    ticket_rows = ticket_rows.where(~represented)
    return union_all(select(eligible_work), ticket_rows).subquery("personal_work")


def _badges(actor_id: UUID, personal_page: Any, limit: int) -> Any:
    # The page already applies current work visibility. Join its returned work
    # rows inside this same statement so suppression and badges share a snapshot.
    ranked = (
        tickets.visible(actor_id)
        .with_only_columns(
            TicketWorkItem.work_item_id,
            Ticket.id,
            Ticket.number,
            Ticket.subject,
            Ticket.status,
            Ticket.priority,
            func.row_number()
            .over(partition_by=TicketWorkItem.work_item_id, order_by=Ticket.id)
            .label("position"),
        )
        .join(TicketWorkItem, TicketWorkItem.ticket_id == Ticket.id)
        .join(personal_page, personal_page.c.id == TicketWorkItem.work_item_id)
        .where(personal_page.c.kind == "work_item", personal_page.c.page_position <= limit)
        .subquery("visible_ticket_badges")
    )
    badge = func.jsonb_build_object(
        "id",
        ranked.c.id,
        "number",
        ranked.c.number,
        "subject",
        ranked.c.subject,
        "status",
        ranked.c.status,
        "priority",
        ranked.c.priority,
    )
    return (
        select(
            ranked.c.work_item_id,
            func.jsonb_agg(aggregate_order_by(badge, ranked.c.position)).label("badge_items"),
        )
        .where(ranked.c.position <= 4)
        .group_by(ranked.c.work_item_id)
        .subquery("page_badges")
    )


def page(
    db: Session, actor_id: UUID, filters: UnifiedWorkFilters, last: UnifiedCursor | None
) -> UnifiedWorkPage:
    candidates = _eligible(actor_id, filters)
    rank = case(PRIORITY, value=candidates.c.priority, else_=4)
    order = (rank, candidates.c.created_at, candidates.c.id, candidates.c.kind)
    query = (
        select(
            candidates,
            rank.label("priority_rank"),
            func.row_number().over(order_by=order).label("page_position"),
        )
        .order_by(*order)
        .limit(filters.limit + 1)
    )
    if last is not None:
        query = query.where(
            tuple_(*order)
            > tuple_(
                literal(last.priority_rank),
                literal(last.created_at),
                literal(last.identifier),
                literal(last.kind),
            )
        )
    personal_page = query.cte("personal_page")
    badges = _badges(actor_id, personal_page, filters.limit)
    rows = list(
        db.execute(
            select(
                personal_page,
                func.coalesce(badges.c.badge_items, cast(literal("[]"), JSONB)).label(
                    "linked_tickets"
                ),
            )
            .outerjoin(
                badges,
                (personal_page.c.kind == "work_item")
                & (badges.c.work_item_id == personal_page.c.id),
            )
            .order_by(personal_page.c.page_position)
        )
    )
    items: list[UnifiedWorkItem | UnifiedTicket] = []
    for row in rows[: filters.limit]:
        if row.kind == "ticket":
            items.append(
                UnifiedTicket(
                    kind="ticket",
                    id=row.id,
                    number=row.number,
                    subject=row.title,
                    status=row.status,
                    priority=row.priority,
                    client_id=row.client_id,
                    queue_id=row.queue_id,
                    queue_name=row.queue_name,
                    created_at=row.created_at,
                )
            )
        else:
            origins = [LinkedTicketBadge.model_validate(value) for value in row.linked_tickets]
            items.append(
                UnifiedWorkItem(
                    kind="work_item",
                    id=row.id,
                    project_id=row.project_id,
                    project_name=row.project_name,
                    title=row.title,
                    status=row.status,
                    priority=row.priority,
                    work_type=row.work_type,
                    due_at=row.due_at,
                    due=due_value(
                        row.due_precision, row.due_at, row.due_date_local, row.due_timezone
                    ),
                    created_at=row.created_at,
                    linked_tickets=origins[:3],
                    has_more_linked_tickets=len(origins) > 3,
                )
            )
    return UnifiedWorkPage(
        items=items,
        as_of=datetime.now(UTC),
        next_cursor=(
            _next_cursor(scope(actor_id, filters), rows[filters.limit - 1])
            if len(rows) > filters.limit
            else None
        ),
    )
