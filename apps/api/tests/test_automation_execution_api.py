"""Current source/target scope and protected original-intent execution recovery."""

from uuid import UUID

from sqlalchemy import text
from test_automation_execution import admin_client, consume_available, effect_context, rule_context
from test_automation_rules import patch_rule
from test_team_api import preconditions, sign_in
from test_tickets import ticket

__all__ = ["admin_client", "effect_context", "rule_context"]


def test_execution_page_is_scoped_and_never_returns_lease_or_payload(
    admin_client, db_engine, effect_context
):
    refs = effect_context
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    response = admin_client.get(path + "/automation-executions")
    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert row["state"] == "pending" and row["can_retry"] is False
    assert row["effect"] is None and response.json()["next_cursor"] is None
    assert "lease_token" not in row and "payload" not in row
    consume_available(db_engine)
    sign_in(admin_client, "agent@example.test")
    visible = admin_client.get(path + "/automation-executions", params={"limit": 1})
    assert visible.status_code == 200 and len(visible.json()["items"]) == 1
    with db_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM role_bindings WHERE scope_kind='project' AND user_id=:id"),
            {"id": UUID(refs["agent_id"])},
        )
    hidden = admin_client.get(path + "/automation-executions", params={"limit": 1})
    assert hidden.status_code == 200 and hidden.json() == {"items": [], "next_cursor": None}
    assert row["id"] not in hidden.text


def test_execution_retry_reuses_original_intent_without_reviving_a_later_disable(
    admin_client, db_engine, effect_context
):
    refs = effect_context
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE clients SET default_project_id=NULL"))
    consume_available(db_engine)
    collection = path + "/automation-executions"
    response = admin_client.get(collection)
    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert row["state"] == "triage" and row["can_retry"] is True
    retry = collection + "/" + row["id"] + "/retry"
    headers = preconditions(row["version"])
    first = admin_client.post(retry, headers=headers)
    assert first.status_code == 202, first.text
    assert first.json() == {"execution_id": row["id"]}
    assert patch_rule(admin_client, refs["rule_path"], enabled=False).status_code == 200
    repeated = admin_client.post(retry, headers=headers)
    assert repeated.status_code == 200 and repeated.json() == first.json()
    consume_available(db_engine)
    current = admin_client.get(collection).json()["items"][0]
    assert current["state"] == "cancelled" and current["can_retry"] is False
    assert admin_client.post(retry, headers=preconditions(current["version"])).status_code == 409
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 0
        assert connection.scalar(text("SELECT count(*) FROM automation_executions")) == 1
    # Authority is checked before even an already committed minimal receipt.
    sign_in(admin_client, "agent@example.test")
    assert admin_client.post(retry, headers=headers).status_code == 404


def test_retry_strict_headers_body_scope_and_reviewed_version(
    admin_client, db_engine, effect_context
):
    refs = effect_context
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE clients SET default_project_id=NULL"))
    consume_available(db_engine)
    collection = path + "/automation-executions"
    response = admin_client.get(collection)
    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    retry = collection + "/" + row["id"] + "/retry"
    assert admin_client.post(retry).status_code == 428
    assert admin_client.post(retry, headers=preconditions(1)).status_code == 409
    assert (
        admin_client.post(retry, json={}, headers=preconditions(row["version"])).status_code == 422
    )
    for query in ["limit=0", "limit=101", "limit=1&limit=2", "unknown=true", "cursor=wrong"]:
        assert admin_client.get(collection + "?" + query).status_code == 422
    assert (
        admin_client.post(retry + "?force=true", headers=preconditions(row["version"])).status_code
        == 422
    )
    bad = {**preconditions(row["version"]), "If-Match": '"2147483648"'}
    assert admin_client.post(retry, headers=bad).status_code == 422
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(collection).status_code == 404
    assert admin_client.post(retry, headers=preconditions(row["version"])).status_code == 404


def test_actual_api_role_recovers_without_reading_unrelated_outbox_payloads(
    admin_client, db_engine, effect_context, settings
):
    from altvia.main import create_app
    from altvia.provision import provision_runtime
    from fastapi.testclient import TestClient
    from test_runtime_provision import runtime_url

    path = ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE clients SET default_project_id=NULL"))
    consume_available(db_engine)
    url = runtime_url(db_engine)
    provision_runtime(db_engine, url.render_as_string(hide_password=False))
    runtime_settings = settings.model_copy(
        update={
            "database_url": settings.database_url.__class__(
                url.render_as_string(hide_password=False)
            )
        }
    )
    with TestClient(
        create_app(runtime_settings),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        sign_in(client, "employee@example.test")
        response = client.get(path + "/automation-executions")
        assert response.status_code == 200, response.text
        row = response.json()["items"][0]
        assert row["can_retry"] is True
        response = client.post(
            path + "/automation-executions/" + row["id"] + "/retry",
            headers=preconditions(row["version"]),
        )
        assert response.status_code == 202, response.text


def test_assignment_view_hides_other_events_and_unexpected_payload_fields(
    admin_client, db_engine, effect_context
):
    import pytest
    from altvia.provision import provision_runtime
    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError
    from test_runtime_provision import runtime_url

    ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    with db_engine.begin() as connection:
        total = connection.scalar(text("SELECT count(*) FROM outbox_events"))
        assert total > 1
        connection.execute(
            text(
                "UPDATE outbox_events SET payload=payload || "
                "jsonb_build_object('unexpected','private-canary-not-an-assignment-field') "
                "WHERE event_id=(SELECT source_event_id FROM automation_executions)"
            )
        )
    url = runtime_url(db_engine)
    provision_runtime(db_engine, url.render_as_string(hide_password=False))
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT * FROM automation_assignment_sources")).all()
            assert len(rows) == 1 and rows[0].unexpected_fields is True
            assert "private-canary" not in str(rows)
            assert rows[0].event_type == "ticket.assigned"
        for statement in (
            "SELECT payload FROM outbox_events",
            "SELECT * FROM outbox_events",
            "UPDATE automation_assignment_sources SET schema_version=99",
        ):
            with pytest.raises(DBAPIError) as caught, engine.begin() as connection:
                connection.execute(text(statement))
            assert caught.value.orig.sqlstate in {"42501", "55000"}
    finally:
        engine.dispose()
    consume_available(db_engine)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 0
        assert (
            connection.scalar(text("SELECT error_code FROM automation_executions"))
            == "invalid_event"
        )
