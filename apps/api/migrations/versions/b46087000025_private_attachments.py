"""Private file identities and immutable generation-fenced scan history."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000025"
down_revision = "b46087000024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("ticket_id", sa.UUID(), sa.ForeignKey("tickets.id")),
        sa.Column("work_item_id", sa.UUID(), sa.ForeignKey("work_items.id")),
        sa.Column("purpose", sa.String(10), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(30), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(72), nullable=False, unique=True),
        sa.Column("creator_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("parent_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(10), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_token", sa.UUID()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(ticket_id IS NOT NULL AND work_item_id IS NULL AND purpose IN "
            "('public','note')) OR (ticket_id IS NULL AND work_item_id IS NOT NULL AND "
            "purpose='work')",
            name="ck_attachment_owner",
        ),
        sa.CheckConstraint(
            "bytes BETWEEN 1 AND 10485760 AND sha256 ~ '^[0-9a-f]{64}$' AND object_key ~"
            " '^objects/[0-9a-f]{64}$'",
            name="ck_attachment_object",
        ),
        sa.CheckConstraint(
            "version>0 AND parent_version>0 AND policy_version=1 AND generation>0 AND "
            "attempts BETWEEN 0 AND 8",
            name="ck_attachment_versions",
        ),
        sa.CheckConstraint(
            "state IN ('quarantine','scanning','ready','rejected','failed') AND "
            "((state='scanning' AND lease_token IS NOT NULL AND lease_until IS NOT NULL)"
            " OR (state<>'scanning' AND lease_token IS NULL AND lease_until IS NULL))",
            name="ck_attachment_state",
        ),
    )
    op.create_index(
        "ix_attachment_ticket_page", "attachments", ["ticket_id", "purpose", "created_at", "id"]
    )
    op.create_index(
        "ix_attachment_work_page", "attachments", ["work_item_id", "purpose", "created_at", "id"]
    )
    op.create_index("ix_attachment_scan_due", "attachments", ["state", "next_attempt_at"])
    op.create_table(
        "attachment_scan_attempts",
        sa.Column("attachment_id", sa.UUID(), sa.ForeignKey("attachments.id"), primary_key=True),
        sa.Column("generation", sa.Integer(), primary_key=True),
        sa.Column("attempt", sa.Integer(), primary_key=True),
        sa.Column("token", sa.UUID(), nullable=False, unique=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disposition", sa.String(10), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("engine", sa.String(16)),
        sa.Column("database_version", sa.Integer()),
        sa.Column("database_date", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "generation>0 AND attempt BETWEEN 1 AND 8 AND finished_at>=claimed_at AND "
            "lease_until>claimed_at",
            name="ck_scan_attempt_bounds",
        ),
        sa.CheckConstraint(
            "disposition IN ('clean','infected','failed')", name="ck_scan_disposition"
        ),
    )
    op.execute("""CREATE FUNCTION altvia_attachment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Immutable attachment'; END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.state<>'quarantine' OR NEW.version<>1 OR NEW.generation<>1 OR NEW.attempts<>0
          OR NEW.lease_token IS NOT NULL OR NEW.lease_until IS NOT NULL THEN
          RAISE EXCEPTION 'Invalid attachment creation'; END IF;
        RETURN NEW;
      END IF;
      IF
        (to_jsonb(NEW)-ARRAY['state','version','generation','attempts','next_attempt_at','lease_token','lease_until'])
        IS DISTINCT FROM
(to_jsonb(OLD)-ARRAY['state','version','generation','attempts','next_attempt_at','lease_token','lease_until'])
        OR OLD.version=2147483647 OR NEW.version<>OLD.version+1 THEN
        RAISE EXCEPTION 'Immutable attachment identity'; END IF;
      IF OLD.state='failed' AND NEW.state='quarantine' AND NEW.generation=OLD.generation+1
          AND NEW.attempts=0 AND NEW.lease_token IS NULL AND NEW.lease_until IS NULL THEN
        RETURN NEW;
      END IF;
      IF NEW.generation<>OLD.generation THEN RAISE EXCEPTION 'Invalid scan generation'; END IF;
      IF OLD.state='quarantine' AND NEW.state='scanning' AND NEW.attempts=OLD.attempts+1
          AND NEW.lease_token IS NOT NULL AND NEW.lease_until>clock_timestamp() THEN
        RETURN NEW;
      END IF;
      IF OLD.state='scanning' AND NEW.state IN ('quarantine','ready','rejected','failed')
          AND NEW.attempts=OLD.attempts AND NEW.lease_token IS NULL AND NEW.lease_until IS NULL
          AND EXISTS(SELECT 1 FROM attachment_scan_attempts a WHERE a.attachment_id=OLD.id
            AND a.generation=OLD.generation AND a.attempt=OLD.attempts AND a.token=OLD.lease_token
            AND a.lease_until=OLD.lease_until
            AND (NEW.state NOT IN ('ready','rejected') OR OLD.lease_until>clock_timestamp())
            AND (NEW.state<>'ready' OR (a.disposition='clean' AND a.reason='clean'
              AND a.engine='1.4.6' AND a.database_version>0
              AND a.database_date>=clock_timestamp()-interval '48 hours'
              AND a.database_date<=clock_timestamp()+interval '5 minutes'))
            AND (NEW.state<>'rejected' OR a.reason IN ('infected','encrypted','limit'))) THEN
        RETURN NEW;
      END IF;
      RAISE EXCEPTION 'Invalid attachment transition'; END $$""")
    op.execute(
        "CREATE TRIGGER attachment_guard BEFORE INSERT OR UPDATE OR DELETE ON "
        "attachments FOR EACH ROW EXECUTE FUNCTION altvia_attachment_guard()"
    )
    op.execute(
        "CREATE TRIGGER attachment_attempt_immutable BEFORE UPDATE OR DELETE ON "
        "attachment_scan_attempts FOR EACH ROW EXECUTE FUNCTION "
        "altvia_reject_audit_mutation()"
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE attachments,attachment_scan_attempts,audit_logs,outbox_events IN"
        " ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM attachments)
      OR EXISTS(SELECT 1 FROM attachment_scan_attempts)
      OR EXISTS(SELECT 1 FROM audit_logs WHERE action LIKE 'file.%')
      OR EXISTS(SELECT 1 FROM outbox_events WHERE aggregate_type='attachment' OR event_type LIKE
        'file.%')
      THEN RAISE EXCEPTION 'Cannot contract private files/history'; END IF; END $$""")
    op.drop_table("attachment_scan_attempts")
    op.drop_table("attachments")
    op.execute("DROP FUNCTION altvia_attachment_guard()")
