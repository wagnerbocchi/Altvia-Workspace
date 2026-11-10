import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia.activity import WorkEventPayload, consume_event
from altvia.models import IdempotencyRecord, OutboxEvent, WorkItem
from altvia.work_schemas import WorkCreate
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in
from test_work_items import create_work, setup_project

__all__ = ["admin_client"]


def created(client, project_id, labels=None):
    response = create_work(client, project_id, external_participants=labels or ["Terceiro"])
    assert response.status_code == 201, response.text
    return "/api/v1/work-items/" + response.json()["work_item_id"]


def events(db_engine):
    with Session(db_engine) as db:
        return list(
            db.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_type == "work_item"))
        )


def test_external_labels_persist_replace_clear_noop_and_remain_redacted(
    admin_client, seeded_user, db_engine
):
    project_id = setup_project(admin_client, seeded_user)
    path = created(admin_client, project_id, [" Terceiro ", "Fornecedor <script>texto</script>"])
    original = admin_client.get(path).json()
    assert original["external_participants"] == ["Fornecedor <script>texto</script>", "Terceiro"]
    assert original["assignee_ids"] == [] and original["owner_id"] is None
    assert admin_client.get("/api/v1/my-work").json()["items"] == []
    assert (
        admin_client.get("/api/v1/work-items", params={"project_id": project_id}).json()["items"][
            0
        ]["external_participants"]
        == original["external_participants"]
    )
    unchanged = admin_client.patch(
        path,
        json={"external_participants": ["Terceiro", "Fornecedor <script>texto</script>"]},
        headers=preconditions(),
    )
    assert unchanged.status_code == 200 and unchanged.json()["version"] == 1
    assert len(events(db_engine)) == 1
    edited = admin_client.patch(
        path, json={"external_participants": ["Consultoria", "Terceiro"]}, headers=preconditions()
    )
    assert edited.status_code == 200 and edited.json()["version"] == 2
    assert edited.headers["etag"] == '"2"'
    assert admin_client.get(path).json()["external_participants"] == ["Consultoria", "Terceiro"]
    assert (
        admin_client.patch(
            path, json={"title": "Independent"}, headers=preconditions(2)
        ).status_code
        == 200
    )
    assert admin_client.get(path).json()["external_participants"] == ["Consultoria", "Terceiro"]
    cleared = admin_client.patch(path, json={"external_participants": []}, headers=preconditions(3))
    assert cleared.status_code == 200 and cleared.json()["version"] == 4
    assert admin_client.get(path).json()["external_participants"] == []
    values = events(db_engine)
    assert [event.event_type for event in values].count("work_item.assigned") == 0
    assert all(
        "Consultoria" not in str(event.payload) and "Terceiro" not in str(event.payload)
        for event in values
    )
    assert (
        sum(event.payload.get("changed_fields") == "external_participants" for event in values) == 2
    )
    for event in values:
        assert consume_event(db_engine, event.event_id, datetime.now(UTC))
        assert not consume_event(db_engine, event.event_id, datetime.now(UTC))
    feed = admin_client.get(path + "/activity").json()["items"]
    assert len(feed) == 4 and all("Consultoria" not in str(event) for event in feed)


@pytest.mark.parametrize(
    "labels",
    [
        None,
        [""],
        ["   "],
        ["a", " a "],
        ["x" * 151],
        [str(i) for i in range(51)],
        ["a\nb"],
        ["a\rb"],
        ["a\x00b"],
        [3],
    ],
)
def test_external_invalid_create_and_patch_have_no_effect(
    admin_client, seeded_user, db_engine, labels
):
    project_id = setup_project(admin_client, seeded_user)
    assert create_work(admin_client, project_id, external_participants=labels).status_code == 422
    response = create_work(admin_client, project_id)
    assert response.status_code == 201
    path = "/api/v1/work-items/" + response.json()["work_item_id"]
    assert (
        admin_client.patch(
            path, json={"external_participants": labels}, headers=preconditions()
        ).status_code
        == 422
    )
    assert admin_client.get(path).json()["version"] == 1 and len(events(db_engine)) == 1


def test_external_exact_unicode_and_boundaries(admin_client, seeded_user):
    project_id = setup_project(admin_client, seeded_user)
    labels = ["\U0001f9d1" * 150, "Parceiro", "parceiro", *[str(i) for i in range(47)]]
    path = created(admin_client, project_id, labels)
    assert admin_client.get(path).json()["external_participants"] == sorted(labels)


