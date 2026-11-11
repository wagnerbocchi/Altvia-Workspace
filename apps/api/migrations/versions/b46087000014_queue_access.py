"""Expand explicit queue grants without deriving customer or team authority."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000014"
down_revision = "b46087000013"
branch_labels = None
depends_on = None

OLD_SCOPE = (
    "(scope_kind='global' AND team_id IS NULL AND client_id IS NULL "
    "AND project_id IS NULL AND role_name='platform_admin') OR "
    "(scope_kind='team' AND team_id IS NOT NULL AND client_id IS NULL "
    "AND project_id IS NULL AND role_name IN ('viewer','operations_manager')) OR "
    "(scope_kind='client' AND client_id IS NOT NULL AND team_id IS NULL "
    "AND project_id IS NULL AND role_name IN ('viewer','operations_manager')) OR "
    "(scope_kind='project' AND project_id IS NOT NULL AND team_id IS NULL "
    "AND client_id IS NULL AND role_name IN ('viewer','agent','project_manager'))"
)


def upgrade() -> None:
    op.add_column("role_bindings", sa.Column("queue_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_role_binding_queue",
        "role_bindings",
        "ticket_queues",
        ["queue_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("ck_role_binding_scope", "role_bindings", type_="check")
    op.create_check_constraint(
        "ck_role_binding_scope",
        "role_bindings",
        f"(({OLD_SCOPE}) AND queue_id IS NULL) OR "
        "(scope_kind='queue' AND queue_id IS NOT NULL AND team_id IS NULL "
        "AND client_id IS NULL AND project_id IS NULL "
        "AND role_name IN ('viewer','agent','operations_manager'))",
    )
    op.create_index(
        "uq_role_bindings_queue",
        "role_bindings",
        ["user_id", "queue_id"],
        unique=True,
        postgresql_where=sa.text("scope_kind='queue'"),
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE role_bindings, outbox_events, audit_logs, activity_events "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM role_bindings WHERE queue_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type='ticket_queue.access_changed')
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action='ticket_queue.access_changed')
        OR EXISTS(SELECT 1 FROM activity_events WHERE event_type='ticket_queue.access_changed')
        THEN RAISE EXCEPTION 'Cannot downgrade while durable queue access data exists';
        END IF;
    END $$""")
    op.drop_index("uq_role_bindings_queue", table_name="role_bindings")
    op.drop_constraint("ck_role_binding_scope", "role_bindings", type_="check")
    op.drop_constraint("fk_role_binding_queue", "role_bindings", type_="foreignkey")
    op.drop_column("role_bindings", "queue_id")
    op.create_check_constraint("ck_role_binding_scope", "role_bindings", OLD_SCOPE)
