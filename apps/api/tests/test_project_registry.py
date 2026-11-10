from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_client_registry import created as create_client
from test_team_api import admin_client, preconditions, sign_in
from test_team_api import created as create_team

__all__ = ["admin_client"]


def area(client, name=" Operations "):
    response = client.post(
        "/api/v1/operational-areas", json={"name": name}, headers=preconditions()
    )
    assert response.status_code == 201, response.text
    return response.json()


def project(client, manager, team, customer=None, classification=None, key=None):
    return client.post(
        "/api/v1/projects",
        json={
            "name": " Project ",
            "scope_kind": "client" if customer else "internal",
            "client_id": customer,
            "team_id": team,
            "operational_area_id": classification,
            "manager_user_id": str(manager),
        },
        headers=preconditions(key=key),
    )


def test_area_lifecycle_unique_names_permissions_and_replay(admin_client):
    assert admin_client.get("/api/v1/projects").json()["can_create"]
    row = area(admin_client)
    assert row["name"] == "Operations" and row["version"] == 1
    assert area(admin_client, "Another")["id"] != row["id"]
    assert (
        admin_client.post(
            "/api/v1/operational-areas", json={"name": "Operations"}, headers=preconditions()
        ).status_code
        == 409
    )
    path = "/api/v1/operational-areas/" + row["id"]
    for version, body in [(1, {"name": "Revised"}), (2, {"active": False}), (3, {"active": True})]:
        response = admin_client.patch(path, json=body, headers=preconditions(version))
        assert response.status_code == 200 and response.json()["version"] == version + 1
    assert (
        admin_client.patch(path, json={"name": "Stale"}, headers=preconditions()).status_code == 409
    )
    sign_in(admin_client, "employee@example.test")
    assert len(admin_client.get("/api/v1/operational-areas").json()["items"]) == 2
    assert (
        admin_client.patch(path, json={"name": "Denied"}, headers=preconditions(4)).status_code
        == 403
    )
    assert admin_client.get("/api/v1/operational-areas?extra=1").status_code == 422


def test_internal_project_explicit_manager_no_admin_or_team_bypass(
    admin_client, seeded_user, db_engine
):
    team = create_team(admin_client)["id"]
    classification = area(admin_client)["id"]
    receipt = project(admin_client, seeded_user, team, classification=classification)
    assert receipt.status_code == 201, receipt.text
    assert set(receipt.json()) == {"project_id", "manager_user_id"}
    path = "/api/v1/projects/" + receipt.json()["project_id"]
    assert admin_client.get(path).status_code == 404
    assert admin_client.get("/api/v1/projects").json()["items"] == []
    sign_in(admin_client, "employee@example.test")
    row = admin_client.get(path)
    assert row.status_code == 200 and row.json()["name"] == "Project"
    assert row.json()["operational_area_name"] == "Operations"
    assert row.json()["client_id"] is None and row.json()["can_manage"]
    assert row.headers["etag"] == '"1"'
    response = admin_client.patch(
        path, json={"name": "Updated", "operational_area_id": None}, headers=preconditions()
    )
    assert response.status_code == 200 and response.json()["operational_area_id"] is None
    assert response.json()["version"] == 2
    for version, active in [(2, False), (3, True)]:
        assert (
            admin_client.patch(
                path, json={"active": active}, headers=preconditions(version)
            ).status_code
            == 200
        )
    members = admin_client.get(path + "/members").json()["items"]
    assert len(members) == 1 and members[0]["id"] == str(seeded_user)
    assert set(members[0]) == {"id", "display_name", "active", "role_name"}
    assert members[0]["role_name"] == "project_manager"
    from altvia.models import ProjectMember

    with Session(db_engine) as db, db.begin():
        db.delete(db.get(ProjectMember, (UUID(receipt.json()["project_id"]), seeded_user)))
    assert admin_client.get(path).status_code == 404


