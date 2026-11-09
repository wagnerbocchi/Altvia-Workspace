from uuid import uuid4

import pytest
from altvia.models import Role, RoleBinding, Team
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def roles(db):
    for name in ["platform_admin", "viewer", "operations_manager", "agent"]:
        db.execute(insert(Role).values(name=name).on_conflict_do_nothing())


def make_team(db):
    row = Team(name="Scope team")
    db.add(row)
    db.flush()
    return row.id


def test_binding_uuid_preserves_global_and_multiple_team_grants(db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        roles(db)
        first, second = make_team(db), make_team(db)
        db.add_all(
            [
                RoleBinding(user_id=seeded_user, role_name="platform_admin", scope_kind="global"),
                RoleBinding(
                    user_id=seeded_user, role_name="viewer", scope_kind="team", team_id=first
                ),
                RoleBinding(
                    user_id=seeded_user, role_name="viewer", scope_kind="team", team_id=second
                ),
                RoleBinding(
                    user_id=seeded_user,
                    role_name="operations_manager",
                    scope_kind="team",
                    team_id=first,
                ),
            ]
        )
    with Session(db_engine) as db:
        bindings = db.scalars(select(RoleBinding).where(RoleBinding.user_id == seeded_user)).all()
        assert len(bindings) == len({row.id for row in bindings}) == 4
        global_row = next(row for row in bindings if row.scope_kind == "global")
        assert global_row.team_id is None


@pytest.mark.parametrize(
    "scope,role,with_team",
    [
        ("global", "viewer", False),
        ("global", "platform_admin", True),
        ("team", "platform_admin", True),
        ("team", "viewer", False),
        ("team", "agent", True),
        ("client", "viewer", True),
    ],
)
def test_scope_check_rejects_unsupported_or_ambiguous_grants(
    db_engine, seeded_user, scope, role, with_team
):
    with Session(db_engine) as db, db.begin():
        roles(db)
        team_id = make_team(db)
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.add(
            RoleBinding(
                user_id=seeded_user,
                role_name=role,
                scope_kind=scope,
                team_id=team_id if with_team else None,
            )
        )
        db.flush()


@pytest.mark.parametrize("scope", ["global", "team"])
def test_duplicate_grant_is_rejected_by_database(db_engine, seeded_user, scope):
    with Session(db_engine) as db, db.begin():
        roles(db)
        team_id = make_team(db) if scope == "team" else None
        role = "viewer" if scope == "team" else "platform_admin"
        db.add(RoleBinding(user_id=seeded_user, role_name=role, scope_kind=scope, team_id=team_id))
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.add(RoleBinding(user_id=seeded_user, role_name=role, scope_kind=scope, team_id=team_id))
        db.flush()


def test_team_scope_requires_existing_team(db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        roles(db)
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.add(
            RoleBinding(user_id=seeded_user, role_name="viewer", scope_kind="team", team_id=uuid4())
        )
        db.flush()
