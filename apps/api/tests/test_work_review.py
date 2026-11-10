from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID

from altvia import management
from altvia.models import OutboxEvent, User, WorkStatusHistory
from altvia.project_registry import set_project_access
from conftest import TEST_PASSWORD
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in
from test_work_items import create_work, setup_project

__all__ = ["admin_client"]


def contributors(db_engine, project_id, names):
    result = []
    with Session(db_engine) as db, db.begin():
        for name in names:
            email = name + "@example.test"
            management.create_user(db, email, name, TEST_PASSWORD)
            set_project_access(db, email, UUID(project_id), "agent")
            result.append(db.scalar(select(User.id).where(User.email_normalized == email)))
    return result


def test_retained_stale_assignments_do_not_block_independent_maintenance(
    admin_client, seeded_user, db_engine
):
    project_id = setup_project(admin_client, seeded_user)
    owner, participant, active = contributors(
        db_engine, project_id, ["old-owner", "old-participant", "active-participant"]
    )
    created = create_work(
        admin_client, project_id, owner_id=str(owner), assignee_ids=[str(participant)]
    )
    assert created.status_code == 201
    path = "/api/v1/work-items/" + created.json()["work_item_id"]
    with Session(db_engine) as db, db.begin():
        set_project_access(db, "old-owner@example.test", UUID(project_id), None)
        management.set_account_active(db, "old-participant@example.test", False)
    response = admin_client.patch(
        path, json={"assignee_ids": [str(participant), str(active)]}, headers=preconditions()
    )
    assert response.status_code == 200, response.text
    assert response.json()["owner_id"] == str(owner)
    assert (
        admin_client.patch(
            path, json={"assignee_ids": [str(participant)]}, headers=preconditions(2)
        ).status_code
        == 200
    )
    assert (
        admin_client.patch(path, json={"owner_id": None}, headers=preconditions(3)).status_code
        == 200
    )
    assert (
        admin_client.patch(
            path, json={"owner_id": str(owner)}, headers=preconditions(4)
        ).status_code
        == 422
    )
    sign_in(admin_client, "old-owner@example.test")
    assert admin_client.get(path).status_code == 404
    assert (
        admin_client.patch(path, json={"title": "denied"}, headers=preconditions(4)).status_code
        == 404
    )


def test_replay_after_candidate_revoke_and_later_versions_has_no_new_effect(
    admin_client, seeded_user, db_engine
):
    project_id = setup_project(admin_client, seeded_user)
    candidate = contributors(db_engine, project_id, ["receipt-owner"])[0]
    body = {
        "project_id": project_id,
        "title": "Receipt",
        "priority": "medium",
        "work_type": "one_off",
        "owner_id": str(candidate),
    }
    create_key = preconditions()
    receipt = admin_client.post("/api/v1/work-items", json=body, headers=create_key)
    assert receipt.status_code == 201
    path = "/api/v1/work-items/" + receipt.json()["work_item_id"]
    transition_key = preconditions()
    transition = admin_client.post(
        path + "/transitions", json={"target_status": "in_progress"}, headers=transition_key
    )
    assert transition.status_code == 200
    comment_key = preconditions(2)
    comment = admin_client.post(path + "/comments", json={"body": "Once"}, headers=comment_key)
    assert comment.status_code == 201
    assert (
        admin_client.patch(path, json={"title": "Later"}, headers=preconditions(3)).status_code
        == 200
    )
    with Session(db_engine) as db, db.begin():
        set_project_access(db, "receipt-owner@example.test", UUID(project_id), None)
    assert (
        admin_client.post("/api/v1/work-items", json=body, headers=create_key).json()
        == receipt.json()
    )
    assert (
        admin_client.post(
            path + "/transitions", json={"target_status": "in_progress"}, headers=transition_key
        ).json()["version"]
        == 2
    )
    assert (
        admin_client.post(path + "/comments", json={"body": "Once"}, headers=comment_key).json()
        == comment.json()
    )
    assert admin_client.get(path).json()["version"] == 4
    assert len(admin_client.get(path + "/comments").json()["items"]) == 1
    assert len(admin_client.get(path + "/status-history").json()["items"]) == 2
    with Session(db_engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.aggregate_id == UUID(receipt.json()["work_item_id"]))
            )
            == 4
        )


