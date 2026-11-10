from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
            "(scope_kind = 'global' AND team_id IS NULL AND client_id IS NULL "
            "AND project_id IS NULL AND role_name = 'platform_admin') OR "
            "(scope_kind = 'team' AND team_id IS NOT NULL AND client_id IS NULL "
            "AND project_id IS NULL AND role_name IN ('viewer','operations_manager')) OR "
            "(scope_kind = 'client' AND client_id IS NOT NULL AND team_id IS NULL "
            "AND project_id IS NULL AND role_name IN ('viewer','operations_manager')) OR "
            "(scope_kind = 'project' AND project_id IS NOT NULL AND team_id IS NULL "
            "AND client_id IS NULL AND role_name IN ('viewer','agent','project_manager'))",
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
        Index(
            "uq_role_bindings_client",
            "user_id",
            "client_id",
            unique=True,
            postgresql_where=text("scope_kind = 'client'"),
        ),
        Index(
            "uq_role_bindings_project",
            "user_id",
            "project_id",
            unique=True,
            postgresql_where=text("scope_kind = 'project'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role_name: Mapped[str] = mapped_column(ForeignKey("roles.name"))
    scope_kind: Mapped[str] = mapped_column(String(20), default="global")
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"))
    client_id: Mapped[UUID | None] = mapped_column(ForeignKey("clients.id"))
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"))


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


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_client_name"),
        CheckConstraint("version > 0", name="ck_client_version"),
        ForeignKeyConstraint(
            ["default_project_id", "id"],
            ["projects.id", "projects.client_id"],
            name="fk_client_default_project",
            use_alter=True,
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150))
    default_project_id: Mapped[UUID | None] = mapped_column()
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClientContact(Base):
    __tablename__ = "client_contacts"
    __table_args__ = (
        UniqueConstraint("client_id", "email_normalized", name="uq_contact_client_email"),
        Index("ix_client_contacts_page", "client_id", "id"),
        CheckConstraint("char_length(btrim(display_name)) > 0", name="ck_contact_name"),
        CheckConstraint("version > 0", name="ck_contact_version"),
        CheckConstraint("verification_state='unverified'", name="ck_contact_verification"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    display_name: Mapped[str] = mapped_column(String(150))
    email_normalized: Mapped[str] = mapped_column(String(254))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    verification_state: Mapped[str] = mapped_column(String(20), default="unverified")
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientAccessGrant(Base):
    __tablename__ = "client_access_grants"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"), primary_key=True)
    granted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OperationalArea(Base):
    __tablename__ = "operational_areas"
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_area_name"),
        CheckConstraint("version > 0", name="ck_area_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("id", "client_id", name="uq_project_client"),
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_project_name"),
        CheckConstraint("version > 0", name="ck_project_version"),
        CheckConstraint(
            "(scope_kind='internal' AND client_id IS NULL) OR "
            "(scope_kind='client' AND client_id IS NOT NULL)",
            name="ck_project_scope",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(default=1)
    scope_kind: Mapped[str] = mapped_column(String(20))
    client_id: Mapped[UUID | None] = mapped_column(ForeignKey("clients.id"), index=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    operational_area_id: Mapped[UUID | None] = mapped_column(ForeignKey("operational_areas.id"))
    operational_area: Mapped[OperationalArea | None] = relationship(lazy="joined")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectMember(Base):
    __tablename__ = "project_members"
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_work_project"),
        ForeignKeyConstraint(
            ["parent_id", "project_id"],
            ["work_items.id", "work_items.project_id"],
            name="fk_work_parent_project",
        ),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_work_parent"),
        CheckConstraint("char_length(btrim(title)) BETWEEN 1 AND 300", name="ck_work_title"),
        CheckConstraint("char_length(description) <= 20000", name="ck_work_description"),
        CheckConstraint(
            "status IN ('todo','in_progress','blocked','done','cancelled')", name="ck_work_status"
        ),
        CheckConstraint("work_type IN ('one_off','ongoing')", name="ck_work_type"),
        CheckConstraint("priority IN ('low','medium','high','critical')", name="ck_work_priority"),
        CheckConstraint("version > 0", name="ck_work_version"),
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes >= 0", name="ck_work_estimate"
        ),
        CheckConstraint(
            "(status='blocked' AND blocked_reason IS NOT NULL "
            "AND char_length(btrim(blocked_reason)) BETWEEN 1 AND 2000) "
            "OR (status<>'blocked' AND blocked_reason IS NULL)",
            name="ck_work_block",
        ),
        CheckConstraint(
            "(status='done' AND completed_at IS NOT NULL) "
            "OR (status<>'done' AND completed_at IS NULL)",
            name="ck_work_completion",
        ),
        CheckConstraint(
            "(due_at IS NULL AND due_precision IS NULL "
            "AND due_date_local IS NULL AND due_timezone IS NULL) "
            "OR (due_at IS NOT NULL AND due_precision IS NOT NULL AND due_precision='date' "
            "AND due_date_local IS NOT NULL AND due_timezone IS NOT NULL) "
            "OR (due_at IS NOT NULL AND due_precision IS NOT NULL AND due_precision='instant' "
            "AND due_date_local IS NULL AND due_timezone IS NULL)",
            name="ck_work_due",
        ),
        Index("ix_work_project_id", "project_id", "id"),
        Index("ix_work_project_status_id", "project_id", "status", "id"),
        Index("ix_work_owner_page", "owner_id", "id"),
        Index(
            "ix_work_search",
            text(
                # Match pg_get_indexdef's canonical casts/parentheses so
                # Alembic can compare the expression without false drift.
                "to_tsvector('portuguese'::regconfig, "
                "(coalesce(title, ''::character varying)::text || ' '::text) "
                "|| coalesce(description, ''::text))"
            ),
            postgresql_using="gin",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    parent_id: Mapped[UUID | None] = mapped_column()
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    owner: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[owner_id])
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="todo")
    work_type: Mapped[str] = mapped_column(String(20), default="one_off")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    blocked_reason: Mapped[str | None] = mapped_column(String(2000))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_precision: Mapped[str | None] = mapped_column(String(10))
    due_date_local: Mapped[date | None] = mapped_column(Date)
    due_timezone: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_minutes: Mapped[int | None] = mapped_column()
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    assignees: Mapped[list["WorkAssignee"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )


class WorkAssignee(Base):
    __tablename__ = "work_item_assignees"
    __table_args__ = (Index("ix_work_assignee_page", "user_id", "work_item_id"),)
    work_item_id: Mapped[UUID] = mapped_column(ForeignKey("work_items.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    user: Mapped[User] = relationship(lazy="joined")


class WorkComment(Base):
    __tablename__ = "work_item_comments"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(body)) BETWEEN 1 AND 10000", name="ck_work_comment_body"
        ),
        Index("ix_work_comment_page", "work_item_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    work_item_id: Mapped[UUID] = mapped_column(ForeignKey("work_items.id"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkStatusHistory(Base):
    __tablename__ = "work_item_status_history"
    __table_args__ = (UniqueConstraint("work_item_id", "version", name="uq_work_status_version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    work_item_id: Mapped[UUID] = mapped_column(ForeignKey("work_items.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(2000))
    version: Mapped[int] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
        CheckConstraint(
            "resource_type IN "
            "('identity','team','client','project','operational_area','work_item')",
            name="ck_activity_resource",
        ),
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
