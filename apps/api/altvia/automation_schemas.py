"""Finite assignment rule contracts; no expressions or caller-owned action IDs."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, StrictBool, field_validator, model_validator

from altvia.work_schemas import Priority, StrictModel, Title

AssignmentStatus = Literal["new", "open", "pending_customer", "pending_third_party", "resolved"]
ExecutionState = Literal[
    "pending", "processing", "succeeded", "triage", "superseded", "cancelled", "dead"
]
ExecutionError = Literal[
    "authorization_lost",
    "project_unavailable",
    "assignee_unavailable",
    "ticket_state_changed",
    "existing_work_needs_review",
    "invalid_event",
    "unsupported_event",
    "broker_unavailable",
    "processing_failed",
    "attempts_exhausted",
    "rule_disabled",
    "source_superseded",
    "lease_expired",
]


class RuleCreate(StrictModel):
    client_id: UUID
    title: Title
    priority: Priority
    ticket_statuses: list[AssignmentStatus] = Field(min_length=1, max_length=5)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Invalid title")
        return value

    @field_validator("ticket_statuses")
    @classmethod
    def canonical_statuses(cls, values: list[AssignmentStatus]) -> list[AssignmentStatus]:
        if len(values) != len(set(values)):
            raise ValueError("Duplicate status")
        return sorted(values)


class RulePatch(StrictModel):
    enabled: StrictBool | None = None
    title: Title | None = None
    priority: Priority | None = None
    ticket_statuses: list[AssignmentStatus] | None = Field(default=None, min_length=1, max_length=5)

    @model_validator(mode="after")
    def complete_patch(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set
        ):
            raise ValueError("A nonempty, non-null patch is required")
        if self.title is not None:
            RuleCreate.valid_title(self.title)
        if self.ticket_statuses is not None:
            self.ticket_statuses = RuleCreate.canonical_statuses(self.ticket_statuses)
        return self


class RuleListQuery(StrictModel):
    client_id: UUID
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=200)


class RuleReceipt(StrictModel):
    queue_id: UUID
    client_id: UUID
    rule_id: UUID


class RuleOutput(StrictModel):
    id: UUID
    queue_id: UUID
    client_id: UUID
    action_id: UUID
    version: int
    queue_version: int
    enabled: bool
    title: str
    priority: Priority
    ticket_statuses: list[AssignmentStatus]
    authorizer_id: UUID
    cancelled_through_version: int
    created_at: datetime
    updated_at: datetime


class RulePage(StrictModel):
    items: list[RuleOutput]
    next_cursor: str | None


class ExecutionEffect(StrictModel):
    work_item_id: UUID
    project_id: UUID
    mode: Literal["created", "adopted"]


class ExecutionOutput(StrictModel):
    id: UUID
    rule_id: UUID
    action_id: UUID
    rule_version: int
    source_event_id: UUID
    state: ExecutionState
    attempts: int
    error_code: ExecutionError | None
    created_at: datetime
    updated_at: datetime
    version: int
    can_retry: bool
    effect: ExecutionEffect | None


class ExecutionPage(StrictModel):
    items: list[ExecutionOutput]
    next_cursor: str | None


class ExecutionReceipt(StrictModel):
    execution_id: UUID
