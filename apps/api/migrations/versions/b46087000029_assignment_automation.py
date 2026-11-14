"""Durable finite assignment rules, source executions and singular work receipts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b46087000029"
down_revision = "b46087000028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("queue_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("cancelled_through_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version > 0 AND cancelled_through_version BETWEEN 0 AND version",
            name="ck_automation_rule_version",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"], ["clients.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["queue_id"], ["ticket_queues.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id", name="uq_automation_action"),
        sa.UniqueConstraint(
            "id", "action_id", "client_id", "queue_id", name="uq_automation_rule_context"
        ),
        sa.UniqueConstraint("queue_id", "client_id", name="uq_automation_rule_scope"),
    )
    op.create_table(
        "automation_rule_revisions",
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("ticket_statuses", postgresql.ARRAY(sa.String(length=30)), nullable=False),
        sa.Column("authorizer_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "array_ndims(ticket_statuses)=1 AND cardinality(ticket_statuses) BETWEEN 1 AND 5 "
            "AND ticket_statuses <@ ARRAY['new','open','pending_customer',"
            "'pending_third_party','resolved']::varchar[] "
            "AND cardinality(ticket_statuses)=(('new'=ANY(ticket_statuses))::int "
            "+('open'=ANY(ticket_statuses))::int+('pending_customer'=ANY(ticket_statuses))::int "
            "+('pending_third_party'=ANY(ticket_statuses))::int+('resolved'=ANY(ticket_statuses))::int)",
            name="ck_automation_ticket_statuses",
        ),
        sa.CheckConstraint(
            "priority IN ('low','medium','high','critical')", name="ck_automation_priority"
        ),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 300", name="ck_automation_title"
        ),
        sa.CheckConstraint("version > 0", name="ck_automation_revision_version"),
        sa.ForeignKeyConstraint(
            ["authorizer_id"], ["users.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["automation_rules.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("rule_id", "version"),
    )
    op.create_table(
        "automation_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("queue_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(state='processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(state<>'processing' AND lease_token IS NULL AND lease_until IS NULL)",
            name="ck_automation_execution_lease",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code IN ('authorization_lost','project_unavailable',"
            "'assignee_unavailable','ticket_state_changed','existing_work_needs_review',"
            "'invalid_event','unsupported_event','broker_unavailable','processing_failed',"
            "'attempts_exhausted','rule_disabled','source_superseded','lease_expired')",
            name="ck_automation_execution_error",
        ),
        sa.CheckConstraint(
            "state IN ('pending','processing','succeeded','triage',"
            "'superseded','cancelled','dead')",
            name="ck_automation_execution_state",
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 8 AND version > 0", name="ck_automation_execution_version"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id", "action_id", "client_id", "queue_id"],
            [
                "automation_rules.id",
                "automation_rules.action_id",
                "automation_rules.client_id",
                "automation_rules.queue_id",
            ],
            name="fk_automation_execution_rule",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id", "rule_version"],
            ["automation_rule_revisions.rule_id", "automation_rule_revisions.version"],
            name="fk_automation_execution_revision",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_event_id"],
            ["outbox_events.event_id"],
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "client_id", "queue_id"],
            ["tickets.id", "tickets.client_id", "tickets.queue_id"],
            name="fk_automation_execution_ticket",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "rule_id",
            "action_id",
            "ticket_id",
            "client_id",
            "queue_id",
            name="uq_automation_execution_context",
        ),
        sa.UniqueConstraint(
            "rule_id", "action_id", "source_event_id", name="uq_automation_execution_source"
        ),
    )
    op.create_index(
        "ix_automation_due",
        "automation_executions",
        ["state", "next_attempt_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_automation_ticket_page",
        "automation_executions",
        ["ticket_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "automation_effects",
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("queue_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("origin_execution_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("mode IN ('created','adopted')", name="ck_automation_effect_mode"),
        sa.ForeignKeyConstraint(
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
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "client_id"],
            ["projects.id", "projects.client_id"],
            name="fk_automation_effect_project",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id", "action_id", "client_id", "queue_id"],
            [
                "automation_rules.id",
                "automation_rules.action_id",
                "automation_rules.client_id",
                "automation_rules.queue_id",
            ],
            name="fk_automation_effect_rule",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "client_id", "queue_id"],
            ["tickets.id", "tickets.client_id", "tickets.queue_id"],
            name="fk_automation_effect_ticket",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["work_item_id", "project_id"],
            ["work_items.id", "work_items.project_id"],
            name="fk_automation_effect_work",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("rule_id", "action_id", "ticket_id"),
        sa.UniqueConstraint("origin_execution_id", name="uq_automation_effect_origin"),
    )
    op.drop_constraint("ck_activity_actor", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_actor",
        "activity_events",
        "actor_kind IN ('user','management_command') OR "
        "(actor_kind='automation' AND actor_id IS NULL AND event_type IN "
        "('work_item.created','ticket.work_linked','work_item.ticket_linked'))",
    )


def downgrade() -> None:
    # Preserve both logical receipts and provenance after live link removal.
    op.execute(
        "LOCK TABLE automation_rules,automation_rule_revisions,automation_executions,"
        "automation_effects,outbox_events,audit_logs,activity_events,idempotency_records "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM automation_rules)
      OR EXISTS(SELECT 1 FROM automation_rule_revisions)
      OR EXISTS(SELECT 1 FROM automation_executions)
      OR EXISTS(SELECT 1 FROM automation_effects)
      OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type LIKE 'automation.%'
        OR (schema_version=2 AND event_type IN
          ('work_item.created','ticket.work_linked','work_item.ticket_linked')))
      OR EXISTS(SELECT 1 FROM audit_logs WHERE action LIKE 'automation.%'
        OR details->>'actor_kind'='automation')
      OR EXISTS(SELECT 1 FROM activity_events WHERE event_type LIKE 'automation.%'
        OR actor_kind='automation')
      OR EXISTS(SELECT 1 FROM idempotency_records WHERE route LIKE 'automation-rule-%'
        OR route LIKE 'automation-retry:%') THEN
        RAISE EXCEPTION 'Cannot contract assignment automation/history';
      END IF; END $$""")
    op.drop_constraint("ck_activity_actor", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_actor",
        "activity_events",
        "actor_kind IN ('user','management_command')",
    )
    op.drop_table("automation_effects")
    op.drop_table("automation_executions")
    op.drop_table("automation_rule_revisions")
    op.drop_table("automation_rules")
