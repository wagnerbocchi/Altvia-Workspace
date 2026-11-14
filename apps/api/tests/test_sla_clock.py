"""Exact bounded SLA clock continuation over immutable native status history."""

import importlib
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from importlib.util import find_spec
from pathlib import Path

import pytest
from altvia.business_time import Window, build_calendar, freeze_timezone

MINUTE = 60_000_000
HOUR = 60 * MINUTE
DAY = 24 * HOUR
START = datetime(2026, 11, 16, 9, tzinfo=UTC)


def test_pure_clock_import_does_not_load_http_dto_or_database_runtime():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import altvia.sla_clock; "
            "forbidden={'sqlalchemy','pydantic','fastapi','altvia.models'}; "
            "assert not forbidden.intersection(sys.modules), "
            "sorted(forbidden.intersection(sys.modules))",
        ],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def owner():
    assert find_spec("altvia.sla_clock") is not None, "Missing bounded native SLA clock owner"
    return importlib.import_module("altvia.sla_clock")


@pytest.fixture
def calendar():
    return build_calendar(freeze_timezone("UTC"), [Window(d, 0, 1440) for d in range(7)], [])


def initial(target=HOUR, at=START):
    return owner().initial(at, 1, "open", target)


def point(version, at, old, new):
    return owner().HistoryPoint(version, at, old, new)


def test_exact_budget_fulfillment_is_on_time_with_integer_microseconds(calendar):
    result = owner().step(
        calendar,
        initial(),
        (),
        START + timedelta(hours=1),
        pauses=frozenset(),
        terminal=True,
        fulfilled=True,
    )
    assert result.complete and result.state == "fulfilled"
    assert result.progress.elapsed_us == HOUR
    assert result.progress.due_at == START + timedelta(hours=1)


def test_one_microsecond_over_budget_breaches_at_original_deadline(calendar):
    result = owner().step(
        calendar, initial(), (), START + timedelta(hours=1, microseconds=1), pauses=frozenset()
    )
    assert result.complete and result.state == "breached"
    assert result.progress.elapsed_us == HOUR + 1
    assert result.progress.due_at == START + timedelta(hours=1)


@pytest.mark.parametrize("fulfilled,expected", [(False, "unfulfilled"), (True, "fulfilled")])
def test_terminal_goal_never_invents_response_or_future_deadline(calendar, fulfilled, expected):
    result = owner().step(
        calendar,
        initial(3 * HOUR),
        (),
        START + timedelta(hours=2),
        pauses=frozenset(),
        terminal=True,
        fulfilled=fulfilled,
    )
    assert result.complete and result.state == expected
    assert result.progress.elapsed_us == 2 * HOUR and result.progress.due_at is None


def test_pause_discards_future_projection_resume_keeps_exact_remaining_time(calendar):
    clock = owner()
    first = clock.step(calendar, initial(), (), START + timedelta(minutes=30), pauses=frozenset())
    assert first.progress.due_at == START + timedelta(hours=1)
    paused = clock.step(
        calendar,
        first.progress,
        (point(2, START + timedelta(minutes=45), "open", "pending_customer"),),
        START + timedelta(hours=2),
        pauses=frozenset({"pending_customer"}),
    )
    assert paused.complete and paused.state == "paused"
    assert paused.progress.elapsed_us == 45 * MINUTE and paused.progress.due_at is None
    resumed = clock.step(
        calendar,
        paused.progress,
        (point(3, START + timedelta(hours=2, minutes=30), "pending_customer", "open"),),
        START + timedelta(hours=2, minutes=45),
        pauses=frozenset({"pending_customer"}),
    )
    assert resumed.progress.elapsed_us == HOUR and resumed.state == "approaching"
    assert resumed.progress.due_at == START + timedelta(hours=2, minutes=45)
    exceeded = clock.step(
        calendar,
        resumed.progress,
        (),
        START + timedelta(hours=2, minutes=45, microseconds=1),
        pauses=frozenset({"pending_customer"}),
    )
    assert exceeded.state == "breached" and exceeded.progress.due_at == resumed.progress.due_at