def test_client_project_ceiling_inheritance_and_revoke_are_fresh(
    admin_client, seeded_user, db_engine
):
    from altvia.client_registry import set_client_access

    customer = create_client(admin_client, seeded_user)
    team = create_team(admin_client)["id"]
    receipt = project(admin_client, seeded_user, team, customer)
    assert receipt.status_code == 201, receipt.text
    path = "/api/v1/projects/" + receipt.json()["project_id"]
    assert admin_client.get(path).status_code == 404
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(path).status_code == 200
    with Session(db_engine) as db, db.begin():
        set_client_access(db, "employee@example.test", UUID(customer), None)
    assert admin_client.get(path).status_code == 401
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(path).status_code == 404
    assert admin_client.get(path + "/members").status_code == 404
    assert admin_client.get(path + "/activity").status_code == 404
    assert (
        admin_client.get("/api/v1/projects", params={"client_id": customer}).json()["items"] == []
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"active": None},
        {"team_id": str(uuid4())},
        {"scope_kind": "client"},
        {"client_id": str(uuid4())},
    ],
)
def test_project_patch_strict_scope_and_null_fields(admin_client, seeded_user, body):
    team = create_team(admin_client)["id"]
    receipt = project(admin_client, seeded_user, team)
    assert receipt.status_code == 201, receipt.text
    sign_in(admin_client, "employee@example.test")
    assert (
        admin_client.patch(
            "/api/v1/projects/" + receipt.json()["project_id"], json=body, headers=preconditions()
        ).status_code
        == 422
    )


def test_project_create_replay_does_not_restore_access_and_scope_is_fresh(
    admin_client, seeded_user, db_engine
):
    team = create_team(admin_client)["id"]
    key = uuid4().hex
    receipt = project(admin_client, seeded_user, team, key=key)
    assert receipt.status_code == 201, receipt.text
    from altvia.project_registry import set_project_access

    with Session(db_engine) as db, db.begin():
        set_project_access(db, "employee@example.test", UUID(receipt.json()["project_id"]), None)
    replay = project(admin_client, seeded_user, team, key=key)
    assert replay.status_code == 200 and replay.json() == receipt.json()
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get("/api/v1/projects/" + receipt.json()["project_id"]).status_code == 404


def test_project_events_project_once_and_never_enter_global_identity_history(
    admin_client, seeded_user, db_engine
):
    from altvia.activity import claim_events, consume_event
    from altvia.models import ActivityEvent

    team = create_team(admin_client)["id"]
    area(admin_client)
    receipt = project(admin_client, seeded_user, team)
    assert receipt.status_code == 201, receipt.text
    for event_id, _ in claim_events(db_engine, datetime.now(UTC)):
        consume_event(db_engine, event_id, datetime.now(UTC))
    assert all(
        row["resource_type"] in {"identity", "team"}
        for row in admin_client.get("/api/v1/identity-activity").json()["items"]
    )
    sign_in(admin_client, "employee@example.test")
    rows = admin_client.get(
        "/api/v1/projects/" + receipt.json()["project_id"] + "/activity"
    ).json()["items"]
    assert len(rows) == 1 and rows[0]["event_type"] == "project.created"
    with Session(db_engine) as db:
        assert (
            db.scalar(
                select(ActivityEvent).where(ActivityEvent.resource_type == "operational_area")
            )
            is not None
        )


def test_scoped_client_manager_creates_only_with_team_read_and_explicit_self(
    admin_client, seeded_user, db_engine
):
    from altvia.management import set_team_role

    team = create_team(admin_client)["id"]
    customer = create_client(admin_client, seeded_user)
    sign_in(admin_client, "employee@example.test")
    assert not admin_client.get("/api/v1/projects").json()["can_create"]
    assert project(admin_client, seeded_user, team, customer).status_code == 404
    with Session(db_engine) as db, db.begin():
        set_team_role(db, "employee@example.test", UUID(team), "viewer", True)
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get("/api/v1/projects").json()["can_create"]
    receipt = project(admin_client, seeded_user, team, customer)
    assert receipt.status_code == 201, receipt.text
    assert admin_client.get("/api/v1/auth/me").status_code == 401
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get("/api/v1/projects/" + receipt.json()["project_id"]).json()["can_manage"]
    assert project(admin_client, seeded_user, team).status_code == 403
    assert project(admin_client, uuid4(), team, customer).status_code == 403


def test_customer_manager_must_already_have_ceiling_and_refs_must_be_active(
    admin_client, seeded_user
):
    team = create_team(admin_client)["id"]
    me = admin_client.get("/api/v1/auth/me").json()["id"]
    customer = create_client(admin_client, seeded_user)
    assert project(admin_client, me, team, customer).status_code == 422
    classification = area(admin_client)["id"]
    assert (
        admin_client.patch(
            "/api/v1/operational-areas/" + classification,
            json={"active": False},
            headers=preconditions(),
        ).status_code
        == 200
    )
    assert (
        project(admin_client, seeded_user, team, classification=classification).status_code == 422
    )
    assert project(admin_client, seeded_user, str(uuid4())).status_code == 422
    assert project(admin_client, seeded_user, team, str(uuid4())).status_code == 422
    assert admin_client.get("/api/v1/projects").json()["items"] == []


