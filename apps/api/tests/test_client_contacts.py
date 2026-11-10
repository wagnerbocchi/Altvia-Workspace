from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from altvia.models import AuditLog, OutboxEvent, Project, Team, User
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_client_registry import created
from test_team_api import admin_client, preconditions, sign_in

__all__ = ["admin_client"]


def contacts(client_id):
    return f"/api/v1/clients/{client_id}/contacts"


def create_contact(
    client, client_id, email="Person@Example.TEST", name=" External person ", key=None
):
    return client.post(
        contacts(client_id),
        json={"display_name": name, "email": email},
        headers=preconditions(key=key),
    )


def managed(client, seeded_user):
    identifier = created(client, seeded_user)
    sign_in(client, "employee@example.test")
    return identifier


def project_row(db_engine, client_id, *, active=True, team_active=True):
    with Session(db_engine) as db, db.begin():
        team = Team(name="Contact project team", active=team_active)
        db.add(team)
        db.flush()
        row = Project(
            name="Default candidate",
            scope_kind="client" if client_id else "internal",
            client_id=UUID(client_id) if client_id else None,
            team_id=team.id,
            active=active,
        )
        db.add(row)
        db.flush()
        return str(row.id)


def test_contact_crud_versions_parent_history_and_no_account_grant(
    admin_client, seeded_user, db_engine
):
    identifier = managed(admin_client, seeded_user)
    with Session(db_engine) as db:
        accounts = db.scalar(select(func.count()).select_from(User))
    receipt = create_contact(admin_client, identifier)
    assert receipt.status_code == 201, receipt.text
    assert set(receipt.json()) == {"client_id", "contact_id"}
    path = contacts(identifier) + "/" + receipt.json()["contact_id"]
    first = admin_client.get(path)
    assert first.status_code == 200 and first.headers["etag"] == '"1"'
    assert first.json()["display_name"] == "External person"
    assert first.json()["email_normalized"] == "person@example.test"
    assert first.json()["verification_state"] == "unverified"
    assert "no-store" in first.headers["cache-control"]
    assert admin_client.get(f"/api/v1/clients/{identifier}").json()["version"] == 2
    for version, body in [
        (1, {"display_name": "Revised", "email": "new@example.test"}),
        (2, {"active": False}),
        (3, {"active": True}),
    ]:
        changed = admin_client.patch(path, json=body, headers=preconditions(version))
        assert changed.status_code == 200 and changed.json()["version"] == version + 1
    noop = admin_client.patch(path, json={"active": True}, headers=preconditions(4))
    assert noop.status_code == 200 and noop.json()["version"] == 4
    assert admin_client.get(f"/api/v1/clients/{identifier}").json()["version"] == 5
    assert (
        admin_client.patch(
            path, json={"display_name": "Stale"}, headers=preconditions()
        ).status_code
        == 409
    )
    assert admin_client.get(contacts(identifier)).json()["items"] == [noop.json()]
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == accounts
        events = list(
            db.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == UUID(identifier)))
        )
        assert len(events) == 5
        assert "new@example.test" not in str([row.payload for row in events])
        assert "Revised" not in str([row.payload for row in events])


def test_duplicate_email_is_client_local_including_archived_contacts(
    admin_client, seeded_user, db_engine
):
    first = created(admin_client, seeded_user)
    second = created(admin_client, seeded_user)
    sign_in(admin_client, "employee@example.test")
    a = create_contact(admin_client, first, "employee@example.test")
    b = create_contact(admin_client, second, "employee@example.test")
    assert a.status_code == b.status_code == 201
    assert a.json()["contact_id"] != b.json()["contact_id"]
    path = contacts(first) + "/" + a.json()["contact_id"]
    assert (
        admin_client.patch(path, json={"active": False}, headers=preconditions()).status_code == 200
    )
    assert create_contact(admin_client, first, " EMPLOYEE@EXAMPLE.TEST ").status_code == 409
    assert admin_client.get(contacts(first)).json()["items"][0]["active"] is False
    assert admin_client.get(contacts(second) + "/" + a.json()["contact_id"]).status_code == 404
    with Session(db_engine) as db:
        assert db.get(User, seeded_user).email_normalized == "employee@example.test"


