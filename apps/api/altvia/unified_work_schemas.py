"""Independent ticket/task summaries; the legacy task-only contract is unchanged."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator

from altvia.ticket_schemas import Status as TicketStatus
from altvia.ticket_schemas import Subject, TicketNumber
from altvia.work_schemas import MyWorkItem, Priority
from altvia.work_schemas import Status as WorkStatus

Kind = Literal["ticket", "work_item"]


class UnifiedWorkFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=512)
    kind: Literal["all", "work_item", "ticket"] = "all"
    priority: Priority | None = None
    client_id: UUID | None = None
    team_id: UUID | None = None
    work_status: WorkStatus | None = None
    ticket_status: TicketStatus | None = None
    q: str | None = Field(default=None, max_length=200)

    @field_validator("q", mode="before")
    @classmethod
    def search_text(cls, value: object) -> object:
        if isinstance(value, str):
            if "\0" in value:
                raise ValueError("NUL is not supported")
            return value.strip() or None
        return value


class LinkedTicketBadge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    number: TicketNumber
    subject: Subject
    status: TicketStatus
    priority: Priority


class UnifiedWorkItem(MyWorkItem):
    kind: Literal["work_item"] = Field(...)
    created_at: AwareDatetime
    linked_tickets: list[LinkedTicketBadge] = Field(max_length=3)
    has_more_linked_tickets: StrictBool


class UnifiedTicket(LinkedTicketBadge):
    kind: Literal["ticket"] = Field(...)
    client_id: UUID
    queue_id: UUID
    queue_name: str
    created_at: AwareDatetime


class UnifiedWorkPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Annotated[UnifiedWorkItem | UnifiedTicket, Field(discriminator="kind")]]
    next_cursor: str | None
    as_of: AwareDatetime
