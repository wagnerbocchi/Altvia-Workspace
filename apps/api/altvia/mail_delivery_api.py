"""Ticket-scoped, reviewed and replay-protected public delivery requests."""

from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from altvia import identity, tickets
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    _expected_version,
    _operation,
    _remember,
    authenticate_request,
)
from altvia.config import Settings
from altvia.mail_delivery import choices, freeze
from altvia.mail_delivery_schemas import (
    DeliveryChoices,
    DeliveryCreate,
    DeliveryOutput,
    DeliveryReceipt,
)
from altvia.models import MailSender, OutboundMessage, TicketMessage, TicketParticipant
from altvia.ticket_api import _collection, _event


def message_parent(db: Session, ticket_id: UUID, message_id: UUID) -> TicketMessage:
    row = db.scalar(
        select(TicketMessage).where(
            TicketMessage.id == message_id, TicketMessage.ticket_id == ticket_id
        )
    )
    if row is None:
        raise identity.IdentityError(404, "not_found")
    return row


def create_mail_delivery_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["mail-delivery"])

    @router.get("/tickets/{identifier}/delivery-choices", response_model=DeliveryChoices)
    def delivery_choices(identifier: UUID, request: Request) -> DeliveryChoices:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            item, access = tickets.scoped_ticket(db, actor.id, identifier)
            _collection(request)
            return choices(db, item, access, actor.id)

    @router.post(
        "/tickets/{identifier}/messages/{message_id}/delivery",
        response_model=DeliveryReceipt,
        status_code=201,
        responses={200: {"model": DeliveryReceipt}},
        openapi_extra={"parameters": [IF_MATCH, IDEMPOTENCY_KEY]},
    )
    def queue_delivery(
        identifier: UUID,
        message_id: UUID,
        body: DeliveryCreate,
        request: Request,
        response: Response,
    ) -> DeliveryReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            item, access = tickets.scoped_ticket(db, actor.id, identifier, write=True)
            message = message_parent(db, identifier, message_id)
            tickets.require_update(item, access, actor.id)
            version = _expected_version(request)
            route = f"ticket-delivery:{identifier}:{message_id}"
            key, fingerprint, saved = _operation(
                db, actor, request, route, body.model_dump(mode="json")
            )
            if saved is not None:
                response.status_code = 200
                return DeliveryReceipt.model_validate(saved.result)
            if item.version != version:
                raise identity.IdentityError(409, "version_conflict")
            tickets.require_active(access, item)
            selected = choices(db, item, access, actor.id)
            if (
                not selected.can_send
                or selected.sender is None
                or selected.participant is None
                or selected.sender.source_id != body.source_id
                or selected.participant.participant_id != body.participant_id
            ):
                raise identity.IdentityError(409, "delivery_ineligible")
            if db.scalar(
                select(OutboundMessage.id).where(OutboundMessage.message_id == message_id)
            ):
                raise identity.IdentityError(409, "delivery_exists")
            sender = db.get(MailSender, body.source_id)
            participant = db.get(TicketParticipant, body.participant_id)
            assert sender is not None and participant is not None
            try:
                row = freeze(db, item, message, sender, participant, actor.id)
            except ValueError:
                raise identity.IdentityError(409, "delivery_content_ineligible") from None
            tickets.advance(item)
            _event(
                db,
                actor,
                item,
                request,
                "delivery_queued",
                message_id=str(message_id),
                delivery_id=str(row.id),
            )
            receipt = DeliveryReceipt(
                ticket_id=identifier, message_id=message_id, delivery_id=row.id
            )
            _remember(db, actor, route, key, fingerprint, receipt, 201)
            return receipt

    @router.get(
        "/tickets/{identifier}/messages/{message_id}/delivery", response_model=DeliveryOutput
    )
    def delivery(identifier: UUID, message_id: UUID, request: Request) -> DeliveryOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            tickets.scoped_ticket(db, actor.id, identifier)
            message_parent(db, identifier, message_id)
            _collection(request)
            row = db.scalar(
                select(OutboundMessage).where(
                    OutboundMessage.message_id == message_id,
                    OutboundMessage.ticket_id == identifier,
                )
            )
            if row is None:
                raise identity.IdentityError(404, "not_found")
            return DeliveryOutput(
                ticket_id=identifier,
                message_id=message_id,
                delivery_id=row.id,
                state=row.state,
                attempts=row.attempts,
                last_error_code=row.last_error_code,
                smtp_message_id=row.smtp_message_id,
                accepted_at=row.accepted_at,
            )

    return router
