"""Preserve global administration and admit explicit constrained team grants."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000004"
down_revision = "b46087000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM role_bindings
                       WHERE scope_kind <> 'global' OR role_name <> 'platform_admin') THEN
                RAISE EXCEPTION 'Unsupported legacy global grants; review before upgrading';
            END IF;
        END $$
    """)
    op.add_column(
        "role_bindings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
    )
    op.add_column("role_bindings", sa.Column("team_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_role_bindings_team_id", "role_bindings", "teams", ["team_id"], ["id"])
    op.drop_constraint("ck_initial_global_scope", "role_bindings", type_="check")
    op.drop_constraint("role_bindings_pkey", "role_bindings", type_="primary")
    op.create_primary_key("role_bindings_pkey", "role_bindings", ["id"])
    op.create_check_constraint(
        "ck_role_binding_scope",
        "role_bindings",
        "(scope_kind = 'global' AND team_id IS NULL AND role_name = 'platform_admin') OR "
        "(scope_kind = 'team' AND team_id IS NOT NULL "
        "AND role_name IN ('viewer','operations_manager'))",
    )
    op.create_index("ix_role_bindings_user_id", "role_bindings", ["user_id"])
    op.create_index(
        "uq_role_bindings_global",
        "role_bindings",
        ["user_id", "role_name"],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'global'"),
    )
    op.create_index(
        "uq_role_bindings_team",
        "role_bindings",
        ["user_id", "role_name", "team_id"],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'team'"),
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM role_bindings
                       WHERE scope_kind <> 'global' OR team_id IS NOT NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade while scoped grants exist';
            END IF;
        END $$
    """)
    op.drop_index("uq_role_bindings_team", table_name="role_bindings")
    op.drop_index("uq_role_bindings_global", table_name="role_bindings")
    op.drop_index("ix_role_bindings_user_id", table_name="role_bindings")
    op.drop_constraint("ck_role_binding_scope", "role_bindings", type_="check")
    op.drop_constraint("fk_role_bindings_team_id", "role_bindings", type_="foreignkey")
    op.drop_constraint("role_bindings_pkey", "role_bindings", type_="primary")
    op.create_primary_key("role_bindings_pkey", "role_bindings", ["user_id", "role_name"])
    op.drop_column("role_bindings", "team_id")
    op.drop_column("role_bindings", "id")
    op.create_check_constraint("ck_initial_global_scope", "role_bindings", "scope_kind = 'global'")
