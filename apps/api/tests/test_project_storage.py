from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia.activity import consume_event
from altvia.models import Client, OperationalArea, OutboxEvent, Project, RoleBinding, Team
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session


def test_project_migration_preserves_clients_and_refuses_populated_downgrade(
    db_engine, seeded_user
):
    config = Config("apps/api/alembic.ini")
    with Session(db_engine) as db, db.begin():
        now = datetime.now(UTC)
        customer = Client(
            name="Preserved customer", active=True, version=1, created_at=now, updated_at=now
        )
        db.add(customer)
        db.flush()
        identifier = customer.id
    command.downgrade(config, "b46087000006")
    command.upgrade(config, "head")
    with Session(db_engine) as db, db.begin():
        assert db.get(Client, identifier).name == "Preserved customer"
        db.add(OperationalArea(name="Retained area"))
    with pytest.raises(
        DBAPIError, match="Cannot downgrade while durable project or area data exists"
    ):
        command.downgrade(config, "b46087000006")
    with Session(db_engine) as db:
        assert db.scalar(select(OperationalArea)).name == "Retained area"
    command.check(config)


def test_project_scope_check_and_exclusive_role_fk_are_enforced(db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        team = Team(name="Owner")
        db.add(team)
        db.flush()
        team_id = team.id
    for scope, customer in [("client", None), ("internal", uuid4()), ("arbitrary", None)]:
        with pytest.raises(IntegrityError), Session(db_engine) as db, db.begin():
            db.add(Project(name="Invalid", scope_kind=scope, client_id=customer, team_id=team_id))
    with pytest.raises(IntegrityError), Session(db_engine) as db, db.begin():
        db.add(
            RoleBinding(
                user_id=seeded_user,
                role_name="platform_admin",
                scope_kind="global",
                project_id=uuid4(),
            )
        )


@pytest.mark.parametrize(
    "resource,event_type,extra",
    [
        ("project", "identity.user_created", {}),
        ("client", "project.created", {"manager_user_id": str(uuid4())}),
        ("project", "project.created", {"manager_user_id": str(uuid4()), "name": "Forbidden"}),
        (
            "project",
            "project.access_changed",
            {"member_user_id": str(uuid4()), "role_name": "operations_manager"},
        ),
        ("operational_area", "operational_area.created", {"manager_user_id": str(uuid4())}),
        ("operational_area", "operational_area.updated", {"changed_fields": "operational_area_id"}),
    ],
)
def test_registry_worker_rejects_invalid_semantic_payload(
    db_engine, seeded_user, resource, event_type, extra
):
    now = datetime.now(UTC)
    with Session(db_engine) as db, db.begin():
        event = OutboxEvent(
            aggregate_type=resource,
            aggregate_id=uuid4(),
            aggregate_version=1,
            event_type=event_type,
            schema_version=1,
            payload={"actor_id": None, "actor_kind": "management_command", **extra},
            occurred_at=now,
            next_attempt_at=now,
            correlation_id=uuid4().hex,
        )
        db.add(event)
        db.flush()
        identifier = event.event_id
    assert not consume_event(db_engine, identifier, now)
    with Session(db_engine) as db:
        event = db.get(OutboxEvent, identifier)
        assert event.status == "dead" and event.last_error_code == "invalid_event"