def test_pause_across_holiday_preserves_working_budget():
    calendar = build_calendar(
        freeze_timezone("UTC"), [Window(d, 540, 1020) for d in range(5)], [date(2026, 11, 17)]
    )
    result = owner().step(
        calendar,
        initial(8 * HOUR),
        (
            point(2, START + timedelta(hours=7), "open", "pending_customer"),
            point(3, START + timedelta(days=2, hours=1), "pending_customer", "open"),
        ),
        START + timedelta(days=2, hours=2),
        pauses=frozenset({"pending_customer"}),
        terminal=True,
        fulfilled=True,
    )
    assert result.state == "fulfilled" and result.progress.elapsed_us == 8 * HOUR
    assert result.progress.due_at == START + timedelta(days=2, hours=2)


def test_only_explicit_pause_states_stop_the_clock(calendar):
    result = owner().step(
        calendar,
        initial(3 * HOUR),
        (point(2, START + timedelta(hours=1), "open", "pending_third_party"),),
        START + timedelta(hours=2),
        pauses=frozenset({"pending_customer"}),
    )
    assert result.state == "running" and result.progress.elapsed_us == 2 * HOUR
    assert result.progress.due_at == START + timedelta(hours=3)


def test_exact_budget_at_closing_does_not_breach_during_nonworking_time():
    calendar = build_calendar(freeze_timezone("UTC"), [Window(d, 540, 1020) for d in range(5)], [])
    result = owner().step(
        calendar, initial(8 * HOUR), (), START + timedelta(hours=14), pauses=frozenset()
    )
    assert result.state == "approaching" and result.progress.elapsed_us == 8 * HOUR
    assert result.progress.due_at == START + timedelta(hours=8)
    result = owner().step(
        calendar, result.progress, (), START + timedelta(days=1, microseconds=1), pauses=frozenset()
    )
    assert result.state == "breached" and result.progress.elapsed_us == 8 * HOUR + 1
    assert result.progress.due_at == START + timedelta(hours=8)


def test_pause_at_already_reached_deadline_preserves_its_actual_instant(calendar):
    result = owner().step(
        calendar,
        initial(),
        (point(2, START + timedelta(hours=1), "open", "pending_customer"),),
        START + timedelta(hours=2),
        pauses=frozenset({"pending_customer"}),
    )
    assert result.state == "paused" and result.progress.elapsed_us == HOUR
    assert result.progress.due_at == START + timedelta(hours=1)
    result = owner().step(
        calendar,
        result.progress,
        (point(3, START + timedelta(hours=3), "pending_customer", "open"),),
        START + timedelta(hours=3, microseconds=1),
        pauses=frozenset({"pending_customer"}),
    )
    assert result.state == "breached" and result.progress.due_at == START + timedelta(hours=1)


def test_long_elapsed_continuation_retains_progress_and_first_actual_deadline(calendar):
    clock = owner()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    progress = initial(40 * DAY, start)
    results = []
    for _ in range(3):
        result = clock.step(calendar, progress, (), start + timedelta(days=45), pauses=frozenset())
        assert result.dates_used <= 16
        results.append(result)
        progress = result.progress
    assert [r.progress.through for r in results] == [
        start + timedelta(days=n) for n in (16, 32, 45)
    ]
    assert not results[0].complete and not results[1].complete
    assert results[2].complete and results[2].state == "breached"
    assert progress.elapsed_us == 45 * DAY and progress.due_at == start + timedelta(days=40)


def test_long_future_search_is_not_restarted_by_new_actual_observations(calendar):
    clock = owner()
    progress = initial(40 * DAY)
    searches = []
    for minute in range(3):
        result = clock.step(
            calendar, progress, (), START + timedelta(minutes=minute), pauses=frozenset()
        )
        assert result.dates_used <= 16
        progress = result.progress
        searches.append(progress.search_through)
    assert searches[0] < searches[1] < searches[2]
    assert result.complete and result.state == "running"
    assert progress.due_at == START + timedelta(days=40)
    assert progress.elapsed_us == 2 * MINUTE


