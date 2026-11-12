"""Private append-only bounded MIME interpretation; no runtime grants."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000019"
down_revision = "b46087000018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_mail_previews",
        sa.Column("variant_id", sa.UUID(), primary_key=True),
        sa.Column("parser_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(998), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("part_count", sa.Integer(), nullable=True),
        sa.Column("attachment_count", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["variant_id"], ["inbound_mail_variants.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("parser_version=1", name="ck_preview_parser"),
        sa.CheckConstraint(
            "(status='ready' AND subject IS NOT NULL AND body_text IS NOT NULL "
            "AND part_count IS NOT NULL AND attachment_count IS NOT NULL AND reason IS NULL "
            "AND char_length(subject)<=998 AND octet_length(subject)<=3992 "
            "AND octet_length(body_text) BETWEEN 1 AND 65536 "
            "AND part_count BETWEEN 1 AND 64 AND attachment_count BETWEEN 0 AND part_count) OR "
            "(status='rejected' AND subject IS NULL AND body_text IS NULL AND part_count IS NULL "
            "AND attachment_count IS NULL AND reason IS NOT NULL AND reason IN "
            "('invalid_raw','invalid_headers','unsupported_mime','invalid_multipart',"
            "'invalid_encoding','unsupported_charset','structure_limit','text_limit',"
            "'html_limit','no_text'))",
            name="ck_preview_result",
        ),
    )
    op.execute("""CREATE FUNCTION altvia_guard_mail_preview() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      RAISE EXCEPTION 'Mail interpretation is append-only';
    END $$""")
    op.execute(
        "CREATE TRIGGER mail_preview_immutable BEFORE UPDATE OR DELETE "
        "ON inbound_mail_previews FOR EACH ROW EXECUTE FUNCTION altvia_guard_mail_preview()"
    )


def downgrade() -> None:
    op.execute("LOCK TABLE inbound_mail_previews,audit_logs,outbox_events IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM inbound_mail_previews)
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action='mailbox.message_normalized')
        OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type='mailbox.message_normalized') THEN
        RAISE EXCEPTION 'Cannot downgrade while durable MIME interpretation or history exists';
      END IF;
    END $$""")
    op.drop_table("inbound_mail_previews")
    op.execute("DROP FUNCTION altvia_guard_mail_preview()")
