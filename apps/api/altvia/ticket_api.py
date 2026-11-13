"""Scoped manual ticket entry points and protected intent receipts."""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Engine, literal, select, tuple_, union_all
from sqlalchemy.orm import Session

from altvia import attachment_links, identity
from altvia import tickets as registry
from altvia.activity_api import ActivityPage, activity_page
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    _collection_query,
    _cursor,
    _etag,
    _expected_version,
    _next_cursor,
    _next_time_cursor,
    _operation,
    _remember,
    _time_cursor,
    authenticate_request,
)
from altvia.config import Settings
from altvia.mail_case_schemas import (
    ConversationPage,
    IncomingMessageOutput,
    OutboundConversationOutput,
)
from altvia.mail_promotion import incoming_output, incoming_outputs
from altvia.models import (
    ActivityEvent,
    Client,
    ClientContact,
    Ticket,
    TicketIncomingMessage,
    TicketMessage,
    TicketNote,
    TicketQueue,
    TicketStatusHistory,
    User,
)
from altvia.ticket_schemas import (
    RequesterChoice,
    RequesterPage,
    TicketClaim,
    TicketClientChoice,
    TicketClientChoices,
    TicketCreate,
    TicketFilters,
    TicketMessageCreate,
    TicketMessageOutput,
    TicketMessagePage,
    TicketMessageReceipt,
    TicketNoteCreate,
    TicketNoteOutput,
    TicketNotePage,
    TicketNoteReceipt,
    TicketOutput,
    TicketPage,
    TicketPatch,
    TicketQueueChoice,
    TicketQueueChoices,
    TicketReceipt,
    TicketState,
    TicketStates,
    TicketTransition,
    TicketTransitionReceipt,
)
from altvia.work_schemas import Candidate, CandidatePage


def _unique_query(request: Request) -> None:
    if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise identity.IdentityError(422, "repeated_query")


def _collection(request: Request) -> None:
    _unique_query(request)
    _collection_query(request)


def _scope(request: Request, filters: TicketFilters, actor_id: UUID) -> str:
    _unique_query(request)
    values = filters.model_dump(mode="json", exclude={"limit", "cursor"}, exclude_none=True)
    if not values.get("q"):
        values.pop("q", None)
    if not values.get("unassigned"):
        values.pop("unassigned", None)
    raw = json.dumps([str(actor_id), values], sort_keys=True, separators=(",", ":"))
    return "tickets:" + hashlib.sha256(raw.encode()).hexdigest()


def _version(item: Ticket, request: Request) -> None:
    if item.version != _expected_version(request):
        raise identity.IdentityError(409, "version_conflict")


def _version_cursor(value: str | None, scope: str) -> int | None:
    if value is None:
        return None
    if not value.startswith(scope) or not re.fullmatch(r"[1-9][0-9]{0,9}", value[len(scope) :]):
        raise identity.IdentityError(422, "invalid_cursor")
    version = int(value[len(scope) :])
    if version > 2147483647:
        raise identity.IdentityError(422, "invalid_cursor")
    return version


def _event(
    db: Session,
    actor: User,
    item: Ticket,
    request: Request,
    event: str,
    *,
    now: datetime | None = None,
    **details: str | None,
) -> None:
    identity.record_event(
        db,
        actor.id,
        item.id,
        "ticket." + event,
        now if now is not None else datetime.now(UTC),
        request.state.correlation_id,
        item.version,
        aggregate_type="ticket",
        details={
            "ticket_id": str(item.id),
            "client_id": str(item.client_id),
            "queue_id": str(item.queue_id),
            **details,
        },
    )


def _assigned(
    db: Session,
    actor: User,
    item: Ticket,
    old: UUID | None,
    request: Request,
    fields: list[str],
    *,
    now: datetime | None = None,
) -> None:
    _event(
        db,
        actor,
        item,
        request,
        "assigned",
        now=now,
        old_assignee_id=str(old) if old else None,
        new_assignee_id=str(item.assignee_id),
        changed_fields=",".join(fields),
    )


