"""Bounded summaries and reviewed preconditions for explicit relationships."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from altvia.admin_http import IF_MATCH
from altvia.ticket_schemas import Status as TicketStatus
from altvia.work_schemas import Priority
from altvia.work_schemas import Status as WorkStatus

IF_MATCH_WORK_ITEM = {**IF_MATCH, "name": "If-Match-Work-Item"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class TicketWorkCreate(StrictModel):
    work_item_id: UUID


class TicketWorkReceipt(StrictModel):
    ticket_id: UUID
    work_item_id: UUID


class TicketWorkListQuery(StrictModel):
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=250)


class TicketWorkChoicesQuery(TicketWorkListQuery):
    project_id: UUID | None = None
    q: (
        Annotated[
            str,
            BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v),
            Field(max_length=200),
        ]
        | None
    ) = None


class WorkLinkChoice(StrictModel):
    work_item_id: UUID
    project_id: UUID
    project_name: str
    title: str
    status: WorkStatus
    priority: Priority
    version: int = Field(ge=1)


class LinkedWork(WorkLinkChoice):
    can_unlink: bool


class LinkedTicket(StrictModel):
    ticket_id: UUID
    number: str = Field(pattern=r"^[1-9][0-9]*$")
    subject: str
    status: TicketStatus
    priority: Priority
    version: int = Field(ge=1)
    can_unlink: bool


class TicketWorkPage(StrictModel):
    items: list[LinkedWork]
    next_cursor: str | None
    can_link: bool


class WorkTicketPage(StrictModel):
    items: list[LinkedTicket]
    next_cursor: str | None


class TicketWorkChoices(StrictModel):
    items: list[WorkLinkChoice]
    next_cursor: str | None
    can_link: bool
