"""Restricted administrative identity activity; no queue payload or audit-table access."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, Select, select, tuple_
from sqlalchemy.orm import Session

from altvia.admin_http import _collection_query, _next_time_cursor, _time_cursor, require_admin
from altvia.config import Settings
from altvia.models import ActivityEvent


class ActivityOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: UUID
    resource_type: str
    resource_id: UUID
    event_type: str
    occurred_at: datetime
    actor_id: UUID | None
    actor_kind: str
    aggregate_version: int
    correlation_id: str
    details: dict[str, str]


class ActivityPage(BaseModel):
    items: list[ActivityOutput]
    next_cursor: str | None


def activity_page(
    db: Session,
    query: Select[tuple[ActivityEvent]],
    scope: str,
    limit: int,
    cursor: str | None,
) -> ActivityPage:
    query = query.order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.event_id.desc()).limit(
        limit + 1
    )
    bound = _time_cursor(cursor, scope)
    if bound:
        query = query.where(tuple_(ActivityEvent.occurred_at, ActivityEvent.event_id) < bound)
    rows = list(db.scalars(query))
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _next_time_cursor(scope, last.occurred_at, last.event_id)
    return ActivityPage(
        items=[ActivityOutput.model_validate(row) for row in rows[:limit]], next_cursor=next_cursor
    )


def create_activity_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Identity administration"])

    @router.get("/identity-activity", response_model=ActivityPage)
    def list_activity(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> ActivityPage:
        with Session(engine) as db, db.begin():
            require_admin(db, request, settings)
            _collection_query(request)
            query = select(ActivityEvent).where(
                ActivityEvent.resource_type.in_(("identity", "team"))
            )
            return activity_page(db, query, "identity-activity-v1", limit, cursor)

    return router