def test_partial_history_never_projects_past_unseen_rows_or_spins_on_same_time(calendar):
    clock = owner()
    rows = tuple(
        point(
            n + 2,
            START,
            "open" if n % 2 == 0 else "pending_customer",
            "pending_customer" if n % 2 == 0 else "open",
        )
        for n in range(499)
    )
    result = clock.step(
        calendar,
        initial(),
        rows,
        START + timedelta(hours=2),
        pauses=frozenset({"pending_customer"}),
        history_complete=False,
    )
    assert not result.complete and result.state == "evaluating"
    assert result.progress.through == START and result.progress.history_version == 500
    assert result.progress.elapsed_us == 0 and result.progress.due_at is None
    result = clock.step(
        calendar,
        result.progress,
        (point(501, START + timedelta(hours=2), "pending_customer", "open"),),
        START + timedelta(hours=2),
        pauses=frozenset({"pending_customer"}),
    )
    assert result.complete and result.progress.due_at == START + timedelta(hours=3)


@pytest.mark.parametrize(
    "rows",
    [
        [(2, 2, "open", "pending_customer"), (3, 1, "pending_customer", "open")],
        [(2, 0, "pending_customer", "open")],
        [(2, -1, "open", "pending_customer")],
        [(2, 0, "open", "pending_customer"), (2, 0, "pending_customer", "open")],
    ],
)
def test_nonmonotone_or_discontinuous_source_history_fails_safely(calendar, rows):
    native = tuple(point(v, START + timedelta(minutes=m), old, new) for v, m, old, new in rows)
    with pytest.raises(ValueError, match="timing_inconsistent"):
        owner().step(calendar, initial(), native, START + timedelta(hours=1), pauses=frozenset())


def test_deadline_outside_supported_range_is_unavailable_not_a_fabricated_due(calendar):
    start = datetime(2099, 12, 31, 23, 59, tzinfo=UTC)
    with pytest.raises(ValueError, match="calculation_unavailable"):
        owner().step(calendar, initial(2 * MINUTE, start), (), start, pauses=frozenset())


def test_source_history_page_bound_is_enforced(calendar):
    row = point(2, START, "open", "pending_customer")
    with pytest.raises(ValueError, match="history_bound"):
        owner().step(calendar, initial(), (row,) * 500, START, pauses=frozenset())


def test_later_pause_cannot_hide_an_already_breached_goal(calendar):
    result = owner().step(
        calendar,
        initial(),
        (point(2, START + timedelta(hours=1, microseconds=1), "open", "pending_customer"),),
        START + timedelta(hours=2),
        pauses=frozenset({"pending_customer"}),
    )
    assert result.state == "breached" and result.progress.current_status == "pending_customer"
    assert result.progress.due_at == START + timedelta(hours=1)


def test_pause_interrupts_long_future_search_and_resume_uses_new_anchor(calendar):
    clock = owner()
    first = clock.step(
        calendar, initial(40 * DAY), (), START, pauses=frozenset({"pending_customer"})
    )
    assert not first.complete and first.progress.search_through > START
    paused = clock.step(
        calendar,
        first.progress,
        (point(2, START + timedelta(minutes=1), "open", "pending_customer"),),
        START + timedelta(minutes=2),
        pauses=frozenset({"pending_customer"}),
    )
    assert paused.state == "paused" and paused.progress.search_through is None
    assert paused.progress.search_remaining_us == 40 * DAY - MINUTE
    resume = START + timedelta(days=1, minutes=1)
    rows = (point(3, resume, "pending_customer", "open"),)
    progress = paused.progress
    for _ in range(5):
        result = clock.step(
            calendar, progress, rows, resume, pauses=frozenset({"pending_customer"})
        )
        progress, rows = result.progress, ()
        if result.complete:
            break
    assert result.complete and progress.due_at == START + timedelta(days=41)
    assert progress.elapsed_us == MINUTE


@pytest.mark.parametrize(
    "changes",
    [
        {"pauses": frozenset({"open"})},
        {"pauses": {"pending_customer"}},
        {"approach_us": -1},
        {"approach_us": True},
        {"terminal": 1},
        {"fulfilled": True},
        {"history_complete": False},
    ],
)
def test_clock_rejects_unbounded_or_ambiguous_evaluation_intent(calendar, changes):
    with pytest.raises(ValueError):
        owner().step(calendar, initial(), (), START, **{"pauses": frozenset(), **changes})
