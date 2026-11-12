"""Scoped classified projection reads and redacted private event validation."""

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, and_, select

from altvia.models import (
    Client,
    ClientAccessGrant,
    MailTriageCase,
    OutboxEvent,
    RoleBinding,
    TicketQueue,
)
from altvia.queue_registry import QUEUE_ROLES

CASE_EVENTS = {
    "mail.case_published",
    "mail.case_aliased",
    "mail.case_collided",
    "mail.case_revoked",
}
READ_COLUMNS = {
    "id",
    "queue_id",
    "client_id",
    "contact_id",
    "contact_name",
    "email_snapshot",
    "subject",
    "body_text",
    "received_at",
    "created_at",
    "state",
    "version",
}
ROUTING_COLUMNS = {
    "message_id",
    "in_reply_to",
    "references_ids",
    "thread_token",
    "ticket_id",
    "incoming_message_id",
}


class CaseEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    actor_id: None
    actor_kind: Literal["management_command", "source_capture"]
    case_id: UUID
    source_id: UUID
    state: Literal["ready", "promoted", "collision", "revoked"]


def validate_case_event(event: OutboxEvent) -> None:
    payload = CaseEventPayload.model_validate(event.payload)
    expected = {
        "mail.case_published": "ready",
        "mail.case_aliased": "ready",
        "mail.case_collided": "collision",
        "mail.case_revoked": "revoked",
    }
    if (
        event.event_type not in CASE_EVENTS
        or event.aggregate_type != "mail_case"
        or event.aggregate_id != payload.case_id
        or (
            event.schema_version
            != (2 if event.event_type == "mail.case_aliased" and payload.state == "promoted" else 1)
        )
        or event.aggregate_version < 1
        or (
            payload.state != expected[event.event_type]
            and not (event.event_type == "mail.case_aliased" and payload.state == "promoted")
        )
        or payload.actor_kind == "source_capture"
        and event.event_type != "mail.case_collided"
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", event.correlation_id)
    ):
        raise ValueError("Invalid mail case event")


def visible(actor_id: UUID, *, detail: bool = False) -> Select[tuple[object, ...]]:
    columns = sorted(READ_COLUMNS - (set() if detail else {"body_text", "email_snapshot"}))
    return (
        select(
            *(getattr(MailTriageCase, name) for name in columns),
            Client.name.label("client_name"),
            TicketQueue.name.label("queue_name"),
        )
        .join(Client, Client.id == MailTriageCase.client_id)
        .join(TicketQueue, TicketQueue.id == MailTriageCase.queue_id)
        .join(
            RoleBinding,
            and_(
                RoleBinding.user_id == actor_id,
                RoleBinding.scope_kind == "queue",
                RoleBinding.queue_id == MailTriageCase.queue_id,
                RoleBinding.role_name.in_(QUEUE_ROLES),
            ),
        )
        .join(
            ClientAccessGrant,
            and_(
                ClientAccessGrant.user_id == actor_id,
                ClientAccessGrant.client_id == MailTriageCase.client_id,
            ),
        )
    )
