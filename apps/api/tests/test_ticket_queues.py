"""Real queue metadata persistence, scoped configuration and protected recovery."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_team_api import admin_client, created, preconditions, sign_in

__all__ = ["admin_client"]


def queue(client, team_id=None, name=" Support ", key=None):
    team_id = team_id or created(client)["id"]
    response = client.post(
        "/api/v1/ticket-queues",
        json={"team_id": team_id, "name": name},
        headers=preconditions(key=key),
    )
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"queue_id"}
    return "/api/v1/ticket-queues/" + response.json()["queue_id"]


def category(client, parent, name=" Category ", key=None):
    response = client.post(
        parent + "/categories", json={"name": name}, headers=preconditions(key=key)
    )
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"queue_id", "category_id"}
    return parent + "/categories/" + response.json()["category_id"]


def test_queue_and_category_persist_versions_noops_and_archives(admin_client, db_engine):
    path = queue(admin_client)
    first = admin_client.get(path)
    assert first.status_code == 200 and first.headers["etag"] == '"1"'
    assert first.json()["name"] == "Support" and first.json()["can_manage"]
    child = category(admin_client, path)
    assert admin_client.get(path).json()["version"] == 2
    assert admin_client.get(child).json()["name"] == "Category"
    changed = admin_client.patch(child, json={"name": "New"}, headers=preconditions())
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert admin_client.get(path).json()["version"] == 3
    assert (
        admin_client.patch(child, json={"name": "New"}, headers=preconditions(2)).json()["version"]
        == 2
    )
    assert admin_client.get(path).json()["version"] == 3
    assert (
        admin_client.patch(path, json={"name": "Stale"}, headers=preconditions()).status_code == 409
    )
    assert (
        admin_client.patch(path, json={"active": False}, headers=preconditions(3)).status_code
        == 200
    )
    assert (
        admin_client.patch(child, json={"active": False}, headers=preconditions(2)).status_code
        == 409
    )
    assert admin_client.get(child).json()["active"]
    assert (
        admin_client.patch(path, json={"active": True}, headers=preconditions(4)).status_code == 200
    )
    assert (
        admin_client.patch(child, json={"active": False}, headers=preconditions(2)).status_code
        == 200
    )
    assert (
        admin_client.patch(child, json={"active": True}, headers=preconditions(3)).status_code
        == 200
    )
    assert admin_client.get(path + "/categories").json()["items"][0]["version"] == 4
    with Session(db_engine) as db:
        from altvia.models import TicketCategory, TicketQueue

        assert db.get(TicketQueue, UUID(path.rsplit("/", 1)[1])).version == 7
        assert db.get(TicketCategory, UUID(child.rsplit("/", 1)[1])).name == "New"


def test_queue_scope_is_explicit_team_binding_and_not_roster_or_client(
    admin_client, seeded_user, db_engine
):
    from altvia.management import set_team_role
    from altvia.models import TeamMember

    team = created(admin_client)
    path = queue(admin_client, team["id"])
    child = category(admin_client, path)
    with Session(db_engine) as db, db.begin():
        db.add(TeamMember(team_id=UUID(team["id"]), user_id=seeded_user))
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(path).status_code == 404
    assert admin_client.get(child).status_code == 404
    assert admin_client.get(path + "/activity").status_code == 404
    assert admin_client.get("/api/v1/ticket-queues").json()["items"] == []
    assert not admin_client.get("/api/v1/ticket-queues").json()["can_create"]
    with Session(db_engine) as db, db.begin():
        set_team_role(db, "employee@example.test", UUID(team["id"]), "viewer", True)
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(path).status_code == 200
    assert not admin_client.get(path).json()["can_manage"]
    assert (
        admin_client.patch(path, json={"name": "Forbidden"}, headers=preconditions(2)).status_code
        == 403
    )
    with Session(db_engine) as db, db.begin():
        set_team_role(db, "employee@example.test", UUID(team["id"]), "operations_manager", True)
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(path).json()["can_manage"]
    assert admin_client.get("/api/v1/ticket-queues?limit=1").json()["can_create"]
    assert (
        admin_client.patch(child, json={"name": "Scoped"}, headers=preconditions()).status_code
        == 200
    )
    assert admin_client.get("/api/v1/clients").json()["items"] == []


def test_queue_creation_replay_keeps_ids_and_fresh_authority(admin_client, db_engine):
    from altvia.management import set_team_role

    team = created(admin_client)
    with Session(db_engine) as db, db.begin():
        set_team_role(db, "admin@example.test", UUID(team["id"]), "operations_manager", True)
    sign_in(admin_client, "admin@example.test")
    key = uuid4().hex
    path = queue(admin_client, team["id"], key=key)
    body = {"team_id": team["id"], "name": "Support"}
    assert (
        admin_client.patch(path, json={"name": "Renamed"}, headers=preconditions()).status_code
        == 200
    )
    replay = admin_client.post("/api/v1/ticket-queues", json=body, headers=preconditions(key=key))
    assert replay.status_code == 200 and replay.json()["queue_id"] == path.rsplit("/", 1)[1]
    assert admin_client.get(path).json()["name"] == "Renamed"
    assert (
        admin_client.post(
            "/api/v1/ticket-queues", json={**body, "name": "Other"}, headers=preconditions(key=key)
        ).status_code
        == 409
    )
    assert (
        admin_client.patch(
            "/api/v1/teams/" + team["id"], json={"active": False}, headers=preconditions()
        ).status_code
        == 200
    )
    assert (
        admin_client.post(
            "/api/v1/ticket-queues", json=body, headers=preconditions(key=key)
        ).status_code
        == 200
    )


@pytest.mark.parametrize("name", ["", " ", "x" * 151, "x\nname", "x\rname", "x\0name"])
def test_queue_rejects_invalid_names(admin_client, name):
    team = created(admin_client)
    assert (
        admin_client.post(
            "/api/v1/ticket-queues",
            json={"team_id": team["id"], "name": name},
            headers=preconditions(),
        ).status_code
        == 422
    )


def test_queue_parent_names_and_query_boundaries(admin_client):
    team = created(admin_client)
    first = queue(admin_client, team["id"], "\ufeffSupport")
    second = queue(admin_client, team["id"], "Other")
    child = category(admin_client, first)
    assert admin_client.get(first).json()["name"] == "\ufeffSupport"
    assert admin_client.get(second + "/categories/" + child.rsplit("/", 1)[1]).status_code == 404
    assert (
        admin_client.patch(
            first, json={"team_id": uuid4().hex}, headers=preconditions(2)
        ).status_code
        == 422
    )
    assert (
        admin_client.patch(
            child, json={"queue_id": uuid4().hex}, headers=preconditions()
        ).status_code
        == 422
    )
    assert (
        admin_client.patch(child, json={"name": None}, headers=preconditions()).status_code == 422
    )
    assert admin_client.patch(child, json={}, headers=preconditions()).status_code == 422
    assert admin_client.patch(child, json={"active": False}).status_code == 428
    assert (
        admin_client.post(
            first + "/categories", json={"name": "Category"}, headers=preconditions()
        ).status_code
        == 409
    )
    assert admin_client.get(first + "/categories?limit=1&limit=2").status_code == 422
    cursor = admin_client.get("/api/v1/ticket-queues?limit=1").json()["next_cursor"]
    assert admin_client.get(first + "/categories", params={"cursor": cursor}).status_code == 422
    assert admin_client.get("/api/v1/ticket-queues?unexpected=1").status_code == 422
    assert admin_client.get("/api/v1/ticket-queue-teams").json()["items"][0]["can_manage"]


def test_queue_events_project_redacted_and_stay_out_of_identity(admin_client, db_engine):
    from altvia.activity import consume_event
    from altvia.models import OutboxEvent

    path = queue(admin_client, name="Private queue label")
    category(admin_client, path, "Private category label")
    with Session(db_engine) as db:
        events = list(
            db.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_type == "ticket_queue"))
        )
        identifiers = [event.event_id for event in events]
        assert len(events) == 2
        assert "Private" not in str([event.payload for event in events])
    for identifier in identifiers:
        assert consume_event(db_engine, identifier, datetime.now(UTC))
        assert not consume_event(db_engine, identifier, datetime.now(UTC))
    history = admin_client.get(path + "/activity").json()["items"]
    assert len(history) == 2 and {row["aggregate_version"] for row in history} == {1, 2}
    assert not any(
        row["resource_type"] == "ticket_queue"
        for row in admin_client.get("/api/v1/identity-activity").json()["items"]
    )
    with Session(db_engine) as db, db.begin():
        bad = OutboxEvent(
            aggregate_type="ticket_queue",
            aggregate_id=UUID(path.rsplit("/", 1)[1]),
            aggregate_version=1,
            event_type="ticket_queue.created",
            payload={"actor_id": str(uuid4()), "actor_kind": "user", "name": "leak"},
            occurred_at=datetime.now(UTC),
            next_attempt_at=datetime.now(UTC),
            correlation_id="invalid_queue_event",
        )
        db.add(bad)
        db.flush()
        bad_id = bad.event_id
    assert not consume_event(db_engine, bad_id, datetime.now(UTC))


def test_queue_atomic_failure_overflow_and_competing_versions(admin_client, db_engine, settings):
    from altvia.main import create_app

    path = queue(admin_client)
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE outbox_events ADD CONSTRAINT test_reject_queue "
                "CHECK (aggregate_type <> 'ticket_queue') NOT VALID"
            )
        )
    try:
        assert (
            admin_client.patch(
                path, json={"name": "Rolled back"}, headers=preconditions()
            ).status_code
            == 503
        )
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE outbox_events DROP CONSTRAINT test_reject_queue"))
    assert admin_client.get(path).json()["name"] == "Support"

    def write(name):
        with TestClient(
            create_app(settings),
            base_url=settings.public_origin,
            headers={
                "Origin": settings.public_origin,
                "X-CSRF-Token": admin_client.headers["X-CSRF-Token"],
            },
            cookies=admin_client.cookies,
        ) as other:
            return other.patch(path, json={"name": name}, headers=preconditions()).status_code

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(write, ["First", "Second"])) == [200, 409]
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE ticket_queues SET version=2147483647 WHERE id=:id"),
            {"id": UUID(path.rsplit("/", 1)[1])},
        )
    assert (
        admin_client.post(
            path + "/categories", json={"name": "Overflow"}, headers=preconditions()
        ).status_code
        == 409
    )
    assert admin_client.get(path + "/categories").json()["items"] == []


def test_queue_runtime_privileges_constraints_and_safe_downgrade(admin_client, db_engine):
    path = queue(admin_client)
    assert {"ticket_queues", "ticket_categories"} <= set(inspect(db_engine).get_table_names())
    with db_engine.begin() as connection:
        for role in ["altvia_app", "altvia_worker"]:
            connection.execute(
                text(
                    f"DO $$ BEGIN CREATE ROLE {role}; "
                    "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
                )
            )
        from altvia.provision import ROLE_PRIVILEGES

        assert ROLE_PRIVILEGES["altvia_app"]["ticket_queues"] == {"SELECT", "INSERT", "UPDATE"}
        assert "ticket_queues" not in ROLE_PRIVILEGES["altvia_worker"]
    with pytest.raises(DBAPIError), db_engine.begin() as connection:
        connection.execute(text("UPDATE ticket_queues SET name=''"))
    config = Config("apps/api/alembic.ini")
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable queue"):
        command.downgrade(config, "b46087000012")
    command.upgrade(config, "head")
    assert admin_client.get(path).json()["name"] == "Support"


def test_queue_receipt_rechecks_revoked_team_scope(admin_client, db_engine, seeded_user):
    from altvia.management import set_team_role

    team = created(admin_client)
    with Session(db_engine) as db, db.begin():
        set_team_role(db, "employee@example.test", UUID(team["id"]), "operations_manager", True)
    sign_in(admin_client, "employee@example.test")
    key = uuid4().hex
    queue(admin_client, team["id"], key=key)
    with Session(db_engine) as db, db.begin():
        set_team_role(db, "employee@example.test", UUID(team["id"]), "operations_manager", False)
    body = {"team_id": team["id"], "name": "Support"}
    assert (
        admin_client.post(
            "/api/v1/ticket-queues", json=body, headers=preconditions(key=key)
        ).status_code
        == 401
    )
    sign_in(admin_client, "employee@example.test")
    assert (
        admin_client.post(
            "/api/v1/ticket-queues", json=body, headers=preconditions(key=key)
        ).status_code
        == 404
    )
    assert not admin_client.get("/api/v1/ticket-queues?limit=1").json()["can_create"]


def test_queue_category_replay_and_duplicate_archived_names(admin_client):
    team = created(admin_client)
    path = queue(admin_client, team["id"])
    key = uuid4().hex
    child = category(admin_client, path, key=key)
    assert (
        admin_client.patch(child, json={"active": False}, headers=preconditions()).status_code
        == 200
    )
    replay = admin_client.post(
        path + "/categories", json={"name": "Category"}, headers=preconditions(key=key)
    )
    assert replay.status_code == 200
    assert replay.json()["category_id"] == child.rsplit("/", 1)[1]
    assert not admin_client.get(child).json()["active"]
    assert (
        admin_client.post(
            path + "/categories", json={"name": "Category"}, headers=preconditions()
        ).status_code
        == 409
    )
    assert (
        admin_client.patch(path, json={"active": False}, headers=preconditions(3)).status_code
        == 200
    )
    assert (
        admin_client.post(
            "/api/v1/ticket-queues",
            json={"team_id": team["id"], "name": "Support"},
            headers=preconditions(),
        ).status_code
        == 409
    )


def test_queue_migration_preserves_existing_team_and_refuses_event_loss(admin_client, db_engine):
    team = created(admin_client)
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000012")
    assert "ticket_queues" not in inspect(db_engine).get_table_names()
    command.upgrade(config, "head")
    assert admin_client.get("/api/v1/teams/" + team["id"]).json()["version"] == 1
    path = queue(admin_client, team["id"])
    with db_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM ticket_queues WHERE id=:id"), {"id": UUID(path.rsplit("/", 1)[1])}
        )
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable queue"):
        command.downgrade(config, "b46087000012")
    command.check(config)


def test_queue_actual_runtime_writes_and_restricted_worker(admin_client, db_engine, settings):
    from altvia.main import create_app
    from altvia.provision import provision_runtime
    from sqlalchemy import create_engine
    from test_runtime_provision import runtime_url

    team = created(admin_client)
    runtime = runtime_url(db_engine)
    worker = runtime.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        runtime.render_as_string(hide_password=False),
        worker.render_as_string(hide_password=False),
    )
    config = settings.model_copy(
        update={
            "database_url": settings.database_url.__class__(
                runtime.render_as_string(hide_password=False)
            )
        }
    )
    with TestClient(
        create_app(config),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        sign_in(client, "admin@example.test")
        path = queue(client, team["id"])
        child = category(client, path)
        assert (
            client.patch(child, json={"active": False}, headers=preconditions()).status_code == 200
        )
        registered = client.get(path).json()
    # The assignment writer now needs native queue metadata. This is read
    # authority only; it must never become queue configuration authority.
    engine = create_engine(worker, hide_parameters=True)
    try:
        with engine.connect() as connection:
            metadata = connection.execute(
                text("SELECT name,active,allow_manual_close,allow_reopen FROM ticket_queues")
            ).one()
            assert tuple(metadata) == tuple(
                registered[key] for key in ("name", "active", "allow_manual_close", "allow_reopen")
            )
    finally:
        engine.dispose()
    for credential, statement in [
        (runtime, "DELETE FROM ticket_queues"),
        (runtime, "DELETE FROM ticket_categories"),
        (worker, "UPDATE ticket_queues SET allow_manual_close=NOT allow_manual_close"),
        (worker, "UPDATE ticket_queues SET active=active"),
        (worker, "UPDATE ticket_queues SET team_id=team_id"),
        (worker, "SELECT * FROM ticket_categories"),
    ]:
        engine = create_engine(credential, hide_parameters=True)
        try:
            with engine.begin() as connection, pytest.raises(DBAPIError, match="permission denied"):
                connection.execute(text(statement))
        finally:
            engine.dispose()
