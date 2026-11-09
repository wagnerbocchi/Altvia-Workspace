from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from altvia import management
from altvia.identity import IdentityError
from altvia.models import AuditLog, OutboxEvent, RoleBinding, SessionRecord, User
from conftest import TEST_PASSWORD
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_sessions import login


def account(db, email="employee@example.test"):
    return db.scalar(select(User).where(User.email_normalized == email))


def bootstrap(db_engine):
    with Session(db_engine) as db, db.begin():
        management.bootstrap_admin(db, "admin@example.test", "Administrator", TEST_PASSWORD)


def test_provision_ordinary_user_has_real_login_without_admin_access(client, db_engine):
    with Session(db_engine) as db, db.begin():
        management.create_user(db, " NEW@example.test ", " New Employee ", TEST_PASSWORD)
    with Session(db_engine) as db:
        user = account(db, "new@example.test")
        assert user.display_name == "New Employee"
        assert user.active and user.password_hash.startswith("$argon2id$")
        assert TEST_PASSWORD not in user.password_hash
        assert db.scalar(select(RoleBinding).where(RoleBinding.user_id == user.id)) is None
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == user.id))
        audit = db.scalar(select(AuditLog).where(AuditLog.resource_id == user.id))
        assert event.event_type == audit.action == "identity.user_created"
        assert TEST_PASSWORD not in str(event.payload) + str(audit.details)
    response = client.post(
        "/api/v1/auth/sessions",
        json={
            "email": "new@example.test",
            "password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["capabilities"] == []


def test_create_duplicate_is_case_normalized_and_has_no_partial_effect(client, db_engine):
    with Session(db_engine) as db, db.begin(), pytest.raises(IdentityError) as error:
        management.create_user(db, " EMPLOYEE@example.test ", "Duplicate", TEST_PASSWORD)
    assert error.value.code == "account_already_exists"
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 0


@pytest.mark.parametrize(
    "email,name,password",
    [
        ("invalid", "Name", TEST_PASSWORD),
        ("new@example.test", " ", TEST_PASSWORD),
        ("new@example.test", "x" * 151, TEST_PASSWORD),
        ("new@example.test", "Name", "short"),
        ("new@example.test", "Name", "é" * 513),
    ],
    ids=["invalid-email", "empty-name", "long-name", "short-password", "oversized-password"],
)
def test_invalid_provisioning_does_not_persist(client, db_engine, email, name, password):
    with Session(db_engine) as db, db.begin(), pytest.raises((ValueError, IdentityError)):
        management.create_user(db, email, name, password)
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 0


def test_disable_and_reenable_revoke_tokens_without_resurrection(client, db_engine):
    assert login(client).status_code == 201
    with Session(db_engine) as db, db.begin():
        assert management.set_account_active(db, "employee@example.test", False)
        assert not management.set_account_active(db, "employee@example.test", False)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).status_code == 401
    with Session(db_engine) as db, db.begin():
        assert management.set_account_active(db, "employee@example.test", True)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).status_code == 201
    with Session(db_engine) as db:
        assert account(db).auth_version == 3
        changes = db.scalars(
            select(AuditLog.action).where(
                AuditLog.action.in_(["identity.user_disabled", "identity.user_enabled"])
            )
        ).all()
        assert sorted(changes) == ["identity.user_disabled", "identity.user_enabled"]


def test_admin_grant_and_revoke_invalidate_sessions_and_are_idempotent(client, db_engine):
    bootstrap(db_engine)
    assert login(client).status_code == 201
    with Session(db_engine) as db, db.begin():
        assert management.set_platform_admin(db, "employee@example.test", True)
        assert not management.set_platform_admin(db, "employee@example.test", True)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).json()["user"]["capabilities"] == ["identity.manage"]
    with Session(db_engine) as db, db.begin():
        assert management.set_platform_admin(db, "employee@example.test", False)
        assert not management.set_platform_admin(db, "employee@example.test", False)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).json()["user"]["capabilities"] == []
    with Session(db_engine) as db:
        assert account(db).auth_version == 3
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action.in_(["identity.admin_granted", "identity.admin_revoked"]))
            )
            == 2
        )


