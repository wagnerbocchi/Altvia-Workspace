"""Restricted administrative identity activity; no queue payload or audit-table access."""

import base64
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, select, tuple_
from sqlalchemy.orm import Session

from altvia import identity
from altvia.admin_http import _collection_query, require_admin
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
            query = (
                select(ActivityEvent)
                .order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.event_id.desc())
                .limit(limit + 1)
            )
            if cursor is not None:
                try:
                    raw = base64.b64decode(
                        cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
                    ).decode("ascii")
                    scope, instant, identifier = raw.split("|")
                    stamp, event_id = datetime.fromisoformat(instant), UUID(identifier)
                    if scope != "identity-activity-v1" or stamp.tzinfo is None:
                        raise ValueError("Invalid cursor")
                    query = query.where(
                        tuple_(ActivityEvent.occurred_at, ActivityEvent.event_id)
                        < (stamp, event_id)
                    )
                except (ValueError, UnicodeError):
                    raise identity.IdentityError(422, "invalid_cursor") from None
            rows = list(db.scalars(query))
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                instant = last.occurred_at.astimezone(UTC).isoformat()
                raw = f"identity-activity-v1|{instant}|{last.event_id}"
                next_cursor = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
            return ActivityPage(
                items=[ActivityOutput.model_validate(row) for row in rows[:limit]],
                next_cursor=next_cursor,
            )

    return router
