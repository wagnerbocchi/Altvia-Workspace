"""Owner-classified immutable case projection; private provenance and invalidation."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000023"
down_revision = "b46087000022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_triage_cases",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("queue_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column(
            "primary_variant_id",
            sa.UUID(),
            sa.ForeignKey("inbound_mail_variants.id"),
            nullable=False,
        ),
        sa.Column("email_snapshot", sa.String(254), nullable=False),
        sa.Column("contact_name", sa.String(150), nullable=False),
        sa.Column("subject", sa.String(998), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("routing_version", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(320)),
        sa.Column("in_reply_to", sa.String(320)),
        sa.Column("references_ids", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("thread_token", sa.String(64)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id", "queue_id"], ["mailbox_sources.id", "mailbox_sources.queue_id"]
        ),
        sa.ForeignKeyConstraint(
            ["contact_id", "client_id"], ["client_contacts.id", "client_contacts.client_id"]
        ),
        sa.UniqueConstraint(
            "id", "source_id", "client_id", "contact_id", "email_snapshot", name="uq_case_context"
        ),
        sa.CheckConstraint(
            "state IN ('ready','collision','revoked') AND version > 0", name="ck_case_state"
        ),
        sa.CheckConstraint("routing_version=1", name="ck_case_routing"),
        sa.CheckConstraint(
            "char_length(subject)<=998 AND octet_length(subject)<=3992 AND "
            "octet_length(body_text) BETWEEN 1 AND 65536",
            name="ck_case_text",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(references_ids)='array' AND jsonb_array_length(references_ids)<=64",
            name="ck_case_references",
        ),
        sa.CheckConstraint(
            "thread_token IS NULL OR thread_token ~ '^[0-9a-f]{64}$'", name="ck_case_token"
        ),
    )
    op.create_index(
        "uq_case_message_context",
        "mail_triage_cases",
        ["source_id", "client_id", "contact_id", "email_snapshot", "message_id"],
        unique=True,
        postgresql_where=sa.text("message_id IS NOT NULL"),
    )
    op.create_index("ix_mail_cases_page", "mail_triage_cases", ["created_at", "id"])
    op.create_table(
        "mail_case_origins",
        sa.Column(
            "variant_id", sa.UUID(), sa.ForeignKey("inbound_mail_variants.id"), primary_key=True
        ),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column(
            "envelope_id", sa.UUID(), sa.ForeignKey("inbound_mail_envelopes.id"), nullable=False
        ),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("email_snapshot", sa.String(254), nullable=False),
        sa.Column("contact_version", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.String(200), nullable=False),
        sa.Column("routing_version", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.Integer(), nullable=False),
        sa.Column("disposition", sa.String(20), nullable=False),
        sa.Column(
            "attested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "source_id", "client_id", "contact_id", "email_snapshot"],
            [
                "mail_triage_cases.id",
                "mail_triage_cases.source_id",
                "mail_triage_cases.client_id",
                "mail_triage_cases.contact_id",
                "mail_triage_cases.email_snapshot",
            ],
        ),
        sa.CheckConstraint(
            "raw_sha256 ~ '^[0-9a-f]{64}$' AND evidence ~ "
            "'^[A-Za-z0-9._:/-]{1,200}$' AND contact_version>0",
            name="ck_origin_proof",
        ),
        sa.CheckConstraint(
            "disposition IN ('primary','alias','collision') AND "
            "routing_version=1 AND parser_version=2",
            name="ck_origin_disposition",
        ),
    )
    op.execute("""CREATE FUNCTION altvia_case_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME='mail_triage_cases' THEN
        IF NOT EXISTS(SELECT 1 FROM inbound_mail_variants v
          JOIN inbound_mail_envelopes e ON e.id=v.envelope_id
          JOIN inbound_mail_previews p ON p.variant_id=v.id AND p.parser_version=2
          JOIN client_contacts c ON c.id=NEW.contact_id AND c.client_id=NEW.client_id
          WHERE v.id=NEW.primary_variant_id AND e.source_id=NEW.source_id
          AND e.state='quarantine' AND p.status='ready' AND p.subject=NEW.subject
          AND p.body_text=NEW.body_text AND c.email_normalized=NEW.email_snapshot
          AND c.display_name=NEW.contact_name AND NEW.received_at=e.created_at
          AND NEW.state='ready' AND NEW.version=1) THEN
          RAISE EXCEPTION 'Invalid classified publication'; END IF;
      ELSE
        IF NOT EXISTS(SELECT 1 FROM inbound_mail_variants v
          JOIN inbound_mail_envelopes e ON e.id=v.envelope_id
          WHERE v.id=NEW.variant_id AND v.envelope_id=NEW.envelope_id
          AND v.raw_sha256=NEW.raw_sha256 AND e.source_id=NEW.source_id) THEN
          RAISE EXCEPTION 'Invalid classified origin'; END IF;
      END IF;
      RETURN NEW; END $$""")
    for table in ("mail_triage_cases", "mail_case_origins"):
        op.execute(
            f"CREATE TRIGGER {table}_insert BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION altvia_case_insert_guard()"
        )
    op.execute("""CREATE FUNCTION altvia_case_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Immutable classified case'; END IF;
      IF (to_jsonb(NEW)-'state'-'version') IS DISTINCT FROM (to_jsonb(OLD)-'state'-'version')
        OR OLD.version=2147483647 OR NEW.version<>OLD.version+1
        OR (OLD.state='collision' AND NEW.state<>'collision')
        OR (OLD.state='revoked' AND NEW.state NOT IN ('revoked','collision'))
        OR (NEW.state='ready' AND OLD.state<>'ready') THEN
        RAISE EXCEPTION 'Invalid classified transition'; END IF;
      RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER mail_case_guard BEFORE UPDATE OR DELETE ON "
        "mail_triage_cases FOR EACH ROW EXECUTE FUNCTION altvia_case_guard()"
    )
    op.execute(
        "CREATE TRIGGER mail_origin_immutable BEFORE UPDATE OR DELETE ON "
        "mail_case_origins FOR EACH ROW EXECUTE FUNCTION "
        "altvia_reject_audit_mutation()"
    )
    op.execute("""CREATE FUNCTION altvia_case_collision() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE item record; instant timestamptz; correlation text; payload jsonb;
    BEGIN
      IF NEW.state='collision' AND OLD.state<>'collision' THEN
        FOR item IN SELECT c.id,c.source_id,c.version FROM mail_triage_cases c
          WHERE c.state<>'collision' AND EXISTS(SELECT 1 FROM mail_case_origins o
            WHERE o.case_id=c.id AND o.envelope_id=NEW.id) ORDER BY c.id FOR UPDATE OF c LOOP
          UPDATE mail_triage_cases SET state='collision',version=version+1 WHERE id=item.id;
          instant:=clock_timestamp(); correlation:=replace(gen_random_uuid()::text,'-','');
          payload:=jsonb_build_object('actor_id',NULL,'actor_kind','source_capture',
            'case_id',item.id::text,'source_id',item.source_id::text,'state','collision');
          INSERT INTO audit_logs(id,actor_id,action,resource_id,occurred_at,correlation_id,details)
            VALUES(gen_random_uuid(),NULL,'mail.case_collided',item.id,instant,correlation,payload);
          INSERT INTO outbox_events(event_id,schema_version,aggregate_type,aggregate_id,
            aggregate_version,event_type,payload,occurred_at,correlation_id,status,attempts,next_attempt_at)
            VALUES(gen_random_uuid(),1,'mail_case',item.id,item.version+1,'mail.case_collided',payload,
              instant,correlation,'pending',0,instant);
        END LOOP;
      END IF; RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER mail_case_collision AFTER UPDATE OF state ON "
        "inbound_mail_envelopes FOR EACH ROW EXECUTE FUNCTION "
        "altvia_case_collision()"
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE "
        "mail_triage_cases,mail_case_origins,audit_logs,outbox_events IN "
        "ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM mail_triage_cases)
      OR EXISTS(SELECT 1 FROM mail_case_origins)
      OR EXISTS(SELECT 1 FROM audit_logs WHERE action LIKE 'mail.case_%')
      OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type LIKE 'mail.case_%')
      THEN RAISE EXCEPTION 'Cannot contract classified mail/history'; END IF; END $$""")
    op.execute("DROP TRIGGER mail_case_collision ON inbound_mail_envelopes")
    op.execute("DROP FUNCTION altvia_case_collision()")
    op.drop_table("mail_case_origins")
    op.drop_table("mail_triage_cases")
    op.execute("DROP FUNCTION altvia_case_guard()")
    op.execute("DROP FUNCTION altvia_case_insert_guard()")
