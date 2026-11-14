"""Truthful automated provenance without private source/execution disclosure."""

from datetime import UTC, datetime
from uuid import UUID

from altvia.activity import consume_event
from sqlalchemy import text
from test_automation_execution import admin_client, consume_available, effect_context, rule_context
from test_team_api import preconditions, sign_in
from test_tickets import ticket

__all__ = ["admin_client", "effect_context", "rule_context"]


def test_schema2_projection_is_once_only_and_work_only_history_hides_source(
    admin_client, db_engine, effect_context, seeded_user
):
    refs = effect_context
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    consume_available(db_engine)
    with db_engine.connect() as connection:
        work_id = connection.scalar(text("SELECT id FROM work_items"))
        execution_id = connection.scalar(text("SELECT id FROM automation_executions"))
        ids = list(
            connection.scalars(text("SELECT event_id FROM outbox_events WHERE schema_version=2"))
        )
    assert work_id is not None and len(ids) == 3
    for identifier in ids:
        assert consume_event(db_engine, identifier, datetime.now(UTC)) is True
        assert consume_event(db_engine, identifier, datetime.now(UTC)) is False
    work_path = f"/api/v1/work-items/{work_id}/activity"
    full = admin_client.get(work_path).json()
    assert len(full["items"]) == 2
    assert {row["event_type"] for row in full["items"]} == {
        "work_item.created",
        "work_item.ticket_linked",
    }
    for row in full["items"]:
        assert row["actor_id"] is None and row["actor_kind"] == "automation"
        assert row["details"]["authorizer_id"] == str(seeded_user)
        assert "execution_id" not in row["details"]
    queue_path = "/api/v1/ticket-queues/" + refs["queue_id"]
    queue = admin_client.get(queue_path).json()
    removed = admin_client.delete(
        queue_path + "/members/" + refs["agent_id"], headers=preconditions(queue["version"])
    )
    assert removed.status_code == 204, removed.text
    sign_in(admin_client, "agent@example.test")
    assert admin_client.get(path).status_code == 404
    own = admin_client.get(work_path, params={"limit": 1})
    assert own.status_code == 200, own.text
    result = own.json()
    assert len(result["items"]) == 1 and result["items"][0]["event_type"] == "work_item.created"
    assert result["next_cursor"] is None
    assert str(execution_id) not in own.text
    assert str(UUID(path.rsplit("/", 1)[1])) not in own.text
    assert result["items"][0]["details"]["authorizer_id"] == str(seeded_user)
