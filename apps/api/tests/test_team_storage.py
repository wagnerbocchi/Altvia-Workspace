from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from altvia import models
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def team(db):
    row = models.Team(name="Support", active=True, version=1)
    db.add(row)
    db.flush()
    return row.id


def operation(actor_id, route="/api/v1/teams", key="retry-1", **changes):
    now = datetime.now(UTC)
    values = dict(
        actor_id=actor_id,
        route=route,
        key=key,
        request_hash="a" * 64,
        status_code=201,
        result={"saved": "safe metadata"},
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    values.update(changes)
    return models.IdempotencyRecord(**values)


def test_team_and_roster_persist_across_connections(db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        team_id = team(db)
        db.add(models.TeamMember(team_id=team_id, user_id=seeded_user, active=True))
    with Session(db_engine) as db:
        persisted = db.get(models.Team, team_id)
        member = db.get(models.TeamMember, (team_id, seeded_user))
        assert persisted.name == "Support" and persisted.version == 1 and persisted.active
        assert persisted.created_at.tzinfo and persisted.updated_at.tzinfo
        assert member.active and member.created_at.tzinfo and member.updated_at.tzinfo


@pytest.mark.parametrize(
    "name,version", [("", 1), ("   ", 1), ("x" * 151, 1), ("Team", 0), ("Team", -1)]
)
def test_database_rejects_invalid_team_values(db_engine, seeded_user, name, version):
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.add(models.Team(name=name, version=version, active=True))
        db.flush()


def test_duplicate_display_names_do_not_merge_team_identity(db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        first, second = team(db), team(db)
        assert first != second
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(models.Team)) == 2


@pytest.mark.parametrize("missing", ["team", "user"])
def test_membership_requires_real_team_and_account(db_engine, seeded_user, missing):
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        team_id = uuid4() if missing == "team" else team(db)
        user_id = uuid4() if missing == "user" else seeded_user
        db.add(models.TeamMember(team_id=team_id, user_id=user_id, active=True))
        db.flush()


def test_membership_is_unique_even_when_inactive(db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        team_id = team(db)
        db.add(models.TeamMember(team_id=team_id, user_id=seeded_user, active=False))
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.add(models.TeamMember(team_id=team_id, user_id=seeded_user, active=True))
        db.flush()


def test_idempotency_namespace_is_actor_route_and_key(db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        original = db.get(models.User, seeded_user)
        other = models.User(
            email_normalized="other@example.test",
            display_name="Other",
            password_hash=original.password_hash,
            active=True,
            auth_version=1,
            created_at=datetime.now(UTC),
        )
        db.add(other)
        db.flush()
        db.add_all(
            [
                operation(seeded_user),
                operation(other.id),
                operation(seeded_user, route="/api/v1/teams/another/members"),
            ]
        )
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.add(operation(seeded_user))
        db.flush()
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(models.IdempotencyRecord)) == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"key": ""},
        {"key": "space invalid"},
        {"status_code": 500},
        {"expires_at": datetime.now(UTC) + timedelta(days=1)},
    ],
)
def test_idempotency_records_reject_invalid_keys_status_and_retention(
    db_engine,
    seeded_user,
    changes,
):
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.add(operation(seeded_user, **changes))
        db.flush()