@pytest.mark.parametrize("operation", ["disable", "revoke"])
def test_last_active_admin_is_protected(client, db_engine, operation):
    bootstrap(db_engine)
    with Session(db_engine) as db, db.begin(), pytest.raises(IdentityError) as error:
        if operation == "disable":
            management.set_account_active(db, "admin@example.test", False)
        else:
            management.set_platform_admin(db, "admin@example.test", False)
    assert error.value.code == "last_active_admin"
    with Session(db_engine) as db:
        user = account(db, "admin@example.test")
        assert user.active and user.auth_version == 1
        assert db.scalar(select(RoleBinding).where(RoleBinding.user_id == user.id)) is not None
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 1


def test_inactive_admin_does_not_satisfy_last_admin_guard(client, db_engine):
    bootstrap(db_engine)
    # Synthetic legacy/corrupt state: a bound but inactive second account.
    with Session(db_engine) as db, db.begin():
        user = account(db)
        user.active = False
        db.add(RoleBinding(user_id=user.id, role_name="platform_admin", scope_kind="global"))
    with Session(db_engine) as db, db.begin(), pytest.raises(IdentityError):
        management.set_account_active(db, "admin@example.test", False)


def test_inactive_account_cannot_receive_new_admin_grant(client, db_engine):
    with Session(db_engine) as db, db.begin():
        management.set_account_active(db, "employee@example.test", False)
    with Session(db_engine) as db, db.begin(), pytest.raises(IdentityError) as error:
        management.set_platform_admin(db, "employee@example.test", True)
    assert error.value.code == "account_inactive"


@pytest.mark.parametrize("operation", ["active", "role"])
def test_missing_account_is_rejected(client, db_engine, operation):
    with Session(db_engine) as db, db.begin(), pytest.raises(IdentityError) as error:
        if operation == "active":
            management.set_account_active(db, "missing@example.test", True)
        else:
            management.set_platform_admin(db, "missing@example.test", True)
    assert error.value.code == "account_not_found"


def test_rollback_preserves_account_sessions_and_audit(client, db_engine):
    assert login(client).status_code == 201
    with Session(db_engine) as db:
        event_count = db.scalar(select(func.count()).select_from(OutboxEvent))
    with pytest.raises(RuntimeError), Session(db_engine) as db, db.begin():
        management.set_account_active(db, "employee@example.test", False)
        raise RuntimeError("transaction interrupted")
    assert client.get("/api/v1/auth/me").status_code == 200
    with Session(db_engine) as db:
        assert account(db).active and account(db).auth_version == 1
        assert db.scalar(select(SessionRecord.revoked_at)) is None
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == event_count


@pytest.mark.parametrize("mixed", [False, True])
def test_concurrent_admin_removals_leave_one_active_admin(client, db_engine, mixed):
    bootstrap(db_engine)
    with Session(db_engine) as db, db.begin():
        management.set_platform_admin(db, "employee@example.test", True)
    barrier = Barrier(2)

    def remove(email, disable):
        barrier.wait(timeout=5)
        try:
            with Session(db_engine) as db, db.begin():
                if disable:
                    management.set_account_active(db, email, False)
                else:
                    management.set_platform_admin(db, email, False)
            return "changed"
        except IdentityError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(remove, "admin@example.test", mixed)
        second = pool.submit(remove, "employee@example.test", False)
        assert sorted([first.result(timeout=10), second.result(timeout=10)]) == [
            "changed",
            "last_active_admin",
        ]
    with Session(db_engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(User)
                .join(
                    RoleBinding,
                    RoleBinding.user_id == User.id,
                )
                .where(User.active.is_(True), RoleBinding.role_name == "platform_admin")
            )
            == 1
        )


def test_create_rolls_back_when_enclosing_transaction_fails(client, db_engine):
    with pytest.raises(RuntimeError), Session(db_engine) as db, db.begin():
        management.create_user(db, "new@example.test", "New", TEST_PASSWORD)
        db.flush()
        raise RuntimeError("interrupted after outbox insert")
    with Session(db_engine) as db:
        assert account(db, "new@example.test") is None
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 0
