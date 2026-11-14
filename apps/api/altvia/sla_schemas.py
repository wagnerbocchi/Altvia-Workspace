"""Strict bounded calendar and SLA policy configuration contracts."""

import re
from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BeforeValidator, Field, StrictBool, StrictInt, field_validator, model_validator

from altvia.business_time import Window, canonical_windows
from altvia.work_schemas import Priority, StrictModel


def _single_line(value: object) -> object:
    if isinstance(value, str):
        if any(character in value for character in "\x00\r\n"):
            raise ValueError("A single-line value is required")
        return value.strip()
    return value


Name = Annotated[str, BeforeValidator(_single_line), Field(min_length=1, max_length=160)]
MinuteTarget = Annotated[StrictInt, Field(ge=1, le=525600)]
Approach = Annotated[StrictInt, Field(ge=0, le=525600)]
Version = Annotated[StrictInt, Field(ge=1, le=2147483647)]
PauseState = Literal["pending_customer", "pending_third_party"]


def _timezone(value: object) -> object:
    # Syntax only: installed lookup belongs after protected replay in the owner.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_+/-]{1,100}", value):
        raise ValueError("An IANA timezone name is required")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("An IANA timezone name is required")
    return value


Timezone = Annotated[str, BeforeValidator(_timezone), Field(max_length=100)]


class WeeklyWindow(StrictModel):
    weekday: Annotated[StrictInt, Field(ge=0, le=6)]
    start_minute: Annotated[StrictInt, Field(ge=0, le=1439)]
    end_minute: Annotated[StrictInt, Field(ge=1, le=1440)]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start_minute >= self.end_minute:
            raise ValueError("Window opening must precede closing")
        return self


def _date(value: object) -> object:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("A civil YYYY-MM-DD date is required")
    return date.fromisoformat(value).isoformat()


class Holiday(StrictModel):
    date: Annotated[str, BeforeValidator(_date)]
    label: Name | None = None


def _windows(values: list[WeeklyWindow]) -> list[WeeklyWindow]:
    return [
        WeeklyWindow(weekday=w.weekday, start_minute=w.start_minute, end_minute=w.end_minute)
        for w in canonical_windows([Window(**value.model_dump()) for value in values])
    ]


def _holidays(values: list[Holiday]) -> list[Holiday]:
    if len({value.date for value in values}) != len(values):
        raise ValueError("Holiday dates cannot repeat")
    return sorted(values, key=lambda value: value.date)


Windows = Annotated[list[WeeklyWindow], Field(min_length=1, max_length=28)]
Holidays = Annotated[list[Holiday], Field(max_length=1000)]
Pauses = Annotated[list[PauseState], Field(max_length=2)]


class CalendarCreate(StrictModel):
    client_id: UUID
    name: Name
    active: StrictBool
    timezone: Timezone
    windows: Windows
    holidays: Holidays

    @field_validator("windows")
    @classmethod
    def valid_windows(cls, values: list[WeeklyWindow]) -> list[WeeklyWindow]:
        return _windows(values)

    @field_validator("holidays")
    @classmethod
    def valid_holidays(cls, values: list[Holiday]) -> list[Holiday]:
        return _holidays(values)


class CalendarPatch(StrictModel):
    name: Name | None = None
    active: StrictBool | None = None
    timezone: Timezone | None = None
    windows: Windows | None = None
    holidays: Holidays | None = None

    @model_validator(mode="after")
    def complete_patch(self) -> Self:
        _nonempty(self)
        if self.windows is not None:
            self.windows = _windows(self.windows)
        if self.holidays is not None:
            self.holidays = _holidays(self.holidays)
        return self


def _nonempty(value: StrictModel) -> None:
    if not value.model_fields_set or any(
        getattr(value, name) is None for name in value.model_fields_set
    ):
        raise ValueError("A nonempty, non-null patch is required")


def _pauses(values: list[PauseState]) -> list[PauseState]:
    if len(values) != len(set(values)):
        raise ValueError("Pause states cannot repeat")
    return sorted(values)


