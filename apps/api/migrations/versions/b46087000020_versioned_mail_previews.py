"""Preserve immutable v1 results while adding independent v2 interpretations."""

from alembic import op

revision = "b46087000020"
down_revision = "b46087000019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Owner normalization commands must be drained before this schema transition.
    # No data, defaults, immutable triggers, foreign keys or grants are rewritten.
    op.drop_constraint("inbound_mail_previews_pkey", "inbound_mail_previews", type_="primary")
    op.create_primary_key(
        "inbound_mail_previews_pkey", "inbound_mail_previews", ["variant_id", "parser_version"]
    )
    op.drop_constraint("ck_preview_parser", "inbound_mail_previews", type_="check")
    op.create_check_constraint(
        "ck_preview_parser", "inbound_mail_previews", "parser_version IN (1,2)"
    )


def downgrade() -> None:
    op.execute("LOCK TABLE inbound_mail_previews,audit_logs,outbox_events IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM inbound_mail_previews WHERE parser_version=2)
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action='mailbox.message_normalized'
                  AND details->>'parser_version'='2')
        OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type='mailbox.message_normalized'
                  AND schema_version=2) THEN
        RAISE EXCEPTION 'Cannot downgrade while durable MIME v2 interpretation or history exists';
      END IF;
    END $$""")
    op.drop_constraint("ck_preview_parser", "inbound_mail_previews", type_="check")
    op.create_check_constraint("ck_preview_parser", "inbound_mail_previews", "parser_version=1")
    op.drop_constraint("inbound_mail_previews_pkey", "inbound_mail_previews", type_="primary")
    op.create_primary_key("inbound_mail_previews_pkey", "inbound_mail_previews", ["variant_id"])
