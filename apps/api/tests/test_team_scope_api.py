from uuid import UUID

import pytest
from altvia import management
from altvia.models import Team, TeamMember
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in  # noqa: F401


@pytest.fixture
def scopes(client, db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        teams = [Team(id=UUID(int=i), name=f"Team {i}") for i in range(1, 7)]
        db.add_all(teams)
        db.flush()
        db.add(TeamMember(team_id=teams[1].id, user_id=seeded_user))
        return [str(team.id) for team in teams]


def grant(db_engine, team_id, role="viewer", enabled=True):
    with Session(db_engine) as db, db.begin():
        management.set_team_role(db, "employee@example.test", UUID(team_id), role, enabled)


@pytest.mark.parametrize("role", ["viewer", "operations_manager"])
def test_scoped_reads_filter_before_pagination_and_authorize_rosters(
    client, db_engine, seeded_user, scopes, role
):
    for team_id in [scopes[1], scopes[3], scopes[5]]:
        grant(db_engine, team_id, role)
    grant(db_engine, scopes[1], "viewer" if role == "operations_manager" else "operations_manager")
    assert sign_in(client, "employee@example.test")["capabilities"] == []
    cursor = None
    seen = []
    for expected in [scopes[1], scopes[3], scopes[5]]:
        params = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/api/v1/teams", params=params)
        assert response.status_code == 200
        page = response.json()
        assert [row["id"] for row in page["items"]] == [expected]
        seen.append(page["items"][0]["id"])
        cursor = page["next_cursor"]
    assert cursor is None and seen == [scopes[1], scopes[3], scopes[5]]
    for index, team_id in enumerate(scopes):
        detail = client.get(f"/api/v1/teams/{team_id}")
        roster = client.get(f"/api/v1/teams/{team_id}/members")
        assert detail.status_code == roster.status_code == (200 if index % 2 else 404)
        if index == 1:
            assert roster.json()["items"][0]["user_id"] == str(seeded_user)
            assert set(roster.json()["items"][0]) == {"user_id", "display_name", "account_active"}
        if index % 2 == 0:
            assert f"Team {index + 1}" not in detail.text + roster.text
    assert client.get("/api/v1/users").status_code == 403


@pytest.mark.parametrize("role", ["viewer", "operations_manager"])
@pytest.mark.usefixtures("admin_client")
def test_scoped_reader_cannot_mutate_or_replay_global_administrative_operations(
    client, db_engine, seeded_user, role
):
    key = "admin-only-replay"
    response = client.post(
        "/api/v1/teams", json={"name": "Original"}, headers={"Idempotency-Key": key}
    )
    team_id = response.json()["id"]
    grant(db_engine, team_id, role)
    sign_in(client, "employee@example.test")
    path = f"/api/v1/teams/{team_id}"
    responses = [
        client.post("/api/v1/teams", json={"name": "Original"}, headers={"Idempotency-Key": key}),
        client.patch(path, json={"name": "Forbidden"}, headers=preconditions()),
        client.post(f"{path}/members", json={"user_id": str(seeded_user)}, headers=preconditions()),
        client.delete(f"{path}/members/{seeded_user}", headers=preconditions()),
        client.get("/api/v1/users"),
    ]
    assert [response.status_code for response in responses] == [403] * 5
    assert client.get(path).json()["name"] == "Original"
    assert client.get(f"{path}/members").json()["items"] == []


def test_membership_alone_is_denied_and_binding_without_membership_allows(
    client, db_engine, scopes
):
    sign_in(client, "employee@example.test")
    assert client.get(f"/api/v1/teams/{scopes[1]}/members").status_code == 403
    grant(db_engine, scopes[3])
    sign_in(client, "employee@example.test")
    assert client.get(f"/api/v1/teams/{scopes[3]}/members").status_code == 200
    assert client.get(f"/api/v1/teams/{scopes[1]}/members").status_code == 404


def test_revocation_invalidates_session_and_removes_only_target_scope(client, db_engine, scopes):
    grant(db_engine, scopes[1])
    grant(db_engine, scopes[3])
    sign_in(client, "employee@example.test")
    grant(db_engine, scopes[1], enabled=False)
    assert client.get("/api/v1/teams").status_code == 401
    sign_in(client, "employee@example.test")
    assert client.get(f"/api/v1/teams/{scopes[1]}").status_code == 404
    assert client.get(f"/api/v1/teams/{scopes[3]}").status_code == 200
    grant(db_engine, scopes[3], enabled=False)
    sign_in(client, "employee@example.test")
    assert client.get("/api/v1/teams").status_code == 403


def test_archive_retains_explicit_read_but_disabled_account_has_no_access(
    client, db_engine, scopes
):
    grant(db_engine, scopes[1])
    sign_in(client, "employee@example.test")
    with Session(db_engine) as db, db.begin():
        db.get(Team, UUID(scopes[1])).active = False
    assert client.get(f"/api/v1/teams/{scopes[1]}").json()["active"] is False
    assert client.get(f"/api/v1/teams/{scopes[1]}/members").status_code == 200
    with Session(db_engine) as db, db.begin():
        management.set_account_active(db, "employee@example.test", False)
    assert client.get("/api/v1/teams").status_code == 401


@pytest.mark.usefixtures("admin_client")
def test_former_admin_with_team_read_role_cannot_replay_own_saved_write(client, db_engine):
    headers = {"Idempotency-Key": "former-admin-replay"}
    body = {"name": "Historical result"}
    original = client.post("/api/v1/teams", json=body, headers=headers)
    assert original.status_code == 201
    team_id = original.json()["id"]
    with Session(db_engine) as db, db.begin():
        management.set_platform_admin(db, "employee@example.test", True)
        management.set_team_role(db, "admin@example.test", UUID(team_id), "viewer", True)
        management.set_platform_admin(db, "admin@example.test", False)
    assert client.post("/api/v1/teams", json=body, headers=headers).status_code == 401
    assert sign_in(client, "admin@example.test")["capabilities"] == []
    assert client.get(f"/api/v1/teams/{team_id}").status_code == 200
    assert client.post("/api/v1/teams", json=body, headers=headers).status_code == 403
