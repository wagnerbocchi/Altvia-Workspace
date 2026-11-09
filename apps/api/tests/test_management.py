import pytest
from altvia.identity import IdentityError
from altvia.management import bootstrap_admin, reset_password
from altvia.models import RoleBinding, User
from conftest import TEST_PASSWORD
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_sessions import login


def test_one_time_bootstrap_creates_only_identity_capability(client, db_engine):
    with Session(db_engine) as db, db.begin():
        bootstrap_admin(db, " ADMIN@example.test ", "Administrator", TEST_PASSWORD)
    with Session(db_engine) as db:
        user = db.scalar(select(User).where(User.email_normalized == "admin@example.test"))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert TEST_PASSWORD not in user.password_hash
        binding = db.scalar(select(RoleBinding).where(RoleBinding.user_id == user.id))
        assert binding.role_name == "platform_admin"
    with Session(db_engine) as db, db.begin(), pytest.raises(IdentityError) as error:
        bootstrap_admin(db, "second@example.test", "Second", TEST_PASSWORD)
    assert error.value.code == "already_bootstrapped"
    response = client.post(
        "/api/v1/auth/sessions",
        json={
            "email": "admin@example.test",
            "password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["capabilities"] == ["identity.manage"]


def test_password_reset_revokes_old_session_and_requires_new_password(client, db_engine):
    assert login(client).status_code == 201
    new_password = "A different secure test password!"
    with Session(db_engine) as db, db.begin():
        reset_password(db, "employee@example.test", new_password)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/sessions",
            json={
                "email": "employee@example.test",
                "password": new_password,
            },
        ).status_code
        == 201
    )


def test_bootstrap_rejects_weak_password_without_creating_user(client, db_engine):
    with Session(db_engine) as db, db.begin(), pytest.raises(IdentityError):
        bootstrap_admin(db, "admin@example.test", "Admin", "short")
    with Session(db_engine) as db:
        assert db.scalar(select(User).where(User.email_normalized == "admin@example.test")) is None