def create_record(
    db: Session,
    actor: User,
    access: registry.Access,
    body: TicketCreate,
    request: Request,
    *,
    source: Literal["manual", "email"] = "manual",
    now: datetime | None = None,
) -> Ticket:
    """Shared creation/history owner; caller authorizes and checks replay first."""
    registry.require_active(access)
    registry.validate_requester(db, access, body.requester_id)
    registry.validate_category(db, access, body.category_id)
    registry.validate_assignee(db, access, body.assignee_id)
    now = now if now is not None else datetime.now(UTC)
    item = Ticket(
        **body.model_dump(),
        status="new",
        source=source,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.flush()
    db.add(
        TicketStatusHistory(
            ticket_id=item.id,
            actor_id=actor.id,
            from_status=None,
            to_status="new",
            reason=None,
            version=1,
            occurred_at=now,
        )
    )
    _event(db, actor, item, request, "created", now=now if source == "email" else None)
    if item.assignee_id is not None:
        _assigned(
            db, actor, item, None, request, ["assignee_id"], now=now if source == "email" else None
        )
    return item


def create_ticket_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Tickets"])

    @router.get("/tickets", response_model=TicketPage)
    def listing(request: Request, filters: Annotated[TicketFilters, Query()]) -> TicketPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            scope = _scope(request, filters, actor.id)
            last = _time_cursor(filters.cursor, scope)
            query = (
                registry.filtered(registry.visible(actor.id), filters)
                .order_by(Ticket.created_at.desc(), Ticket.id.desc())
                .limit(filters.limit + 1)
            )
            if last is not None:
                query = query.where(tuple_(Ticket.created_at, Ticket.id) < last)
            rows = list(db.execute(query))
            return TicketPage(
                items=[
                    registry.output(
                        item,
                        registry.Access(item.client, item.queue, role, active, note_access),
                        actor.id,
                    )
                    for item, role, active, note_access in rows[: filters.limit]
                ],
                next_cursor=_next_time_cursor(
                    scope, rows[filters.limit - 1][0].created_at, rows[filters.limit - 1][0].id
                )
                if len(rows) > filters.limit
                else None,
                can_create=registry.can_create(db, actor.id),
            )

    @router.post(
        "/tickets",
        response_model=TicketReceipt,
        status_code=201,
        responses={200: {"model": TicketReceipt}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create(body: TicketCreate, request: Request, response: Response) -> TicketReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            access = registry.creation_access(
                db, actor.id, body.client_id, body.queue_id, write=True
            )
            if not access.manage and body.assignee_id not in {None, actor.id}:
                raise identity.IdentityError(403, "forbidden")
            route = "/api/v1/tickets"
            key, fingerprint, saved = _operation(
                db, actor, request, route, body.model_dump(mode="json")
            )
            if saved is not None:
                response.status_code = 200
                return TicketReceipt.model_validate(saved.result)
            item = create_record(db, actor, access, body, request)
            receipt = TicketReceipt(ticket_id=item.id)
            _remember(db, actor, route, key, fingerprint, receipt, 201)
            return receipt

    @router.get("/tickets/{identifier}", response_model=TicketOutput)
    def get(identifier: UUID, request: Request, response: Response) -> TicketOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            item, access = registry.scoped_ticket(db, actor.id, identifier)
            _etag(response, item.version)
            return registry.output(item, access, actor.id)

    @router.patch(
        "/tickets/{identifier}",
        response_model=TicketOutput,
        openapi_extra={"parameters": [IF_MATCH]},
    )
    def patch(
        identifier: UUID, body: TicketPatch, request: Request, response: Response
    ) -> TicketOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            item, access = registry.scoped_ticket(db, actor.id, identifier, write=True)
            registry.require_update(item, access, actor.id)
            if not access.manage and body.model_fields_set & {"assignee_id", "requester_id"}:
                raise identity.IdentityError(403, "forbidden")
            _version(item, request)
            changes = sorted(
                field
                for field in body.model_fields_set
                if getattr(item, field) != getattr(body, field)
            )
            if changes:
                registry.require_active(access, item)
                if "requester_id" in changes and body.requester_id is not None:
                    registry.validate_requester(db, access, body.requester_id)
                if "category_id" in changes:
                    registry.validate_category(db, access, body.category_id)
                if "assignee_id" in changes:
                    registry.validate_assignee(db, access, body.assignee_id)
                old = item.assignee_id
                registry.advance(item)
                for field in changes:
                    setattr(item, field, getattr(body, field))
                if "assignee_id" in changes and item.assignee_id is not None:
                    _assigned(db, actor, item, old, request, changes)
                else:
                    _event(db, actor, item, request, "updated", changed_fields=",".join(changes))
                db.flush()
                item, access = registry.scoped_ticket(db, actor.id, identifier)
            _etag(response, item.version)
            return registry.output(item, access, actor.id)

    @router.post(
        "/tickets/{identifier}/claim",
        response_model=TicketReceipt,
        openapi_extra={"parameters": [IF_MATCH, IDEMPOTENCY_KEY]},
    )
    def claim(identifier: UUID, body: TicketClaim, request: Request) -> TicketReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            item, access = registry.scoped_ticket(db, actor.id, identifier, write=True)
            if not access.contribute:
                raise identity.IdentityError(403, "forbidden")
            version = _expected_version(request)
            route = f"ticket-claim:{identifier}"
            key, fingerprint, saved = _operation(db, actor, request, route, body.model_dump())
            if saved is not None:
                return TicketReceipt.model_validate(saved.result)
            if item.version != version:
                raise identity.IdentityError(409, "version_conflict")
            if item.assignee_id not in {None, actor.id}:
                raise identity.IdentityError(409, "ticket_already_assigned")
            if item.assignee_id is None:
                registry.require_active(access, item)
                registry.validate_assignee(db, access, actor.id)
                registry.advance(item)
                item.assignee_id = actor.id
                _assigned(db, actor, item, None, request, ["assignee_id"])
            receipt = TicketReceipt(ticket_id=item.id)
            _remember(db, actor, route, key, fingerprint, receipt, 200)
            return receipt

    @router.post(
        "/tickets/{identifier}/transitions",
        response_model=TicketTransitionReceipt,
        openapi_extra={"parameters": [IF_MATCH, IDEMPOTENCY_KEY]},
    )
    def transition(
        identifier: UUID, body: TicketTransition, request: Request
    ) -> TicketTransitionReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            item, access = registry.scoped_ticket(db, actor.id, identifier, write=True)
            registry.require_update(item, access, actor.id)
            version = _expected_version(request)
            route = f"ticket-transition:{identifier}"
            key, fingerprint, saved = _operation(
                db, actor, request, route, body.model_dump(mode="json")
            )
            if saved is not None:
                return TicketTransitionReceipt.model_validate(saved.result)
            if item.version != version:
                raise identity.IdentityError(409, "version_conflict")
            history = registry.transition(db, item, access, actor.id, body)
            if history is not None:
                _event(
                    db,
                    actor,
                    item,
                    request,
                    "status_changed",
                    from_status=history.from_status,
                    to_status=history.to_status,
                    history_id=str(history.id),
                )
            receipt = TicketTransitionReceipt(
                ticket_id=item.id, history_id=history.id if history else None
            )
            _remember(db, actor, route, key, fingerprint, receipt, 200)
            return receipt

    @router.get("/tickets/{identifier}/messages", response_model=TicketMessagePage)
    def messages(
        identifier: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> TicketMessagePage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_ticket(db, actor.id, identifier)
            _collection(request)
            scope = f"v1|ticket-messages:{actor.id}:{identifier}|"
            last = _version_cursor(cursor, scope)
            query = (
                select(TicketMessage)
                .where(TicketMessage.ticket_id == identifier)
                .order_by(TicketMessage.ticket_version)
                .limit(limit + 1)
            )
            if last is not None:
                query = query.where(TicketMessage.ticket_version > last)
            rows = list(db.scalars(query))
            return TicketMessagePage(
                items=[registry.message_output(row) for row in rows[:limit]],
                next_cursor=scope + str(rows[limit - 1].ticket_version)
                if len(rows) > limit
                else None,
            )

    @router.get("/tickets/{identifier}/conversation", response_model=ConversationPage)
    def conversation(
        identifier: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> ConversationPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_ticket(db, actor.id, identifier)
            _collection(request)
            scope = f"v1|ticket-conversation:{actor.id}:{identifier}|"
            last = _version_cursor(cursor, scope) or 0
            query = union_all(
                select(
                    TicketIncomingMessage.id,
                    TicketIncomingMessage.ticket_version,
                    literal("incoming").label("kind"),
                ).where(
                    TicketIncomingMessage.ticket_id == identifier,
                    TicketIncomingMessage.ticket_version > last,
                ),
                select(
                    TicketMessage.id,
                    TicketMessage.ticket_version,
                    literal("outbound").label("kind"),
                ).where(TicketMessage.ticket_id == identifier, TicketMessage.ticket_version > last),
            ).subquery()
            rows = list(db.execute(select(query).order_by(query.c.ticket_version).limit(limit + 1)))
            incoming = {
                row.id: row
                for row in db.scalars(
                    select(TicketIncomingMessage).where(
                        TicketIncomingMessage.ticket_id == identifier,
                        TicketIncomingMessage.id.in_(
                            [row.id for row in rows[:limit] if row.kind == "incoming"]
                        ),
                    )
                )
            }
            outbound = {
                row.id: row
                for row in db.scalars(
                    select(TicketMessage).where(
                        TicketMessage.ticket_id == identifier,
                        TicketMessage.id.in_(
                            [row.id for row in rows[:limit] if row.kind == "outbound"]
                        ),
                    )
                )
            }
            incoming_values = incoming_outputs(db, actor.id, list(incoming.values()))
            return ConversationPage(
                items=[
                    incoming_values[row.id]
                    if row.kind == "incoming"
                    else OutboundConversationOutput(
                        ticket_version=row.ticket_version,
                        message=registry.message_output(outbound[row.id]),
                    )
                    for row in rows[:limit]
                ],
                next_cursor=scope + str(rows[limit - 1].ticket_version)
                if len(rows) > limit
                else None,
            )

    @router.get(
        "/tickets/{identifier}/incoming-messages/{incoming_id}",
        response_model=IncomingMessageOutput,
    )
    def incoming_message(
        identifier: UUID, incoming_id: UUID, request: Request
    ) -> IncomingMessageOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_ticket(db, actor.id, identifier)
            row = db.scalar(
                select(TicketIncomingMessage).where(
                    TicketIncomingMessage.ticket_id == identifier,
                    TicketIncomingMessage.id == incoming_id,
                )
            )
            if row is None:
                raise identity.IdentityError(404, "not_found")
            return incoming_output(db, actor.id, row)

    @router.get("/tickets/{identifier}/messages/{message_id}", response_model=TicketMessageOutput)
    def message(identifier: UUID, message_id: UUID, request: Request) -> TicketMessageOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_ticket(db, actor.id, identifier)
            row = db.scalar(
                select(TicketMessage).where(
                    TicketMessage.id == message_id, TicketMessage.ticket_id == identifier
                )
            )
            if row is None:
                raise identity.IdentityError(404, "not_found")
            return registry.message_output(row)

    @router.post(
        "/tickets/{identifier}/messages",
        response_model=TicketMessageReceipt,
        status_code=201,
        responses={200: {"model": TicketMessageReceipt}},
        openapi_extra={"parameters": [IF_MATCH, IDEMPOTENCY_KEY]},
    )
    def append_message(
        identifier: UUID,
        body: TicketMessageCreate,
        request: Request,
        response: Response,
    ) -> TicketMessageReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            item, access = registry.scoped_ticket(db, actor.id, identifier, write=True)
            registry.require_update(item, access, actor.id)
            version = _expected_version(request)
            route = f"ticket-message:{identifier}"
            key, fingerprint, saved = _operation(
                db, actor, request, route, attachment_links.intent(body)
            )
            if saved is not None:
                response.status_code = 200
                return TicketMessageReceipt.model_validate(saved.result)
            if item.version != version:
                raise identity.IdentityError(409, "version_conflict")
            registry.require_active(access, item)
            files = attachment_links.locked(db, "ticket", item.id, "public", body.attachment_ids)
            registry.advance(item)
            message = TicketMessage(
                ticket_id=item.id,
                author_id=actor.id,
                body_text=body.body_text,
                attachment_count=len(files),
                ticket_version=item.version,
                created_at=item.updated_at,
            )
            db.add(message)
            db.flush()
            attachment_links.attach(db, message.id, item.id, "public", files)
            _event(db, actor, item, request, "message_drafted", message_id=str(message.id))
            receipt = TicketMessageReceipt(ticket_id=item.id, message_id=message.id)
            _remember(db, actor, route, key, fingerprint, receipt, 201)
            return receipt

    @router.get("/tickets/{identifier}/notes", response_model=TicketNotePage)
    def notes(
        identifier: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> TicketNotePage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            _, access = registry.scoped_ticket(db, actor.id, identifier)
            registry.require_notes(access)
            _collection(request)
            scope = f"v1|ticket-notes:{actor.id}:{identifier}|"
            last = _version_cursor(cursor, scope)
            query = (
                select(TicketNote)
                .where(TicketNote.ticket_id == identifier)
                .order_by(TicketNote.ticket_version)
                .limit(limit + 1)
            )
            if last is not None:
                query = query.where(TicketNote.ticket_version > last)
            rows = list(db.scalars(query))
            return TicketNotePage(
                items=[registry.note_output(row) for row in rows[:limit]],
                next_cursor=scope + str(rows[limit - 1].ticket_version)
                if len(rows) > limit
                else None,
            )

    @router.get("/tickets/{identifier}/notes/{note_id}", response_model=TicketNoteOutput)
    def note(identifier: UUID, note_id: UUID, request: Request) -> TicketNoteOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            _, access = registry.scoped_ticket(db, actor.id, identifier)
            registry.require_notes(access)
            row = db.scalar(
                select(TicketNote).where(
                    TicketNote.id == note_id, TicketNote.ticket_id == identifier
                )
            )
            if row is None:
                raise identity.IdentityError(404, "not_found")
            return registry.note_output(row)

    @router.post(
        "/tickets/{identifier}/notes",
        response_model=TicketNoteReceipt,
        status_code=201,
        responses={200: {"model": TicketNoteReceipt}},
        openapi_extra={"parameters": [IF_MATCH, IDEMPOTENCY_KEY]},
    )
    def append_note(
        identifier: UUID, body: TicketNoteCreate, request: Request, response: Response
    ) -> TicketNoteReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            item, access = registry.scoped_ticket(db, actor.id, identifier, write=True)
            registry.require_notes(access, write=True)
            version = _expected_version(request)
            route = f"ticket-note:{identifier}"
            key, fingerprint, saved = _operation(
                db, actor, request, route, attachment_links.intent(body)
            )
            if saved is not None:
                response.status_code = 200
                return TicketNoteReceipt.model_validate(saved.result)
            if item.version != version:
                raise identity.IdentityError(409, "version_conflict")
            registry.require_active(access, item)
            files = attachment_links.locked(db, "ticket", item.id, "note", body.attachment_ids)
            registry.advance(item)
            note = TicketNote(
                ticket_id=item.id,
                author_id=actor.id,
                body_text=body.body_text,
                attachment_count=len(files),
                ticket_version=item.version,
                created_at=item.updated_at,
            )
            db.add(note)
            db.flush()
            attachment_links.attach(db, note.id, item.id, "note", files)
            _event(db, actor, item, request, "note_added", note_id=str(note.id))
            receipt = TicketNoteReceipt(ticket_id=item.id, note_id=note.id)
            _remember(db, actor, route, key, fingerprint, receipt, 201)
            return receipt

    @router.get("/tickets/{identifier}/status-history", response_model=TicketStates)
    def states(
        identifier: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> TicketStates:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_ticket(db, actor.id, identifier)
            _collection(request)
            scope = f"v1|ticket-states:{actor.id}:{identifier}|"
            query = (
                select(TicketStatusHistory)
                .where(TicketStatusHistory.ticket_id == identifier)
                .order_by(TicketStatusHistory.version.desc())
                .limit(limit + 1)
            )
            version = _version_cursor(cursor, scope)
            if version is not None:
                query = query.where(TicketStatusHistory.version < version)
            rows = list(db.scalars(query))
            return TicketStates(
                items=[TicketState.model_validate(row) for row in rows[:limit]],
                next_cursor=scope + str(rows[limit - 1].version) if len(rows) > limit else None,
            )

    @router.get("/tickets/{identifier}/activity", response_model=ActivityPage)
    def activity(
        identifier: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> ActivityPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            _, access = registry.scoped_ticket(db, actor.id, identifier)
            _collection(request)
            query = select(ActivityEvent).where(
                ActivityEvent.resource_type == "ticket", ActivityEvent.resource_id == identifier
            )
            if not registry.can_read_notes(access):
                query = query.where(ActivityEvent.event_type != "ticket.note_added")
            return activity_page(
                db,
                query,
                f"ticket-activity:{actor.id}:{identifier}",
                limit,
                cursor,
            )

    @router.get("/ticket-choices/queues", response_model=TicketQueueChoices)
    def queues(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> TicketQueueChoices:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            _collection(request)
            scope = f"ticket-queue-choices:{actor.id}"
            last = _cursor(cursor, scope)
            query = registry.queues(actor.id).order_by(TicketQueue.id).limit(limit + 1)
            if last:
                query = query.where(TicketQueue.id > last)
            rows = list(db.execute(query))
            return TicketQueueChoices(
                items=[
                    TicketQueueChoice(
                        id=queue.id,
                        name=queue.name,
                        active=queue.active and active,
                        can_create=role in {"agent", "operations_manager"}
                        and queue.active
                        and active,
                        can_assign=role == "operations_manager" and queue.active and active,
                    )
                    for queue, role, active in rows[:limit]
                ],
                next_cursor=_next_cursor(scope, rows[limit - 1][0].id)
                if len(rows) > limit
                else None,
                can_create=registry.can_create(db, actor.id),
            )

    @router.get("/ticket-choices/{queue_id}/clients", response_model=TicketClientChoices)
    def clients(
        queue_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> TicketClientChoices:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_queue(db, actor.id, queue_id, writer=True)
            _collection(request)
            scope = f"ticket-client-choices:{actor.id}:{queue_id}"
            last = _cursor(cursor, scope)
            query = (
                registry.clients(actor.id).where(Client.active).order_by(Client.id).limit(limit + 1)
            )
            if last:
                query = query.where(Client.id > last)
            rows = list(db.scalars(query))
            return TicketClientChoices(
                items=[TicketClientChoice(id=row.id, name=row.name) for row in rows[:limit]],
                next_cursor=_next_cursor(scope, rows[limit - 1].id) if len(rows) > limit else None,
            )

    @router.get(
        "/ticket-choices/{queue_id}/clients/{client_id}/requesters", response_model=RequesterPage
    )
    def requesters(
        queue_id: UUID,
        client_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> RequesterPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            access = registry.creation_access(db, actor.id, client_id, queue_id)
            registry.require_active(access)
            _collection(request)
            scope = f"ticket-requesters:{actor.id}:{queue_id}:{client_id}"
            last = _cursor(cursor, scope)
            query = (
                select(ClientContact)
                .where(ClientContact.client_id == client_id, ClientContact.active)
                .order_by(ClientContact.id)
                .limit(limit + 1)
            )
            if last:
                query = query.where(ClientContact.id > last)
            rows = list(db.scalars(query))
            return RequesterPage(
                items=[
                    RequesterChoice(
                        id=row.id,
                        display_name=row.display_name,
                        email=row.email_normalized,
                        verification_state="unverified",
                    )
                    for row in rows[:limit]
                ],
                next_cursor=_next_cursor(scope, rows[limit - 1].id) if len(rows) > limit else None,
            )

    @router.get(
        "/ticket-choices/{queue_id}/clients/{client_id}/assignees", response_model=CandidatePage
    )
    def assignees(
        queue_id: UUID,
        client_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> CandidatePage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            access = registry.creation_access(db, actor.id, client_id, queue_id)
            if not access.manage:
                raise identity.IdentityError(403, "forbidden")
            registry.require_active(access)
            _collection(request)
            scope = f"ticket-assignees:{actor.id}:{queue_id}:{client_id}"
            last = _cursor(cursor, scope)
            query = registry.candidates(queue_id, client_id).order_by(User.id).limit(limit + 1)
            if last:
                query = query.where(User.id > last)
            rows = list(db.scalars(query))
            return CandidatePage(
                items=[Candidate(id=row.id, display_name=row.display_name) for row in rows[:limit]],
                next_cursor=_next_cursor(scope, rows[limit - 1].id) if len(rows) > limit else None,
            )

    return router
