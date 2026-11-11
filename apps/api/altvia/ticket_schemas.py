"""Manual ticket contracts and their independent lifecycle."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from altvia.work_schemas import Candidate, Priority

Status = Literal["new", "open", "pending_customer", "pending_third_party", "resolved", "closed"]
TICKET_TRANSITIONS = {
    "new": {"open"},
    "open": {"pending_customer", "pending_third_party", "resolved"},
    "pending_customer": {"open", "resolved"},
    "pending_third_party": {"open", "resolved"},
    "resolved": {"closed", "open"},
    "closed": {"open"},
}


def _text(value: object) -> object:
    if isinstance(value, str) and "\0" in value:
        raise ValueError("NUL is not supported")
    return value


def _subject(value: object) -> object:
    value = _text(value)
    if isinstance(value, str):
        value = value.strip()
        if "\r" in value or "\n" in value:
            raise ValueError("A single-line subject is required")
    return value


Subject = Annotated[str, BeforeValidator(_subject), Field(min_length=1, max_length=300)]
Description = Annotated[str, BeforeValidator(_text), Field(max_length=20000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TicketCreate(StrictModel):
    client_id: UUID
    queue_id: UUID
    requester_id: UUID
    subject: Subject
    description: Description = ""
    priority: Priority
    category_id: UUID | None = None
    assignee_id: UUID | None = None


class TicketPatch(StrictModel):
    subject: Subject | None = None
    description: Description | None = None
    priority: Priority | None = None
    category_id: UUID | None = None
    assignee_id: UUID | None = None
    requester_id: UUID | None = None

    @model_validator(mode="after")
    def nonempty_patch(self) -> "TicketPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        for field in self.model_fields_set - {"category_id", "assignee_id"}:
            if getattr(self, field) is None:
                raise ValueError("A non-null value is required")
        return self


class TicketClaim(StrictModel):
    pass


class TicketTransition(StrictModel):
    target_status: Status
    reason: Annotated[str, BeforeValidator(_text), Field(max_length=2000)] | None = None

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class TicketReceipt(StrictModel):
    ticket_id: UUID


class TicketTransitionReceipt(TicketReceipt):
    history_id: UUID | None


class TicketNoteCreate(StrictModel):
    body_text: Annotated[str, BeforeValidator(_text), Field(min_length=1, max_length=10000)]

    @field_validator("body_text", mode="before")
    @classmethod
    def stripped_body(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TicketNoteReceipt(TicketReceipt):
    note_id: UUID


class TicketNoteOutput(StrictModel):
    id: UUID
    ticket_id: UUID
    author_id: UUID
    author_name: str
    body_text: str
    visibility: Literal["internal"] = "internal"
    ticket_version: int
    created_at: datetime


class TicketNotePage(StrictModel):
    items: list[TicketNoteOutput]
    next_cursor: str | None


class TicketOutput(StrictModel):
    id: UUID
    number: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")]
    client_id: UUID
    client_name: str
    queue_id: UUID
    queue_name: str
    requester_id: UUID
    requester_name: str
    requester_email: str
    requester_active: bool
    requester_verification: Literal["unverified"]
    category_id: UUID | None
    category_name: str | None
    assignee_id: UUID | None
    assignee_name: str | None
    subject: str
    description: str
    priority: Priority
    status: Status
    source: Literal["manual"]
    resolved_at: datetime | None
    closed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    writable: bool
    can_update: bool
    can_assign: bool
    can_claim: bool
    can_read_notes: bool
    can_add_note: bool
    allowed_transitions: list[Status]


class TicketFilters(StrictModel):
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=300)
    queue_id: UUID | None = None
    client_id: UUID | None = None
    status: Status | None = None
    priority: Priority | None = None
    assignee_id: UUID | None = None
    unassigned: bool = False
    q: (
        Annotated[
            str,
            BeforeValidator(_text),
            BeforeValidator(lambda value: value.strip() if isinstance(value, str) else value),
            Field(max_length=200),
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def consistent_assignment(self) -> "TicketFilters":
        if self.unassigned and self.assignee_id is not None:
            raise ValueError("Assignment filters conflict")
        return self


class TicketPage(StrictModel):
    items: list[TicketOutput]
    next_cursor: str | None
    can_create: bool


class TicketQueueChoice(StrictModel):
    id: UUID
    name: str
    active: bool
    can_create: bool
    can_assign: bool


class TicketQueueChoices(StrictModel):
    items: list[TicketQueueChoice]
    next_cursor: str | None
    can_create: bool


class TicketClientChoice(StrictModel):
    id: UUID
    name: str


class TicketClientChoices(StrictModel):
    items: list[TicketClientChoice]
    next_cursor: str | None


class RequesterChoice(Candidate):
    email: str
    verification_state: Literal["unverified"]


class RequesterPage(StrictModel):
    items: list[RequesterChoice]
    next_cursor: str | None


class TicketState(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    actor_id: UUID
    from_status: Status | None
    to_status: Status
    reason: str | None
    version: int
    occurred_at: datetime


class TicketStates(StrictModel):
    items: list[TicketState]
    next_cursor: str | None
