"""Expose only immutable assignment metadata needed by protected recovery."""

from alembic import op

revision = "b46087000030"
down_revision = "b46087000029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE VIEW public.automation_assignment_sources
      WITH (security_barrier=true) AS
      SELECT execution.id AS execution_id,
        event.aggregate_type,event.aggregate_id,event.aggregate_version,
        event.schema_version,event.event_type,
        (SELECT coalesce(jsonb_object_agg(field.key,field.value),'{}'::jsonb)
         FROM jsonb_each(CASE WHEN jsonb_typeof(event.payload)='object'
           THEN event.payload ELSE '{}'::jsonb END) AS field
         WHERE field.key=ANY(ARRAY['actor_id','actor_kind','ticket_id','client_id',
           'queue_id','changed_fields','old_assignee_id','new_assignee_id'])) AS payload,
        CASE WHEN jsonb_typeof(event.payload)='object' THEN
          event.payload-ARRAY['actor_id','actor_kind','ticket_id','client_id',
            'queue_id','changed_fields','old_assignee_id','new_assignee_id']<>'{}'::jsonb
          ELSE true END AS unexpected_fields
      FROM public.automation_executions AS execution
      JOIN public.outbox_events AS event ON event.event_id=execution.source_event_id
      WHERE event.event_type='ticket.assigned' AND event.aggregate_type='ticket'
        AND event.schema_version=1""")
    op.execute("REVOKE ALL ON public.automation_assignment_sources FROM PUBLIC")


def downgrade() -> None:
    # Derived metadata only; source events and all durable identities survive.
    op.execute("DROP VIEW public.automation_assignment_sources")
