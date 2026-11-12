"""Immutable promoted incoming history and protected case receipts."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000024"
down_revision = "b46087000023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_ticket_source", "tickets")
    op.create_check_constraint("ck_ticket_source", "tickets", "source IN ('manual','email')")
    op.create_unique_constraint("uq_ticket_context", "tickets", ["id", "client_id", "queue_id"])
    op.create_unique_constraint(
        "uq_case_ticket_context", "mail_triage_cases", ["id", "client_id", "queue_id"]
    )
    op.add_column("mail_triage_cases", sa.Column("ticket_id", sa.UUID()))
    op.add_column("mail_triage_cases", sa.Column("incoming_message_id", sa.UUID()))
    op.create_index(
        "ix_case_anchor_context",
        "mail_triage_cases",
        ["queue_id", "client_id", "contact_id", "email_snapshot", "message_id"],
        postgresql_where=sa.text("message_id IS NOT NULL AND ticket_id IS NOT NULL"),
    )
    op.drop_constraint("ck_case_state", "mail_triage_cases")
    op.create_check_constraint(
        "ck_case_state",
        "mail_triage_cases",
        "state IN ('ready','promoted','collision','revoked') AND version>0",
    )
    op.create_check_constraint(
        "ck_case_receipt",
        "mail_triage_cases",
        "(ticket_id IS NULL)=(incoming_message_id IS NULL) AND "
        "(state<>'promoted' OR ticket_id IS NOT NULL)",
    )
    op.create_table(
        "ticket_incoming_messages",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("queue_id", sa.UUID(), nullable=False),
        sa.Column("ticket_version", sa.Integer(), nullable=False),
        sa.Column(
            "actor_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id", "client_id", "queue_id"],
            ["tickets.id", "tickets.client_id", "tickets.queue_id"],
            name="fk_incoming_ticket_context",
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "client_id", "queue_id"],
            ["mail_triage_cases.id", "mail_triage_cases.client_id", "mail_triage_cases.queue_id"],
            name="fk_incoming_case_context",
        ),
        sa.UniqueConstraint("case_id", name="uq_incoming_case"),
        sa.UniqueConstraint("ticket_id", "ticket_version", name="uq_incoming_version"),
        sa.UniqueConstraint("id", "ticket_id", "case_id", name="uq_incoming_receipt"),
        sa.CheckConstraint("ticket_version>1", name="ck_incoming_version"),
    )
    op.create_index(
        "ix_incoming_ticket_page", "ticket_incoming_messages", ["ticket_id", "ticket_version"]
    )
    op.create_foreign_key(
        "fk_case_receipt",
        "mail_triage_cases",
        "ticket_incoming_messages",
        ["incoming_message_id", "ticket_id", "id"],
        ["id", "ticket_id", "case_id"],
    )
    op.execute("""CREATE OR REPLACE FUNCTION altvia_case_guard()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Immutable classified case'; END IF;
      IF (to_jsonb(NEW)-'state'-'version'-'ticket_id'-'incoming_message_id') IS DISTINCT FROM
        (to_jsonb(OLD)-'state'-'version'-'ticket_id'-'incoming_message_id')
        OR OLD.version=2147483647 OR NEW.version<>OLD.version+1
        OR (OLD.state='collision' AND NEW.state<>'collision')
        OR (OLD.state='revoked' AND NEW.state NOT IN ('revoked','collision'))
        OR (NEW.state='ready' AND OLD.state<>'ready')
        OR (OLD.ticket_id IS NOT NULL AND (NEW.ticket_id IS DISTINCT FROM OLD.ticket_id
          OR NEW.incoming_message_id IS DISTINCT FROM OLD.incoming_message_id))
        OR (OLD.ticket_id IS NULL AND NEW.ticket_id IS NOT NULL AND
          (OLD.state<>'ready' OR NEW.state<>'promoted'))
        OR (NEW.state='promoted' AND OLD.state NOT IN ('ready','promoted')) THEN
        RAISE EXCEPTION 'Invalid classified transition'; END IF;
      RETURN NEW; END $$""")
    op.execute("""CREATE FUNCTION altvia_incoming_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NOT EXISTS(SELECT 1 FROM mail_triage_cases c JOIN tickets t
          ON t.id=NEW.ticket_id AND t.client_id=c.client_id AND t.queue_id=c.queue_id
          WHERE c.id=NEW.case_id AND c.state='ready' AND c.ticket_id IS NULL
          AND c.received_at=NEW.received_at AND t.version=NEW.ticket_version
          AND t.requester_id=c.contact_id) THEN
        RAISE EXCEPTION 'Invalid incoming history'; END IF;
      RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER incoming_insert BEFORE INSERT ON ticket_incoming_messages "
        "FOR EACH ROW EXECUTE FUNCTION altvia_incoming_guard()"
    )
    op.execute(
        "CREATE TRIGGER incoming_immutable BEFORE UPDATE OR DELETE ON ticket_incoming_messages "
        "FOR EACH ROW EXECUTE FUNCTION altvia_reject_audit_mutation()"
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE mail_triage_cases,mail_case_origins,ticket_incoming_messages,"
        "tickets,audit_logs,outbox_events IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM mail_triage_cases)
      OR EXISTS(SELECT 1 FROM mail_case_origins) OR EXISTS(SELECT 1 FROM ticket_incoming_messages)
      OR EXISTS(SELECT 1 FROM tickets WHERE source='email')
      OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type='ticket.message_received'
        OR (event_type='mail.case_aliased' AND schema_version=2))
      OR EXISTS(SELECT 1 FROM audit_logs WHERE action='ticket.message_received')
      THEN RAISE EXCEPTION 'Cannot contract incoming conversation/history'; END IF; END $$""")
    op.drop_constraint("fk_case_receipt", "mail_triage_cases")
    op.drop_table("ticket_incoming_messages")
    op.execute("DROP FUNCTION altvia_incoming_guard()")
    op.drop_constraint("ck_case_receipt", "mail_triage_cases")
    op.drop_index("ix_case_anchor_context", "mail_triage_cases")
    op.drop_column("mail_triage_cases", "incoming_message_id")
    op.drop_column("mail_triage_cases", "ticket_id")
    op.drop_constraint("uq_case_ticket_context", "mail_triage_cases")
    op.drop_constraint("uq_ticket_context", "tickets")
    op.drop_constraint("ck_case_state", "mail_triage_cases")
    op.create_check_constraint(
        "ck_case_state",
        "mail_triage_cases",
        "state IN ('ready','collision','revoked') AND version>0",
    )
    op.drop_constraint("ck_ticket_source", "tickets")
    op.create_check_constraint("ck_ticket_source", "tickets", "source='manual'")
    op.execute("""CREATE OR REPLACE FUNCTION altvia_case_guard()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Immutable classified case'; END IF;
      IF (to_jsonb(NEW)-'state'-'version') IS DISTINCT FROM (to_jsonb(OLD)-'state'-'version')
        OR OLD.version=2147483647 OR NEW.version<>OLD.version+1
        OR (OLD.state='collision' AND NEW.state<>'collision')
        OR (OLD.state='revoked' AND NEW.state NOT IN ('revoked','collision'))
        OR (NEW.state='ready' AND OLD.state<>'ready') THEN
        RAISE EXCEPTION 'Invalid classified transition'; END IF;
      RETURN NEW; END $$""")
