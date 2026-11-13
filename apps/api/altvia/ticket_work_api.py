"""Canonical ticket-first mutations with protected dual-version intent receipts."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Engine, false
from sqlalchemy.orm import Session

from altvia import identity, ticket_work, tickets, work_items
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    _cursor,
    _expected_version,
    _next_cursor,
    _operation,
    _remember,
    authenticate_request,
)
from altvia.config import Settings
from altvia.ticket_work import ReviewedLinkVersions
from altvia.ticket_work_schemas import (
    IF_MATCH_WORK_ITEM,
    LinkedTicket,
    LinkedWork,
    TicketWorkChoices,
    TicketWorkChoicesQuery,
    TicketWorkCreate,
    TicketWorkListQuery,
    TicketWorkPage,
    TicketWorkReceipt,
    WorkLinkChoice,
    WorkTicketPage,
)


def _reviewed_versions(request: Request) -> ReviewedLinkVersions:
    if len(request.headers.getlist("if-match")) > 1:
        raise identity.IdentityError(422, "invalid_version")
    ticket = _expected_version(request)
    if len(request.headers.getlist("if-match-work-item")) > 1:
        raise identity.IdentityError(422, "invalid_work_item_version")
    work = _expected_version(
        request,
        header="if-match-work-item",
        required_code="work_item_version_required",
        invalid_code="invalid_work_item_version",
    )
    return ReviewedLinkVersions(ticket, work)


def _scope(
    actor_id: UUID,
    parent_id: UUID,
    direction: Literal["work", "tickets", "choices"],
    filters: dict[str, object],
) -> str:
    values = {k: v for k, v in filters.items() if k not in {"limit", "cursor"} and v is not None}
    if not values.get("q"):
        values.pop("q", None)
    raw = json.dumps(
        [str(actor_id), str(parent_id), direction, values], sort_keys=True, separators=(",", ":")
    )
    return "ticket-work:" + hashlib.sha256(raw.encode()).hexdigest()


def _unique_query(request: Request) -> None:
    if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise identity.IdentityError(422, "repeated_query")


def create_ticket_work_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["ticket-work"])

    @router.get("/tickets/{identifier}/work-items", response_model=TicketWorkPage)
    def linked_work(
        identifier: UUID, request: Request, filters: Annotated[TicketWorkListQuery, Query()]
    ) -> TicketWorkPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            ticket, access = tickets.scoped_ticket(db, actor.id, identifier)
            _unique_query(request)
            scope = _scope(actor.id, identifier, "work", {})
            last = _cursor(filters.cursor, scope)
            query = ticket_work.linked_work_query(actor.id, identifier)
            identifier_column = query.selected_columns.work_item_id
            if last is not None:
                query = query.where(identifier_column > last)
            rows = (
                db.execute(query.order_by(identifier_column).limit(filters.limit + 1))
                .mappings()
                .all()
            )
            return TicketWorkPage(
                items=[LinkedWork.model_validate(row) for row in rows[: filters.limit]],
                next_cursor=_next_cursor(scope, rows[filters.limit - 1]["work_item_id"])
                if len(rows) > filters.limit
                else None,
                can_link=tickets.can_update(ticket, access, actor.id)
                and access.active
                and ticket.status != "closed",
            )

    @router.get("/work-items/{identifier}/tickets", response_model=WorkTicketPage)
    def linked_tickets(
        identifier: UUID, request: Request, filters: Annotated[TicketWorkListQuery, Query()]
    ) -> WorkTicketPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            work_items.scoped_work(db, actor.id, identifier)
            _unique_query(request)
            scope = _scope(actor.id, identifier, "tickets", {})
            last = _cursor(filters.cursor, scope)
            query = ticket_work.linked_ticket_query(actor.id, identifier)
            identifier_column = query.selected_columns.ticket_id
            if last is not None:
                query = query.where(identifier_column > last)
            rows = (
                db.execute(query.order_by(identifier_column).limit(filters.limit + 1))
                .mappings()
                .all()
            )
            return WorkTicketPage(
                items=[LinkedTicket.model_validate(row) for row in rows[: filters.limit]],
                next_cursor=_next_cursor(scope, rows[filters.limit - 1]["ticket_id"])
                if len(rows) > filters.limit
                else None,
            )

    @router.get("/tickets/{identifier}/work-item-choices", response_model=TicketWorkChoices)
    def choices(
        identifier: UUID, request: Request, filters: Annotated[TicketWorkChoicesQuery, Query()]
    ) -> TicketWorkChoices:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            ticket, access = tickets.scoped_ticket(db, actor.id, identifier)
            tickets.require_update(ticket, access, actor.id)
            _unique_query(request)
            scope = _scope(actor.id, identifier, "choices", filters.model_dump(mode="json"))
            last = _cursor(filters.cursor, scope)
            can_link = access.active and ticket.status != "closed"
            query = ticket_work.work_choices_query(actor.id, ticket, filters)
            identifier_column = query.selected_columns.work_item_id
            if not can_link:
                query = query.where(false())
            if last is not None:
                query = query.where(identifier_column > last)
            rows = (
                db.execute(query.order_by(identifier_column).limit(filters.limit + 1))
                .mappings()
                .all()
            )
            return TicketWorkChoices(
                items=[WorkLinkChoice.model_validate(row) for row in rows[: filters.limit]],
                next_cursor=_next_cursor(scope, rows[filters.limit - 1]["work_item_id"])
                if len(rows) > filters.limit
                else None,
                can_link=can_link,
            )

    def mutate(
        identifier: UUID, work_id: UUID, request: Request, response: Response, *, linked: bool
    ) -> TicketWorkReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            pair = ticket_work.scoped_pair(db, actor.id, identifier, work_id, write=True)
            reviewed = _reviewed_versions(request)
            route = (
                f"ticket-work-link:{identifier}"
                if linked
                else f"ticket-work-unlink:{identifier}:{work_id}"
            )
            key, fingerprint, saved = _operation(
                db,
                actor,
                request,
                route,
                {
                    "ticket_id": str(identifier),
                    "work_item_id": str(work_id),
                    "ticket_version": reviewed.ticket,
                    "work_item_version": reviewed.work_item,
                },
            )
            if saved is not None:
                response.status_code = 200 if linked else 204
                return TicketWorkReceipt.model_validate(saved.result)
            if (
                pair.ticket.version != reviewed.ticket
                or pair.work_item.version != reviewed.work_item
            ):
                raise identity.IdentityError(409, "version_conflict")
            changed = ticket_work.change_link(
                db,
                actor.id,
                pair,
                linked=linked,
                now=datetime.now(UTC),
                correlation_id=request.state.correlation_id,
            )
            result = TicketWorkReceipt(ticket_id=identifier, work_item_id=work_id)
            response.status_code = (201 if changed else 200) if linked else 204
            _remember(db, actor, route, key, fingerprint, result, response.status_code)
            return result

    @router.post(
        "/tickets/{identifier}/work-items",
        status_code=201,
        response_model=TicketWorkReceipt,
        responses={200: {"model": TicketWorkReceipt}},
        openapi_extra={"parameters": [IF_MATCH, IF_MATCH_WORK_ITEM, IDEMPOTENCY_KEY]},
    )
    def link(
        identifier: UUID, body: TicketWorkCreate, request: Request, response: Response
    ) -> TicketWorkReceipt:
        return mutate(identifier, body.work_item_id, request, response, linked=True)

    @router.delete(
        "/tickets/{identifier}/work-items/{work_id}",
        status_code=204,
        openapi_extra={"parameters": [IF_MATCH, IF_MATCH_WORK_ITEM, IDEMPOTENCY_KEY]},
    )
    def unlink(identifier: UUID, work_id: UUID, request: Request) -> Response:
        response = Response(status_code=204)
        mutate(identifier, work_id, request, response, linked=False)
        return response

    return router
