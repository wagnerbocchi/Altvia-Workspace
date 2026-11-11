"""Owner-only opaque mail quarantine, UID identities and immutable raw variants."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000017"
down_revision = "b46087000016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    created = lambda: sa.Column(  # noqa: E731
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    op.create_table(
        "mailbox_sources",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("source_key", sa.String(64), nullable=False, unique=True),
        sa.Column("queue_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        created(),
        sa.ForeignKeyConstraint(["queue_id"], ["ticket_queues.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("source_key ~ '^[A-Za-z0-9_-]{1,64}$'", name="ck_mail_source_key"),
        sa.CheckConstraint("version > 0", name="ck_mail_source_version"),
    )
    op.create_table(
        "inbound_mail_envelopes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("uid_validity", sa.BigInteger(), nullable=False),
        sa.Column("uid", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="quarantine"),
        created(),
        sa.ForeignKeyConstraint(["source_id"], ["mailbox_sources.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("source_id", "uid_validity", "uid", name="uq_mail_envelope_identity"),
        sa.CheckConstraint("uid_validity BETWEEN 1 AND 4294967295", name="ck_mail_uid_validity"),
        sa.CheckConstraint("uid BETWEEN 1 AND 4294967295", name="ck_mail_uid"),
        sa.CheckConstraint("state IN ('quarantine','collision')", name="ck_mail_envelope_state"),
    )
    op.create_table(
        "inbound_mail_variants",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("envelope_id", sa.UUID(), nullable=False),
        sa.Column("raw_message", sa.LargeBinary(), nullable=False),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        created(),
        sa.ForeignKeyConstraint(
            ["envelope_id"], ["inbound_mail_envelopes.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("envelope_id", "raw_sha256", name="uq_mail_variant_hash"),
        sa.CheckConstraint(
            "octet_length(raw_message) BETWEEN 1 AND 2097152", name="ck_mail_raw_size"
        ),
        sa.CheckConstraint("raw_sha256=encode(sha256(raw_message),'hex')", name="ck_mail_raw_hash"),
    )
    op.execute(
        "CREATE TRIGGER inbound_mail_variants_immutable BEFORE UPDATE OR DELETE "
        "ON inbound_mail_variants FOR EACH ROW EXECUTE FUNCTION altvia_reject_audit_mutation()"
    )
    op.execute("""CREATE FUNCTION altvia_guard_mail_identity() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF TG_TABLE_NAME='mailbox_sources' THEN
        IF ROW(NEW.id,NEW.source_key,NEW.queue_id,NEW.created_at)
          IS DISTINCT FROM ROW(OLD.id,OLD.source_key,OLD.queue_id,OLD.created_at) THEN
          RAISE EXCEPTION 'Mail source identity is immutable';
        END IF;
      ELSE
        IF ROW(NEW.id,NEW.source_id,NEW.uid_validity,NEW.uid,NEW.created_at)
          IS DISTINCT FROM ROW(OLD.id,OLD.source_id,OLD.uid_validity,OLD.uid,OLD.created_at)
          OR (OLD.state='collision' AND NEW.state <> 'collision') THEN
          RAISE EXCEPTION 'Mail receipt identity and collision are immutable';
        END IF;
      END IF;
      RETURN NEW;
    END $$""")
    for table in ("mailbox_sources", "inbound_mail_envelopes"):
        op.execute(
            f"CREATE TRIGGER {table}_identity BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION altvia_guard_mail_identity()"
        )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE mailbox_sources,inbound_mail_envelopes,inbound_mail_variants,"
        "audit_logs,outbox_events IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM mailbox_sources)
        OR EXISTS(SELECT 1 FROM inbound_mail_envelopes)
        OR EXISTS(SELECT 1 FROM inbound_mail_variants)
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action IN
          ('mailbox_source.created','mailbox.message_quarantined'))
        OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type IN
          ('mailbox_source.created','mailbox.message_quarantined')) THEN
        RAISE EXCEPTION 'Cannot downgrade while durable mail intake or history exists';
      END IF;
    END $$""")
    op.drop_table("inbound_mail_variants")
    op.drop_table("inbound_mail_envelopes")
    op.drop_table("mailbox_sources")
    op.execute("DROP FUNCTION altvia_guard_mail_identity()")
