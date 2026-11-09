from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from altvia import management
from altvia.models import AuditLog, IdempotencyRecord, OutboxEvent, RoleBinding, Team, TeamMember
from conftest import TEST_PASSWORD
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session


def sign_in(client, email):
    response = client.post(
        "/api/v1/auth/sessions", json={"email": email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 201
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()["user"]


@pytest.fixture
def admin_client(client, db_engine):
    with Session(db_engine) as db, db.begin():
        management.bootstrap_admin(db, "admin@example.test", "Administrator", TEST_PASSWORD)
    sign_in(client, "admin@example.test")
    return client


def preconditions(version=1, key=None):
    return {"If-Match": f'"{version}"', "Idempotency-Key": key or uuid4().hex}


def create(client, name="Support", key=None):
    return client.post(
        "/api/v1/teams",
        json={"name": name},
        headers={
            "Idempotency-Key": key or uuid4().hex,
        },
    )


def created(client, name="Support"):
    response = create(client, name)
    assert response.status_code == 201
    assert response.headers["etag"] == '"1"'
    return response.json()


def counts(db_engine):
    with Session(db_engine) as db:
        return (
            db.scalar(select(func.count()).select_from(Team)),
            db.scalar(select(func.count()).select_from(TeamMember)),
            db.scalar(select(func.count()).select_from(IdempotencyRecord)),
            db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_type == "team",
                )
            ),
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.action.startswith("identity.team_"),
                )
            ),
        )


def test_real_team_lifecycle_and_safe_account_lookup(admin_client, db_engine, seeded_user):
    client = admin_client
    users = client.get("/api/v1/users")
    assert users.status_code == 200
    assert users.headers["cache-control"].find("no-store") >= 0
    employee = next(item for item in users.json()["items"] if item["id"] == str(seeded_user))
    assert set(employee) == {"id", "display_name", "email", "active"}
    team = created(client, " Support ")
    assert team["name"] == "Support" and team["active"] and team["version"] == 1
    assert set(team) == {"id", "name", "active", "version", "created_at", "updated_at"}
    path = f"/api/v1/teams/{team['id']}"
    assert client.get(path).json() == team
    changed = client.patch(path, json={"name": "Operations"}, headers=preconditions())
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert changed.headers["etag"] == '"2"'
    no_op = client.patch(path, json={"name": "Operations"}, headers=preconditions(2))
    assert no_op.json() == changed.json()
    archived = client.patch(path, json={"active": False}, headers=preconditions(2))
    assert archived.json()["version"] == 3 and not archived.json()["active"]
    assert client.get(path).json() == archived.json()
    assert client.get("/api/v1/teams").json()["items"] == [archived.json()]
    assert counts(db_engine) == (1, 0, 1, 3, 3)


def test_roster_add_remove_reactivate_without_implicit_privileges(
    admin_client, db_engine, seeded_user
):
    client = admin_client
    team = created(client)
    path = f"/api/v1/teams/{team['id']}/members"
    added = client.post(path, json={"user_id": str(seeded_user)}, headers=preconditions())
    assert added.status_code == 201
    assert added.json() == {"team_id": team["id"], "user_id": str(seeded_user), "team_version": 2}
    assert added.headers["etag"] == '"2"'
    same = client.post(path, json={"user_id": str(seeded_user)}, headers=preconditions(2))
    assert same.status_code == 200 and same.json()["team_version"] == 2
    members = client.get(path).json()["items"]
    assert members == [
        {"user_id": str(seeded_user), "display_name": "Test Employee", "account_active": True}
    ]
    removed = client.delete(f"{path}/{seeded_user}", headers=preconditions(2))
    assert removed.status_code == 204 and removed.headers["etag"] == '"3"'
    assert client.get(path).json()["items"] == []
    assert client.delete(f"{path}/{seeded_user}", headers=preconditions(3)).headers["etag"] == '"3"'
    readded = client.post(path, json={"user_id": str(seeded_user)}, headers=preconditions(3))
    assert readded.status_code == 201 and readded.json()["team_version"] == 4
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(TeamMember)) == 1
        assert db.scalar(select(TeamMember.active))
        assert db.scalar(select(RoleBinding).where(RoleBinding.user_id == seeded_user)) is None
        events = db.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_type == "team")).all()
        for event in events:
            if event.event_type != "identity.team_created":
                assert event.payload["member_user_id"] == str(seeded_user)
    assert counts(db_engine)[3:] == (4, 4)
    user = sign_in(client, "employee@example.test")
    assert user["capabilities"] == []
    assert client.get(path).status_code == 403


