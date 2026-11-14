"""Exact business time, frozen timezone rules and bounded deadline continuation."""

import hashlib
import struct
from datetime import UTC, date, datetime, timedelta
from importlib import import_module
from importlib.util import find_spec

import pytest

SECOND = 1_000_000
MINUTE = 60 * SECOND


def owner():
    assert find_spec("altvia.business_time") is not None, "Business-time engine is not implemented"
    return import_module("altvia.business_time")


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def calendar(zone="UTC", windows=((0, 540, 1020),), holidays=()):
    module = owner()
    return module.build_calendar(
        module.freeze_timezone(zone), [module.Window(*window) for window in windows], holidays
    )


def fixed_zone(seconds, name="Test/Seconds"):
    wire = (
        b"TZif\0"
        + b"\0" * 15
        + struct.pack(">6l", 0, 0, 0, 0, 1, 4)
        + struct.pack(">lBB", seconds, 0, 0)
        + b"TST\0"
    )
    return owner().FrozenZone(name, wire, hashlib.sha256(wire).hexdigest())


def test_work_window_counts_only_actual_intersection_with_microseconds():
    module = owner()
    snapshot = calendar()
    assert (
        module.elapsed_us(
            snapshot, instant("2026-11-09T08:59:59.250000Z"), instant("2026-11-09T09:15:00.125000Z")
        )
        == 15 * MINUTE + 125_000
    )


def test_touching_windows_coalesce_but_lunch_remains_outside_business_time():
    module = owner()
    snapshot = calendar(windows=((0, 780, 1020), (0, 540, 600), (0, 600, 720)))
    assert module.intervals(snapshot, date(2026, 11, 9)) == (
        (instant("2026-11-09T09:00Z"), instant("2026-11-09T12:00Z")),
        (instant("2026-11-09T13:00Z"), instant("2026-11-09T17:00Z")),
    )
    assert (
        module.elapsed_us(snapshot, instant("2026-11-09T08:00Z"), instant("2026-11-09T18:00Z"))
        == 7 * 60 * MINUTE
    )


def test_local_holiday_removes_the_correct_utc_portion_across_midnight():
    module = owner()
    base = calendar("Pacific/Apia", windows=((5, 0, 1440),))
    holiday = calendar("Pacific/Apia", windows=((5, 0, 1440),), holidays=[date(2011, 12, 31)])
    start, end = instant("2011-12-30T00:00Z"), instant("2011-12-31T00:00Z")
    assert module.elapsed_us(base, start, end) == 14 * 60 * MINUTE
    assert module.elapsed_us(holiday, start, end) == 0


@pytest.mark.parametrize(
    ("zone", "windows", "start", "end", "minutes"),
    [
        ("America/New_York", ((6, 90, 105),), "2026-11-01T04:00Z", "2026-11-01T08:00Z", 30),
        ("America/New_York", ((6, 120, 180),), "2026-03-08T05:00Z", "2026-03-08T09:00Z", 0),
        ("America/New_York", ((6, 90, 210),), "2026-03-08T05:00Z", "2026-03-08T09:00Z", 60),
        ("America/New_York", ((6, 0, 1440),), "2026-03-08T00:00Z", "2026-03-09T12:00Z", 23 * 60),
        ("America/New_York", ((6, 0, 1440),), "2026-11-01T00:00Z", "2026-11-02T12:00Z", 25 * 60),
        ("Australia/Lord_Howe", ((6, 90, 105),), "2026-04-04T13:00Z", "2026-04-04T17:00Z", 30),
        ("Australia/Lord_Howe", ((6, 120, 180),), "2026-10-03T13:00Z", "2026-10-03T18:00Z", 30),
        ("Pacific/Apia", ((4, 0, 1440),), "2011-12-29T00:00Z", "2011-12-31T00:00Z", 0),
    ],
)
def test_dst_repeated_missing_half_hour_and_skipped_date(zone, windows, start, end, minutes):
    assert (
        owner().elapsed_us(calendar(zone, windows), instant(start), instant(end))
        == minutes * MINUTE
    )


