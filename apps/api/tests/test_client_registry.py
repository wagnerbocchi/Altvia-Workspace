from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from altvia.models import AuditLog, OutboxEvent, RoleBinding
from conftest import TEST_PASSWORD
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in

__all__ = ["admin_client"]


def create(client, manager, name=" Client One ", key=None):
    return client.post(
        "/api/v1/clients",
        json={"name": name, "manager_user_id": str(manager)},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def created(client, manager, name="Client One"):
    result = create(client, manager, name)
    assert result.status_code == 201, result.text
    assert set(result.json()) == {"client_id", "manager_user_id"}
    return result.json()["client_id"]


def test_client_is_real_scoped_persisted_and_never_an_admin_bypass(admin_client, seeded_user):
    client = admin_client
    receipt = create(client, seeded_user)
    assert receipt.status_code == 201
    path = "/api/v1/clients/" + receipt.json()["client_id"]
    assert client.get("/api/v1/clients").json() == {"items": [], "next_cursor": None}
    assert client.get(path).status_code == 404
    assert (
        client.patch(path, json={"name": "Forbidden"}, headers=preconditions()).status_code == 404
    )
    sign_in(client, "employee@example.test")
    row = client.get(path)
    assert row.status_code == 200 and row.headers["etag"] == '"1"'
    assert row.json()["name"] == "Client One" and row.json()["can_manage"]
    assert "no-store" in row.headers["cache-control"]
    changed = client.patch(path, json={"name": "Renamed"}, headers=preconditions())
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert (
        client.patch(path, json={"name": "Renamed"}, headers=preconditions(2)).json()
        == changed.json()
    )
    assert (
        client.patch(path, json={"active": False}, headers=preconditions(2)).json()["version"] == 3
    )
    assert client.get(path).json()["active"] is False
    assert (
        client.patch(path, json={"active": True}, headers=preconditions(3)).json()["version"] == 4
    )
    assert client.get("/api/v1/clients").json()["items"][0]["name"] == "Renamed"


def test_anonymous_and_ordinary_account_cannot_provision_clients(client, seeded_user):
    assert client.get("/api/v1/clients").status_code == 401
    assert create(client, seeded_user).status_code == 401
    sign_in(client, "employee@example.test")
    assert client.get("/api/v1/clients").json()["items"] == []
    assert create(client, seeded_user).status_code == 403


def test_explicit_self_manager_selection_revokes_current_session(admin_client, db_engine):
    client = admin_client
    me = client.get("/api/v1/auth/me").json()
    identifier = created(client, me["id"])
    assert client.get("/api/v1/auth/me").status_code == 401
    sign_in(client, "admin@example.test")
    assert client.get(f"/api/v1/clients/{identifier}").json()["can_manage"]


def test_creation_receipt_replay_never_regrants_revoked_access(
    admin_client, seeded_user, db_engine
):
    from altvia.client_registry import set_client_access

    key = uuid4().hex
    receipt = create(admin_client, seeded_user, key=key)
    identifier = UUID(receipt.json()["client_id"])
    with Session(db_engine) as db, db.begin():
        assert set_client_access(db, "employee@example.test", identifier, None)
    replay = create(admin_client, seeded_user, key=key)
    assert replay.status_code == 200 and replay.json() == receipt.json()
    assert create(admin_client, seeded_user, name="Different", key=key).status_code == 409
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(f"/api/v1/clients/{identifier}").status_code == 404


def test_client_ceiling_and_role_are_independently_required(admin_client, seeded_user, db_engine):
    from altvia.models import ClientAccessGrant

    first = created(admin_client, seeded_user, "First")
    second = created(admin_client, seeded_user, "Second")
    with Session(db_engine) as db, db.begin():
        db.delete(db.get(ClientAccessGrant, (seeded_user, UUID(first))))
        db.delete(db.scalar(select(RoleBinding).where(RoleBinding.client_id == UUID(second))))
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get("/api/v1/clients").json()["items"] == []
    for identifier in (first, second, uuid4()):
        assert admin_client.get(f"/api/v1/clients/{identifier}").status_code == 404
        assert admin_client.get(f"/api/v1/clients/{identifier}/activity").status_code == 404


def test_client_access_demotion_is_fresh_and_no_op_does_not_revoke(
    admin_client, seeded_user, db_engine
):
    from altvia.client_registry import set_client_access

    identifier = created(admin_client, seeded_user)
    sign_in(admin_client, "employee@example.test")
    with Session(db_engine) as db, db.begin():
        assert not set_client_access(
            db, "employee@example.test", UUID(identifier), "operations_manager"
        )
    assert admin_client.get(f"/api/v1/clients/{identifier}").status_code == 200
    with Session(db_engine) as db, db.begin():
        assert set_client_access(db, "employee@example.test", UUID(identifier), "viewer")
    assert admin_client.get(f"/api/v1/clients/{identifier}").status_code == 401
    sign_in(admin_client, "employee@example.test")
    assert not admin_client.get(f"/api/v1/clients/{identifier}").json()["can_manage"]
    assert (
        admin_client.patch(
            f"/api/v1/clients/{identifier}", json={"name": "Denied"}, headers=preconditions(2)
        ).status_code
        == 403
    )


def test_client_projection_is_scoped_and_cannot_leak_to_identity_activity(
    admin_client, seeded_user, db_engine
):
    from altvia.activity import claim_events, consume_event

    identifier = created(admin_client, seeded_user)
    for event_id, _ in claim_events(db_engine, datetime.now(UTC)):
        consume_event(db_engine, event_id, datetime.now(UTC))
    assert all(
        row["resource_type"] != "client"
        for row in admin_client.get("/api/v1/identity-activity").json()["items"]
    )
    assert admin_client.get(f"/api/v1/clients/{identifier}/activity").status_code == 404
    sign_in(admin_client, "employee@example.test")
    feed = admin_client.get(f"/api/v1/clients/{identifier}/activity").json()
    assert feed["items"][0]["event_type"] == "client.created"
    assert feed["items"][0]["details"] == {"manager_user_id": str(seeded_user)}
    assert "Client One" not in str(feed) and TEST_PASSWORD not in str(feed)
    assert admin_client.get("/api/v1/identity-activity").status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"active": None},
        {"name": " "},
        {"active": 1},
        {"name": "x", "client_id": str(uuid4())},
    ],
)
def test_client_patch_rejects_invalid_or_mass_assignment(admin_client, seeded_user, body):
    identifier = created(admin_client, seeded_user)
    sign_in(admin_client, "employee@example.test")
    assert (
        admin_client.patch(
            f"/api/v1/clients/{identifier}", json=body, headers=preconditions()
        ).status_code
        == 422
    )


