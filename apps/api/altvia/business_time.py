"""Bounded business time on immutable installed timezone and calendar snapshots."""

import hashlib
import io
import re
import zoneinfo
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import IO

MAX_TZIF_BYTES = 256 * 1024
MAX_BUDGET_US = 525600 * 60_000_000
START = datetime(2000, 1, 1, tzinfo=UTC)
END = datetime(2100, 1, 1, tzinfo=UTC)
TICK = timedelta(microseconds=1)
DAY = timedelta(days=1)
Interval = tuple[datetime, datetime]


@lru_cache(maxsize=16)
def _parsed_zone(name: str, wire: bytes) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo.from_file(io.BytesIO(wire), key=name)
    except (ValueError, OSError, EOFError) as error:
        raise ValueError("Invalid frozen timezone") from error


@dataclass(frozen=True)
class FrozenZone:
    name: str
    tzif: bytes
    sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not re.fullmatch(r"[A-Za-z0-9_+/-]{1,100}", self.name)
            or any(part in {"", ".", ".."} for part in self.name.split("/"))
            or type(self.tzif) is not bytes
            or not 1 <= len(self.tzif) <= MAX_TZIF_BYTES
            or not isinstance(self.sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.sha256)
            or hashlib.sha256(self.tzif).hexdigest() != self.sha256
        ):
            raise ValueError("Invalid frozen timezone")
        _parsed_zone(self.name, self.tzif)


@lru_cache(maxsize=1)
def _installed_names() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


def _bounded_read(stream: IO[bytes]) -> bytes:
    wire = stream.read(MAX_TZIF_BYTES + 1)
    if not 1 <= len(wire) <= MAX_TZIF_BYTES:
        raise ValueError("Timezone artifact outside supported bound")
    return wire


def freeze_timezone(name: str) -> FrozenZone:
    if (
        not isinstance(name, str)
        or not re.fullmatch(r"[A-Za-z0-9_+/-]{1,100}", name)
        or any(part in {"", ".", ".."} for part in name.split("/"))
        or name not in _installed_names()
    ):
        raise ValueError("Select an installed IANA timezone")
    parts = name.split("/")
    for directory in zoneinfo.TZPATH:
        try:
            with Path(directory).joinpath(*parts).open("rb") as stream:
                wire = _bounded_read(stream)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ValueError("Installed timezone unavailable") from error
        return FrozenZone(name, wire, hashlib.sha256(wire).hexdigest())
    try:
        # Windows already has the locked tzdata dependency through its installed
        # toolchain. Linux normally uses its image's native TZPATH artifacts.
        with files("tzdata.zoneinfo").joinpath(*parts).open("rb") as stream:
            wire = _bounded_read(stream)
    except (ModuleNotFoundError, FileNotFoundError, OSError) as error:
        raise ValueError("Installed timezone unavailable") from error
    return FrozenZone(name, wire, hashlib.sha256(wire).hexdigest())


@dataclass(frozen=True, order=True)
class Window:
    weekday: int
    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        if (
            any(
                type(value) is not int
                for value in (self.weekday, self.start_minute, self.end_minute)
            )
            or not 0 <= self.weekday <= 6
            or not 0 <= self.start_minute < self.end_minute <= 1440
        ):
            raise ValueError("Invalid weekly window")


def _windows(values: Sequence[Window]) -> tuple[Window, ...]:
    if not 1 <= len(values) <= 28 or any(not isinstance(value, Window) for value in values):
        raise ValueError("Select between one and 28 weekly windows")
    merged: list[Window] = []
    for value in sorted(values):
        if merged and merged[-1].weekday == value.weekday:
            previous = merged[-1]
            if value.start_minute < previous.end_minute:
                raise ValueError("Weekly windows cannot overlap or repeat")
            if value.start_minute == previous.end_minute:
                merged[-1] = Window(previous.weekday, previous.start_minute, value.end_minute)
                continue
        merged.append(value)
    return tuple(merged)


def _holidays(values: Sequence[date]) -> frozenset[date]:
    if len(values) > 1000 or any(type(value) is not date for value in values):
        raise ValueError("Invalid holiday dates")
    result = frozenset(values)
    if len(result) != len(values):
        raise ValueError("Holiday dates cannot repeat")
    return result


