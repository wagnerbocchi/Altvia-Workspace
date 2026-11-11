"""Ownership and serialization of queue configuration metadata."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Exists

from altvia import identity
from altvia.management import _invalidate_sessions, lock_identity_writes
from altvia.models import Role, RoleBinding, Team, TicketCategory, TicketQueue, User

QUEUE_ROLES = frozenset({"viewer", "agent", "operations_manager"})


def visible_teams(user_id: UUID) -> Select[tuple[Team, bool]]:
    platform = (
        select(RoleBinding.id)
        .where(
            RoleBinding.user_id == user_id,
            RoleBinding.scope_kind == "global",
            RoleBinding.role_name == "platform_admin",
        )
        .exists()
    )

    def bound(roles: set[str]) -> Exists:
        return (
            select(RoleBinding.id)
            .where(
                RoleBinding.user_id == user_id,
                RoleBinding.scope_kind == "team",
                RoleBinding.team_id == Team.id,
                RoleBinding.role_name.in_(roles),
            )
            .correlate(Team)
            .exists()
        )

    manage = or_(platform, bound({"operations_manager"}))
    return select(Team, manage.label("can_manage")).where(
        or_(platform, bound({"operations_manager", "viewer"}))
    )


def visible_queues(user_id: UUID) -> Select[tuple[TicketQueue, str, bool, bool]]:
    teams = visible_teams(user_id).subquery()
    member = (
        select(RoleBinding.id)
        .where(
            RoleBinding.user_id == user_id,
            RoleBinding.scope_kind == "queue",
            RoleBinding.queue_id == TicketQueue.id,
            RoleBinding.role_name.in_(QUEUE_ROLES),
        )
        .correlate(TicketQueue)
        .exists()
    )
    return (
        select(TicketQueue, Team.name, Team.active, func.coalesce(teams.c.can_manage, False))
        .join(Team, Team.id == TicketQueue.team_id)
        .outerjoin(teams, teams.c.id == Team.id)
        .where(or_(teams.c.id.is_not(None), member))
    )


def scoped_team(
    db: Session, user_id: UUID, identifier: UUID, *, write: bool = False
) -> tuple[Team, bool]:
    query = visible_teams(user_id).where(Team.id == identifier)
    if write:
        query = query.with_for_update(of=Team).execution_options(populate_existing=True)
    row = db.execute(query).one_or_none()
    if row is None:
        raise identity.IdentityError(404, "not_found")
    team, manage = row
    if write and not manage:
        raise identity.IdentityError(403, "forbidden")
    return team, manage


def scoped_queue(
    db: Session, user_id: UUID, identifier: UUID, *, write: bool = False
) -> tuple[TicketQueue, str, bool, bool]:
    query = visible_queues(user_id).where(TicketQueue.id == identifier)
    if write:
        reviewed = db.execute(query).one_or_none()
        if reviewed is None:
            raise identity.IdentityError(404, "not_found")
        if not reviewed[3]:
            raise identity.IdentityError(403, "forbidden")
        scoped_team(db, user_id, reviewed[0].team_id, write=True)
        query = query.with_for_update(of=TicketQueue).execution_options(populate_existing=True)
    row = db.execute(query).one_or_none()
    if row is None:
        raise identity.IdentityError(404, "not_found")
    queue, name, active, manage = row
    return queue, name, active, manage


def scoped_category(
    db: Session, queue_id: UUID, identifier: UUID, *, write: bool = False
) -> TicketCategory:
    query = select(TicketCategory).where(
        TicketCategory.id == identifier, TicketCategory.queue_id == queue_id
    )
    if write:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise identity.IdentityError(404, "not_found")
    return row


def queue_access_user(db: Session, queue_id: UUID, user_id: UUID) -> User | None:
    return db.scalar(
        select(User)
        .join(RoleBinding, RoleBinding.user_id == User.id)
        .where(
            User.id == user_id, RoleBinding.scope_kind == "queue", RoleBinding.queue_id == queue_id
        )
        .with_for_update(of=User)
    )


def change_queue_access(
    db: Session,
    target: User,
    queue: TicketQueue,
    team_active: bool,
    role: str | None,
    actor_id: UUID,
    correlation_id: str,
) -> bool:
    """Caller holds configuration authority and the team/queue write locks."""
    lock_identity_writes(db)
    if role is not None and role not in QUEUE_ROLES:
        raise identity.IdentityError(422, "invalid_queue_role")
    binding = db.scalar(
        select(RoleBinding).where(
            RoleBinding.user_id == target.id,
            RoleBinding.scope_kind == "queue",
            RoleBinding.queue_id == queue.id,
        )
    )
    if (binding is None and role is None) or (binding is not None and binding.role_name == role):
        return False
    if role is not None:
        require_active(team_active, queue.active)
        if not target.active:
            raise identity.IdentityError(422, "invalid_queue_member")
        db.execute(insert(Role).values(name=role).on_conflict_do_nothing())
        if binding is None:
            db.add(
                RoleBinding(
                    user_id=target.id, scope_kind="queue", queue_id=queue.id, role_name=role
                )
            )
        else:
            binding.role_name = role
    elif binding is not None:
        db.delete(binding)
    advance(queue)
    now = datetime.now(UTC)
    _invalidate_sessions(db, target, now)
    identity.record_event(
        db,
        actor_id,
        queue.id,
        "ticket_queue.access_changed",
        now,
        correlation_id,
        queue.version,
        aggregate_type="ticket_queue",
        details={"member_user_id": str(target.id), "role_name": role or "removed"},
    )
    return True


def require_active(team_active: bool, queue_active: bool = True) -> None:
    if not team_active or not queue_active:
        raise identity.IdentityError(409, "inactive_parent")


def advance(row: TicketQueue | TicketCategory) -> None:
    if row.version >= 2147483647:
        raise identity.IdentityError(409, "version_exhausted")
    row.version += 1
    row.updated_at = datetime.now(UTC)


def unique_queue_name(db: Session, team_id: UUID, name: str, except_id: UUID | None = None) -> None:
    query = select(TicketQueue.id).where(TicketQueue.team_id == team_id, TicketQueue.name == name)
    if except_id is not None:
        query = query.where(TicketQueue.id != except_id)
    if db.scalar(query) is not None:
        raise identity.IdentityError(409, "name_exists")


def unique_category_name(
    db: Session, queue_id: UUID, name: str, except_id: UUID | None = None
) -> None:
    query = select(TicketCategory.id).where(
        TicketCategory.queue_id == queue_id, TicketCategory.name == name
    )
    if except_id is not None:
        query = query.where(TicketCategory.id != except_id)
    if db.scalar(query) is not None:
        raise identity.IdentityError(409, "name_exists")
