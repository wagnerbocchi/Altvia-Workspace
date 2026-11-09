import secrets

import pytest
from altvia import management, provision
from altvia.main import create_app
from conftest import TEST_PASSWORD
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_team_api import sign_in


def runtime_url(db_engine):
    return db_engine.url.set(username="altvia_app", password=secrets.token_urlsafe(24))


def test_worker_role_is_restricted_and_api_activity_is_read_only(db_engine, seeded_user):
    worker = runtime_url(db_engine).set(username="altvia_worker")
    provision.provision_runtime(
        db_engine,
        runtime_url(db_engine).render_as_string(hide_password=False),
        worker.render_as_string(hide_password=False),
    )
    engine = create_engine(worker, hide_parameters=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT event_id FROM outbox_events LIMIT 1"))
            connection.execute(text("SELECT event_id FROM activity_events LIMIT 1"))
            connection.execute(text("SELECT event_id FROM processed_events LIMIT 1"))
        for statement in (
            "SELECT * FROM users",
            "SELECT * FROM sessions",
            "SELECT * FROM audit_logs",
            "UPDATE users SET active=false",
            "UPDATE outbox_events SET payload='{}'",
            "DELETE FROM outbox_events",
            "DELETE FROM activity_events",
            "DELETE FROM processed_events",
            "UPDATE activity_events SET event_type='forged'",
            "CREATE TABLE forbidden_worker(id int)",
            "CREATE ROLE forbidden_worker_admin SUPERUSER",
        ):
            with engine.begin() as connection, pytest.raises(DBAPIError):
                connection.execute(text(statement))
    finally:
        engine.dispose()


def test_runtime_role_can_operate_api_but_cannot_migrate_or_rewrite_history(
    db_engine, seeded_user, settings
):
    url = runtime_url(db_engine)
    provision.provision_runtime(db_engine, url.render_as_string(hide_password=False))
    provision.provision_runtime(db_engine, url.render_as_string(hide_password=False))
    with Session(db_engine) as db, db.begin():
        management.bootstrap_admin(db, "admin@example.test", "Runtime admin", TEST_PASSWORD)
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == "altvia_app"
        for statement in [
            "CREATE TABLE forbidden_runtime_ddl(id int)",
            "CREATE SCHEMA forbidden_runtime_schema",
            "CREATE TEMP TABLE forbidden_runtime_temp(id int)",
            "SELECT * FROM audit_logs",
            "UPDATE audit_logs SET action='tampered'",
            "DELETE FROM audit_logs",
            "SELECT * FROM outbox_events",
            "UPDATE outbox_events SET status='delivered'",
            "SELECT * FROM alembic_version",
            "CREATE ROLE forbidden_runtime_admin SUPERUSER",
        ]:
            with engine.begin() as connection, pytest.raises(DBAPIError):
                connection.execute(text(statement))
        runtime_settings = settings.model_copy(
            update={
                "database_url": settings.database_url.__class__(
                    url.render_as_string(hide_password=False)
                )
            }
        )
        with TestClient(
            create_app(runtime_settings),
            base_url=settings.public_origin,
            headers={"Origin": settings.public_origin},
        ) as client:
            assert client.get("/api/v1/health/ready").status_code == 200
            sign_in(client, "employee@example.test")
            assert client.get("/api/v1/auth/me").status_code == 200
            sign_in(client, "admin@example.test")
            team = client.post(
                "/api/v1/teams",
                json={"name": "Runtime team"},
                headers={"Idempotency-Key": "runtime-proof"},
            )
            assert team.status_code == 201
            assert client.get(f"/api/v1/teams/{team.json()['id']}").status_code == 200
            assert client.delete("/api/v1/auth/sessions/current").status_code == 204
            assert client.get("/api/v1/auth/me").status_code == 401
    finally:
        engine.dispose()


def test_runtime_password_uses_driver_quoting(db_engine, seeded_user):
    url = runtime_url(db_engine).set(password="Synthetic ' quote ; -- password")
    provision.provision_runtime(db_engine, url.render_as_string(hide_password=False))
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == "altvia_app"
    finally:
        engine.dispose()


def test_provision_failure_does_not_echo_secrets(monkeypatch, capsys):
    secret = "postgresql+psycopg://owner:private-password@postgres/altvia_test"

    def invalid():
        raise ValueError(secret)

    monkeypatch.setattr(provision, "Settings", invalid)
    assert provision.main() == 1
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err


@pytest.mark.parametrize(
    "grant,revoke",
    [
        (
            "GRANT SELECT ON users TO altvia_app WITH GRANT OPTION",
            "REVOKE GRANT OPTION FOR SELECT ON users FROM altvia_app",
        ),
        (
            "GRANT CREATE ON DATABASE {} TO altvia_app",
            "REVOKE CREATE ON DATABASE {} FROM altvia_app",
        ),
        ("GRANT TEMP ON DATABASE {} TO altvia_app", "REVOKE TEMP ON DATABASE {} FROM altvia_app"),
        (
            "GRANT CREATE ON SCHEMA public TO altvia_app",
            "REVOKE CREATE ON SCHEMA public FROM altvia_app",
        ),
        (
            "GRANT UPDATE(action) ON audit_logs TO altvia_app",
            "REVOKE UPDATE(action) ON audit_logs FROM altvia_app",
        ),
        ("GRANT SELECT ON audit_logs TO PUBLIC", "REVOKE SELECT ON audit_logs FROM PUBLIC"),
        (
            "GRANT UPDATE(action) ON audit_logs TO PUBLIC",
            "REVOKE UPDATE(action) ON audit_logs FROM PUBLIC",
        ),
    ],
)
def test_preexisting_database_schema_or_history_acl_is_refused_atomically(
    db_engine, seeded_user, grant, revoke
):
    url = runtime_url(db_engine)
    provision.provision_runtime(db_engine, url.render_as_string(hide_password=False))
    with db_engine.begin() as connection:
        connection.connection.driver_connection.execute(
            sql.SQL(grant).format(sql.Identifier(db_engine.url.database))
        )
    try:
        changed = url.set(password=secrets.token_urlsafe(32))
        with pytest.raises(ValueError):
            provision.provision_runtime(db_engine, changed.render_as_string(hide_password=False))
        # Rejection must precede password rotation or partial privilege mutation.
        engine = create_engine(url, hide_parameters=True)
        try:
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT current_user")) == "altvia_app"
        finally:
            engine.dispose()
    finally:
        with db_engine.begin() as connection:
            connection.connection.driver_connection.execute(
                sql.SQL(revoke).format(sql.Identifier(db_engine.url.database))
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("username", "postgres"),
        ("database", "other_database"),
        ("host", "untrusted.example.test"),
        ("port", 1),
        ("password", None),
    ],
)
def test_runtime_credentials_must_target_same_database_and_fixed_role(db_engine, field, value):
    url = runtime_url(db_engine)
    if field == "password":
        url = url._replace(password=None)
    else:
        url = url.set(**{field: value})
    with pytest.raises(ValueError):
        provision.provision_runtime(db_engine, url.render_as_string(hide_password=False))


