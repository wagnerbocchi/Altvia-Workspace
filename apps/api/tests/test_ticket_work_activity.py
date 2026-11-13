"""Reciprocal event validation and current counterpart history privacy."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from altvia import identity
from altvia.activity import consume_event
from altvia.models import ActivityEvent, OutboxEvent, ProcessedEvent
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_team_api import admin_client
from ticket_work_support import make_link_context

__all__ = ["admin_client"]


def emit(engine, ctx, actor, event="ticket.work_linked", **changes):
    payload = {
        "ticket_id": str(ctx.ticket_id),
        "work_item_id": str(ctx.work_item_id),
        "client_id": str(ctx.client_id),
        "queue_id": str(ctx.queue_id),
        "project_id": str(ctx.project_id),
        "relation_type": "related",
    }
    resource = "ticket" if event.startswith("ticket.") else "work_item"
    identifier = ctx.ticket_id if resource == "ticket" else ctx.work_item_id
    with Session(engine) as db, db.begin():
        identity.record_event(
            db,
            actor,
            identifier,
            event,
            datetime.now(UTC),
            uuid4().hex,
            2,
            aggregate_type=resource,
            details=payload,
        )
        db.flush()
        row = db.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.event_type == event)
            .order_by(OutboxEvent.occurred_at.desc())
        )
        for key, value in changes.items():
            setattr(row, key, value)
        return row.event_id


@pytest.mark.parametrize(
    "event",
    [
        "ticket.work_linked",
        "ticket.work_unlinked",
        "work_item.ticket_linked",
        "work_item.ticket_unlinked",
    ],
)
def test_strict_link_events_project_once(admin_client, db_engine, seeded_user, event):
    ctx = make_link_context(admin_client, db_engine, seeded_user)
    event_id = emit(db_engine, ctx, seeded_user, event)
    assert consume_event(db_engine, event_id, datetime.now(UTC))
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        projected = db.get(ActivityEvent, event_id)
        assert projected.details["work_item_id"] == str(ctx.work_item_id)
        assert (
            len(list(db.scalars(select(ProcessedEvent).where(ProcessedEvent.event_id == event_id))))
            == 1
        )


@pytest.mark.parametrize(
    "fault",
    [
        "extra",
        "missing",
        "null",
        "uuid",
        "relation",
        "actor",
        "aggregate",
        "type",
        "schema",
        "version",
    ],
)
def test_link_event_strict_rejection(admin_client, db_engine, seeded_user, fault):
    ctx = make_link_context(admin_client, db_engine, seeded_user)
    event_id = emit(db_engine, ctx, seeded_user)
    with Session(db_engine) as db, db.begin():
        event = db.get(OutboxEvent, event_id)
        payload = dict(event.payload)
        if fault == "extra":
            payload["title"] = "Private subject"
        elif fault == "missing":
            payload.pop("project_id")
        elif fault == "null":
            payload["actor_id"] = None
        elif fault == "uuid":
            payload["work_item_id"] = "not-a-uuid"
        elif fault == "relation":
            payload["relation_type"] = "implements"
        elif fault == "actor":
            payload["actor_kind"] = "management_command"
        elif fault == "aggregate":
            event.aggregate_id = uuid4()
        elif fault == "type":
            event.aggregate_type = "work_item"
        elif fault == "schema":
            event.schema_version = 2
        elif fault == "version":
            event.aggregate_version = 0
        event.payload = payload
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(ActivityEvent, event_id) is None
        assert db.get(OutboxEvent, event_id).status == "dead"
        assert (
            list(db.scalars(select(ProcessedEvent).where(ProcessedEvent.event_id == event_id)))
            == []
        )


@pytest.mark.parametrize("direction", ["ticket", "work_item"])
def test_link_event_privacy_precedes_cursor_and_survives_unlink(
    admin_client, db_engine, seeded_user, direction
):
    from altvia.models import RoleBinding
    from sqlalchemy import delete
    from test_ticket_work import link, unlink

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    assert link(admin_client, ctx).status_code == 201
    assert unlink(admin_client, ctx, 2).status_code == 204
    with Session(db_engine) as db:
        ids = list(
            db.scalars(
                select(OutboxEvent.event_id).where(
                    OutboxEvent.aggregate_id.in_([ctx.ticket_id, ctx.work_item_id])
                )
            )
        )
    for event_id in ids:
        assert consume_event(db_engine, event_id, datetime.now(UTC))
    parent = (
        f"/api/v1/tickets/{ctx.ticket_id}"
        if direction == "ticket"
        else f"/api/v1/work-items/{ctx.work_item_id}"
    )
    visible = admin_client.get(parent + "/activity").json()["items"]
    assert len(visible) == 3  # created, linked, unlinked without any live link
    assert {row["event_type"] for row in visible} == (
        {"ticket.created", "ticket.work_linked", "ticket.work_unlinked"}
        if direction == "ticket"
        else {"work_item.created", "work_item.ticket_linked", "work_item.ticket_unlinked"}
    )
    hidden_ids = {
        row["event_id"]
        for row in visible
        if row["event_type"] not in {"ticket.created", "work_item.created"}
    }
    with Session(db_engine) as db, db.begin():
        scopes = {"project", "client"} if direction == "ticket" else {"queue"}
        db.execute(
            delete(RoleBinding).where(
                RoleBinding.user_id == seeded_user, RoleBinding.scope_kind.in_(scopes)
            )
        )
    result = admin_client.get(parent + "/activity?limit=1")
    assert result.status_code == 200, result.text
    page = result.json()
    assert len(page["items"]) == 1 and page["next_cursor"] is None
    assert page["items"][0]["event_type"] == (
        "ticket.created" if direction == "ticket" else "work_item.created"
    )
    assert all(identifier not in result.text for identifier in hidden_ids)


@pytest.mark.parametrize(
    "field", ["work_item_id", "ticket_id", "client_id", "queue_id", "project_id"]
)
def test_malformed_or_changed_history_context_fails_closed(
    admin_client, db_engine, seeded_user, field
):
    ctx = make_link_context(admin_client, db_engine, seeded_user)
    event_id = emit(db_engine, ctx, seeded_user)
    assert consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db, db.begin():
        row = db.get(ActivityEvent, event_id)
        row.details = {**row.details, field: "invalid-uuid-value"}
    response = admin_client.get(f"/api/v1/tickets/{ctx.ticket_id}/activity?limit=1")
    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "next_cursor": None}
