"""Index-only task discovery; rollback never deletes operational data."""

from alembic import op

revision = "b46087000009"
down_revision = "b46087000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE INDEX ix_work_search ON work_items USING gin
        (to_tsvector('portuguese'::regconfig,
         coalesce(title,'') || ' ' || coalesce(description,'')))""")
    op.create_index("ix_work_project_status_id", "work_items", ["project_id", "status", "id"])
    op.create_index("ix_work_owner_page", "work_items", ["owner_id", "id"])
    op.create_index("ix_work_assignee_page", "work_item_assignees", ["user_id", "work_item_id"])
    op.drop_index("ix_work_items_owner_id", table_name="work_items")
    op.drop_index("ix_work_item_assignees_user_id", table_name="work_item_assignees")


def downgrade() -> None:
    op.create_index("ix_work_items_owner_id", "work_items", ["owner_id"])
    op.create_index("ix_work_item_assignees_user_id", "work_item_assignees", ["user_id"])
    op.drop_index("ix_work_assignee_page", table_name="work_item_assignees")
    op.drop_index("ix_work_owner_page", table_name="work_items")
    op.drop_index("ix_work_project_status_id", table_name="work_items")
    op.drop_index("ix_work_search", table_name="work_items")
