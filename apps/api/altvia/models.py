from datetime import date, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
            "note_access='none' OR (scope_kind='queue' "
            "AND role_name IN ('agent','operations_manager') "
            "AND note_access IN ('read','write'))",
            name="ck_role_binding_note_access",
        ),
        CheckConstraint(
            "(scope_kind = 'global' AND team_id IS NULL AND client_id IS NULL "
            "AND project_id IS NULL AND queue_id IS NULL AND role_name = 'platform_admin') OR "
            "(scope_kind = 'team' AND team_id IS NOT NULL AND client_id IS NULL "
            "AND project_id IS NULL AND queue_id IS NULL "
            "AND role_name IN ('viewer','operations_manager')) OR "
            "(scope_kind = 'client' AND client_id IS NOT NULL AND team_id IS NULL "
            "AND project_id IS NULL AND queue_id IS NULL "
            "AND role_name IN ('viewer','operations_manager')) OR "
            "(scope_kind = 'project' AND project_id IS NOT NULL AND team_id IS NULL "
            "AND client_id IS NULL AND queue_id IS NULL "
            "AND role_name IN ('viewer','agent','project_manager')) OR "
            "(scope_kind = 'queue' AND queue_id IS NOT NULL AND team_id IS NULL "
            "AND client_id IS NULL AND project_id IS NULL "
            "AND role_name IN ('viewer','agent','operations_manager'))",
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
        Index(
            "uq_role_bindings_queue",
            "user_id",
            "queue_id",
            unique=True,
            postgresql_where=text("scope_kind = 'queue'"),
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
    queue_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ticket_queues.id", name="fk_role_binding_queue", ondelete="RESTRICT")
    )
    note_access: Mapped[str] = mapped_column(String(10), default="none", server_default="none")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[UUID | None]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    correlation_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, str | None]] = mapped_column(JSONB, default=dict)


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


