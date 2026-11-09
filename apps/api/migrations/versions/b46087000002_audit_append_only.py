"""Enforce immutable audit history for ordinary UPDATE and DELETE statements."""

from alembic import op

revision = "b46087000002"
down_revision = "abc22906cd75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION altvia_reject_audit_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Audit history is append-only' USING ERRCODE = '42501';
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER audit_logs_immutable BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION altvia_reject_audit_mutation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_logs_immutable ON audit_logs")
    op.execute("DROP FUNCTION altvia_reject_audit_mutation()")
