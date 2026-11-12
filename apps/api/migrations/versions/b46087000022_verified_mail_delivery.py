"""Verified public delivery, immutable snapshots and finite owned attempt state."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000022"
down_revision = "b46087000021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mailbox_sources ADD CONSTRAINT uq_mail_source_queue UNIQUE(id,queue_id)"
    )
    op.execute("ALTER TABLE ticket_messages ADD CONSTRAINT uq_message_ticket UNIQUE(id,ticket_id)")
    op.create_table(
        "mail_senders",
        sa.Column("source_id", sa.UUID(), primary_key=True),
        sa.Column("queue_id", sa.UUID(), nullable=False, unique=True),
        sa.Column("from_email", sa.String(254), nullable=False),
        sa.Column("namespace_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id", "queue_id"], ["mailbox_sources.id", "mailbox_sources.queue_id"]
        ),
        sa.CheckConstraint("namespace_hash ~ '^[0-9a-f]{64}$'"),
        sa.CheckConstraint("from_email ~ '^[A-Za-z0-9.!#$%&''*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+$'"),
    )
    op.create_table(
        "ticket_participants",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("ticket_id", sa.UUID(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("contact_id", sa.UUID(), sa.ForeignKey("client_contacts.id"), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("evidence", sa.String(200), nullable=False),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("id", "ticket_id"),
        sa.CheckConstraint("version > 0 AND evidence ~ '^[A-Za-z0-9._:/-]{1,200}$'"),
        sa.CheckConstraint("email ~ '^[A-Za-z0-9.!#$%&''*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+$'"),
    )
    op.create_index(
        "uq_active_ticket_requester",
        "ticket_participants",
        ["ticket_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_table(
        "ticket_mail_threads",
        sa.Column("ticket_id", sa.UUID(), sa.ForeignKey("tickets.id"), primary_key=True),
        sa.Column("token", sa.String(64), unique=True, nullable=False),
        sa.CheckConstraint("token ~ '^[0-9a-f]{64}$'"),
    )
    op.create_table(
        "outbound_messages",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("ticket_id", sa.UUID(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("message_id", sa.UUID(), unique=True, nullable=False),
        sa.Column("participant_id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), sa.ForeignKey("mail_senders.source_id"), nullable=False),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("envelope_from", sa.String(254), nullable=False),
        sa.Column("envelope_to", sa.String(254), nullable=False),
        sa.Column("namespace_hash", sa.String(64), nullable=False),
        sa.Column("wire", sa.LargeBinary(), nullable=False),
        sa.Column("smtp_message_id", sa.String(320), unique=True, nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.UUID()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(40)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id", "ticket_id"], ["ticket_messages.id", "ticket_messages.ticket_id"]
        ),
        sa.ForeignKeyConstraint(
            ["participant_id", "ticket_id"],
            ["ticket_participants.id", "ticket_participants.ticket_id"],
        ),
        sa.CheckConstraint(
            "state IN ('queued','preparing','transmitting','accepted','failed','uncertain')"
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 8 AND version > 0"),
        sa.CheckConstraint("octet_length(wire) BETWEEN 1 AND 262144"),
        sa.CheckConstraint("namespace_hash ~ '^[0-9a-f]{64}$'"),
        sa.CheckConstraint(
            "(state IN ('preparing','transmitting'))="
            "(lease_token IS NOT NULL AND lease_until IS NOT NULL)"
        ),
        sa.CheckConstraint("(state='accepted')=(accepted_at IS NOT NULL)"),
        sa.CheckConstraint(
            "last_error_code IS NULL OR last_error_code IN "
            "('temporary','permanent','transport','eligibility_revoked',"
            "'lease_expired','data_unknown','retry_exhausted')"
        ),
    )
    op.execute("""CREATE FUNCTION altvia_delivery_insert_guard() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF TG_TABLE_NAME='ticket_participants' THEN
        IF NOT EXISTS(SELECT 1 FROM tickets t JOIN client_contacts c
          ON c.id=t.requester_id AND c.client_id=t.client_id
          WHERE t.id=NEW.ticket_id AND c.id=NEW.contact_id AND c.email_normalized=NEW.email
            AND c.active AND NEW.active AND NEW.version=1) THEN
          RAISE EXCEPTION 'Invalid ticket requester attestation';
        END IF;
        RETURN NEW;
      END IF;
      IF NOT EXISTS(SELECT 1 FROM tickets t
        JOIN ticket_messages m ON m.ticket_id=t.id AND m.id=NEW.message_id
        JOIN ticket_participants p ON p.ticket_id=t.id AND p.id=NEW.participant_id
        JOIN mail_senders s ON s.queue_id=t.queue_id AND s.source_id=NEW.source_id
        WHERE t.id=NEW.ticket_id AND p.contact_id=t.requester_id AND p.active
          AND p.email=NEW.envelope_to AND s.from_email=NEW.envelope_from
          AND s.namespace_hash=NEW.namespace_hash) THEN
        RAISE EXCEPTION 'Invalid public delivery identity';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER participant_insert_guard BEFORE INSERT ON ticket_participants "
        "FOR EACH ROW EXECUTE FUNCTION altvia_delivery_insert_guard()"
    )
    op.execute(
        "CREATE TRIGGER outbound_insert_guard BEFORE INSERT ON outbound_messages "
        "FOR EACH ROW EXECUTE FUNCTION altvia_delivery_insert_guard()"
    )
    op.create_index("ix_delivery_pending", "outbound_messages", ["state", "next_attempt_at"])
    op.execute("""CREATE FUNCTION altvia_delivery_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Immutable mail record'; END IF;
      IF TG_TABLE_NAME='ticket_participants' THEN
        IF ROW(NEW.id,NEW.ticket_id,NEW.contact_id,NEW.email,NEW.evidence,NEW.attested_at)
          IS DISTINCT FROM ROW(OLD.id,OLD.ticket_id,OLD.contact_id,OLD.email,OLD.evidence,
          OLD.attested_at)
          OR OLD.active=false OR NEW.active=true OR NEW.version<>OLD.version+1 THEN
          RAISE EXCEPTION 'Immutable attestation'; END IF;
      ELSE
        IF ROW(NEW.id,NEW.ticket_id,NEW.message_id,NEW.source_id,NEW.participant_id,NEW.actor_id,
          NEW.envelope_from,NEW.envelope_to,NEW.namespace_hash,NEW.wire,NEW.smtp_message_id,NEW.created_at)
          IS DISTINCT FROM ROW(OLD.id,OLD.ticket_id,OLD.message_id,OLD.source_id,
          OLD.participant_id,OLD.actor_id,
          OLD.envelope_from,OLD.envelope_to,OLD.namespace_hash,OLD.wire,OLD.smtp_message_id,OLD.created_at)
          THEN RAISE EXCEPTION 'Immutable delivery snapshot'; END IF;
      END IF;
      RETURN NEW; END $$""")
    for table in ("outbound_messages", "ticket_participants"):
        op.execute(
            f"CREATE TRIGGER {table}_guard BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION altvia_delivery_guard()"
        )
    for table in ("mail_senders", "ticket_mail_threads"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION altvia_reject_audit_mutation()"
        )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE outbound_messages,ticket_participants,mail_senders,ticket_mail_threads,"
        "audit_logs,outbox_events,activity_events IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM outbound_messages)
      OR EXISTS(SELECT 1 FROM ticket_participants)
      OR EXISTS(SELECT 1 FROM mail_senders) OR EXISTS(SELECT 1 FROM ticket_mail_threads)
      OR EXISTS(SELECT 1 FROM audit_logs WHERE action LIKE 'mail.delivery_%'
        OR action LIKE 'mail.participant_%'
        OR action='mail.sender_registered' OR action='ticket.delivery_queued')
      OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type LIKE 'mail.delivery_%'
        OR event_type='ticket.delivery_queued')
      OR EXISTS(SELECT 1 FROM activity_events WHERE event_type='ticket.delivery_queued')
      THEN RAISE EXCEPTION 'Cannot contract durable mail delivery/history'; END IF; END $$""")
    for table in (
        "outbound_messages",
        "ticket_mail_threads",
        "ticket_participants",
        "mail_senders",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION altvia_delivery_guard()")
    op.execute("DROP FUNCTION altvia_delivery_insert_guard()")
    op.drop_constraint("uq_message_ticket", "ticket_messages")
    op.drop_constraint("uq_mail_source_queue", "mailbox_sources")
