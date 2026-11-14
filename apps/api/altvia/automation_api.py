"""Scoped rule configuration with protected queue/rule version intent receipts."""

import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from altvia import automation_rules as rules
from altvia import identity
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    _cursor,
    _etag,
    _expected_version,
    _next_cursor,
    _operation,
    _remember,
    authenticate_request,
)
from altvia.automation_schemas import (
    RuleCreate,
    RuleListQuery,
    RuleOutput,
    RulePage,
    RulePatch,
    RuleReceipt,
)
from altvia.config import Settings
from altvia.models import AutomationRule

IF_MATCH_QUEUE = {**IF_MATCH, "name": "If-Match-Queue", "description": "Reviewed queue version"}


def _query(request: Request, *, listing: bool = False) -> None:
    allowed = {"client_id", "limit", "cursor"} if listing else set()
    if not set(request.query_params) <= allowed:
        raise identity.IdentityError(422, "unsupported_query")
    if any(len(request.query_params.getlist(name)) != 1 for name in request.query_params):
        raise identity.IdentityError(422, "repeated_query")


def _versions(request: Request, *, patch: bool = False) -> tuple[int, int | None]:
    for header in ("if-match", "if-match-queue", "idempotency-key"):
        if len(request.headers.getlist(header)) > 1:
            raise identity.IdentityError(422, "invalid_precondition")
    reviewed = _expected_version(request)
    queue = (
        _expected_version(
            request,
            header="if-match-queue",
            required_code="queue_version_required",
            invalid_code="invalid_queue_version",
        )
        if patch
        else None
    )
    return reviewed, queue


def _rule(db: Session, queue_id: UUID, rule_id: UUID, *, write: bool = False) -> AutomationRule:
    query = select(AutomationRule).where(
        AutomationRule.id == rule_id, AutomationRule.queue_id == queue_id
    )
    if write:
        query = query.with_for_update().execution_options(populate_existing=True)
    rule = db.scalar(query)
    if rule is None:
        raise identity.IdentityError(404, "not_found")
    return rule


def create_automation_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/ticket-queues/{queue_id}/automation-rules", tags=["Assignment automation"]
    )

    @router.get("", response_model=RulePage)
    def listing(
        queue_id: UUID, request: Request, filters: Annotated[RuleListQuery, Query()]
    ) -> RulePage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            _query(request, listing=True)
            permission = rules.access(db, actor.id, filters.client_id, queue_id)
            scope = (
                "automation-rules:"
                + hashlib.sha256(f"{actor.id}:{queue_id}:{filters.client_id}".encode()).hexdigest()
            )
            last = _cursor(filters.cursor, scope)
            query = select(AutomationRule).where(
                AutomationRule.queue_id == queue_id, AutomationRule.client_id == filters.client_id
            )
            if last is not None:
                query = query.where(AutomationRule.id > last)
            rows = list(db.scalars(query.order_by(AutomationRule.id).limit(filters.limit + 1)))
            return RulePage(
                items=[
                    rules.output(row, rules.current_revision(db, row), permission.queue.version)
                    for row in rows[: filters.limit]
                ],
                next_cursor=_next_cursor(scope, rows[filters.limit - 1].id)
                if len(rows) > filters.limit
                else None,
            )

    @router.post(
        "",
        response_model=RuleReceipt,
        status_code=201,
        responses={200: {"model": RuleReceipt}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY, IF_MATCH]},
    )
    def create(
        queue_id: UUID, body: RuleCreate, request: Request, response: Response
    ) -> RuleReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            _query(request)
            permission = rules.access(db, actor.id, body.client_id, queue_id, write=True)
            version, _ = _versions(request)
            route = f"automation-rule-create:{queue_id}:{body.client_id}"
            key, fingerprint, saved = _operation(
                db,
                actor,
                request,
                route,
                {"body": body.model_dump(mode="json"), "queue_version": version},
            )
            if saved is not None:
                response.status_code = 200
                return RuleReceipt.model_validate(saved.result)
            if permission.queue.version != version:
                raise identity.IdentityError(409, "version_conflict")
            rule = rules.create(db, actor.id, permission, body, request.state.correlation_id)
            receipt = RuleReceipt(rule_id=rule.id, queue_id=queue_id, client_id=body.client_id)
            _remember(db, actor, route, key, fingerprint, receipt, 201)
            return receipt

    @router.get("/{rule_id}", response_model=RuleOutput)
    def detail(queue_id: UUID, rule_id: UUID, request: Request, response: Response) -> RuleOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            _query(request)
            rule = _rule(db, queue_id, rule_id)
            permission = rules.access(db, actor.id, rule.client_id, queue_id)
            _etag(response, rule.version)
            return rules.output(rule, rules.current_revision(db, rule), permission.queue.version)

    @router.patch(
        "/{rule_id}",
        response_model=RuleReceipt,
        openapi_extra={"parameters": [IDEMPOTENCY_KEY, IF_MATCH, IF_MATCH_QUEUE]},
    )
    def patch(queue_id: UUID, rule_id: UUID, body: RulePatch, request: Request) -> RuleReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            _query(request)
            rule = _rule(db, queue_id, rule_id)
            permission = rules.access(db, actor.id, rule.client_id, queue_id, write=True)
            rule = _rule(db, queue_id, rule_id, write=True)
            version, queue_version = _versions(request, patch=True)
            route = "automation-rule-patch:" + str(rule.id)
            key, fingerprint, saved = _operation(
                db,
                actor,
                request,
                route,
                {
                    "body": body.model_dump(mode="json", exclude_unset=True),
                    "rule_version": version,
                    "queue_version": queue_version,
                },
            )
            if saved is not None:
                return RuleReceipt.model_validate(saved.result)
            if rule.version != version or permission.queue.version != queue_version:
                raise identity.IdentityError(409, "version_conflict")
            rules.patch(db, actor.id, permission, rule, body, request.state.correlation_id)
            receipt = RuleReceipt(rule_id=rule.id, queue_id=queue_id, client_id=rule.client_id)
            _remember(db, actor, route, key, fingerprint, receipt, 200)
            return receipt

    return router
