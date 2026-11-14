"""Native SLA cursor, concurrency, immutable artifact and private-event boundaries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

from altvia import business_time, client_registry
from altvia.activity import consume_event
from altvia.models import BusinessCalendarRevision, Client, OutboxEvent
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_automation_rules import queue_version, rule_context
from test_sla_configuration import (
    calendar_body,
    collection,
    create_calendar,
    create_policy,
    patch,
    policy_body,
    reviewed,
)
from test_team_api import admin_client, preconditions, sign_in

__all__ = ["admin_client", "rule_context"]


def test_cursors_bind_kind_customer_and_current_authority_without_counts(
    admin_client, db_engine, rule_context, seeded_user
):
    refs = rule_context
    paths = {create_calendar(admin_client, refs) for _ in range(2)}
    client_ids = [path.rsplit("/", 1)[1] for path in paths]
    first = admin_client.get(collection(refs), params={"client_id": refs["client_id"], "limit": 1})
    assert first.status_code == 200
    cursor = first.json()["next_cursor"]
    assert cursor and "total" not in first.json()
    second = admin_client.get(
        collection(refs), params={"client_id": refs["client_id"], "limit": 1, "cursor": cursor}
    )
    assert second.status_code == 200 and second.json()["next_cursor"] is None
    assert {first.json()["items"][0]["id"], second.json()["items"][0]["id"]} == set(client_ids)
    assert (
        admin_client.get(
            collection(refs, "sla-policies"),
            params={"client_id": refs["client_id"], "cursor": cursor},
        ).status_code
        == 422
    )
    with Session(db_engine) as db, db.begin():
        now = datetime.now(UTC)
        other = Client(name="Other synthetic customer", active=True, created_at=now, updated_at=now)
        db.add(other)
        db.flush()
        other_id = str(other.id)
        client_registry.set_client_access(
            db, "employee@example.test", other.id, "operations_manager"
        )
    sign_in(admin_client, "employee@example.test")
    assert (
        admin_client.get(
            collection(refs), params={"client_id": other_id, "cursor": cursor}
        ).status_code
        == 422
    )
    foreign_refs = {**refs, "client_id": other_id}
    foreign_calendar = create_calendar(admin_client, foreign_refs)
    denied = admin_client.post(
        collection(refs, "sla-policies"),
        json=policy_body(refs, foreign_calendar),
        headers=preconditions(queue_version(admin_client, refs)),
    )
    assert denied.status_code == 404
    assert (
        admin_client.post(
            collection(refs, "sla-policies"),
            json=policy_body(refs, next(iter(paths)), category_id=str(uuid4())),
            headers=preconditions(queue_version(admin_client, refs)),
        ).status_code
        == 404
    )
    with db_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM client_access_grants WHERE user_id=:actor AND client_id=:client"),
            {"actor": seeded_user, "client": UUID(refs["client_id"])},
        )
    # Current scope is checked before parsing even this formerly valid cursor.
    assert (
        admin_client.get(
            collection(refs), params={"client_id": refs["client_id"], "cursor": "malformed"}
        ).status_code
        == 404
    )


def test_explicit_same_name_timezone_refresh_freezes_new_rules_and_retains_old_policy(
    admin_client, db_engine, rule_context, monkeypatch
):
    refs = rule_context
    path = create_calendar(admin_client, refs)
    policy = create_policy(admin_client, refs, path)
    original = admin_client.get(path).json()
    actual = business_time.freeze_timezone("Etc/GMT+1")
    refreshed = business_time.FrozenZone("UTC", actual.tzif, actual.sha256)
    calls = []

    def installed(name):
        calls.append(name)
        return refreshed

    monkeypatch.setattr(business_time, "freeze_timezone", installed)
    assert patch(admin_client, path, name="Metadata edit").status_code == 200
    assert calls == []
    headers = reviewed(admin_client, path)
    assert admin_client.patch(path, json={"timezone": "UTC"}, headers=headers).status_code == 200
    changed = admin_client.get(path).json()
    assert calls == ["UTC"] and changed["version"] == 3
    assert changed["tzif_sha256"] == refreshed.sha256 != original["tzif_sha256"]
    assert admin_client.get(policy).json()["calendar_version"] == 1
    assert patch(admin_client, path, name="Later metadata").status_code == 200
    assert admin_client.patch(path, json={"timezone": "UTC"}, headers=headers).status_code == 200
    assert calls == ["UTC"]
    with Session(db_engine) as db:
        revisions = list(
            db.scalars(select(BusinessCalendarRevision).order_by(BusinessCalendarRevision.version))
        )
        assert [r.tzif_sha256 for r in revisions] == [
            original["tzif_sha256"],
            original["tzif_sha256"],
            refreshed.sha256,
            refreshed.sha256,
        ]
    assert (
        patch(admin_client, policy, calendar_id=original["id"], calendar_version=3).status_code
        == 200
    )
    assert admin_client.get(policy).json()["calendar_version"] == 3


def test_concurrent_protected_create_has_one_effect_and_reviewed_edit_has_one_winner(
    admin_client, db_engine, rule_context
):
    refs = rule_context
    path = collection(refs)
    headers = preconditions(queue_version(admin_client, refs))
    barrier = Barrier(2)

    def create():
        barrier.wait()
        return admin_client.post(path, json=calendar_body(refs), headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json() == results[1].json()
    detail = path + "/" + results[0].json()["calendar_id"]
    original = admin_client.get(detail).json()
    headers = reviewed(admin_client, detail)
    barrier = Barrier(2)

    def edit(name):
        barrier.wait()
        return admin_client.patch(
            detail, json={"name": name}, headers={**headers, "Idempotency-Key": uuid4().hex}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ["First edit", "Second edit"]))
    assert sorted(r.status_code for r in results) == [200, 409]
    current = admin_client.get(detail).json()
    assert current["version"] == 2 and current["queue_version"] == original["queue_version"] + 1
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM business_calendars")) == 1
        assert connection.scalar(text("SELECT count(*) FROM business_calendar_revisions")) == 2


def test_private_sla_events_reject_unknown_fields_envelopes_and_shared_content(
    admin_client, db_engine, rule_context
):
    path = create_calendar(admin_client, rule_context)
    assert patch(admin_client, path, name="Second revision").status_code == 200
    policy = create_policy(admin_client, rule_context, path)
    assert patch(admin_client, policy, enabled=True).status_code == 200
    with Session(db_engine) as db:
        events = list(
            db.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_type.in_(["business_calendar", "sla_policy"])
                )
            )
        )
        seeds = [
            (e.aggregate_type, e.aggregate_id, e.aggregate_version, e.event_type, e.payload)
            for e in events
        ]
    identifiers = []
    for kind, resource, version, event_type, payload in seeds:
        variants = [
            {"payload": {**payload, "body": "Must never project"}},
            {"payload": {**payload, "actor_kind": "management_command"}},
            {"aggregate_id": uuid4()},
            {"schema_version": 2},
            {"event_type": kind + ".unknown"},
        ]
        if event_type.endswith(".created"):
            variants.append({"payload": {**payload, "changed_fields": "name"}})
        else:
            variants.append({"payload": {**payload, "changed_fields": "name,name"}})
        for changes in variants:
            now = datetime.now(UTC)
            with Session(db_engine) as db, db.begin():
                event = OutboxEvent(
                    **{
                        "aggregate_type": kind,
                        "aggregate_id": resource,
                        "aggregate_version": version,
                        "event_type": event_type,
                        "schema_version": 1,
                        "payload": payload,
                        "occurred_at": now,
                        "correlation_id": "sla_private_test",
                        "next_attempt_at": now,
                        **changes,
                    }
                )
                db.add(event)
                db.flush()
                identifier = event.event_id
            assert not consume_event(db_engine, identifier, now)
            identifiers.append(identifier)
    with db_engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT count(*) FROM outbox_events WHERE event_id=ANY(:ids) "
                "AND status='dead' AND last_error_code='invalid_event'"
            ),
            {"ids": identifiers},
        ) == len(identifiers)
        assert connection.scalar(text("SELECT count(*) FROM activity_events")) == 0
