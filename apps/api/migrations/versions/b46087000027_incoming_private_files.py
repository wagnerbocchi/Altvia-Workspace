"""Immutable ordered case-owned files with owner-only creation provenance."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000027"
down_revision = "b46087000026"
branch_labels = None
depends_on = None

CASE_HEADER = (
    "(file_extraction_version=0 AND file_set_status='legacy' AND file_count=0 AND "
    "file_rejection_reason IS NULL) OR (file_extraction_version=1 AND "
    "((file_set_status='complete' AND file_count BETWEEN 0 AND 20 AND "
    "file_rejection_reason IS NULL) OR (file_set_status='unavailable' AND file_count=0 AND "
    "file_rejection_reason IS NOT NULL AND file_rejection_reason IN "
    "('file_structure','file_count','file_size','file_encoding','file_filename',"
    "'file_type','file_parameter'))))"
)
OWNERS = (
    "(mail_case_id IS NULL AND file_position IS NULL AND creator_id IS NOT NULL AND "
    "((ticket_id IS NOT NULL AND work_item_id IS NULL AND purpose IN ('public','note')) OR "
    "(ticket_id IS NULL AND work_item_id IS NOT NULL AND purpose='work'))) OR "
    "(mail_case_id IS NOT NULL AND ticket_id IS NULL AND work_item_id IS NULL AND "
    "purpose='incoming' AND creator_id IS NULL AND parent_version=1 AND "
    "file_position IS NOT NULL AND file_position BETWEEN 0 AND 19)"
)


def upgrade() -> None:
    for column in (
        sa.Column("file_extraction_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_set_status", sa.String(11), nullable=False, server_default="legacy"),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_rejection_reason", sa.String(20)),
    ):
        op.add_column("mail_triage_cases", column)
    op.create_check_constraint("ck_case_files", "mail_triage_cases", CASE_HEADER)
    op.add_column("attachments", sa.Column("mail_case_id", sa.UUID()))
    op.add_column("attachments", sa.Column("file_position", sa.Integer()))
    op.create_foreign_key(
        "fk_attachment_mail_case",
        "attachments",
        "mail_triage_cases",
        ["mail_case_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_attachment_case_position", "attachments", ["mail_case_id", "file_position"]
    )
    op.alter_column("attachments", "creator_id", nullable=True)
    op.drop_constraint("ck_attachment_owner", "attachments")
    op.create_check_constraint("ck_attachment_owner", "attachments", OWNERS)
    # Existing JSON identity guards automatically cover the new immutable fields.
    # No case lookup is permitted on the ordinary worker UPDATE path.
    op.execute("""CREATE FUNCTION altvia_case_file_insert() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF current_user<>(SELECT pg_get_userbyid(relowner) FROM pg_class
        WHERE oid='attachments'::regclass) THEN
        RAISE EXCEPTION 'Case file owner required'; END IF;
      IF NOT EXISTS(SELECT 1 FROM mail_triage_cases WHERE id=NEW.mail_case_id
        AND file_extraction_version=1 AND file_set_status='complete'
        AND NEW.file_position<file_count) THEN
        RAISE EXCEPTION 'Invalid immutable case file'; END IF;
      RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER case_file_insert BEFORE INSERT ON attachments FOR EACH ROW "
        "WHEN (NEW.mail_case_id IS NOT NULL) EXECUTE FUNCTION altvia_case_file_insert()"
    )
    op.execute("""CREATE FUNCTION altvia_case_file_count() RETURNS trigger
    LANGUAGE plpgsql AS $$ DECLARE identifier uuid; expected integer; actual integer; BEGIN
      IF TG_TABLE_NAME='mail_triage_cases' THEN identifier=NEW.id;
      ELSE identifier=NEW.mail_case_id; END IF;
      SELECT file_count INTO expected FROM mail_triage_cases WHERE id=identifier;
      SELECT count(*) INTO actual FROM attachments WHERE mail_case_id=identifier;
      IF expected IS DISTINCT FROM actual THEN
        RAISE EXCEPTION 'Immutable case file count mismatch'; END IF;
      RETURN NULL; END $$""")
    op.execute(
        "CREATE CONSTRAINT TRIGGER case_file_count AFTER INSERT ON mail_triage_cases "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION altvia_case_file_count()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER case_file_count AFTER INSERT ON attachments "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.mail_case_id IS NOT NULL) "
        "EXECUTE FUNCTION altvia_case_file_count()"
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE mail_triage_cases,attachments,audit_logs,outbox_events IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM mail_triage_cases
      WHERE file_extraction_version<>0)
      OR EXISTS(SELECT 1 FROM attachments WHERE mail_case_id IS NOT NULL)
      OR EXISTS(SELECT 1 FROM outbox_events WHERE aggregate_type='attachment' AND schema_version=2)
      OR EXISTS(SELECT 1 FROM audit_logs WHERE action='file.uploaded'
        AND details->>'actor_kind'='management_command') THEN
      RAISE EXCEPTION 'Cannot contract incoming files/history'; END IF; END $$""")
    op.execute("DROP TRIGGER case_file_count ON mail_triage_cases")
    op.execute("DROP TRIGGER case_file_count ON attachments")
    op.execute("DROP TRIGGER case_file_insert ON attachments")
    op.execute("DROP FUNCTION altvia_case_file_count()")
    op.execute("DROP FUNCTION altvia_case_file_insert()")
    op.drop_constraint("ck_attachment_owner", "attachments")
    op.create_check_constraint(
        "ck_attachment_owner",
        "attachments",
        "(ticket_id IS NOT NULL AND work_item_id IS NULL AND purpose IN "
        "('public','note')) OR (ticket_id IS NULL AND work_item_id IS NOT NULL AND purpose='work')",
    )
    op.alter_column("attachments", "creator_id", nullable=False)
    op.drop_constraint("uq_attachment_case_position", "attachments")
    op.drop_constraint("fk_attachment_mail_case", "attachments")
    op.drop_column("attachments", "file_position")
    op.drop_column("attachments", "mail_case_id")
    op.drop_constraint("ck_case_files", "mail_triage_cases")
    for column in (
        "file_extraction_version",
        "file_set_status",
        "file_count",
        "file_rejection_reason",
    ):
        op.drop_column("mail_triage_cases", column)
