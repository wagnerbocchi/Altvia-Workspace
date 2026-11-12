"""Public delivery DTOs contain no frozen wire, evidence or configuration secrets."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from altvia.attachment_schemas import AttachmentSelection

DeliveryState = Literal["queued", "preparing", "transmitting", "accepted", "failed", "uncertain"]


class DeliveryCreate(AttachmentSelection):
    participant_id: UUID
    source_id: UUID


class SenderChoice(BaseModel):
    source_id: UUID
    from_email: str


class ParticipantChoice(BaseModel):
    participant_id: UUID
    email: str
    display_name: str


class DeliveryChoices(BaseModel):
    sender: SenderChoice | None
    participant: ParticipantChoice | None
    can_send: bool


class DeliveryReceipt(BaseModel):
    ticket_id: UUID
    message_id: UUID
    delivery_id: UUID


class DeliveryOutput(DeliveryReceipt):
    state: DeliveryState
    attempts: int
    last_error_code: str | None
    smtp_message_id: str
    accepted_at: datetime | None
