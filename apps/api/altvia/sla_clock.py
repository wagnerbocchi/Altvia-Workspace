"""Bounded immutable SLA clock steps; native sources retain all authority."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal

from altvia import business_time
from altvia.business_time import CalendarSnapshot
from altvia.ticket_state import TICKET_TRANSITIONS, Status

MAX_DATES = 16
MAX_HISTORY = 499
MAX_ELAPSED_US = 3_155_760_000_000_000
TICK = timedelta(microseconds=1)
ClockState = Literal[
    "evaluating", "running", "paused", "approaching", "fulfilled", "unfulfilled", "breached"
]


def _instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timing_inconsistent")
    value = value.astimezone(UTC)
    if not business_time.START <= value <= business_time.END:
        raise ValueError("timing_inconsistent")
    return value


@dataclass(frozen=True)
class HistoryPoint:
    version: int
    at: datetime
    from_status: Status
    to_status: Status

    def __post_init__(self) -> None:
        object.__setattr__(self, "at", _instant(self.at))
        if (
            type(self.version) is not int
            or not 1 <= self.version <= 2147483647
            or self.from_status not in TICKET_TRANSITIONS
            or self.to_status not in TICKET_TRANSITIONS[self.from_status]
        ):
            raise ValueError("timing_inconsistent")


@dataclass(frozen=True)
class ClockProgress:
    through: datetime
    history_version: int
    current_status: Status
    target_us: int
    elapsed_us: int
    due_at: datetime | None
    search_through: datetime | None
    search_remaining_us: int

    def __post_init__(self) -> None:
        for name in ("through", "due_at", "search_through"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _instant(value))
        if (
            type(self.history_version) is not int
            or not 1 <= self.history_version <= 2147483647
            or self.current_status not in TICKET_TRANSITIONS
            or type(self.target_us) is not int
            or not 1 <= self.target_us <= business_time.MAX_BUDGET_US
            or type(self.elapsed_us) is not int
            or not 0 <= self.elapsed_us <= MAX_ELAPSED_US
            or type(self.search_remaining_us) is not int
            or not 0 <= self.search_remaining_us <= self.target_us
            or (self.due_at is not None and self.search_remaining_us != 0)
            or (self.due_at is None and self.search_remaining_us == 0)
        ):
            raise ValueError("timing_inconsistent")


@dataclass(frozen=True)
class ClockStep:
    progress: ClockProgress
    complete: bool
    state: ClockState
    dates_used: int
    rows_used: int


def initial(at: datetime, version: int, status: Status, target_us: int) -> ClockProgress:
    at = _instant(at)
    if at == business_time.END or status not in {"new", "open"}:
        raise ValueError("timing_inconsistent")
    return ClockProgress(at, version, status, target_us, 0, None, at, target_us)


def _dates(left: datetime, right: datetime) -> int:
    return 0 if left == right else ((right - TICK).date() - left.date()).days + 1


def _horizon(start: datetime, dates: int) -> datetime:
    if not dates:
        return start
    return min(
        business_time.END,
        datetime.combine(start.date(), datetime.min.time(), UTC) + timedelta(days=dates),
    )


def _segment(
    calendar: CalendarSnapshot, progress: ClockProgress, end: datetime, pauses: frozenset[str]
) -> ClockProgress:
    if end == progress.through:
        return progress
    if progress.current_status in {"resolved", "closed"}:
        raise ValueError("timing_inconsistent")
    if progress.current_status in pauses:
        return replace(progress, through=end)
    used = business_time.elapsed_us(calendar, progress.through, end)
    if progress.elapsed_us < progress.target_us <= progress.elapsed_us + used:
        due = business_time.advance(
            calendar, progress.through, progress.target_us - progress.elapsed_us, end
        ).due_at
        if due is None:
            raise ValueError("calculation_unavailable")
        return replace(
            progress,
            through=end,
            elapsed_us=progress.elapsed_us + used,
            due_at=due,
            search_through=due,
            search_remaining_us=0,
        )
    return replace(progress, through=end, elapsed_us=progress.elapsed_us + used)


def step(
    calendar: CalendarSnapshot,
    progress: ClockProgress,
    history: Sequence[HistoryPoint],
    cutoff: datetime,
    *,
    pauses: frozenset[str],
    approach_us: int = 0,
    history_complete: bool = True,
    terminal: bool = False,
    fulfilled: bool = False,
) -> ClockStep:
    """Continue actual time first, then its independent bounded future search."""
    if len(history) > MAX_HISTORY:
        raise ValueError("history_bound")
    if (
        not isinstance(calendar, CalendarSnapshot)
        or not isinstance(progress, ClockProgress)
        or type(pauses) is not frozenset
        or not pauses <= {"pending_customer", "pending_third_party"}
        or type(approach_us) is not int
        or not 0 <= approach_us <= business_time.MAX_BUDGET_US
        or any(type(value) is not bool for value in (history_complete, terminal, fulfilled))
        or (fulfilled and not terminal)
    ):
        raise ValueError("invalid_clock_input")
    cutoff = _instant(cutoff)
    if cutoff < progress.through or (not history_complete and not history):
        raise ValueError("timing_inconsistent")
    previous_time, previous_version, previous_status = (
        progress.through,
        progress.history_version,
        progress.current_status,
    )
    for point in history:
        if (
            not isinstance(point, HistoryPoint)
            or point.version <= previous_version
            or point.at < previous_time
            or point.from_status != previous_status
            or (not terminal and point.at > cutoff)
        ):
            raise ValueError("timing_inconsistent")
        previous_time, previous_version, previous_status = point.at, point.version, point.to_status

    original = progress.through
    end = min(cutoff, _horizon(original, MAX_DATES))
    blocked = not history_complete and history[-1].at <= cutoff
    if blocked:
        end = min(end, history[-1].at)
    consumed = 0
    for point in history:
        if point.at > end:
            break
        progress = _segment(calendar, progress, point.at, pauses)
        was_paused, is_paused = progress.current_status in pauses, point.to_status in pauses
        progress = replace(progress, history_version=point.version, current_status=point.to_status)
        if was_paused != is_paused and progress.elapsed_us < progress.target_us:
            progress = replace(
                progress,
                due_at=None,
                search_through=None if is_paused else point.at,
                search_remaining_us=progress.target_us - progress.elapsed_us,
            )
        consumed += 1
    progress = _segment(calendar, progress, end, pauses)
    if progress.current_status in {"resolved", "closed"} and not terminal:
        raise ValueError("timing_inconsistent")
    dates_used = _dates(original, progress.through)
    actual_complete = progress.through == cutoff and not blocked
    is_paused = progress.current_status in pauses

    if (
        actual_complete
        and not terminal
        and not is_paused
        and progress.due_at is None
        and dates_used < MAX_DATES
    ):
        if progress.search_through is None:
            raise ValueError("timing_inconsistent")
        search_start = progress.search_through
        search = business_time.advance(
            calendar,
            search_start,
            progress.search_remaining_us,
            _horizon(search_start, MAX_DATES - dates_used),
        )
        progress = replace(
            progress,
            search_through=search.through,
            search_remaining_us=search.remaining_us,
            due_at=search.due_at,
        )
        dates_used += _dates(search_start, search.through)
        if search.due_at is None and search.through == business_time.END:
            raise ValueError("calculation_unavailable")

    complete = actual_complete and (terminal or is_paused or progress.due_at is not None)
    state: ClockState
    if not complete:
        state = "evaluating"
    elif terminal:
        state = (
            "breached"
            if progress.elapsed_us > progress.target_us
            else ("fulfilled" if fulfilled else "unfulfilled")
        )
    elif progress.elapsed_us > progress.target_us:
        state = "breached"
    elif is_paused:
        state = "paused"
    elif progress.target_us - progress.elapsed_us <= approach_us:
        state = "approaching"
    else:
        state = "running"
    return ClockStep(progress, complete, state, dates_used, consumed)
