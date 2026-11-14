"""Append-only SLA observations and strict body-free native ticket provenance."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, StrictInt
from sqlalchemy.orm import Session

from altvia.models import AuditLog, OutboxEvent, TicketSlaEvent, TicketSlaState
from altvia.work_schemas import StrictModel

DOMAIN_EVENTS = frozenset({"ticket.sla_breached", "ticket.sla_corrected"})
GoalName = Literal["first_response", "resolution"]


class Observation(StrictModel):
    actor_id: None
    actor_kind: Literal["sla_worker"]
    ticket_id: UUID
    client_id: UUID
    queue_id: UUID
    cycle_number: StrictInt = Field(ge=1, le=2147483647)
    goal: GoalName
    outcome: Literal["breached", "fulfilled"]
    observed_at: AwareDatetime


def record_breach(
    db: Session,
    cycle: TicketSlaState,
    goal: GoalName,
    ticket_version: int,
    occurred_at: datetime,
    observed_at: datetime,
) -> TicketSlaEvent:
    return _record(
        db, cycle, goal, ticket_version, occurred_at, observed_at, "breached", "breached"
    )


def record_correction(
    db: Session,
    cycle: TicketSlaState,
    ticket_version: int,
    observed_at: datetime,
    delivery_id: UUID,
    outcome: Literal["fulfilled", "breached"],
) -> TicketSlaEvent:
    return _record(
        db,
        cycle,
        "first_response",
        ticket_version,
        observed_at,
        observed_at,
        "corrected",
        outcome,
        delivery_id,
    )


def _record(
    db: Session,
    cycle: TicketSlaState,
    goal: GoalName,
    ticket_version: int,
    occurred_at: datetime,
    observed_at: datetime,
    kind: Literal["breached", "corrected"],
    outcome: Literal["breached", "fulfilled"],
    delivery_id: UUID | None = None,
) -> TicketSlaEvent:
    identifier = uuid4()
    payload = Observation(
        actor_id=None,
        actor_kind="sla_worker",
        ticket_id=cycle.ticket_id,
        client_id=cycle.client_id,
        queue_id=cycle.queue_id,
        cycle_number=cycle.cycle_number,
        goal=goal,
        outcome=outcome,
        observed_at=observed_at,
    )
    db.add(
        OutboxEvent(
            event_id=identifier,
            aggregate_type="ticket",
            aggregate_id=cycle.ticket_id,
            aggregate_version=ticket_version,
            event_type="ticket.sla_" + kind,
            schema_version=1,
            payload=payload.model_dump(mode="json"),
            occurred_at=occurred_at,
            correlation_id=identifier.hex,
            next_attempt_at=observed_at,
        )
    )
    db.flush()
    row = TicketSlaEvent(
        event_id=identifier,
        ticket_id=cycle.ticket_id,
        cycle_number=cycle.cycle_number,
        goal=goal,
        kind=kind,
        outcome=outcome,
        source_delivery_id=delivery_id,
        occurred_at=occurred_at,
        observed_at=observed_at,
        observed_ticket_version=ticket_version,
    )
    db.add(row)
    db.add(
        AuditLog(
            actor_id=None,
            action="ticket.sla_" + kind,
            resource_id=cycle.ticket_id,
            occurred_at=observed_at,
            correlation_id=identifier.hex,
            details={
                "actor_kind": "sla_worker",
                "event_id": str(identifier),
                "cycle_number": str(cycle.cycle_number),
                "goal": goal,
            },
        )
    )
    db.flush()
    return row


def validate_domain_event(db: Session, event: OutboxEvent) -> Observation:
    if event.schema_version != 1 or event.event_type not in DOMAIN_EVENTS:
        raise ValueError("Invalid SLA observation envelope")
    payload = Observation.model_validate(event.payload)
    row = db.get(TicketSlaEvent, event.event_id)
    if row is None:
        raise ValueError("Missing SLA observation ledger")
    cycle = db.get(TicketSlaState, (row.ticket_id, row.cycle_number))
    if (
        cycle is None
        or cycle.policy_id is None
        or event.aggregate_type != "ticket"
        or event.aggregate_id != row.ticket_id
        or payload.ticket_id != row.ticket_id
        or payload.client_id != cycle.client_id
        or payload.queue_id != cycle.queue_id
        or payload.cycle_number != row.cycle_number
        or payload.goal != row.goal
        or payload.outcome != row.outcome
        or payload.observed_at != row.observed_at
        or event.aggregate_version != row.observed_ticket_version
        or event.occurred_at != row.occurred_at
        or event.event_type != "ticket.sla_" + row.kind
    ):
        raise ValueError("Invalid SLA observation provenance")
    return payload
