"""Task-owned unverified external labels, independent of internal assignment."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000012"
down_revision = "b46087000011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_item_external_participants",
        sa.Column(
            "work_item_id",
            sa.Uuid(),
            sa.ForeignKey("work_items.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("unresolved_label", sa.String(150), primary_key=True),
        sa.CheckConstraint(
            "char_length(unresolved_label) BETWEEN 1 AND 150 "
            "AND unresolved_label=btrim(unresolved_label)",
            name="ck_work_external_label",
        ),
        sa.CheckConstraint(
            "position(chr(10) in unresolved_label)=0 AND position(chr(13) in unresolved_label)=0",
            name="ck_work_external_line",
        ),
    )


def downgrade() -> None:
    # Exclude concurrent link writes before checking, including direct SQL inserts.
    op.execute("LOCK TABLE work_item_external_participants IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM work_item_external_participants)
        OR EXISTS(SELECT 1 FROM outbox_events WHERE aggregate_type='work_item'
            AND payload->>'changed_fields' ~ '(^|,)external_participants(,|$)')
        OR EXISTS(SELECT 1 FROM activity_events WHERE resource_type='work_item'
            AND details->>'changed_fields' ~ '(^|,)external_participants(,|$)')
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action LIKE 'work_item.%'
            AND details->>'changed_fields' ~ '(^|,)external_participants(,|$)')
        THEN RAISE EXCEPTION 'Cannot downgrade while durable external involvement exists';
        END IF;
    END $$""")
    op.drop_table("work_item_external_participants")
