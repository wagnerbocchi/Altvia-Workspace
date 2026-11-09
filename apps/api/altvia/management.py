from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from altvia.identity import PASSWORDS, IdentityError, normalize_email, record_event
from altvia.models import Role, RoleBinding, SessionRecord, Team, User
from altvia.policy import TEAM_READ_ROLES


def hash_new_password(password: str) -> str:
    if not 14 <= len(password) or len(password.encode()) > 1024:
        raise IdentityError(422, "password_length_invalid")
    return PASSWORDS.hash(password)


def lock_identity_writes(db: Session) -> None:
    # Shared with one-time bootstrap: active-admin checks must serialize.
    db.execute(text("SELECT pg_advisory_xact_lock(723504391)"))


def _new_user(email: str, display_name: str, password: str) -> User:
    email = normalize_email(email)
    display_name = display_name.strip()
    if not 1 <= len(display_name) <= 150:
        raise IdentityError(422, "display_name_invalid")
    password_hash = hash_new_password(password)
    return User(
        email_normalized=email,
        display_name=display_name,
        password_hash=password_hash,
        active=True,
        auth_version=1,
        created_at=datetime.now(UTC),
    )


def _insert_user(db: Session, user: User) -> None:
    if db.scalar(select(User.id).where(User.email_normalized == user.email_normalized)):
        raise IdentityError(409, "account_already_exists")
    db.add(user)
    db.flush()


def create_user(db: Session, email: str, display_name: str, password: str) -> None:
    user = _new_user(email, display_name, password)
    lock_identity_writes(db)
    _insert_user(db, user)
    record_event(db, None, user.id, "identity.user_created", user.created_at, uuid4().hex, 1)


def bootstrap_admin(db: Session, email: str, display_name: str, password: str) -> None:
    user = _new_user(email, display_name, password)
    lock_identity_writes(db)
    if db.scalar(select(RoleBinding).where(RoleBinding.role_name == "platform_admin")):
        raise IdentityError(409, "already_bootstrapped")
    _insert_user(db, user)
    db.execute(insert(Role).values(name="platform_admin").on_conflict_do_nothing())
    db.add(RoleBinding(user_id=user.id, role_name="platform_admin", scope_kind="global"))
    record_event(db, None, user.id, "identity.admin_bootstrapped", user.created_at, uuid4().hex, 1)


def _locked_user(db: Session, email: str) -> User:
    # These operations never change user keys. Allow audit FK key-share locks
    # while waiting for an authenticated request's session lock to be released.
    user = db.scalar(
        select(User)
        .where(User.email_normalized == normalize_email(email))
        .with_for_update(key_share=True)
    )
    if user is None:
        raise IdentityError(404, "account_not_found")
    return user


def _invalidate_sessions(db: Session, user: User, now: datetime) -> None:
    user.auth_version += 1
    db.execute(
        update(SessionRecord)
        .where(SessionRecord.user_id == user.id, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def reset_password(db: Session, email: str, password: str) -> None:
    lock_identity_writes(db)
    user = _locked_user(db, email)
    user.password_hash = hash_new_password(password)
    now = datetime.now(UTC)
    _invalidate_sessions(db, user, now)
    record_event(db, None, user.id, "identity.password_reset", now, uuid4().hex, user.auth_version)


def _is_admin(db: Session, user: User) -> bool:
    return (
        db.scalar(
            select(RoleBinding).where(
                RoleBinding.user_id == user.id,
                RoleBinding.role_name == "platform_admin",
                RoleBinding.scope_kind == "global",
            )
        )
        is not None
    )


def _require_another_admin(db: Session, user: User) -> None:
    another = db.scalar(
        select(User.id)
        .join(RoleBinding)
        .where(
            User.id != user.id,
            User.active.is_(True),
            RoleBinding.role_name == "platform_admin",
            RoleBinding.scope_kind == "global",
        )
        .limit(1)
    )
    if another is None:
        raise IdentityError(409, "last_active_admin")


def set_account_active(db: Session, email: str, active: bool) -> bool:
    lock_identity_writes(db)
    user = _locked_user(db, email)
    if user.active == active:
        return False
    if not active and _is_admin(db, user):
        _require_another_admin(db, user)
    user.active = active
    now = datetime.now(UTC)
    _invalidate_sessions(db, user, now)
    action = "identity.user_enabled" if active else "identity.user_disabled"
    record_event(db, None, user.id, action, now, uuid4().hex, user.auth_version)
    return True


def set_platform_admin(db: Session, email: str, enabled: bool) -> bool:
    lock_identity_writes(db)
    user = _locked_user(db, email)
    if enabled and not user.active:
        raise IdentityError(409, "account_inactive")
    if _is_admin(db, user) == enabled:
        return False
    if enabled:
        db.execute(insert(Role).values(name="platform_admin").on_conflict_do_nothing())
        db.add(RoleBinding(user_id=user.id, role_name="platform_admin", scope_kind="global"))
    else:
        if user.active:
            _require_another_admin(db, user)
        db.execute(
            delete(RoleBinding).where(
                RoleBinding.user_id == user.id,
                RoleBinding.role_name == "platform_admin",
                RoleBinding.scope_kind == "global",
            )
        )
    now = datetime.now(UTC)
    _invalidate_sessions(db, user, now)
    action = "identity.admin_granted" if enabled else "identity.admin_revoked"
    record_event(db, None, user.id, action, now, uuid4().hex, user.auth_version)
    return True


def set_team_role(db: Session, email: str, team_id: UUID, role: str, enabled: bool) -> bool:
    if role not in TEAM_READ_ROLES:
        raise IdentityError(422, "invalid_team_role")
    lock_identity_writes(db)
    user = _locked_user(db, email)
    team = db.scalar(select(Team).where(Team.id == team_id).with_for_update(key_share=True))
    if team is None:
        raise IdentityError(404, "team_not_found")
    if enabled and not user.active:
        raise IdentityError(409, "account_inactive")
    if enabled and not team.active:
        raise IdentityError(409, "team_inactive")
    binding = db.scalar(
        select(RoleBinding).where(
            RoleBinding.user_id == user.id,
            RoleBinding.role_name == role,
            RoleBinding.scope_kind == "team",
            RoleBinding.team_id == team_id,
        )
    )
    if (binding is not None) == enabled:
        return False
    if enabled:
        db.execute(insert(Role).values(name=role).on_conflict_do_nothing())
        db.add(RoleBinding(user_id=user.id, role_name=role, scope_kind="team", team_id=team_id))
    else:
        assert binding is not None
        db.delete(binding)
    now = datetime.now(UTC)
    _invalidate_sessions(db, user, now)
    action = "identity.team_role_granted" if enabled else "identity.team_role_revoked"
    record_event(
        db,
        None,
        user.id,
        action,
        now,
        uuid4().hex,
        user.auth_version,
        details={"team_id": str(team_id), "role_name": role},
    )
    return True
