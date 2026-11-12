"""Current customer ceiling and queue-role filtered published-case reads."""

import hashlib
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Engine, tuple_
from sqlalchemy.orm import Session

from altvia import identity, mail_cases
from altvia.admin_http import _etag, _next_time_cursor, _time_cursor, authenticate_request
from altvia.config import Settings
from altvia.mail_case_schemas import CaseDetail, CaseFilters, CasePage, CaseSummary
from altvia.models import MailTriageCase


def create_mail_case_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/mail-cases", tags=["Mail cases"])

    @router.get("", response_model=CasePage)
    def listing(request: Request, filters: Annotated[CaseFilters, Query()]) -> CasePage:
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise identity.IdentityError(422, "repeated_query")
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            values = filters.model_dump(mode="json", exclude={"limit", "cursor"}, exclude_none=True)
            bound = json.dumps([str(actor.id), values], sort_keys=True, separators=(",", ":"))
            scope = "mail-cases:" + hashlib.sha256(bound.encode()).hexdigest()
            last = _time_cursor(filters.cursor, scope)
            query = mail_cases.visible(actor.id)
            for name in ("queue_id", "client_id", "state"):
                value = getattr(filters, name)
                if value is not None:
                    query = query.where(getattr(MailTriageCase, name) == value)
            if last is not None:
                query = query.where(tuple_(MailTriageCase.created_at, MailTriageCase.id) < last)
            rows = list(
                db.execute(
                    query.order_by(
                        MailTriageCase.created_at.desc(), MailTriageCase.id.desc()
                    ).limit(filters.limit + 1)
                ).mappings()
            )
            return CasePage(
                items=[CaseSummary.model_validate(row) for row in rows[: filters.limit]],
                next_cursor=_next_time_cursor(
                    scope, rows[filters.limit - 1]["created_at"], rows[filters.limit - 1]["id"]
                )
                if len(rows) > filters.limit
                else None,
            )

    @router.get("/{case_id}", response_model=CaseDetail)
    def detail(case_id: UUID, request: Request, response: Response) -> CaseDetail:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            row = (
                db.execute(
                    mail_cases.visible(actor.id, detail=True).where(MailTriageCase.id == case_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise identity.IdentityError(404, "not_found")
            _etag(response, row["version"])
            return CaseDetail.model_validate(row)

    return router
