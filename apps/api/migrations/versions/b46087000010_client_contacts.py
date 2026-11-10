"""External contacts and a database-enforced same-client default project."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000010"
down_revision = "b46087000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_project_client", "projects", ["id", "client_id"])
    op.add_column("clients", sa.Column("default_project_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_client_default_project",
        "clients",
        "projects",
        ["default_project_id", "id"],
        ["id", "client_id"],
    )
    op.create_table(
        "client_contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("email_normalized", sa.String(254), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("verification_state", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("client_id", "email_normalized", name="uq_contact_client_email"),
        sa.CheckConstraint("char_length(btrim(display_name)) > 0", name="ck_contact_name"),
        sa.CheckConstraint("version > 0", name="ck_contact_version"),
        sa.CheckConstraint("verification_state='unverified'", name="ck_contact_verification"),
    )
    op.create_index("ix_client_contacts_page", "client_contacts", ["client_id", "id"])


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM client_contacts)
        OR EXISTS(SELECT 1 FROM clients WHERE default_project_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM outbox_events WHERE
            event_type IN ('client.contact_created','client.contact_updated') OR
            (event_type='client.updated' AND
             payload->>'changed_fields' LIKE '%default_project_id%'))
        OR EXISTS(SELECT 1 FROM activity_events WHERE
            event_type IN ('client.contact_created','client.contact_updated') OR
            (event_type='client.updated' AND
             details->>'changed_fields' LIKE '%default_project_id%'))
        OR EXISTS(SELECT 1 FROM audit_logs WHERE
            action IN ('client.contact_created','client.contact_updated') OR
            (action='client.updated' AND details->>'changed_fields' LIKE '%default_project_id%'))
        THEN RAISE EXCEPTION 'Cannot downgrade while durable contact or default data exists';
        END IF;
    END $$""")
    op.drop_table("client_contacts")
    op.drop_constraint("fk_client_default_project", "clients", type_="foreignkey")
    op.drop_column("clients", "default_project_id")
    op.drop_constraint("uq_project_client", "projects", type_="unique")
