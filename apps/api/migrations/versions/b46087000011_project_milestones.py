"""Project-owned milestone records with existing deadline precision semantics."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000011"
down_revision = "b46087000010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_milestones",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("due_precision", sa.String(10)),
        sa.Column("due_date_local", sa.Date()),
        sa.Column("due_timezone", sa.String(100)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("char_length(btrim(title)) > 0", name="ck_milestone_title"),
        sa.CheckConstraint("state IN ('planned','done','cancelled')", name="ck_milestone_state"),
        sa.CheckConstraint("version > 0", name="ck_milestone_version"),
        sa.CheckConstraint(
            "(due_at IS NULL AND due_precision IS NULL "
            "AND due_date_local IS NULL AND due_timezone IS NULL) "
            "OR (due_at IS NOT NULL AND due_precision IS NOT NULL AND due_precision='date' "
            "AND due_date_local IS NOT NULL AND due_timezone IS NOT NULL) "
            "OR (due_at IS NOT NULL AND due_precision IS NOT NULL AND due_precision='instant' "
            "AND due_date_local IS NULL AND due_timezone IS NULL)",
            name="ck_milestone_due",
        ),
    )
    op.create_index("ix_project_milestones_page", "project_milestones", ["project_id", "id"])


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM project_milestones)
        OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type IN
            ('project.milestone_created','project.milestone_updated'))
        OR EXISTS(SELECT 1 FROM activity_events WHERE event_type IN
            ('project.milestone_created','project.milestone_updated'))
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action IN
            ('project.milestone_created','project.milestone_updated'))
        THEN RAISE EXCEPTION 'Cannot downgrade while durable milestone data exists';
        END IF;
    END $$""")
    op.drop_table("project_milestones")
