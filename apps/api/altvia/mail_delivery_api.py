"""Ticket-scoped, reviewed and replay-protected public delivery requests."""

from contextlib import ExitStack
from threading import BoundedSemaphore
from typing import NamedTuple
from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from altvia import attachment_links, identity, tickets
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    _expected_version,
    _operation,
    _remember,
    authenticate_request,
)
from altvia.attachment_api import unavailable
from altvia.config import Settings
from altvia.file_storage import S3Store, StorageError
from altvia.file_storage_owner import load_storage
from altvia.mail_delivery import MAX_MIME_BYTES, PublicFile, choices, freeze
from altvia.mail_delivery_schemas import (
    DeliveryChoices,
    DeliveryCreate,
    DeliveryOutput,
    DeliveryReceipt,
)
from altvia.models import (
    Attachment,
    MailSender,
    OutboundMessage,
    Ticket,
    TicketMessage,
    TicketParticipant,
    User,
)
from altvia.ticket_api import _collection, _event

_PREPARATIONS = BoundedSemaphore(1)


class DeliveryContext(NamedTuple):
    actor: User
    item: Ticket
    message: TicketMessage
    sender: MailSender
    participant: TicketParticipant
    files: list[Attachment]
    key: str
    fingerprint: str


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
        route = f"ticket-delivery:{identifier}:{message_id}"

        def checked(db: Session) -> DeliveryContext | DeliveryReceipt:
            actor = authenticate_request(db, request, settings, write=True)
            item, access = tickets.scoped_ticket(db, actor.id, identifier, write=True)
            message = message_parent(db, identifier, message_id)
            tickets.require_update(item, access, actor.id)
            version = _expected_version(request)
            key, fingerprint, saved = _operation(
                db, actor, request, route, attachment_links.intent(body)
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
            ids = [file.id for file in message.attachments]
            if body.attachment_ids != ids:
                raise identity.IdentityError(409, "delivery_attachment_review_required")
            files = attachment_links.locked(db, "ticket", identifier, "public", ids)
            if sum(file.bytes for file in files) > MAX_MIME_BYTES:
                raise identity.IdentityError(409, "delivery_content_ineligible")
            sender = db.get(MailSender, body.source_id)
            participant = db.get(TicketParticipant, body.participant_id)
            assert sender is not None and participant is not None
            return DeliveryContext(
                actor, item, message, sender, participant, files, key, fingerprint
            )

        def publish(
            db: Session,
            context: DeliveryContext,
            files: list[PublicFile],
        ) -> DeliveryReceipt:
            actor, item, message, sender, participant, _, key, fingerprint = context
            try:
                row = freeze(db, item, message, sender, participant, actor.id, files)
            except ValueError:
                raise identity.IdentityError(409, "delivery_content_ineligible") from None
            tickets.advance(item)
            _event(
                db,
                actor,
                item,
                request,
                "delivery_queued",
                now=row.created_at,
                message_id=str(message_id),
                delivery_id=str(row.id),
            )
            receipt = DeliveryReceipt(
                ticket_id=identifier, message_id=message_id, delivery_id=row.id
            )
            _remember(db, actor, route, key, fingerprint, receipt, 201)
            return receipt

        # The first transaction checks current authority and protected replay BEFORE storage.
        with Session(engine) as db, db.begin():
            context = checked(db)
            if isinstance(context, DeliveryReceipt):
                return context
            if not context.files:
                return publish(db, context, [])
            snapshots = [
                (f.id, f.object_key, f.bytes, f.sha256, f.filename, f.media_type)
                for f in context.files
            ]
        if not _PREPARATIONS.acquire(blocking=False):
            raise unavailable()
        try:
            with ExitStack() as stack:
                if settings.storage_file is None:
                    raise unavailable()
                try:
                    store = S3Store(load_storage(settings.storage_file))
                except ValueError:
                    raise unavailable() from None
                stack.callback(store.close)
                prepared = []
                for file_id, object_key, size, digest, filename, media_type in snapshots:
                    source = stack.enter_context(
                        store.verified_spool(object_key, size=size, sha256=digest)
                    )
                    prepared.append(PublicFile(file_id, filename, media_type, source.read()))
                # No S3 operation or private spool read occurs under a database transaction.
                with Session(engine) as db, db.begin():
                    context = checked(db)
                    if isinstance(context, DeliveryReceipt):
                        return context
                    current = [
                        (f.id, f.object_key, f.bytes, f.sha256, f.filename, f.media_type)
                        for f in context.files
                    ]
                    if current != snapshots:
                        raise identity.IdentityError(409, "delivery_attachment_review_required")
                    return publish(db, context, prepared)
        except StorageError:
            raise unavailable() from None
        finally:
            _PREPARATIONS.release()

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