def test_assignment_revoke_denies_saved_transition_before_receipt(
    admin_client, seeded_user, db_engine
):
    project_id = setup_project(admin_client, seeded_user)
    agent = contributors(db_engine, project_id, ["former-assignee"])[0]
    created = create_work(admin_client, project_id, assignee_ids=[str(agent)])
    path = "/api/v1/work-items/" + created.json()["work_item_id"]
    sign_in(admin_client, "former-assignee@example.test")
    key = preconditions()
    assert (
        admin_client.post(
            path + "/transitions", json={"target_status": "in_progress"}, headers=key
        ).status_code
        == 200
    )
    sign_in(admin_client, "employee@example.test")
    assert (
        admin_client.patch(path, json={"assignee_ids": []}, headers=preconditions(2)).status_code
        == 200
    )
    sign_in(admin_client, "former-assignee@example.test")
    assert (
        admin_client.post(
            path + "/transitions", json={"target_status": "in_progress"}, headers=key
        ).status_code
        == 403
    )


def test_same_state_noop_and_concurrent_version_winner(admin_client, seeded_user, db_engine):
    project_id = setup_project(admin_client, seeded_user)
    created = create_work(admin_client, project_id)
    identifier = UUID(created.json()["work_item_id"])
    path = "/api/v1/work-items/" + str(identifier)
    assert (
        admin_client.post(
            path + "/transitions", json={"target_status": "todo"}, headers=preconditions()
        ).json()["version"]
        == 1
    )
    with Session(db_engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(WorkStatusHistory)
                .where(WorkStatusHistory.work_item_id == identifier)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.aggregate_id == identifier)
            )
            == 1
        )
    start = Barrier(2)

    def write(title):
        start.wait(timeout=5)
        return admin_client.patch(path, json={"title": title}, headers=preconditions()).status_code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, ["First", "Second"]))
    assert sorted(results) == [200, 409]
    assert admin_client.get(path).json()["version"] == 2


def test_role_and_ceiling_revoke_deny_saved_receipts(admin_client, seeded_user, db_engine):
    from altvia.models import ClientAccessGrant
    from test_client_registry import created as create_client
    from test_project_registry import project
    from test_team_api import created as create_team

    customer = create_client(admin_client, seeded_user)
    team = create_team(admin_client)["id"]
    project_id = project(admin_client, seeded_user, team, customer).json()["project_id"]
    sign_in(admin_client, "employee@example.test")
    body = {
        "project_id": project_id,
        "title": "Scoped receipt",
        "priority": "low",
        "work_type": "one_off",
    }
    key = preconditions()
    assert admin_client.post("/api/v1/work-items", json=body, headers=key).status_code == 201
    with Session(db_engine) as db, db.begin():
        db.delete(db.get(ClientAccessGrant, (seeded_user, UUID(customer))))
    assert admin_client.post("/api/v1/work-items", json=body, headers=key).status_code == 404
    with Session(db_engine) as db, db.begin():
        db.add(
            ClientAccessGrant(
                user_id=seeded_user, client_id=UUID(customer), created_at=datetime.now(UTC)
            )
        )
        set_project_access(db, "employee@example.test", UUID(project_id), "viewer")
        from altvia.models import RoleBinding

        for binding in db.scalars(
            select(RoleBinding).where(
                RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "client"
            )
        ):
            db.delete(binding)
    assert admin_client.post("/api/v1/work-items", json=body, headers=key).status_code == 401
    sign_in(admin_client, "employee@example.test")
    assert admin_client.post("/api/v1/work-items", json=body, headers=key).status_code == 403
