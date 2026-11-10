"""Persist team-scoped queue and category configuration."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000013"
down_revision = "b46087000012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_activity_resource", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_resource",
        "activity_events",
        "resource_type IN "
        "('identity','team','client','project','operational_area','work_item','ticket_queue')",
    )
    op.create_table(
        "ticket_queues",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("team_id", "name", name="uq_queue_team_name"),
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_queue_name"),
        sa.CheckConstraint(
            "position(chr(10) in name)=0 AND position(chr(13) in name)=0", name="ck_queue_line"
        ),
        sa.CheckConstraint("version > 0", name="ck_queue_version"),
    )
    op.create_index("ix_ticket_queues_page", "ticket_queues", ["team_id", "id"])
    op.create_table(
        "ticket_categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "queue_id",
            sa.Uuid(),
            sa.ForeignKey("ticket_queues.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("queue_id", "name", name="uq_category_queue_name"),
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_category_name"),
        sa.CheckConstraint(
            "position(chr(10) in name)=0 AND position(chr(13) in name)=0", name="ck_category_line"
        ),
        sa.CheckConstraint("version > 0", name="ck_category_version"),
    )
    op.create_index("ix_ticket_categories_page", "ticket_categories", ["queue_id", "id"])


def downgrade() -> None:
    op.execute("LOCK TABLE ticket_queues, ticket_categories IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM ticket_queues)
        OR EXISTS(SELECT 1 FROM ticket_categories)
        OR EXISTS(SELECT 1 FROM outbox_events WHERE aggregate_type='ticket_queue')
        OR EXISTS(SELECT 1 FROM activity_events WHERE resource_type='ticket_queue')
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action LIKE 'ticket_queue.%')
        THEN RAISE EXCEPTION 'Cannot downgrade while durable queue data exists';
        END IF;
    END $$""")
    op.drop_table("ticket_categories")
    op.drop_table("ticket_queues")
    op.drop_constraint("ck_activity_resource", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_resource",
        "activity_events",
        "resource_type IN ('identity','team','client','project','operational_area','work_item')",
    )
