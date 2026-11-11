"""Persisted queue grants with separate configuration and customer boundaries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia import identity, management
from altvia.models import AuditLog, ClientAccessGrant, OutboxEvent, RoleBinding, User
from conftest import TEST_PASSWORD
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in
from test_ticket_queues import category, queue

__all__ = ["admin_client"]


def setup(client, engine):
    path = queue(client)
    with Session(engine) as db, db.begin():
        target = management.create_user(db, "member@example.test", "Queue member", TEST_PASSWORD)
        identifier = target.id
    return path, identifier


def add(client, path, version=1, role="agent", email="member@example.test", key=None):
    return client.post(
        path + "/members",
        json={"email": email, "role_name": role},
        headers=preconditions(version, key),
    )


def events(engine, path):
    with Session(engine) as db:
        return list(
            db.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == UUID(path.rsplit("/", 1)[1]),
                    OutboxEvent.event_type == "ticket_queue.access_changed",
                )
            )
        )


def test_queue_access_persistence_versions_sessions_and_redacted_events(admin_client, db_engine):
    path, target = setup(admin_client, db_engine)
    response = add(admin_client, path, email=" MEMBER@EXAMPLE.TEST ")
    assert response.status_code == 201, response.text
    assert response.json() == {"queue_id": path.rsplit("/", 1)[1], "user_id": str(target)}
    assert admin_client.get(path).json()["version"] == 2
    assert add(admin_client, path, 2).status_code == 201
    assert admin_client.get(path).json()["version"] == 2
    members = admin_client.get(path + "/members").json()
    assert members["queue_version"] == 2 and members["next_cursor"] is None
    assert members["items"] == [
        {
            "id": str(target),
            "display_name": "Queue member",
            "active": True,
            "role_name": "agent",
            "note_access": "none",
        }
    ]
    member_path = path + "/members/" + str(target)
    changed = admin_client.patch(
        member_path, json={"role_name": "viewer"}, headers=preconditions(2)
    )
    assert changed.status_code == 204 and changed.headers["etag"] == '"3"'
    with Session(db_engine) as db:
        assert db.get(User, target).auth_version == 3
        assert not list(
            db.scalars(select(ClientAccessGrant).where(ClientAccessGrant.user_id == target))
        )
        assert (
            db.scalar(select(RoleBinding.role_name).where(RoleBinding.user_id == target))
            == "viewer"
        )
        assert db.scalar(select(AuditLog).where(AuditLog.action == "ticket_queue.access_changed"))
    removed = admin_client.delete(member_path, headers=preconditions(3))
    assert removed.status_code == 204 and removed.headers["etag"] == '"4"'
    assert admin_client.delete(member_path, headers=preconditions(4)).headers["etag"] == '"4"'
    assert (
        admin_client.delete(path + "/members/" + str(uuid4()), headers=preconditions(4)).status_code
        == 204
    )
    assert len(events(db_engine, path)) == 3
    assert all(
        set(row.payload) == {"actor_id", "actor_kind", "member_user_id", "role_name"}
        for row in events(db_engine, path)
    )
    assert all("example.test" not in str(row.payload) for row in events(db_engine, path))
    with Session(db_engine) as db:
        assert db.get(User, target).auth_version == 4
        assert db.scalar(select(RoleBinding).where(RoleBinding.user_id == target)) is None


@pytest.mark.parametrize("role", ["viewer", "agent", "operations_manager"])
def test_queue_only_scope_never_grants_configuration_customer_or_other_queues(
    admin_client, db_engine, role
):
    path, _ = setup(admin_client, db_engine)
    child = category(admin_client, path)
    other = queue(admin_client, name="Hidden")
    team_id = admin_client.get(path).json()["team_id"]
    assert add(admin_client, path, 2, role=role).status_code == 201
    sign_in(admin_client, "member@example.test")
    assert admin_client.get(path).status_code == 200
    assert not admin_client.get(path).json()["can_manage"]
    assert admin_client.get(child).status_code == 200
    assert admin_client.get(path + "/activity").status_code == 200
    assert admin_client.get(path + "/members").status_code == 200
    page = admin_client.get("/api/v1/ticket-queues").json()
    assert [row["id"] for row in page["items"]] == [path.rsplit("/", 1)[1]]
    assert not page["can_create"]
    assert admin_client.get("/api/v1/ticket-queue-teams").json()["items"] == []
    assert admin_client.get(other).status_code == 404
    assert admin_client.get("/api/v1/teams/" + team_id).status_code == 403
    assert admin_client.get("/api/v1/teams/" + str(uuid4())).status_code == 403
    assert admin_client.get("/api/v1/clients").json()["items"] == []
    assert admin_client.get("/api/v1/users").status_code == 403
    assert add(admin_client, path, 3).status_code == 403
    assert (
        admin_client.patch(path, json={"name": "Denied"}, headers=preconditions(3)).status_code
        == 403
    )
    assert (
        admin_client.patch(
            path + "/members/" + str(uuid4()),
            json={"role_name": "viewer"},
            headers=preconditions(3),
        ).status_code
        == 403
    )


def test_queue_access_replay_never_regrants_and_rechecks_present_authority(admin_client, db_engine):
    path, target = setup(admin_client, db_engine)
    key = uuid4().hex
    first = add(admin_client, path, key=key)
    assert first.status_code == 201
    assert (
        admin_client.delete(path + "/members/" + str(target), headers=preconditions(2)).status_code
        == 204
    )
    with Session(db_engine) as db, db.begin():
        db.get(User, target).active = False
    replay = add(admin_client, path, key=key)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert "etag" not in replay.headers
    assert add(admin_client, path, role="viewer", key=key).status_code == 409
    with Session(db_engine) as db, db.begin():
        management.set_platform_admin(db, "employee@example.test", True)
        management.set_platform_admin(db, "admin@example.test", False)
    assert add(admin_client, path, key=key).status_code == 401
    sign_in(admin_client, "admin@example.test")
    assert add(admin_client, path, key=key).status_code == 404


def test_queue_access_inactive_parents_noop_and_removal(admin_client, db_engine):
    path, target = setup(admin_client, db_engine)
    assert add(admin_client, path).status_code == 201
    assert (
        admin_client.patch(path, json={"active": False}, headers=preconditions(2)).status_code
        == 200
    )
    with Session(db_engine) as db, db.begin():
        db.get(User, target).active = False
    assert add(admin_client, path, 3).status_code == 201
    assert (
        admin_client.patch(
            path + "/members/" + str(target), json={"role_name": "viewer"}, headers=preconditions(3)
        ).status_code
        == 409
    )
    assert (
        admin_client.delete(path + "/members/" + str(target), headers=preconditions(3)).status_code
        == 204
    )
    assert admin_client.get(path).json()["version"] == 4
    assert len(events(db_engine, path)) == 2


def test_queue_member_input_preconditions_scopes_and_paging(admin_client, db_engine):
    path, target = setup(admin_client, db_engine)
    body = {"email": "member@example.test", "role_name": "agent"}
    assert admin_client.post(path + "/members", json=body).status_code == 428
    assert (
        admin_client.post(path + "/members", json=body, headers={"If-Match": '"1"'}).status_code
        == 428
    )
    for extra in [
        {"role_name": "platform_admin"},
        {"email": "bad"},
        {"client_id": str(uuid4())},
        {"user_id": str(target)},
    ]:
        assert (
            admin_client.post(
                path + "/members", json={**body, **extra}, headers=preconditions()
            ).status_code
            == 422
        )
    assert add(admin_client, path, email="unknown@example.test").status_code == 422
    with Session(db_engine) as db, db.begin():
        db.get(User, target).active = False
    assert add(admin_client, path).status_code == 422
    with Session(db_engine) as db, db.begin():
        db.get(User, target).active = True
    assert add(admin_client, path).status_code == 201
    assert add(admin_client, path, 1).status_code == 409
    assert (
        admin_client.patch(
            path + "/members/" + str(uuid4()), json={"role_name": "agent"}, headers=preconditions(2)
        ).status_code
        == 404
    )
    for query in ["?limit=0", "?limit=101", "?limit=1&limit=2", "?q=x", "?cursor=bad"]:
        assert admin_client.get(path + "/members" + query).status_code == 422
    assert admin_client.get("/api/v1/ticket-queues/" + str(uuid4()) + "/members").status_code == 404


def test_queue_access_event_failure_and_exhaustion_roll_back_all_effects(
    admin_client, db_engine, monkeypatch
):
    path, target = setup(admin_client, db_engine)
    before = admin_client.get(path).json()["version"]
    original = identity.record_event

    def fail(*args, **kwargs):
        if args[3] == "ticket_queue.access_changed":
            raise RuntimeError("injected atomicity failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(identity, "record_event", fail)
    with pytest.raises(RuntimeError, match="injected atomicity"):
        add(admin_client, path)
    monkeypatch.setattr(identity, "record_event", original)
    with Session(db_engine) as db:
        assert db.get(User, target).auth_version == 1
        assert db.scalar(select(RoleBinding).where(RoleBinding.user_id == target)) is None
    assert admin_client.get(path).json()["version"] == before
    assert not events(db_engine, path)
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE ticket_queues SET version=2147483647 WHERE id=:id"),
            {"id": UUID(path.rsplit("/", 1)[1])},
        )
    assert add(admin_client, path, 2147483647).status_code == 409
    with Session(db_engine) as db:
        assert db.get(User, target).auth_version == 1
        assert db.scalar(select(RoleBinding).where(RoleBinding.user_id == target)) is None


def test_queue_access_concurrent_reviewed_writes_one_wins(admin_client, db_engine, settings):
    from altvia.main import create_app

    path, _ = setup(admin_client, db_engine)
    cookies = dict(admin_client.cookies)
    csrf = admin_client.headers["X-CSRF-Token"]

    def grant(role):
        with TestClient(
            create_app(settings),
            base_url=settings.public_origin,
            headers={"Origin": settings.public_origin, "X-CSRF-Token": csrf},
        ) as client:
            client.cookies.update(cookies)
            return add(client, path, role=role).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(grant, ["viewer", "agent"]))
    assert sorted(results) == [201, 409]
    assert len(events(db_engine, path)) == 1


def test_queue_access_guarded_migration_and_scope_constraints(admin_client, db_engine):
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000013")
    assert "queue_id" not in {
        column["name"] for column in inspect(db_engine).get_columns("role_bindings")
    }
    command.upgrade(config, "head")
    path, target = setup(admin_client, db_engine)
    assert add(admin_client, path).status_code == 201
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable queue access"):
        command.downgrade(config, "b46087000013")
    with pytest.raises(DBAPIError), db_engine.begin() as connection:
        connection.execute(
            text("UPDATE role_bindings SET scope_kind='team' WHERE user_id=:id"), {"id": target}
        )
    with pytest.raises(DBAPIError), db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO role_bindings(user_id,role_name,scope_kind,queue_id) "
                "VALUES(:user,'viewer','queue',:queue)"
            ),
            {"user": target, "queue": UUID(path.rsplit("/", 1)[1])},
        )
    command.check(config)


def test_queue_access_projection_is_strict_scoped_and_idempotent(admin_client, db_engine):
    from altvia.activity import consume_event
    from altvia.models import ActivityEvent

    path, _ = setup(admin_client, db_engine)
    assert add(admin_client, path).status_code == 201
    event = events(db_engine, path)[0]
    now = datetime.now(UTC)
    assert consume_event(db_engine, event.event_id, now)
    assert not consume_event(db_engine, event.event_id, now)
    with Session(db_engine) as db:
        projected = db.scalar(select(ActivityEvent).where(ActivityEvent.event_id == event.event_id))
        assert projected.resource_type == "ticket_queue"
    assert all(
        row["event_type"] != "ticket_queue.access_changed"
        for row in admin_client.get("/api/v1/identity-activity").json()["items"]
    )
    with Session(db_engine) as db, db.begin():
        bad = OutboxEvent(
            aggregate_type="ticket_queue",
            aggregate_id=event.aggregate_id,
            aggregate_version=2,
            event_type=event.event_type,
            payload={**event.payload, "email": "private@example.test"},
            occurred_at=now,
            correlation_id=uuid4().hex,
            next_attempt_at=now,
        )
        db.add(bad)
        db.flush()
        bad_id = bad.event_id
    assert not consume_event(db_engine, bad_id, now)


def test_queue_member_page_rejects_concurrent_grant(admin_client, db_engine, monkeypatch):
    from altvia import queue_registry

    path, target_id = setup(admin_client, db_engine)
    original = queue_registry.scoped_queue
    changed = False

    def interleave(db, user_id, queue_id, **kwargs):
        nonlocal changed
        result = original(db, user_id, queue_id, **kwargs)
        if not changed:
            changed = True
            with Session(db_engine) as concurrent, concurrent.begin():
                management.lock_identity_writes(concurrent)
                row, _, active, _ = original(concurrent, user_id, queue_id, write=True)
                target = concurrent.get(User, target_id)
                queue_registry.change_queue_access(
                    concurrent, target, row, active, "agent", user_id, uuid4().hex
                )
        return result

    monkeypatch.setattr(queue_registry, "scoped_queue", interleave)
    assert admin_client.get(path + "/members").status_code == 409
    current = admin_client.get(path + "/members").json()
    assert current["queue_version"] == 2 and len(current["items"]) == 1


def test_queue_access_identity_lock_precedes_authentication(admin_client, db_engine, monkeypatch):
    path, _ = setup(admin_client, db_engine)
    with TestClient(
        admin_client.app,
        base_url=str(admin_client.base_url),
        headers={"Origin": str(admin_client.base_url).rstrip("/")},
    ) as writer:
        sign_in(writer, "admin@example.test")
        entered_auth = Event()
        authenticate = identity.authenticate

        def observe(db, token):
            entered_auth.set()
            return authenticate(db, token)

        monkeypatch.setattr(identity, "authenticate", observe)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with Session(db_engine) as revoker, revoker.begin():
                management.reset_password(revoker, "admin@example.test", TEST_PASSWORD)
                pid = revoker.scalar(text("SELECT pg_backend_pid()"))
                future = pool.submit(add, writer, path)
                blocked = False
                deadline = monotonic() + 5
                while monotonic() < deadline and not entered_auth.is_set():
                    with db_engine.connect() as monitor:
                        blocked = bool(
                            monitor.scalar(
                                text(
                                    "SELECT EXISTS (SELECT 1 FROM pg_locks l "
                                    "WHERE l.locktype='advisory' AND NOT l.granted "
                                    "AND :revoker = ANY(pg_blocking_pids(l.pid)))"
                                ),
                                {"revoker": pid},
                            )
                        )
                    if blocked:
                        break
                    sleep(0.02)
                assert blocked and not entered_auth.is_set() and not future.done()
            assert future.result(timeout=10).status_code == 401
    assert not events(db_engine, path)


def test_queue_roster_cursors_bind_actor_and_parent(admin_client, db_engine, seeded_user):
    path, target = setup(admin_client, db_engine)
    assert add(admin_client, path).status_code == 201
    assert add(admin_client, path, 2, email="employee@example.test").status_code == 201
    page = admin_client.get(path + "/members?limit=1").json()
    assert page["next_cursor"]
    second = admin_client.get(path + "/members", params={"cursor": page["next_cursor"]}).json()
    assert {page["items"][0]["id"], second["items"][0]["id"]} == {str(target), str(seeded_user)}
    other = queue(admin_client, name="Other")
    assert (
        admin_client.get(other + "/members", params={"cursor": page["next_cursor"]}).status_code
        == 422
    )
    sign_in(admin_client, "employee@example.test")
    assert (
        admin_client.get(path + "/members", params={"cursor": page["next_cursor"]}).status_code
        == 422
    )


@pytest.mark.parametrize("operation", ["add", "change", "remove"])
def test_queue_access_and_target_logout_finish_without_deadlock(
    admin_client, db_engine, monkeypatch, operation
):
    from altvia import queue_registry

    path, target_id = setup(admin_client, db_engine)
    version = 1
    if operation != "add":
        assert add(admin_client, path).status_code == 201
        version = 2
    member_path = path + "/members/" + str(target_id)
    logout_authenticated, target_locked, allow_logout = Event(), Event(), Event()
    real_record = identity.record_event
    real_invalidate = queue_registry._invalidate_sessions

    def record(db, actor_id, resource_id, event, *args, **kwargs):
        if event == "identity.session_revoked" and actor_id == target_id:
            logout_authenticated.set()
            assert allow_logout.wait(10)
        return real_record(db, actor_id, resource_id, event, *args, **kwargs)

    def invalidate(db, user, now):
        if user.id == target_id:
            target_locked.set()
        return real_invalidate(db, user, now)

    def mutate():
        if operation == "add":
            return add(admin_client, path)
        if operation == "change":
            return admin_client.patch(
                member_path, json={"role_name": "viewer"}, headers=preconditions(version)
            )
        return admin_client.delete(member_path, headers=preconditions(version))

    with TestClient(
        admin_client.app,
        base_url=str(admin_client.base_url),
        headers={"Origin": str(admin_client.base_url).rstrip("/")},
    ) as target:
        sign_in(target, "member@example.test")
        monkeypatch.setattr(identity, "record_event", record)
        monkeypatch.setattr(queue_registry, "_invalidate_sessions", invalidate)
        with ThreadPoolExecutor(max_workers=2) as pool:
            logout = pool.submit(target.delete, "/api/v1/auth/sessions/current")
            try:
                assert logout_authenticated.wait(5)
                mutation = pool.submit(mutate)
                assert target_locked.wait(5)
            finally:
                allow_logout.set()
            assert logout.result(timeout=15).status_code == 204
            assert mutation.result(timeout=15).status_code == (201 if operation == "add" else 204)
        assert target.get("/api/v1/auth/me").status_code == 401
    assert admin_client.get(path).json()["version"] == version + 1
    changes = events(db_engine, path)
    assert len(changes) == (1 if operation == "add" else 2)
    assert changes[-1].payload["role_name"] in {"agent", "viewer", "removed"}
    members = admin_client.get(path + "/members").json()["items"]
    assert members == (
        []
        if operation == "remove"
        else [
            {
                "id": str(target_id),
                "display_name": "Queue member",
                "active": True,
                "role_name": "viewer" if operation == "change" else "agent",
                "note_access": "none",
            }
        ]
    )
