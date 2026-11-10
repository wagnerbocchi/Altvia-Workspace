"""Real project access writes: atomic delegation, fresh ACL and immutable receipts."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from altvia import management
from altvia.models import (
    AuditLog,
    ClientAccessGrant,
    OutboxEvent,
    Project,
    ProjectMember,
    RoleBinding,
    User,
)
from conftest import TEST_PASSWORD
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_client_registry import created as create_client
from test_project_registry import project
from test_team_api import admin_client, preconditions, sign_in
from test_team_api import created as create_team

__all__ = ["admin_client"]


def setup(client, seeded_user, engine, *, customer=False):
    team = create_team(client)["id"]
    client_id = create_client(client, seeded_user) if customer else None
    receipt = project(client, seeded_user, team, client_id)
    assert receipt.status_code == 201
    with Session(engine) as db, db.begin():
        target = management.create_user(db, "member@example.test", "Member", TEST_PASSWORD)
        target_id = target.id
    sign_in(client, "employee@example.test")
    return "/api/v1/projects/" + receipt.json()["project_id"], target_id, client_id


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
                    OutboxEvent.event_type == "project.access_changed",
                )
            )
        )


def test_member_lifecycle_atomic_persistence_noop_and_redacted_event(
    admin_client, seeded_user, db_engine
):
    path, target, _ = setup(admin_client, seeded_user, db_engine)
    response = add(admin_client, path, email=" MEMBER@EXAMPLE.TEST ")
    assert response.status_code == 201, response.text
    assert response.json() == {"project_id": path.rsplit("/", 1)[1], "user_id": str(target)}
    assert admin_client.get(path).json()["version"] == 2
    assert add(admin_client, path, 2).status_code == 201
    assert admin_client.get(path).json()["version"] == 2
    member_path = path + "/members/" + str(target)
    changed = admin_client.patch(
        member_path, json={"role_name": "viewer"}, headers=preconditions(2)
    )
    assert changed.status_code == 204 and changed.headers["etag"] == '"3"'
    with Session(db_engine) as db:
        assert db.get(ProjectMember, (UUID(path.rsplit("/", 1)[1]), target)) is not None
        assert db.get(User, target).auth_version == 3
        assert (
            db.scalar(select(RoleBinding.role_name).where(RoleBinding.user_id == target))
            == "viewer"
        )
        assert db.scalar(select(AuditLog).where(AuditLog.action == "project.access_changed"))
    members = admin_client.get(path + "/members").json()["items"]
    assert next(row for row in members if row["id"] == str(target))["role_name"] == "viewer"
    removed = admin_client.delete(member_path, headers=preconditions(3))
    assert removed.status_code == 204 and removed.headers["etag"] == '"4"'
    assert admin_client.delete(member_path, headers=preconditions(4)).headers["etag"] == '"4"'
    assert (
        admin_client.delete(path + "/members/" + str(uuid4()), headers=preconditions(4)).status_code
        == 204
    )
    assert len(events(db_engine, path)) == 3
    assert all("member@example.test" not in str(row.payload) for row in events(db_engine, path))
    assert all(row.payload["actor_id"] == str(seeded_user) for row in events(db_engine, path))
    with Session(db_engine) as db:
        assert db.get(User, target).auth_version == 4
        assert db.get(ProjectMember, (UUID(path.rsplit("/", 1)[1]), target)) is None
        assert db.scalar(select(RoleBinding).where(RoleBinding.user_id == target)) is None


def test_member_replay_preserves_receipt_and_never_regrants(admin_client, seeded_user, db_engine):
    path, target, _ = setup(admin_client, seeded_user, db_engine)
    key = uuid4().hex
    response = add(admin_client, path, key=key)
    assert response.status_code == 201
    assert (
        admin_client.delete(path + "/members/" + str(target), headers=preconditions(2)).status_code
        == 204
    )
    with Session(db_engine) as db, db.begin():
        db.get(User, target).active = False
    replay = add(admin_client, path, key=key)
    assert replay.status_code == 200 and replay.json() == response.json()
    assert "etag" not in replay.headers
    assert admin_client.get(path).json()["version"] == 3
    assert len(events(db_engine, path)) == 2
    assert add(admin_client, path, role="viewer", key=key).status_code == 409
    from altvia.project_registry import set_project_access

    with Session(db_engine) as db, db.begin():
        set_project_access(db, "employee@example.test", UUID(path.rsplit("/", 1)[1]), "viewer")
    assert add(admin_client, path, key=key).status_code == 401
    sign_in(admin_client, "employee@example.test")
    assert add(admin_client, path, key=key).status_code == 403


@pytest.mark.parametrize("role", ["viewer", "agent"])
def test_readable_members_cannot_manage_or_discover_accounts(
    admin_client, seeded_user, db_engine, role
):
    path, target, _ = setup(admin_client, seeded_user, db_engine)
    assert add(admin_client, path, role=role).status_code == 201
    sign_in(admin_client, "member@example.test")
    assert admin_client.get(path + "/members").status_code == 200
    assert admin_client.get("/api/v1/users").status_code == 403
    assert add(admin_client, path, 2).status_code == 403
    assert (
        admin_client.patch(
            path + "/members/" + str(target),
            json={"role_name": "project_manager"},
            headers=preconditions(2),
        ).status_code
        == 403
    )
    assert (
        admin_client.delete(path + "/members/" + str(target), headers=preconditions(2)).status_code
        == 403
    )


def test_platform_admin_has_no_project_member_bypass(admin_client, seeded_user, db_engine):
    path, target, _ = setup(admin_client, seeded_user, db_engine)
    sign_in(admin_client, "admin@example.test")
    assert add(admin_client, path).status_code == 404
    assert (
        admin_client.delete(path + "/members/" + str(target), headers=preconditions()).status_code
        == 404
    )


@pytest.mark.parametrize("email", ["unknown@example.test", "member@example.test"])
def test_client_add_never_creates_ceiling_or_reveals_ineligible_target(
    admin_client, seeded_user, db_engine, email
):
    path, target, customer = setup(admin_client, seeded_user, db_engine, customer=True)
    response = add(admin_client, path, email=email)
    assert response.status_code == 422 and response.json()["code"] == "invalid_project_member"
    with Session(db_engine) as db:
        assert db.get(ClientAccessGrant, (target, UUID(customer))) is None
        assert db.get(User, target).auth_version == 1
    assert admin_client.get(path).json()["version"] == 1


def test_inactive_target_same_state_noop_but_role_change_denied_and_removal_allowed(
    admin_client, seeded_user, db_engine
):
    path, target, _ = setup(admin_client, seeded_user, db_engine)
    assert add(admin_client, path).status_code == 201
    with Session(db_engine) as db, db.begin():
        db.get(User, target).active = False
    assert add(admin_client, path, 2).status_code == 201
    assert (
        admin_client.patch(
            path + "/members/" + str(target), json={"role_name": "viewer"}, headers=preconditions(2)
        ).status_code
        == 422
    )
    assert (
        admin_client.patch(path, json={"active": False}, headers=preconditions(2)).status_code
        == 200
    )
    assert add(admin_client, path, 3).status_code == 201
    assert (
        admin_client.delete(path + "/members/" + str(target), headers=preconditions(3)).status_code
        == 204
    )
    assert len(events(db_engine, path)) == 2


def test_member_write_preconditions_and_strict_bodies(admin_client, seeded_user, db_engine):
    path, target, _ = setup(admin_client, seeded_user, db_engine)
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
    assert add(admin_client, path, 2).status_code == 409
    assert (
        admin_client.patch(
            path + "/members/" + str(target), json={"role_name": "viewer"}, headers=preconditions()
        ).status_code
        == 404
    )
    assert admin_client.delete(path + "/members/" + str(target)).status_code == 428
    assert add(admin_client, path).status_code == 201
    assert (
        admin_client.delete(path + "/members/" + str(target), headers=preconditions()).status_code
        == 409
    )
    assert (
        admin_client.post(
            path + "/members",
            json=body,
            headers={**preconditions(2), "Origin": "https://evil.test"},
        ).status_code
        == 403
    )


def test_self_demotion_ends_session_and_preserves_history(admin_client, seeded_user, db_engine):
    path, _, _ = setup(admin_client, seeded_user, db_engine)
    changed = admin_client.patch(
        path + "/members/" + str(seeded_user), json={"role_name": "viewer"}, headers=preconditions()
    )
    assert changed.status_code == 204
    assert admin_client.get(path).status_code == 401
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(path).status_code == 200
    assert not admin_client.get(path).json()["can_manage"]
    assert len(events(db_engine, path)) == 1


@pytest.mark.parametrize("half", ["member", "binding"])
def test_member_write_repairs_split_pair(admin_client, seeded_user, db_engine, half):
    path, target, _ = setup(admin_client, seeded_user, db_engine)
    assert add(admin_client, path).status_code == 201
    with Session(db_engine) as db, db.begin():
        if half == "member":
            db.delete(db.get(ProjectMember, (UUID(path.rsplit("/", 1)[1]), target)))
        else:
            db.delete(db.scalar(select(RoleBinding).where(RoleBinding.user_id == target)))
    response = admin_client.patch(
        path + "/members/" + str(target), json={"role_name": "agent"}, headers=preconditions(2)
    )
    assert response.status_code == 204 and response.headers["etag"] == '"3"'
    assert any(
        row["id"] == str(target) for row in admin_client.get(path + "/members").json()["items"]
    )


def test_concurrent_member_posts_have_one_effect_and_stale_loser(
    admin_client, seeded_user, db_engine
):
    path, _, _ = setup(admin_client, seeded_user, db_engine)
    cookies = dict(admin_client.cookies)
    headers = dict(admin_client.headers)

    def invoke(_):
        with TestClient(
            admin_client.app, base_url=str(admin_client.base_url), headers=headers, cookies=cookies
        ) as channel:
            return add(channel, path).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(invoke, range(2))) == [201, 409]
    assert admin_client.get(path).json()["version"] == 2
    assert len(events(db_engine, path)) == 1


def test_member_page_carries_the_reviewed_project_version(admin_client, seeded_user, db_engine):
    path, _, _ = setup(admin_client, seeded_user, db_engine)
    assert admin_client.get(path + "/members").json()["project_version"] == 1
    assert add(admin_client, path).status_code == 201
    page = admin_client.get(path + "/members").json()
    assert page["project_version"] == 2 and len(page["items"]) == 2


@pytest.mark.parametrize("revocation", ["account", "ceiling"])
def test_revocation_lock_precedes_member_session_authentication(
    admin_client, seeded_user, db_engine, monkeypatch, revocation
):
    from altvia import identity
    from altvia.client_registry import set_client_access

    path, target, customer = setup(admin_client, seeded_user, db_engine, customer=True)
    with TestClient(
        admin_client.app,
        base_url=str(admin_client.base_url),
        headers={"Origin": str(admin_client.base_url).rstrip("/")},
    ) as writer:
        sign_in(writer, "employee@example.test")
        assert dict(writer.cookies) != dict(admin_client.cookies)
        entered_auth = Event()
        real_authenticate = identity.authenticate

        def observe_authentication(db, token):
            entered_auth.set()
            return real_authenticate(db, token)

        monkeypatch.setattr(identity, "authenticate", observe_authentication)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with Session(db_engine) as revoker, revoker.begin():
                if revocation == "account":
                    management.set_account_active(revoker, "employee@example.test", False)
                else:
                    set_client_access(revoker, "employee@example.test", UUID(customer), None)
                revoker_pid = revoker.scalar(text("SELECT pg_backend_pid()"))
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
                                {"revoker": revoker_pid},
                            )
                        )
                    if blocked:
                        break
                    sleep(0.02)
                assert not entered_auth.is_set(), "Member authentication ran before revocation lock"
                assert blocked, "Expected a real advisory-lock waiter behind the revoker"
                assert not future.done()
            response = future.result(timeout=10)
        assert entered_auth.is_set()
        assert response.status_code == 401
    with Session(db_engine) as db:
        assert db.get(Project, UUID(path.rsplit("/", 1)[1])).version == 1
        assert db.get(ProjectMember, (UUID(path.rsplit("/", 1)[1]), target)) is None
    assert events(db_engine, path) == []


def test_member_page_rejects_a_change_between_parent_and_roster_reads(
    admin_client, seeded_user, db_engine, monkeypatch
):
    from altvia import project_registry

    path, _, _ = setup(admin_client, seeded_user, db_engine)
    original = project_registry.scoped_project
    changed = False

    def interleave(db, user_id, project_id, **kwargs):
        nonlocal changed
        result = original(db, user_id, project_id, **kwargs)
        if not changed:
            changed = True
            with Session(db_engine) as concurrent, concurrent.begin():
                project_registry.set_project_access(
                    concurrent, "member@example.test", project_id, "agent"
                )
        return result

    monkeypatch.setattr(project_registry, "scoped_project", interleave)
    response = admin_client.get(path + "/members")
    assert response.status_code == 409
    assert response.json()["code"] == "version_conflict"
    current = admin_client.get(path + "/members").json()
    assert current["project_version"] == 2 and len(current["items"]) == 2
