"""Native ticket SLA cycles, bounded goals and immutable validated evidence."""

from alembic import op

revision = "b46087000032"
down_revision = "b46087000031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_delivery_ticket_context", "outbound_messages", ["id", "ticket_id"]
    )
    op.execute("""CREATE TABLE ticket_sla_states (
    ticket_id UUID NOT NULL,
    cycle_number INTEGER NOT NULL,
    client_id UUID NOT NULL,
    queue_id UUID NOT NULL,
    start_version INTEGER NOT NULL,
    start_at TIMESTAMP WITH TIME ZONE NOT NULL,
    start_status VARCHAR(20) NOT NULL,
    initial_category_id UUID,
    initial_priority VARCHAR(20) NOT NULL,
    policy_id UUID,
    policy_version INTEGER,
    state VARCHAR(20) NOT NULL,
    next_check_at TIMESTAMP WITH TIME ZONE,
    version BIGINT DEFAULT '1' NOT NULL,
    end_version INTEGER DEFAULT NULL,
    end_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    first_response_delivery_id UUID DEFAULT NULL,
    first_response_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    computed_through_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    safe_error VARCHAR(40) DEFAULT NULL,
    PRIMARY KEY (ticket_id, cycle_number),
    CONSTRAINT fk_sla_cycle_ticket FOREIGN KEY(ticket_id, client_id, queue_id)
    REFERENCES tickets (id, client_id, queue_id) ON DELETE RESTRICT ON UPDATE
    RESTRICT,
    CONSTRAINT fk_sla_cycle_start FOREIGN KEY(ticket_id, start_version) REFERENCES
    ticket_status_history (ticket_id, version) ON DELETE RESTRICT ON UPDATE
    RESTRICT,
    CONSTRAINT fk_sla_cycle_end FOREIGN KEY(ticket_id, end_version) REFERENCES
    ticket_status_history (ticket_id, version) ON DELETE RESTRICT ON UPDATE
    RESTRICT,
    CONSTRAINT fk_sla_cycle_policy FOREIGN KEY(policy_id, policy_version,
    client_id, queue_id) REFERENCES sla_policy_revisions (policy_id, version,
    client_id, queue_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_sla_cycle_category FOREIGN KEY(initial_category_id, queue_id)
    REFERENCES ticket_categories (id, queue_id) ON DELETE RESTRICT ON UPDATE
    RESTRICT,
    CONSTRAINT uq_sla_cycle_start UNIQUE (ticket_id, start_version),
    CONSTRAINT ck_sla_cycle_version CHECK (cycle_number BETWEEN 1 AND 2147483647
    AND start_version BETWEEN 1 AND 2147483647 AND version>0),
    CONSTRAINT ck_sla_cycle_selector CHECK (start_status IN ('new','open') AND
    initial_priority IN ('low','medium','high','critical')),
    CONSTRAINT ck_sla_cycle_start_time CHECK (start_at >= TIMESTAMPTZ
    '2000-01-01 00:00:00+00' AND start_at < TIMESTAMPTZ '2100-01-01 00:00:00+00'),

    CONSTRAINT ck_sla_cycle_snapshot CHECK ((policy_id IS NULL AND policy_version
    IS NULL AND state='unconfigured' AND next_check_at IS NULL AND
    first_response_delivery_id IS NULL) OR (policy_id IS NOT NULL AND
    policy_version IS NOT NULL AND policy_version BETWEEN 1 AND 2147483647 AND
    state IN ('evaluating','ready','unavailable'))),
    CONSTRAINT ck_sla_cycle_end CHECK ((end_version IS NULL)=(end_at IS NULL) AND
    (end_version IS NULL OR (end_version>start_version AND end_at>=start_at))),
    CONSTRAINT ck_sla_cycle_response CHECK ((first_response_delivery_id IS
    NULL)=(first_response_at IS NULL) AND (first_response_at IS NULL OR
    (first_response_at>=start_at AND (end_at IS NULL OR
    first_response_at<=end_at)))),
    CONSTRAINT ck_sla_cycle_evaluation CHECK ((state='unavailable')=(safe_error IS
    NOT NULL) AND (safe_error IS NULL OR safe_error IN
    ('timing_inconsistent','calculation_unavailable','source_invalid','processing_failed'))
    AND (state NOT IN ('ready','unavailable') OR evaluated_at IS NOT NULL) AND
    (computed_through_at IS NULL OR computed_through_at>=start_at))
)""")
    op.execute(
        """CREATE INDEX ix_sla_cycle_due ON ticket_sla_states (next_check_at, ticket_id,
    cycle_number) WHERE next_check_at IS NOT NULL"""
    )
    op.execute("""CREATE TABLE ticket_sla_goals (
    ticket_id UUID NOT NULL,
    cycle_number INTEGER NOT NULL,
    goal VARCHAR(20) NOT NULL,
    evaluated_through_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_history_version INTEGER NOT NULL,
    current_status VARCHAR(20) NOT NULL,
    search_remaining_us BIGINT NOT NULL,
    search_through_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    elapsed_us BIGINT DEFAULT '0' NOT NULL,
    due_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    outcome VARCHAR(20) DEFAULT 'evaluating' NOT NULL,
    PRIMARY KEY (ticket_id, cycle_number, goal),
    CONSTRAINT fk_sla_goal_cycle FOREIGN KEY(ticket_id, cycle_number) REFERENCES
    ticket_sla_states (ticket_id, cycle_number) ON DELETE RESTRICT ON UPDATE
    RESTRICT,
    CONSTRAINT fk_sla_goal_history FOREIGN KEY(ticket_id, last_history_version)
    REFERENCES ticket_status_history (ticket_id, version) ON DELETE RESTRICT ON
    UPDATE RESTRICT,
    CONSTRAINT ck_sla_goal_kind CHECK (goal IN ('first_response','resolution')),
    CONSTRAINT ck_sla_goal_progress CHECK (last_history_version BETWEEN 1 AND
    2147483647 AND current_status IN
    ('new','open','pending_customer','pending_third_party','resolved','closed')
    AND elapsed_us BETWEEN 0 AND 3155760000000000 AND search_remaining_us BETWEEN
    0 AND 31536000000000),
    CONSTRAINT ck_sla_goal_deadline CHECK (evaluated_through_at>=TIMESTAMPTZ
    '2000-01-01 00:00:00+00' AND evaluated_through_at<=TIMESTAMPTZ
    '2100-01-01 00:00:00+00' AND (due_at IS NULL OR due_at BETWEEN TIMESTAMPTZ
    '2000-01-01 00:00:00+00' AND TIMESTAMPTZ '2100-01-01 00:00:00+00') AND
    (search_through_at IS NULL OR search_through_at BETWEEN TIMESTAMPTZ
    '2000-01-01 00:00:00+00' AND TIMESTAMPTZ '2100-01-01 00:00:00+00') AND
    ((due_at IS NOT NULL AND search_remaining_us=0) OR (due_at IS NULL AND
    search_remaining_us>0))),
    CONSTRAINT ck_sla_goal_outcome CHECK (outcome IN
    ('evaluating','running','paused','approaching','fulfilled','unfulfilled','breached'))
)""")
    op.execute("""CREATE TABLE ticket_sla_acceptances (
    delivery_id UUID NOT NULL,
    ticket_id UUID NOT NULL,
    cycle_number INTEGER NOT NULL,
    source_event_id UUID NOT NULL,
    message_version INTEGER NOT NULL,
    accepted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    delivery_version INTEGER NOT NULL,
    observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (delivery_id),
    CONSTRAINT fk_sla_acceptance_cycle FOREIGN KEY(ticket_id, cycle_number)
    REFERENCES ticket_sla_states (ticket_id, cycle_number) ON DELETE RESTRICT ON
    UPDATE RESTRICT,
    CONSTRAINT fk_sla_acceptance_delivery FOREIGN KEY(delivery_id, ticket_id)
    REFERENCES outbound_messages (id, ticket_id) ON DELETE RESTRICT ON UPDATE
    RESTRICT,
    CONSTRAINT fk_sla_acceptance_message FOREIGN KEY(ticket_id, message_version)
    REFERENCES ticket_messages (ticket_id, ticket_version) ON DELETE RESTRICT ON
    UPDATE RESTRICT,
    CONSTRAINT uq_sla_acceptance_cycle UNIQUE (delivery_id, ticket_id,
    cycle_number),
    CONSTRAINT uq_sla_acceptance_event UNIQUE (source_event_id),
    CONSTRAINT ck_sla_acceptance_evidence CHECK (delivery_version BETWEEN 1 AND
    2147483647 AND accepted_at<=observed_at),
    FOREIGN KEY(source_event_id) REFERENCES outbox_events (event_id) ON DELETE
    RESTRICT
)""")
    op.execute(
        """CREATE INDEX ix_sla_acceptance_first ON ticket_sla_acceptances (ticket_id,
    cycle_number, accepted_at, delivery_id)"""
    )
    op.execute("""CREATE TABLE ticket_sla_events (
    event_id UUID NOT NULL,
    ticket_id UUID NOT NULL,
    cycle_number INTEGER NOT NULL,
    goal VARCHAR(20) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    outcome VARCHAR(20) NOT NULL,
    source_delivery_id UUID,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    observed_ticket_version INTEGER NOT NULL,
    PRIMARY KEY (event_id),
    CONSTRAINT fk_sla_event_goal FOREIGN KEY(ticket_id, cycle_number, goal)
    REFERENCES ticket_sla_goals (ticket_id, cycle_number, goal) ON DELETE RESTRICT
    ON UPDATE RESTRICT,
    CONSTRAINT fk_sla_event_acceptance FOREIGN KEY(source_delivery_id, ticket_id,
    cycle_number) REFERENCES ticket_sla_acceptances (delivery_id, ticket_id,
    cycle_number) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_sla_event_kind CHECK ((kind='breached' AND source_delivery_id IS
    NULL AND outcome='breached') OR (kind='corrected' AND goal='first_response'
    AND source_delivery_id IS NOT NULL AND outcome IN ('fulfilled','breached'))),
    CONSTRAINT ck_sla_event_observation CHECK (observed_ticket_version BETWEEN 1
    AND 2147483647 AND occurred_at<=observed_at),
    FOREIGN KEY(event_id) REFERENCES outbox_events (event_id) ON DELETE RESTRICT
)""")
    op.execute(
        """CREATE UNIQUE INDEX uq_sla_breach ON ticket_sla_events (ticket_id, cycle_number,
    goal) WHERE kind='breached'"""
    )
    op.execute(
        """CREATE UNIQUE INDEX uq_sla_correction ON ticket_sla_events (ticket_id,
    cycle_number, source_delivery_id) WHERE kind='corrected'"""
    )
    op.execute(
        """ALTER TABLE ticket_sla_states ADD CONSTRAINT fk_sla_cycle_response FOREIGN
    KEY(first_response_delivery_id, ticket_id, cycle_number) REFERENCES
    ticket_sla_acceptances (delivery_id, ticket_id, cycle_number) ON DELETE
    RESTRICT ON UPDATE RESTRICT"""
    )
    op.execute(
        """CREATE INDEX ix_sla_acceptance_sources ON outbox_events (occurred_at, event_id)
    WHERE event_type='mail.delivery_changed' AND payload->>'state'='accepted'"""
    )
    op.drop_constraint("ck_activity_actor", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_actor",
        "activity_events",
        """actor_kind IN ('user','management_command') OR (actor_kind='automation' AND
    actor_id IS NULL AND event_type IN
    ('work_item.created','ticket.work_linked','work_item.ticket_linked')) OR
    (actor_kind='sla_worker' AND actor_id IS NULL AND resource_type='ticket' AND
    event_type IN ('ticket.sla_breached','ticket.sla_corrected'))""",
    )
    op.execute("""CREATE VIEW public.sla_public_acceptance_sources WITH (security_barrier=true) AS
    SELECT d.id AS delivery_id,d.ticket_id,d.message_id,m.ticket_version AS
    message_version,
      d.version AS delivery_version,d.accepted_at,d.created_at AS
    delivery_created_at,
      m.created_at AS message_created_at
    FROM public.outbound_messages d JOIN public.ticket_messages m
      ON m.id=d.message_id AND m.ticket_id=d.ticket_id
    WHERE d.state='accepted' AND d.accepted_at IS NOT NULL
      AND m.visibility='public' AND m.direction='outbound'""")
    op.execute("REVOKE ALL ON public.sla_public_acceptance_sources FROM PUBLIC")


