"""Native scoped SLA configuration, frozen revisions and protected write intent."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from altvia.activity import consume_event
from sqlalchemy import text
from test_automation_rules import queue_version, rule_context
from test_team_api import admin_client, preconditions, sign_in

__all__ = ["admin_client", "rule_context"]


def test_selected_policy_specificity_precedes_reference_eligibility(
    admin_client, db_engine, rule_context, seeded_user
):
    from uuid import UUID

    from altvia import identity, sla_configuration
    from sqlalchemy.orm import Session

    refs = rule_context
    calendar = create_calendar(admin_client, refs)
    specific_calendar = create_calendar(admin_client, refs, name="Specific calendar")
    selected = []
    for selector in (
        {},
        {"priority": "high"},
        {"category_id": refs["category_id"]},
        {"category_id": refs["category_id"], "priority": "high"},
    ):
        chosen_calendar = specific_calendar if len(selected) == 3 else calendar
        path = create_policy(admin_client, refs, chosen_calendar, **selector)
        assert patch(admin_client, path, enabled=True).status_code == 200
        selected.append(path)

    def choose():
        with Session(db_engine) as db:
            result = sla_configuration.select_revision(
                db,
                UUID(refs["client_id"]),
                UUID(refs["queue_id"]),
                UUID(refs["category_id"]),
                "high",
            )
            return str(result[0].id) if result else None

    assert choose() == selected[3].rsplit("/", 1)[1]
    # Provenance is not a recurring permission token.
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE users SET active=false WHERE id=:id"), {"id": seeded_user})
    assert choose() == selected[3].rsplit("/", 1)[1]
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE users SET active=true WHERE id=:id"), {"id": seeded_user})
    assert patch(admin_client, specific_calendar, active=False).status_code == 200
    with pytest.raises(identity.IdentityError) as error:
        choose()
    assert error.value.status == 409 and error.value.code == "sla_configuration_unavailable"
    assert patch(admin_client, selected[3], enabled=False).status_code == 200
    assert choose() == selected[2].rsplit("/", 1)[1]
    assert patch(admin_client, selected[3], enabled=True).status_code == 409
    assert patch(admin_client, specific_calendar, active=True).status_code == 200
    assert patch(admin_client, selected[3], enabled=True).status_code == 200
    for index in (3, 2, 1, 0):
        assert choose() == selected[index].rsplit("/", 1)[1]
        assert patch(admin_client, selected[index], enabled=False).status_code == 200
    assert choose() is None


def collection(refs, kind="business-calendars"):
    return f"/api/v1/ticket-queues/{refs['queue_id']}/{kind}"


def calendar_body(refs, **changes):
    return {
        "client_id": refs["client_id"],
        "name": "  Synthetic service calendar  ",
        "active": True,
        "timezone": "UTC",
        "windows": [
            {"weekday": 0, "start_minute": 600, "end_minute": 720},
            {"weekday": 0, "start_minute": 540, "end_minute": 600},
        ],
        "holidays": [{"date": "2026-11-10", "label": "  Synthetic holiday  "}],
        **changes,
    }


def create_calendar(client, refs, **changes):
    result = client.post(
        collection(refs),
        json=calendar_body(refs, **changes),
        headers=preconditions(queue_version(client, refs)),
    )
    assert result.status_code == 201, result.text
    return collection(refs) + "/" + result.json()["calendar_id"]


def policy_body(refs, calendar_path, **changes):
    return {
        "client_id": refs["client_id"],
        "name": "Synthetic response policy",
        "calendar_id": calendar_path.rsplit("/", 1)[1],
        "calendar_version": 1,
        "first_response_minutes": 60,
        "resolution_minutes": 240,
        "approach_minutes": 15,
        "pause_states": ["pending_customer"],
        **changes,
    }


def create_policy(client, refs, calendar_path, **changes):
    result = client.post(
        collection(refs, "sla-policies"),
        json=policy_body(refs, calendar_path, **changes),
        headers=preconditions(queue_version(client, refs)),
    )
    assert result.status_code == 201, result.text
    return collection(refs, "sla-policies") + "/" + result.json()["policy_id"]


def reviewed(client, path):
    detail = client.get(path)
    assert detail.status_code == 200, detail.text
    return {
        **preconditions(detail.json()["version"]),
        "If-Match-Queue": f'"{detail.json()["queue_version"]}"',
    }


def patch(client, path, **changes):
    return client.patch(path, json=changes, headers=reviewed(client, path))


def test_calendar_and_disabled_policy_are_real_private_versioned_resources(
    admin_client, db_engine, rule_context, seeded_user
):
    refs = rule_context
    before = queue_version(admin_client, refs)
    calendar = create_calendar(admin_client, refs)
    result = admin_client.get(calendar)
    assert result.status_code == 200, result.text
    value = result.json()
    assert value["name"] == "Synthetic service calendar"
    assert value["version"] == 1 and value["queue_version"] == before + 1
    assert value["can_edit"] is True and value["active"] is True
    assert value["windows"] == [{"weekday": 0, "start_minute": 540, "end_minute": 720}]
    assert value["holidays"] == [{"date": "2026-11-10", "label": "Synthetic holiday"}]
    assert len(value["tzif_sha256"]) == 64 and "tzif" not in value
    assert result.headers["etag"] == '"1"'
    listing = admin_client.get(collection(refs), params={"client_id": refs["client_id"]})
    assert listing.status_code == 200, listing.text
    summary = listing.json()["items"][0]
    assert summary == {
        k: v for k, v in value.items() if k not in {"windows", "holidays", "tzif_sha256"}
    }
    assert listing.json()["next_cursor"] is None and "total" not in listing.json()
    policy = create_policy(admin_client, refs, calendar)
    output = admin_client.get(policy).json()
    assert output["enabled"] is False and output["version"] == 1
    assert output["authorizer_id"] == str(seeded_user)
    assert output["calendar_version"] == 1 and output["queue_version"] == before + 2
    assert output["category_id"] is None and output["priority"] is None
    assert patch(admin_client, policy, enabled=True).status_code == 200
    assert admin_client.get(policy).json()["enabled"] is True
    with db_engine.connect() as connection:
        events = list(
            connection.scalars(
                text(
                    "SELECT event_id FROM outbox_events "
                    "WHERE aggregate_type IN ('business_calendar','sla_policy')"
                )
            )
        )
        assert len(events) == 3
    for event in events:
        assert consume_event(db_engine, event, datetime.now(UTC))
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM business_calendar_revisions")) == 1
        assert connection.scalar(text("SELECT count(*) FROM sla_policy_revisions")) == 2
        assert (
            connection.scalar(
                text("SELECT count(*) FROM activity_events WHERE event_id=ANY(:ids)"),
                {"ids": events},
            )
            == 0
        )


@pytest.mark.parametrize("kind", ["business-calendars", "sla-policies"])
@pytest.mark.parametrize("missing", ["config", "queue", "client_role", "ceiling"])
def test_sla_configuration_requires_every_current_conjunct(
    admin_client, db_engine, rule_context, seeded_user, kind, missing
):
    refs = rule_context
    calendar = create_calendar(admin_client, refs)
    path = calendar if kind == "business-calendars" else create_policy(admin_client, refs, calendar)
    intent = reviewed(admin_client, path)
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
        admin_client.get(
            collection(refs, kind), params={"client_id": refs["client_id"]}
        ).status_code
        == expected
    )
    assert admin_client.patch(path, json={"name": "Denied"}, headers=intent).status_code == expected
    body = calendar_body(refs) if kind == "business-calendars" else policy_body(refs, calendar)
    assert (
        admin_client.post(collection(refs, kind), json=body, headers=preconditions(1)).status_code
        == expected
    )


def test_platform_configuration_never_grants_sla_customer_content(admin_client, rule_context):
    refs = rule_context
    path = create_calendar(admin_client, refs)
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path).status_code == 404
    assert (
        admin_client.get(collection(refs), params={"client_id": refs["client_id"]}).status_code
        == 404
    )
    assert (
        admin_client.post(
            collection(refs), json=calendar_body(refs), headers=preconditions(1)
        ).status_code
        == 404
    )


def test_protected_create_and_patch_replay_preserve_newer_revisions(
    admin_client, db_engine, rule_context
):
    refs = rule_context
    body, headers = calendar_body(refs), preconditions(queue_version(admin_client, refs))
    created = admin_client.post(collection(refs), json=body, headers=headers)
    assert created.status_code == 201, created.text
    path = collection(refs) + "/" + created.json()["calendar_id"]
    intent = reviewed(admin_client, path)
    assert (
        admin_client.patch(path, json={"name": "Revision two"}, headers=intent).status_code == 200
    )
    assert patch(admin_client, path, active=False).status_code == 200
    before = admin_client.get(path).json()
    assert (
        admin_client.patch(path, json={"name": "Revision two"}, headers=intent).status_code == 200
    )
    replay = admin_client.post(collection(refs), json=body, headers=headers)
    assert replay.status_code == 200 and replay.json() == created.json()
    assert admin_client.get(path).json() == before
    assert (
        admin_client.patch(path, json={"name": "Other intent"}, headers=intent).status_code == 409
    )
    assert patch(admin_client, path, active=False).status_code == 200
    assert admin_client.get(path).json() == before
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM business_calendar_revisions")) == 3


def test_committed_timezone_replay_and_omitted_field_do_not_reopen_installed_catalog(
    admin_client, rule_context, monkeypatch
):
    refs = rule_context
    body, headers = calendar_body(refs), preconditions(queue_version(admin_client, refs))
    created = admin_client.post(collection(refs), json=body, headers=headers)
    assert created.status_code == 201, created.text
    path = collection(refs) + "/" + created.json()["calendar_id"]
    original = admin_client.get(path).json()["tzif_sha256"]
    from altvia import business_time

    def unavailable(_):
        raise ValueError("Installed timezone unavailable")

    monkeypatch.setattr(business_time, "freeze_timezone", unavailable)
    assert admin_client.post(collection(refs), json=body, headers=headers).status_code == 200
    assert patch(admin_client, path, name="Metadata only").status_code == 200
    assert admin_client.get(path).json()["tzif_sha256"] == original
    assert patch(admin_client, path, timezone="UTC").status_code == 422


def test_archived_parents_allow_read_noop_disable_and_replay_only(
    admin_client, db_engine, rule_context
):
    refs = rule_context
    calendar = create_calendar(admin_client, refs)
    policy = create_policy(admin_client, refs, calendar)
    assert patch(admin_client, policy, enabled=True).status_code == 200
    intent = reviewed(admin_client, policy)
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE clients SET active=false"))
    assert admin_client.get(calendar).json()["can_edit"] is False
    assert patch(admin_client, calendar, name="Not allowed").status_code == 409
    assert patch(admin_client, calendar, active=False).status_code == 200
    assert (
        admin_client.patch(
            policy,
            json={"enabled": False},
            headers={**intent, "If-Match-Queue": f'"{queue_version(admin_client, refs)}"'},
        ).status_code
        == 200
    )
    assert patch(admin_client, policy, enabled=False).status_code == 200
    assert patch(admin_client, policy, enabled=True).status_code == 409


def test_policy_selector_unique_and_reference_scope_and_revision_checked(
    admin_client, db_engine, rule_context
):
    refs = rule_context
    calendar = create_calendar(admin_client, refs)
    policy = create_policy(admin_client, refs, calendar)
    response = admin_client.post(
        collection(refs, "sla-policies"),
        json=policy_body(refs, calendar),
        headers=preconditions(queue_version(admin_client, refs)),
    )
    assert response.status_code == 409 and response.json()["code"] == "sla_policy_exists"
    assert (
        patch(
            admin_client, policy, calendar_id=calendar.rsplit("/", 1)[1], calendar_version=2
        ).status_code
        == 404
    )
    assert (
        patch(admin_client, policy, calendar_id=str(uuid4()), calendar_version=1).status_code == 404
    )
    assert patch(admin_client, calendar, active=False).status_code == 200
    assert patch(admin_client, policy, enabled=True).status_code == 409
    assert patch(admin_client, policy, enabled=False).status_code == 200


def test_queue_and_own_overflow_roll_back_revisions_and_events(
    admin_client, db_engine, rule_context
):
    refs = rule_context
    calendar = create_calendar(admin_client, refs)
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE ticket_queues SET version=2147483647"))
    assert patch(admin_client, calendar, name="Overflow").status_code == 409
    with db_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM business_calendar_revisions")) == 1
        assert connection.scalar(text("SELECT version FROM business_calendars")) == 1
        connection.execute(text("UPDATE ticket_queues SET version=2"))
        connection.execute(text("UPDATE business_calendars SET version=2147483647"))
        connection.execute(
            text(
                "INSERT INTO business_calendar_revisions SELECT calendar_id,2147483647,"
                "client_id,queue_id,active,name,timezone,windows,holidays,tzif,tzif_sha256,"
                "created_at FROM business_calendar_revisions WHERE version=1"
            )
        )
    assert patch(admin_client, calendar, name="Own overflow").status_code == 409
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM business_calendar_revisions")) == 2
        assert (
            connection.scalar(
                text("SELECT count(*) FROM outbox_events WHERE aggregate_type='business_calendar'")
            )
            == 1
        )


@pytest.mark.parametrize("kind", ["business-calendars", "sla-policies"])
def test_sla_http_strict_query_headers_csrf_and_reviewed_versions(admin_client, rule_context, kind):
    refs = rule_context
    calendar = create_calendar(admin_client, refs)
    path = calendar if kind == "business-calendars" else create_policy(admin_client, refs, calendar)
    headers = reviewed(admin_client, path)
    for missing in ("If-Match", "If-Match-Queue", "Idempotency-Key"):
        result = admin_client.patch(
            path,
            json={"name": "Review"},
            headers={k: v for k, v in headers.items() if k != missing},
        )
        assert result.status_code == 428, result.text
    for header in ("If-Match", "If-Match-Queue"):
        for value in ('W/"1"', '"0"', '"2147483648"', '"1", "2"'):
            result = admin_client.patch(
                path, json={"name": "Review"}, headers={**headers, header: value}
            )
            assert result.status_code == 422, result.text
    for header in headers:
        repeated = [*headers.items(), (header, headers[header])]
        assert (
            admin_client.patch(path, json={"name": "Review"}, headers=repeated).status_code == 422
        )
    assert (
        admin_client.patch(
            path, json={"name": "Review"}, headers={**headers, "If-Match-Queue": '"2147483647"'}
        ).status_code
        == 409
    )
    assert (
        admin_client.patch(
            path, json={"name": "Review"}, headers={**headers, "X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert (
        admin_client.patch(
            path,
            json={"name": "Review"},
            headers={**headers, "Origin": "https://foreign.example.test"},
        ).status_code
        == 403
    )
    for query in (
        "",
        "?client_id=" + refs["client_id"] + "&unknown=1",
        "?client_id=" + refs["client_id"] + "&client_id=" + refs["client_id"],
        "?client_id=" + refs["client_id"] + "&limit=0",
        "?client_id=" + refs["client_id"] + "&limit=101",
    ):
        assert admin_client.get(collection(refs, kind) + query).status_code == 422
    assert admin_client.get(path + "?unknown=1").status_code == 422
    assert (
        admin_client.patch(
            path + "?unknown=1", json={"name": "Review"}, headers=headers
        ).status_code
        == 422
    )
    assert admin_client.delete(path).status_code == 405


def test_policy_protected_replay_noop_and_later_disable_survive_parent_archive(
    admin_client, db_engine, rule_context, seeded_user
):
    refs = rule_context
    calendar = create_calendar(admin_client, refs)
    body = policy_body(refs, calendar)
    headers = preconditions(queue_version(admin_client, refs))
    result = admin_client.post(collection(refs, "sla-policies"), json=body, headers=headers)
    assert result.status_code == 201, result.text
    path = collection(refs, "sla-policies") + "/" + result.json()["policy_id"]
    enabled_intent = reviewed(admin_client, path)
    assert (
        admin_client.patch(path, json={"enabled": True}, headers=enabled_intent).status_code == 200
    )
    assert patch(admin_client, path, enabled=False).status_code == 200
    before = admin_client.get(path).json()
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE clients SET active=false"))
    replay = admin_client.post(collection(refs, "sla-policies"), json=body, headers=headers)
    assert replay.status_code == 200 and replay.json() == result.json()
    assert (
        admin_client.patch(path, json={"enabled": True}, headers=enabled_intent).status_code == 200
    )
    assert (
        patch(admin_client, path, enabled=False, pause_states=["pending_customer"]).status_code
        == 200
    )
    after = admin_client.get(path).json()
    assert {k: v for k, v in after.items() if k != "can_edit"} == {
        k: v for k, v in before.items() if k != "can_edit"
    }
    with db_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM sla_policy_revisions")) == 3
        connection.execute(
            text("DELETE FROM client_access_grants WHERE user_id=:id"), {"id": seeded_user}
        )
    assert (
        admin_client.post(collection(refs, "sla-policies"), json=body, headers=headers).status_code
        == 404
    )
    assert (
        admin_client.patch(path, json={"enabled": True}, headers=enabled_intent).status_code == 404
    )


def test_actual_runtime_configuration_writes_and_worker_private_ack(
    admin_client, db_engine, rule_context, settings
):
    from altvia import provision
    from altvia.main import create_app
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from test_runtime_provision import runtime_url

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
        calendar = create_calendar(client, rule_context)
        policy = create_policy(client, rule_context, calendar)
        assert patch(client, policy, enabled=True).status_code == 200
        assert patch(client, calendar, name="Runtime revision").status_code == 200
        assert client.get(calendar).json()["version"] == 2
    with db_engine.connect() as connection:
        events = list(
            connection.scalars(
                text(
                    "SELECT event_id FROM outbox_events "
                    "WHERE aggregate_type IN ('business_calendar','sla_policy')"
                )
            )
        )
    worker = create_engine(worker_url, hide_parameters=True)
    try:
        for event in events:
            assert consume_event(worker, event, datetime.now(UTC))
    finally:
        worker.dispose()
    with db_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM activity_events WHERE event_id=ANY(:ids)"),
                {"ids": events},
            )
            == 0
        )
