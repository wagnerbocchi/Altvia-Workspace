"""Current ticket authority before bounded read-only frozen SLA projections."""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from altvia import tickets
from altvia.admin_http import authenticate_request
from altvia.config import Settings
from altvia.models import (
    BusinessCalendarRevision,
    SlaPolicyRevision,
    TicketSlaEvent,
    TicketSlaGoal,
    TicketSlaState,
    TicketStatusHistory,
)
from altvia.sla_schemas import (
    CycleState,
    GoalStatus,
    SlaCycleOutput,
    SlaCyclePage,
    SlaCycleQuery,
    SlaGoalOutput,
)
from altvia.ticket_api import _collection, _version_cursor
from altvia.work_schemas import Priority


@dataclass(frozen=True)
class Snapshot:
    cycle: TicketSlaState
    policy: SlaPolicyRevision | None
    calendar_name: str | None
    calendar_version: int | None
    timezone: str | None
    end_at: datetime | None
    history_version: int


def _snapshots(db: Session, ticket_id: UUID, before: int | None, limit: int) -> list[Snapshot]:
    end = (
        select(TicketStatusHistory.version)
        .where(
            TicketStatusHistory.ticket_id == TicketSlaState.ticket_id,
            TicketStatusHistory.version > TicketSlaState.start_version,
            TicketStatusHistory.to_status == "resolved",
        )
        .order_by(TicketStatusHistory.version)
        .limit(1)
        .correlate(TicketSlaState)
        .scalar_subquery()
    )
    end_at = (
        select(TicketStatusHistory.occurred_at)
        .where(
            TicketStatusHistory.ticket_id == TicketSlaState.ticket_id,
            TicketStatusHistory.version == end,
        )
        .correlate(TicketSlaState)
        .scalar_subquery()
    )
    history_version = (
        select(func.max(TicketStatusHistory.version))
        .where(
            TicketStatusHistory.ticket_id == TicketSlaState.ticket_id,
            TicketStatusHistory.version >= TicketSlaState.start_version,
            TicketStatusHistory.version <= func.coalesce(end, 2147483647),
        )
        .correlate(TicketSlaState)
        .scalar_subquery()
    )
    query = (
        select(
            TicketSlaState,
            SlaPolicyRevision,
            BusinessCalendarRevision.name,
            BusinessCalendarRevision.version,
            BusinessCalendarRevision.timezone,
            end_at,
            history_version,
        )
        .outerjoin(
            SlaPolicyRevision,
            (SlaPolicyRevision.policy_id == TicketSlaState.policy_id)
            & (SlaPolicyRevision.version == TicketSlaState.policy_version),
        )
        .outerjoin(
            BusinessCalendarRevision,
            (BusinessCalendarRevision.calendar_id == SlaPolicyRevision.calendar_id)
            & (BusinessCalendarRevision.version == SlaPolicyRevision.calendar_version),
        )
        .where(TicketSlaState.ticket_id == ticket_id)
        .order_by(TicketSlaState.cycle_number.desc())
        .limit(limit)
    )
    if before is not None:
        query = query.where(TicketSlaState.cycle_number < before)
    rows = db.execute(query)
    return [Snapshot(*row) for row in rows]