@dataclass(frozen=True)
class CalendarSnapshot:
    zone: FrozenZone
    windows: tuple[Window, ...]
    holidays: frozenset[date]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.zone, FrozenZone)
            or type(self.windows) is not tuple
            or type(self.holidays) is not frozenset
            or _windows(self.windows) != self.windows
        ):
            raise ValueError("Immutable canonical calendar required")
        _holidays(tuple(self.holidays))


def build_calendar(
    zone: FrozenZone, windows: Sequence[Window], holidays: Sequence[date]
) -> CalendarSnapshot:
    return CalendarSnapshot(zone, _windows(windows), _holidays(holidays))


def _append(rows: list[Interval], start: datetime, end: datetime) -> None:
    if rows and rows[-1][1] == start:
        rows[-1] = (rows[-1][0], end)
    else:
        rows.append((start, end))


@lru_cache(maxsize=256)
def _day_intervals(calendar: CalendarSnapshot, utc_day: date) -> tuple[Interval, ...]:
    zone = _parsed_zone(calendar.zone.name, calendar.zone.tzif)
    weekly = tuple(
        tuple((row.start_minute, row.end_minute) for row in calendar.windows if row.weekday == day)
        for day in range(7)
    )

    def eligible(local: datetime) -> bool:
        minute = local.hour * 60 + local.minute
        return local.date() not in calendar.holidays and any(
            opening <= minute < closing for opening, closing in weekly[local.weekday()]
        )

    rows: list[Interval] = []
    start = datetime.combine(utc_day, datetime.min.time(), UTC)
    for minute in range(1440):
        left = start + timedelta(minutes=minute)
        right = left + timedelta(minutes=1)
        first, last = left.astimezone(zone), (right - TICK).astimezone(zone)
        first_allowed = eligible(first)
        if first.utcoffset() == last.utcoffset() and first_allowed == eligible(last):
            if first_allowed:
                _append(rows, left, right)
            continue
        # TZif transitions occur at integer seconds. Minute-sized wall windows
        # may nevertheless start inside a UTC minute for a second-based offset.
        for second in range(60):
            point = left + timedelta(seconds=second)
            if eligible(point.astimezone(zone)):
                _append(rows, point, point + timedelta(seconds=1))
    return tuple(rows)


def intervals(calendar: CalendarSnapshot, utc_day: date) -> tuple[Interval, ...]:
    if type(utc_day) is not date or not START.date() <= utc_day < END.date():
        raise ValueError("UTC day outside supported range")
    return _day_intervals(calendar, utc_day)


def _span(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if (
        not isinstance(start, datetime)
        or not isinstance(end, datetime)
        or start.utcoffset() is None
        or end.utcoffset() is None
    ):
        raise ValueError("Aware instants required")
    try:
        start, end = start.astimezone(UTC), end.astimezone(UTC)
    except OverflowError as error:
        raise ValueError("Span outside supported range") from error
    if not START <= start <= end <= END:
        raise ValueError("Span outside supported range")
    if start != end and ((end - TICK).date() - start.date()).days >= 32:
        raise ValueError("At most 32 UTC dates per step")
    return start, end


def _intersections(
    calendar: CalendarSnapshot, start: datetime, end: datetime
) -> Iterator[Interval]:
    day = start.date()
    while datetime.combine(day, datetime.min.time(), UTC) < end:
        for opening, closing in intervals(calendar, day):
            left, right = max(start, opening), min(end, closing)
            if left < right:
                yield left, right
        day += DAY


def _microseconds(delta: timedelta) -> int:
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def elapsed_us(calendar: CalendarSnapshot, start: datetime, end: datetime) -> int:
    start, end = _span(start, end)
    return sum(_microseconds(right - left) for left, right in _intersections(calendar, start, end))


@dataclass(frozen=True)
class DeadlineProgress:
    through: datetime
    remaining_us: int
    due_at: datetime | None


def advance(
    calendar: CalendarSnapshot, start: datetime, budget_us: int, end: datetime
) -> DeadlineProgress:
    start, end = _span(start, end)
    if type(budget_us) is not int or not 0 <= budget_us <= MAX_BUDGET_US:
        raise ValueError("Invalid business-time budget")
    if budget_us == 0:
        return DeadlineProgress(start, 0, start)
    for left, right in _intersections(calendar, start, end):
        available = _microseconds(right - left)
        if budget_us <= available:
            due = left + timedelta(microseconds=budget_us)
            return DeadlineProgress(due, 0, due)
        budget_us -= available
    return DeadlineProgress(end, budget_us, None)
