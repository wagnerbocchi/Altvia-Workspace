from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia.models import ActivityEvent, Client, ClientAccessGrant, RoleBinding, Team
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_client_registry import admin_client, created
from test_team_api import preconditions, sign_in

__all__ = ["admin_client"]


def test_client_migration_preserves_older_schema_and_refuses_customer_data_loss(
    db_engine, seeded_user
):
    config = Config("apps/api/alembic.ini")
    with Session(db_engine) as db, db.begin():
        team = Team(name="Preserved team")
        db.add(team)
        db.flush()
        identifier = team.id
    command.downgrade(config, "b46087000005")
    command.upgrade(config, "head")
    with Session(db_engine) as db, db.begin():
        assert db.get(Team, identifier).name == "Preserved team"
        now = datetime.now(UTC)
        client = Client(name="Retained", active=True, version=1, created_at=now, updated_at=now)
        db.add(client)
        db.flush()
        client_id = client.id
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable client data exists"):
        command.downgrade(config, "b46087000005")
    with Session(db_engine) as db:
        assert db.get(Client, client_id).name == "Retained"
    command.check(config)


def test_two_clients_and_cross_client_activity_cursors_are_isolated(
    admin_client, db_engine, seeded_user
):
    from altvia import management
    from altvia.activity import claim_events, consume_event
    from conftest import TEST_PASSWORD

    first = created(admin_client, seeded_user, "Authorized")
    with Session(db_engine) as db, db.begin():
        other = management.create_user(
            db, "other-client@example.test", "Other manager", TEST_PASSWORD
        )
        other_id = other.id
    second = created(admin_client, other_id, "Private client")
    sign_in(admin_client, "employee@example.test")
    assert [row["id"] for row in admin_client.get("/api/v1/clients").json()["items"]] == [first]
    assert admin_client.get(f"/api/v1/clients/{second}").status_code == 404
    assert (
        admin_client.patch(
            f"/api/v1/clients/{second}", json={"name": "Denied"}, headers=preconditions()
        ).status_code
        == 404
    )
    assert admin_client.get(f"/api/v1/clients/{second}/activity").status_code == 404
    assert (
        admin_client.patch(
            f"/api/v1/clients/{first}", json={"name": "Changed"}, headers=preconditions()
        ).status_code
        == 200
    )
    for event_id, _ in claim_events(db_engine, datetime.now(UTC)):
        consume_event(db_engine, event_id, datetime.now(UTC))
    page = admin_client.get(f"/api/v1/clients/{first}/activity?limit=1").json()
    assert page["next_cursor"]
    tail = admin_client.get(
        f"/api/v1/clients/{first}/activity", params={"cursor": page["next_cursor"]}
    ).json()
    assert len(tail["items"]) == 1 and tail["items"][0]["resource_id"] == first
    sign_in(admin_client, "other-client@example.test")
    assert (
        admin_client.get(
            f"/api/v1/clients/{second}/activity", params={"cursor": page["next_cursor"]}
        ).status_code
        == 422
    )


def test_exclusive_client_scope_and_foreign_keys_are_database_enforced(
    admin_client, seeded_user, db_engine
):
    identifier = UUID(created(admin_client, seeded_user))
    with Session(db_engine) as db:
        valid = db.scalar(select(RoleBinding).where(RoleBinding.client_id == identifier))
        assert valid.scope_kind == "client" and valid.team_id is None
    for assignments in (
        "scope_kind='global'",
        "team_id=gen_random_uuid()",
        "client_id=NULL",
        "role_name='platform_admin'",
    ):
        with db_engine.begin() as connection, pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE role_bindings SET " + assignments + " WHERE client_id=:id"),
                {"id": identifier},
            )
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.add(
            ClientAccessGrant(user_id=seeded_user, client_id=uuid4(), created_at=datetime.now(UTC))
        )
        db.flush()


def test_client_projection_malformed_data_does_not_become_visible(
    admin_client, seeded_user, db_engine
):
    from altvia.activity import consume_event
    from altvia.models import OutboxEvent

    identifier = UUID(created(admin_client, seeded_user))
    with Session(db_engine) as db, db.begin():
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == identifier))
        event.payload = {**event.payload, "name": "must not appear in a projection"}
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"
        assert db.get(ActivityEvent, event_id) is None


@pytest.mark.parametrize("payload", [{}, {"role_name": "viewer"}])
def test_client_created_event_requires_its_delegation_metadata(
    admin_client, seeded_user, db_engine, payload
):
    from altvia.activity import consume_event
    from altvia.models import OutboxEvent

    identifier = UUID(created(admin_client, seeded_user))
    with Session(db_engine) as db, db.begin():
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == identifier))
        event.payload = {
            key: value for key, value in event.payload.items() if key != "manager_user_id"
        } | payload
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
