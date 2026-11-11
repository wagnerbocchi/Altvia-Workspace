"""Owner-only fenced IMAPS progress without runtime grants."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000018"
down_revision = "b46087000017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mailbox_poll_states",
        sa.Column("source_id", sa.UUID(), primary_key=True),
        sa.Column("namespace_hash", sa.String(64), nullable=True),
        sa.Column("uid_validity", sa.BigInteger(), nullable=True),
        sa.Column("last_uid", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("lease_token", sa.UUID(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["mailbox_sources.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("last_uid BETWEEN 0 AND 4294967295", name="ck_poll_uid"),
        sa.CheckConstraint(
            "(namespace_hash IS NULL AND uid_validity IS NULL AND last_uid=0) OR "
            "(namespace_hash IS NOT NULL AND uid_validity IS NOT NULL "
            "AND namespace_hash ~ '^[0-9a-f]{64}$' AND uid_validity BETWEEN 1 AND 4294967295)",
            name="ck_poll_namespace",
        ),
        sa.CheckConstraint("(lease_token IS NULL)=(lease_until IS NULL)", name="ck_poll_lease"),
    )
    op.execute("""CREATE FUNCTION altvia_guard_poll_progress() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF NEW.source_id IS DISTINCT FROM OLD.source_id
        OR (OLD.namespace_hash IS NOT NULL
            AND NEW.namespace_hash IS DISTINCT FROM OLD.namespace_hash)
        OR (OLD.uid_validity IS NOT NULL AND NEW.uid_validity IS NULL)
        OR (NEW.uid_validity IS NOT DISTINCT FROM OLD.uid_validity AND NEW.last_uid < OLD.last_uid)
        OR (NEW.uid_validity IS DISTINCT FROM OLD.uid_validity AND NEW.last_uid <> 0)
      THEN RAISE EXCEPTION 'Poll namespace and forward progress must be preserved'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER mailbox_poll_progress BEFORE UPDATE ON mailbox_poll_states "
        "FOR EACH ROW EXECUTE FUNCTION altvia_guard_poll_progress()"
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE mailbox_poll_states,mailbox_sources,audit_logs,outbox_events "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM mailbox_poll_states)
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action='mailbox.poll_checkpointed')
        OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type='mailbox.poll_checkpointed') THEN
        RAISE EXCEPTION 'Cannot downgrade while durable IMAP poll state or history exists';
      END IF;
    END $$""")
    op.drop_table("mailbox_poll_states")
    op.execute("DROP FUNCTION altvia_guard_poll_progress()")
