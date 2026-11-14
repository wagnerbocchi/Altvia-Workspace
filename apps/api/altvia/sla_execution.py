"""Bounded transactional SLA evaluation; Redis carries no timer authority."""

from datetime import UTC, date, datetime, timedelta
from threading import Event
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from altvia import business_time, mail_delivery, sla_clock, sla_events
from altvia.management import lock_identity_writes
from altvia.models import (
    AuditLog,
    BusinessCalendarRevision,
    Client,
    OutboxEvent,
    ProcessedEvent,
    SlaPolicyRevision,
    Team,
    Ticket,
    TicketQueue,
    TicketSlaAcceptance,
    TicketSlaEvent,
    TicketSlaGoal,
    TicketSlaState,
    TicketStatusHistory,
)
from altvia.ticket_state import Status

HISTORY_PAGE = 498
MAX_VERSION = 9223372036854775807
ACCEPTANCE_CONSUMER = "sla_acceptance_v1"


def _capture(db: Session, event: OutboxEvent, now: datetime) -> None:
    mail_delivery.validate_delivery_event(event)
    source = (
        db.execute(
            text("SELECT * FROM sla_public_acceptance_sources WHERE delivery_id=:id"),
            {"id": event.aggregate_id},
        )
        .mappings()
        .one_or_none()
    )
    if source is None:
        raise ValueError("source_invalid")
    accepted = source["accepted_at"]
    if (
        event.payload["state"] != "accepted"
        or event.payload["error_code"] is not None
        or event.aggregate_version != source["delivery_version"]
        or datetime.fromisoformat(cast(str, event.payload["accepted_at"])) != accepted
        or not source["message_created_at"] <= source["delivery_created_at"] <= accepted
        or not accepted <= event.occurred_at <= now
    ):
        raise ValueError("source_invalid")
    hint = db.scalar(
        select(TicketSlaState)
        .where(
            TicketSlaState.ticket_id == source["ticket_id"],
            TicketSlaState.start_version <= source["message_version"],
        )
        .order_by(TicketSlaState.start_version.desc())
        .limit(1)
    )
    if hint is None or hint.policy_id is None:
        return
    owned = _locked(db, hint.ticket_id, hint.cycle_number)
    if owned is None:
        return
    cycle, _ = owned
    end = _end(db, cycle, now)
    if accepted < cycle.start_at or (
        end is not None and (source["message_version"] >= end[0] or accepted > end[1])
    ):
        return
    if db.get(TicketSlaAcceptance, source["delivery_id"]) is not None:
        return
    db.add(
        TicketSlaAcceptance(
            delivery_id=source["delivery_id"],
            ticket_id=cycle.ticket_id,
            cycle_number=cycle.cycle_number,
            source_event_id=event.event_id,
            message_version=source["message_version"],
            accepted_at=accepted,
            delivery_version=source["delivery_version"],
            observed_at=now,
        )
    )
    if cycle.version < MAX_VERSION:
        cycle.next_check_at = now
        # Old derived values are retained, but cannot be presented as current
        # while newly captured evidence awaits evaluation.
        cycle.state, cycle.safe_error = "evaluating", None
        cycle.version += 1
    db.flush()


def capture_acceptances(engine: Engine, limit: int = 20, *, stop: Event | None = None) -> int:
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("invalid_sla_limit")
    with Session(engine) as db:
        identifiers = list(
            db.scalars(
                select(OutboxEvent.event_id)
                .where(
                    OutboxEvent.event_type == "mail.delivery_changed",
                    OutboxEvent.payload["state"].astext == "accepted",
                    ~select(ProcessedEvent.event_id)
                    .where(
                        ProcessedEvent.consumer == ACCEPTANCE_CONSUMER,
                        ProcessedEvent.event_id == OutboxEvent.event_id,
                    )
                    .exists(),
                )
                .order_by(OutboxEvent.occurred_at, OutboxEvent.event_id)
                .limit(limit)
            )
        )
    count = 0
    for identifier in identifiers:
        if stop is not None and stop.is_set():
            break
        with Session(engine) as db, db.begin():
            # Source envelopes are immutable; do not lock an outbox row before
            # the native identity/parent protocol used by all ticket writers.
            lock_identity_writes(db)
            if db.get(ProcessedEvent, (ACCEPTANCE_CONSUMER, identifier)) is not None:
                continue
            event = db.get(OutboxEvent, identifier)
            if event is None:
                continue
            now = _clock(db)
            try:
                with db.begin_nested():
                    _capture(db, event, now)
            except (ValueError, TypeError, KeyError):
                db.add(
                    AuditLog(
                        actor_id=None,
                        action="sla.acceptance_rejected",
                        resource_id=identifier,
                        occurred_at=now,
                        correlation_id=identifier.hex,
                        details={"error_code": "source_invalid"},
                    )
                )
            # SQL failures roll back evidence and receipt, allowing recovery.
            db.add(
                ProcessedEvent(consumer=ACCEPTANCE_CONSUMER, event_id=identifier, processed_at=now)
            )
            count += 1
    return count


