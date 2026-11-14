"""Native creation/reopen snapshots, rollback and legacy replay boundaries."""

from uuid import UUID, uuid4

import pytest
from altvia import provision
from altvia.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from test_automation_rules import queue_version, rule_context
from test_runtime_provision import runtime_url
from test_sla_configuration import create_calendar, create_policy, patch
from test_team_api import admin_client, preconditions, sign_in
from test_tickets import create, ticket, transition

__all__ = ["admin_client", "rule_context"]

TABLES = {"ticket_sla_states", "ticket_sla_goals", "ticket_sla_acceptances", "ticket_sla_events"}


def test_api_credential_can_only_initialize_cycles_not_impersonate_evaluation(
    admin_client, db_engine, rule_context, settings
):
    require_storage(db_engine)
    enabled(admin_client, rule_context)
    app_url = runtime_url(db_engine)
    worker_url = runtime_url(db_engine).set(username="altvia_worker")
    provision.provision_runtime(
        db_engine,
        app_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
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
        path = ticket(client, rule_context)
        change(client, path, "open")
    app = create_engine(app_url, hide_parameters=True)
    worker = create_engine(worker_url, hide_parameters=True)
    try:
        for statement in (
            "UPDATE ticket_sla_states SET state='ready'",
            "UPDATE ticket_sla_goals SET elapsed_us=1",
            "INSERT INTO ticket_sla_states(ticket_id,evaluated_at) "
            "SELECT ticket_id,now() FROM ticket_sla_states",
            "INSERT INTO ticket_sla_goals(ticket_id,elapsed_us) "
            "SELECT ticket_id,1 FROM ticket_sla_goals",
            "INSERT INTO ticket_sla_goals(ticket_id,outcome) "
            "SELECT ticket_id,'fulfilled' FROM ticket_sla_goals",
        ):
            with app.begin() as connection, pytest.raises(DBAPIError) as error:
                connection.execute(text(statement))
            assert error.value.orig.sqlstate == "42501"
        for statement in (
            "INSERT INTO ticket_sla_states(ticket_id) SELECT id FROM tickets",
            "UPDATE tickets SET status='resolved'",
            "SELECT body_text FROM ticket_messages",
        ):
            with worker.begin() as connection, pytest.raises(DBAPIError) as error:
                connection.execute(text(statement))
            assert error.value.orig.sqlstate == "42501"
    finally:
        app.dispose()
        worker.dispose()


def require_storage(engine):
    with engine.connect() as connection:
        actual = {
            name
            for name in TABLES
            if connection.scalar(text("SELECT to_regclass(:name)"), {"name": "public." + name})
        }
    assert actual == TABLES, "Missing native SLA cycle/evidence persistence"


def enabled(client, refs):
    calendar = create_calendar(client, refs)
    policy = create_policy(client, refs, calendar)
    assert patch(client, policy, enabled=True).status_code == 200
    return calendar, policy


def change(client, path, target, key=None):
    version = client.get(path).json()["version"]
    result = transition(client, path, version, target, "Synthetic lifecycle reason", key)
    assert result.status_code == 200, result.text
    return result


def test_real_creation_records_unconfigured_cycle_without_targets_or_clock_work(
    admin_client, db_engine, rule_context
):
    require_storage(db_engine)
    path = ticket(admin_client, rule_context)
    with db_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT s.cycle_number,s.start_version,s.start_at,s.start_status,s.policy_id,"
                "s.state,s.next_check_at,h.occurred_at FROM ticket_sla_states s "
                "JOIN ticket_status_history h ON h.ticket_id=s.ticket_id "
                "AND h.version=s.start_version"
            )
        ).one()
        assert row[0:2] == (1, 1) and row[2] == row[7] and row[3] == "new"
        assert row[4:7] == (None, "unconfigured", None)
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_goals")) == 0
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_acceptances")) == 0
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_events")) == 0
    assert admin_client.get(path).json()["version"] == 1


