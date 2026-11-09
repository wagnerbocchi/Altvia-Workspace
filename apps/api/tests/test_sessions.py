from datetime import UTC, datetime, timedelta

import pytest
from altvia.main import create_app
from altvia.models import AuditLog, OutboxEvent, SessionRecord, User
from conftest import TEST_PASSWORD
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session


def login(client):
    return client.post(
        "/api/v1/auth/sessions",
        json={
            "email": " EMPLOYEE@example.test ",
            "password": TEST_PASSWORD,
        },
    )


def test_login_persists_hashes_and_survives_app_recreation(client, settings, db_engine):
    response = login(client)
    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert all(flag in cookie for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"))
    assert "Domain=" not in cookie
    token = client.cookies["__Host-altvia_session"]
    csrf = response.json()["csrf_token"]
    with Session(db_engine) as db:
        stored = db.scalar(select(SessionRecord))
        assert stored.token_hash != token and len(stored.token_hash) == 64
        assert stored.csrf_hash != csrf
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1
    with TestClient(create_app(settings), base_url=settings.public_origin) as restarted:
        restarted.cookies.set("__Host-altvia_session", token)
        me = restarted.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == "employee@example.test"
        assert me.json()["csrf_token"] == csrf
        assert "password_hash" not in me.text


@pytest.mark.parametrize("email", ["employee@example.test", "unknown@example.test"])
def test_wrong_password_and_unknown_account_have_identical_safe_failure(client, email):
    response = client.post("/api/v1/auth/sessions", json={"email": email, "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert "set-cookie" not in response.headers
    assert "wrong" not in response.text and email not in response.text


def test_logout_requires_csrf_then_revokes_session(client):
    response = login(client)
    assert response.status_code == 201
    assert client.delete("/api/v1/auth/sessions/current").status_code == 403
    token = response.json()["csrf_token"]
    assert (
        client.delete("/api/v1/auth/sessions/current", headers={"X-CSRF-Token": token}).status_code
        == 204
    )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_wrong_origin_cannot_login_or_revoke(client):
    assert (
        client.post(
            "/api/v1/auth/sessions",
            headers={"Origin": "https://evil.test"},
            json={"email": "employee@example.test", "password": TEST_PASSWORD},
        ).status_code
        == 403
    )
    response = login(client)
    assert (
        client.delete(
            "/api/v1/auth/sessions/current",
            headers={
                "Origin": "https://evil.test",
                "X-CSRF-Token": response.json()["csrf_token"],
            },
        ).status_code
        == 403
    )
    assert client.get("/api/v1/auth/me").status_code == 200


@pytest.mark.parametrize("condition", ["absolute", "idle", "inactive", "auth_version", "revoked"])
def test_expired_revoked_or_disabled_identity_is_denied(client, db_engine, seeded_user, condition):
    assert login(client).status_code == 201
    now = datetime.now(UTC)
    with Session(db_engine) as db, db.begin():
        if condition == "absolute":
            db.execute(update(SessionRecord).values(expires_at=now - timedelta(seconds=1)))
        elif condition == "idle":
            db.execute(update(SessionRecord).values(last_seen_at=now - timedelta(minutes=31)))
        elif condition == "revoked":
            db.execute(update(SessionRecord).values(revoked_at=now))
        elif condition == "inactive":
            db.execute(update(User).where(User.id == seeded_user).values(active=False))
        else:
            db.execute(update(User).where(User.id == seeded_user).values(auth_version=2))
    assert client.get("/api/v1/auth/me").status_code == 401


def test_validation_never_echoes_credentials_and_rejects_unknown_fields(client):
    response = client.post(
        "/api/v1/auth/sessions",
        json={
            "email": "bad",
            "password": TEST_PASSWORD,
            "platform_admin": True,
        },
    )
    assert response.status_code == 422
    assert TEST_PASSWORD not in response.text
    assert "input" not in response.text


def test_login_attempt_limit_is_persistent_across_apps(client, settings):
    for _ in range(8):
        response = client.post(
            "/api/v1/auth/sessions",
            json={
                "email": "employee@example.test",
                "password": "wrong",
            },
        )
        assert response.status_code == 401
    with TestClient(
        create_app(settings),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as restarted:
        response = login(restarted)
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0


def test_oversize_login_rejected_without_echo(client):
    response = client.post(
        "/api/v1/auth/sessions", content=b"a" * 20000, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


def test_ready_checks_database(client):
    assert client.get("/api/v1/health/ready").json() == {"status": "ready"}


def test_logout_replay_is_idempotent(client):
    response = login(client)
    headers = {"X-CSRF-Token": response.json()["csrf_token"]}
    assert client.delete("/api/v1/auth/sessions/current", headers=headers).status_code == 204
    assert client.delete("/api/v1/auth/sessions/current", headers=headers).status_code == 204


def test_inactive_account_cannot_create_a_session(client, db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        db.execute(update(User).where(User.id == seeded_user).values(active=False))
    response = login(client)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(SessionRecord)) == 0


def test_session_cookie_cannot_be_used_as_csrf_token(client):
    assert login(client).status_code == 201
    response = client.delete(
        "/api/v1/auth/sessions/current",
        headers={
            "X-CSRF-Token": client.cookies["__Host-altvia_session"],
        },
    )
    assert response.status_code == 403


def test_missing_origin_rejects_credential_login(client):
    client.headers.pop("origin")
    assert login(client).status_code == 403