def test_a_holiday_removes_both_occurrences_of_a_repeated_local_window():
    snapshot = calendar("America/New_York", ((6, 90, 105),), [date(2026, 11, 1)])
    assert (
        owner().elapsed_us(snapshot, instant("2026-11-01T04:00Z"), instant("2026-11-01T08:00Z"))
        == 0
    )


def test_frozen_tzif_with_second_offset_keeps_partial_minutes_exact():
    module = owner()
    # Trusted synthetic standard TZif v1: fixed +00:00:30, one type, no transition.
    # It tests arithmetic only; HTTP cannot upload or select a custom TZif.
    zone = fixed_zone(30)
    snapshot = module.build_calendar(zone, [module.Window(0, 540, 541)], [])
    assert module.intervals(snapshot, date(2026, 11, 9)) == (
        (instant("2026-11-09T08:59:30Z"), instant("2026-11-09T09:00:30Z")),
    )
    assert (
        module.elapsed_us(
            snapshot, instant("2026-11-09T08:59:30.250000Z"), instant("2026-11-09T09:00:29.750000Z")
        )
        == 59_500_000
    )


def test_same_timezone_name_cannot_replace_a_captured_revisions_rules():
    module = owner()
    original = module.build_calendar(fixed_zone(0), [module.Window(0, 540, 541)], [])
    changed = module.build_calendar(fixed_zone(30), [module.Window(0, 540, 541)], [])
    start, end = instant("2026-11-09T09:00:40Z"), instant("2026-11-09T09:01:00Z")
    assert original.zone.name == changed.zone.name
    assert module.elapsed_us(original, start, end) == 20 * SECOND
    assert module.elapsed_us(changed, start, end) == 0
    assert module.elapsed_us(original, start, end) == 20 * SECOND


def test_deadline_keeps_a_partial_microsecond_budget_exact():
    module = owner()
    start = instant("2026-11-09T09:00:00.125000Z")
    result = module.advance(calendar(), start, 1_250_001, instant("2026-11-09T10:00Z"))
    assert result.due_at == result.through == instant("2026-11-09T09:00:01.375001Z")
    assert result.remaining_us == 0


def test_deadline_continuation_preserves_budget_across_weekend_and_exact_closing():
    module = owner()
    snapshot = calendar(windows=tuple((day, 540, 1020) for day in range(5)))
    start, friday_end = instant("2026-11-13T16:00Z"), instant("2026-11-13T17:00Z")
    partial = module.advance(snapshot, start, 120 * MINUTE, friday_end)
    assert partial.through == friday_end and partial.remaining_us == 60 * MINUTE
    assert partial.due_at is None
    resumed = module.advance(
        snapshot, partial.through, partial.remaining_us, instant("2026-11-16T10:00Z")
    )
    assert resumed.due_at == resumed.through == instant("2026-11-16T10:00Z")
    assert resumed.remaining_us == 0
    exact = module.advance(
        snapshot, instant("2026-11-09T16:00Z"), 60 * MINUTE, instant("2026-11-09T18:00Z")
    )
    assert exact.due_at == instant("2026-11-09T17:00Z")


def test_zero_span_zero_budget_and_non_utc_input_preserve_the_actual_instant():
    module = owner()
    snapshot = calendar()
    start = instant("2026-11-09T09:00Z")
    assert module.elapsed_us(snapshot, start, start) == 0
    assert module.advance(snapshot, start, 0, start).due_at == start
    assert module.advance(snapshot, start, MINUTE, start).remaining_us == MINUTE
    assert (
        module.elapsed_us(snapshot, instant("2026-11-09T10:00+01:00"), start + timedelta(minutes=1))
        == MINUTE
    )


