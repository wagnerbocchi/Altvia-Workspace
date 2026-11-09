from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from altvia import identity, management
from altvia.models import AuditLog, OutboxEvent, RoleBinding, Team, User
from conftest import TEST_PASSWORD
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_sessions import login


@pytest.fixture
def team_id(db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        team = Team(name="Delegated group")
        db.add(team)
        db.flush()
        return team.id


def grant(db, team_id, role="viewer", enabled=True, email="employee@example.test"):
    return management.set_team_role(db, email, team_id, role, enabled)


def test_grant_and_revoke_are_audited_idempotent_and_revoke_sessions(
    client, db_engine, team_id, seeded_user
):
    assert login(client).status_code == 201
    with Session(db_engine) as db, db.begin():
        assert grant(db, team_id)
        assert not grant(db, team_id)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).json()["user"]["capabilities"] == []
    with Session(db_engine) as db, db.begin():
        assert grant(db, team_id, enabled=False)
        assert not grant(db, team_id, enabled=False)
    assert client.get("/api/v1/auth/me").status_code == 401
    with Session(db_engine) as db:
        assert db.get(User, seeded_user).auth_version == 3
        changes = db.scalars(
            select(OutboxEvent).where(
                OutboxEvent.event_type.in_(
                    [
                        "identity.team_role_granted",
                        "identity.team_role_revoked",
                    ]
                )
            )
        ).all()
        assert len(changes) == 2
        for event in changes:
            assert event.aggregate_id == seeded_user
            assert (
                event.payload["team_id"] == str(team_id) and event.payload["role_name"] == "viewer"
            )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.action.in_(
                        ["identity.team_role_granted", "identity.team_role_revoked"]
                    )
                )
            )
            == 2
        )


def test_same_role_on_multiple_teams_and_other_role_survive_targeted_revoke(
    db_engine, team_id, seeded_user
):
    with Session(db_engine) as db, db.begin():
        other = Team(name="Other scope")
        db.add(other)
        db.flush()
        other_id = other.id
        assert grant(db, team_id)
        assert grant(db, other_id)
        assert grant(db, team_id, "operations_manager")
        assert grant(db, team_id, enabled=False)
    with Session(db_engine) as db:
        bindings = db.scalars(select(RoleBinding).where(RoleBinding.user_id == seeded_user)).all()
        assert {(row.role_name, row.team_id) for row in bindings} == {
            ("viewer", other_id),
            ("operations_manager", team_id),
        }
        assert identity.capabilities(db, db.get(User, seeded_user)) == []


@pytest.mark.parametrize("inactive", ["user", "team"])
def test_inactive_target_cannot_receive_grant(db_engine, team_id, seeded_user, inactive):
    with Session(db_engine) as db, db.begin():
        if inactive == "user":
            management.set_account_active(db, "employee@example.test", False)
        else:
            db.get(Team, team_id).active = False
    with Session(db_engine) as db, db.begin(), pytest.raises(identity.IdentityError) as error:
        grant(db, team_id)
    assert error.value.code == ("account_inactive" if inactive == "user" else "team_inactive")
    with Session(db_engine) as db:
        assert db.scalar(select(RoleBinding).where(RoleBinding.user_id == seeded_user)) is None


def test_revocation_remains_possible_for_inactive_targets(db_engine, team_id, seeded_user):
    with Session(db_engine) as db, db.begin():
        grant(db, team_id)
        management.set_account_active(db, "employee@example.test", False)
        db.get(Team, team_id).active = False
    with Session(db_engine) as db, db.begin():
        assert grant(db, team_id, enabled=False)
    with Session(db_engine) as db:
        assert not db.get(User, seeded_user).active
        assert db.scalar(select(RoleBinding).where(RoleBinding.user_id == seeded_user)) is None


@pytest.mark.parametrize("role", ["platform_admin", "agent", "unknown"])
def test_no_generic_role_escalation(db_engine, team_id, role):
    with Session(db_engine) as db, db.begin(), pytest.raises(identity.IdentityError) as error:
        grant(db, team_id, role)
    assert error.value.code == "invalid_team_role"


@pytest.mark.parametrize("missing", ["user", "team"])
def test_unknown_target_is_not_provisioned(db_engine, team_id, missing):
    with Session(db_engine) as db, db.begin(), pytest.raises(identity.IdentityError) as error:
        grant(
            db,
            uuid4() if missing == "team" else team_id,
            email="missing@example.test" if missing == "user" else "employee@example.test",
        )
    assert error.value.status == 404


def test_failed_transaction_restores_grant_version_session_and_history(
    client, db_engine, team_id, seeded_user
):
    assert login(client).status_code == 201
    with pytest.raises(RuntimeError), Session(db_engine) as db, db.begin():
        grant(db, team_id)
        db.flush()
        raise RuntimeError("operation interrupted")
    assert client.get("/api/v1/auth/me").status_code == 200
    with Session(db_engine) as db:
        assert db.get(User, seeded_user).auth_version == 1
        assert db.scalar(select(RoleBinding).where(RoleBinding.user_id == seeded_user)) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "identity.team_role_granted")
            )
            == 0
        )


def test_concurrent_duplicate_grant_has_one_effect(db_engine, team_id, seeded_user):
    barrier = Barrier(2)

    def apply():
        barrier.wait(timeout=10)
        with Session(db_engine) as db, db.begin():
            return grant(db, team_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(apply), pool.submit(apply)
        assert sorted([first.result(timeout=20), second.result(timeout=20)]) == [False, True]
    with Session(db_engine) as db:
        assert db.get(User, seeded_user).auth_version == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(RoleBinding)
                .where(RoleBinding.user_id == seeded_user)
            )
            == 1
        )


def test_team_grants_do_not_count_as_global_administrators(client, db_engine, team_id):
    with Session(db_engine) as db, db.begin():
        management.bootstrap_admin(db, "admin@example.test", "Admin", TEST_PASSWORD)
        grant(db, team_id, "operations_manager")
    with Session(db_engine) as db, db.begin(), pytest.raises(identity.IdentityError) as error:
        management.set_platform_admin(db, "admin@example.test", False)
    assert error.value.code == "last_active_admin"
