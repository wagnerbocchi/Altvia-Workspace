"""Current management reports with explicit clocks and reconciled native counts."""

import re
from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from altvia.work_schemas import Priority, StrictModel

Count = Annotated[StrictInt, Field(ge=0)]


class AnalyticsFilters(StrictModel):
    reference_at: AwareDatetime
    due_through: AwareDatetime
    timezone: str = Field(min_length=1, max_length=100)
    priority: Priority | None = None
    client_id: UUID | None = None
    team_id: UUID | None = None
    project_id: UUID | None = None
    responsible_id: UUID | None = None
    unassigned: bool = False
    created_from: AwareDatetime | None = None
    created_before: AwareDatetime | None = None

    @field_validator("reference_at", "due_through", "created_from", "created_before", mode="before")
    @classmethod
    def iso_instant(cls, value: object) -> object:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}[Tt]", value):
            return value
        raise ValueError("An aware ISO instant is required")

    @field_validator("reference_at", "due_through", "created_from", "created_before")
    @classmethod
    def utc_instant(cls, value: datetime | None) -> datetime | None:
        try:
            return value.astimezone(UTC) if value is not None else None
        except (ValueError, OverflowError):
            raise ValueError("The UTC instant cannot be represented") from None

    @field_validator("timezone")
    @classmethod
    def timezone_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_+/-]{1,100}", value):
            raise ValueError("An installed timezone name is required")
        return value

    @model_validator(mode="after")
    def valid_ranges(self) -> Self:
        if self.reference_at >= self.due_through:
            raise ValueError("reference_at must precede due_through")
        if (self.created_from is None) != (self.created_before is None):
            raise ValueError("Both creation-period bounds are required")
        if self.created_from is not None and self.created_before is not None:
            if self.created_from >= self.created_before:
                raise ValueError("created_from must precede created_before")
        if self.unassigned and self.responsible_id is not None:
            raise ValueError("Choose a responsible person or unassigned")
        return self


class ActiveWorkCounts(StrictModel):
    active_work_item_count: Count
    active_ticket_count: Count
    blocked_work_item_count: Count
    ongoing_work_item_count: Count
    active_no_due_date_count: Count
    overdue_work_item_count: Count
    due_soon_work_item_count: Count
    later_due_work_item_count: Count


class WorkloadFilters(AnalyticsFilters):
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=320)


class ScopeFilters(StrictModel):
    kind: Literal["client", "project", "team", "responsible"]
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=320)


class AnalyticsWorkloadRow(ActiveWorkCounts):
    user_id: UUID | None
    name: str | None = Field(min_length=1, max_length=150)

    @model_validator(mode="after")
    def paired_principal(self) -> Self:
        if (self.user_id is None) != (self.name is None):
            raise ValueError("Principal identity and label must be paired")
        return self


class AnalyticsScope(StrictModel):
    id: UUID
    name: str = Field(min_length=1, max_length=150)


class AnalyticsScopePage(StrictModel):
    items: list[AnalyticsScope]
    next_cursor: str | None


class WorkStatusCounts(StrictModel):
    todo: Count
    in_progress: Count
    blocked: Count
    done: Count
    cancelled: Count


class TicketStatusCounts(StrictModel):
    new: Count
    open: Count
    pending_customer: Count
    pending_third_party: Count
    resolved: Count
    closed: Count


class PriorityCounts(StrictModel):
    low: Count
    medium: Count
    high: Count
    critical: Count


class AnalyticsOverview(ActiveWorkCounts):
    observed_at: AwareDatetime
    filters: AnalyticsFilters
    work_item_count: Count
    ticket_count: Count
    represented_ticket_count: Count
    standalone_ticket_count: Count
    unified_count: Count
    active_unified_count: Count
    all_missing_deadline_count: Count
    unassigned_work_item_count: Count
    unassigned_ticket_count: Count
    pending_customer_ticket_count: Count
    pending_third_party_ticket_count: Count
    sla_legacy_ticket_count: Count
    sla_unconfigured_ticket_count: Count
    sla_configured_ticket_count: Count
    sla_recorded_breach_ticket_count: Count
    sla_corrected_ticket_count: Count
    sla_last_observation_at: AwareDatetime | None
    work_status_counts: WorkStatusCounts
    ticket_status_counts: TicketStatusCounts
    work_priority_counts: PriorityCounts
    ticket_priority_counts: PriorityCounts


class AnalyticsWorkloadPage(StrictModel):
    items: list[AnalyticsWorkloadRow]
    next_cursor: str | None
    overview: AnalyticsOverview
