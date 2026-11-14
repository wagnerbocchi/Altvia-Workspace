"""Real scoped configuration, protected off/on intent and atomic source staging."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from altvia import management
from altvia.activity import consume_event
from altvia.models import OutboxEvent
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in
from test_tickets import setup, ticket

__all__ = ["admin_client"]


@pytest.fixture
def rule_context(admin_client, db_engine, seeded_user):
    refs = setup(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        team = db.scalar(
            text("SELECT team_id FROM ticket_queues WHERE id=:id"), {"id": UUID(refs["queue_id"])}
        )
        management.set_team_role(db, "employee@example.test", team, "operations_manager", True)
    sign_in(admin_client, "employee@example.test")
    return refs


def route(refs):
    return f"/api/v1/ticket-queues/{refs['queue_id']}/automation-rules"


def rule_body(refs, **changes):
    return {
        "client_id": refs["client_id"],
        "title": "  Configured assignment work  ",
        "priority": "medium",
        "ticket_statuses": ["open", "new"],
        **changes,
    }


def queue_version(client, refs):
    response = client.get("/api/v1/ticket-queues/" + refs["queue_id"])
    assert response.status_code == 200, response.text
    return response.json()["version"]


def create_rule(client, refs):
    version, key = queue_version(client, refs), uuid4().hex
    response = client.post(route(refs), json=rule_body(refs), headers=preconditions(version, key))
    assert response.status_code == 201, response.text
    return route(refs) + "/" + response.json()["rule_id"]


def patch_rule(client, path, **changes):
    current = client.get(path)
    assert current.status_code == 200, current.text
    headers = {
        **preconditions(current.json()["version"]),
        "If-Match-Queue": f'"{current.json()["queue_version"]}"',
    }
    return client.patch(path, json=changes, headers=headers)


def test_rule_create_is_disabled_and_records_private_revision(
    admin_client, db_engine, rule_context, seeded_user
):
    refs = rule_context
    original_queue = queue_version(admin_client, refs)
    path = create_rule(admin_client, refs)
    detail = admin_client.get(path)
    assert detail.status_code == 200
    value = detail.json()
    assert value["title"] == "Configured assignment work"
    assert value["ticket_statuses"] == ["new", "open"]
    assert value["enabled"] is False and value["version"] == 1
    assert value["cancelled_through_version"] == 0
    assert value["queue_version"] == original_queue + 1
    assert value["authorizer_id"] == str(seeded_user)
    assert detail.headers["etag"] == '"1"'
    listing = admin_client.get(route(refs), params={"client_id": refs["client_id"], "limit": 1})
    assert listing.status_code == 200
    assert listing.json()["items"] == [value]
    assert listing.json()["next_cursor"] is None and "total" not in listing.json()
    with db_engine.connect() as connection:
        events = list(
            connection.execute(
                text("SELECT event_id FROM outbox_events WHERE event_type LIKE 'automation.%'")
            )
        )
        assert len(events) == 1
    assert consume_event(db_engine, events[0][0], datetime.now(UTC))
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM automation_rule_revisions")) == 1
        assert (
            connection.scalar(
                text("SELECT count(*) FROM activity_events WHERE event_id=:id"),
                {"id": events[0][0]},
            )
            == 0
        )


def test_disable_off_on_and_old_patch_replay_preserve_floor(admin_client, db_engine, rule_context):
    path = create_rule(admin_client, rule_context)
    before = admin_client.get(path).json()
    intent = {
        **preconditions(1),
        "If-Match-Queue": f'"{before["queue_version"]}"',
    }
    assert admin_client.patch(path, json={"enabled": True}, headers=intent).status_code == 200
    assert patch_rule(admin_client, path, enabled=False).status_code == 200
    disabled = admin_client.get(path).json()
    assert disabled["version"] == disabled["cancelled_through_version"] == 3
    assert disabled["enabled"] is False
    assert admin_client.patch(path, json={"enabled": True}, headers=intent).status_code == 200
    assert admin_client.get(path).json() == disabled
    assert patch_rule(admin_client, path, enabled=True).status_code == 200
    enabled = admin_client.get(path).json()
    assert enabled["version"] == 4 and enabled["cancelled_through_version"] == 3
    assert enabled["action_id"] == before["action_id"] and enabled["enabled"] is True
    # A semantically identical status-set reorder is a protected no-op.
    assert patch_rule(admin_client, path, ticket_statuses=["open", "new"]).status_code == 200
    assert admin_client.get(path).json() == enabled
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM automation_rule_revisions")) == 4


def test_create_replay_preserves_later_state_and_rechecks_current_scope(
    admin_client, db_engine, rule_context, seeded_user
):
    refs = rule_context
    headers = preconditions(queue_version(admin_client, refs))
    first = admin_client.post(route(refs), json=rule_body(refs), headers=headers)
    assert first.status_code == 201, first.text
    path = route(refs) + "/" + first.json()["rule_id"]
    assert patch_rule(admin_client, path, enabled=True).status_code == 200
    before = admin_client.get(path).json()
    replay = admin_client.post(route(refs), json=rule_body(refs), headers=headers)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert admin_client.get(path).json() == before
    assert (
        admin_client.post(
            route(refs), json=rule_body(refs, title="Changed intent"), headers=headers
        ).status_code
        == 409
    )
    assert (
        admin_client.post(
            route(refs), json=rule_body(refs), headers={**headers, "If-Match": "bad"}
        ).status_code
        == 422
    )
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE clients SET active=false"))
    assert admin_client.post(route(refs), json=rule_body(refs), headers=headers).status_code == 200
    with db_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM client_access_grants WHERE user_id=:id"), {"id": seeded_user}
        )
    assert admin_client.post(route(refs), json=rule_body(refs), headers=headers).status_code == 404


def test_rule_strict_fields_and_dual_preconditions(admin_client, rule_context):
    refs = rule_context
    for changes in (
        {"enabled": True},
        {"title": " "},
        {"title": "x\x00y"},
        {"ticket_statuses": []},
        {"ticket_statuses": ["new", "new"]},
        {"ticket_statuses": ["closed"]},
        {"priority": "urgent"},
        {"client_id": None},
        {"action_id": str(uuid4())},
    ):
        response = admin_client.post(
            route(refs),
            json=rule_body(refs, **changes),
            headers=preconditions(queue_version(admin_client, refs)),
        )
        assert response.status_code == 422, response.text
    path = create_rule(admin_client, refs)
    for body in (
        {},
        {"enabled": None},
        {"enabled": 1},
        {"title": None},
        {"client_id": refs["client_id"]},
    ):
        assert (
            admin_client.patch(
                path, json=body, headers={**preconditions(1), "If-Match-Queue": '"1"'}
            ).status_code
            == 422
        )
    assert (
        admin_client.patch(path, json={"enabled": True}, headers=preconditions(1)).status_code
        == 428
    )
    value = admin_client.get(path).json()
    headers = {**preconditions(1), "If-Match-Queue": f'"{value["queue_version"]}"'}
    assert (
        admin_client.patch(
            path, json={"enabled": True}, headers={**headers, "If-Match-Queue": 'W/"1"'}
        ).status_code
        == 422
    )
    assert (
        admin_client.patch(
            path, json={"enabled": True}, headers={**headers, "If-Match": '"2"'}
        ).status_code
        == 409
    )
    assert admin_client.patch(path, json={"enabled": True}, headers=headers).status_code == 200
    assert admin_client.patch(path, json={"enabled": False}, headers=headers).status_code == 409
    for query in (
        "",
        "?client_id=" + refs["client_id"] + "&unknown=1",
        "?client_id=" + refs["client_id"] + "&client_id=" + refs["client_id"],
    ):
        assert admin_client.get(route(refs) + query).status_code == 422
    assert admin_client.get(path + "?unknown=1").status_code == 422


@pytest.mark.parametrize("missing", ["config", "queue", "client_role", "ceiling"])
def test_rule_config_requires_every_current_conjunct(
    admin_client, db_engine, rule_context, seeded_user, missing
):
    refs = rule_context
    path = create_rule(admin_client, refs)
    with db_engine.begin() as connection:
        if missing == "ceiling":
            connection.execute(
                text("DELETE FROM client_access_grants WHERE user_id=:actor"),
                {"actor": seeded_user},
            )
        else:
            scope = {"config": "team", "queue": "queue", "client_role": "client"}[missing]
            connection.execute(
                text("DELETE FROM role_bindings WHERE user_id=:actor AND scope_kind=:scope"),
                {"actor": seeded_user, "scope": scope},
            )
    expected = 403 if missing == "config" else 404
    assert admin_client.get(path).status_code == expected
    assert (
        admin_client.get(route(refs), params={"client_id": refs["client_id"]}).status_code
        == expected
    )
    assert (
        admin_client.patch(
            path, json={"enabled": True}, headers={**preconditions(1), "If-Match-Queue": '"1"'}
        ).status_code
        == expected
    )


def test_assignment_stages_captured_enabled_revision_atomically(
    admin_client, db_engine, rule_context
):
    refs = rule_context
    path = create_rule(admin_client, refs)
    # Disabled assignment remains the incumbent manual path, without a job.
    ticket(admin_client, refs, assignee_id=refs["agent_id"])
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM automation_executions")) == 0
    assert patch_rule(admin_client, path, enabled=True).status_code == 200
    target = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    with db_engine.connect() as connection:
        rows = list(
            connection.execute(
                text(
                    "SELECT e.rule_version,e.state,o.event_type,o.payload "
                    "FROM automation_executions e JOIN outbox_events o "
                    "ON o.event_id=e.source_event_id"
                )
            )
        )
        assert len(rows) == 1 and rows[0][:3] == (2, "pending", "ticket.assigned")
        assert rows[0][3]["new_assignee_id"] == refs["agent_id"]
        assert set(rows[0][3]) == {
            "actor_id",
            "actor_kind",
            "ticket_id",
            "client_id",
            "queue_id",
            "old_assignee_id",
            "new_assignee_id",
            "changed_fields",
        }
    assert patch_rule(admin_client, path, title="New configured title").status_code == 200
    key = uuid4().hex
    headers = preconditions(1, key)
    change = {"assignee_id": None}
    assert admin_client.patch(target, json=change, headers=headers).status_code == 200
    assert (
        admin_client.patch(
            target, json={"assignee_id": refs["agent_id"]}, headers=preconditions(2)
        ).status_code
        == 200
    )
    with db_engine.connect() as connection:
        assert list(
            connection.scalars(
                text("SELECT rule_version FROM automation_executions ORDER BY created_at,id")
            )
        ) == [2, 3]


def test_staging_failure_rolls_back_native_ticket_and_event(admin_client, db_engine, rule_context):
    refs = rule_context
    path = create_rule(admin_client, refs)
    assert patch_rule(admin_client, path, enabled=True).status_code == 200
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE automation_executions ADD CONSTRAINT test_reject_job "
                "CHECK(false) NOT VALID"
            )
        )
    from test_tickets import create

    try:
        response = create(admin_client, refs, assignee_id=refs["agent_id"])
        assert response.status_code == 503
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE automation_executions DROP CONSTRAINT test_reject_job")
            )
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM tickets")) == 0
        assert connection.scalar(text("SELECT count(*) FROM ticket_status_history")) == 0
        assert (
            connection.scalar(
                text("SELECT count(*) FROM outbox_events WHERE aggregate_type='ticket'")
            )
            == 0
        )
        assert connection.scalar(text("SELECT count(*) FROM automation_executions")) == 0


def test_claim_and_manual_create_replay_stage_each_source_once(
    admin_client, db_engine, rule_context
):
    from test_tickets import create

    refs = rule_context
    path = create_rule(admin_client, refs)
    assert patch_rule(admin_client, path, enabled=True).status_code == 200
    key = uuid4().hex
    first = create(admin_client, refs, key, assignee_id=refs["agent_id"])
    assert first.status_code == 201
    assert create(admin_client, refs, key, assignee_id=refs["agent_id"]).status_code == 200
    unassigned = ticket(admin_client, refs)
    sign_in(admin_client, "agent@example.test")
    key = uuid4().hex
    for _ in range(2):
        response = admin_client.post(unassigned + "/claim", json={}, headers=preconditions(1, key))
        assert response.status_code == 200, response.text
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM automation_executions")) == 2
        assert (
            connection.scalar(
                text("SELECT count(DISTINCT source_event_id) FROM automation_executions")
            )
            == 2
        )


def test_native_mail_promotion_and_receipt_replay_stage_once(admin_client, db_engine, rule_context):
    from altvia.mail_intake import register_source
    from test_mail_cases import publish
    from test_mail_promotion import promote

    refs = rule_context
    path = create_rule(admin_client, refs)
    assert patch_rule(admin_client, path, enabled=True).status_code == 200
    with Session(db_engine) as db, db.begin():
        register_source(db, "synthetic-source", UUID(refs["queue_id"]))
    case = publish(db_engine, refs)
    body = {
        "action": "create",
        "subject": "Reviewed subject",
        "priority": "high",
        "assignee_id": refs["agent_id"],
    }
    key = uuid4().hex
    first = promote(admin_client, case.case_id, body, key=key)
    assert first.status_code == 201, first.text
    assert promote(admin_client, case.case_id, body, key=key).status_code == 200
    with db_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT e.rule_version,t.source,o.event_type,o.aggregate_version,t.version "
                "FROM automation_executions e JOIN tickets t ON t.id=e.ticket_id "
                "JOIN outbox_events o ON o.event_id=e.source_event_id"
            )
        ).one()
        assert tuple(row) == (2, "email", "ticket.assigned", 1, 2)


def test_archived_disable_replay_and_parent_version_failure_are_atomic(
    admin_client, db_engine, rule_context
):
    path = create_rule(admin_client, rule_context)
    assert patch_rule(admin_client, path, enabled=True).status_code == 200
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE clients SET active=false"))
    assert patch_rule(admin_client, path, title="Forbidden archived edit").status_code == 409
    assert patch_rule(admin_client, path, enabled=False).status_code == 200
    assert patch_rule(admin_client, path, enabled=False).status_code == 200
    before = admin_client.get(path).json()
    assert before["version"] == before["cancelled_through_version"] == 3
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE clients SET active=true"))
        connection.execute(text("UPDATE ticket_queues SET version=2147483647"))
    assert patch_rule(admin_client, path, enabled=True).status_code == 409
    after = admin_client.get(path).json()
    assert after["enabled"] is False and after["version"] == 3
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM automation_rule_revisions")) == 3


def test_platform_configuration_does_not_grant_rule_content(admin_client, rule_context):
    refs = rule_context
    path = create_rule(admin_client, refs)
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path).status_code == 404
    assert admin_client.get(route(refs), params={"client_id": refs["client_id"]}).status_code == 404
    assert (
        admin_client.post(route(refs), json=rule_body(refs), headers=preconditions(1)).status_code
        == 404
    )


def test_corrupt_private_metadata_never_projects_or_executes(admin_client, db_engine, rule_context):
    create_rule(admin_client, rule_context)
    with Session(db_engine) as db:
        original = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "automation.rule_created")
        )
        assert original is not None
        payload, aggregate = dict(original.payload), original.aggregate_id
    identifiers = []
    for changes, properties in (
        ({"title": "private text must not project"}, {}),
        ({"actor_kind": "arbitrary_script"}, {}),
        ({"rule_id": str(uuid4())}, {}),
        ({"changed_fields": None}, {}),
        ({}, {"schema_version": 2}),
        ({}, {"event_type": "automation.execute_script"}),
    ):
        now = datetime.now(UTC)
        with Session(db_engine) as db, db.begin():
            event = OutboxEvent(
                **{
                    "aggregate_type": "automation_rule",
                    "aggregate_id": aggregate,
                    "aggregate_version": 1,
                    "event_type": "automation.rule_created",
                    "schema_version": 1,
                    "payload": {**payload, **changes},
                    "occurred_at": now,
                    "correlation_id": uuid4().hex,
                    "status": "pending",
                    "attempts": 0,
                    "next_attempt_at": now,
                    **properties,
                }
            )
            db.add(event)
            db.flush()
            identifier = event.event_id
        assert not consume_event(db_engine, identifier, datetime.now(UTC))
        identifiers.append(identifier)
    with Session(db_engine) as db:
        for identifier in identifiers:
            event = db.get(OutboxEvent, identifier)
            assert event.status == "dead" and event.last_error_code == "invalid_event"
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM activity_events")) == 0
        assert connection.scalar(text("SELECT count(*) FROM automation_executions")) == 0
