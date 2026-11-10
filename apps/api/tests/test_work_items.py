from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_project_registry import project
from test_team_api import admin_client, preconditions, sign_in
from test_team_api import created as create_team

__all__ = ["admin_client"]


def setup_project(client, manager):
    team = create_team(client)["id"]
    response = project(client, manager, team)
    assert response.status_code == 201, response.text
    sign_in(client, "employee@example.test")
    return response.json()["project_id"]


def create_work(client, project_id, **fields):
    return client.post(
        "/api/v1/work-items",
        json={
            "project_id": project_id,
            "title": " Task ",
            "priority": "medium",
            "work_type": "one_off",
            **fields,
        },
        headers=preconditions(),
    )


def test_work_lifecycle_and_replay(admin_client, seeded_user, db_engine):
    client = admin_client
    project_id = setup_project(client, seeded_user)
    body = {
        "project_id": project_id,
        "title": " First task ",
        "priority": "high",
        "work_type": "one_off",
        "owner_id": str(seeded_user),
    }
    headers = preconditions()
    response = client.post("/api/v1/work-items", json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"work_item_id", "project_id"}
    assert client.post("/api/v1/work-items", json=body, headers=headers).json() == response.json()
    path = "/api/v1/work-items/" + response.json()["work_item_id"]
    row = client.get(path)
    assert row.headers["etag"] == '"1"'
    assert row.json()["title"] == "First task" and row.json()["status"] == "todo"
    assert row.json()["owner_name"] == "Test Employee"
    assert row.json()["due"] is None and row.json()["completed_at"] is None
    patched = client.patch(
        path, json={"description": "Plain <script>text</script>"}, headers=preconditions()
    )
    assert patched.status_code == 200 and patched.json()["version"] == 2
    assert client.patch(path, json={"title": "stale"}, headers=preconditions()).status_code == 409
    for version, status, reason in [
        (2, "in_progress", None),
        (3, "blocked", "Waiting"),
        (4, "in_progress", None),
        (5, "done", None),
        (6, "in_progress", "Reopen"),
    ]:
        transition = {"target_status": status, "reason": reason}
        key = preconditions(version)
        result = client.post(path + "/transitions", json=transition, headers=key)
        assert result.status_code == 200, result.text
        assert result.json()["version"] == version + 1
        assert (result.json()["completed_at"] is not None) == (status == "done")
        assert (result.json()["blocked_reason"] is not None) == (status == "blocked")
        replay = client.post(path + "/transitions", json=transition, headers=key)
        assert replay.status_code == 200 and replay.json() == result.json()
    comment_headers = preconditions(7)
    comment = client.post(
        path + "/comments", json={"body": "Internal evidence"}, headers=comment_headers
    )
    assert comment.status_code == 201, comment.text
    assert (
        client.post(
            path + "/comments", json={"body": "Internal evidence"}, headers=comment_headers
        ).status_code
        == 200
    )
    assert len(client.get(path + "/comments").json()["items"]) == 1
    assert client.get(path).json()["version"] == 8
    states = client.get(path + "/status-history").json()["items"]
    assert len(states) == 6 and states[0]["to_status"] == "in_progress"
    assert any(state["reason"] == "Waiting" for state in states)
    from altvia.activity import consume_event
    from altvia.models import OutboxEvent

    with Session(db_engine) as db:
        events = list(
            db.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_type == "work_item"))
        )
        identifiers = [event.event_id for event in events]
        assert all(
            "First task" not in str(event.payload) and "Waiting" not in str(event.payload)
            for event in events
        )
    for identifier in identifiers:
        assert consume_event(db_engine, identifier, datetime.now(UTC))
        assert not consume_event(db_engine, identifier, datetime.now(UTC))
    assert len(client.get(path + "/activity").json()["items"]) == 8
    assert client.get(f"/api/v1/projects/{project_id}/activity").json()["items"] == []