def _outputs(db: Session, rows: list[Snapshot], now: datetime) -> list[SlaCycleOutput]:
    if not rows:
        return []
    ticket_id = rows[0].cycle.ticket_id
    numbers = [s.cycle.cycle_number for s in rows]
    goals = {
        (g.cycle_number, g.goal): g
        for g in db.scalars(
            select(TicketSlaGoal).where(
                TicketSlaGoal.ticket_id == ticket_id, TicketSlaGoal.cycle_number.in_(numbers)
            )
        )
    }
    events: dict[tuple[int, str], list[TicketSlaEvent]] = {}
    # At most one breach is needed for each goal. Corrections are projected by
    # DISTINCT below, rather than loading an unbounded evidence history per page.
    for event in db.scalars(
        select(TicketSlaEvent).where(
            TicketSlaEvent.ticket_id == ticket_id,
            TicketSlaEvent.cycle_number.in_(numbers),
            TicketSlaEvent.kind == "breached",
        )
    ):
        events.setdefault((event.cycle_number, event.goal), []).append(event)
    corrected = set(
        db.scalars(
            select(TicketSlaEvent.cycle_number)
            .where(
                TicketSlaEvent.ticket_id == ticket_id,
                TicketSlaEvent.cycle_number.in_(numbers),
                TicketSlaEvent.kind == "corrected",
            )
            .distinct()
        )
    )
    result = []
    for snapshot in rows:
        cycle, policy = snapshot.cycle, snapshot.policy
        state = cast(CycleState, cycle.state)
        resolution = goals.get((cycle.cycle_number, "resolution"))
        if state == "ready" and (
            resolution is None or resolution.last_history_version < snapshot.history_version
        ):
            state = "evaluating"
        if (
            state == "ready"
            and snapshot.end_at is None
            and (cycle.evaluated_at is None or cycle.evaluated_at < now - timedelta(seconds=90))
        ):
            state = "stale"
        summaries: dict[str, SlaGoalOutput | None] = {}
        for name in ("first_response", "resolution"):
            goal = goals.get((cycle.cycle_number, name))
            if goal is None or policy is None:
                summaries[name] = None
                continue
            minutes = (
                policy.first_response_minutes
                if name == "first_response"
                else policy.resolution_minutes
            )
            summaries[name] = SlaGoalOutput(
                status="evaluating" if state == "evaluating" else cast(GoalStatus, goal.outcome),
                target_minutes=minutes,
                elapsed_business_seconds=goal.elapsed_us // 1_000_000,
                remaining_business_seconds=max(0, minutes * 60_000_000 - goal.elapsed_us + 999_999)
                // 1_000_000,
                due_at=goal.due_at,
                fulfilled_at=cycle.first_response_at if name == "first_response" else cycle.end_at,
                breached_at=next(
                    (e.occurred_at for e in events.get((cycle.cycle_number, name), [])), None
                ),
                corrected=name == "first_response" and cycle.cycle_number in corrected,
            )
        result.append(
            SlaCycleOutput(
                number=cycle.cycle_number,
                start_at=cycle.start_at,
                end_at=snapshot.end_at,
                initial_category_id=cycle.initial_category_id,
                initial_priority=cast(Priority, cycle.initial_priority),
                policy_name=policy.name if policy else None,
                policy_version=cycle.policy_version,
                calendar_name=snapshot.calendar_name,
                calendar_version=snapshot.calendar_version,
                timezone=snapshot.timezone,
                state=state,
                computed_through_at=cycle.computed_through_at,
                evaluated_at=cycle.evaluated_at,
                safe_error=cycle.safe_error,
                first_response=summaries["first_response"],
                resolution=summaries["resolution"],
            )
        )
    return result


def create_sla_read_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/tickets", tags=["Ticket SLA outcomes"])

    @router.get("/{identifier}/sla", response_model=SlaCyclePage)
    def outcomes(
        identifier: UUID, request: Request, filters: Annotated[SlaCycleQuery, Query()]
    ) -> SlaCyclePage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            tickets.scoped_ticket(db, actor.id, identifier)
            # The native helper checks known/unique query keys separately from
            # the typed values. Authorization deliberately precedes both cursor
            # interpretation and any SLA metadata lookup.
            _collection(request)
            scope = (
                "ticket-sla:"
                + hashlib.sha256(f"{actor.id}:{identifier}".encode()).hexdigest()
                + ":"
            )
            last = _version_cursor(filters.cursor, scope)
            now = db.scalar(select(func.clock_timestamp()))
            if not isinstance(now, datetime):
                raise ValueError("Missing database observation clock")
            current = _snapshots(db, identifier, None, 1)
            history = (
                _snapshots(
                    db,
                    identifier,
                    min(last, current[0].cycle.cycle_number)
                    if last is not None
                    else current[0].cycle.cycle_number,
                    filters.limit + 1,
                )
                if current
                else []
            )
            visible = _outputs(db, current + history[: filters.limit], now)
            return SlaCyclePage(
                current=visible[0] if current else None,
                history=visible[1:] if current else [],
                observed_at=now,
                next_cursor=scope + str(history[filters.limit - 1].cycle.cycle_number)
                if len(history) > filters.limit
                else None,
            )

    return router
