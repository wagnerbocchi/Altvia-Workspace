"""Read-only current scoped SLA outcomes and preserved paged cycles."""

from uuid import uuid4

from altvia import provision
from altvia.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_automation_rules import rule_context
from test_runtime_provision import runtime_url
from test_sla_cycles import change
from test_sla_execution import owner, tracked
from test_team_api import admin_client, sign_in
from test_tickets import ticket

__all__ = ["admin_client", "rule_context"]


def test_real_frozen_outcomes_are_read_only_without_private_evidence(
    admin_client, db_engine, rule_context
):
    path, _, calendar, policy = tracked(admin_client, db_engine, rule_context)
    assert owner().evaluate_due(db_engine) == 1
    with db_engine.connect() as connection:
        before = connection.execute(
            text("SELECT version,evaluated_at FROM ticket_sla_states")
        ).one()
    response = admin_client.get(path + "/sla")
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {"current", "history", "next_cursor", "observed_at"}
    cycle = data["current"]
    assert cycle["number"] == 1 and cycle["state"] == "ready"
    assert (
        cycle["policy_name"] == admin_client.get(policy).json()["name"]
        and cycle["calendar_name"] == admin_client.get(calendar).json()["name"]
    )
    assert cycle["first_response"]["status"] == "breached"
    assert cycle["first_response"]["target_minutes"] == 1
    assert cycle["first_response"]["breached_at"] and not cycle["first_response"]["corrected"]
    assert cycle["first_response"]["remaining_business_seconds"] == 0
    assert not {"delivery_id", "policy_id", "tzif", "source_event_id", "source_delivery_id"} & set(
        cycle
    )
    assert data["history"] == [] and data["next_cursor"] is None
    assert admin_client.get(path + "/sla").status_code == 200
    with db_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version,evaluated_at FROM ticket_sla_states")).one()
            == before
        )

    sign_in(admin_client, "viewer@example.test")
    assert admin_client.get(policy).status_code == 404
    assert admin_client.get(path + "/sla").json()["current"]["policy_name"] == cycle["policy_name"]


def test_unconfigured_and_legacy_cycles_never_invent_targets(admin_client, db_engine, rule_context):
    path = ticket(admin_client, rule_context)
    response = admin_client.get(path + "/sla")
    assert response.status_code == 200, response.text
    cycle = response.json()["current"]
    assert cycle["state"] == "unconfigured" and cycle["first_response"] is None
    change(admin_client, path, "open")
    change(admin_client, path, "resolved")
    assert admin_client.get(path + "/sla").json()["current"]["end_at"]
    # Owner-only fixture represents an actual pre-migration ticket, not backfill.
    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM ticket_sla_states"))
    assert admin_client.get(path + "/sla").json()["current"] is None
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE ticket_queues SET allow_reopen=true"))
    change(admin_client, path, "open")
    assert admin_client.get(path + "/sla").json()["current"]["number"] == 1


def test_cycle_paging_is_actor_ticket_bound_and_hidden_scope_precedes_cursor(
    admin_client, db_engine, rule_context
):
    path = ticket(admin_client, rule_context)
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE ticket_queues SET allow_reopen=true"))
    for _ in range(3):
        change(admin_client, path, "open")
        change(admin_client, path, "resolved")
    change(admin_client, path, "open")
    first = admin_client.get(path + "/sla?limit=1")
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["current"]["number"] == 4 and data["history"][0]["number"] == 3
    cursor = data["next_cursor"]
    second = admin_client.get(path + "/sla", params={"cursor": cursor, "limit": 1})
    assert second.status_code == 200 and second.json()["history"][0]["number"] == 2
    other = ticket(admin_client, rule_context)
    assert admin_client.get(other + "/sla", params={"cursor": cursor}).status_code == 422
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path + "/sla?cursor=invalid").status_code == 404
    assert (
        admin_client.get("/api/v1/tickets/" + str(uuid4()) + "/sla?cursor=invalid").status_code
        == 404
    )


def test_stale_failed_and_new_history_remain_explicit(admin_client, db_engine, rule_context):
    path, _, _, _ = tracked(admin_client, db_engine, rule_context)
    assert owner().evaluate_due(db_engine) == 1
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE ticket_sla_states SET evaluated_at=now()-interval '2 minutes'")
        )
    result = admin_client.get(path + "/sla")
    assert result.status_code == 200, result.text
    assert result.json()["current"]["state"] == "stale"
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE ticket_sla_states SET evaluated_at=now()"))
    change(admin_client, path, "open")
    assert admin_client.get(path + "/sla").json()["current"]["state"] == "evaluating"
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE ticket_sla_states SET state='unavailable',safe_error='timing_inconsistent'"
            )
        )
    cycle = admin_client.get(path + "/sla").json()["current"]
    assert cycle["state"] == "unavailable" and cycle["safe_error"] == "timing_inconsistent"


def test_strict_query_and_restricted_api_role_outcome_read(
    admin_client, db_engine, rule_context, settings
):
    path, _, _, _ = tracked(admin_client, db_engine, rule_context)
    app_url = runtime_url(db_engine)
    provision.provision_runtime(
        db_engine,
        app_url.render_as_string(hide_password=False),
        app_url.set(username="altvia_worker").render_as_string(hide_password=False),
    )
    config = settings.model_copy(
        update={
            "database_url": settings.database_url.__class__(
                app_url.render_as_string(hide_password=False)
            )
        }
    )
    with TestClient(
        create_app(config),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        sign_in(client, "employee@example.test")
        response = client.get(path + "/sla")
        assert response.status_code == 200, response.text
        for query in (
            "?limit=0",
            "?limit=101",
            "?limit=1&limit=2",
            "?unknown=1",
            "?cursor=invalid",
        ):
            assert client.get(path + "/sla" + query).status_code == 422