@pytest.mark.parametrize("role", ["anonymous", "member"])
@pytest.mark.parametrize(
    "operation", ["users", "list", "create", "detail", "patch", "members", "add", "remove"]
)
def test_every_team_route_requires_identity_management(
    admin_client,
    db_engine,
    seeded_user,
    role,
    operation,
):
    client = admin_client
    team = created(client, "Private team name")
    path = f"/api/v1/teams/{team['id']}"
    assert (
        client.post(
            f"{path}/members", json={"user_id": str(seeded_user)}, headers=preconditions()
        ).status_code
        == 201
    )
    if role == "anonymous":
        client.cookies.clear()
    else:
        sign_in(client, "employee@example.test")
    before = counts(db_engine)
    if operation == "users":
        response = client.get("/api/v1/users")
    elif operation == "list":
        response = client.get("/api/v1/teams")
    elif operation == "create":
        response = create(client)
    elif operation == "detail":
        response = client.get(path)
    elif operation == "patch":
        response = client.patch(path, json={"active": False}, headers=preconditions(2))
    elif operation == "members":
        response = client.get(f"{path}/members")
    elif operation == "add":
        response = client.post(
            f"{path}/members", json={"user_id": str(seeded_user)}, headers=preconditions(2)
        )
    else:
        response = client.delete(f"{path}/members/{seeded_user}", headers=preconditions(2))
    assert response.status_code == (401 if role == "anonymous" else 403)
    assert "Private team name" not in response.text and "employee@example.test" not in response.text
    assert counts(db_engine) == before


@pytest.mark.parametrize(
    "guard", ["origin-missing", "origin-foreign", "csrf-missing", "csrf-wrong"]
)
def test_team_writes_enforce_origin_and_csrf_before_effects(admin_client, db_engine, guard):
    client = admin_client
    if guard == "origin-missing":
        del client.headers["Origin"]
    elif guard == "origin-foreign":
        client.headers["Origin"] = "https://foreign.invalid"
    elif guard == "csrf-missing":
        del client.headers["X-CSRF-Token"]
    else:
        client.headers["X-CSRF-Token"] = "invalid"
    response = create(client)
    assert response.status_code == 403
    assert counts(db_engine) == (0, 0, 0, 0, 0)


def test_matching_create_replay_is_historical_and_conflicting_key_is_rejected(
    admin_client, db_engine
):
    client = admin_client
    key = uuid4().hex
    first = create(client, " Support ", key)
    assert first.status_code == 201
    replay = create(client, "Support", key)
    assert replay.status_code == 200 and replay.json() == first.json()
    path = f"/api/v1/teams/{first.json()['id']}"
    assert client.patch(path, json={"name": "Renamed"}, headers=preconditions()).status_code == 200
    historical = create(client, "Support", key)
    assert historical.json() == first.json()
    assert client.get(path).json()["name"] == "Renamed"
    conflict = create(client, "Different", key)
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    assert counts(db_engine) == (1, 0, 1, 2, 2)
    with Session(db_engine) as db:
        record = db.scalar(select(IdempotencyRecord))
        assert record.expires_at - record.created_at >= timedelta(days=7)
        assert set(record.result) == {"id", "name", "active", "version", "created_at", "updated_at"}


@pytest.mark.parametrize("key", [None, "", "space invalid", "x" * 129])
def test_critical_create_requires_safe_bounded_idempotency_key(admin_client, db_engine, key):
    headers = {} if key is None else {"Idempotency-Key": key}
    response = admin_client.post("/api/v1/teams", json={"name": "Support"}, headers=headers)
    assert response.status_code == (428 if key is None else 422)
    assert counts(db_engine) == (0, 0, 0, 0, 0)