@pytest.mark.parametrize("role", ["agent", "viewer"])
def test_external_metadata_requires_manager_and_never_grants_access(
    admin_client, seeded_user, db_engine, role
):
    from altvia.project_registry import set_project_access

    project_id = setup_project(admin_client, seeded_user)
    path = created(admin_client, project_id)
    assert (
        admin_client.patch(
            path, json={"owner_id": str(seeded_user)}, headers=preconditions()
        ).status_code
        == 200
    )
    with Session(db_engine) as db, db.begin():
        set_project_access(db, "employee@example.test", UUID(project_id), role)
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(path).json()["external_participants"] == ["Terceiro"]
    for labels in [[], ["Terceiro"], ["Another"]]:
        assert (
            admin_client.patch(
                path, json={"external_participants": labels}, headers=preconditions(2)
            ).status_code
            == 403
        )
    assert (
        create_work(
            admin_client, project_id, owner_id=str(seeded_user), external_participants=["Terceiro"]
        ).status_code
        == 403
    )
    if role == "agent":
        assert (
            admin_client.patch(
                path, json={"title": "Agent content"}, headers=preconditions(2)
            ).status_code
            == 200
        )
        assert create_work(admin_client, project_id, owner_id=str(seeded_user)).status_code == 201
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path).status_code == 404
    assert (
        admin_client.patch(
            path, json={"external_participants": ["New"]}, headers=preconditions()
        ).status_code
        == 404
    )


