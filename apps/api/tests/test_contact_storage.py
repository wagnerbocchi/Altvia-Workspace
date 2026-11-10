from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia.models import ActivityEvent, Client, OutboxEvent
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_client_contacts import contacts, create_contact, managed, project_row
from test_client_registry import created
from test_team_api import admin_client, preconditions, sign_in

__all__ = ["admin_client"]


def test_contact_migration_preserves_clients_and_refuses_loss(db_engine, seeded_user):
    now = datetime.now(UTC)
    with Session(db_engine) as db, db.begin():
        row = Client(name="Preserved", active=True, version=1, created_at=now, updated_at=now)
        db.add(row)
        db.flush()
        identifier = row.id
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000009")
    assert "client_contacts" not in inspect(db_engine).get_table_names()
    command.upgrade(config, "head")
    with Session(db_engine) as db:
        assert db.get(Client, identifier).name == "Preserved"
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO client_contacts(id,client_id,display_name,email_normalized,"
                "active,version,verification_state) "
                "VALUES (:id,:client,'External','person@example.test',true,1,'unverified')"
            ),
            {"id": uuid4(), "client": identifier},
        )
    with pytest.raises(
        DBAPIError, match="Cannot downgrade while durable contact or default data exists"
    ):
        command.downgrade(config, "b46087000009")
    assert "client_contacts" in inspect(db_engine).get_table_names()
    command.check(config)


def test_default_scope_is_enforced_in_sql_and_blocks_parent_scope_rewrite(
    admin_client, seeded_user, db_engine
):
    first = created(admin_client, seeded_user)
    second = created(admin_client, seeded_user)
    valid = project_row(db_engine, first)
    invalid = [project_row(db_engine, second), project_row(db_engine, None), str(uuid4())]
    for identifier in invalid:
        with db_engine.begin() as connection, pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE clients SET default_project_id=:project WHERE id=:client"),
                {"client": first, "project": identifier},
            )
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE clients SET default_project_id=:project WHERE id=:client"),
            {"client": first, "project": valid},
        )
    with db_engine.begin() as connection, pytest.raises(DBAPIError):
        connection.execute(
            text("UPDATE projects SET client_id=:client WHERE id=:project"),
            {"client": second, "project": valid},
        )
    with pytest.raises(
        DBAPIError, match="Cannot downgrade while durable contact or default data exists"
    ):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000009")


def test_contacts_enforce_verification_uniqueness_and_parent_in_sql(
    admin_client, seeded_user, db_engine
):
    identifier = managed(admin_client, seeded_user)
    receipt = create_contact(admin_client, identifier)
    assert receipt.status_code == 201
    for assignments in [
        "verification_state='verified'",
        "version=0",
        "display_name=' '",
        "client_id='00000000-0000-0000-0000-000000000000'",
    ]:
        with db_engine.begin() as connection, pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE client_contacts SET " + assignments + " WHERE id=:id"),
                {"id": receipt.json()["contact_id"]},
            )
    with db_engine.begin() as connection, pytest.raises(DBAPIError):
        connection.execute(
            text(
                "INSERT INTO client_contacts(id,client_id,display_name,email_normalized,"
                "active,version,verification_state) SELECT gen_random_uuid(),client_id,"
                "display_name,email_normalized,active,version,verification_state "
                "FROM client_contacts"
            )
        )


def test_contact_events_project_once_redacted_and_only_into_client_feed(
    admin_client, seeded_user, db_engine
):
    from altvia.activity import claim_events, consume_event

    identifier = managed(admin_client, seeded_user)
    receipt = create_contact(admin_client, identifier)
    assert receipt.status_code == 201
    path = contacts(identifier) + "/" + receipt.json()["contact_id"]
    assert (
        admin_client.patch(
            path,
            json={"email": "new@example.test", "display_name": "New contact"},
            headers=preconditions(),
        ).status_code
        == 200
    )
    for event_id, _ in claim_events(db_engine, datetime.now(UTC)):
        assert consume_event(db_engine, event_id, datetime.now(UTC))
        assert not consume_event(db_engine, event_id, datetime.now(UTC))
    feed = admin_client.get(f"/api/v1/clients/{identifier}/activity").json()["items"]
    assert [row["event_type"] for row in feed] == [
        "client.contact_updated",
        "client.contact_created",
        "client.created",
    ]
    assert feed[0]["details"] == {
        "contact_id": receipt.json()["contact_id"],
        "changed_fields": "display_name,email",
    }
    assert "new@example.test" not in str(feed) and "New contact" not in str(feed)
    sign_in(admin_client, "admin@example.test")
    assert all(
        row["resource_type"] != "client"
        for row in admin_client.get("/api/v1/identity-activity").json()["items"]
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"email": "private@example.test"},
        {"changed_fields": "email,email"},
        {"changed_fields": "verification_state"},
        {"contact_id": None},
    ],
)
def test_malformed_contact_event_is_dead_not_exposed(admin_client, seeded_user, db_engine, bad):
    from altvia.activity import consume_event

    identifier = managed(admin_client, seeded_user)
    assert create_contact(admin_client, identifier).status_code == 201
    with Session(db_engine) as db, db.begin():
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "client.contact_created")
        )
        event.payload = event.payload | bad
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"
        assert db.get(ActivityEvent, event_id) is None


def test_api_contact_runtime_privilege_and_worker_denial(db_engine, seeded_user, settings):
    from altvia import management, provision
    from altvia.main import create_app
    from conftest import TEST_PASSWORD
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from test_runtime_provision import runtime_url

    app_url = runtime_url(db_engine)
    worker_url = runtime_url(db_engine).set(username="altvia_worker")
    provision.provision_runtime(
        db_engine,
        app_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    with Session(db_engine) as db, db.begin():
        management.bootstrap_admin(db, "admin@example.test", "Admin", TEST_PASSWORD)
    configured = settings.model_copy(
        update={
            "database_url": settings.database_url.__class__(
                app_url.render_as_string(hide_password=False)
            ),
            "database_url_file": None,
        }
    )
    with TestClient(
        create_app(configured),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        sign_in(client, "admin@example.test")
        identifier = created(client, seeded_user)
        sign_in(client, "employee@example.test")
        assert create_contact(client, identifier).status_code == 201
        assert (
            client.get(contacts(identifier)).json()["items"][0]["verification_state"]
            == "unverified"
        )
    worker = create_engine(worker_url, hide_parameters=True)
    runtime = create_engine(app_url, hide_parameters=True)
    try:
        with runtime.begin() as connection, pytest.raises(DBAPIError):
            connection.execute(text("DELETE FROM client_contacts"))
        with worker.begin() as connection, pytest.raises(DBAPIError):
            connection.execute(text("SELECT * FROM client_contacts"))
    finally:
        worker.dispose()
        runtime.dispose()
