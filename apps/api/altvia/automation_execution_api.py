"""Scoped durable outcomes and reviewed recovery, never worker lease disclosure."""

import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Engine, Select, and_, or_, select
from sqlalchemy.orm import Session

from altvia import automation_execution as execution
from altvia import automation_rules, identity, project_registry, tickets
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    _cursor,
    _next_cursor,
    _operation,
    _remember,
    authenticate_request,
)
from altvia.admin_http import queue_configuration_versions as _versions
from altvia.automation_schemas import (
    ExecutionEffect,
    ExecutionOutput,
    ExecutionPage,
    ExecutionReceipt,
)
from altvia.config import Settings
from altvia.models import AutomationEffect, AutomationExecution, AutomationRule, Project, Ticket


def _query(request: Request, *, listing: bool = False) -> None:
    allowed = {"limit", "cursor"} if listing else set()
    if not set(request.query_params) <= allowed:
        raise identity.IdentityError(422, "unsupported_query")
    if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise identity.IdentityError(422, "repeated_query")


def _visible(
    actor_id: UUID, ticket_id: UUID
) -> Select[tuple[AutomationExecution, AutomationEffect]]:
    projects = project_registry.visible_projects(actor_id).with_only_columns(Project.id)
    return (
        select(AutomationExecution, AutomationEffect)
        .outerjoin(
            AutomationEffect,
            and_(
                AutomationEffect.rule_id == AutomationExecution.rule_id,
                AutomationEffect.action_id == AutomationExecution.action_id,
                AutomationEffect.ticket_id == AutomationExecution.ticket_id,
            ),
        )
        .where(
            AutomationExecution.ticket_id == ticket_id,
            or_(AutomationEffect.work_item_id.is_(None), AutomationEffect.project_id.in_(projects)),
        )
    )


def _can_retry(
    db: Session,
    actor_id: UUID,
    entry: AutomationExecution,
    ticket: Ticket,
    permission: tickets.Access,
) -> bool:
    try:
        automation_rules.access(db, actor_id, entry.client_id, entry.queue_id)
        execution.require_retry(db, entry, ticket, permission)
        return True
    except identity.IdentityError:
        return False


def create_execution_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tickets/{ticket_id}/automation-executions", tags=["Assignment automation"]
    )

    @router.get("", response_model=ExecutionPage)
    def listing(
        ticket_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> ExecutionPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            _query(request, listing=True)
            ticket, permission = tickets.scoped_ticket(db, actor.id, ticket_id, metadata_only=True)
            scope = (
                "automation-executions:"
                + hashlib.sha256(f"{actor.id}:{ticket_id}".encode()).hexdigest()
            )
            last = _cursor(cursor, scope)
            query = _visible(actor.id, ticket_id)
            if last is not None:
                query = query.where(AutomationExecution.id > last)
            rows = list(db.execute(query.order_by(AutomationExecution.id).limit(limit + 1)))
            items = []
            for entry, effect in rows[:limit]:
                items.append(
                    ExecutionOutput(
                        **{
                            field: getattr(entry, field)
                            for field in (
                                "id",
                                "rule_id",
                                "action_id",
                                "rule_version",
                                "source_event_id",
                                "state",
                                "attempts",
                                "error_code",
                                "created_at",
                                "updated_at",
                                "version",
                            )
                        },
                        can_retry=_can_retry(db, actor.id, entry, ticket, permission),
                        effect=ExecutionEffect(
                            work_item_id=effect.work_item_id,
                            project_id=effect.project_id,
                            mode=effect.mode,
                        )
                        if effect is not None
                        else None,
                    )
                )
            return ExecutionPage(
                items=items,
                next_cursor=_next_cursor(scope, rows[limit - 1][0].id)
                if len(rows) > limit
                else None,
            )

    @router.post(
        "/{execution_id}/retry",
        response_model=ExecutionReceipt,
        status_code=202,
        responses={200: {"model": ExecutionReceipt}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY, IF_MATCH]},
    )
    async def retry(
        ticket_id: UUID, execution_id: UUID, request: Request, response: Response
    ) -> ExecutionReceipt:
        async for chunk in request.stream():
            if chunk:
                raise identity.IdentityError(422, "unexpected_body")
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            _query(request)
            ticket, permission = tickets.scoped_ticket(
                db, actor.id, ticket_id, write=True, metadata_only=True
            )
            row = db.execute(
                _visible(actor.id, ticket_id).where(AutomationExecution.id == execution_id)
            ).one_or_none()
            if row is None:
                raise identity.IdentityError(404, "not_found")
            entry, _ = row
            automation_rules.access(db, actor.id, entry.client_id, entry.queue_id)
            db.scalar(
                select(AutomationRule).where(AutomationRule.id == entry.rule_id).with_for_update()
            )
            entry = db.scalars(
                select(AutomationExecution)
                .where(AutomationExecution.id == execution_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).one()
            version, _ = _versions(request)
            route = f"automation-retry:{ticket_id}:{execution_id}"
            key, fingerprint, saved = _operation(db, actor, request, route, {"version": version})
            if saved is not None:
                response.status_code = 200
                return ExecutionReceipt.model_validate(saved.result)
            if entry.version != version:
                raise identity.IdentityError(409, "version_conflict")
            execution.require_retry(db, entry, ticket, permission)
            execution.retry(db, actor.id, entry, request.state.correlation_id)
            receipt = ExecutionReceipt(execution_id=entry.id)
            _remember(db, actor, route, key, fingerprint, receipt, 202)
            return receipt

    return router
