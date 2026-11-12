"""Concrete immutable content sets and actual versioned outbound MIME."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000026"
down_revision = "b46087000025"
branch_labels = None
depends_on = None

OWNERS = (
    ("ticket_messages", "ticket_message_attachments", "message_id", "ticket_id", "public"),
    ("ticket_notes", "ticket_note_attachments", "note_id", "ticket_id", "note"),
    ("work_item_comments", "work_comment_attachments", "comment_id", "work_item_id", "work"),
)


def upgrade() -> None:
    for parent in ("ticket_id", "work_item_id"):
        op.create_unique_constraint(
            f"uq_attachment_{parent}_purpose", "attachments", ["id", parent, "purpose"]
        )
    for content, links, key, parent, purpose in OWNERS:
        op.add_column(
            content, sa.Column("attachment_count", sa.Integer(), nullable=False, server_default="0")
        )
        op.create_check_constraint(
            f"ck_{content}_attachment_count", content, "attachment_count BETWEEN 0 AND 20"
        )
        if content != "ticket_messages":
            op.create_unique_constraint(f"uq_{content}_parent", content, ["id", parent])
        op.create_table(
            links,
            sa.Column(key, sa.UUID(), primary_key=True),
            sa.Column("attachment_id", sa.UUID(), primary_key=True),
            sa.Column(parent, sa.UUID(), nullable=False),
            sa.Column("purpose", sa.String(10), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint([key, parent], [f"{content}.id", f"{content}.{parent}"]),
            sa.ForeignKeyConstraint(
                ["attachment_id", parent, "purpose"],
                ["attachments.id", f"attachments.{parent}", "attachments.purpose"],
            ),
            sa.UniqueConstraint(key, "position"),
            sa.CheckConstraint(f"purpose='{purpose}' AND position BETWEEN 0 AND 19"),
        )
        op.execute(f"""CREATE FUNCTION altvia_{links}_insert() RETURNS trigger
        LANGUAGE plpgsql AS $$ DECLARE expected integer; BEGIN
          SELECT attachment_count INTO expected FROM {content} WHERE id=NEW.{key};
          IF expected IS NULL OR NEW.position>=expected OR NOT EXISTS(
            SELECT 1 FROM attachments WHERE id=NEW.attachment_id AND {parent}=NEW.{parent}
              AND purpose='{purpose}' AND state='ready' AND policy_version=1) THEN
            RAISE EXCEPTION 'Invalid immutable content attachment'; END IF;
          RETURN NEW; END $$""")
        op.execute(
            f"CREATE TRIGGER link_insert BEFORE INSERT ON {links} "
            f"FOR EACH ROW EXECUTE FUNCTION altvia_{links}_insert()"
        )
        op.execute(
            f"CREATE TRIGGER link_immutable BEFORE UPDATE OR DELETE "
            f"ON {links} FOR EACH ROW EXECUTE FUNCTION "
            f"altvia_reject_audit_mutation()"
        )
        op.execute(f"""CREATE FUNCTION altvia_{links}_count() RETURNS trigger
        LANGUAGE plpgsql AS $$ DECLARE identifier uuid; expected integer; actual integer; BEGIN
          IF TG_TABLE_NAME='{content}' THEN identifier=NEW.id;
          ELSE identifier=NEW.{key}; END IF;
          SELECT attachment_count INTO expected FROM {content} WHERE id=identifier;
          SELECT count(*) INTO actual FROM {links} WHERE {key}=identifier;
          IF expected IS DISTINCT FROM actual THEN
            RAISE EXCEPTION 'Immutable content attachment count mismatch'; END IF;
          RETURN NULL; END $$""")
        for table in (content, links):
            op.execute(
                f"CREATE CONSTRAINT TRIGGER attachment_count_guard AFTER "
                f"INSERT ON {table} DEFERRABLE INITIALLY DEFERRED FOR "
                f"EACH ROW EXECUTE FUNCTION altvia_{links}_count()"
            )
    op.add_column(
        "outbound_messages",
        sa.Column("wire_format", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute("""DO $$ DECLARE item record; BEGIN
      FOR item IN SELECT conname FROM pg_constraint WHERE conrelid='outbound_messages'::regclass
        AND contype='c' AND pg_get_constraintdef(oid) LIKE '%octet_length(wire)%' LOOP
        EXECUTE format('ALTER TABLE outbound_messages DROP CONSTRAINT %I',item.conname);
      END LOOP; END $$""")
    op.create_check_constraint(
        "ck_outbound_wire_format",
        "outbound_messages",
        "(wire_format=1 AND octet_length(wire) BETWEEN 1 AND "
        "262144) OR (wire_format=2 AND octet_length(wire) "
        "BETWEEN 1 AND 26214400)",
    )
    op.execute("""CREATE FUNCTION altvia_delivery_format_guard() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='UPDATE' THEN
        IF NEW.wire_format IS DISTINCT FROM OLD.wire_format THEN
          RAISE EXCEPTION 'Immutable delivery format'; END IF;
      ELSE
        IF NOT EXISTS(SELECT 1 FROM ticket_messages WHERE id=NEW.message_id
          AND ticket_id=NEW.ticket_id AND ((attachment_count=0 AND NEW.wire_format=1)
            OR (attachment_count>0 AND NEW.wire_format=2))) THEN
          RAISE EXCEPTION 'Invalid delivery content format'; END IF;
      END IF; RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER delivery_format_guard BEFORE INSERT OR "
        "UPDATE ON outbound_messages FOR EACH ROW EXECUTE "
        "FUNCTION altvia_delivery_format_guard()"
    )


def downgrade() -> None:
    tables = ",".join(
        [t for content, links, *_ in OWNERS for t in (content, links)] + ["outbound_messages"]
    )
    op.execute(f"LOCK TABLE {tables} IN ACCESS EXCLUSIVE MODE")
    checks = " OR ".join(
        [
            f"EXISTS(SELECT 1 FROM {links}) OR EXISTS(SELECT 1 FROM "
            f"{content} WHERE attachment_count<>0)"
            for content, links, *_ in OWNERS
        ]
    )
    op.execute(
        f"DO $$ BEGIN IF {checks} OR EXISTS(SELECT 1 FROM "
        f"outbound_messages WHERE wire_format=2) THEN RAISE "
        f"EXCEPTION 'Cannot contract immutable file "
        f"content/history'; END IF; END $$"
    )
    op.execute("DROP TRIGGER delivery_format_guard ON outbound_messages")
    op.execute("DROP FUNCTION altvia_delivery_format_guard()")
    op.drop_constraint("ck_outbound_wire_format", "outbound_messages")
    op.create_check_constraint(
        "ck_outbound_wire_legacy", "outbound_messages", "octet_length(wire) BETWEEN 1 AND 262144"
    )
    op.drop_column("outbound_messages", "wire_format")
    for content, links, _, _, _ in reversed(OWNERS):
        op.execute(f"DROP TRIGGER attachment_count_guard ON {content}")
        op.drop_table(links)
        op.execute(f"DROP FUNCTION altvia_{links}_insert()")
        op.execute(f"DROP FUNCTION altvia_{links}_count()")
        if content != "ticket_messages":
            op.drop_constraint(f"uq_{content}_parent", content)
        op.drop_constraint(f"ck_{content}_attachment_count", content)
        op.drop_column(content, "attachment_count")
    for parent in ("ticket_id", "work_item_id"):
        op.drop_constraint(f"uq_attachment_{parent}_purpose", "attachments")
