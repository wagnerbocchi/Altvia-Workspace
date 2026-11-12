"""Ticket authority, linked-reference integrity and independent state ownership."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, literal_column, select
from sqlalchemy.orm import Session

from altvia import identity
from altvia.models import (
    Client,
    ClientAccessGrant,
    ClientContact,
    RoleBinding,
    Team,
    Ticket,
    TicketCategory,
    TicketMessage,
    TicketNote,
    TicketQueue,
    TicketStatusHistory,
    User,
)
from altvia.queue_registry import QUEUE_ROLES
from altvia.ticket_schemas import (
    TICKET_TRANSITIONS,
    TicketFilters,
    TicketMessageOutput,
    TicketNoteOutput,
    TicketOutput,
    TicketTransition,
)

SEARCH_DOCUMENT = (
    "to_tsvector('portuguese'::regconfig, "
    "coalesce(tickets.subject,'') || ' ' || coalesce(tickets.description,''))"
)


@dataclass(frozen=True)
class Access:
    client: Client
    queue: TicketQueue
    role: str
    team_active: bool
    note_access: str = "none"

    @property
    def manage(self) -> bool:
        return self.role == "operations_manager"

    @property
    def contribute(self) -> bool:
        return self.role in {"agent", "operations_manager"}

    @property
    def active(self) -> bool:
        return self.client.active and self.queue.active and self.team_active


def queues(user_id: UUID) -> Select[tuple[TicketQueue, str, bool]]:
    return (
        select(TicketQueue, RoleBinding.role_name, Team.active)
        .join(
            RoleBinding,
            and_(
                RoleBinding.queue_id == TicketQueue.id,
                RoleBinding.user_id == user_id,
                RoleBinding.scope_kind == "queue",
                RoleBinding.role_name.in_(QUEUE_ROLES),
            ),
        )
        .join(Team, Team.id == TicketQueue.team_id)
    )


def clients(user_id: UUID) -> Select[tuple[Client]]:
    return (
        select(Client)
        .join(ClientAccessGrant, ClientAccessGrant.client_id == Client.id)
        .where(ClientAccessGrant.user_id == user_id)
    )


def can_create(db: Session, user_id: UUID) -> bool:
    query = (
        queues(user_id)
        .join(ClientAccessGrant, ClientAccessGrant.user_id == user_id)
        .join(Client, Client.id == ClientAccessGrant.client_id)
        .where(
            RoleBinding.role_name.in_({"agent", "operations_manager"}),
            TicketQueue.active,
            Team.active,
            Client.active,
        )
    )
    return bool(db.scalar(select(query.exists())))


def scoped_queue(
    db: Session, actor_id: UUID, queue_id: UUID, *, writer: bool = False
) -> tuple[TicketQueue, str, bool]:
    row = db.execute(queues(actor_id).where(TicketQueue.id == queue_id)).one_or_none()
    if row is None:
        raise identity.IdentityError(404, "not_found")
    if writer and row[1] not in {"agent", "operations_manager"}:
        raise identity.IdentityError(403, "forbidden")
    return row[0], row[1], row[2]


def _lock_parents(db: Session, client: Client, queue: TicketQueue) -> bool:
    db.execute(
        select(Client)
        .where(Client.id == client.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    team = db.scalar(
        select(Team)
        .where(Team.id == queue.team_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    db.execute(
        select(TicketQueue)
        .where(TicketQueue.id == queue.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    return team is not None and team.active


def creation_access(
    db: Session, actor_id: UUID, client_id: UUID, queue_id: UUID, *, write: bool = False
) -> Access:
    queue, role, team_active = scoped_queue(db, actor_id, queue_id, writer=True)
    client = db.scalar(clients(actor_id).where(Client.id == client_id))
    if client is None:
        raise identity.IdentityError(404, "not_found")
    if write:
        team_active = _lock_parents(db, client, queue)
    return Access(client, queue, role, team_active)


def visible(user_id: UUID) -> Select[tuple[Ticket, str, bool, str]]:
    return (
        select(Ticket, RoleBinding.role_name, Team.active, RoleBinding.note_access)
        .join(
            RoleBinding,
            and_(
                RoleBinding.user_id == user_id,
                RoleBinding.scope_kind == "queue",
                RoleBinding.queue_id == Ticket.queue_id,
                RoleBinding.role_name.in_(QUEUE_ROLES),
            ),
        )
        .join(
            ClientAccessGrant,
            and_(
                ClientAccessGrant.user_id == user_id,
                ClientAccessGrant.client_id == Ticket.client_id,
            ),
        )
        .join(TicketQueue, TicketQueue.id == Ticket.queue_id)
        .join(Team, Team.id == TicketQueue.team_id)
    )


def scoped_ticket(
    db: Session, actor_id: UUID, identifier: UUID, *, write: bool = False
) -> tuple[Ticket, Access]:
    query = (
        visible(actor_id).where(Ticket.id == identifier).execution_options(populate_existing=True)
    )
    row = db.execute(query).one_or_none()
    if row is None:
        raise identity.IdentityError(404, "not_found")
    item, role, team_active, note_access = row
    if write:
        _lock_parents(db, item.client, item.queue)
        item, role, team_active, note_access = db.execute(
            query.with_for_update(of=Ticket).execution_options(populate_existing=True)
        ).one()
    return item, Access(item.client, item.queue, role, team_active, note_access)


def can_read_notes(access: Access) -> bool:
    return access.contribute and access.note_access in {"read", "write"}


def require_notes(access: Access, *, write: bool = False) -> None:
    if not can_read_notes(access) or (write and access.note_access != "write"):
        raise identity.IdentityError(403, "forbidden")


def note_output(note: TicketNote) -> TicketNoteOutput:
    return TicketNoteOutput(
        id=note.id,
        ticket_id=note.ticket_id,
        author_id=note.author_id,
        author_name=note.author.display_name,
        body_text=note.body_text,
        ticket_version=note.ticket_version,
        created_at=note.created_at,
    )


def can_update(item: Ticket, access: Access, actor_id: UUID) -> bool:
    return access.manage or (access.contribute and item.assignee_id == actor_id)


def message_output(message: TicketMessage) -> TicketMessageOutput:
    return TicketMessageOutput(
        id=message.id,
        ticket_id=message.ticket_id,
        author_id=message.author_id,
        author_name=message.author.display_name,
        body_text=message.body_text,
        visibility=message.visibility,
        direction=message.direction,
        ticket_version=message.ticket_version,
        created_at=message.created_at,
    )


def require_update(item: Ticket, access: Access, actor_id: UUID) -> None:
    if not can_update(item, access, actor_id):
        raise identity.IdentityError(403, "forbidden")


def require_active(access: Access, item: Ticket | None = None) -> None:
    if not access.active:
        raise identity.IdentityError(409, "ticket_parent_inactive")
    if item is not None and item.status == "closed":
        raise identity.IdentityError(409, "ticket_closed")


def candidates(queue_id: UUID, client_id: UUID) -> Select[tuple[User]]:
    bound = (
        select(RoleBinding.id)
        .where(
            RoleBinding.user_id == User.id,
            RoleBinding.scope_kind == "queue",
            RoleBinding.queue_id == queue_id,
            RoleBinding.role_name.in_({"agent", "operations_manager"}),
        )
        .correlate(User)
        .exists()
    )
    ceiling = (
        select(ClientAccessGrant.user_id)
        .where(ClientAccessGrant.user_id == User.id, ClientAccessGrant.client_id == client_id)
        .correlate(User)
        .exists()
    )
    return select(User).where(User.active, bound, ceiling)


def validate_assignee(db: Session, access: Access, identifier: UUID | None) -> None:
    if (
        identifier is not None
        and db.scalar(
            candidates(access.queue.id, access.client.id)
            .where(User.id == identifier)
            .with_for_update(of=User, key_share=True)
        )
        is None
    ):
        raise identity.IdentityError(422, "invalid_ticket_assignee")


def validate_requester(db: Session, access: Access, identifier: UUID) -> None:
    if (
        db.scalar(
            select(ClientContact.id)
            .where(
                ClientContact.id == identifier,
                ClientContact.client_id == access.client.id,
                ClientContact.active,
            )
            .with_for_update(key_share=True)
        )
        is None
    ):
        raise identity.IdentityError(422, "invalid_ticket_requester")


def validate_category(db: Session, access: Access, identifier: UUID | None) -> None:
    if (
        identifier is not None
        and db.scalar(
            select(TicketCategory.id)
            .where(
                TicketCategory.id == identifier,
                TicketCategory.queue_id == access.queue.id,
                TicketCategory.active,
            )
            .with_for_update(key_share=True)
        )
        is None
    ):
        raise identity.IdentityError(422, "invalid_ticket_category")


def advance(item: Ticket) -> None:
    if item.version >= 2147483647:
        raise identity.IdentityError(409, "version_exhausted")
    item.version += 1
    item.updated_at = datetime.now(UTC)


def targets(item: Ticket, access: Access, actor_id: UUID) -> list[str]:
    if not access.active or not can_update(item, access, actor_id):
        return []
    allowed = set(TICKET_TRANSITIONS[item.status])
    if item.status == "closed" and not access.manage:
        allowed.clear()
    if not access.queue.allow_reopen and item.status in {"resolved", "closed"}:
        allowed.discard("open")
    if not access.queue.allow_manual_close or not access.manage:
        allowed.discard("closed")
    return sorted(allowed)


def output(item: Ticket, access: Access, actor_id: UUID) -> TicketOutput:
    writable = access.active and item.status != "closed"
    fields = {
        key: getattr(item, key)
        for key in (
            "id",
            "client_id",
            "queue_id",
            "requester_id",
            "category_id",
            "assignee_id",
            "subject",
            "description",
            "priority",
            "status",
            "source",
            "resolved_at",
            "closed_at",
            "version",
            "created_at",
            "updated_at",
        )
    }
    return TicketOutput.model_validate(
        {
            **fields,
            "number": str(item.number),
            "client_name": item.client.name,
            "queue_name": item.queue.name,
            "requester_name": item.requester.display_name,
            "requester_email": item.requester.email_normalized,
            "requester_active": item.requester.active,
            "requester_verification": item.requester.verification_state,
            "category_name": item.category.name if item.category else None,
            "assignee_name": item.assignee.display_name if item.assignee else None,
            "writable": writable,
            "can_update": writable and can_update(item, access, actor_id),
            "can_assign": writable and access.manage,
            "can_claim": writable and access.contribute and item.assignee_id is None,
            "can_read_notes": can_read_notes(access),
            "can_add_note": writable and access.contribute and access.note_access == "write",
            "can_add_message": writable and can_update(item, access, actor_id),
            "allowed_transitions": targets(item, access, actor_id),
        }
    )


def transition(
    db: Session, item: Ticket, access: Access, actor_id: UUID, body: TicketTransition
) -> TicketStatusHistory | None:
    if item.status == body.target_status:
        return None
    require_active(access)
    if body.target_status not in targets(item, access, actor_id):
        raise identity.IdentityError(409, "invalid_ticket_transition")
    if body.target_status in {
        "pending_customer",
        "pending_third_party",
        "resolved",
    } or (body.target_status == "open" and item.status in {"resolved", "closed"}):
        if not body.reason:
            raise identity.IdentityError(422, "ticket_reason_required")
    old = item.status
    advance(item)
    item.status = body.target_status
    if item.status == "resolved":
        item.resolved_at = item.updated_at
    elif item.status == "closed":
        item.closed_at = item.updated_at
    elif old in {"resolved", "closed"}:
        item.resolved_at = item.closed_at = None
    history = TicketStatusHistory(
        ticket_id=item.id,
        actor_id=actor_id,
        from_status=old,
        to_status=item.status,
        reason=body.reason,
        version=item.version,
        occurred_at=item.updated_at,
    )
    db.add(history)
    db.flush()
    return history


def filtered(query: Select[Any], filters: TicketFilters) -> Select[Any]:
    for key in ("queue_id", "client_id", "status", "priority", "assignee_id"):
        value = getattr(filters, key)
        if value is not None:
            query = query.where(getattr(Ticket, key) == value)
    if filters.unassigned:
        query = query.where(Ticket.assignee_id.is_(None))
    if filters.q:
        query = query.where(
            literal_column(SEARCH_DOCUMENT).op("@@")(
                func.websearch_to_tsquery(literal_column("'portuguese'::regconfig"), filters.q)
            )
        )
    return query