def test_contact_receipt_is_minimal_and_requires_fresh_scope_before_replay(
    admin_client, seeded_user, db_engine
):
    from altvia.client_registry import set_client_access

    identifier = managed(admin_client, seeded_user)
    key = uuid4().hex
    receipt = create_contact(admin_client, identifier, key=key)
    assert receipt.status_code == 201
    path = contacts(identifier) + "/" + receipt.json()["contact_id"]
    assert (
        admin_client.patch(
            path, json={"email": "edited@example.test"}, headers=preconditions()
        ).status_code
        == 200
    )
    replay = create_contact(admin_client, identifier, key=key)
    assert replay.status_code == 200 and replay.json() == receipt.json()
    assert "edited@example.test" not in replay.text
    assert (
        create_contact(admin_client, identifier, email="other@example.test", key=key).status_code
        == 409
    )
    with Session(db_engine) as db, db.begin():
        set_client_access(db, "employee@example.test", UUID(identifier), "viewer")
    sign_in(admin_client, "employee@example.test")
    assert create_contact(admin_client, identifier, key=key).status_code == 403
    assert admin_client.get(path).status_code == 200
    assert (
        admin_client.patch(path, json={"active": False}, headers=preconditions(2)).status_code
        == 403
    )
    with Session(db_engine) as db, db.begin():
        set_client_access(db, "employee@example.test", UUID(identifier), None)
    sign_in(admin_client, "employee@example.test")
    assert create_contact(admin_client, identifier, key=key).status_code == 404


def test_platform_admin_and_partial_client_grants_never_read_contacts(
    admin_client, seeded_user, db_engine
):
    from altvia.models import ClientAccessGrant, RoleBinding

    identifier = created(admin_client, seeded_user)
    assert admin_client.get(contacts(identifier)).status_code == 404
    assert create_contact(admin_client, identifier).status_code == 404
    sign_in(admin_client, "employee@example.test")
    assert create_contact(admin_client, identifier).status_code == 201
    with Session(db_engine) as db, db.begin():
        db.delete(db.get(ClientAccessGrant, (seeded_user, UUID(identifier))))
    assert admin_client.get(contacts(identifier)).status_code == 404
    with Session(db_engine) as db, db.begin():
        db.add(
            ClientAccessGrant(
                user_id=seeded_user, client_id=UUID(identifier), created_at=datetime.now(UTC)
            )
        )
        db.delete(db.scalar(select(RoleBinding).where(RoleBinding.client_id == UUID(identifier))))
    assert admin_client.get(contacts(identifier)).status_code == 404


@pytest.mark.parametrize(
    "email",
    [
        "x",
        "a\r\n@example.test",
        "Name <a@example.test>",
        "a@example.test,b@example.test",
        "a..b@example.test",
        ".a@example.test",
        "a@-example.test",
        "a@example..test",
        "á@example.test",
        "a@example.test\x00",
    ],
)
def test_contact_email_rejects_non_mailbox_input(admin_client, seeded_user, email):
    identifier = managed(admin_client, seeded_user)
    assert create_contact(admin_client, identifier, email).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"display_name": None},
        {"email": None},
        {"active": None},
        {"active": "true"},
        {"verification_state": "verified"},
        {"client_id": str(uuid4())},
        {"email_normalized": "a@example.test"},
    ],
)
def test_contact_patch_rejects_mass_assignment(admin_client, seeded_user, body):
    identifier = managed(admin_client, seeded_user)
    receipt = create_contact(admin_client, identifier)
    assert receipt.status_code == 201
    path = contacts(identifier) + "/" + receipt.json()["contact_id"]
    assert admin_client.patch(path, json=body, headers=preconditions()).status_code == 422


