"""Native same-client ticket/work links without new content authority."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000028"
down_revision = "b46087000027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_work_items",
        sa.Column("ticket_id", sa.UUID(), primary_key=True),
        sa.Column("work_item_id", sa.UUID(), primary_key=True),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("queue_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("relation_type", sa.String(7), nullable=False),
        sa.Column(
            "created_by",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "client_id", "queue_id"],
            ["tickets.id", "tickets.client_id", "tickets.queue_id"],
            name="fk_ticket_work_ticket_context",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["work_item_id", "project_id"],
            ["work_items.id", "work_items.project_id"],
            name="fk_ticket_work_work_project",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "client_id"],
            ["projects.id", "projects.client_id"],
            name="fk_ticket_work_project_client",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.CheckConstraint("relation_type='related'", name="ck_ticket_work_relation"),
    )
    op.create_index("ix_ticket_work_reverse", "ticket_work_items", ["work_item_id", "ticket_id"])


def downgrade() -> None:
    # Fence every writer of the durable evidence before checking for contraction.
    # Removing live links never erases the compatibility required by old history.
    op.execute(
        "LOCK TABLE ticket_work_items,outbox_events,audit_logs,activity_events,"
        "idempotency_records IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM ticket_work_items)
      OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type IN
        ('ticket.work_linked','ticket.work_unlinked',
         'work_item.ticket_linked','work_item.ticket_unlinked'))
      OR EXISTS(SELECT 1 FROM audit_logs WHERE action IN
        ('ticket.work_linked','ticket.work_unlinked',
         'work_item.ticket_linked','work_item.ticket_unlinked'))
      OR EXISTS(SELECT 1 FROM activity_events WHERE event_type IN
        ('ticket.work_linked','ticket.work_unlinked',
         'work_item.ticket_linked','work_item.ticket_unlinked'))
      OR EXISTS(SELECT 1 FROM idempotency_records WHERE route LIKE 'ticket-work-link:%'
        OR route LIKE 'ticket-work-unlink:%') THEN
        RAISE EXCEPTION 'Cannot contract ticket/work links/history';
      END IF; END $$""")
    # Parent unique keys belong to earlier migrations; all other ACLs stay intact.
    op.drop_table("ticket_work_items")
