from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from altvia import management
from altvia.models import OutboxEvent
from conftest import TEST_PASSWORD
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_team_api import sign_in


def test_real_identity_activity_projection_feed_and_replay(client, db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        management.bootstrap_admin(db, "admin@example.test", "Admin", TEST_PASSWORD)
    sign_in(client, "admin@example.test")
    response = client.get("/api/v1/identity-activity")
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}
    from altvia.activity import claim_events, consume_event
    from altvia.models import ActivityEvent, ProcessedEvent

    now = datetime.now(UTC)
    leases = claim_events(db_engine, now)
    assert len(leases) == 2
    for event_id, _ in leases:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert (
                sum(
                    pool.map(
                        lambda _, current_id=event_id: consume_event(db_engine, current_id, now),
                        range(2),
                    )
                )
                == 1
            )
        assert consume_event(db_engine, event_id, now) is False
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(ActivityEvent)) == 2
        assert db.scalar(select(func.count()).select_from(ProcessedEvent)) == 2
        assert all(e.status == "delivered" for e in db.scalars(select(OutboxEvent)))
    first = client.get("/api/v1/identity-activity?limit=1").json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = client.get(
        "/api/v1/identity-activity", params={"limit": 1, "cursor": first["next_cursor"]}
    ).json()
    assert (
        len(second["items"]) == 1
        and second["items"][0]["event_id"] != first["items"][0]["event_id"]
    )
    assert second["next_cursor"] is None
    assert TEST_PASSWORD not in str(first) and "password_hash" not in str(first)


def test_activity_acl_and_strict_collection_queries(client):
    assert client.get("/api/v1/identity-activity").status_code == 401
    sign_in(client, "employee@example.test")
    assert client.get("/api/v1/identity-activity").status_code == 403


def test_lease_reclaim_fences_late_publisher_and_logical_dead_letter(db_engine, seeded_user):
    from altvia.activity import claim_events, consume_event, publication_failed, replay_event

    with Session(db_engine) as db, db.begin():
        management.create_user(db, "new@example.test", "New", TEST_PASSWORD)
    now = datetime.now(UTC)
    event_id, first = claim_events(db_engine, now)[0]
    assert claim_events(db_engine, now) == []
    assert claim_events(db_engine, now + timedelta(seconds=31)) == [
        (event_id, now + timedelta(seconds=61))
    ]
    assert publication_failed(db_engine, event_id, first, now, "broker_unavailable") is False
    with Session(db_engine) as db, db.begin():
        row = db.get(OutboxEvent, event_id)
        row.event_type = "unregistered.actor"
    assert consume_event(db_engine, event_id, now) is False
    with Session(db_engine) as db:
        row = db.get(OutboxEvent, event_id)
        assert row.status == "dead" and row.last_error_code == "unsupported_event"
    assert consume_event(db_engine, event_id, now) is False
    with Session(db_engine) as db, db.begin():
        db.get(OutboxEvent, event_id).event_type = "identity.user_created"
    assert replay_event(db_engine, event_id, now)
    assert consume_event(db_engine, event_id, now)
    assert replay_event(db_engine, event_id, now) is False


def test_publication_failure_backs_off_and_exhausted_lease_does_not_discard_last_job(
    db_engine, seeded_user
):
    from altvia.activity import claim_events, consume_event, publication_failed

    with Session(db_engine) as db, db.begin():
        management.create_user(db, "backoff@example.test", "New", TEST_PASSWORD)
    now = datetime.now(UTC)
    event_id, lease = claim_events(db_engine, now)[0]
    assert publication_failed(db_engine, event_id, lease, now, "broker_unavailable")
    assert not claim_events(db_engine, now)
    with Session(db_engine) as db, db.begin():
        row = db.get(OutboxEvent, event_id)
        assert now + timedelta(seconds=5) <= row.next_attempt_at <= now + timedelta(seconds=6)
        row.attempts = 7
    [(same_id, _)] = claim_events(db_engine, now + timedelta(seconds=7))
    assert same_id == event_id
    # The eighth published attempt can finish before its lease expires.
    assert consume_event(db_engine, event_id, now + timedelta(seconds=8))


@pytest.mark.parametrize(
    "payload",
    [
        {"actor_kind": "management_command", "actor_id": None, "password": "must-never-project"},
        {"actor_kind": "root", "actor_id": None},
        {"actor_kind": "user", "actor_id": "not-a-uuid"},
        {"actor_kind": "user", "actor_id": None},
    ],
)
def test_hostile_event_payload_is_quarantined_without_data_leak(db_engine, seeded_user, payload):
    from altvia.activity import consume_event
    from altvia.models import ActivityEvent

    now = datetime.now(UTC)
    with Session(db_engine) as db, db.begin():
        row = OutboxEvent(
            event_id=uuid4(),
            aggregate_type="identity",
            aggregate_id=seeded_user,
            aggregate_version=1,
            event_type="identity.user_created",
            schema_version=1,
            payload=payload,
            occurred_at=now,
            correlation_id="proof",
            status="pending",
            attempts=0,
            next_attempt_at=now,
        )
        db.add(row)
        event_id = row.event_id
    assert consume_event(db_engine, event_id, now) is False
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"
        assert db.scalar(select(func.count()).select_from(ActivityEvent)) == 0