def test_client_http_preconditions_and_safe_version_conflict(admin_client, seeded_user):
    identifier = created(admin_client, seeded_user)
    sign_in(admin_client, "employee@example.test")
    path = f"/api/v1/clients/{identifier}"
    assert admin_client.patch(path, json={"name": "Next"}).status_code == 428
    assert (
        admin_client.patch(path, json={"name": "Next"}, headers=preconditions(99)).status_code
        == 409
    )
    assert (
        admin_client.patch(
            path,
            json={"name": "Next"},
            headers={**preconditions(), "Origin": "https://foreign.example"},
        ).status_code
        == 403
    )
    assert (
        admin_client.patch(
            path, json={"name": "Next"}, headers={**preconditions(), "X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert admin_client.get("/api/v1/clients?limit=101").status_code == 422
    assert admin_client.get("/api/v1/clients?search=hidden").status_code == 422


def test_client_collection_cursor_is_bound_to_current_user(admin_client, seeded_user, db_engine):
    from altvia.client_registry import set_client_access

    first = created(admin_client, seeded_user, "A")
    created(admin_client, seeded_user, "B")
    sign_in(admin_client, "employee@example.test")
    page = admin_client.get("/api/v1/clients?limit=1").json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    tail = admin_client.get("/api/v1/clients", params={"cursor": page["next_cursor"]}).json()
    assert len(tail["items"]) == 1 and tail["items"][0]["id"] != page["items"][0]["id"]
    with Session(db_engine) as db, db.begin():
        assert set_client_access(db, "employee@example.test", UUID(first), None)
    sign_in(admin_client, "admin@example.test")
    assert (
        admin_client.get("/api/v1/clients", params={"cursor": page["next_cursor"]}).status_code
        == 422
    )


def test_concurrent_provisioning_key_has_one_effect(admin_client, seeded_user, db_engine):
    key = uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(admin_client, seeded_user, key=key), range(2)))
    assert sorted(row.status_code for row in responses) == [200, 201]
    assert responses[0].json() == responses[1].json()
    with Session(db_engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "client.created")
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "client.created")
            )
            == 1
        )