class MailboxSource(Base):
    __tablename__ = "mailbox_sources"
    __table_args__ = (
        CheckConstraint("source_key ~ '^[A-Za-z0-9_-]{1,64}$'", name="ck_mail_source_key"),
        UniqueConstraint("id", "queue_id", name="uq_mail_source_queue"),
        CheckConstraint("version > 0", name="ck_mail_source_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_key: Mapped[str] = mapped_column(String(64), unique=True)
    queue_id: Mapped[UUID] = mapped_column(ForeignKey("ticket_queues.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MailboxPollState(Base):
    __tablename__ = "mailbox_poll_states"
    __table_args__ = (
        CheckConstraint("last_uid BETWEEN 0 AND 4294967295", name="ck_poll_uid"),
        CheckConstraint(
            "(namespace_hash IS NULL AND uid_validity IS NULL AND last_uid=0) OR "
            "(namespace_hash IS NOT NULL AND uid_validity IS NOT NULL "
            "AND namespace_hash ~ '^[0-9a-f]{64}$' AND uid_validity BETWEEN 1 AND 4294967295)",
            name="ck_poll_namespace",
        ),
        CheckConstraint("(lease_token IS NULL)=(lease_until IS NULL)", name="ck_poll_lease"),
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("mailbox_sources.id", ondelete="RESTRICT"), primary_key=True
    )
    namespace_hash: Mapped[str | None] = mapped_column(String(64))
    uid_validity: Mapped[int | None] = mapped_column(BigInteger)
    last_uid: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InboundMailEnvelope(Base):
    __tablename__ = "inbound_mail_envelopes"
    __table_args__ = (
        UniqueConstraint("source_id", "uid_validity", "uid", name="uq_mail_envelope_identity"),
        CheckConstraint("uid_validity BETWEEN 1 AND 4294967295", name="ck_mail_uid_validity"),
        CheckConstraint("uid BETWEEN 1 AND 4294967295", name="ck_mail_uid"),
        CheckConstraint("state IN ('quarantine','collision')", name="ck_mail_envelope_state"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("mailbox_sources.id", ondelete="RESTRICT"))
    uid_validity: Mapped[int] = mapped_column(BigInteger)
    uid: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(
        String(20), default="quarantine", server_default="quarantine"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InboundMailVariant(Base):
    __tablename__ = "inbound_mail_variants"
    __table_args__ = (
        UniqueConstraint("envelope_id", "raw_sha256", name="uq_mail_variant_hash"),
        CheckConstraint("octet_length(raw_message) BETWEEN 1 AND 2097152", name="ck_mail_raw_size"),
        CheckConstraint("raw_sha256=encode(sha256(raw_message),'hex')", name="ck_mail_raw_hash"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    envelope_id: Mapped[UUID] = mapped_column(
        ForeignKey("inbound_mail_envelopes.id", ondelete="RESTRICT")
    )
    raw_message: Mapped[bytes] = mapped_column(LargeBinary)
    raw_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InboundMailPreview(Base):
    __tablename__ = "inbound_mail_previews"
    __table_args__ = (
        CheckConstraint("parser_version IN (1,2)", name="ck_preview_parser"),
        CheckConstraint(
            "(status='ready' AND subject IS NOT NULL AND body_text IS NOT NULL "
            "AND part_count IS NOT NULL AND attachment_count IS NOT NULL AND reason IS NULL "
            "AND char_length(subject)<=998 AND octet_length(subject)<=3992 "
            "AND octet_length(body_text) BETWEEN 1 AND 65536 "
            "AND part_count BETWEEN 1 AND 64 AND attachment_count BETWEEN 0 AND part_count) OR "
            "(status='rejected' AND subject IS NULL AND body_text IS NULL AND part_count IS NULL "
            "AND attachment_count IS NULL AND reason IS NOT NULL AND reason IN "
            "('invalid_raw','invalid_headers','unsupported_mime','invalid_multipart',"
            "'invalid_encoding','unsupported_charset','structure_limit','text_limit',"
            "'html_limit','no_text'))",
            name="ck_preview_result",
        ),
    )
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("inbound_mail_variants.id", ondelete="RESTRICT"), primary_key=True
    )
    parser_version: Mapped[int] = mapped_column(primary_key=True, default=2, server_default="1")
    status: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str | None] = mapped_column(String(998))
    body_text: Mapped[str | None] = mapped_column(Text)
    part_count: Mapped[int | None]
    attachment_count: Mapped[int | None]
    reason: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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


class TicketQueue(Base):
    __tablename__ = "ticket_queues"
    __table_args__ = (
        UniqueConstraint("team_id", "name", name="uq_queue_team_name"),
        Index("ix_ticket_queues_page", "team_id", "id"),
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_queue_name"),
        CheckConstraint(
            "position(chr(10) in name)=0 AND position(chr(13) in name)=0", name="ck_queue_line"
        ),
        CheckConstraint("version > 0", name="ck_queue_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(150))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_manual_close: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    allow_reopen: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TicketCategory(Base):
    __tablename__ = "ticket_categories"
    __table_args__ = (
        UniqueConstraint("queue_id", "name", name="uq_category_queue_name"),
        UniqueConstraint("id", "queue_id", name="uq_category_identity_queue"),
        Index("ix_ticket_categories_page", "queue_id", "id"),
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_category_name"),
        CheckConstraint(
            "position(chr(10) in name)=0 AND position(chr(13) in name)=0", name="ck_category_line"
        ),
        CheckConstraint("version > 0", name="ck_category_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    queue_id: Mapped[UUID] = mapped_column(ForeignKey("ticket_queues.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(150))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(default=1)
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
        UniqueConstraint("id", "client_id", name="uq_contact_identity_client"),
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


class ProjectMilestone(Base):
    __tablename__ = "project_milestones"
    __table_args__ = (
        CheckConstraint("char_length(btrim(title)) > 0", name="ck_milestone_title"),
        CheckConstraint("state IN ('planned','done','cancelled')", name="ck_milestone_state"),
        CheckConstraint("version > 0", name="ck_milestone_version"),
        CheckConstraint(
            "(due_at IS NULL AND due_precision IS NULL "
            "AND due_date_local IS NULL AND due_timezone IS NULL) "
            "OR (due_at IS NOT NULL AND due_precision IS NOT NULL AND due_precision='date' "
            "AND due_date_local IS NOT NULL AND due_timezone IS NOT NULL) "
            "OR (due_at IS NOT NULL AND due_precision IS NOT NULL AND due_precision='instant' "
            "AND due_date_local IS NULL AND due_timezone IS NULL)",
            name="ck_milestone_due",
        ),
        Index("ix_project_milestones_page", "project_id", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(300))
    state: Mapped[str] = mapped_column(String(20), default="planned")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_precision: Mapped[str | None] = mapped_column(String(10))
    due_date_local: Mapped[date | None] = mapped_column(Date)
    due_timezone: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    external_participants: Mapped[list["WorkExternalParticipant"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )


class WorkExternalParticipant(Base):
    __tablename__ = "work_item_external_participants"
    __table_args__ = (
        CheckConstraint(
            "char_length(unresolved_label) BETWEEN 1 AND 150 "
            "AND unresolved_label=btrim(unresolved_label)",
            name="ck_work_external_label",
        ),
        CheckConstraint(
            "position(chr(10) in unresolved_label)=0 AND position(chr(13) in unresolved_label)=0",
            name="ck_work_external_line",
        ),
    )
    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="RESTRICT"), primary_key=True
    )
    unresolved_label: Mapped[str] = mapped_column(String(150), primary_key=True)


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
            "attachment_count BETWEEN 0 AND 20", name="ck_work_item_comments_attachment_count"
        ),
        UniqueConstraint("id", "work_item_id", name="uq_work_item_comments_parent"),
        CheckConstraint(
            "char_length(btrim(body)) BETWEEN 1 AND 10000", name="ck_work_comment_body"
        ),
        Index("ix_work_comment_page", "work_item_id", "created_at", "id"),
    )
    attachment_count: Mapped[int] = mapped_column(default=0, server_default="0")
    attachments: Mapped[list["Attachment"]] = relationship(
        secondary="work_comment_attachments",
        primaryjoin="WorkComment.id == WorkCommentAttachment.comment_id",
        secondaryjoin="Attachment.id == WorkCommentAttachment.attachment_id",
        order_by="WorkCommentAttachment.position",
        viewonly=True,
        lazy="selectin",
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


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("id", "client_id", "queue_id", name="uq_ticket_context"),
        UniqueConstraint("number", name="uq_ticket_number"),
        ForeignKeyConstraint(
            ["requester_id", "client_id"],
            ["client_contacts.id", "client_contacts.client_id"],
            name="fk_ticket_requester_client",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["category_id", "queue_id"],
            ["ticket_categories.id", "ticket_categories.queue_id"],
            name="fk_ticket_category_queue",
            ondelete="RESTRICT",
        ),
        CheckConstraint("number > 0", name="ck_ticket_number"),
        CheckConstraint(
            r"char_length(btrim(subject,U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F"
            r"\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009"
            r"\200A\2028\2029\202F\205F\3000')) > 0",
            name="ck_ticket_subject",
        ),
        CheckConstraint(
            "position(chr(10) in subject)=0 AND position(chr(13) in subject)=0",
            name="ck_ticket_subject_line",
        ),
        CheckConstraint("char_length(description) <= 20000", name="ck_ticket_description"),
        CheckConstraint("version > 0", name="ck_ticket_version"),
        CheckConstraint(
            "priority IN ('low','medium','high','critical')", name="ck_ticket_priority"
        ),
        CheckConstraint("source IN ('manual','email')", name="ck_ticket_source"),
        CheckConstraint(
            "status IN ('new','open','pending_customer','pending_third_party','resolved','closed')",
            name="ck_ticket_status",
        ),
        CheckConstraint(
            "(status IN ('new','open','pending_customer','pending_third_party') "
            "AND resolved_at IS NULL AND closed_at IS NULL) OR "
            "(status='resolved' AND resolved_at IS NOT NULL AND closed_at IS NULL) OR "
            "(status='closed' AND resolved_at IS NOT NULL AND closed_at IS NOT NULL)",
            name="ck_ticket_state_times",
        ),
        Index("ix_tickets_queue_page", "queue_id", text("created_at DESC"), text("id DESC")),
        Index("ix_tickets_client_page", "client_id", text("created_at DESC"), text("id DESC")),
        Index("ix_tickets_assignee", "assignee_id", "queue_id", "status"),
        Index(
            "ix_ticket_search",
            text(
                "to_tsvector('portuguese'::regconfig, "
                "(coalesce(subject, ''::character varying)::text || ' '::text) "
                "|| coalesce(description, ''::text))"
            ),
            postgresql_using="gin",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    number: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"))
    requester_id: Mapped[UUID] = mapped_column()
    queue_id: Mapped[UUID] = mapped_column(ForeignKey("ticket_queues.id", ondelete="RESTRICT"))
    category_id: Mapped[UUID | None] = mapped_column()
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    subject: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), default="new", server_default="new")
    priority: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    client: Mapped[Client] = relationship(foreign_keys=[client_id], lazy="joined", viewonly=True)
    queue: Mapped[TicketQueue] = relationship(foreign_keys=[queue_id], lazy="joined", viewonly=True)
    requester: Mapped[ClientContact] = relationship(
        foreign_keys=[requester_id, client_id], lazy="joined", viewonly=True
    )
    category: Mapped[TicketCategory | None] = relationship(
        foreign_keys=[category_id, queue_id], lazy="joined", viewonly=True
    )
    assignee: Mapped[User | None] = relationship(
        foreign_keys=[assignee_id], lazy="joined", viewonly=True
    )


class TicketWorkItem(Base):
    __tablename__ = "ticket_work_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "client_id", "queue_id"],
            ["tickets.id", "tickets.client_id", "tickets.queue_id"],
            name="fk_ticket_work_ticket_context",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["work_item_id", "project_id"],
            ["work_items.id", "work_items.project_id"],
            name="fk_ticket_work_work_project",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "client_id"],
            ["projects.id", "projects.client_id"],
            name="fk_ticket_work_project_client",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        CheckConstraint("relation_type='related'", name="ck_ticket_work_relation"),
        Index("ix_ticket_work_reverse", "work_item_id", "ticket_id"),
    )
    ticket_id: Mapped[UUID] = mapped_column(primary_key=True)
    work_item_id: Mapped[UUID] = mapped_column(primary_key=True)
    client_id: Mapped[UUID]
    queue_id: Mapped[UUID]
    project_id: Mapped[UUID]
    relation_type: Mapped[Literal["related"]] = mapped_column(String(7), default="related")
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TicketStatusHistory(Base):
    __tablename__ = "ticket_status_history"
    __table_args__ = (
        UniqueConstraint("ticket_id", "version", name="uq_ticket_state_version"),
        CheckConstraint("version > 0", name="ck_ticket_state_version"),
        CheckConstraint(
            "reason IS NULL OR char_length(reason) <= 2000", name="ck_ticket_state_reason"
        ),
        CheckConstraint(
            "(from_status IS NULL AND to_status='new' AND version=1) OR "
            "(from_status IS NOT NULL AND version > 1 AND ("
            "(from_status='new' AND to_status='open') OR "
            "(from_status='open' AND to_status IN "
            "('pending_customer','pending_third_party','resolved')) OR "
            "(from_status IN ('pending_customer','pending_third_party') "
            "AND to_status IN ('open','resolved')) OR "
            "(from_status='resolved' AND to_status IN ('closed','open')) OR "
            "(from_status='closed' AND to_status='open')))",
            name="ck_ticket_state_graph",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int]
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TicketNote(Base):
    __tablename__ = "ticket_notes"
    __table_args__ = (
        CheckConstraint(
            "attachment_count BETWEEN 0 AND 20", name="ck_ticket_notes_attachment_count"
        ),
        UniqueConstraint("id", "ticket_id", name="uq_ticket_notes_parent"),
        UniqueConstraint("ticket_id", "ticket_version", name="uq_ticket_note_version"),
        CheckConstraint("ticket_version > 1", name="ck_ticket_note_version"),
        CheckConstraint("char_length(body_text) <= 10000", name="ck_ticket_note_length"),
        CheckConstraint(
            r"char_length(btrim(body_text,U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F"
            r"\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009"
            r"\200A\2028\2029\202F\205F\3000')) > 0",
            name="ck_ticket_note_body",
        ),
    )
    attachment_count: Mapped[int] = mapped_column(default=0, server_default="0")
    attachments: Mapped[list["Attachment"]] = relationship(
        secondary="ticket_note_attachments",
        primaryjoin="TicketNote.id == TicketNoteAttachment.note_id",
        secondaryjoin="Attachment.id == TicketNoteAttachment.attachment_id",
        order_by="TicketNoteAttachment.position",
        viewonly=True,
        lazy="selectin",
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id", ondelete="RESTRICT"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    body_text: Mapped[str] = mapped_column(Text)
    ticket_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    author: Mapped[User] = relationship(lazy="joined", viewonly=True)


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        CheckConstraint(
            "attachment_count BETWEEN 0 AND 20", name="ck_ticket_messages_attachment_count"
        ),
        UniqueConstraint("id", "ticket_id", name="uq_message_ticket"),
        UniqueConstraint("ticket_id", "ticket_version", name="uq_ticket_message_version"),
        CheckConstraint("ticket_version > 1", name="ck_ticket_message_version"),
        CheckConstraint("char_length(body_text) <= 10000", name="ck_ticket_message_length"),
        CheckConstraint(
            r"char_length(btrim(body_text,U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F"
            r"\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009"
            r"\200A\2028\2029\202F\205F\3000')) > 0",
            name="ck_ticket_message_body",
        ),
        CheckConstraint(
            "visibility='public' AND direction='outbound'", name="ck_ticket_message_kind"
        ),
    )
    attachment_count: Mapped[int] = mapped_column(default=0, server_default="0")
    attachments: Mapped[list["Attachment"]] = relationship(
        secondary="ticket_message_attachments",
        primaryjoin="TicketMessage.id == TicketMessageAttachment.message_id",
        secondaryjoin="Attachment.id == TicketMessageAttachment.attachment_id",
        order_by="TicketMessageAttachment.position",
        viewonly=True,
        lazy="selectin",
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id", ondelete="RESTRICT"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    body_text: Mapped[str] = mapped_column(Text)
    ticket_version: Mapped[int]
    visibility: Mapped[str] = mapped_column(String(16), default="public", server_default="public")
    direction: Mapped[str] = mapped_column(
        String(16), default="outbound", server_default="outbound"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    author: Mapped[User] = relationship(lazy="joined", viewonly=True)

    delivery: Mapped["OutboundMessage | None"] = relationship(
        foreign_keys="OutboundMessage.message_id", lazy="joined", viewonly=True
    )


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        CheckConstraint("aggregate_version > 0", name="ck_activity_version"),
        CheckConstraint(
            "resource_type IN "
            "('identity','team','client','project','operational_area"
            "','work_item','ticket_queue','ticket')",
            name="ck_activity_resource",
        ),
        CheckConstraint(
            "actor_kind IN ('user','management_command') OR "
            "(actor_kind='automation' AND actor_id IS NULL AND event_type IN "
            "('work_item.created','ticket.work_linked','work_item.ticket_linked'))",
            name="ck_activity_actor",
        ),
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
    details: Mapped[dict[str, str | None]] = mapped_column(JSONB)


class MailSender(Base):
    __tablename__ = "mail_senders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "queue_id"], ["mailbox_sources.id", "mailbox_sources.queue_id"]
        ),
        CheckConstraint("namespace_hash ~ '^[0-9a-f]{64}$'"),
        CheckConstraint("from_email ~ '^[A-Za-z0-9.!#$%&''*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+$'"),
    )
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    queue_id: Mapped[UUID] = mapped_column(unique=True)
    from_email: Mapped[str] = mapped_column(String(254))
    namespace_hash: Mapped[str] = mapped_column(String(64))


class TicketParticipant(Base):
    __tablename__ = "ticket_participants"
    __table_args__ = (
        UniqueConstraint("id", "ticket_id"),
        Index(
            "uq_active_ticket_requester", "ticket_id", unique=True, postgresql_where=text("active")
        ),
        CheckConstraint("version > 0 AND evidence ~ '^[A-Za-z0-9._:/-]{1,200}$'"),
        CheckConstraint("email ~ '^[A-Za-z0-9.!#$%&''*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+$'"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id"))
    contact_id: Mapped[UUID] = mapped_column(ForeignKey("client_contacts.id"))
    email: Mapped[str] = mapped_column(String(254))
    evidence: Mapped[str] = mapped_column(String(200), deferred=True)
    attested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), deferred=True)
    active: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=1)


class TicketMailThread(Base):
    __tablename__ = "ticket_mail_threads"
    __table_args__ = (CheckConstraint("token ~ '^[0-9a-f]{64}$'"),)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True)


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "ticket_id"], ["ticket_messages.id", "ticket_messages.ticket_id"]
        ),
        ForeignKeyConstraint(
            ["participant_id", "ticket_id"],
            ["ticket_participants.id", "ticket_participants.ticket_id"],
        ),
        Index("ix_delivery_pending", "state", "next_attempt_at"),
        CheckConstraint(
            "state IN ('queued','preparing','transmitting','accepted','failed','uncertain')"
        ),
        CheckConstraint("attempts BETWEEN 0 AND 8 AND version > 0"),
        CheckConstraint(
            "(wire_format=1 AND octet_length(wire) BETWEEN 1 AND "
            "262144) OR (wire_format=2 AND octet_length(wire) "
            "BETWEEN 1 AND 26214400)",
            name="ck_outbound_wire_format",
        ),
        CheckConstraint("namespace_hash ~ '^[0-9a-f]{64}$'"),
        CheckConstraint(
            "(state IN ('preparing','transmitting'))="
            "(lease_token IS NOT NULL AND lease_until IS NOT NULL)"
        ),
        CheckConstraint("(state='accepted')=(accepted_at IS NOT NULL)"),
        CheckConstraint(
            "last_error_code IS NULL OR last_error_code IN "
            "('temporary','permanent','transport','eligibility_revoked',"
            "'lease_expired','data_unknown','retry_exhausted')"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id"))
    message_id: Mapped[UUID] = mapped_column(unique=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("mail_senders.source_id"))
    participant_id: Mapped[UUID]
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    envelope_from: Mapped[str] = mapped_column(String(254))
    envelope_to: Mapped[str] = mapped_column(String(254))
    namespace_hash: Mapped[str] = mapped_column(String(64))
    wire_format: Mapped[int] = mapped_column(default=1, server_default="1")
    wire: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    smtp_message_id: Mapped[str] = mapped_column(String(320), unique=True)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    version: Mapped[int] = mapped_column(default=1)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(40))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MailTriageCase(Base):
    __tablename__ = "mail_triage_cases"
    __table_args__ = (
        CheckConstraint(
            "(file_extraction_version=0 AND file_set_status='legacy' AND file_count=0 AND "
            "file_rejection_reason IS NULL) OR (file_extraction_version=1 AND "
            "((file_set_status='complete' AND file_count BETWEEN 0 AND 20 AND "
            "file_rejection_reason IS NULL) OR (file_set_status='unavailable' AND file_count=0 AND "
            "file_rejection_reason IS NOT NULL AND file_rejection_reason IN "
            "('file_structure','file_count','file_size','file_encoding','file_filename',"
            "'file_type','file_parameter'))))",
            name="ck_case_files",
        ),
        UniqueConstraint("id", "client_id", "queue_id", name="uq_case_ticket_context"),
        ForeignKeyConstraint(
            ["incoming_message_id", "ticket_id", "id"],
            [
                "ticket_incoming_messages.id",
                "ticket_incoming_messages.ticket_id",
                "ticket_incoming_messages.case_id",
            ],
            name="fk_case_receipt",
            use_alter=True,
        ),
        CheckConstraint(
            "(ticket_id IS NULL)=(incoming_message_id IS NULL) AND "
            "(state<>'promoted' OR ticket_id IS NOT NULL)",
            name="ck_case_receipt",
        ),
        ForeignKeyConstraint(
            ["source_id", "queue_id"], ["mailbox_sources.id", "mailbox_sources.queue_id"]
        ),
        ForeignKeyConstraint(
            ["contact_id", "client_id"], ["client_contacts.id", "client_contacts.client_id"]
        ),
        UniqueConstraint(
            "id", "source_id", "client_id", "contact_id", "email_snapshot", name="uq_case_context"
        ),
        Index(
            "uq_case_message_context",
            "source_id",
            "client_id",
            "contact_id",
            "email_snapshot",
            "message_id",
            unique=True,
            postgresql_where=text("message_id IS NOT NULL"),
        ),
        Index("ix_mail_cases_page", "created_at", "id"),
        Index(
            "ix_case_anchor_context",
            "queue_id",
            "client_id",
            "contact_id",
            "email_snapshot",
            "message_id",
            postgresql_where=text("message_id IS NOT NULL AND ticket_id IS NOT NULL"),
        ),
        CheckConstraint(
            "state IN ('ready','promoted','collision','revoked') AND version > 0",
            name="ck_case_state",
        ),
        CheckConstraint("routing_version=1", name="ck_case_routing"),
        CheckConstraint(
            "char_length(subject)<=998 AND octet_length(subject)<=3992 AND "
            "octet_length(body_text) BETWEEN 1 AND 65536",
            name="ck_case_text",
        ),
        CheckConstraint(
            "jsonb_typeof(references_ids)='array' AND jsonb_array_length(references_ids)<=64",
            name="ck_case_references",
        ),
        CheckConstraint(
            "thread_token IS NULL OR thread_token ~ '^[0-9a-f]{64}$'", name="ck_case_token"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID]
    queue_id: Mapped[UUID]
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    contact_id: Mapped[UUID]
    primary_variant_id: Mapped[UUID] = mapped_column(ForeignKey("inbound_mail_variants.id"))
    file_extraction_version: Mapped[int] = mapped_column(server_default="0", deferred=True)
    file_set_status: Mapped[str] = mapped_column(String(11), server_default="legacy", deferred=True)
    file_count: Mapped[int] = mapped_column(server_default="0", deferred=True)
    file_rejection_reason: Mapped[str | None] = mapped_column(String(20), deferred=True)
    email_snapshot: Mapped[str] = mapped_column(String(254))
    contact_name: Mapped[str] = mapped_column(String(150))
    subject: Mapped[str] = mapped_column(String(998))
    body_text: Mapped[str] = mapped_column(Text, deferred=True)
    routing_version: Mapped[int] = mapped_column(default=1)
    message_id: Mapped[str | None] = mapped_column(String(320), deferred=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(320), deferred=True)
    references_ids: Mapped[list[str]] = mapped_column(JSONB, deferred=True)
    thread_token: Mapped[str | None] = mapped_column(String(64), deferred=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    state: Mapped[str] = mapped_column(String(20), default="ready")
    version: Mapped[int] = mapped_column(default=1)
    ticket_id: Mapped[UUID | None]
    incoming_message_id: Mapped[UUID | None]


class TicketIncomingMessage(Base):
    __tablename__ = "ticket_incoming_messages"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_incoming_case"),
        UniqueConstraint("ticket_id", "ticket_version", name="uq_incoming_version"),
        UniqueConstraint("id", "ticket_id", "case_id", name="uq_incoming_receipt"),
        ForeignKeyConstraint(
            ["ticket_id", "client_id", "queue_id"],
            ["tickets.id", "tickets.client_id", "tickets.queue_id"],
            name="fk_incoming_ticket_context",
        ),
        ForeignKeyConstraint(
            ["case_id", "client_id", "queue_id"],
            ["mail_triage_cases.id", "mail_triage_cases.client_id", "mail_triage_cases.queue_id"],
            name="fk_incoming_case_context",
        ),
        CheckConstraint("ticket_version>1", name="ck_incoming_version"),
        Index("ix_incoming_ticket_page", "ticket_id", "ticket_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID]
    ticket_id: Mapped[UUID]
    client_id: Mapped[UUID]
    queue_id: Mapped[UUID]
    ticket_version: Mapped[int]
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MailCaseOrigin(Base):
    __tablename__ = "mail_case_origins"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "source_id", "client_id", "contact_id", "email_snapshot"],
            [
                "mail_triage_cases.id",
                "mail_triage_cases.source_id",
                "mail_triage_cases.client_id",
                "mail_triage_cases.contact_id",
                "mail_triage_cases.email_snapshot",
            ],
        ),
        CheckConstraint(
            "raw_sha256 ~ '^[0-9a-f]{64}$' AND evidence ~ "
            "'^[A-Za-z0-9._:/-]{1,200}$' AND contact_version>0",
            name="ck_origin_proof",
        ),
        CheckConstraint(
            "disposition IN ('primary','alias','collision') AND "
            "routing_version=1 AND parser_version=2",
            name="ck_origin_disposition",
        ),
    )
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("inbound_mail_variants.id"), primary_key=True
    )
    case_id: Mapped[UUID]
    source_id: Mapped[UUID]
    envelope_id: Mapped[UUID] = mapped_column(ForeignKey("inbound_mail_envelopes.id"))
    raw_sha256: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[UUID]
    contact_id: Mapped[UUID]
    email_snapshot: Mapped[str] = mapped_column(String(254))
    contact_version: Mapped[int]
    evidence: Mapped[str] = mapped_column(String(200))
    routing_version: Mapped[int] = mapped_column(default=1)
    parser_version: Mapped[int] = mapped_column(default=2)
    disposition: Mapped[str] = mapped_column(String(20))
    attested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Attachment(Base):
    """Private immutable upload identity; scan lifecycle is versioned separately."""

    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint("mail_case_id", "file_position", name="uq_attachment_case_position"),
        UniqueConstraint("id", "ticket_id", "purpose", name="uq_attachment_ticket_id_purpose"),
        UniqueConstraint(
            "id", "work_item_id", "purpose", name="uq_attachment_work_item_id_purpose"
        ),
        CheckConstraint(
            "(mail_case_id IS NULL AND file_position IS NULL AND creator_id IS NOT NULL AND "
            "((ticket_id IS NOT NULL AND work_item_id IS NULL AND purpose IN ('public','note')) OR "
            "(ticket_id IS NULL AND work_item_id IS NOT NULL AND purpose='work'))) OR "
            "(mail_case_id IS NOT NULL AND ticket_id IS NULL AND work_item_id IS NULL AND "
            "purpose='incoming' AND creator_id IS NULL AND parent_version=1 AND "
            "file_position IS NOT NULL AND file_position BETWEEN 0 AND 19)",
            name="ck_attachment_owner",
        ),
        CheckConstraint(
            "bytes BETWEEN 1 AND 10485760 AND sha256 ~ '^[0-9a-f]{64}$' AND object_key ~"
            " '^objects/[0-9a-f]{64}$'",
            name="ck_attachment_object",
        ),
        CheckConstraint(
            "version>0 AND parent_version>0 AND policy_version=1 AND generation>0 AND "
            "attempts BETWEEN 0 AND 8",
            name="ck_attachment_versions",
        ),
        CheckConstraint(
            "state IN ('quarantine','scanning','ready','rejected','failed') AND "
            "((state='scanning' AND lease_token IS NOT NULL AND lease_until IS NOT NULL)"
            " OR (state<>'scanning' AND lease_token IS NULL AND lease_until IS NULL))",
            name="ck_attachment_state",
        ),
        Index("ix_attachment_ticket_page", "ticket_id", "purpose", "created_at", "id"),
        Index("ix_attachment_work_page", "work_item_id", "purpose", "created_at", "id"),
        Index("ix_attachment_scan_due", "state", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID | None] = mapped_column(ForeignKey("tickets.id"))
    work_item_id: Mapped[UUID | None] = mapped_column(ForeignKey("work_items.id"))
    mail_case_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("mail_triage_cases.id", name="fk_attachment_mail_case", ondelete="RESTRICT")
    )
    file_position: Mapped[int | None]
    purpose: Mapped[str] = mapped_column(String(10))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(30))
    bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(72), unique=True)
    creator_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    parent_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    policy_version: Mapped[int] = mapped_column(default=1)
    version: Mapped[int] = mapped_column(default=1)
    state: Mapped[str] = mapped_column(String(10), default="quarantine")
    generation: Mapped[int] = mapped_column(default=1)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttachmentScanAttempt(Base):
    """Immutable completed/expired attempt identity, including fenced lease."""

    __tablename__ = "attachment_scan_attempts"
    __table_args__ = (
        CheckConstraint(
            "generation>0 AND attempt BETWEEN 1 AND 8 AND finished_at>=claimed_at AND "
            "lease_until>claimed_at",
            name="ck_scan_attempt_bounds",
        ),
        CheckConstraint("disposition IN ('clean','infected','failed')", name="ck_scan_disposition"),
        CheckConstraint(
            "reason IN ('clean','infected','encrypted','limit','scan_error','protocol',"
            "'unavailable','cancelled','timeout','database_invalid','database_changed',"
            "'storage_unavailable','storage_integrity','lease_expired')",
            name="ck_scan_reason",
        ),
    )

    attachment_id: Mapped[UUID] = mapped_column(ForeignKey("attachments.id"), primary_key=True)
    generation: Mapped[int] = mapped_column(primary_key=True)
    attempt: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[UUID] = mapped_column(unique=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    disposition: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(30))
    engine: Mapped[str | None] = mapped_column(String(16))
    database_version: Mapped[int | None]
    database_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TicketMessageAttachment(Base):
    __tablename__ = "ticket_message_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "ticket_id"], ["ticket_messages.id", "ticket_messages.ticket_id"]
        ),
        ForeignKeyConstraint(
            ["attachment_id", "ticket_id", "purpose"],
            ["attachments.id", "attachments.ticket_id", "attachments.purpose"],
        ),
        UniqueConstraint("message_id", "position"),
        CheckConstraint("purpose='public' AND position BETWEEN 0 AND 19"),
    )
    message_id: Mapped[UUID] = mapped_column(primary_key=True)
    attachment_id: Mapped[UUID] = mapped_column(primary_key=True)
    ticket_id: Mapped[UUID]
    purpose: Mapped[str] = mapped_column(String(10))
    position: Mapped[int]


