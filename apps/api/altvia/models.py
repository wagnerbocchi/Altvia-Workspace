from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from altvia.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("auth_version > 0", name="ck_user_auth_version"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email_normalized: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    auth_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    auth_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(50), primary_key=True)


class RoleBinding(Base):
    __tablename__ = "role_bindings"
    __table_args__ = (
        CheckConstraint(
            "(scope_kind = 'global' AND team_id IS NULL AND role_name = 'platform_admin') OR "
            "(scope_kind = 'team' AND team_id IS NOT NULL "
            "AND role_name IN ('viewer','operations_manager'))",
            name="ck_role_binding_scope",
        ),
        Index(
            "uq_role_bindings_global",
            "user_id",
            "role_name",
            unique=True,
            postgresql_where=text("scope_kind = 'global'"),
        ),
        Index(
            "uq_role_bindings_team",
            "user_id",
            "role_name",
            "team_id",
            unique=True,
            postgresql_where=text("scope_kind = 'team'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role_name: Mapped[str] = mapped_column(ForeignKey("roles.name"))
    scope_kind: Mapped[str] = mapped_column(String(20), default="global")
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[UUID | None]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    correlation_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_outbox_attempts"),
        CheckConstraint(
            "status IN ('pending','processing','delivered','dead')", name="ck_outbox_status"
        ),
    )
    event_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[UUID]
    aggregate_version: Mapped[int]
    event_type: Mapped[str] = mapped_column(String(80))
    schema_version: Mapped[int] = mapped_column(default=1)
    payload: Mapped[dict[str, str | None]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(50))


class LoginBucket(Base):
    __tablename__ = "login_buckets"
    __table_args__ = (CheckConstraint("attempts > 0", name="ck_login_attempts"),)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    attempts: Mapped[int]


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_team_name"),
        CheckConstraint("version > 0", name="ck_team_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamMember(Base):
    __tablename__ = "team_members"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint("key ~ '^[A-Za-z0-9._:-]{1,128}$'", name="ck_idempotency_key"),
        CheckConstraint("status_code BETWEEN 200 AND 299", name="ck_idempotency_status"),
        CheckConstraint(
            "expires_at >= created_at + INTERVAL '168 hours'", name="ck_idempotency_retention"
        ),
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    route: Mapped[str] = mapped_column(String(160), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int]
    result: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    consumer: Mapped[str] = mapped_column(String(50), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("outbox_events.event_id"), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        CheckConstraint("aggregate_version > 0", name="ck_activity_version"),
        CheckConstraint("resource_type IN ('identity','team')", name="ck_activity_resource"),
        CheckConstraint("actor_kind IN ('user','management_command')", name="ck_activity_actor"),
        Index("ix_activity_order", "occurred_at", "event_id"),
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("outbox_events.event_id"), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[UUID]
    event_type: Mapped[str] = mapped_column(String(80))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[UUID | None]
    actor_kind: Mapped[str] = mapped_column(String(30))
    aggregate_version: Mapped[int]
    correlation_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, str]] = mapped_column(JSONB)
