import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from altvia.config import Settings
from altvia.database import make_engine
from altvia.main import create_app
from altvia.models import User
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

TEST_PASSWORD = "A long test password 2026!"


@pytest.fixture(scope="session")
def settings():
    return Settings()


@pytest.fixture(scope="session")
def db_engine(settings):
    if os.environ.get("ALTVIA_ALLOW_TEST_DB") != "1":
        pytest.fail("Integration tests require an explicitly disposable test database")
    engine = make_engine(settings)
    if engine.url.database != "altvia_test":
        pytest.fail("Integration test database must be named altvia_test")
    config = Config(str(Path("apps/api/alembic.ini")))
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def seeded_user(db_engine):
    # Only the explicitly isolated altvia_test database is reset.
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE team_members,teams,idempotency_records,"
                "sessions,role_bindings,audit_logs,outbox_events,"
                "login_buckets,users CASCADE"
            )
        )
    with Session(db_engine) as db, db.begin():
        user = User(
            email_normalized="employee@example.test",
            display_name="Test Employee",
            password_hash=PasswordHasher(memory_cost=65536, time_cost=3, parallelism=1).hash(
                TEST_PASSWORD
            ),
            active=True,
            auth_version=1,
            created_at=datetime.now(UTC),
        )
        db.add(user)
        db.flush()
        user_id = user.id
    return user_id


@pytest.fixture
def client(settings, seeded_user):
    with TestClient(
        create_app(settings),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        yield client
