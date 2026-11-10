"""Project ownership: customer ceiling, explicit project membership or client role."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Exists

from altvia import client_registry, identity
from altvia.management import _invalidate_sessions, _locked_user, lock_identity_writes
from altvia.models import (
    Client,
    ClientAccessGrant,
    OperationalArea,
    Project,
    ProjectMember,
    Role,
    RoleBinding,
    Team,
    User,
)

PROJECT_ROLES = frozenset({"viewer", "agent", "project_manager"})


def visible_projects(user_id: UUID) -> Select[tuple[Project, bool]]:
    def direct(roles: set[str] | frozenset[str]) -> Exists:
        return (
            select(RoleBinding.id)
            .join(
                ProjectMember,
                and_(
                    ProjectMember.project_id == RoleBinding.project_id,
                    ProjectMember.user_id == RoleBinding.user_id,
                ),
            )
            .where(
                RoleBinding.user_id == user_id,
                RoleBinding.scope_kind == "project",
                RoleBinding.project_id == Project.id,
                RoleBinding.role_name.in_(roles),
            )
            .correlate(Project)
            .exists()
        )

    def inherited(roles: set[str]) -> Exists:
        return (
            select(RoleBinding.id)
            .where(
                RoleBinding.user_id == user_id,
                RoleBinding.scope_kind == "client",
                RoleBinding.client_id == Project.client_id,
                RoleBinding.role_name.in_(roles),
            )
            .correlate(Project)
            .exists()
        )

    ceiling = (
        select(ClientAccessGrant.user_id)
        .where(
            ClientAccessGrant.user_id == user_id, ClientAccessGrant.client_id == Project.client_id
        )
        .correlate(Project)
        .exists()
    )
    manage = or_(direct({"project_manager"}), inherited({"operations_manager"}))
    return select(Project, manage.label("can_manage")).where(
        or_(Project.client_id.is_(None), ceiling),
        or_(direct(PROJECT_ROLES), inherited({"viewer", "operations_manager"})),
    )


def scoped_project(
    db: Session, user_id: UUID, project_id: UUID, *, write: bool = False
) -> tuple[Project, bool]:
    query = visible_projects(user_id).where(Project.id == project_id)
    if write:
        query = query.with_for_update(of=Project)
    row = db.execute(query).one_or_none()
    if row is None:
        raise identity.IdentityError(404, "not_found")
    project, manage = row
    if write and not manage:
        raise identity.IdentityError(403, "forbidden")
    return project, manage


def advance(resource: Project | OperationalArea) -> None:
    if resource.version >= 2147483647:
        raise identity.IdentityError(409, "version_exhausted")
    resource.version += 1
    resource.updated_at = datetime.now(UTC)


def active_area(db: Session, identifier: UUID) -> OperationalArea:
    area = db.get(OperationalArea, identifier)
    if area is None or not area.active:
        raise identity.IdentityError(422, "invalid_operational_area")
    return area


def unique_area_name(db: Session, name: str, except_id: UUID | None = None) -> None:
    query = select(OperationalArea.id).where(OperationalArea.name == name)
    if except_id is not None:
        query = query.where(OperationalArea.id != except_id)
    if db.scalar(query) is not None:
        raise identity.IdentityError(409, "area_name_exists")


def creation_authority(
    db: Session, actor: User, client_id: UUID | None, team_id: UUID, manager_id: UUID
) -> None:
    if "identity.manage" in identity.capabilities(db, actor):
        return
    if client_id is None or manager_id != actor.id:
        raise identity.IdentityError(403, "forbidden")
    client_registry.scoped_client(db, actor.id, client_id, write=True)
    team_role = db.scalar(
        select(RoleBinding.id).where(
            RoleBinding.user_id == actor.id,
            RoleBinding.scope_kind == "team",
            RoleBinding.team_id == team_id,
            RoleBinding.role_name.in_({"viewer", "operations_manager"}),
        )
    )
    if team_role is None:
        raise identity.IdentityError(404, "not_found")


def _change_access(db: Session, user: User, project: Project, role: str | None) -> bool:
    binding = db.scalar(
        select(RoleBinding).where(
            RoleBinding.user_id == user.id,
            RoleBinding.scope_kind == "project",
            RoleBinding.project_id == project.id,
        )
    )
    member = db.get(ProjectMember, (project.id, user.id))
    if (role is None and binding is None and member is None) or (
        role is not None
        and binding is not None
        and binding.role_name == role
        and member is not None
    ):
        return False
    if role is not None:
        if not user.active or not project.active:
            raise identity.IdentityError(
                409, "account_inactive" if not user.active else "project_inactive"
            )
        if project.client_id is not None:
            client = db.get(Client, project.client_id)
            if client is None or not client.active:
                raise identity.IdentityError(409, "client_inactive")
            if db.get(ClientAccessGrant, (user.id, project.client_id)) is None:
                raise identity.IdentityError(422, "client_access_required")
        db.execute(insert(Role).values(name=role).on_conflict_do_nothing())
        if binding is None:
            db.add(
                RoleBinding(
                    user_id=user.id, role_name=role, scope_kind="project", project_id=project.id
                )
            )
        else:
            binding.role_name = role
        if member is None:
            db.add(ProjectMember(project_id=project.id, user_id=user.id))
    else:
        if binding is not None:
            db.delete(binding)
        if member is not None:
            db.delete(member)
    _invalidate_sessions(db, user, datetime.now(UTC))
    return True


def create_project(
    db: Session,
    actor: User,
    name: str,
    scope_kind: str,
    client_id: UUID | None,
    team_id: UUID,
    area_id: UUID | None,
    manager_id: UUID,
    correlation_id: str,
) -> Project:
    lock_identity_writes(db)
    team = db.get(Team, team_id)
    if team is None or not team.active:
        raise identity.IdentityError(422, "invalid_project_team")
    if client_id is not None:
        client = db.get(Client, client_id)
        if client is None or not client.active:
            raise identity.IdentityError(422, "invalid_project_client")
    if area_id is not None:
        active_area(db, area_id)
    manager = db.scalar(select(User).where(User.id == manager_id).with_for_update(key_share=True))
    if manager is None or not manager.active:
        raise identity.IdentityError(422, "invalid_initial_manager")
    now = datetime.now(UTC)
    project = Project(
        name=name,
        scope_kind=scope_kind,
        client_id=client_id,
        team_id=team_id,
        operational_area_id=area_id,
        active=True,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.flush()
    _change_access(db, manager, project, "project_manager")
    identity.record_event(
        db,
        actor.id,
        project.id,
        "project.created",
        now,
        correlation_id,
        1,
        aggregate_type="project",
        details={"manager_user_id": str(manager_id)},
    )
    return project


def set_project_access(db: Session, email: str, project_id: UUID, role: str | None) -> bool:
    if role is not None and role not in PROJECT_ROLES:
        raise identity.IdentityError(422, "invalid_project_role")
    lock_identity_writes(db)
    user = _locked_user(db, email)
    project = db.scalar(select(Project).where(Project.id == project_id).with_for_update(of=Project))
    if project is None:
        raise identity.IdentityError(404, "not_found")
    if not _change_access(db, user, project, role):
        return False
    advance(project)
    identity.record_event(
        db,
        None,
        project.id,
        "project.access_changed",
        datetime.now(UTC),
        uuid4().hex,
        project.version,
        aggregate_type="project",
        details={"member_user_id": str(user.id), "role_name": role or "none"},
    )
    return True
