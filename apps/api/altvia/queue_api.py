"""Versioned queue configuration with team metadata scope and immutable receipts."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from altvia import identity
from altvia import queue_registry as registry
from altvia.activity_api import ActivityPage, activity_page
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    _collection_query,
    _cursor,
    _etag,
    _expected_version,
    _next_cursor,
    _operation,
    _remember,
    authenticate_request,
)
from altvia.config import Settings
from altvia.models import ActivityEvent, Team, TicketCategory, TicketQueue, User
from altvia.queue_schemas import (
    CategoryCreate,
    CategoryOutput,
    CategoryPage,
    CategoryReceipt,
    QueueCreate,
    QueueOutput,
    QueuePage,
    QueuePatch,
    QueueReceipt,
    QueueRecord,
    QueueTeam,
    QueueTeamPage,
)


def _collection(request: Request) -> None:
    _collection_query(request)
    if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise identity.IdentityError(422, "unsupported_query")


def _output(queue: TicketQueue, team_name: str, team_active: bool, can_manage: bool) -> QueueOutput:
    return QueueOutput(
        **QueueRecord.model_validate(queue).model_dump(),
        team_id=queue.team_id,
        team_name=team_name,
        team_active=team_active,
        can_manage=can_manage,
    )


def _event(
    db: Session,
    actor: User,
    queue: TicketQueue,
    event: str,
    request: Request,
    category_id: UUID | None = None,
    changes: list[str] | None = None,
) -> None:
    details = {}
    if category_id is not None:
        details["category_id"] = str(category_id)
    if changes is not None:
        details["changed_fields"] = ",".join(changes)
    identity.record_event(
        db,
        actor.id,
        queue.id,
        event,
        datetime.now(UTC),
        request.state.correlation_id,
        queue.version,
        aggregate_type="ticket_queue",
        details=details,
    )


def create_queue_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Service Desk configuration"])

    @router.get("/ticket-queue-teams", response_model=QueueTeamPage)
    def teams(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> QueueTeamPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            _collection(request)
            scope = f"queue-teams:{actor.id}"
            last = _cursor(cursor, scope)
            query = registry.visible_teams(actor.id).order_by(Team.id).limit(limit + 1)
            if last is not None:
                query = query.where(Team.id > last)
            rows = list(db.execute(query))
            return QueueTeamPage(
                items=[
                    QueueTeam(id=team.id, name=team.name, active=team.active, can_manage=manage)
                    for team, manage in rows[:limit]
                ],
                next_cursor=_next_cursor(scope, rows[limit - 1][0].id)
                if len(rows) > limit
                else None,
            )

    @router.get("/ticket-queues", response_model=QueuePage)
    def listing(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> QueuePage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            _collection(request)
            scope = f"ticket-queues:{actor.id}"
            last = _cursor(cursor, scope)
            query = registry.visible_queues(actor.id).order_by(TicketQueue.id).limit(limit + 1)
            if last is not None:
                query = query.where(TicketQueue.id > last)
            rows = list(db.execute(query))
            teams = registry.visible_teams(actor.id).subquery()
            can_create = (
                db.scalar(
                    select(select(teams.c.id).where(teams.c.active, teams.c.can_manage).exists())
                )
                is True
            )
            return QueuePage(
                items=[_output(*row) for row in rows[:limit]],
                can_create=can_create,
                next_cursor=_next_cursor(scope, rows[limit - 1][0].id)
                if len(rows) > limit
                else None,
            )

    @router.post(
        "/ticket-queues",
        response_model=QueueReceipt,
        status_code=201,
        responses={200: {"model": QueueReceipt}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create(body: QueueCreate, request: Request, response: Response) -> QueueReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            team, _ = registry.scoped_team(db, actor.id, body.team_id, write=True)
            route = "/api/v1/ticket-queues"
            key, digest, saved = _operation(db, actor, request, route, body.model_dump(mode="json"))
            if saved is not None:
                response.status_code = 200
                return QueueReceipt.model_validate(saved.result)
            registry.require_active(team.active)
            registry.unique_queue_name(db, team.id, body.name)
            queue = TicketQueue(team_id=team.id, name=body.name)
            db.add(queue)
            db.flush()
            _event(db, actor, queue, "ticket_queue.created", request)
            receipt = QueueReceipt(queue_id=queue.id)
            _remember(db, actor, route, key, digest, receipt, 201)
            return receipt

    @router.get("/ticket-queues/{queue_id}", response_model=QueueOutput)
    def get(queue_id: UUID, request: Request, response: Response) -> QueueOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            row = registry.scoped_queue(db, actor.id, queue_id)
            _etag(response, row[0].version)
            return _output(*row)

    @router.patch(
        "/ticket-queues/{queue_id}",
        response_model=QueueOutput,
        openapi_extra={"parameters": [IF_MATCH]},
    )
    def patch(
        queue_id: UUID, body: QueuePatch, request: Request, response: Response
    ) -> QueueOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            row = registry.scoped_queue(db, actor.id, queue_id, write=True)
            queue, _, team_active, _ = row
            if queue.version != _expected_version(request):
                raise identity.IdentityError(409, "version_conflict")
            changes = [
                field
                for field in body.model_fields_set
                if getattr(queue, field) != getattr(body, field)
            ]
            if changes:
                registry.require_active(team_active)
                if body.name is not None:
                    registry.unique_queue_name(db, queue.team_id, body.name, queue.id)
                registry.advance(queue)
                for field in changes:
                    setattr(queue, field, getattr(body, field))
                _event(db, actor, queue, "ticket_queue.updated", request, changes=sorted(changes))
            _etag(response, queue.version)
            return _output(*row)

    @router.get("/ticket-queues/{queue_id}/activity", response_model=ActivityPage)
    def activity(
        queue_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> ActivityPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_queue(db, actor.id, queue_id)
            _collection(request)
            query = select(ActivityEvent).where(
                ActivityEvent.resource_type == "ticket_queue", ActivityEvent.resource_id == queue_id
            )
            return activity_page(db, query, f"queue-activity:{actor.id}:{queue_id}", limit, cursor)

    @router.get("/ticket-queues/{queue_id}/categories", response_model=CategoryPage)
    def categories(
        queue_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> CategoryPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_queue(db, actor.id, queue_id)
            _collection(request)
            scope = f"queue-categories:{actor.id}:{queue_id}"
            last = _cursor(cursor, scope)
            query = (
                select(TicketCategory)
                .where(TicketCategory.queue_id == queue_id)
                .order_by(TicketCategory.id)
                .limit(limit + 1)
            )
            if last is not None:
                query = query.where(TicketCategory.id > last)
            rows = list(db.scalars(query))
            return CategoryPage(
                items=[CategoryOutput.model_validate(row) for row in rows[:limit]],
                next_cursor=_next_cursor(scope, rows[limit - 1].id) if len(rows) > limit else None,
            )

    @router.post(
        "/ticket-queues/{queue_id}/categories",
        response_model=CategoryReceipt,
        status_code=201,
        responses={200: {"model": CategoryReceipt}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create_category(
        queue_id: UUID, body: CategoryCreate, request: Request, response: Response
    ) -> CategoryReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            queue, _, team_active, _ = registry.scoped_queue(db, actor.id, queue_id, write=True)
            route = f"/api/v1/ticket-queues/{queue_id}/categories"
            key, digest, saved = _operation(db, actor, request, route, body.model_dump(mode="json"))
            if saved is not None:
                response.status_code = 200
                return CategoryReceipt.model_validate(saved.result)
            registry.require_active(team_active, queue.active)
            registry.unique_category_name(db, queue.id, body.name)
            registry.advance(queue)
            row = TicketCategory(queue_id=queue.id, name=body.name)
            db.add(row)
            db.flush()
            _event(db, actor, queue, "ticket_queue.category_created", request, row.id)
            receipt = CategoryReceipt(queue_id=queue.id, category_id=row.id)
            _remember(db, actor, route, key, digest, receipt, 201)
            return receipt

    @router.get("/ticket-queues/{queue_id}/categories/{category_id}", response_model=CategoryOutput)
    def get_category(
        queue_id: UUID, category_id: UUID, request: Request, response: Response
    ) -> CategoryOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_queue(db, actor.id, queue_id)
            row = registry.scoped_category(db, queue_id, category_id)
            _etag(response, row.version)
            return CategoryOutput.model_validate(row)

    @router.patch(
        "/ticket-queues/{queue_id}/categories/{category_id}",
        response_model=CategoryOutput,
        openapi_extra={"parameters": [IF_MATCH]},
    )
    def patch_category(
        queue_id: UUID, category_id: UUID, body: QueuePatch, request: Request, response: Response
    ) -> CategoryOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            queue, _, team_active, _ = registry.scoped_queue(db, actor.id, queue_id, write=True)
            row = registry.scoped_category(db, queue_id, category_id, write=True)
            if row.version != _expected_version(request):
                raise identity.IdentityError(409, "version_conflict")
            changes = [
                field
                for field in body.model_fields_set
                if getattr(row, field) != getattr(body, field)
            ]
            if changes:
                registry.require_active(team_active, queue.active)
                if body.name is not None:
                    registry.unique_category_name(db, queue.id, body.name, row.id)
                registry.advance(queue)
                registry.advance(row)
                for field in changes:
                    setattr(row, field, getattr(body, field))
                _event(
                    db,
                    actor,
                    queue,
                    "ticket_queue.category_updated",
                    request,
                    row.id,
                    sorted(changes),
                )
            _etag(response, row.version)
            return CategoryOutput.model_validate(row)

    return router