@pytest.mark.parametrize("value", [None, "*", 'W/"1"', '"0"', '"01"', '"1.0"'])
def test_mutations_require_strong_positive_version_precondition(admin_client, db_engine, value):
    team = created(admin_client)
    headers = {} if value is None else {"If-Match": value}
    response = admin_client.patch(
        f"/api/v1/teams/{team['id']}", json={"name": "Changed"}, headers=headers
    )
    assert response.status_code == (428 if value is None else 422)
    assert counts(db_engine) == (1, 0, 1, 1, 1)


def test_stale_patch_and_membership_fail_without_consuming_retry_key(
    admin_client, db_engine, seeded_user
):
    client = admin_client
    team = created(client)
    path = f"/api/v1/teams/{team['id']}"
    assert client.patch(path, json={"name": "New"}, headers=preconditions()).status_code == 200
    assert client.patch(path, json={"active": False}, headers=preconditions()).status_code == 409
    key = uuid4().hex
    failed = client.post(
        f"{path}/members", json={"user_id": str(seeded_user)}, headers=preconditions(1, key)
    )
    assert failed.status_code == 409
    successful = client.post(
        f"{path}/members", json={"user_id": str(seeded_user)}, headers=preconditions(2, key)
    )
    assert successful.status_code == 201
    assert (
        client.delete(f"{path}/members/{seeded_user}", headers=preconditions(2)).status_code == 409
    )
    assert counts(db_engine) == (1, 1, 2, 3, 3)


def test_membership_replay_does_not_restore_later_removed_membership(
    admin_client, db_engine, seeded_user
):
    client = admin_client
    team = created(client)
    path = f"/api/v1/teams/{team['id']}/members"
    key = uuid4().hex
    first = client.post(path, json={"user_id": str(seeded_user)}, headers=preconditions(1, key))
    assert first.status_code == 201
    assert client.delete(f"{path}/{seeded_user}", headers=preconditions(2)).status_code == 204
    replay = client.post(path, json={"user_id": str(seeded_user)}, headers=preconditions(1, key))
    assert replay.status_code == 200 and replay.json() == first.json()
    assert client.get(path).json()["items"] == []
    assert (
        client.post(
            path, json={"user_id": str(seeded_user)}, headers=preconditions(3, key)
        ).status_code
        == 409
    )
    assert counts(db_engine) == (1, 1, 2, 3, 3)


@pytest.mark.parametrize("revoke", ["role", "account"])
def test_replay_requires_fresh_authorization(admin_client, db_engine, revoke):
    client = admin_client
    key = uuid4().hex
    assert create(client, "Protected team", key).status_code == 201
    with Session(db_engine) as db, db.begin():
        management.set_platform_admin(db, "employee@example.test", True)
        if revoke == "role":
            management.set_platform_admin(db, "admin@example.test", False)
        else:
            management.set_account_active(db, "admin@example.test", False)
    before = counts(db_engine)
    denied = create(client, "Protected team", key)
    assert denied.status_code == 401 and "Protected team" not in denied.text
    if revoke == "role":
        sign_in(client, "admin@example.test")
        assert create(client, "Protected team", key).status_code == 403
    assert counts(db_engine) == before


def test_route_and_actor_namespaces_do_not_collide(admin_client, db_engine, seeded_user):
    client = admin_client
    key = uuid4().hex
    first = create(client, "First", key)
    assert first.status_code == 201
    path = f"/api/v1/teams/{first.json()['id']}/members"
    assert (
        client.post(
            path, json={"user_id": str(seeded_user)}, headers=preconditions(1, key)
        ).status_code
        == 201
    )
    with Session(db_engine) as db, db.begin():
        management.set_platform_admin(db, "employee@example.test", True)
    sign_in(client, "employee@example.test")
    other = create(client, "Second", key)
    assert other.status_code == 201 and other.json()["id"] != first.json()["id"]
    assert counts(db_engine)[:3] == (2, 1, 3)


