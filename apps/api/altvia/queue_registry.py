"""Ownership and serialization of queue configuration metadata."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Exists

from altvia import identity
from altvia.models import RoleBinding, Team, TicketCategory, TicketQueue


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
    return select(TicketQueue, teams.c.name, teams.c.active, teams.c.can_manage).join(
        teams, teams.c.id == TicketQueue.team_id
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
        team_id = db.scalar(query.with_only_columns(TicketQueue.team_id))
        if team_id is None:
            raise identity.IdentityError(404, "not_found")
        scoped_team(db, user_id, team_id, write=True)
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
