"""Client content ownership: explicit ceiling plus client role, never global bypass."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from altvia.identity import IdentityError, record_event
from altvia.management import _invalidate_sessions, _locked_user, lock_identity_writes
from altvia.models import Client, ClientAccessGrant, Role, RoleBinding, User

CLIENT_ROLES = frozenset({"viewer", "operations_manager"})


def visible_clients(user_id: UUID) -> Select[tuple[Client, str]]:
    return (
        select(Client, RoleBinding.role_name)
        .join(ClientAccessGrant, ClientAccessGrant.client_id == Client.id)
        .join(RoleBinding, RoleBinding.client_id == Client.id)
        .where(
            ClientAccessGrant.user_id == user_id,
            RoleBinding.user_id == user_id,
            RoleBinding.scope_kind == "client",
            RoleBinding.role_name.in_(CLIENT_ROLES),
        )
    )


def scoped_client(
    db: Session, user_id: UUID, client_id: UUID, *, write: bool = False
) -> tuple[Client, str]:
    query = visible_clients(user_id).where(Client.id == client_id)
    if write:
        query = query.with_for_update(of=Client)
    row = db.execute(query).one_or_none()
    if row is None:
        raise IdentityError(404, "not_found")
    client, role = row
    if write and role != "operations_manager":
        raise IdentityError(403, "forbidden")
    return client, role


def advance(client: Client) -> None:
    if client.version >= 2147483647:
        raise IdentityError(409, "version_exhausted")
    client.version += 1
    client.updated_at = datetime.now(UTC)


def _change_access(
    db: Session, user: User, client: Client, role: str | None, actor_id: UUID | None
) -> bool:
    binding = db.scalar(
        select(RoleBinding).where(
            RoleBinding.user_id == user.id,
            RoleBinding.client_id == client.id,
            RoleBinding.scope_kind == "client",
        )
    )
    grant = db.get(ClientAccessGrant, (user.id, client.id))
    if role is not None and (not user.active or not client.active):
        raise IdentityError(409, "account_inactive" if not user.active else "client_inactive")
    if role is None and binding is None and grant is None:
        return False
    if role is not None and binding is not None and binding.role_name == role and grant is not None:
        return False
    now = datetime.now(UTC)
    if role is None:
        if binding is not None:
            db.delete(binding)
        if grant is not None:
            db.delete(grant)
    else:
        db.execute(insert(Role).values(name=role).on_conflict_do_nothing())
        if binding is None:
            db.add(
                RoleBinding(
                    user_id=user.id, role_name=role, scope_kind="client", client_id=client.id
                )
            )
        else:
            binding.role_name = role
        if grant is None:
            db.add(
                ClientAccessGrant(
                    user_id=user.id, client_id=client.id, granted_by=actor_id, created_at=now
                )
            )
    _invalidate_sessions(db, user, now)
    return True


def create_client(
    db: Session, name: str, manager_id: UUID, actor: User, correlation_id: str
) -> Client:
    lock_identity_writes(db)
    manager = db.scalar(select(User).where(User.id == manager_id).with_for_update(key_share=True))
    if manager is None or not manager.active:
        raise IdentityError(422, "invalid_initial_manager")
    now = datetime.now(UTC)
    client = Client(name=name, active=True, version=1, created_at=now, updated_at=now)
    db.add(client)
    db.flush()
    _change_access(db, manager, client, "operations_manager", actor.id)
    record_event(
        db,
        actor.id,
        client.id,
        "client.created",
        now,
        correlation_id,
        1,
        aggregate_type="client",
        details={"manager_user_id": str(manager_id)},
    )
    return client


def set_client_access(db: Session, email: str, client_id: UUID, role: str | None) -> bool:
    if role is not None and role not in CLIENT_ROLES:
        raise IdentityError(422, "invalid_client_role")
    lock_identity_writes(db)
    user = _locked_user(db, email)
    client = db.scalar(select(Client).where(Client.id == client_id).with_for_update())
    if client is None:
        raise IdentityError(404, "not_found")
    if not _change_access(db, user, client, role, None):
        return False
    advance(client)
    record_event(
        db,
        None,
        client.id,
        "client.access_changed",
        client.updated_at,
        uuid4().hex,
        client.version,
        aggregate_type="client",
        details={"member_user_id": str(user.id), "role_name": role or "none"},
    )
    return True