def test_contact_pages_bind_actor_and_parent_and_reject_repeated_queries(admin_client, seeded_user):
    first = created(admin_client, seeded_user)
    second = created(admin_client, seeded_user)
    sign_in(admin_client, "employee@example.test")
    for index in range(3):
        assert create_contact(admin_client, first, f"p{index}@example.test").status_code == 201
    page = admin_client.get(contacts(first), params={"limit": 1}).json()
    tail = admin_client.get(contacts(first), params={"cursor": page["next_cursor"]}).json()
    assert len(tail["items"]) == 2
    assert page["items"][0]["id"] not in [row["id"] for row in tail["items"]]
    assert (
        admin_client.get(contacts(second), params={"cursor": page["next_cursor"]}).status_code
        == 422
    )
    assert admin_client.get(contacts(first) + "?limit=1&limit=2").status_code == 422
    assert admin_client.get(contacts(first) + "?other=1").status_code == 422


def test_duplicate_contact_race_commits_one_receipt_event_and_parent_advance(
    admin_client, seeded_user, db_engine
):
    identifier = managed(admin_client, seeded_user)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create_contact(admin_client, identifier), range(2)))
    assert sorted(row.status_code for row in results) == [201, 409]
    assert len(admin_client.get(contacts(identifier)).json()["items"]) == 1
    assert admin_client.get(f"/api/v1/clients/{identifier}").json()["version"] == 2
    with Session(db_engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "client.contact_created")
            )
            == 1
        )


def test_archived_client_blocks_real_contact_changes_but_allows_replay_and_noop(
    admin_client, seeded_user
):
    identifier = managed(admin_client, seeded_user)
    key = uuid4().hex
    receipt = create_contact(admin_client, identifier, key=key)
    assert receipt.status_code == 201
    path = contacts(identifier) + "/" + receipt.json()["contact_id"]
    assert (
        admin_client.patch(
            f"/api/v1/clients/{identifier}", json={"active": False}, headers=preconditions(2)
        ).status_code
        == 200
    )
    assert create_contact(admin_client, identifier, key=key).status_code == 200
    assert create_contact(admin_client, identifier, "new@example.test").status_code == 409
    assert (
        admin_client.patch(
            path, json={"display_name": "External person"}, headers=preconditions()
        ).status_code
        == 200
    )
    assert (
        admin_client.patch(
            path, json={"display_name": "Changed"}, headers=preconditions()
        ).status_code
        == 409
    )


def test_default_project_same_client_active_eligibility_clear_noop_and_stale(
    admin_client, seeded_user, db_engine
):
    identifier = created(admin_client, seeded_user)
    other = created(admin_client, seeded_user)
    valid = project_row(db_engine, identifier)
    invalid = [
        project_row(db_engine, other),
        project_row(db_engine, None),
        project_row(db_engine, identifier, active=False),
        project_row(db_engine, identifier, team_active=False),
        str(uuid4()),
    ]
    sign_in(admin_client, "employee@example.test")
    path = f"/api/v1/clients/{identifier}"
    assert admin_client.get(path).json()["default_project_id"] is None
    for project_id in invalid:
        assert (
            admin_client.patch(
                path, json={"default_project_id": project_id}, headers=preconditions()
            ).status_code
            == 422
        )
    changed = admin_client.patch(path, json={"default_project_id": valid}, headers=preconditions())
    assert changed.status_code == 200 and changed.json()["default_project_id"] == valid
    assert changed.json()["version"] == 2
    assert (
        admin_client.patch(
            path, json={"default_project_id": valid}, headers=preconditions(2)
        ).json()
        == changed.json()
    )
    assert (
        admin_client.patch(
            path, json={"default_project_id": None}, headers=preconditions()
        ).status_code
        == 409
    )
    with Session(db_engine) as db, db.begin():
        db.get(Project, UUID(valid)).active = False
    assert admin_client.get(path).json()["default_project_id"] == valid
    assert (
        admin_client.patch(path, json={"active": False}, headers=preconditions(2)).status_code
        == 200
    )
    assert (
        admin_client.patch(
            path, json={"default_project_id": None}, headers=preconditions(3)
        ).json()["version"]
        == 4
    )