def test_inactive_team_or_user_rejects_new_membership_but_preserves_roster(
    admin_client,
    db_engine,
    seeded_user,
):
    client = admin_client
    team = created(client)
    path = f"/api/v1/teams/{team['id']}"
    assert (
        client.post(
            f"{path}/members", json={"user_id": str(seeded_user)}, headers=preconditions()
        ).status_code
        == 201
    )
    with Session(db_engine) as db, db.begin():
        management.set_account_active(db, "employee@example.test", False)
    roster = client.get(f"{path}/members").json()["items"]
    assert roster[0]["account_active"] is False
    assert (
        client.post(
            f"{path}/members", json={"user_id": str(seeded_user)}, headers=preconditions(2)
        ).status_code
        == 409
    )
    assert client.patch(path, json={"active": False}, headers=preconditions(2)).status_code == 200
    assert (
        client.post(
            f"{path}/members", json={"user_id": str(seeded_user)}, headers=preconditions(3)
        ).status_code
        == 409
    )
    assert len(client.get(f"{path}/members").json()["items"]) == 1
    assert counts(db_engine) == (1, 1, 2, 3, 3)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"active": None},
        {"active": "false"},
        {"role": "platform_admin"},
        {"name": " "},
        {"name": "x" * 151},
    ],
)
def test_patch_rejects_unknown_empty_null_or_invalid_fields(admin_client, db_engine, body):
    team = created(admin_client)
    response = admin_client.patch(f"/api/v1/teams/{team['id']}", json=body, headers=preconditions())
    assert response.status_code == 422
    assert counts(db_engine) == (1, 0, 1, 1, 1)


def test_json_body_bounds_and_media_type_are_enforced(admin_client, db_engine):
    client = admin_client
    headers = {"Idempotency-Key": uuid4().hex, "Content-Type": "application/json"}
    assert (
        client.post(
            "/api/v1/teams", content='{"name":"' + "x" * 17000 + '"}', headers=headers
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/v1/teams",
            content='{"name":"Support"}',
            headers={**headers, "Content-Type": "text/plain"},
        ).status_code
        == 415
    )
    good = client.post(
        "/api/v1/teams",
        content='{"name":"Support"}',
        headers={**headers, "Content-Type": "Application/JSON; charset=utf-8"},
    )
    assert good.status_code == 201
    assert counts(db_engine) == (1, 0, 1, 1, 1)


def test_lists_use_stable_uuid_cursors_bound_to_each_route(admin_client, seeded_user):
    client = admin_client
    teams = [created(client, "First"), created(client, "Second")]
    page = client.get("/api/v1/teams?limit=1").json()
    rest = client.get("/api/v1/teams", params={"limit": 1, "cursor": page["next_cursor"]}).json()
    assert {page["items"][0]["id"], rest["items"][0]["id"]} == {item["id"] for item in teams}
    assert rest["next_cursor"] is None
    user_page = client.get("/api/v1/users?limit=1").json()
    assert user_page["next_cursor"]
    assert (
        client.get("/api/v1/teams", params={"cursor": user_page["next_cursor"]}).status_code == 422
    )
    assert client.get("/api/v1/users", params={"cursor": page["next_cursor"]}).status_code == 422
    assert client.get("/api/v1/teams?limit=101").status_code == 422
    assert client.get("/api/v1/teams?cursor=invalid").status_code == 422
    admin_id = client.get("/api/v1/auth/me").json()["id"]
    path = f"/api/v1/teams/{teams[0]['id']}/members"
    assert (
        client.post(path, json={"user_id": str(seeded_user)}, headers=preconditions()).status_code
        == 201
    )
    assert (
        client.post(path, json={"user_id": admin_id}, headers=preconditions(2)).status_code == 201
    )
    members = client.get(path, params={"limit": 1}).json()
    final = client.get(path, params={"limit": 1, "cursor": members["next_cursor"]}).json()
    assert {members["items"][0]["user_id"], final["items"][0]["user_id"]} == {
        str(seeded_user),
        admin_id,
    }
    other_path = f"/api/v1/teams/{teams[1]['id']}/members"
    assert client.get(other_path, params={"cursor": members["next_cursor"]}).status_code == 422


