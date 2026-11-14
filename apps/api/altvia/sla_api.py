"""Scoped calendar/policy HTTP boundary with reviewed, durable write intents."""

import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from altvia import identity
from altvia import queue_client_configuration as scope
from altvia import sla_configuration as config
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    IF_MATCH_QUEUE,
    _cursor,
    _etag,
    _next_cursor,
    _operation,
    _remember,
    authenticate_request,
    configuration_query,
    queue_configuration_versions,
)
from altvia.config import Settings
from altvia.models import BusinessCalendar, SlaPolicy
from altvia.sla_schemas import (
    CalendarCreate,
    CalendarOutput,
    CalendarPage,
    CalendarPatch,
    CalendarReceipt,
    PolicyCalendarSnapshot,
    PolicyCreate,
    PolicyOutput,
    PolicyPage,
    PolicyPatch,
    PolicyReceipt,
    SlaConfigurationQuery,
)


def _scope(actor_id: UUID, queue_id: UUID, client_id: UUID, kind: str) -> str:
    return kind + ":" + hashlib.sha256(f"{actor_id}:{queue_id}:{client_id}".encode()).hexdigest()


def create_sla_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/ticket-queues/{queue_id}", tags=["Ticket SLA configuration"])

    @router.get("/business-calendars", response_model=CalendarPage)
    def calendars(
        queue_id: UUID, request: Request, filters: Annotated[SlaConfigurationQuery, Query()]
    ) -> CalendarPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            configuration_query(request, listing=True)
            permission = scope.access(db, actor.id, filters.client_id, queue_id)
            cursor_scope = _scope(actor.id, queue_id, filters.client_id, "sla-calendars")
            last = _cursor(filters.cursor, cursor_scope)
            query = select(BusinessCalendar).where(
                BusinessCalendar.queue_id == queue_id,
                BusinessCalendar.client_id == filters.client_id,
            )
            if last is not None:
                query = query.where(BusinessCalendar.id > last)
            rows = list(db.scalars(query.order_by(BusinessCalendar.id).limit(filters.limit + 1)))
            return CalendarPage(
                items=[
                    config.calendar_summary(db, row, permission) for row in rows[: filters.limit]
                ],
                next_cursor=_next_cursor(cursor_scope, rows[filters.limit - 1].id)
                if len(rows) > filters.limit
                else None,
            )

    @router.get("/business-calendars/{calendar_id}", response_model=CalendarOutput)
    def calendar_detail(
        queue_id: UUID, calendar_id: UUID, request: Request, response: Response
    ) -> CalendarOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            configuration_query(request)
            row = config.calendar(db, queue_id, calendar_id)
            permission = scope.access(db, actor.id, row.client_id, queue_id)
            _etag(response, row.version)
            return config.calendar_output(db, row, permission)

    @router.post(
        "/business-calendars",
        response_model=CalendarReceipt,
        status_code=201,
        responses={200: {"model": CalendarReceipt}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY, IF_MATCH]},
    )
    def calendar_create(
        queue_id: UUID, body: CalendarCreate, request: Request, response: Response
    ) -> CalendarReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            configuration_query(request)
            permission = scope.access(db, actor.id, body.client_id, queue_id, write=True)
            version, _ = queue_configuration_versions(request)
            route = f"sla-calendar-create:{queue_id}:{body.client_id}"
            key, fingerprint, saved = _operation(
                db,
                actor,
                request,
                route,
                {
                    "body": body.model_dump(mode="json"),
                    "queue_version": version,
                },
            )
            if saved is not None:
                response.status_code = 200
                return CalendarReceipt.model_validate(saved.result)
            if permission.queue.version != version:
                raise identity.IdentityError(409, "version_conflict")
            row = config.create_calendar(
                db, actor.id, permission, body, request.state.correlation_id
            )
            receipt = CalendarReceipt(
                calendar_id=row.id, queue_id=queue_id, client_id=body.client_id
            )
            _remember(db, actor, route, key, fingerprint, receipt, 201)
            return receipt

    @router.patch(
        "/business-calendars/{calendar_id}",
        response_model=CalendarReceipt,
        openapi_extra={"parameters": [IDEMPOTENCY_KEY, IF_MATCH, IF_MATCH_QUEUE]},
    )
    def calendar_patch(
        queue_id: UUID, calendar_id: UUID, body: CalendarPatch, request: Request
    ) -> CalendarReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            configuration_query(request)
            row = config.calendar(db, queue_id, calendar_id)
            permission = scope.access(db, actor.id, row.client_id, queue_id, write=True)
            row = config.calendar(db, queue_id, calendar_id, write=True)
            version, queue_version = queue_configuration_versions(request, patch=True)
            route = "sla-calendar-patch:" + str(row.id)
            key, fingerprint, saved = _operation(
                db,
                actor,
                request,
                route,
                {
                    "body": body.model_dump(mode="json", exclude_unset=True),
                    "calendar_version": version,
                    "queue_version": queue_version,
                },
            )
            if saved is not None:
                return CalendarReceipt.model_validate(saved.result)
            if row.version != version or permission.queue.version != queue_version:
                raise identity.IdentityError(409, "version_conflict")
            config.patch_calendar(db, actor.id, permission, row, body, request.state.correlation_id)
            receipt = CalendarReceipt(
                calendar_id=row.id, queue_id=queue_id, client_id=row.client_id
            )
            _remember(db, actor, route, key, fingerprint, receipt, 200)
            return receipt

    @router.get("/sla-policies", response_model=PolicyPage)
    def policies(
        queue_id: UUID, request: Request, filters: Annotated[SlaConfigurationQuery, Query()]
    ) -> PolicyPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            configuration_query(request, listing=True)
            permission = scope.access(db, actor.id, filters.client_id, queue_id)
            cursor_scope = _scope(actor.id, queue_id, filters.client_id, "sla-policies")
            last = _cursor(filters.cursor, cursor_scope)
            query = select(SlaPolicy).where(
                SlaPolicy.queue_id == queue_id, SlaPolicy.client_id == filters.client_id
            )
            if last is not None:
                query = query.where(SlaPolicy.id > last)
            rows = list(db.scalars(query.order_by(SlaPolicy.id).limit(filters.limit + 1)))
            return PolicyPage(
                items=[config.policy_output(db, row, permission) for row in rows[: filters.limit]],
                next_cursor=_next_cursor(cursor_scope, rows[filters.limit - 1].id)
                if len(rows) > filters.limit
                else None,
            )

    @router.get("/sla-policies/{policy_id}", response_model=PolicyOutput)
    def policy_detail(
        queue_id: UUID, policy_id: UUID, request: Request, response: Response
    ) -> PolicyOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            configuration_query(request)
            row = config.policy(db, queue_id, policy_id)
            permission = scope.access(db, actor.id, row.client_id, queue_id)
            _etag(response, row.version)
            return config.policy_output(db, row, permission)

    @router.get(
        "/sla-policies/{policy_id}/calendar-snapshot", response_model=PolicyCalendarSnapshot
    )
    def selected_calendar(
        queue_id: UUID, policy_id: UUID, request: Request
    ) -> PolicyCalendarSnapshot:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            configuration_query(request)
            row = config.policy(db, queue_id, policy_id)
            scope.access(db, actor.id, row.client_id, queue_id)
            return config.policy_calendar_output(db, row)

    @router.post(
        "/sla-policies",
        response_model=PolicyReceipt,
        status_code=201,
        responses={200: {"model": PolicyReceipt}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY, IF_MATCH]},
    )
    def policy_create(
        queue_id: UUID, body: PolicyCreate, request: Request, response: Response
    ) -> PolicyReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            configuration_query(request)
            permission = scope.access(db, actor.id, body.client_id, queue_id, write=True)
            version, _ = queue_configuration_versions(request)
            route = f"sla-policy-create:{queue_id}:{body.client_id}"
            key, fingerprint, saved = _operation(
                db,
                actor,
                request,
                route,
                {
                    "body": body.model_dump(mode="json"),
                    "queue_version": version,
                },
            )
            if saved is not None:
                response.status_code = 200
                return PolicyReceipt.model_validate(saved.result)
            if permission.queue.version != version:
                raise identity.IdentityError(409, "version_conflict")
            row = config.create_policy(db, actor.id, permission, body, request.state.correlation_id)
            receipt = PolicyReceipt(policy_id=row.id, queue_id=queue_id, client_id=body.client_id)
            _remember(db, actor, route, key, fingerprint, receipt, 201)
            return receipt

    @router.patch(
        "/sla-policies/{policy_id}",
        response_model=PolicyReceipt,
        openapi_extra={"parameters": [IDEMPOTENCY_KEY, IF_MATCH, IF_MATCH_QUEUE]},
    )
    def policy_patch(
        queue_id: UUID, policy_id: UUID, body: PolicyPatch, request: Request
    ) -> PolicyReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            configuration_query(request)
            row = config.policy(db, queue_id, policy_id)
            permission = scope.access(db, actor.id, row.client_id, queue_id, write=True)
            row = config.policy(db, queue_id, policy_id, write=True)
            version, queue_version = queue_configuration_versions(request, patch=True)
            route = "sla-policy-patch:" + str(row.id)
            key, fingerprint, saved = _operation(
                db,
                actor,
                request,
                route,
                {
                    "body": body.model_dump(mode="json", exclude_unset=True),
                    "policy_version": version,
                    "queue_version": queue_version,
                },
            )
            if saved is not None:
                return PolicyReceipt.model_validate(saved.result)
            if row.version != version or permission.queue.version != queue_version:
                raise identity.IdentityError(409, "version_conflict")
            config.patch_policy(db, actor.id, permission, row, body, request.state.correlation_id)
            receipt = PolicyReceipt(policy_id=row.id, queue_id=queue_id, client_id=row.client_id)
            _remember(db, actor, route, key, fingerprint, receipt, 200)
            return receipt

    return router