def test_subtask_and_assignment_boundaries(admin_client, seeded_user, db_engine):
    client = admin_client
    project_id = setup_project(client, seeded_user)
    parent = create_work(client, project_id)
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["work_item_id"]
    child = create_work(client, project_id, parent_id=parent_id, assignee_ids=[str(seeded_user)])
    assert child.status_code == 201, child.text
    assert client.get("/api/v1/work-items/" + child.json()["work_item_id"]).json()["assignees"] == [
        {"id": str(seeded_user), "display_name": "Test Employee"}
    ]
    child_id = child.json()["work_item_id"]
    path = "/api/v1/work-items/"
    assert (
        client.patch(
            path + parent_id, json={"parent_id": child_id}, headers=preconditions()
        ).status_code
        == 409
    )
    assert (
        client.patch(
            path + child_id, json={"parent_id": child_id}, headers=preconditions()
        ).status_code
        == 409
    )
    assert create_work(client, project_id, parent_id=str(uuid4())).status_code == 422
    assert create_work(client, project_id, owner_id=str(uuid4())).status_code == 422
    assert create_work(client, project_id, assignee_ids=[str(seeded_user)] * 2).status_code == 422
    candidates = client.get(f"/api/v1/projects/{project_id}/work-candidates").json()["items"]
    assert candidates == [{"id": str(seeded_user), "display_name": "Test Employee"}]
    listing = client.get("/api/v1/work-items", params={"project_id": project_id, "limit": 1}).json()
    assert len(listing["items"]) == 1 and listing["next_cursor"] and listing["can_create"]
    assert client.get("/api/v1/work-items").status_code == 422
    sign_in(client, "admin@example.test")
    assert client.get(path + child_id).status_code == 404
    assert client.get(path + child_id + "/comments").status_code == 404
    assert client.get("/api/v1/work-items", params={"project_id": project_id}).status_code == 404


@pytest.mark.parametrize("role", ["agent", "viewer"])
def test_agent_and_viewer_authority(admin_client, seeded_user, db_engine, role):
    from altvia.project_registry import set_project_access

    project_id = setup_project(admin_client, seeded_user)
    created = create_work(admin_client, project_id, owner_id=str(seeded_user))
    assert created.status_code == 201, created.text
    path = "/api/v1/work-items/" + created.json()["work_item_id"]
    with Session(db_engine) as db, db.begin():
        set_project_access(db, "employee@example.test", UUID(project_id), role)
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(path).status_code == 200
    assert admin_client.patch(
        path, json={"title": "Edited"}, headers=preconditions()
    ).status_code == (200 if role == "agent" else 403)
    assert (
        admin_client.patch(
            path, json={"owner_id": str(seeded_user)}, headers=preconditions(2)
        ).status_code
        == 403
    )
    response = create_work(admin_client, project_id, owner_id=str(seeded_user))
    assert response.status_code == (201 if role == "agent" else 403)


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "done"},
        {"title": " "},
        {"priority": "urgent"},
        {"work_type": "recurring"},
        {"estimated_minutes": -1},
        {"due": {"precision": "instant", "instant": 0}},
        {"due": {"precision": "date", "date": 0, "timezone": "UTC"}},
        {"due": {"precision": "instant", "instant": "2026-11-09T12:00:00"}},
        {"due": {"precision": "date", "date": "2026-11-09", "timezone": "Invalid/Zone"}},
        {"due": {"precision": "date", "date": "2011-12-30", "timezone": "Pacific/Apia"}},
    ],
)
def test_work_strict_create_fields(admin_client, seeded_user, fields):
    project_id = setup_project(admin_client, seeded_user)
    assert create_work(admin_client, project_id, **fields).status_code == 422


def test_date_precision_and_ongoing_end(admin_client, seeded_user):
    project_id = setup_project(admin_client, seeded_user)
    response = create_work(
        admin_client,
        project_id,
        work_type="ongoing",
        due={"precision": "date", "date": "2026-11-09", "timezone": "America/Sao_Paulo"},
    )
    assert response.status_code == 201, response.text
    path = "/api/v1/work-items/" + response.json()["work_item_id"]
    row = admin_client.get(path).json()
    assert row["status"] == "in_progress" and row["due_at"] == "2026-11-10T03:00:00Z"
    assert (
        admin_client.post(
            path + "/transitions", json={"target_status": "done"}, headers=preconditions()
        ).status_code
        == 409
    )
    ended = admin_client.post(
        path + "/transitions",
        json={"target_status": "done", "end_operation": True, "reason": "Operation ended"},
        headers=preconditions(),
    )
    assert ended.status_code == 200 and ended.json()["completed_at"]
    assert (
        admin_client.patch(path, json={"due": None}, headers=preconditions(2)).json()["due_at"]
        is None
    )


