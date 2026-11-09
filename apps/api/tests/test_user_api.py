import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from altvia import identity, management
from altvia.models import AuditLog, IdempotencyRecord, OutboxEvent, SessionRecord, User
from conftest import TEST_PASSWORD
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_team_api import created, preconditions, sign_in


@pytest.fixture
def admin_client(client, db_engine):
    with Session(db_engine) as db, db.begin():
        management.bootstrap_admin(db, "admin@example.test", "Administrator", TEST_PASSWORD)
    sign_in(client, "admin@example.test")
    return client


def create_account(client, **overrides):
    return client.post(
        "/api/v1/users",
        json={
            "email": " New@Example.Test ",
            "display_name": " New Employee ",
            "password": TEST_PASSWORD,
            **overrides,
        },
        headers={"Idempotency-Key": uuid4().hex},
    )


def test_account_lifecycle_and_attributed_atomic_events(admin_client, db_engine):
    client = admin_client
    actor_id = client.get("/api/v1/auth/me").json()["id"]
    response = create_account(client)
    assert response.status_code == 201
    account = response.json()
    assert account["email"] == "new@example.test"
    assert account["display_name"] == "New Employee"
    assert account["version"] == 1 and account["active"] and not account["platform_admin"]
    assert set(account) == {
        "id",
        "email",
        "display_name",
        "active",
        "platform_admin",
        "version",
        "created_at",
    }
    path = f"/api/v1/users/{account['id']}"
    assert client.get(path).json() == account
    assert response.headers["etag"] == '"1"'
    team = created(client)
    changes = [
        ("platform-admin", {"enabled": True}),
        ("team-roles", {"team_id": team["id"], "role_name": "viewer", "enabled": True}),
        ("password", {"password": "A replacement password 2026!"}),
        ("activation", {"active": False}),
        ("team-roles", {"team_id": team["id"], "role_name": "viewer", "enabled": False}),
        ("platform-admin", {"enabled": False}),
        ("activation", {"active": True}),
    ]
    for version, (suffix, body) in enumerate(changes, 1):
        changed = client.post(path + "/" + suffix, json=body, headers=preconditions(version))
        assert changed.status_code == 200, changed.text
        assert changed.json()["version"] == version + 1
        assert changed.headers["etag"] == f'"{version + 1}"'
    with Session(db_engine) as db:
        events = list(db.scalars(select(AuditLog).where(AuditLog.resource_id == account["id"])))
        assert len(events) == 8
        assert all(str(event.actor_id) == actor_id for event in events)
        assert (
            len(
                list(
                    db.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == account["id"]))
                )
            )
            == 8
        )
        user = db.get(User, account["id"])
        assert identity.PASSWORDS.verify(user.password_hash, "A replacement password 2026!")


def test_password_replay_is_historical_secret_safe_and_does_not_revoke_new_session(
    admin_client, db_engine
):
    client = admin_client
    me = client.get("/api/v1/auth/me").json()
    path = f"/api/v1/users/{me['id']}/password"
    headers = preconditions()
    body = {"password": TEST_PASSWORD}
    first = client.post(path, json=body, headers=headers)
    assert first.status_code == 200
    assert first.headers["x-session-revoked"] == "true"
    assert "Max-Age=0" in first.headers["set-cookie"]
    assert client.get("/api/v1/auth/me").status_code == 401
    sign_in(client, "admin@example.test")
    # A subsequent change makes the first receipt historical.
    second = client.post(path, json=body, headers=preconditions(2))
    assert second.status_code == 200
    sign_in(client, "admin@example.test")
    replay = client.post(path, json=body, headers=headers)
    assert replay.json() == first.json()
    assert "x-session-revoked" not in replay.headers and "set-cookie" not in replay.headers
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get(path.removesuffix("/password")).json()["version"] == 3
    with Session(db_engine) as db:
        receipts = list(db.scalars(select(IdempotencyRecord)))
        assert len(receipts) == 2
        public = json.dumps([r.result for r in receipts])
        public += json.dumps([a.details for a in db.scalars(select(AuditLog))])
        public += json.dumps([e.payload for e in db.scalars(select(OutboxEvent))])
        assert TEST_PASSWORD not in public and "$argon2" not in public
        assert all(len(r.request_hash) == 64 for r in receipts)
        # Credential fingerprints are deliberately costly, scoped Argon2id outputs.
        import hashlib

        from argon2.low_level import Type, hash_secret_raw

        canonical = json.dumps(
            {"password": TEST_PASSWORD, "version": 1}, sort_keys=True, separators=(",", ":")
        ).encode()
        salt = hashlib.sha256(
            json.dumps([me["id"], path, headers["Idempotency-Key"]], separators=(",", ":")).encode()
        ).digest()[:16]
        expected = hash_secret_raw(canonical, salt, 3, 65536, 1, 32, Type.ID).hex()
        assert (
            next(r for r in receipts if r.key == headers["Idempotency-Key"]).request_hash
            == expected
        )


