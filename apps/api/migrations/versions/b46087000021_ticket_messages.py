"""Immutable public response drafts, structurally independent of private notes."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000021"
down_revision = "b46087000020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("ticket_version", sa.Integer(), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="public"),
        sa.Column("direction", sa.String(16), nullable=False, server_default="outbound"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("ticket_id", "ticket_version", name="uq_ticket_message_version"),
        sa.CheckConstraint("ticket_version > 1", name="ck_ticket_message_version"),
        sa.CheckConstraint("char_length(body_text) <= 10000", name="ck_ticket_message_length"),
        sa.CheckConstraint(
            r"char_length(btrim(body_text,U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F"
            r"\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009"
            r"\200A\2028\2029\202F\205F\3000')) > 0",
            name="ck_ticket_message_body",
        ),
        sa.CheckConstraint(
            "visibility='public' AND direction='outbound'", name="ck_ticket_message_kind"
        ),
    )
    op.execute(
        "CREATE TRIGGER ticket_messages_immutable BEFORE UPDATE OR DELETE ON ticket_messages "
        "FOR EACH ROW EXECUTE FUNCTION altvia_reject_audit_mutation()"
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE ticket_messages,tickets,audit_logs,outbox_events,activity_events "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM ticket_messages)
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action='ticket.message_drafted')
        OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type='ticket.message_drafted')
        OR EXISTS(SELECT 1 FROM activity_events WHERE event_type='ticket.message_drafted') THEN
        RAISE EXCEPTION 'Cannot downgrade while durable public message or history exists';
      END IF;
    END $$""")
    op.drop_table("ticket_messages")
