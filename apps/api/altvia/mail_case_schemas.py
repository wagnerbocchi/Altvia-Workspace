"""Published mail case read contracts; no provenance or routing identifiers."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool

from altvia.ticket_schemas import Status, StrictModel, Subject, TicketMessageOutput, _text
from altvia.work_schemas import Priority

CaseState = Literal["ready", "promoted", "collision", "revoked"]


class CaseFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=600)
    queue_id: UUID | None = None
    client_id: UUID | None = None
    state: CaseState | None = None


class CaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    queue_id: UUID
    queue_name: str
    client_id: UUID
    client_name: str
    contact_id: UUID
    contact_name: str
    subject: str
    received_at: datetime
    created_at: datetime
    state: CaseState
    version: int


class CaseDetail(CaseSummary):
    email_snapshot: str
    body_text: str
    can_create: bool
    can_append: bool
    candidate_ticket_id: UUID | None
    candidate_ticket_number: str | None
    candidate_ticket_version: int | None
    candidate_ticket_status: Status | None
    candidate_can_reopen: bool
    promotion_receipt: "PromotionReceipt | None" = None


class CasePage(BaseModel):
    items: list[CaseSummary]
    next_cursor: str | None


class PromotionCreate(StrictModel):
    action: Literal["create"]
    subject: Subject
    priority: Priority
    category_id: UUID | None = None
    assignee_id: UUID | None = None


class PromotionAppend(StrictModel):
    action: Literal["append"]
    ticket_id: UUID
    ticket_version: int = Field(gt=0, le=2147483647, strict=True)
    reopen: StrictBool
    reopen_reason: Annotated[str, BeforeValidator(_text), Field(max_length=2000)] | None = None


PromotionIntent = Annotated[PromotionCreate | PromotionAppend, Field(discriminator="action")]


class PromotionReceipt(StrictModel):
    case_id: UUID
    ticket_id: UUID
    incoming_message_id: UUID


class IncomingMessageOutput(StrictModel):
    kind: Literal["incoming"] = "incoming"
    id: UUID
    case_id: UUID
    ticket_id: UUID
    ticket_version: int
    actor_id: UUID
    contact_name: str
    email_snapshot: str
    subject: str
    body_text: str
    received_at: datetime
    recorded_at: datetime
    invalidation_warning: Literal["incoming_attestation_invalidated"] | None


class OutboundConversationOutput(StrictModel):
    kind: Literal["outbound"] = "outbound"
    ticket_version: int
    message: TicketMessageOutput


ConversationRecord = Annotated[
    IncomingMessageOutput | OutboundConversationOutput, Field(discriminator="kind")
]


class ConversationPage(StrictModel):
    items: list[ConversationRecord]
    next_cursor: str | None