class TicketNoteAttachment(Base):
    __tablename__ = "ticket_note_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["note_id", "ticket_id"], ["ticket_notes.id", "ticket_notes.ticket_id"]
        ),
        ForeignKeyConstraint(
            ["attachment_id", "ticket_id", "purpose"],
            ["attachments.id", "attachments.ticket_id", "attachments.purpose"],
        ),
        UniqueConstraint("note_id", "position"),
        CheckConstraint("purpose='note' AND position BETWEEN 0 AND 19"),
    )
    note_id: Mapped[UUID] = mapped_column(primary_key=True)
    attachment_id: Mapped[UUID] = mapped_column(primary_key=True)
    ticket_id: Mapped[UUID]
    purpose: Mapped[str] = mapped_column(String(10))
    position: Mapped[int]


class WorkCommentAttachment(Base):
    __tablename__ = "work_comment_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["comment_id", "work_item_id"],
            ["work_item_comments.id", "work_item_comments.work_item_id"],
        ),
        ForeignKeyConstraint(
            ["attachment_id", "work_item_id", "purpose"],
            ["attachments.id", "attachments.work_item_id", "attachments.purpose"],
        ),
        UniqueConstraint("comment_id", "position"),
        CheckConstraint("purpose='work' AND position BETWEEN 0 AND 19"),
    )
    comment_id: Mapped[UUID] = mapped_column(primary_key=True)
    attachment_id: Mapped[UUID] = mapped_column(primary_key=True)
    work_item_id: Mapped[UUID]
    purpose: Mapped[str] = mapped_column(String(10))
    position: Mapped[int]