def test_fresh_authorization_precedes_receipt_and_noop_preserves_sessions(
    admin_client, db_engine, seeded_user
):
    client = admin_client
    path = f"/api/v1/users/{seeded_user}/activation"
    headers = preconditions()
    response = client.post(path, json={"active": True}, headers=headers)
    assert response.status_code == 200 and response.json()["version"] == 1
    conflict = client.post(path, json={"active": False}, headers=headers)
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    with Session(db_engine) as db, db.begin():
        # Another administrator can revoke the actor while retaining the guard.
        management.set_platform_admin(db, "employee@example.test", True)
        management.set_platform_admin(db, "admin@example.test", False)
    assert client.post(path, json={"active": True}, headers=headers).status_code == 401


@pytest.mark.parametrize(
    "suffix,body",
    [
        ("activation", {"active": False}),
        ("platform-admin", {"enabled": False}),
    ],
)
def test_last_admin_refused(admin_client, suffix, body):
    me = admin_client.get("/api/v1/auth/me").json()
    response = admin_client.post(
        f"/api/v1/users/{me['id']}/{suffix}", json=body, headers=preconditions()
    )
    assert response.status_code == 409 and response.json()["code"] == "last_active_admin"
    assert admin_client.get("/api/v1/auth/me").status_code == 200


@pytest.mark.parametrize(
    "headers,status",
    [
        ({}, 428),
        ({"If-Match": '"1"'}, 428),
        ({"Idempotency-Key": "valid"}, 428),
        ({"If-Match": '"0"', "Idempotency-Key": "valid"}, 422),
        ({"If-Match": '"2"', "Idempotency-Key": "valid"}, 409),
        ({"If-Match": '"1"', "Idempotency-Key": "bad space"}, 422),
        ({"If-Match": '"1"', "Idempotency-Key": "valid", "Origin": "https://evil.test"}, 403),
        ({"If-Match": '"1"', "Idempotency-Key": "valid", "X-CSRF-Token": "bad"}, 403),
    ],
)
def test_write_preconditions(admin_client, seeded_user, headers, status):
    response = admin_client.post(
        f"/api/v1/users/{seeded_user}/activation", json={"active": False}, headers=headers
    )
    assert response.status_code == status


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short"},
        {"password": "🙂" * 257},
        {"email": "invalid"},
        {"display_name": " "},
        {"display_name": "x" * 151},
        {"platform_admin": True},
        {"active": False},
        {"password": 12345},
    ],
)
def test_strict_create_redacts_validation(admin_client, overrides):
    response = create_account(admin_client, **overrides)
    assert response.status_code == 422
    assert TEST_PASSWORD not in response.text and "🙂" not in response.text


def test_account_body_boundary_and_ordinary_denial(client, seeded_user):
    sign_in(client, "employee@example.test")
    assert client.get(f"/api/v1/users/{seeded_user}").status_code == 403
    assert client.get(f"/api/v1/users/{seeded_user}/team-roles").status_code == 403
    assert create_account(client).status_code == 403
    response = client.post(
        "/api/v1/users",
        content='{"password":"' + "x" * 17000 + '"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert (
        client.post(
            "/api/v1/users", content="{}", headers={"Content-Type": "text/plain"}
        ).status_code
        == 415
    )