@pytest.mark.parametrize("elevated", ["superuser", "membership", "ownership"])
def test_existing_elevated_runtime_role_is_refused(db_engine, seeded_user, elevated):
    url = runtime_url(db_engine)
    provision.provision_runtime(db_engine, url.render_as_string(hide_password=False))
    with db_engine.begin() as connection:
        if elevated == "superuser":
            connection.execute(text("ALTER ROLE altvia_app SUPERUSER"))
        elif elevated == "membership":
            connection.connection.driver_connection.execute(
                sql.SQL("GRANT {} TO altvia_app").format(sql.Identifier(db_engine.url.username))
            )
        else:
            connection.execute(text("ALTER TABLE users OWNER TO altvia_app"))
    try:
        with pytest.raises(ValueError):
            provision.provision_runtime(db_engine, url.render_as_string(hide_password=False))
    finally:
        with db_engine.begin() as connection:
            if elevated == "superuser":
                connection.execute(text("ALTER ROLE altvia_app NOSUPERUSER"))
            elif elevated == "membership":
                connection.connection.driver_connection.execute(
                    sql.SQL("REVOKE {} FROM altvia_app").format(
                        sql.Identifier(db_engine.url.username)
                    )
                )
            else:
                connection.execute(text("ALTER TABLE users OWNER TO CURRENT_USER"))