@pytest.mark.parametrize("different", [False, True])
def test_concurrent_critical_create_has_one_effect(admin_client, db_engine, different):
    barrier = Barrier(2)
    key = uuid4().hex

    def submit(name):
        barrier.wait(timeout=10)
        return create(admin_client, name, key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = (
            pool.submit(submit, "Support"),
            pool.submit(submit, "Other" if different else "Support"),
        )
        responses = [a.result(timeout=20), b.result(timeout=20)]
    assert sorted(response.status_code for response in responses) == (
        [201, 409] if different else [200, 201]
    )
    assert counts(db_engine) == (1, 0, 1, 1, 1)
    if not different:
        assert responses[0].json() == responses[1].json()


def test_concurrent_edits_with_same_version_have_one_winner(admin_client, db_engine):
    team = created(admin_client)
    barrier = Barrier(2)

    def update(name):
        barrier.wait(timeout=10)
        return admin_client.patch(
            f"/api/v1/teams/{team['id']}", json={"name": name}, headers=preconditions()
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(update, "First"), pool.submit(update, "Second")
        responses = [a.result(timeout=20), b.result(timeout=20)]
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert counts(db_engine) == (1, 0, 1, 2, 2)


def test_team_and_retry_outcome_roll_back_if_outbox_fails(admin_client, db_engine):
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE outbox_events ADD CONSTRAINT test_reject_team "
                "CHECK (event_type <> 'identity.team_created')"
            )
        )
    key = uuid4().hex
    try:
        failed = create(admin_client, "Support", key)
        assert failed.status_code == 503 and "SQL" not in failed.text
        assert counts(db_engine) == (0, 0, 0, 0, 0)
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE outbox_events DROP CONSTRAINT test_reject_team"))
    assert create(admin_client, "Support", key).status_code == 201
    assert counts(db_engine) == (1, 0, 1, 1, 1)


def test_missing_team_and_member_account_are_not_fabricated(admin_client, db_engine):
    client = admin_client
    missing = uuid4()
    assert client.get(f"/api/v1/teams/{missing}").status_code == 404
    assert client.get(f"/api/v1/teams/{missing}/members").status_code == 404
    team = created(client)
    path = f"/api/v1/teams/{team['id']}/members"
    assert (
        client.post(path, json={"user_id": str(missing)}, headers=preconditions()).status_code
        == 404
    )
    assert counts(db_engine) == (1, 0, 1, 1, 1)


@pytest.mark.parametrize("collection", ["users", "teams", "members"])
def test_collections_reject_unsupported_filters(admin_client, collection):
    path = f"/api/v1/{collection}"
    if collection == "members":
        team = created(admin_client)
        path = f"/api/v1/teams/{team['id']}/members"
    response = admin_client.get(path, params={"client_id": str(uuid4())})
    assert response.status_code == 422


def test_concurrent_member_retry_precedes_stale_version_check(admin_client, db_engine, seeded_user):
    team = created(admin_client)
    path = f"/api/v1/teams/{team['id']}/members"
    barrier = Barrier(2)
    key = uuid4().hex

    def submit():
        barrier.wait(timeout=10)
        return admin_client.post(
            path, json={"user_id": str(seeded_user)}, headers=preconditions(1, key)
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(submit), pool.submit(submit)
        responses = [a.result(timeout=20), b.result(timeout=20)]
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json() == responses[1].json()
    assert counts(db_engine) == (1, 1, 2, 2, 2)


def test_readiness_fails_when_required_team_schema_is_missing(client, db_engine):
    assert client.get("/api/v1/health/ready").status_code == 200
    with db_engine.begin() as connection:
        connection.execute(text("ALTER TABLE teams RENAME TO test_unmigrated_teams"))
    try:
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 503
        assert "test_unmigrated_teams" not in response.text and "SQL" not in response.text
        assert client.get("/api/v1/health/live").status_code == 200
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE test_unmigrated_teams RENAME TO teams"))
