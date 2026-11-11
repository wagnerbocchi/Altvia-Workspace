"""Explicit private-note permission and append-only ticket notes."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000016"
down_revision = "b46087000015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "role_bindings",
        sa.Column("note_access", sa.String(10), nullable=False, server_default="none"),
    )
    op.create_check_constraint(
        "ck_role_binding_note_access",
        "role_bindings",
        "note_access='none' OR (scope_kind='queue' "
        "AND role_name IN ('agent','operations_manager') "
        "AND note_access IN ('read','write'))",
    )
    op.create_table(
        "ticket_notes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("ticket_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("ticket_id", "ticket_version", name="uq_ticket_note_version"),
        sa.CheckConstraint("ticket_version > 1", name="ck_ticket_note_version"),
        sa.CheckConstraint("char_length(body_text) <= 10000", name="ck_ticket_note_length"),
        sa.CheckConstraint(
            r"char_length(btrim(body_text,U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F"
            r"\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009"
            r"\200A\2028\2029\202F\205F\3000')) > 0",
            name="ck_ticket_note_body",
        ),
    )
    op.execute(
        "CREATE TRIGGER ticket_notes_immutable BEFORE UPDATE OR DELETE ON ticket_notes "
        "FOR EACH ROW EXECUTE FUNCTION altvia_reject_audit_mutation()"
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE ticket_notes, role_bindings, outbox_events, audit_logs, activity_events "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM ticket_notes)
        OR EXISTS(SELECT 1 FROM role_bindings WHERE note_access <> 'none')
        OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type='ticket.note_added'
            OR (event_type='ticket_queue.access_changed' AND payload ? 'note_access'))
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action='ticket.note_added'
            OR (action='ticket_queue.access_changed' AND details ? 'note_access'))
        OR EXISTS(SELECT 1 FROM activity_events WHERE event_type='ticket.note_added'
            OR (event_type='ticket_queue.access_changed' AND details ? 'note_access'))
        THEN RAISE EXCEPTION 'Cannot downgrade while durable note data or access history exists';
        END IF;
    END $$""")
    op.drop_table("ticket_notes")
    op.drop_constraint("ck_role_binding_note_access", "role_bindings", type_="check")
    op.drop_column("role_bindings", "note_access")
