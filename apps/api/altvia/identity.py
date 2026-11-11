import hashlib
import hmac
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from altvia.models import AuditLog, LoginBucket, OutboxEvent, RoleBinding, SessionRecord, User

PASSWORDS = PasswordHasher(memory_cost=65536, time_cost=3, parallelism=1)
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))
HASH_SLOTS = BoundedSemaphore(2)
COOKIE_NAME = "__Host-altvia_session"


def normalize_email(value: str) -> str:
    value = value.strip().casefold()
    if value.count("@") != 1 or any(c.isspace() for c in value):
        raise ValueError("Invalid email")
    local, domain = value.split("@")
    if not local or not domain or "." not in domain or len(value) > 254:
        raise ValueError("Invalid email")
    return value


class IdentityError(Exception):
    def __init__(self, status: int, code: str, retry_after: int | None = None):
        self.status, self.code, self.retry_after = status, code, retry_after


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b"altvia-csrf-v1", hashlib.sha256).hexdigest()


def record_event(
    db: Session,
    actor_id: UUID | None,
    resource_id: UUID,
    event: str,
    now: datetime,
    correlation_id: str,
    version: int,
    *,
    aggregate_type: str = "identity",
    details: Mapping[str, str | None] | None = None,
) -> None:
    metadata = dict(details or {})
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=event,
            resource_id=resource_id,
            occurred_at=now,
            correlation_id=correlation_id,
            details={**metadata, "actor_kind": "user" if actor_id else "management_command"},
        )
    )
    db.add(
        OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=resource_id,
            aggregate_version=version,
            event_type=event,
            schema_version=1,
            payload={
                **metadata,
                "actor_id": str(actor_id) if actor_id else None,
                "actor_kind": "user" if actor_id else "management_command",
            },
            occurred_at=now,
            correlation_id=correlation_id,
            status="pending",
            attempts=0,
            next_attempt_at=now,
        )
    )


def charge_login_attempt(db: Session, email: str, source: str, now: datetime) -> None:
    window = int(now.timestamp()) // 600
    db.execute(delete(LoginBucket).where(LoginBucket.window < window - 1))
    exceeded = False
    # Stable lock order avoids account/IP bucket deadlocks under concurrency.
    for key, limit in sorted(((digest("account:" + email), 8), (digest("source:" + source), 40))):
        statement = insert(LoginBucket).values(key=key, window=window, attempts=1)
        upsert = statement.on_conflict_do_update(
            index_elements=[LoginBucket.key, LoginBucket.window],
            set_={"attempts": LoginBucket.attempts + 1},
        ).returning(LoginBucket.attempts)
        attempts = db.scalar(upsert)
        exceeded = exceeded or (attempts is not None and attempts > limit)
    db.commit()  # Failed credentials must not roll back rate-control accounting.
    if exceeded:
        raise IdentityError(429, "login_rate_limited", (window + 1) * 600 - int(now.timestamp()))


def login(
    db: Session,
    email: str,
    password: str,
    source: str,
    correlation_id: str,
) -> tuple[User, SessionRecord, str]:
    now = datetime.now(UTC)
    charge_login_attempt(db, email, source, now)
    if not HASH_SLOTS.acquire(blocking=False):
        raise IdentityError(503, "authentication_busy", 1)
    try:
        user = db.scalar(select(User).where(User.email_normalized == email).with_for_update())
        valid = False
        try:
            valid = PASSWORDS.verify(user.password_hash if user else DUMMY_HASH, password)
        except VerificationError:
            pass
        if not user or not user.active or not valid:
            db.add(
                AuditLog(
                    actor_id=None,
                    action="identity.login_rejected",
                    resource_id=None,
                    occurred_at=now,
                    correlation_id=correlation_id,
                    details={},
                )
            )
            db.commit()
            raise IdentityError(401, "invalid_credentials")
        if PASSWORDS.check_needs_rehash(user.password_hash):
            user.password_hash = PASSWORDS.hash(password)
        token = secrets.token_urlsafe(32)
        session = SessionRecord(
            user_id=user.id,
            token_hash=digest(token),
            csrf_hash=digest(csrf_token(token)),
            auth_version=user.auth_version,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=12),
        )
        db.add(session)
        db.flush()
        record_event(
            db,
            user.id,
            session.id,
            "identity.session_created",
            now,
            correlation_id,
            user.auth_version,
        )
        db.commit()
        return user, session, token
    finally:
        HASH_SLOTS.release()


def authenticate(db: Session, token: str | None) -> tuple[User, SessionRecord]:
    if not token or len(token) != 43:
        raise IdentityError(401, "authentication_required")
    row = db.execute(
        select(User, SessionRecord)
        .join(SessionRecord, SessionRecord.user_id == User.id)
        .where(SessionRecord.token_hash == digest(token))
        .with_for_update(of=SessionRecord)
    ).one_or_none()
    now = datetime.now(UTC)
    if row is None:
        raise IdentityError(401, "authentication_required")
    user, session = row
    if (
        not user.active
        or user.auth_version != session.auth_version
        or session.revoked_at is not None
        or session.expires_at <= now
        or session.last_seen_at + timedelta(minutes=30) <= now
    ):
        raise IdentityError(401, "authentication_required")
    session.last_seen_at = now
    return user, session


def capabilities(db: Session, user: User) -> list[str]:
    admin = db.scalar(
        select(RoleBinding).where(
            RoleBinding.user_id == user.id,
            RoleBinding.role_name == "platform_admin",
            RoleBinding.scope_kind == "global",
        )
    )
    # A platform role never confers customer-content permissions.
    return ["identity.manage"] if admin else []