def downgrade() -> None:
    op.execute("""LOCK TABLE ticket_sla_states,ticket_sla_goals,ticket_sla_acceptances,
      ticket_sla_events,outbox_events,audit_logs,activity_events,processed_events
      IN ACCESS EXCLUSIVE MODE""")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM ticket_sla_states) OR EXISTS(SELECT 1 FROM
    ticket_sla_goals)
        OR EXISTS(SELECT 1 FROM ticket_sla_acceptances) OR EXISTS(SELECT 1 FROM
    ticket_sla_events)
        OR EXISTS(SELECT 1 FROM processed_events WHERE
    consumer='sla_acceptance_v1')
        OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type IN
          ('ticket.sla_breached','ticket.sla_corrected'))
        OR EXISTS(SELECT 1 FROM audit_logs WHERE action IN
          ('ticket.sla_breached','ticket.sla_corrected','sla.acceptance_rejected'))
        OR EXISTS(SELECT 1 FROM activity_events WHERE event_type IN
          ('ticket.sla_breached','ticket.sla_corrected'))
      THEN RAISE EXCEPTION 'Cannot contract ticket SLA snapshots/history'; END IF;
    END $$""")
    op.execute("DROP VIEW public.sla_public_acceptance_sources")
    op.drop_constraint("fk_sla_cycle_response", "ticket_sla_states", type_="foreignkey")
    op.drop_table("ticket_sla_events")
    op.drop_table("ticket_sla_acceptances")
    op.drop_table("ticket_sla_goals")
    op.drop_table("ticket_sla_states")
    op.drop_index("ix_sla_acceptance_sources", table_name="outbox_events")
    op.drop_constraint("uq_delivery_ticket_context", "outbound_messages", type_="unique")
    op.drop_constraint("ck_activity_actor", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_actor",
        "activity_events",
        "actor_kind IN ('user','management_command') OR "
        "(actor_kind='automation' AND actor_id IS NULL AND event_type IN "
        "('work_item.created','ticket.work_linked','work_item.ticket_linked'))",
    )