def test_saved_creation_receipt_survives_archived_reference(admin_client, seeded_user):
    project_id = setup_project(admin_client, seeded_user)
    headers = preconditions()
    body = {
        "project_id": project_id,
        "title": "Committed",
        "priority": "low",
        "work_type": "one_off",
    }
    first = admin_client.post("/api/v1/work-items", json=body, headers=headers)
    assert first.status_code == 201
    assert (
        admin_client.patch(
            f"/api/v1/projects/{project_id}", json={"active": False}, headers=preconditions()
        ).status_code
        == 200
    )
    replay = admin_client.post("/api/v1/work-items", json=body, headers=headers)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert (
        admin_client.get("/api/v1/work-items/" + first.json()["work_item_id"])
        .json()
        .get("project_writable")
        is False
    )
    assert create_work(admin_client, project_id).status_code == 409


@pytest.mark.parametrize("missing", ["membership", "binding", "both"])
def test_task_scope_needs_both_halves_despite_assignment(
    admin_client, seeded_user, db_engine, missing
):
    from altvia.models import ProjectMember, RoleBinding

    project_id = setup_project(admin_client, seeded_user)
    response = create_work(admin_client, project_id, owner_id=str(seeded_user))
    assert response.status_code == 201
    identifier = response.json()["work_item_id"]
    with Session(db_engine) as db, db.begin():
        if missing in {"membership", "both"}:
            db.delete(db.get(ProjectMember, (UUID(project_id), seeded_user)))
        if missing in {"binding", "both"}:
            db.delete(
                db.scalar(select(RoleBinding).where(RoleBinding.project_id == UUID(project_id)))
            )
    for suffix in ["", "/comments", "/activity"]:
        assert admin_client.get(f"/api/v1/work-items/{identifier}{suffix}").status_code == 404
    assert create_work(admin_client, project_id).status_code == 404


@pytest.mark.parametrize(
    "day,zone,expected",
    [
        ("2025-11-01", "America/Havana", "2025-11-02T04:00:00Z"),
        ("2026-10-31", "America/Havana", "2026-11-01T04:00:00Z"),
        ("2026-03-07", "America/Havana", "2026-03-08T05:00:00Z"),
        ("2026-11-10", "America/Sao_Paulo", "2026-11-11T03:00:00Z"),
        ("2011-12-29", "Pacific/Apia", "2011-12-30T10:00:00Z"),
        ("2018-11-03", "America/Sao_Paulo", "2018-11-04T03:00:00Z"),
    ],
)
def test_ambiguous_next_midnight_uses_first_boundary(
    admin_client, seeded_user, db_engine, day, zone, expected
):
    project_id = setup_project(admin_client, seeded_user)
    response = create_work(
        admin_client, project_id, due={"precision": "date", "date": day, "timezone": zone}
    )
    assert response.status_code == 201
    row = admin_client.get("/api/v1/work-items/" + response.json()["work_item_id"]).json()
    assert row["due_at"] == expected
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    # Raw writers must use the same exact boundary as the typed API.
    with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
        connection.execute(text("UPDATE work_items SET due_at=due_at+interval '1 microsecond'"))
    assert caught.value.orig.sqlstate == "23514"


def test_cross_customer_task_ceiling_is_fresh(admin_client, seeded_user, db_engine):
    from altvia.models import ClientAccessGrant
    from test_client_registry import created as create_client

    customer = create_client(admin_client, seeded_user)
    team = create_team(admin_client)["id"]
    project_id = project(admin_client, seeded_user, team, customer).json()["project_id"]
    sign_in(admin_client, "employee@example.test")
    response = create_work(admin_client, project_id, owner_id=str(seeded_user))
    assert response.status_code == 201
    path = "/api/v1/work-items/" + response.json()["work_item_id"]
    with Session(db_engine) as db, db.begin():
        db.delete(db.get(ClientAccessGrant, (seeded_user, UUID(customer))))
    assert admin_client.get(path).status_code == 404
    assert (
        admin_client.patch(path, json={"title": "denied"}, headers=preconditions()).status_code
        == 404
    )
