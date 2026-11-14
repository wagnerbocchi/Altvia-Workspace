"""Actual JSON transport and database-owned assignment recovery."""

import time
from datetime import UTC, datetime
from threading import Event

from sqlalchemy import text
from test_automation_execution import admin_client, effect_context, rule_context
from test_tickets import ticket
from test_worker import broker_settings

__all__ = ["admin_client", "effect_context", "rule_context", "broker_settings"]


def test_real_assignment_transport_recovers_lost_message_and_committed_redelivery(
    admin_client, db_engine, effect_context, broker_settings
):
    from altvia import worker as owner
    from altvia.worker import build_worker

    ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    broker, running, _ = build_worker(db_engine, broker_settings)
    try:
        assert "assignment_work" in broker.actors
        assert owner.dispatch_assignment_once(db_engine, broker, datetime.now(UTC)) == 1
        broker.client.flushdb()  # The harness owns this isolated authenticated Redis.
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE automation_executions SET "
                    "lease_until=clock_timestamp()-interval '1 second'"
                )
            )
        assert owner.dispatch_assignment_once(db_engine, broker, datetime.now(UTC)) == 1
        with db_engine.connect() as connection:
            identifier, token = connection.execute(
                text("SELECT id,lease_token FROM automation_executions")
            ).one()
        registered = broker.get_actor("assignment_work")
        payload = registered.message(str(identifier), str(token)).encode().decode()
        assert "Configured assignment work" not in payload and "password" not in payload
        running.start()
        for _ in range(200):
            with db_engine.connect() as connection:
                if connection.scalar(text("SELECT count(*) FROM automation_effects")) == 1:
                    break
            time.sleep(0.05)
        else:
            raise AssertionError("Real assignment worker did not commit the effect")
        registered.send(str(identifier), str(token))
        registered.send("invalid", "invalid")
        broker.join("automation", timeout=5000)
        running.join()
        with db_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM work_items")) == 1
            assert connection.scalar(text("SELECT count(*) FROM automation_effects")) == 1
            assert connection.scalar(text("SELECT attempts FROM automation_executions")) == 2
            assert connection.scalar(text("SELECT state FROM automation_executions")) == "succeeded"
    finally:
        running.stop(timeout=5000)
        broker.client.close()


def test_assignment_dispatch_stop_and_broker_failure_retain_durable_recovery(
    admin_client, db_engine, effect_context, broker_settings, monkeypatch
):
    from altvia import worker as owner
    from redis.exceptions import ConnectionError

    ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    broker, _, _ = owner.build_worker(db_engine, broker_settings)
    stop = Event()
    stop.set()
    try:
        assert hasattr(owner, "dispatch_assignment_once")
        assert owner.dispatch_assignment_once(db_engine, broker, datetime.now(UTC), stop) == 0
        registered = broker.get_actor("assignment_work")

        def unavailable(*args):
            raise ConnectionError("Synthetic transport failure")

        monkeypatch.setattr(registered, "send", unavailable)
        assert owner.dispatch_assignment_once(db_engine, broker, datetime.now(UTC)) == 0
        with db_engine.connect() as connection:
            state, attempts, code, token, until, delayed = connection.execute(
                text(
                    "SELECT state,attempts,error_code,lease_token,lease_until,"
                    "next_attempt_at>clock_timestamp() FROM automation_executions"
                )
            ).one()
        assert (state, attempts, code, token, until, delayed) == (
            "pending",
            1,
            "broker_unavailable",
            None,
            None,
            True,
        )
    finally:
        broker.client.close()
