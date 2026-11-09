"""Expand durable outbox processing and a restricted administrative activity projection."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b46087000005"
down_revision = "b46087000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("last_error_code", sa.String(50), nullable=True))
    op.create_table(
        "processed_events",
        sa.Column("consumer", sa.String(50), primary_key=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("outbox_events.event_id"), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "activity_events",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("outbox_events.event_id"), primary_key=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_kind", sa.String(30), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("aggregate_version > 0", name="ck_activity_version"),
        sa.CheckConstraint("resource_type IN ('identity','team')", name="ck_activity_resource"),
        sa.CheckConstraint("actor_kind IN ('user','management_command')", name="ck_activity_actor"),
    )
    op.create_index("ix_activity_order", "activity_events", ["occurred_at", "event_id"])


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM activity_events) OR EXISTS(SELECT 1 FROM processed_events)
        THEN RAISE EXCEPTION 'Cannot downgrade while durable activity exists'; END IF;
    END $$""")
    op.drop_index("ix_activity_order", table_name="activity_events")
    op.drop_table("activity_events")
    op.drop_table("processed_events")
    op.drop_column("outbox_events", "last_error_code")