def test_team_role_pages_constraints_and_account_version(admin_client, seeded_user):
    client = admin_client
    team = created(client)
    path = f"/api/v1/users/{seeded_user}/team-roles"
    for version, role in enumerate(("viewer", "operations_manager"), 1):
        response = client.post(
            path,
            json={"team_id": team["id"], "role_name": role, "enabled": True},
            headers=preconditions(version),
        )
        assert response.status_code == 200
    page = client.get(path + "?limit=1")
    assert page.headers["etag"] == '"3"'
    assert len(page.json()["items"]) == 1 and page.json()["next_cursor"]
    item = page.json()["items"][0]
    assert item["team_id"] == team["id"] and item["team_name"] == "Support"
    assert item["team_active"] is True
    other = client.get(path, params={"limit": 1, "cursor": page.json()["next_cursor"]})
    assert other.json()["items"][0]["id"] != item["id"]
    assert other.json()["next_cursor"] is None
    assert client.get(path + "?search=all").status_code == 422
    assert client.get(path, params={"cursor": "bad"}).status_code == 422
    bad = client.post(
        path,
        json={"team_id": team["id"], "role_name": "platform_admin", "enabled": True},
        headers=preconditions(3),
    )
    assert bad.status_code == 422
    client.patch(f"/api/v1/teams/{team['id']}", json={"active": False}, headers=preconditions())
    blocked = client.post(
        path,
        json={"team_id": team["id"], "role_name": "viewer", "enabled": True},
        headers=preconditions(3),
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "team_inactive"


def test_version_exhaustion_rolls_back(admin_client, db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        db.get(User, seeded_user).auth_version = 2147483647
    path = f"/api/v1/users/{seeded_user}/activation"
    response = admin_client.post(path, json={"active": False}, headers=preconditions(2147483647))
    assert response.status_code == 409 and response.json()["code"] == "version_exhausted"
    with Session(db_engine) as db:
        assert db.get(User, seeded_user).active
        assert not list(
            db.scalars(
                select(SessionRecord).where(
                    SessionRecord.user_id == seeded_user, SessionRecord.revoked_at.is_not(None)
                )
            )
        )


def test_concurrent_create_replay_has_one_effect_and_normalized_payload(admin_client, db_engine):
    headers = {"Idempotency-Key": uuid4().hex, "X-Correlation-ID": "account-create-proof"}
    body = {"email": " Replay@Example.Test ", "display_name": " Replay ", "password": TEST_PASSWORD}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: admin_client.post("/api/v1/users", json=body, headers=headers), range(2)
            )
        )
    assert all(response.status_code == 201 for response in responses)
    assert responses[0].json() == responses[1].json()
    body.update(email="replay@example.test", display_name="Replay")
    assert (
        admin_client.post("/api/v1/users", json=body, headers=headers).json() == responses[0].json()
    )
    body["password"] += "changed"
    assert admin_client.post("/api/v1/users", json=body, headers=headers).status_code == 409
    with Session(db_engine) as db:
        events = list(
            db.scalars(select(AuditLog).where(AuditLog.resource_id == responses[0].json()["id"]))
        )
        assert len(events) == 1 and events[0].correlation_id == "account-create-proof"
        assert len(list(db.scalars(select(IdempotencyRecord)))) == 1


def test_inactive_account_grant_rejected_and_strict_boolean(admin_client, seeded_user):
    path = f"/api/v1/users/{seeded_user}"
    for invalid in (1, "true", None):
        response = admin_client.post(
            path + "/activation", json={"active": invalid}, headers=preconditions()
        )
        assert response.status_code == 422
    assert (
        admin_client.post(
            path + "/activation", json={"active": False}, headers=preconditions()
        ).status_code
        == 200
    )
    denied = admin_client.post(
        path + "/platform-admin", json={"enabled": True}, headers=preconditions(2)
    )
    assert denied.status_code == 409 and denied.json()["code"] == "account_inactive"
    team = created(admin_client)
    denied = admin_client.post(
        path + "/team-roles",
        json={"enabled": True, "team_id": team["id"], "role_name": "viewer"},
        headers=preconditions(2),
    )
    assert denied.status_code == 409 and denied.json()["code"] == "account_inactive"