def _clock(db: Session) -> datetime:
    now = db.scalar(select(func.clock_timestamp()))
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("timing_inconsistent")
    return now.astimezone(UTC)


def _locked(db: Session, ticket_id: UUID, number: int) -> tuple[TicketSlaState, int] | None:
    lock_identity_writes(db)
    hint = db.get(TicketSlaState, (ticket_id, number))
    if hint is None:
        return None
    # Captured obligations continue after archive/authorizer departure. These
    # locks serialize metadata and native facts; no stored actor grants access.
    db.execute(select(Client.id).where(Client.id == hint.client_id).with_for_update()).one()
    team_id = db.scalar(select(TicketQueue.team_id).where(TicketQueue.id == hint.queue_id))
    db.execute(select(Team.id).where(Team.id == team_id).with_for_update()).one()
    db.execute(
        select(TicketQueue.id).where(TicketQueue.id == hint.queue_id).with_for_update()
    ).one()
    version = db.scalar(select(Ticket.version).where(Ticket.id == ticket_id).with_for_update())
    row = db.scalar(
        select(TicketSlaState)
        .where(
            TicketSlaState.ticket_id == ticket_id,
            TicketSlaState.cycle_number == number,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or version is None:
        return None
    return row, version


def _calendar(db: Session, revision: SlaPolicyRevision) -> business_time.CalendarSnapshot:
    row = db.get(BusinessCalendarRevision, (revision.calendar_id, revision.calendar_version))
    if row is None:
        raise ValueError("calculation_unavailable")
    try:
        return business_time.build_calendar(
            business_time.FrozenZone(row.timezone, row.tzif, row.tzif_sha256),
            [
                business_time.Window(
                    cast(int, w["weekday"]),
                    cast(int, w["start_minute"]),
                    cast(int, w["end_minute"]),
                )
                for w in row.windows
            ],
            [date.fromisoformat(cast(str, holiday["date"])) for holiday in row.holidays],
        )
    except (ValueError, TypeError, KeyError):
        raise ValueError("calculation_unavailable") from None


def _end(db: Session, cycle: TicketSlaState, now: datetime) -> tuple[int, datetime] | None:
    end = db.execute(
        select(TicketStatusHistory.version, TicketStatusHistory.occurred_at)
        .where(
            TicketStatusHistory.ticket_id == cycle.ticket_id,
            TicketStatusHistory.version > cycle.start_version,
            TicketStatusHistory.to_status == "resolved",
        )
        .order_by(TicketStatusHistory.version)
        .limit(1)
    ).one_or_none()
    if end is not None and not cycle.start_at <= end[1] <= now:
        raise ValueError("timing_inconsistent")
    return (end[0], end[1]) if end is not None else None


def _evaluate(db: Session, cycle: TicketSlaState, ticket_version: int, now: datetime) -> None:
    if cycle.policy_id is None or cycle.policy_version is None or cycle.version >= MAX_VERSION:
        raise ValueError("calculation_unavailable")
    revision = db.get(SlaPolicyRevision, (cycle.policy_id, cycle.policy_version))
    if revision is None or (revision.client_id, revision.queue_id) != (
        cycle.client_id,
        cycle.queue_id,
    ):
        raise ValueError("calculation_unavailable")
    calendar = _calendar(db, revision)
    goals = {
        g.goal: g
        for g in db.scalars(
            select(TicketSlaGoal).where(
                TicketSlaGoal.ticket_id == cycle.ticket_id,
                TicketSlaGoal.cycle_number == cycle.cycle_number,
            )
        )
    }
    if set(goals) != {"first_response", "resolution"}:
        raise ValueError("calculation_unavailable")
    end = _end(db, cycle, now)
    stop = end[1] if end else now
    if not cycle.start_at <= stop <= now:
        raise ValueError("timing_inconsistent")
    facts = {
        r[0]: (r[1], r[2])
        for r in db.execute(
            select(
                TicketStatusHistory.version,
                TicketStatusHistory.to_status,
                TicketStatusHistory.occurred_at,
            ).where(
                TicketStatusHistory.ticket_id == cycle.ticket_id,
                TicketStatusHistory.version.in_(
                    {cycle.start_version, *(g.last_history_version for g in goals.values())}
                ),
            )
        )
    }
    if facts.get(cycle.start_version) != (cycle.start_status, cycle.start_at):
        raise ValueError("timing_inconsistent")
    query = select(TicketSlaAcceptance).where(
        TicketSlaAcceptance.ticket_id == cycle.ticket_id,
        TicketSlaAcceptance.cycle_number == cycle.cycle_number,
        TicketSlaAcceptance.message_version >= cycle.start_version,
        TicketSlaAcceptance.accepted_at >= cycle.start_at,
    )
    if end is not None:
        query = query.where(
            TicketSlaAcceptance.message_version < end[0], TicketSlaAcceptance.accepted_at <= end[1]
        )
    candidate = db.scalar(
        query.order_by(TicketSlaAcceptance.accepted_at, TicketSlaAcceptance.delivery_id).limit(1)
    )
    if candidate is not None and candidate.accepted_at > now:
        raise ValueError("timing_inconsistent")
    response_changed = cycle.first_response_delivery_id != (
        candidate.delivery_id if candidate else None
    ) or cycle.first_response_at != (candidate.accepted_at if candidate else None)
    results: dict[str, sla_clock.ClockStep] = {}
    cutoffs: dict[str, datetime] = {}
    for name, minutes in (
        ("first_response", revision.first_response_minutes),
        ("resolution", revision.resolution_minutes),
    ):
        goal = goals[name]
        target = minutes * 60_000_000
        if name == "first_response" and response_changed:
            progress = sla_clock.initial(
                cycle.start_at, cycle.start_version, cast(Status, cycle.start_status), target
            )
        else:
            last = facts.get(goal.last_history_version)
            if (
                last is None
                or last[0] != goal.current_status
                or last[1] > goal.evaluated_through_at
                or goal.last_history_version < cycle.start_version
                or (goal.elapsed_us >= target and goal.due_at is None)
            ):
                raise ValueError("timing_inconsistent")
            progress = sla_clock.ClockProgress(
                goal.evaluated_through_at,
                goal.last_history_version,
                cast(Status, goal.current_status),
                target,
                goal.elapsed_us,
                goal.due_at,
                goal.search_through_at,
                goal.search_remaining_us,
            )
        fulfilled = candidate is not None if name == "first_response" else end is not None
        cutoff = candidate.accepted_at if name == "first_response" and candidate else stop
        terminal = fulfilled or end is not None
        history = select(
            TicketStatusHistory.version,
            TicketStatusHistory.occurred_at,
            TicketStatusHistory.from_status,
            TicketStatusHistory.to_status,
        ).where(
            TicketStatusHistory.ticket_id == cycle.ticket_id,
            TicketStatusHistory.version > progress.history_version,
        )
        if end is not None:
            history = history.where(TicketStatusHistory.version <= end[0])
        rows = list(db.execute(history.order_by(TicketStatusHistory.version).limit(HISTORY_PAGE)))
        result = sla_clock.step(
            calendar,
            progress,
            [
                sla_clock.HistoryPoint(
                    r[0],
                    r[1],
                    cast(Status, r[2]),
                    cast(Status, r[3]),
                )
                for r in rows
            ],
            cutoff,
            pauses=frozenset(revision.pause_states),
            approach_us=revision.approach_minutes * 60_000_000,
            history_complete=len(rows) < HISTORY_PAGE,
            terminal=terminal,
            fulfilled=fulfilled,
        )
        results[name], cutoffs[name] = result, cutoff
    # All source/clock validation precedes derived writes. The enclosing savepoint
    # also rolls back both goals and every observation if any SQL write fails.
    cycle.end_version, cycle.end_at = end if end else (None, None)
    cycle.first_response_delivery_id = candidate.delivery_id if candidate else None
    cycle.first_response_at = candidate.accepted_at if candidate else None
    cycle.version += 1
    cycle.evaluated_at = now
    complete = all(r.complete for r in results.values())
    cycle.state, cycle.safe_error = ("ready" if complete else "evaluating"), None
    cycle.computed_through_at = min(
        stop if r.progress.through == cutoffs[name] else r.progress.through
        for name, r in results.items()
    )
    cycle.next_check_at = (
        None if complete and end else now + timedelta(seconds=30 if complete else 1)
    )
    previous_response_outcome = goals["first_response"].outcome
    for name, result in results.items():
        goal, progress = goals[name], result.progress
        goal.evaluated_through_at, goal.last_history_version = (
            progress.through,
            progress.history_version,
        )
        goal.current_status, goal.elapsed_us = progress.current_status, progress.elapsed_us
        goal.due_at, goal.search_through_at = progress.due_at, progress.search_through
        goal.search_remaining_us = progress.search_remaining_us
        # Preserve the last completed outcome through bounded recomputation.
        # The cycle's evaluating state makes its partial progress explicit.
        if result.complete:
            goal.outcome = result.state
    observed = {
        e.goal
        for e in db.scalars(
            select(TicketSlaEvent).where(
                TicketSlaEvent.ticket_id == cycle.ticket_id,
                TicketSlaEvent.cycle_number == cycle.cycle_number,
                TicketSlaEvent.kind == "breached",
            )
        )
    }
    for name, result in results.items():
        if result.progress.elapsed_us > result.progress.target_us and name not in observed:
            if result.progress.due_at is None:
                raise ValueError("calculation_unavailable")
            sla_events.record_breach(
                db,
                cycle,
                cast(sla_events.GoalName, name),
                ticket_version,
                result.progress.due_at,
                now,
            )
    response = results["first_response"]
    if (
        candidate is not None
        and response.complete
        and response.state in {"fulfilled", "breached"}
        and ("first_response" in observed or previous_response_outcome == "unfulfilled")
        and not db.scalar(
            select(TicketSlaEvent.event_id)
            .where(
                TicketSlaEvent.ticket_id == cycle.ticket_id,
                TicketSlaEvent.cycle_number == cycle.cycle_number,
                TicketSlaEvent.kind == "corrected",
                TicketSlaEvent.source_delivery_id == candidate.delivery_id,
            )
            .exists()
            .select()
        )
    ):
        sla_events.record_correction(
            db,
            cycle,
            ticket_version,
            now,
            candidate.delivery_id,
            cast(Literal["fulfilled", "breached"], response.state),
        )
    db.flush()


def evaluate_due(engine: Engine, limit: int = 20, *, stop: Event | None = None) -> int:
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("invalid_sla_limit")
    with Session(engine) as db:
        due = list(
            db.execute(
                select(TicketSlaState.ticket_id, TicketSlaState.cycle_number)
                .where(
                    TicketSlaState.next_check_at <= func.clock_timestamp(),
                )
                .order_by(
                    TicketSlaState.next_check_at,
                    TicketSlaState.ticket_id,
                    TicketSlaState.cycle_number,
                )
                .limit(limit)
            )
        )
    count = 0
    for identifier, number in due:
        if stop is not None and stop.is_set():
            break
        with Session(engine) as db, db.begin():
            owned = _locked(db, identifier, number)
            if owned is None:
                continue
            cycle, ticket_version = owned
            now = _clock(db)
            if cycle.next_check_at is None or cycle.next_check_at > now:
                continue
            try:
                with db.begin_nested():
                    _evaluate(db, cycle, ticket_version, now)
            except (ValueError, TypeError, KeyError, SQLAlchemyError) as error:
                # No exception text or payload becomes persisted/user-facing data.
                code = error.args[0] if isinstance(error, ValueError) and error.args else None
                cycle.state, cycle.safe_error = (
                    "unavailable",
                    (
                        code
                        if code in {"timing_inconsistent", "calculation_unavailable"}
                        else "processing_failed"
                    ),
                )
                cycle.evaluated_at = now
                cycle.next_check_at = (
                    now + timedelta(seconds=60) if cycle.version < MAX_VERSION else None
                )
                if cycle.version < MAX_VERSION:
                    cycle.version += 1
            count += 1
    return count
