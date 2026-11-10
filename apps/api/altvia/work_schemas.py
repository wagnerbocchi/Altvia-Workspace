"""Strict work-item contracts; state is changed only through explicit transitions."""

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from altvia.deadlines import DateDue as DateDue
from altvia.deadlines import Due as Due
from altvia.deadlines import InstantDue as InstantDue

Status = Literal["todo", "in_progress", "blocked", "done", "cancelled"]
Priority = Literal["low", "medium", "high", "critical"]
WORK_TRANSITIONS = {
    "todo": {"in_progress", "blocked", "cancelled"},
    "in_progress": {"blocked", "done", "cancelled"},
    "blocked": {"todo", "in_progress", "cancelled"},
    "done": {"in_progress"},
    "cancelled": {"todo"},
}
Title = Annotated[
    str,
    BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v),
    Field(min_length=1, max_length=300),
]
ExternalLabel = Annotated[
    str,
    BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v),
    Field(min_length=1, max_length=150),
]


def external_labels(values: list[str]) -> list[str]:
    if len(values) != len(set(values)) or any(
        any(character in value for character in "\x00\r\n") for value in values
    ):
        raise ValueError("Duplicate or invalid external participant")
    return values


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkCreate(StrictModel):
    project_id: UUID
    title: Title
    priority: Priority
    work_type: Literal["one_off", "ongoing"]
    description: str = Field(default="", max_length=20000)
    parent_id: UUID | None = None
    owner_id: UUID | None = None
    assignee_ids: list[UUID] = Field(default_factory=list, max_length=50)
    external_participants: list[ExternalLabel] = Field(default_factory=list, max_length=50)
    due: Due | None = None
    estimated_minutes: Annotated[StrictInt, Field(ge=0, le=2147483647)] | None = None

    @field_validator("assignee_ids")
    @classmethod
    def unique_assignees(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate participant")
        return value

    _external_labels = field_validator("external_participants")(external_labels)


class WorkPatch(StrictModel):
    title: Title | None = None
    description: str | None = Field(default=None, max_length=20000)
    priority: Priority | None = None
    parent_id: UUID | None = None
    owner_id: UUID | None = None
    assignee_ids: list[UUID] | None = Field(default=None, max_length=50)
    external_participants: list[ExternalLabel] | None = Field(default=None, max_length=50)
    due: Due | None = None
    estimated_minutes: Annotated[StrictInt, Field(ge=0, le=2147483647)] | None = None

    @model_validator(mode="after")
    def valid_patch(self) -> "WorkPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        for key in {
            "title",
            "description",
            "priority",
            "assignee_ids",
            "external_participants",
        } & self.model_fields_set:
            if getattr(self, key) is None:
                raise ValueError("A non-null value is required")
        if self.assignee_ids is not None:
            WorkCreate.unique_assignees(self.assignee_ids)
        if self.external_participants is not None:
            external_labels(self.external_participants)
        return self


class Transition(StrictModel):
    target_status: Status
    reason: str | None = Field(default=None, max_length=2000)
    end_operation: StrictBool = False


class CommentCreate(StrictModel):
    body: Annotated[
        str,
        BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v),
        Field(min_length=1, max_length=10000),
    ]


class WorkReceipt(StrictModel):
    work_item_id: UUID
    project_id: UUID


class WorkOutput(StrictModel):
    id: UUID
    project_id: UUID
    parent_id: UUID | None
    owner_id: UUID | None
    owner_name: str | None
    assignees: list["Candidate"]
    assignee_ids: list[UUID]
    external_participants: list[str] = Field(default_factory=list)
    title: str
    description: str
    priority: Priority
    work_type: Literal["one_off", "ongoing"]
    status: Status
    blocked_reason: str | None
    due: Due | None
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    estimated_minutes: int | None
    version: int
    created_at: datetime
    updated_at: datetime
    can_update: bool
    can_manage: bool
    can_comment: bool
    project_writable: bool


class WorkPage(StrictModel):
    items: list[WorkOutput]
    next_cursor: str | None
    can_create: bool
    can_manage: bool
    project_writable: bool


class WorkFilters(StrictModel):
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=250)
    status: Status | None = None
    priority: Priority | None = None
    work_type: Literal["one_off", "ongoing"] | None = None
    owner_id: UUID | None = None
    involved_user_id: UUID | None = None
    unassigned: bool = False
    due_presence: Literal["dated", "undated"] | None = None
    due_from: AwareDatetime | None = None
    due_before: AwareDatetime | None = None
    q: (
        Annotated[
            str,
            BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v),
            Field(max_length=200),
        ]
        | None
    ) = None

    @field_validator("due_from", "due_before", mode="before")
    @classmethod
    def iso_range(cls, value: object) -> object:
        if isinstance(value, str) and not re.match(r"^\d{4}-\d{2}-\d{2}[Tt ]", value):
            raise ValueError("Use an aware ISO timestamp")
        return value

    @model_validator(mode="after")
    def valid_range(self) -> "WorkFilters":
        if self.due_from and self.due_before and self.due_from >= self.due_before:
            raise ValueError("due_from must precede due_before")
        return self


class ProjectWorkFilters(WorkFilters):
    project_id: UUID


class MyWorkFilters(WorkFilters):
    project_id: UUID | None = None
    client_id: UUID | None = None
    team_id: UUID | None = None


class MyWorkItem(StrictModel):
    kind: Literal["work_item"] = "work_item"
    id: UUID
    project_id: UUID
    project_name: str
    title: str
    status: Status
    priority: Priority
    work_type: Literal["one_off", "ongoing"]
    due: Due | None
    due_at: datetime | None


class MyWorkPage(StrictModel):
    items: list[MyWorkItem]
    next_cursor: str | None
    as_of: datetime


class Candidate(StrictModel):
    id: UUID
    display_name: str


class CandidatePage(StrictModel):
    items: list[Candidate]
    next_cursor: str | None


class CommentOutput(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    work_item_id: UUID
    author_id: UUID
    body: str
    created_at: datetime


class CommentPage(StrictModel):
    items: list[CommentOutput]
    next_cursor: str | None


class StateOutput(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    actor_id: UUID
    from_status: Status | None
    to_status: Status
    reason: str | None
    version: int
    occurred_at: datetime


class StatePage(StrictModel):
    items: list[StateOutput]
    next_cursor: str | None
