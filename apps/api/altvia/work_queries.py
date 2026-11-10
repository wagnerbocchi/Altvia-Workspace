"""One SQL filter owner for project discovery and the authorized personal queue."""

import hashlib
import json
from datetime import UTC
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import Select, func, literal_column, or_, select

from altvia import identity
from altvia.models import WorkAssignee, WorkItem
from altvia.work_schemas import WorkFilters

# Explicit constant configuration and expression match the immutable GIN index.
# Keep user data in bound parameters, including websearch syntax.
SEARCH_DOCUMENT = (
    "to_tsvector('portuguese'::regconfig, coalesce(title,'') || ' ' || coalesce(description,''))"
)


def involved(user_id: UUID) -> Any:
    participant = (
        select(WorkAssignee.work_item_id)
        .where(WorkAssignee.work_item_id == WorkItem.id, WorkAssignee.user_id == user_id)
        .correlate(WorkItem)
        .exists()
    )
    return or_(WorkItem.owner_id == user_id, participant)


def filtered(query: Select[Any], filters: WorkFilters) -> Select[Any]:
    for field in ("status", "priority", "work_type", "owner_id"):
        value = getattr(filters, field)
        if value is not None:
            query = query.where(getattr(WorkItem, field) == value)
    if filters.involved_user_id is not None:
        query = query.where(involved(filters.involved_user_id))
    if filters.unassigned:
        query = query.where(WorkItem.owner_id.is_(None))
    if filters.due_presence:
        query = query.where(
            WorkItem.due_at.is_not(None)
            if filters.due_presence == "dated"
            else WorkItem.due_at.is_(None)
        )
    if filters.due_from:
        query = query.where(WorkItem.due_at >= filters.due_from)
    if filters.due_before:
        query = query.where(WorkItem.due_at < filters.due_before)
    if filters.q:
        query = query.where(
            literal_column(SEARCH_DOCUMENT).op("@@")(
                func.websearch_to_tsquery(literal_column("'portuguese'::regconfig"), filters.q)
            )
        )
    return query


def scope(request: Request, filters: WorkFilters, actor: UUID, collection: str) -> str:
    # Query models forbid unknown keys. Duplicate keys must not be silently
    # collapsed to their last value by the HTTP framework.
    if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise identity.IdentityError(422, "repeated_query")
    values = filters.model_dump(mode="json", exclude={"limit", "cursor"}, exclude_none=True)
    if not values.get("q"):
        values.pop("q", None)
    if not values.get("unassigned"):
        values.pop("unassigned", None)
    for field in ("due_from", "due_before"):
        value = getattr(filters, field)
        if value:
            values[field] = value.astimezone(UTC).isoformat()
    if collection == "work-items" and set(values) == {"project_id"}:
        return f"work-items:{values['project_id']}"
    raw = json.dumps([str(actor), values], sort_keys=True, separators=(",", ":"))
    return collection + ":" + hashlib.sha256(raw.encode()).hexdigest()
