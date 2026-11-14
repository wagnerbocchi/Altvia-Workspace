"""DB-owned SLA evaluation, native timing and append-only observation facts."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from threading import Barrier
from uuid import UUID

import pytest
from altvia import provision
from altvia.activity import consume_event
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from test_automation_rules import rule_context
from test_runtime_provision import runtime_url
from test_sla_configuration import create_calendar, create_policy, patch
from test_sla_cycles import change
from test_team_api import admin_client
from test_tickets import ticket

__all__ = ["admin_client", "rule_context"]


def owner():
    assert find_spec("altvia.sla_execution") is not None, "Missing durable native SLA evaluator"
    return importlib.import_module("altvia.sla_execution")


def tracked(client, engine, refs, *, first=1, resolution=2):
    calendar = create_calendar(
        client,
        refs,
        holidays=[],
        windows=[{"weekday": n, "start_minute": 0, "end_minute": 1440} for n in range(7)],
    )
    policy = create_policy(
        client,
        refs,
        calendar,
        first_response_minutes=first,
        resolution_minutes=resolution,
        approach_minutes=0,
    )
    assert patch(client, policy, enabled=True).status_code == 200
    path = ticket(client, refs)
    identifier = UUID(path.rsplit("/", 1)[1])
    # This owner-only fixture backdates only the newly created synthetic ticket
    # and its still-unevaluated source/progress in the guarded disposable DB.
    start = datetime.now(UTC) - timedelta(minutes=3)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE tickets SET created_at=:start WHERE id=:id"),
            {"start": start, "id": identifier},
        )
        connection.execute(
            text(
                "UPDATE ticket_status_history SET occurred_at=:start "
                "WHERE ticket_id=:id AND version=1"
            ),
            {"start": start, "id": identifier},
        )
        connection.execute(
            text(
                "UPDATE ticket_sla_states SET start_at=:start,next_check_at=:start "
                "WHERE ticket_id=:id"
            ),
            {"start": start, "id": identifier},
        )
        connection.execute(
            text(
                "UPDATE ticket_sla_goals SET evaluated_through_at=:start,search_through_at=:start "
                "WHERE ticket_id=:id"
            ),
            {"start": start, "id": identifier},
        )
    return path, start, calendar, policy


def test_due_database_clock_observes_each_breach_once_at_exact_deadline(
    admin_client, db_engine, rule_context
):
    worker = owner()
    path, start, _, _ = tracked(admin_client, db_engine, rule_context)
    assert worker.evaluate_due(db_engine) == 1
    with db_engine.connect() as connection:
        rows = list(
            connection.execute(
                text(
                    "SELECT goal,kind,occurred_at,observed_at,observed_ticket_version "
                    "FROM ticket_sla_events ORDER BY goal"
                )
            )
        )
        assert [(r[0], r[1], r[2], r[4]) for r in rows] == [
            ("first_response", "breached", start + timedelta(minutes=1), 1),
            ("resolution", "breached", start + timedelta(minutes=2), 1),
        ]
        assert all(r[3] > r[2] for r in rows)
        assert connection.scalar(text("SELECT state FROM ticket_sla_states")) == "ready"
        assert (
            connection.scalar(
                text("SELECT count(*) FROM ticket_sla_goals WHERE outcome='breached'")
            )
            == 2
        )
    assert worker.evaluate_due(db_engine) == 0
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE ticket_sla_states SET next_check_at=now()-interval '1 second'")
        )
    assert worker.evaluate_due(db_engine) == 1
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_events")) == 2
        assert (
            connection.scalar(
                text("SELECT count(*) FROM outbox_events WHERE event_type='ticket.sla_breached'")
            )
            == 2
        )
    assert admin_client.get(path).json()["version"] == 1


def test_breach_activity_is_a_system_observation_without_private_evidence_or_state_mutation(
    admin_client, db_engine, rule_context
):
    worker = owner()
    path, _, _, _ = tracked(admin_client, db_engine, rule_context)
    assert worker.evaluate_due(db_engine) == 1
    with db_engine.connect() as connection:
        rows = list(
            connection.execute(
                text(
                    "SELECT event_id,payload FROM outbox_events "
                    "WHERE event_type='ticket.sla_breached'"
                )
            )
        )
    assert len(rows) == 2
    for identifier, payload in rows:
        assert payload["actor_id"] is None and payload["actor_kind"] == "sla_worker"
        assert set(payload) == {
            "actor_id",
            "actor_kind",
            "ticket_id",
            "client_id",
            "queue_id",
            "cycle_number",
            "goal",
            "outcome",
            "observed_at",
        }
        assert consume_event(db_engine, identifier, datetime.now(UTC))
        assert not consume_event(db_engine, identifier, datetime.now(UTC))
    activity = admin_client.get(path + "/activity")
    assert activity.status_code == 200, activity.text
    entries = activity.json()["items"]
    assert len(entries) == 2 and {e["actor_kind"] for e in entries} == {"sla_worker"}
    assert all(e["resource_type"] == "ticket" and e["aggregate_version"] == 1 for e in entries)
    assert all(not set(e["details"]) & {"delivery_id", "source_event_id"} for e in entries)
    assert admin_client.get(path).json()["version"] == 1


def test_resolution_fulfills_only_resolution_and_stops_missing_response_under_budget(
    admin_client, db_engine, rule_context
):
    worker = owner()
    path, _, _, _ = tracked(admin_client, db_engine, rule_context, first=60, resolution=240)
    change(admin_client, path, "open")
    change(admin_client, path, "resolved")
    assert worker.evaluate_due(db_engine) == 1
    with db_engine.connect() as connection:
        assert list(
            connection.execute(text("SELECT goal,outcome FROM ticket_sla_goals ORDER BY goal"))
        ) == [("first_response", "unfulfilled"), ("resolution", "fulfilled")]
        end = connection.scalar(text("SELECT end_at FROM ticket_sla_states"))
        assert end == connection.scalar(
            text("SELECT occurred_at FROM ticket_status_history WHERE to_status='resolved'")
        )
        assert connection.scalar(text("SELECT next_check_at FROM ticket_sla_states")) is None
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_events")) == 0


def test_existing_captured_clocks_continue_after_calendar_policy_archive_and_authorizer_exit(
    admin_client, db_engine, rule_context, seeded_user
):
    worker = owner()
    _, _, calendar, policy = tracked(admin_client, db_engine, rule_context)
    assert patch(admin_client, calendar, active=False).status_code == 200
    assert patch(admin_client, policy, enabled=False).status_code == 200
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE users SET active=false WHERE id=:id"), {"id": seeded_user})
    assert worker.evaluate_due(db_engine) == 1
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_events")) == 2
        assert connection.scalar(text("SELECT state FROM ticket_sla_states")) == "ready"


def test_competing_database_workers_have_one_observation_transaction(
    admin_client, db_engine, rule_context
):
    worker = owner()
    tracked(admin_client, db_engine, rule_context)
    barrier = Barrier(2)

    def evaluate():
        barrier.wait()
        return worker.evaluate_due(db_engine)

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _: evaluate(), range(2)))
    assert sorted(counts) == [0, 1]
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_events")) == 2
        assert connection.scalar(text("SELECT version FROM ticket_sla_states")) == 2


def test_actual_worker_evaluates_projects_activity_without_ticket_content_or_initial_writer(
    admin_client, db_engine, rule_context
):
    module = owner()
    tracked(admin_client, db_engine, rule_context)
    worker_url = runtime_url(db_engine).set(username="altvia_worker")
    provision.provision_runtime(
        db_engine,
        runtime_url(db_engine).render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    engine = create_engine(worker_url, hide_parameters=True)
    try:
        assert module.evaluate_due(engine) == 1
        with db_engine.connect() as connection:
            events = list(connection.scalars(text("SELECT event_id FROM ticket_sla_events")))
        for event in events:
            assert consume_event(engine, event, datetime.now(UTC))
        for statement in (
            "UPDATE tickets SET status='resolved'",
            "SELECT body_text FROM ticket_messages",
            "SELECT reason FROM ticket_status_history",
            "UPDATE sla_policy_revisions SET enabled=false",
            "UPDATE ticket_sla_states SET policy_version=policy_version",
            "UPDATE ticket_sla_goals SET goal=goal",
            "INSERT INTO ticket_sla_states(ticket_id) SELECT id FROM tickets",
            "DELETE FROM ticket_sla_events",
        ):
            with engine.begin() as connection, pytest.raises(DBAPIError) as error:
                connection.execute(text(statement))
            assert error.value.orig.sqlstate == "42501"
    finally:
        engine.dispose()


def test_poison_source_defers_safely_without_changing_progress_or_starving_next_cycle(
    admin_client, db_engine, rule_context
):
    worker = owner()
    path, _, _, _ = tracked(admin_client, db_engine, rule_context)
    other = ticket(admin_client, rule_context)
    identifier = UUID(path.rsplit("/", 1)[1])
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE ticket_sla_goals SET current_status='pending_customer' WHERE ticket_id=:id"
            ),
            {"id": identifier},
        )
    assert worker.evaluate_due(db_engine) == 2
    with db_engine.connect() as connection:
        bad = connection.execute(
            text(
                "SELECT state,safe_error,next_check_at,evaluated_at "
                "FROM ticket_sla_states WHERE ticket_id=:id"
            ),
            {"id": identifier},
        ).one()
        assert bad[:2] == ("unavailable", "timing_inconsistent") and bad[2] > bad[3]
        assert (
            connection.scalar(
                text("SELECT max(elapsed_us) FROM ticket_sla_goals WHERE ticket_id=:id"),
                {"id": identifier},
            )
            == 0
        )
        assert (
            connection.scalar(
                text("SELECT state FROM ticket_sla_states WHERE ticket_id=:id"),
                {"id": UUID(other.rsplit("/", 1)[1])},
            )
            == "ready"
        )
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_events")) == 0


def test_second_event_sql_failure_rolls_back_both_clocks_and_first_observation(
    admin_client, db_engine, rule_context
):
    worker = owner()
    tracked(admin_client, db_engine, rule_context)
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE ticket_sla_events ADD CONSTRAINT synthetic_reject_resolution_event "
                "CHECK(goal<>'resolution') NOT VALID"
            )
        )
    try:
        assert worker.evaluate_due(db_engine) == 1
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ticket_sla_events DROP CONSTRAINT "
                    "synthetic_reject_resolution_event"
                )
            )
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_events")) == 0
        assert connection.scalar(text("SELECT max(elapsed_us) FROM ticket_sla_goals")) == 0
        assert (
            connection.scalar(
                text("SELECT count(*) FROM outbox_events WHERE event_type='ticket.sla_breached'")
            )
            == 0
        )
        assert connection.scalar(text("SELECT state FROM ticket_sla_states")) == "unavailable"


@pytest.mark.parametrize("limit", [0, 21, True, "20"])
def test_evaluator_rejects_unbounded_or_coerced_batches_before_database_access(limit):
    with pytest.raises(ValueError):
        owner().evaluate_due(None, limit=limit)
    with pytest.raises(ValueError):
        owner().capture_acceptances(None, limit=limit)


def test_evaluator_cancellation_leaves_next_native_cycle_due(
    admin_client, db_engine, rule_context, monkeypatch
):
    from threading import Event

    module = owner()
    tracked(admin_client, db_engine, rule_context)
    ticket(admin_client, rule_context)
    stop = Event()
    original = module._evaluate

    def evaluate(*args):
        original(*args)
        stop.set()

    monkeypatch.setattr(module, "_evaluate", evaluate)
    assert module.evaluate_due(db_engine, stop=stop) == 1
    with db_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM ticket_sla_states WHERE evaluated_at IS NULL")
            )
            == 1
        )


def test_native_pause_resume_preserves_exact_business_budget(admin_client, db_engine, rule_context):
    module = owner()
    path, start, _, _ = tracked(admin_client, db_engine, rule_context, first=60, resolution=240)
    change(admin_client, path, "open")
    change(admin_client, path, "pending_customer")
    assert module.evaluate_due(db_engine) == 1
    with db_engine.connect() as connection:
        paused = connection.scalar(
            text("SELECT occurred_at FROM ticket_status_history WHERE to_status='pending_customer'")
        )
        goals = list(
            connection.execute(text("SELECT elapsed_us,due_at,outcome FROM ticket_sla_goals"))
        )
        assert all(
            timedelta(microseconds=g[0]) == paused - start and g[1] is None and g[2] == "paused"
            for g in goals
        )
    change(admin_client, path, "open")
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE ticket_sla_states SET next_check_at=now()"))
    assert module.evaluate_due(db_engine) == 1
    with db_engine.connect() as connection:
        resumed = connection.scalar(
            text("SELECT max(occurred_at) FROM ticket_status_history WHERE to_status='open'")
        )
        due = connection.scalar(
            text("SELECT due_at FROM ticket_sla_goals WHERE goal='first_response'")
        )
        assert due == resumed + timedelta(minutes=60) - (paused - start)


def test_long_same_time_history_continues_without_false_projection_or_starving_other_ticket(
    admin_client, db_engine, rule_context, seeded_user
):
    from altvia.models import TicketStatusHistory
    from sqlalchemy.orm import Session

    module = owner()
    path, start, _, _ = tracked(admin_client, db_engine, rule_context, first=60)
    identifier = UUID(path.rsplit("/", 1)[1])
    other = ticket(admin_client, rule_context)
    # Guarded owner fixture represents a long valid immutable history. Same-time
    # ordering still comes from native versions, never broker arrival or a scan cap.
    with Session(db_engine) as db, db.begin():
        previous = "new"
        for version in range(2, 1053):
            status = "open" if version % 2 == 0 else "pending_customer"
            db.add(
                TicketStatusHistory(
                    ticket_id=identifier,
                    actor_id=seeded_user,
                    version=version,
                    from_status=previous,
                    to_status=status,
                    reason="Synthetic long-history fixture",
                    occurred_at=start + timedelta(seconds=1),
                )
            )
            previous = status
        db.execute(
            text("UPDATE tickets SET version=1052,status='open' WHERE id=:id"), {"id": identifier}
        )
    assert module.evaluate_due(db_engine) == 2
    with db_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT state FROM ticket_sla_states WHERE ticket_id=:id"), {"id": identifier}
            )
            == "evaluating"
        )
        assert (
            connection.scalar(
                text("SELECT state FROM ticket_sla_states WHERE ticket_id=:id"),
                {"id": UUID(other.rsplit("/", 1)[1])},
            )
            == "ready"
        )
        assert list(
            connection.execute(
                text(
                    "SELECT last_history_version,due_at FROM ticket_sla_goals WHERE ticket_id=:id"
                ),
                {"id": identifier},
            )
        ) == [(499, None), (499, None)]
    for _ in range(2):
        with db_engine.begin() as connection:
            connection.execute(
                text("UPDATE ticket_sla_states SET next_check_at=now() WHERE ticket_id=:id"),
                {"id": identifier},
            )
        assert module.evaluate_due(db_engine) == 1
    with db_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT state FROM ticket_sla_states WHERE ticket_id=:id"), {"id": identifier}
            )
            == "ready"
        )
        assert (
            connection.scalar(
                text("SELECT min(last_history_version) FROM ticket_sla_goals WHERE ticket_id=:id"),
                {"id": identifier},
            )
            == 1052
        )