def test_area_replay_no_op_csrf_and_strict_values(admin_client):
    headers = preconditions()
    response = admin_client.post("/api/v1/operational-areas", json={"name": "One"}, headers=headers)
    assert response.status_code == 201
    replay = admin_client.post("/api/v1/operational-areas", json={"name": "One"}, headers=headers)
    assert replay.status_code == 200 and replay.json() == response.json()
    path = "/api/v1/operational-areas/" + response.json()["id"]
    assert (
        admin_client.patch(path, json={"name": "One"}, headers=preconditions()).json()["version"]
        == 1
    )
    for body in [{}, {"name": " "}, {"name": None}, {"active": 1}, {"extra": True}]:
        assert admin_client.patch(path, json=body, headers=preconditions()).status_code == 422
    assert (
        admin_client.patch(
            path, json={"name": "Denied"}, headers={"If-Match": '"1"', "X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert admin_client.patch(path, json={"name": "Missing"}).status_code == 428


def test_project_access_changes_are_atomic_noops_and_still_require_customer_ceiling(
    admin_client, seeded_user, db_engine
):
    from altvia.identity import IdentityError
    from altvia.models import ClientAccessGrant, Project, ProjectMember, RoleBinding
    from altvia.project_registry import set_project_access

    customer = create_client(admin_client, seeded_user)
    team = create_team(admin_client)["id"]
    receipt = project(admin_client, seeded_user, team, customer)
    assert receipt.status_code == 201
    identifier = UUID(receipt.json()["project_id"])
    with Session(db_engine) as db, db.begin():
        assert not set_project_access(db, "employee@example.test", identifier, "project_manager")
        db.get(Project, identifier).active = False
    with Session(db_engine) as db, db.begin():
        assert not set_project_access(db, "employee@example.test", identifier, "project_manager")
        assert set_project_access(db, "employee@example.test", identifier, None)
    with Session(db_engine) as db, db.begin():
        assert db.get(ProjectMember, (identifier, seeded_user)) is None
        assert db.scalar(select(RoleBinding).where(RoleBinding.project_id == identifier)) is None
        assert db.get(ClientAccessGrant, (seeded_user, UUID(customer))) is not None
    with (
        Session(db_engine) as db,
        db.begin(),
        pytest.raises(IdentityError, match="project_inactive"),
    ):
        set_project_access(db, "employee@example.test", identifier, "viewer")


def test_project_collection_and_child_cursors_are_bound_and_authorized(admin_client, seeded_user):
    team = create_team(admin_client)["id"]
    first = project(admin_client, seeded_user, team).json()["project_id"]
    second = project(admin_client, seeded_user, team).json()["project_id"]
    sign_in(admin_client, "employee@example.test")
    page = admin_client.get("/api/v1/projects?limit=1").json()
    assert page["next_cursor"]
    tail = admin_client.get("/api/v1/projects", params={"cursor": page["next_cursor"]}).json()
    assert {row["id"] for row in page["items"] + tail["items"]} == {first, second}
    assert (
        admin_client.get(
            "/api/v1/projects", params={"client_id": str(uuid4()), "cursor": page["next_cursor"]}
        ).status_code
        == 422
    )
    assert admin_client.get("/api/v1/projects?extra=1").status_code == 422
    assert admin_client.get("/api/v1/projects/" + str(uuid4()) + "/members").status_code == 404


def test_concurrent_project_creation_reuses_one_receipt_and_one_grant(
    admin_client, seeded_user, db_engine
):
    from altvia.models import Project, ProjectMember, User
    from sqlalchemy import func

    team = create_team(admin_client)["id"]
    key = uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as executor:
        replies = list(
            executor.map(lambda _: project(admin_client, seeded_user, team, key=key), range(2))
        )
    assert sorted(reply.status_code for reply in replies) == [200, 201]
    assert replies[0].json() == replies[1].json()
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 1
        assert db.scalar(select(func.count()).select_from(ProjectMember)) == 1
        assert db.get(User, seeded_user).auth_version == 2


@pytest.mark.parametrize("role", ["viewer", "operations_manager"])
def test_inherited_client_role_reads_without_project_records_but_never_writes_as_viewer(
    admin_client, seeded_user, db_engine, role
):
    from altvia.client_registry import set_client_access
    from altvia.project_registry import set_project_access

    customer = create_client(admin_client, seeded_user)
    team = create_team(admin_client)["id"]
    receipt = project(admin_client, seeded_user, team, customer)
    assert receipt.status_code == 201
    identifier = receipt.json()["project_id"]
    with Session(db_engine) as db, db.begin():
        set_project_access(db, "employee@example.test", UUID(identifier), None)
        set_client_access(db, "employee@example.test", UUID(customer), role)
    sign_in(admin_client, "employee@example.test")
    path = "/api/v1/projects/" + identifier
    assert admin_client.get(path).json()["can_manage"] is (role == "operations_manager")
    assert admin_client.get(path + "/members").json()["items"] == []
    assert [row["id"] for row in admin_client.get("/api/v1/projects").json()["items"]] == [
        identifier
    ]
    changed = admin_client.patch(
        path, json={"name": "Inherited authority"}, headers=preconditions(2)
    )
    assert changed.status_code == (200 if role == "operations_manager" else 403)


def test_project_membership_alone_never_grants_internal_scope(admin_client, seeded_user, db_engine):
    from altvia.models import RoleBinding

    team = create_team(admin_client)["id"]
    receipt = project(admin_client, seeded_user, team)
    identifier = UUID(receipt.json()["project_id"])
    with Session(db_engine) as db, db.begin():
        db.delete(db.scalar(select(RoleBinding).where(RoleBinding.project_id == identifier)))
    sign_in(admin_client, "employee@example.test")
    for suffix in ["", "/members", "/activity"]:
        assert admin_client.get(f"/api/v1/projects/{identifier}{suffix}").status_code == 404
    assert admin_client.get("/api/v1/projects").json()["items"] == []


@pytest.mark.parametrize("role", ["viewer", "agent", "project_manager"])
def test_direct_project_roles_execute_scoped_sql_with_both_halves(
    admin_client, seeded_user, db_engine, role
):
    from altvia.project_registry import set_project_access

    team = create_team(admin_client)["id"]
    receipt = project(admin_client, seeded_user, team)
    identifier = receipt.json()["project_id"]
    with Session(db_engine) as db, db.begin():
        set_project_access(db, "employee@example.test", UUID(identifier), role)
    sign_in(admin_client, "employee@example.test")
    path = "/api/v1/projects/" + identifier
    row = admin_client.get(path)
    assert row.status_code == 200
    assert row.json()["can_manage"] is (role == "project_manager")
    changed = admin_client.patch(
        path, json={"name": "Direct authority"}, headers=preconditions(row.json()["version"])
    )
    assert changed.status_code == (200 if role == "project_manager" else 403)


def test_team_metadata_role_never_grants_internal_project_content(
    admin_client, seeded_user, db_engine
):
    from altvia.management import set_team_role
    from altvia.project_registry import set_project_access

    team = create_team(admin_client)["id"]
    receipt = project(admin_client, seeded_user, team)
    identifier = receipt.json()["project_id"]
    with Session(db_engine) as db, db.begin():
        set_project_access(db, "employee@example.test", UUID(identifier), None)
        set_team_role(db, "employee@example.test", UUID(team), "operations_manager", True)
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get("/api/v1/teams/" + team).status_code == 200
    for suffix in ["", "/members", "/activity"]:
        assert admin_client.get(f"/api/v1/projects/{identifier}{suffix}").status_code == 404
    assert admin_client.get("/api/v1/projects").json()["items"] == []


def test_scoped_project_creation_replay_rechecks_revoked_creation_authority(
    admin_client, seeded_user, db_engine
):
    from altvia.client_registry import set_client_access
    from altvia.management import set_team_role

    team = create_team(admin_client)["id"]
    customer = create_client(admin_client, seeded_user)
    with Session(db_engine) as db, db.begin():
        set_team_role(db, "employee@example.test", UUID(team), "viewer", True)
    sign_in(admin_client, "employee@example.test")
    key = uuid4().hex
    receipt = project(admin_client, seeded_user, team, customer, key=key)
    assert receipt.status_code == 201
    with Session(db_engine) as db, db.begin():
        set_client_access(db, "employee@example.test", UUID(customer), "viewer")
    sign_in(admin_client, "employee@example.test")
    assert project(admin_client, seeded_user, team, customer, key=key).status_code == 403
