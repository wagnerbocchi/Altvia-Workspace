"""Work invariants reuse project authority; assignment is never a content grant."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, and_, false, or_, select, text, true
from sqlalchemy.orm import Session

from altvia import identity, project_registry
from altvia.deadlines import due_output as due_output
from altvia.deadlines import set_due as set_due
from altvia.models import (
    Client,
    ClientAccessGrant,
    Project,
    ProjectMember,
    RoleBinding,
    Team,
    User,
    WorkItem,
    WorkStatusHistory,
)
from altvia.work_schemas import (
    WORK_TRANSITIONS,
    Candidate,
    Transition,
    WorkOutput,
)


@dataclass(frozen=True)
class Access:
    project: Project
    manage: bool
    contribute: bool
    writable: bool


def candidates(project: Project) -> Select[tuple[User]]:
    direct = (
        select(RoleBinding.id)
        .join(
            ProjectMember,
            and_(
                ProjectMember.project_id == RoleBinding.project_id,
                ProjectMember.user_id == RoleBinding.user_id,
            ),
        )
        .where(
            RoleBinding.user_id == User.id,
            RoleBinding.project_id == project.id,
            RoleBinding.scope_kind == "project",
            RoleBinding.role_name.in_({"agent", "project_manager"}),
        )
        .correlate(User)
        .exists()
    )
    inherited = (
        select(RoleBinding.id)
        .where(
            RoleBinding.user_id == User.id,
            RoleBinding.scope_kind == "client",
            RoleBinding.client_id == project.client_id,
            RoleBinding.role_name == "operations_manager",
        )
        .correlate(User)
        .exists()
        if project.client_id
        else false()
    )
    ceiling = (
        select(ClientAccessGrant.user_id)
        .where(
            ClientAccessGrant.user_id == User.id,
            ClientAccessGrant.client_id == project.client_id,
        )
        .correlate(User)
        .exists()
        if project.client_id
        else true()
    )
    return select(User).where(User.active.is_(True), or_(direct, inherited), ceiling)


def access(db: Session, user_id: UUID, project_id: UUID, *, write: bool = False) -> Access:
    project, manage = project_registry.scoped_project(db, user_id, project_id)
    contribute = manage or db.scalar(candidates(project).where(User.id == user_id)) is not None
    if write:
        if not contribute:
            raise identity.IdentityError(403, "forbidden")
        # Same key as the database trigger; always before a work row lock.
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
            {"scope": "altvia:work-graph:" + str(project_id)},
        )
    team = db.get(Team, project.team_id)
    customer = db.get(Client, project.client_id) if project.client_id else None
    writable = bool(
        project.active
        and team is not None
        and team.active
        and (project.client_id is None or (customer is not None and customer.active))
    )
    return Access(project, manage, contribute, writable)


def require_active(db: Session, permission: Access) -> None:
    if not permission.writable:
        raise identity.IdentityError(409, "project_inactive")


def scoped_work(
    db: Session, user_id: UUID, identifier: UUID, *, write: bool = False
) -> tuple[WorkItem, Access]:
    project_id = db.scalar(select(WorkItem.project_id).where(WorkItem.id == identifier))
    if project_id is None:
        raise identity.IdentityError(404, "not_found")
    permission = access(db, user_id, project_id, write=write)
    query = select(WorkItem).where(WorkItem.id == identifier)
    if write:
        query = query.with_for_update(of=WorkItem)
    item = db.scalars(query).one()
    return item, permission


def can_update(item: WorkItem, permission: Access, user_id: UUID) -> bool:
    return permission.manage or (
        permission.contribute
        and (item.owner_id == user_id or user_id in {row.user_id for row in item.assignees})
    )


def require_update(item: WorkItem, permission: Access, user_id: UUID) -> None:
    if not can_update(item, permission, user_id):
        raise identity.IdentityError(403, "forbidden")


def validate_assignments(
    db: Session, permission: Access, owner: UUID | None, assignees: list[UUID]
) -> dict[UUID, User]:
    identifiers = set(assignees) | ({owner} if owner else set())
    if identifiers:
        allowed = {
            user.id: user
            for user in db.scalars(candidates(permission.project).where(User.id.in_(identifiers)))
        }
        if set(allowed) != identifiers:
            raise identity.IdentityError(422, "invalid_contributor")
        return allowed
    return {}


def validate_parent(db: Session, item: WorkItem) -> None:
    if item.parent_id is None:
        return
    if item.parent_id == item.id:
        raise identity.IdentityError(409, "parent_cycle")
    parent = db.scalar(
        select(WorkItem).where(
            WorkItem.id == item.parent_id, WorkItem.project_id == item.project_id
        )
    )
    if parent is None:
        raise identity.IdentityError(422, "invalid_parent")
    cycle = db.scalar(
        text("""WITH RECURSIVE ancestors AS (
        SELECT id,parent_id FROM work_items WHERE id=:parent
        UNION SELECT w.id,w.parent_id FROM work_items w JOIN ancestors a ON w.id=a.parent_id
    ) SELECT EXISTS(SELECT 1 FROM ancestors WHERE id=:id)"""),
        {"parent": item.parent_id, "id": item.id},
    )
    if cycle:
        raise identity.IdentityError(409, "parent_cycle")


def output(item: WorkItem, permission: Access, user_id: UUID) -> WorkOutput:
    return WorkOutput(
        **{
            field: getattr(item, field)
            for field in WorkOutput.model_fields
            if field
            not in {
                "due",
                "assignee_ids",
                "owner_name",
                "assignees",
                "can_update",
                "can_manage",
                "can_comment",
                "project_writable",
            }
        },
        due=due_output(item),
        project_writable=permission.writable,
        owner_name=item.owner.display_name if item.owner else None,
        assignees=[
            Candidate(id=row.user_id, display_name=row.user.display_name)
            for row in sorted(item.assignees, key=lambda row: str(row.user_id))
        ],
        assignee_ids=sorted((row.user_id for row in item.assignees), key=str),
        can_update=can_update(item, permission, user_id),
        can_manage=permission.manage,
        can_comment=permission.contribute,
    )


def advance(item: WorkItem) -> None:
    if item.version >= 2147483647:
        raise identity.IdentityError(409, "version_exhausted")
    item.version += 1
    item.updated_at = datetime.now(UTC)


def transition(
    db: Session, item: WorkItem, permission: Access, actor: UUID, body: Transition
) -> bool:
    if item.status == body.target_status:
        return False
    reason = body.reason.strip() if body.reason else None
    if (
        body.target_status not in WORK_TRANSITIONS[item.status]
        or (item.status == "cancelled" and not permission.manage)
        or (
            (item.status in {"done", "cancelled"} or body.target_status == "blocked") and not reason
        )
        or (
            item.work_type == "ongoing"
            and body.target_status == "done"
            and not (body.end_operation and reason)
        )
    ):
        raise identity.IdentityError(409, "invalid_transition")
    old = item.status
    item.status = body.target_status
    item.blocked_reason = reason if item.status == "blocked" else None
    now = datetime.now(UTC)
    if item.status == "in_progress" and item.started_at is None:
        item.started_at = now
    item.completed_at = now if item.status == "done" else None
    advance(item)
    db.add(
        WorkStatusHistory(
            work_item_id=item.id,
            actor_id=actor,
            from_status=old,
            to_status=item.status,
            reason=reason,
            version=item.version,
            occurred_at=now,
        )
    )
    return True