@pytest.mark.parametrize(
    "name", ["", "../UTC", "/etc/passwd", "Etc/../../UTC", "UTC\0", "Unknown/Zone"]
)
def test_timezone_capture_rejects_untrusted_names(name):
    with pytest.raises(ValueError):
        owner().freeze_timezone(name)


def test_frozen_zone_rejects_corruption_mutable_input_and_unparseable_tzif():
    module = owner()
    zone = module.freeze_timezone("UTC")
    assert hashlib.sha256(zone.tzif).hexdigest() == zone.sha256
    with pytest.raises(ValueError):
        module.FrozenZone(zone.name, zone.tzif, "0" * 64)
    with pytest.raises(ValueError):
        module.FrozenZone(zone.name, bytearray(zone.tzif), zone.sha256)
    wire = b"not a TZif file"
    with pytest.raises(ValueError):
        module.FrozenZone("Test/Invalid", wire, hashlib.sha256(wire).hexdigest())


@pytest.mark.parametrize(
    "values",
    [(True, 0, 60), (7, 0, 60), (0, -1, 60), (0, 0, 1441), (0, 60, 60), (0, 61, 60), (0, 0, True)],
)
def test_window_rejects_invalid_exact_integer_ranges(values):
    with pytest.raises(ValueError):
        owner().Window(*values)


@pytest.mark.parametrize(
    "windows",
    [
        (),
        ((0, 540, 600), (0, 540, 600)),
        ((0, 540, 660), (0, 600, 720)),
        tuple((0, minute, minute + 1) for minute in range(29)),
    ],
)
def test_calendar_rejects_missing_duplicate_overlapping_or_unbounded_windows(windows):
    with pytest.raises(ValueError):
        calendar(windows=windows)


def test_duplicate_or_unbounded_holidays_are_not_silently_normalized():
    holiday = date(2026, 11, 9)
    with pytest.raises(ValueError):
        calendar(holidays=[holiday, holiday])
    with pytest.raises(ValueError):
        calendar(holidays=[holiday + timedelta(days=n) for n in range(1001)])
    with pytest.raises(ValueError):
        calendar(holidays=[datetime(2026, 11, 9, tzinfo=UTC)])


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 11, 9), instant("2026-11-09T10:00Z")),
        (instant("2026-11-09T11:00Z"), instant("2026-11-09T10:00Z")),
        (instant("1999-12-31T23:59:59Z"), instant("2000-01-01T00:00Z")),
        (instant("2099-12-31T00:00Z"), instant("2100-01-01T00:00:01Z")),
        (instant("2026-01-01T12:00Z"), instant("2026-02-02T12:00Z")),
    ],
)
def test_unsupported_or_unbounded_span_is_rejected_without_partial_success(start, end):
    module = owner()
    snapshot = calendar()
    with pytest.raises(ValueError):
        module.elapsed_us(snapshot, start, end)
    with pytest.raises(ValueError):
        module.advance(snapshot, start, MINUTE, end)


@pytest.mark.parametrize("budget", [-1, True, 1.5, 525600 * MINUTE + 1])
def test_deadline_rejects_invalid_or_over_policy_bound_budget(budget):
    with pytest.raises(ValueError):
        owner().advance(
            calendar(), instant("2026-11-09T09:00Z"), budget, instant("2026-11-09T10:00Z")
        )


def test_exact_32_day_span_and_exclusive_upper_endpoint_are_supported():
    module = owner()
    snapshot = calendar(windows=tuple((day, 0, 1440) for day in range(7)))
    start, end = instant("2026-01-01T00:00Z"), instant("2026-02-02T00:00Z")
    assert module.elapsed_us(snapshot, start, end) == 32 * 24 * 60 * MINUTE
    assert (
        module.elapsed_us(snapshot, instant("2099-12-31T00:00Z"), instant("2100-01-01T00:00Z"))
        == 24 * 60 * MINUTE
    )
