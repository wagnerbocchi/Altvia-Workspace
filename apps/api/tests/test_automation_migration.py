"""Native assignment ledger identities, constraints and safe contraction."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia.models import ActivityEvent, AuditLog, IdempotencyRecord, OutboxEvent
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_runtime_provision import runtime_url
from test_team_api import admin_client
from ticket_work_support import make_link_context

__all__ = ["admin_client"]

TABLES = {
    "automation_rules",
    "automation_rule_revisions",
    "automation_executions",
    "automation_effects",
}


def insert(connection, table, values):
    # Only fixed test-owned table/column dictionaries reach this owner helper.
    connection.execute(
        text(
            f"INSERT INTO {table} ({','.join(values)}) "
            f"VALUES ({','.join(':' + name for name in values)})"
        ),
        values,
    )


@pytest.fixture
def ledger(admin_client, db_engine, seeded_user):
    context = make_link_context(admin_client, db_engine, seeded_user)
    rule = {
        "id": uuid4(),
        "client_id": context.client_id,
        "queue_id": context.queue_id,
        "action_id": uuid4(),
        "version": 1,
        "cancelled_through_version": 0,
    }
    revision = {
        "rule_id": rule["id"],
        "version": 1,
        "enabled": False,
        "title": "Configured task",
        "priority": "medium",
        "ticket_statuses": ["new", "open"],
        "authorizer_id": seeded_user,
    }
    with db_engine.begin() as connection:
        source = connection.scalar(
            text("SELECT event_id FROM outbox_events WHERE aggregate_id=:id LIMIT 1"),
            {"id": context.ticket_id},
        )
        assert source is not None
        execution = {
            "id": uuid4(),
            "rule_id": rule["id"],
            "action_id": rule["action_id"],
            "rule_version": 1,
            "client_id": context.client_id,
            "queue_id": context.queue_id,
            "ticket_id": context.ticket_id,
            "source_event_id": source,
            "state": "pending",
            "attempts": 0,
            "version": 1,
        }
        insert(connection, "automation_rules", rule)
        insert(connection, "automation_rule_revisions", revision)
        insert(connection, "automation_executions", execution)
    effect = {
        "rule_id": rule["id"],
        "action_id": rule["action_id"],
        **asdict(context),
        "origin_execution_id": execution["id"],
        "mode": "created",
    }
    return rule, revision, execution, effect


def rejected(db_engine, table, values, sqlstate):
    with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
        insert(connection, table, values)
    assert caught.value.orig.sqlstate == sqlstate


def test_assignment_ledger_schema_exists(db_engine):
    assert TABLES <= set(inspect(db_engine).get_table_names())


def test_rule_revision_scope_and_native_value_constraints(db_engine, ledger):
    rule, revision, _, _ = ledger
    rejected(db_engine, "automation_rules", {**rule, "id": uuid4()}, "23505")
    for field, value in (("version", 0), ("cancelled_through_version", -1)):
        with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
            connection.execute(
                text(f"UPDATE automation_rules SET {field}=:value"), {"value": value}
            )
        assert caught.value.orig.sqlstate == "23514"
    with pytest.raises(DBAPIError), db_engine.begin() as connection:
        connection.execute(text("UPDATE automation_rules SET cancelled_through_version=2"))
    invalid = [
        ({"title": " "}, "23514"),
        ({"title": "x" * 301}, "22001"),
        ({"priority": "urgent"}, "23514"),
        ({"ticket_statuses": []}, "23514"),
        ({"ticket_statuses": ["new", "new"]}, "23514"),
        ({"ticket_statuses": ["closed"]}, "23514"),
        ({"ticket_statuses": [None]}, "23514"),
        ({"ticket_statuses": [["new"]]}, "23514"),
        ({"authorizer_id": uuid4()}, "23503"),
        ({"rule_id": uuid4()}, "23503"),
    ]
    for changes, code in invalid:
        rejected(
            db_engine, "automation_rule_revisions", {**revision, "version": 2, **changes}, code
        )
    with db_engine.begin() as connection:
        insert(connection, "automation_rule_revisions", {**revision, "version": 2, "enabled": True})
        assert connection.scalar(text("SELECT count(*) FROM automation_rule_revisions")) == 2


def test_execution_source_context_state_and_lease_constraints(db_engine, ledger):
    _, _, execution, _ = ledger
    rejected(db_engine, "automation_executions", {**execution, "id": uuid4()}, "23505")
    for changes, code in [
        ({"action_id": uuid4()}, "23503"),
        ({"client_id": uuid4()}, "23503"),
        ({"queue_id": uuid4()}, "23503"),
        ({"ticket_id": uuid4()}, "23503"),
        ({"source_event_id": uuid4()}, "23503"),
        ({"rule_version": 99}, "23503"),
    ]:
        assignments = ",".join(f"{field}=:{field}" for field in changes)
        with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
            connection.execute(text("UPDATE automation_executions SET " + assignments), changes)
        assert caught.value.orig.sqlstate == code
    invalid_updates = [
        "state='invented'",
        "state='processing'",
        "lease_token='00000000-0000-0000-0000-000000000001'",
        "lease_until=clock_timestamp()",
        "attempts=-1",
        "attempts=9",
        "version=0",
        "error_code='private exception text'",
    ]
    for assignments in invalid_updates:
        with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
            connection.execute(text("UPDATE automation_executions SET " + assignments))
        assert caught.value.orig.sqlstate == "23514"
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE automation_executions SET state='processing',lease_token=:token,"
                "lease_until=clock_timestamp()+interval '30 seconds',attempts=1"
            ),
            {"token": uuid4()},
        )


def test_effect_native_context_receipt_survives_unlink(db_engine, ledger, seeded_user):
    _, _, execution, effect = ledger
    for changes in (
        {"action_id": uuid4()},
        {"project_id": uuid4()},
        {"work_item_id": uuid4()},
        {"ticket_id": uuid4()},
        {"origin_execution_id": uuid4()},
        {"client_id": uuid4()},
        {"queue_id": uuid4()},
    ):
        rejected(db_engine, "automation_effects", {**effect, **changes}, "23503")
    rejected(db_engine, "automation_effects", {**effect, "mode": "linked"}, "23514")
    for field in effect:
        rejected(db_engine, "automation_effects", {**effect, field: None}, "23502")
    # A real different execution must still have the SAME ticket/rule context.
    other_ticket, other_source, other_execution = uuid4(), uuid4(), uuid4()
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tickets (id,client_id,queue_id,requester_id,subject,priority) "
                "SELECT :new,client_id,queue_id,requester_id,'Other ticket',priority "
                "FROM tickets WHERE id=:original"
            ),
            {"new": other_ticket, "original": effect["ticket_id"]},
        )
        connection.execute(
            text(
                "INSERT INTO outbox_events (event_id,aggregate_type,aggregate_id,"
                "aggregate_version,event_type,schema_version,payload,occurred_at,"
                "correlation_id,status,attempts,next_attempt_at) "
                "SELECT :new,aggregate_type,:ticket,aggregate_version,event_type,"
                "schema_version,payload,occurred_at,correlation_id,status,attempts,"
                "next_attempt_at FROM outbox_events WHERE event_id=:original"
            ),
            {"new": other_source, "ticket": other_ticket, "original": execution["source_event_id"]},
        )
        insert(
            connection,
            "automation_executions",
            {
                **execution,
                "id": other_execution,
                "ticket_id": other_ticket,
                "source_event_id": other_source,
            },
        )
    rejected(
        db_engine, "automation_effects", {**effect, "origin_execution_id": other_execution}, "23503"
    )
    with db_engine.begin() as connection:
        insert(connection, "automation_effects", effect)
        insert(
            connection,
            "ticket_work_items",
            {
                key: value
                for key, value in {
                    **effect,
                    "relation_type": "related",
                    "created_by": seeded_user,
                }.items()
                if key not in {"rule_id", "action_id", "origin_execution_id", "mode"}
            },
        )
        connection.execute(text("DELETE FROM ticket_work_items"))
        assert connection.scalar(text("SELECT count(*) FROM automation_effects")) == 1
    rejected(db_engine, "automation_effects", effect, "23505")
    for table, column, identifier in (
        ("automation_rules", "id", effect["rule_id"]),
        ("automation_executions", "id", execution["id"]),
        ("work_items", "id", effect["work_item_id"]),
    ):
        with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
            connection.execute(text(f"DELETE FROM {table} WHERE {column}=:id"), {"id": identifier})
        assert caught.value.orig.sqlstate == "23503"


def test_ledger_api_columns_and_no_premature_worker_writer(db_engine, ledger):
    from altvia.provision import provision_runtime

    api = runtime_url(db_engine)
    worker = api.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        api.render_as_string(hide_password=False),
        worker.render_as_string(hide_password=False),
    )
    for url, denied in (
        (
            api,
            [
                "UPDATE automation_rules SET action_id=action_id",
                "UPDATE automation_rule_revisions SET title=title",
                "DELETE FROM automation_rules",
                "UPDATE automation_executions SET ticket_id=ticket_id",
                "INSERT INTO automation_effects SELECT * FROM automation_effects",
                "DELETE FROM automation_effects",
            ],
        ),
        (worker, [f"SELECT * FROM {table}" for table in sorted(TABLES)]),
    ):
        engine = create_engine(url, hide_parameters=True)
        try:
            for statement in denied:
                with pytest.raises(DBAPIError) as caught, engine.begin() as connection:
                    connection.execute(text(statement))
                assert caught.value.orig.sqlstate == "42501"
            if url == api:
                with engine.begin() as connection:
                    connection.execute(text("UPDATE automation_rules SET version=version+1"))
                    assert (
                        connection.scalar(text("SELECT count(*) FROM automation_executions")) == 1
                    )
        finally:
            engine.dispose()


def test_ledger_populated_downgrade_refuses_and_preserves(db_engine, ledger):
    config = Config("apps/api/alembic.ini")
    with pytest.raises(DBAPIError, match="Cannot contract assignment automation"):
        command.downgrade(config, "b46087000028")
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM automation_rules")) == 1
        assert connection.scalar(text("SELECT count(*) FROM automation_executions")) == 1


@pytest.mark.parametrize(
    "history",
    ["outbox", "audit", "activity", "create_receipt", "patch_receipt", "retry_receipt"],
)
def test_empty_ledger_downgrade_retains_automation_history(db_engine, seeded_user, history):
    now = datetime.now(UTC)
    with Session(db_engine) as db, db.begin():
        event = OutboxEvent(
            event_type="automation.rule_created",
            aggregate_type="automation_rule",
            aggregate_id=uuid4(),
            aggregate_version=1,
            schema_version=1,
            payload={},
            occurred_at=now,
            correlation_id="migration-history",
            status="pending",
            attempts=0,
            next_attempt_at=now,
        )
        db.add(event)
        db.flush()
        if history.endswith("_receipt"):
            db.delete(event)
            route = {
                "create_receipt": "automation-rule-create:",
                "patch_receipt": "automation-rule-patch:",
                "retry_receipt": "automation-retry:",
            }[history]
            db.add(
                IdempotencyRecord(
                    actor_id=seeded_user,
                    route=route + str(uuid4()),
                    key=uuid4().hex,
                    request_hash="a" * 64,
                    status_code=200,
                    result={},
                    created_at=now,
                    expires_at=now + timedelta(days=7),
                )
            )
        elif history == "audit":
            db.delete(event)
            db.add(
                AuditLog(
                    actor_id=seeded_user,
                    action="automation.rule_created",
                    resource_id=uuid4(),
                    occurred_at=now,
                    correlation_id="migration-history",
                    details={},
                )
            )
        elif history == "activity":
            event.event_type = "work_item.created"
            event.aggregate_type = "work_item"
            event.schema_version = 2
            db.add(
                ActivityEvent(
                    event_id=event.event_id,
                    resource_type="work_item",
                    resource_id=event.aggregate_id,
                    event_type="work_item.created",
                    actor_id=None,
                    actor_kind="automation",
                    aggregate_version=1,
                    occurred_at=now,
                    correlation_id="migration-history",
                    details={"authorizer_id": str(seeded_user)},
                )
            )
    with pytest.raises(DBAPIError, match="Cannot contract assignment automation"):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000028")


def test_ledger_empty_roundtrip_preserves_native_schema_and_no_enabled_rules(
    db_engine, seeded_user
):
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000028")
    assert not TABLES.intersection(inspect(db_engine).get_table_names())
    command.upgrade(config, "head")
    command.check(config)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM automation_rules")) == 0
        assert (
            connection.scalar(text("SELECT count(*) FROM users WHERE id=:id"), {"id": seeded_user})
            == 1
        )