def test_external_legacy_create_fingerprint_and_transition_receipt(
    admin_client, seeded_user, db_engine
):
    project_id = setup_project(admin_client, seeded_user)
    body = {
        "project_id": project_id,
        "title": "Legacy",
        "priority": "medium",
        "work_type": "one_off",
    }
    headers = preconditions()
    result = admin_client.post("/api/v1/work-items", json=body, headers=headers)
    assert result.status_code == 201
    # Simulate the exact pre-expansion canonical body without rewriting its protocol.
    legacy = WorkCreate.model_validate(body).model_dump(
        mode="json", exclude={"external_participants"}
    )
    with Session(db_engine) as db, db.begin():
        record = db.get(
            IdempotencyRecord,
            (seeded_user, "work-create:" + project_id, headers["Idempotency-Key"]),
        )
        record.request_hash = hashlib.sha256(
            json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    replay = admin_client.post(
        "/api/v1/work-items", json={**body, "external_participants": []}, headers=headers
    )
    assert replay.status_code == 200 and replay.json() == result.json()
    path = "/api/v1/work-items/" + result.json()["work_item_id"]
    transition = {"target_status": "in_progress"}
    key = preconditions()
    assert admin_client.post(path + "/transitions", json=transition, headers=key).status_code == 200
    with Session(db_engine) as db, db.begin():
        record = db.get(
            IdempotencyRecord,
            (seeded_user, "work-transition:" + path.rsplit("/", 1)[1], key["Idempotency-Key"]),
        )
        record.result = {k: v for k, v in record.result.items() if k != "external_participants"}
    replay = admin_client.post(path + "/transitions", json=transition, headers=key)
    assert replay.status_code == 200 and replay.json()["external_participants"] == []


def test_external_create_replay_keeps_current_labels_and_checks_fresh_authority(
    admin_client, seeded_user, db_engine
):
    from altvia.project_registry import set_project_access

    project_id = setup_project(admin_client, seeded_user)
    body = {
        "project_id": project_id,
        "title": "Original",
        "priority": "medium",
        "work_type": "one_off",
        "external_participants": ["Terceiro"],
    }
    key = preconditions()
    created_response = admin_client.post("/api/v1/work-items", json=body, headers=key)
    assert created_response.status_code == 201
    path = "/api/v1/work-items/" + created_response.json()["work_item_id"]
    assert (
        admin_client.patch(
            path, json={"external_participants": ["Changed"]}, headers=preconditions()
        ).status_code
        == 200
    )
    assert admin_client.post("/api/v1/work-items", json=body, headers=key).status_code == 200
    assert admin_client.get(path).json()["external_participants"] == ["Changed"]
    with Session(db_engine) as db, db.begin():
        set_project_access(db, "employee@example.test", UUID(project_id), "viewer")
    sign_in(admin_client, "employee@example.test")
    assert admin_client.post("/api/v1/work-items", json=body, headers=key).status_code == 403


def test_external_stale_and_exhausted_updates_roll_back_labels(
    admin_client, seeded_user, db_engine
):
    project_id = setup_project(admin_client, seeded_user)
    path = created(admin_client, project_id)
    assert (
        admin_client.patch(
            path, json={"external_participants": ["Stale"]}, headers=preconditions(7)
        ).status_code
        == 409
    )
    with Session(db_engine) as db, db.begin():
        db.get(WorkItem, UUID(path.rsplit("/", 1)[1])).version = 2147483647
    assert (
        admin_client.patch(
            path, json={"external_participants": ["Overflow"]}, headers=preconditions(2147483647)
        ).status_code
        == 409
    )
    assert admin_client.get(path).json()["external_participants"] == ["Terceiro"]
    assert len(events(db_engine)) == 1


def test_external_concurrent_distinct_sessions_keep_one_reviewed_change(admin_client, seeded_user):
    project_id = setup_project(admin_client, seeded_user)
    path = created(admin_client, project_id)
    channels = [
        TestClient(
            admin_client.app,
            base_url=str(admin_client.base_url),
            headers={"Origin": str(admin_client.base_url).rstrip("/")},
        )
        for _ in range(2)
    ]
    try:
        for channel in channels:
            sign_in(channel, "employee@example.test")
        assert dict(channels[0].cookies) != dict(channels[1].cookies)
        with ThreadPoolExecutor(2) as pool:
            codes = list(
                pool.map(
                    lambda pair: (
                        pair[0]
                        .patch(
                            path, json={"external_participants": [pair[1]]}, headers=preconditions()
                        )
                        .status_code
                    ),
                    zip(channels, ["First", "Second"], strict=True),
                )
            )
        assert sorted(codes) == [200, 409]
        assert admin_client.get(path).json()["version"] == 2
    finally:
        for channel in channels:
            channel.close()


def test_external_archived_references_refuse_mutation(admin_client, seeded_user):
    project_id = setup_project(admin_client, seeded_user)
    path = created(admin_client, project_id)
    assert (
        admin_client.patch(
            "/api/v1/projects/" + project_id, json={"active": False}, headers=preconditions()
        ).status_code
        == 200
    )
    assert admin_client.get(path).json()["external_participants"] == ["Terceiro"]
    assert (
        admin_client.patch(
            path, json={"external_participants": []}, headers=preconditions()
        ).status_code
        == 409
    )


def test_external_strict_projection_allows_only_the_field_name():
    data = {
        "actor_id": str(uuid4()),
        "actor_kind": "user",
        "project_id": str(uuid4()),
        "changed_fields": "external_participants",
    }
    assert WorkEventPayload.model_validate(data).changed_fields == "external_participants"
    with pytest.raises(ValidationError):
        WorkEventPayload.model_validate({**data, "external_participants": ["Private"]})


@pytest.mark.parametrize("clear", [False, True])
def test_external_downgrade_refuses_links_and_cleared_durable_events(
    admin_client, seeded_user, db_engine, clear
):
    project_id = setup_project(admin_client, seeded_user)
    config = Config("apps/api/alembic.ini")
    legacy = create_work(admin_client, project_id)
    assert legacy.status_code == 201
    legacy_path = "/api/v1/work-items/" + legacy.json()["work_item_id"]
    command.downgrade(config, "b46087000011")
    assert "work_item_external_participants" not in inspect(db_engine).get_table_names()
    command.upgrade(config, "head")
    preserved = admin_client.get(legacy_path).json()
    assert preserved["external_participants"] == [] and preserved["version"] == 1
    path = created(admin_client, project_id)
    if clear:
        assert (
            admin_client.patch(
                path, json={"external_participants": []}, headers=preconditions()
            ).status_code
            == 200
        )
    with pytest.raises(
        DBAPIError, match="Cannot downgrade while durable external involvement exists"
    ):
        command.downgrade(config, "b46087000011")
    command.check(config)


def test_external_runtime_least_privilege_and_database_constraints(
    admin_client, seeded_user, db_engine, settings
):
    from altvia.main import create_app
    from altvia.provision import provision_runtime
    from test_runtime_provision import runtime_url

    project_id = setup_project(admin_client, seeded_user)
    url = runtime_url(db_engine)
    worker = runtime_url(db_engine).set(username="altvia_worker")
    provision_runtime(
        db_engine,
        url.render_as_string(hide_password=False),
        worker.render_as_string(hide_password=False),
    )
    config = settings.model_copy(
        update={
            "database_url": settings.database_url.__class__(
                url.render_as_string(hide_password=False)
            )
        }
    )
    with TestClient(
        create_app(config),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        sign_in(client, "employee@example.test")
        path = created(client, project_id)
        assert (
            client.patch(
                path, json={"external_participants": []}, headers=preconditions()
            ).status_code
            == 200
        )
    for credential, statement in [
        (url, "UPDATE work_item_external_participants SET unresolved_label='No'"),
        (worker, "SELECT * FROM work_item_external_participants"),
    ]:
        engine = create_engine(credential, hide_parameters=True)
        try:
            with engine.begin() as connection, pytest.raises(DBAPIError, match="permission denied"):
                connection.execute(text(statement))
        finally:
            engine.dispose()
    for label in [" ", "x" * 151, "a\nb", "a\rb"]:
        with db_engine.begin() as connection, pytest.raises(DBAPIError):
            connection.execute(
                text(
                    "INSERT INTO work_item_external_participants(work_item_id,unresolved_label) "
                    "VALUES(:id,:label)"
                ),
                {"id": UUID(path.rsplit("/", 1)[1]), "label": label},
            )
