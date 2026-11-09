"""Expand explicit customer registry, ceilings and scoped client activity."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000006"
down_revision = "b46087000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_client_name"),
        sa.CheckConstraint("version > 0", name="ck_client_version"),
    )
    op.create_table(
        "client_access_grants",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id"), primary_key=True),
        sa.Column("granted_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("role_bindings", sa.Column("client_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_role_binding_client", "role_bindings", "clients", ["client_id"], ["id"]
    )
    op.drop_constraint("ck_role_binding_scope", "role_bindings", type_="check")
    op.create_check_constraint(
        "ck_role_binding_scope",
        "role_bindings",
        "(scope_kind = 'global' AND team_id IS NULL AND client_id IS NULL "
        "AND role_name = 'platform_admin') OR "
        "(scope_kind = 'team' AND team_id IS NOT NULL AND client_id IS NULL "
        "AND role_name IN ('viewer','operations_manager')) OR "
        "(scope_kind = 'client' AND client_id IS NOT NULL AND team_id IS NULL "
        "AND role_name IN ('viewer','operations_manager'))",
    )
    op.create_index(
        "uq_role_bindings_client",
        "role_bindings",
        ["user_id", "client_id"],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'client'"),
    )
    op.drop_constraint("ck_activity_resource", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_resource", "activity_events", "resource_type IN ('identity','team','client')"
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM clients)
        OR EXISTS(SELECT 1 FROM activity_events WHERE resource_type='client')
        THEN RAISE EXCEPTION 'Cannot downgrade while durable client data exists'; END IF;
    END $$""")
    op.drop_constraint("ck_activity_resource", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_resource", "activity_events", "resource_type IN ('identity','team')"
    )
    op.drop_index("uq_role_bindings_client", table_name="role_bindings")
    op.drop_constraint("ck_role_binding_scope", "role_bindings", type_="check")
    op.create_check_constraint(
        "ck_role_binding_scope",
        "role_bindings",
        "(scope_kind = 'global' AND team_id IS NULL AND role_name = 'platform_admin') OR "
        "(scope_kind = 'team' AND team_id IS NOT NULL "
        "AND role_name IN ('viewer','operations_manager'))",
    )
    op.drop_constraint("fk_role_binding_client", "role_bindings", type_="foreignkey")
    op.drop_column("role_bindings", "client_id")
    op.drop_table("client_access_grants")
    op.drop_table("clients")