class PolicyCreate(StrictModel):
    client_id: UUID
    category_id: UUID | None = None
    priority: Priority | None = None
    name: Name
    calendar_id: UUID
    calendar_version: Version
    first_response_minutes: MinuteTarget
    resolution_minutes: MinuteTarget
    approach_minutes: Approach
    pause_states: Pauses

    @field_validator("pause_states")
    @classmethod
    def valid_pauses(cls, values: list[PauseState]) -> list[PauseState]:
        return _pauses(values)


class PolicyPatch(StrictModel):
    name: Name | None = None
    enabled: StrictBool | None = None
    calendar_id: UUID | None = None
    calendar_version: Version | None = None
    first_response_minutes: MinuteTarget | None = None
    resolution_minutes: MinuteTarget | None = None
    approach_minutes: Approach | None = None
    pause_states: Pauses | None = None

    @model_validator(mode="after")
    def complete_patch(self) -> Self:
        _nonempty(self)
        if (self.calendar_id is None) != (self.calendar_version is None):
            raise ValueError("Calendar identity and reviewed revision must be submitted together")
        if self.pause_states is not None:
            self.pause_states = _pauses(self.pause_states)
        return self


class SlaConfigurationQuery(StrictModel):
    client_id: UUID
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=200)


class CalendarReceipt(StrictModel):
    queue_id: UUID
    client_id: UUID
    calendar_id: UUID


class PolicyReceipt(StrictModel):
    queue_id: UUID
    client_id: UUID
    policy_id: UUID


class CalendarSummary(StrictModel):
    id: UUID
    client_id: UUID
    queue_id: UUID
    version: int
    queue_version: int
    name: str
    active: bool
    timezone: str
    can_edit: bool
    created_at: datetime
    updated_at: datetime


class CalendarOutput(CalendarSummary):
    windows: list[WeeklyWindow]
    holidays: list[Holiday]
    tzif_sha256: str


class PolicyOutput(StrictModel):
    id: UUID
    client_id: UUID
    queue_id: UUID
    category_id: UUID | None
    priority: Priority | None
    version: int
    queue_version: int
    enabled: bool
    name: str
    calendar_id: UUID
    calendar_version: int
    first_response_minutes: int
    resolution_minutes: int
    approach_minutes: int
    pause_states: list[PauseState]
    authorizer_id: UUID
    can_edit: bool
    created_at: datetime
    updated_at: datetime


class CalendarPage(StrictModel):
    items: list[CalendarSummary]
    next_cursor: str | None


class PolicyPage(StrictModel):
    items: list[PolicyOutput]
    next_cursor: str | None


GoalStatus = Literal[
    "evaluating", "running", "paused", "approaching", "fulfilled", "unfulfilled", "breached"
]
CycleState = Literal["unconfigured", "evaluating", "ready", "stale", "unavailable"]


class SlaGoalOutput(StrictModel):
    status: GoalStatus
    target_minutes: int
    elapsed_business_seconds: int
    remaining_business_seconds: int
    due_at: datetime | None
    fulfilled_at: datetime | None
    breached_at: datetime | None
    corrected: bool


class SlaCycleOutput(StrictModel):
    number: int
    start_at: datetime
    end_at: datetime | None
    initial_category_id: UUID | None
    initial_priority: Priority
    policy_name: str | None
    policy_version: int | None
    calendar_name: str | None
    calendar_version: int | None
    timezone: str | None
    state: CycleState
    computed_through_at: datetime | None
    evaluated_at: datetime | None
    safe_error: (
        Literal[
            "timing_inconsistent", "calculation_unavailable", "source_invalid", "processing_failed"
        ]
        | None
    )
    first_response: SlaGoalOutput | None
    resolution: SlaGoalOutput | None


class SlaCyclePage(StrictModel):
    current: SlaCycleOutput | None
    history: list[SlaCycleOutput]
    next_cursor: str | None
    observed_at: datetime


class SlaCycleQuery(StrictModel):
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=300)
