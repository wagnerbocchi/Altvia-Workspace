import os
import time
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from altvia import management
from altvia.models import OutboxEvent
from conftest import TEST_PASSWORD
from sqlalchemy import select
from sqlalchemy.orm import Session


@pytest.fixture
def broker_settings(settings):
    from altvia.config import WorkerSettings
    from redis import Redis

    if os.environ.get("ALTVIA_ALLOW_TEST_DB") != "1" or not os.environ.get("ALTVIA_REDIS_URL"):
        pytest.fail("Worker integration requires isolated guarded PostgreSQL and Redis")
    config = WorkerSettings(
        database_url=settings.database_url, redis_url=os.environ["ALTVIA_REDIS_URL"]
    )
    client = Redis.from_url(config.redis_url.get_secret_value())
    client.flushdb()  # Only the harness's explicitly disposable Redis service.
    yield config
    client.flushdb()
    client.close()


def test_real_json_transport_recovers_redis_loss_without_duplicate_effect(
    broker_settings, db_engine, seeded_user
):
    from altvia.models import ActivityEvent
    from altvia.worker import build_worker, dispatch_once

    with Session(db_engine) as db, db.begin():
        management.create_user(db, "queue@example.test", "Queue", TEST_PASSWORD)
    broker, worker, actor = build_worker(db_engine, broker_settings)
    now = datetime.now(UTC)
    try:
        assert dispatch_once(db_engine, actor, now) == 1
        broker.client.flushdb()  # Lost transport is recovered from authoritative leases.
        assert dispatch_once(db_engine, actor, now + timedelta(seconds=31)) == 1
        worker.start()
        for _ in range(100):
            with Session(db_engine) as db:
                rows = list(db.scalars(select(ActivityEvent)))
                if rows:
                    assert len(rows) == 1
                    break
            time.sleep(0.05)
        else:
            pytest.fail("Real Redis consumer did not project the durable event")
        with Session(db_engine) as db:
            event = db.scalar(select(OutboxEvent))
            assert event.status == "delivered" and event.attempts == 2
        assert TEST_PASSWORD not in actor.message(str(event.event_id)).encode().decode()
        actor.send(str(event.event_id))  # Redelivery after committed effect.
        broker.join("identity", timeout=5000)
        worker.join()
        with Session(db_engine) as db:
            assert len(list(db.scalars(select(ActivityEvent)))) == 1
    finally:
        worker.stop(timeout=5000)
        broker.client.close()


def test_dispatch_cancellation_leaves_remaining_leases_recoverable(
    broker_settings, db_engine, seeded_user, monkeypatch
):
    from altvia.worker import build_worker, dispatch_once

    with Session(db_engine) as db, db.begin():
        management.create_user(db, "cancel@example.test", "Cancel", TEST_PASSWORD)
        for active in (False, True, False, True):
            management.set_account_active(db, "cancel@example.test", active)
    broker, worker, actor = build_worker(db_engine, broker_settings)
    stopped = Event()
    original = actor.send

    def send_once(identifier):
        result = original(identifier)  # Real JSON message goes through authenticated Redis.
        stopped.set()
        return result

    monkeypatch.setattr(actor, "send", send_once)
    try:
        assert dispatch_once(db_engine, actor, datetime.now(UTC), stopped) == 1
        with Session(db_engine) as db:
            rows = list(db.scalars(select(OutboxEvent)))
            assert len(rows) == 5 and all(
                row.status == "processing" and row.lease_until is not None for row in rows
            )
    finally:
        broker.client.close()
