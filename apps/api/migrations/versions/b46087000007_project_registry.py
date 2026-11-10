"""Expand project scopes, real members and operational classification."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000007"
down_revision = "b46087000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, prefix in [("operational_areas", "area"), ("projects", "project")]:
        columns = [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("name", sa.String(150), nullable=False, unique=table == "operational_areas"),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        ]
        constraints = [
            sa.CheckConstraint("char_length(btrim(name)) > 0", name=f"ck_{prefix}_name"),
            sa.CheckConstraint("version > 0", name=f"ck_{prefix}_version"),
        ]
        if table == "projects":
            columns += [
                sa.Column("scope_kind", sa.String(20), nullable=False),
                sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id"), nullable=True),
                sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id"), nullable=False),
                sa.Column(
                    "operational_area_id",
                    sa.Uuid(),
                    sa.ForeignKey("operational_areas.id"),
                    nullable=True,
                ),
            ]
            constraints += [
                sa.CheckConstraint(
                    "(scope_kind='internal' AND client_id IS NULL) OR "
                    "(scope_kind='client' AND client_id IS NOT NULL)",
                    name="ck_project_scope",
                )
            ]
        op.create_table(table, *columns, *constraints)
    op.create_index("ix_projects_client_id", "projects", ["client_id"])
    op.create_index("ix_projects_team_id", "projects", ["team_id"])
    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])
    op.add_column("role_bindings", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_role_binding_project", "role_bindings", "projects", ["project_id"], ["id"]
    )
    op.drop_constraint("ck_role_binding_scope", "role_bindings", type_="check")
    op.create_check_constraint(
        "ck_role_binding_scope",
        "role_bindings",
        "(scope_kind='global' AND team_id IS NULL AND client_id IS NULL "
        "AND project_id IS NULL AND role_name='platform_admin') OR "
        "(scope_kind='team' AND team_id IS NOT NULL AND client_id IS NULL "
        "AND project_id IS NULL AND role_name IN ('viewer','operations_manager')) OR "
        "(scope_kind='client' AND client_id IS NOT NULL AND team_id IS NULL "
        "AND project_id IS NULL AND role_name IN ('viewer','operations_manager')) OR "
        "(scope_kind='project' AND project_id IS NOT NULL AND team_id IS NULL "
        "AND client_id IS NULL AND role_name IN ('viewer','agent','project_manager'))",
    )
    op.create_index(
        "uq_role_bindings_project",
        "role_bindings",
        ["user_id", "project_id"],
        unique=True,
        postgresql_where=sa.text("scope_kind='project'"),
    )
    op.drop_constraint("ck_activity_resource", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_resource",
        "activity_events",
        "resource_type IN ('identity','team','client','project','operational_area')",
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM projects) OR EXISTS(SELECT 1 FROM operational_areas)
        OR EXISTS(SELECT 1 FROM activity_events
                  WHERE resource_type IN ('project','operational_area'))
        THEN RAISE EXCEPTION 'Cannot downgrade while durable project or area data exists';
        END IF;
    END $$""")
    op.drop_constraint("ck_activity_resource", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_resource", "activity_events", "resource_type IN ('identity','team','client')"
    )
    op.drop_index("uq_role_bindings_project", table_name="role_bindings")
    op.drop_constraint("ck_role_binding_scope", "role_bindings", type_="check")
    op.create_check_constraint(
        "ck_role_binding_scope",
        "role_bindings",
        "(scope_kind='global' AND team_id IS NULL AND client_id IS NULL "
        "AND role_name='platform_admin') OR "
        "(scope_kind='team' AND team_id IS NOT NULL AND client_id IS NULL "
        "AND role_name IN ('viewer','operations_manager')) OR "
        "(scope_kind='client' AND client_id IS NOT NULL AND team_id IS NULL "
        "AND role_name IN ('viewer','operations_manager'))",
    )
    op.drop_constraint("fk_role_binding_project", "role_bindings", type_="foreignkey")
    op.drop_column("role_bindings", "project_id")
    op.drop_table("project_members")
    op.drop_table("projects")
    op.drop_table("operational_areas")
