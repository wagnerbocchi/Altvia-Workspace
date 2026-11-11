"""Persist manual tickets, scoped references, immutable states and queue policy."""

import sqlalchemy as sa
from alembic import op

revision = "b46087000015"
down_revision = "b46087000014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("allow_manual_close", "allow_reopen"):
        op.add_column(
            "ticket_queues",
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.create_unique_constraint(
        "uq_contact_identity_client", "client_contacts", ["id", "client_id"]
    )
    op.create_unique_constraint(
        "uq_category_identity_queue", "ticket_categories", ["id", "queue_id"]
    )
    op.execute(r"""
CREATE TABLE tickets (
    id UUID NOT NULL,
    number BIGINT GENERATED ALWAYS AS IDENTITY,
    client_id UUID NOT NULL,
    requester_id UUID NOT NULL,
    queue_id UUID NOT NULL,
    category_id UUID,
    assignee_id UUID,
    subject VARCHAR(300) NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    status VARCHAR(20) DEFAULT 'new' NOT NULL,
    priority VARCHAR(20) NOT NULL,
    source VARCHAR(20) DEFAULT 'manual' NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE,
    closed_at TIMESTAMP WITH TIME ZONE,
    version INTEGER DEFAULT '1' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_ticket_number UNIQUE (number),
    CONSTRAINT fk_ticket_requester_client FOREIGN KEY(requester_id, client_id)
        REFERENCES client_contacts (id, client_id) ON DELETE RESTRICT,
    CONSTRAINT fk_ticket_category_queue FOREIGN KEY(category_id, queue_id)
        REFERENCES ticket_categories (id, queue_id) ON DELETE RESTRICT,
    CONSTRAINT ck_ticket_number CHECK (number > 0),
    CONSTRAINT ck_ticket_subject CHECK (char_length(btrim(subject,
        U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680'
        || U&'\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029'
        || U&'\202F\205F\3000')) > 0),
    CONSTRAINT ck_ticket_subject_line CHECK (
        position(chr(10) in subject)=0 AND position(chr(13) in subject)=0),
    CONSTRAINT ck_ticket_description CHECK (char_length(description) <= 20000),
    CONSTRAINT ck_ticket_version CHECK (version > 0),
    CONSTRAINT ck_ticket_priority CHECK (priority IN ('low','medium','high','critical')),
    CONSTRAINT ck_ticket_source CHECK (source='manual'),
    CONSTRAINT ck_ticket_status CHECK (status IN (
        'new','open','pending_customer','pending_third_party','resolved','closed')),
    CONSTRAINT ck_ticket_state_times CHECK (
        (status IN ('new','open','pending_customer','pending_third_party')
            AND resolved_at IS NULL AND closed_at IS NULL)
        OR (status='resolved' AND resolved_at IS NOT NULL AND closed_at IS NULL)
        OR (status='closed' AND resolved_at IS NOT NULL AND closed_at IS NOT NULL)),
    FOREIGN KEY(client_id) REFERENCES clients (id) ON DELETE RESTRICT,
    FOREIGN KEY(queue_id) REFERENCES ticket_queues (id) ON DELETE RESTRICT,
    FOREIGN KEY(assignee_id) REFERENCES users (id) ON DELETE RESTRICT
)
""")
    op.execute(
        "CREATE INDEX ix_ticket_search ON tickets USING gin "
        "(to_tsvector('portuguese'::regconfig, "
        "coalesce(subject,'') || ' ' || coalesce(description,'')))"
    )
    op.execute("""CREATE INDEX ix_tickets_assignee ON tickets (assignee_id, queue_id, status)""")
    op.execute(
        """CREATE INDEX ix_tickets_client_page ON tickets (client_id, created_at DESC, id DESC)"""
    )
    op.execute(
        """CREATE INDEX ix_tickets_queue_page ON tickets (queue_id, created_at DESC, id DESC)"""
    )
    op.execute(r"""
CREATE TABLE ticket_status_history (
    id UUID NOT NULL,
    ticket_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    from_status VARCHAR(20),
    to_status VARCHAR(20) NOT NULL,
    reason TEXT,
    version INTEGER NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_ticket_state_version UNIQUE (ticket_id, version),
    CONSTRAINT ck_ticket_state_version CHECK (version > 0),
    CONSTRAINT ck_ticket_state_reason CHECK (reason IS NULL OR char_length(reason) <= 2000),
    CONSTRAINT ck_ticket_state_graph CHECK (
        (from_status IS NULL AND to_status='new' AND version=1)
        OR (from_status IS NOT NULL AND version > 1 AND (
            (from_status='new' AND to_status='open')
            OR (from_status='open' AND to_status IN (
                'pending_customer','pending_third_party','resolved'))
            OR (from_status IN ('pending_customer','pending_third_party')
                AND to_status IN ('open','resolved'))
            OR (from_status='resolved' AND to_status IN ('closed','open'))
            OR (from_status='closed' AND to_status='open')))),
    FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE RESTRICT,
    FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE RESTRICT
)
""")
    op.drop_constraint("ck_activity_resource", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_resource",
        "activity_events",
        "resource_type IN ('identity','team','client','project',"
        "'operational_area','work_item','ticket_queue','ticket')",
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE tickets, ticket_status_history, ticket_queues, outbox_events, "
        "audit_logs, activity_events IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM tickets)
        OR EXISTS(SELECT 1 FROM ticket_status_history)
        OR EXISTS(SELECT 1 FROM outbox_events WHERE aggregate_type='ticket')
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action LIKE 'ticket.%')
        OR EXISTS(SELECT 1 FROM activity_events WHERE resource_type='ticket')
        OR EXISTS(SELECT 1 FROM ticket_queues WHERE allow_manual_close OR allow_reopen)
        OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type='ticket_queue.updated' AND
            (payload->>'changed_fields' LIKE '%allow_manual_close%'
            OR payload->>'changed_fields' LIKE '%allow_reopen%'))
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action='ticket_queue.updated' AND
            (details->>'changed_fields' LIKE '%allow_manual_close%'
            OR details->>'changed_fields' LIKE '%allow_reopen%'))
        OR EXISTS(SELECT 1 FROM activity_events WHERE event_type='ticket_queue.updated' AND
            (details->>'changed_fields' LIKE '%allow_manual_close%'
            OR details->>'changed_fields' LIKE '%allow_reopen%'))
        THEN RAISE EXCEPTION 'Cannot downgrade while durable ticket or workflow data exists';
        END IF;
    END $$""")
    op.drop_table("ticket_status_history")
    op.drop_table("tickets")
    op.drop_constraint("uq_contact_identity_client", "client_contacts", type_="unique")
    op.drop_constraint("uq_category_identity_queue", "ticket_categories", type_="unique")
    op.drop_column("ticket_queues", "allow_manual_close")
    op.drop_column("ticket_queues", "allow_reopen")
    op.drop_constraint("ck_activity_resource", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_resource",
        "activity_events",
        "resource_type IN ('identity','team','client','project',"
        "'operational_area','work_item','ticket_queue')",
    )
