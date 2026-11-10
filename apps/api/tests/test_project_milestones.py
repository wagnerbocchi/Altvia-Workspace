"""Real milestone storage, scoped writes and immutable submission receipts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_project_members import setup
from test_team_api import admin_client, preconditions, sign_in

__all__ = ["admin_client"]


def create(client, parent, body=None, key=None):
    return client.post(
        parent + "/milestones", json=body or {"title": " Delivery "}, headers=preconditions(key=key)
    )


def created(client, parent, body=None, key=None):
    response = create(client, parent, body, key)
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"project_id", "milestone_id"}
    return parent + "/milestones/" + response.json()["milestone_id"]


def test_milestone_persists_deadline_states_versions_and_noop(admin_client, seeded_user, db_engine):
    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    path = created(
        admin_client,
        parent,
        {
            "title": " Delivery ",
            "due": {"precision": "date", "date": "2026-11-10", "timezone": "America/Sao_Paulo"},
        },
    )
    row = admin_client.get(path)
    assert row.status_code == 200 and row.headers["etag"] == '"1"'
    assert row.json()["title"] == "Delivery" and row.json()["state"] == "planned"
    assert row.json()["due_at"] == "2026-11-11T03:00:00Z"
    assert admin_client.get(parent).json()["version"] == 2
    for version, state in [(1, "done"), (2, "planned"), (3, "cancelled")]:
        response = admin_client.patch(path, json={"state": state}, headers=preconditions(version))
        assert response.status_code == 200 and response.json()["version"] == version + 1
        assert response.json()["state"] == state
    assert (
        admin_client.patch(path, json={"state": "done"}, headers=preconditions(4)).status_code
        == 409
    )
    noop = admin_client.patch(path, json={"state": "cancelled"}, headers=preconditions(4))
    assert noop.status_code == 200 and noop.json()["version"] == 4
    assert admin_client.get(parent).json()["version"] == 5
    page = admin_client.get(parent + "/milestones").json()
    assert page["items"][0]["id"] == path.rsplit("/", 1)[1]
    assert page["items"][0]["can_manage"]


def test_milestone_replay_never_resets_current_state_and_rechecks_authority(
    admin_client, seeded_user, db_engine
):
    from altvia.project_registry import set_project_access

    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    key = uuid4().hex
    path = created(admin_client, parent, key=key)
    assert (
        admin_client.patch(path, json={"state": "done"}, headers=preconditions()).status_code == 200
    )
    replay = create(admin_client, parent, key=key)
    assert replay.status_code == 200 and replay.json()["milestone_id"] == path.rsplit("/", 1)[1]
    assert admin_client.get(path).json()["state"] == "done"
    assert create(admin_client, parent, {"title": "Different"}, key).status_code == 409
    with Session(db_engine) as db, db.begin():
        set_project_access(db, "employee@example.test", UUID(parent.rsplit("/", 1)[1]), "viewer")
    assert create(admin_client, parent, key=key).status_code == 401
    sign_in(admin_client, "employee@example.test")
    assert create(admin_client, parent, key=key).status_code == 403


def test_milestone_cross_parent_and_platform_admin_are_hidden(admin_client, seeded_user, db_engine):
    from altvia.models import Project
    from altvia.project_registry import set_project_access

    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    path = created(admin_client, parent)
    with Session(db_engine) as db, db.begin():
        visible = db.get(Project, UUID(parent.rsplit("/", 1)[1]))
        hidden = Project(name="Hidden", scope_kind="internal", team_id=visible.team_id)
        db.add(hidden)
        db.flush()
        hidden_id = str(hidden.id)
        set_project_access(db, "employee@example.test", hidden.id, "project_manager")
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(f"/api/v1/projects/{hidden_id}").status_code == 200
    wrong = f"/api/v1/projects/{hidden_id}/milestones/" + path.rsplit("/", 1)[1]
    assert admin_client.get(wrong).status_code == 404
    assert (
        admin_client.patch(wrong, json={"title": "No"}, headers=preconditions()).status_code == 404
    )
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path).status_code == 404
    assert create(admin_client, parent).status_code == 404


def test_milestone_client_ceiling_and_readonly_role(admin_client, seeded_user, db_engine):
    from altvia.client_registry import set_client_access

    parent, _, customer = setup(admin_client, seeded_user, db_engine, customer=True)
    path = created(admin_client, parent)
    with Session(db_engine) as db, db.begin():
        # Explicitly approved ceiling plus role, independently of project membership.
        set_client_access(db, "member@example.test", UUID(customer), "viewer")
    sign_in(admin_client, "member@example.test")
    assert admin_client.get(path).status_code == 200
    assert not admin_client.get(path).json()["can_manage"]
    assert create(admin_client, parent).status_code == 403
    assert (
        admin_client.patch(path, json={"title": "No"}, headers=preconditions()).status_code == 403
    )
    with Session(db_engine) as db, db.begin():
        set_client_access(db, "member@example.test", UUID(customer), None)
    assert admin_client.get(path).status_code == 401
    sign_in(admin_client, "member@example.test")
    assert admin_client.get(path).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": None},
        {"state": None},
        {"state": "blocked"},
        {"project_id": str(uuid4())},
        {"title": " "},
        {"due": {"precision": "instant", "instant": "2026-11-10T12:00:00"}},
    ],
)
def test_milestone_patch_rejects_invalid_and_cross_scope_fields(
    admin_client, seeded_user, db_engine, body
):
    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    path = created(admin_client, parent)
    assert admin_client.patch(path, json=body, headers=preconditions()).status_code == 422


def test_milestone_inactive_noop_replay_but_real_writes_denied(
    admin_client, seeded_user, db_engine
):
    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    key = uuid4().hex
    path = created(admin_client, parent, key=key)
    assert (
        admin_client.patch(parent, json={"active": False}, headers=preconditions(2)).status_code
        == 200
    )
    assert not admin_client.get(path).json()["project_writable"]
    assert create(admin_client, parent, key=key).status_code == 200
    assert create(admin_client, parent).status_code == 409
    assert (
        admin_client.patch(path, json={"title": "Delivery"}, headers=preconditions()).status_code
        == 200
    )
    assert (
        admin_client.patch(path, json={"title": "New"}, headers=preconditions()).status_code == 409
    )


def test_milestone_exact_instant_survives_title_edit_and_clears_explicitly(
    admin_client, seeded_user, db_engine
):
    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    path = created(
        admin_client,
        parent,
        {
            "title": "Exact",
            "due": {"precision": "instant", "instant": "2026-11-10T12:34:56.123456Z"},
        },
    )
    edited = admin_client.patch(path, json={"title": "Revised"}, headers=preconditions())
    assert edited.json()["due"]["instant"] == "2026-11-10T12:34:56.123456Z"
    assert (
        admin_client.patch(path, json={"due": None}, headers=preconditions(2)).json()["due_at"]
        is None
    )
    assert (
        admin_client.patch(path, json={"title": "Stale"}, headers=preconditions()).status_code
        == 409
    )
    assert admin_client.patch(path, json={"title": "Missing version"}).status_code == 428


def test_milestone_invalid_timezone_rolls_back_parent_and_row(admin_client, seeded_user, db_engine):
    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    for day, zone in [("2026-11-10", "Unknown/Place"), ("2011-12-30", "Pacific/Apia")]:
        assert (
            create(
                admin_client,
                parent,
                {"title": "Invalid", "due": {"precision": "date", "date": day, "timezone": zone}},
            ).status_code
            == 422
        )
    assert admin_client.get(parent).json()["version"] == 1
    assert admin_client.get(parent + "/milestones").json()["items"] == []


def test_milestone_events_project_once_without_titles_or_identity_leak(
    admin_client, seeded_user, db_engine
):
    from altvia.activity import claim_events, consume_event
    from altvia.models import OutboxEvent

    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    path = created(admin_client, parent)
    assert (
        admin_client.patch(path, json={"state": "done"}, headers=preconditions()).status_code == 200
    )
    for event_id, _ in claim_events(db_engine, datetime.now(UTC)):
        consume_event(db_engine, event_id, datetime.now(UTC))
        assert not consume_event(db_engine, event_id, datetime.now(UTC))
    events = admin_client.get(parent + "/activity").json()["items"]
    assert {row["event_type"] for row in events} >= {
        "project.milestone_created",
        "project.milestone_updated",
    }
    with Session(db_engine) as db:
        rows = list(
            db.scalars(
                select(OutboxEvent).where(OutboxEvent.event_type.like("project.milestone_%"))
            )
        )
        assert len(rows) == 2 and all(row.status == "delivered" for row in rows)
        assert all("Delivery" not in str(row.payload) for row in rows)
    sign_in(admin_client, "admin@example.test")
    assert all(
        "milestone" not in row["event_type"]
        for row in admin_client.get("/api/v1/identity-activity").json()["items"]
    )


def test_milestone_pagination_is_bound_and_strict(admin_client, seeded_user, db_engine):
    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    for _ in range(3):
        created(admin_client, parent)
    collection = parent + "/milestones"
    page = admin_client.get(collection + "?limit=1").json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    next_page = admin_client.get(
        collection, params={"limit": 1, "cursor": page["next_cursor"]}
    ).json()
    assert next_page["items"][0]["id"] != page["items"][0]["id"]
    for query in ["?extra=1", "?limit=1&limit=2", "?cursor=bad"]:
        assert admin_client.get(collection + query).status_code == 422


def test_milestone_competing_edits_use_distinct_sessions(admin_client, seeded_user, db_engine):
    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    path = created(admin_client, parent)
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
            results = list(
                pool.map(
                    lambda pair: (
                        pair[0]
                        .patch(path, json={"title": pair[1]}, headers=preconditions())
                        .status_code
                    ),
                    zip(channels, ["First", "Second"], strict=True),
                )
            )
        assert sorted(results) == [200, 409]
        assert admin_client.get(path).json()["version"] == 2
    finally:
        for channel in channels:
            channel.close()


def test_milestone_migration_preserves_projects_and_refuses_loss(
    admin_client, seeded_user, db_engine
):
    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000010")
    assert "project_milestones" not in inspect(db_engine).get_table_names()
    command.upgrade(config, "head")
    assert admin_client.get(parent).status_code == 200
    created(admin_client, parent)
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable milestone data exists"):
        command.downgrade(config, "b46087000010")
    command.check(config)


def test_milestone_runtime_api_writes_but_cannot_delete_or_grant_worker_reads(
    admin_client, seeded_user, db_engine, settings
):
    from altvia.main import create_app
    from altvia.provision import provision_runtime
    from test_runtime_provision import runtime_url

    parent, _, _ = setup(admin_client, seeded_user, db_engine)
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
        path = created(client, parent)
        assert (
            client.patch(path, json={"state": "done"}, headers=preconditions()).status_code == 200
        )
    for credential, statement in [
        (url, "DELETE FROM project_milestones"),
        (worker, "SELECT * FROM project_milestones"),
    ]:
        engine = create_engine(credential, hide_parameters=True)
        try:
            with engine.begin() as connection, pytest.raises(DBAPIError, match="permission denied"):
                connection.execute(text(statement))
        finally:
            engine.dispose()


def test_milestone_http_security_and_sql_constraints(admin_client, seeded_user, db_engine):
    parent, _, _ = setup(admin_client, seeded_user, db_engine)
    assert admin_client.post(parent + "/milestones", json={"title": "No key"}).status_code == 428
    assert create(admin_client, parent, {"title": "No", "state": "done"}).status_code == 422
    assert (
        admin_client.post(
            parent + "/milestones",
            json={"title": "No"},
            headers={**preconditions(), "Origin": "https://evil.test"},
        ).status_code
        == 403
    )
    assert (
        admin_client.post(
            parent + "/milestones",
            json={"title": "No"},
            headers={**preconditions(), "X-CSRF-Token": "wrong"},
        ).status_code
        == 403
    )
    path = created(admin_client, parent)
    for assignment in ["state='blocked'", "version=0", "title=' '", "due_precision='date'"]:
        with db_engine.begin() as connection, pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE project_milestones SET " + assignment + " WHERE id=:id"),
                {"id": UUID(path.rsplit("/", 1)[1])},
            )