class AutomationRule(Base):
    __tablename__ = "automation_rules"
    __table_args__ = (
        UniqueConstraint("queue_id", "client_id", name="uq_automation_rule_scope"),
        UniqueConstraint("action_id", name="uq_automation_action"),
        UniqueConstraint(
            "id", "action_id", "client_id", "queue_id", name="uq_automation_rule_context"
        ),
        CheckConstraint(
            "version > 0 AND cancelled_through_version BETWEEN 0 AND version",
            name="ck_automation_rule_version",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    queue_id: Mapped[UUID] = mapped_column(
        ForeignKey("ticket_queues.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    action_id: Mapped[UUID] = mapped_column(default=uuid4)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    cancelled_through_version: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutomationRuleRevision(Base):
    __tablename__ = "automation_rule_revisions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_automation_revision_version"),
        CheckConstraint("char_length(btrim(title)) BETWEEN 1 AND 300", name="ck_automation_title"),
        CheckConstraint(
            "priority IN ('low','medium','high','critical')", name="ck_automation_priority"
        ),
        CheckConstraint(
            "array_ndims(ticket_statuses)=1 AND cardinality(ticket_statuses) BETWEEN 1 AND 5 "
            "AND ticket_statuses <@ ARRAY['new','open','pending_customer',"
            "'pending_third_party','resolved']::varchar[] "
            "AND cardinality(ticket_statuses)=(('new'=ANY(ticket_statuses))::int "
            "+('open'=ANY(ticket_statuses))::int+('pending_customer'=ANY(ticket_statuses))::int "
            "+('pending_third_party'=ANY(ticket_statuses))::int+('resolved'=ANY(ticket_statuses))::int)",
            name="ck_automation_ticket_statuses",
        ),
    )
    rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        primary_key=True,
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False, server_default="false")
    title: Mapped[str] = mapped_column(String(300))
    priority: Mapped[str] = mapped_column(String(20))
    ticket_statuses: Mapped[list[str]] = mapped_column(ARRAY(String(30)))
    authorizer_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutomationExecution(Base):
    __tablename__ = "automation_executions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["rule_id", "action_id", "client_id", "queue_id"],
            [
                "automation_rules.id",
                "automation_rules.action_id",
                "automation_rules.client_id",
                "automation_rules.queue_id",
            ],
            name="fk_automation_execution_rule",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["rule_id", "rule_version"],
            ["automation_rule_revisions.rule_id", "automation_rule_revisions.version"],
            name="fk_automation_execution_revision",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["ticket_id", "client_id", "queue_id"],
            ["tickets.id", "tickets.client_id", "tickets.queue_id"],
            name="fk_automation_execution_ticket",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint(
            "rule_id", "action_id", "source_event_id", name="uq_automation_execution_source"
        ),
        UniqueConstraint(
            "id",
            "rule_id",
            "action_id",
            "ticket_id",
            "client_id",
            "queue_id",
            name="uq_automation_execution_context",
        ),
        CheckConstraint(
            "state IN ('pending','processing','succeeded','triage',"
            "'superseded','cancelled','dead')",
            name="ck_automation_execution_state",
        ),
        CheckConstraint(
            "attempts BETWEEN 0 AND 8 AND version > 0", name="ck_automation_execution_version"
        ),
        CheckConstraint(
            "(state='processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(state<>'processing' AND lease_token IS NULL AND lease_until IS NULL)",
            name="ck_automation_execution_lease",
        ),
        CheckConstraint(
            "error_code IS NULL OR error_code IN ('authorization_lost','project_unavailable',"
            "'assignee_unavailable','ticket_state_changed','existing_work_needs_review',"
            "'invalid_event','unsupported_event','broker_unavailable','processing_failed',"
            "'attempts_exhausted','rule_disabled','source_superseded','lease_expired')",
            name="ck_automation_execution_error",
        ),
        Index("ix_automation_due", "state", "next_attempt_at", "id"),
        Index("ix_automation_ticket_page", "ticket_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rule_id: Mapped[UUID]
    action_id: Mapped[UUID]
    rule_version: Mapped[int]
    client_id: Mapped[UUID]
    queue_id: Mapped[UUID]
    ticket_id: Mapped[UUID]
    source_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("outbox_events.event_id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    state: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutomationEffect(Base):
    __tablename__ = "automation_effects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["rule_id", "action_id", "client_id", "queue_id"],
            [
                "automation_rules.id",
                "automation_rules.action_id",
                "automation_rules.client_id",
                "automation_rules.queue_id",
            ],
            name="fk_automation_effect_rule",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["ticket_id", "client_id", "queue_id"],
            ["tickets.id", "tickets.client_id", "tickets.queue_id"],
            name="fk_automation_effect_ticket",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["work_item_id", "project_id"],
            ["work_items.id", "work_items.project_id"],
            name="fk_automation_effect_work",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "client_id"],
            ["projects.id", "projects.client_id"],
            name="fk_automation_effect_project",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["origin_execution_id", "rule_id", "action_id", "ticket_id", "client_id", "queue_id"],
            [
                "automation_executions.id",
                "automation_executions.rule_id",
                "automation_executions.action_id",
                "automation_executions.ticket_id",
                "automation_executions.client_id",
                "automation_executions.queue_id",
            ],
            name="fk_automation_effect_execution",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("origin_execution_id", name="uq_automation_effect_origin"),
        CheckConstraint("mode IN ('created','adopted')", name="ck_automation_effect_mode"),
    )
    rule_id: Mapped[UUID] = mapped_column(primary_key=True)
    action_id: Mapped[UUID] = mapped_column(primary_key=True)
    ticket_id: Mapped[UUID] = mapped_column(primary_key=True)
    client_id: Mapped[UUID]
    queue_id: Mapped[UUID]
    project_id: Mapped[UUID]
    work_item_id: Mapped[UUID]
    origin_execution_id: Mapped[UUID]
    mode: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
