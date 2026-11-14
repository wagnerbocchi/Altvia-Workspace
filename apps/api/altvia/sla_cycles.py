"""Freeze native creation/reopen obligations under the existing ticket locks."""

from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from altvia import business_time, identity, sla_clock, sla_configuration
from altvia.models import Ticket, TicketSlaGoal, TicketSlaState, TicketStatusHistory
from altvia.ticket_state import Status


def freeze_cycle(db: Session, ticket: Ticket, history: TicketStatusHistory) -> None:
    """Caller owns identity and native parents/ticket; its native event owns audit."""
    creation = history.from_status is None and history.to_status == "new" and history.version == 1
    reopening = history.from_status in {"resolved", "closed"} and history.to_status == "open"
    if (
        history.ticket_id != ticket.id
        or history.version != ticket.version
        or history.to_status != ticket.status
        or not (creation or reopening)
    ):
        raise identity.IdentityError(503, "invalid_sla_source")
    start = history.occurred_at
    if start.utcoffset() is None or not business_time.START <= start < business_time.END:
        raise identity.IdentityError(409, "sla_timing_inconsistent")
    latest = db.scalar(
        select(TicketSlaState)
        .where(TicketSlaState.ticket_id == ticket.id)
        .order_by(TicketSlaState.cycle_number.desc())
        .limit(1)
    )
    if latest is not None:
        if latest.start_version == history.version:
            return
        if latest.start_version > history.version or latest.start_at > start:
            raise identity.IdentityError(409, "sla_timing_inconsistent")
        if latest.cycle_number >= 2147483647:
            raise identity.IdentityError(409, "version_exhausted")
    selected = sla_configuration.select_revision(
        db, ticket.client_id, ticket.queue_id, ticket.category_id, ticket.priority
    )
    revision = selected[1] if selected is not None else None
    row = TicketSlaState(
        ticket_id=ticket.id,
        cycle_number=latest.cycle_number + 1 if latest is not None else 1,
        client_id=ticket.client_id,
        queue_id=ticket.queue_id,
        start_version=history.version,
        start_at=start,
        start_status=history.to_status,
        initial_category_id=ticket.category_id,
        initial_priority=ticket.priority,
        policy_id=revision.policy_id if revision else None,
        policy_version=revision.version if revision else None,
        state="evaluating" if revision else "unconfigured",
        next_check_at=start if revision else None,
    )
    db.add(row)
    db.flush()
    if revision is None:
        return
    for name, minutes in (
        ("first_response", revision.first_response_minutes),
        ("resolution", revision.resolution_minutes),
    ):
        clock = sla_clock.initial(
            start, history.version, cast(Status, history.to_status), minutes * 60_000_000
        )
        db.add(
            TicketSlaGoal(
                ticket_id=row.ticket_id,
                cycle_number=row.cycle_number,
                goal=name,
                evaluated_through_at=clock.through,
                last_history_version=clock.history_version,
                current_status=clock.current_status,
                search_through_at=clock.search_through,
                search_remaining_us=clock.search_remaining_us,
            )
        )
    db.flush()
