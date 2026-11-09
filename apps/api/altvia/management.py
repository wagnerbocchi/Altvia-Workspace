from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from altvia.identity import PASSWORDS, IdentityError, normalize_email, record_event
from altvia.models import Role, RoleBinding, SessionRecord, User


def hash_new_password(password: str) -> str:
    if not 14 <= len(password) or len(password.encode()) > 1024:
        raise IdentityError(422, "password_length_invalid")
    return PASSWORDS.hash(password)


def bootstrap_admin(db: Session, email: str, display_name: str, password: str) -> None:
    email = normalize_email(email)
    display_name = display_name.strip()
    if not 1 <= len(display_name) <= 150:
        raise IdentityError(422, "display_name_invalid")
    password_hash = hash_new_password(password)
    db.execute(text("SELECT pg_advisory_xact_lock(723504391)"))
    if db.scalar(select(RoleBinding).where(RoleBinding.role_name == "platform_admin")):
        raise IdentityError(409, "already_bootstrapped")
    if db.scalar(select(User).where(User.email_normalized == email)):
        raise IdentityError(409, "account_already_exists")
    db.execute(insert(Role).values(name="platform_admin").on_conflict_do_nothing())
    now = datetime.now(UTC)
    user = User(
        email_normalized=email,
        display_name=display_name,
        password_hash=password_hash,
        active=True,
        auth_version=1,
        created_at=now,
    )
    db.add(user)
    db.flush()
    db.add(RoleBinding(user_id=user.id, role_name="platform_admin", scope_kind="global"))
    record_event(db, None, user.id, "identity.admin_bootstrapped", now, uuid4().hex, 1)


def reset_password(db: Session, email: str, password: str) -> None:
    user = db.scalar(
        select(User).where(User.email_normalized == normalize_email(email)).with_for_update()
    )
    if user is None:
        raise IdentityError(404, "account_not_found")
    user.password_hash = hash_new_password(password)
    user.auth_version += 1
    now = datetime.now(UTC)
    db.execute(
        update(SessionRecord)
        .where(SessionRecord.user_id == user.id, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    record_event(db, None, user.id, "identity.password_reset", now, uuid4().hex, user.auth_version)