def test_creation_freezes_policy_calendar_and_initial_selector_without_changing_legacy_event(
    admin_client, db_engine, rule_context
):
    require_storage(db_engine)
    refs = rule_context
    calendar, policy = enabled(admin_client, refs)
    path = ticket(admin_client, refs)
    initial = admin_client.get(policy).json()
    assert patch(admin_client, calendar, name="Later calendar").status_code == 200
    assert patch(admin_client, policy, first_response_minutes=90).status_code == 200
    with db_engine.connect() as connection:
        snapshot = connection.execute(
            text(
                "SELECT s.policy_id,s.policy_version,s.initial_category_id,s.initial_priority,"
                "r.calendar_version,r.first_response_minutes,s.state FROM ticket_sla_states s "
                "JOIN sla_policy_revisions r ON r.policy_id=s.policy_id "
                "AND r.version=s.policy_version"
            )
        ).one()
        assert snapshot[:2] == (UUID(initial["id"]), 2)
        assert snapshot[2:6] == (UUID(refs["category_id"]), "high", 1, 60)
        assert snapshot[6] == "evaluating"
        goals = list(
            connection.execute(
                text(
                    "SELECT goal,last_history_version,current_status,elapsed_us,"
                    "search_remaining_us "
                    "FROM ticket_sla_goals ORDER BY goal"
                )
            )
        )
        assert goals == [
            ("first_response", 1, "new", 0, 60 * 60_000_000),
            ("resolution", 1, "new", 0, 240 * 60_000_000),
        ]
        event = connection.execute(
            text(
                "SELECT schema_version,payload FROM outbox_events "
                "WHERE aggregate_type='ticket' AND event_type='ticket.created'"
            )
        ).one()
        assert event[0] == 1
        assert set(event[1]) == {"actor_id", "actor_kind", "ticket_id", "client_id", "queue_id"}
    assert admin_client.get(path).json()["version"] == 1


def test_reopen_selects_new_revision_once_and_old_create_transition_replays_do_not_rebase(
    admin_client, db_engine, rule_context
):
    require_storage(db_engine)
    refs = rule_context
    _, policy = enabled(admin_client, refs)
    queue = "/api/v1/ticket-queues/" + refs["queue_id"]
    assert (
        admin_client.patch(
            queue,
            json={"allow_reopen": True},
            headers=preconditions(queue_version(admin_client, refs)),
        ).status_code
        == 200
    )
    key = uuid4().hex
    created = create(admin_client, refs, key)
    assert created.status_code == 201
    path = "/api/v1/tickets/" + created.json()["ticket_id"]
    change(admin_client, path, "open")
    resolved_key = uuid4().hex
    change(admin_client, path, "resolved", resolved_key)
    assert patch(admin_client, policy, resolution_minutes=480).status_code == 200
    reopen_key = uuid4().hex
    reopened = change(admin_client, path, "open", reopen_key)
    assert (
        transition(admin_client, path, 3, "open", "Synthetic lifecycle reason", reopen_key).json()
        == reopened.json()
    )
    change(admin_client, path, "open")
    assert (
        transition(
            admin_client, path, 2, "resolved", "Synthetic lifecycle reason", resolved_key
        ).status_code
        == 200
    )
    assert create(admin_client, refs, key).status_code == 200
    with db_engine.connect() as connection:
        rows = list(
            connection.execute(
                text(
                    "SELECT cycle_number,start_version,start_status,policy_version "
                    "FROM ticket_sla_states ORDER BY cycle_number"
                )
            )
        )
        assert rows == [(1, 1, "new", 2), (2, 4, "open", 3)]
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_goals")) == 4
        assert connection.scalar(text("SELECT count(*) FROM ticket_status_history")) == 4


def test_selected_archived_calendar_rolls_back_native_ticket_history_and_receipt(
    admin_client, db_engine, rule_context
):
    require_storage(db_engine)
    calendar, _ = enabled(admin_client, rule_context)
    assert patch(admin_client, calendar, active=False).status_code == 200
    key = uuid4().hex
    denied = create(admin_client, rule_context, key)
    assert denied.status_code == 409 and denied.json()["code"] == "sla_configuration_unavailable"
    with db_engine.connect() as connection:
        for table in ("tickets", "ticket_status_history", "ticket_sla_states", "ticket_sla_goals"):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        assert (
            connection.scalar(
                text("SELECT count(*) FROM outbox_events WHERE aggregate_type='ticket'")
            )
            == 0
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM idempotency_records WHERE key=:key"), {"key": key}
            )
            == 0
        )
    assert patch(admin_client, calendar, active=True).status_code == 200
    assert create(admin_client, rule_context, key).status_code == 201


def test_partial_goal_write_failure_rolls_back_entire_native_creation(
    admin_client, db_engine, rule_context
):
    require_storage(db_engine)
    enabled(admin_client, rule_context)
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE ticket_sla_goals ADD CONSTRAINT synthetic_reject_resolution "
                "CHECK(goal<>'resolution') NOT VALID"
            )
        )
    try:
        result = create(admin_client, rule_context)
        assert result.status_code == 503
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE ticket_sla_goals DROP CONSTRAINT synthetic_reject_resolution")
            )
    with db_engine.connect() as connection:
        for table in ("tickets", "ticket_status_history", "ticket_sla_states", "ticket_sla_goals"):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        assert (
            connection.scalar(
                text("SELECT count(*) FROM outbox_events WHERE aggregate_type='ticket'")
            )
            == 0
        )
