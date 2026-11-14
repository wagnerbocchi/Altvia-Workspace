"""Real versioned calendar/policy storage and least-privilege boundaries."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from altvia import management, models, provision
from altvia.business_time import freeze_timezone
from conftest import TEST_PASSWORD
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_automation_rules import rule_context
from test_runtime_provision import runtime_url
from test_team_api import admin_client

__all__ = ["admin_client", "rule_context"]

TABLES = {
    "business_calendars",
    "business_calendar_revisions",
    "sla_policies",
    "sla_policy_revisions",
}


def test_sla_configuration_has_native_persistent_tables(db_engine):
    with db_engine.connect() as connection:
        actual = {
            name
            for name in TABLES
            if connection.scalar(text("SELECT to_regclass(:name)"), {"name": "public." + name})
        }
    assert actual == TABLES


def insert(connection, model, values):
    connection.execute(getattr(models, model).__table__.insert(), values)


@pytest.fixture
def storage(db_engine, rule_context, seeded_user):
    zone = freeze_timezone("UTC")
    with Session(db_engine) as db, db.begin():
        parent = db.get(models.TicketQueue, UUID(rule_context["queue_id"]))
        now = datetime.now(UTC)
        other_client = models.Client(
            name="Another synthetic SLA customer", created_at=now, updated_at=now
        )
        other_queue = models.TicketQueue(team_id=parent.team_id, name="Another synthetic SLA queue")
        db.add_all([other_client, other_queue])
        db.flush()
        foreign_category = models.TicketCategory(queue_id=other_queue.id, name="Other category")
        db.add(foreign_category)
        db.flush()
        foreign = (other_client.id, other_queue.id, foreign_category.id)
    calendar = {
        "id": uuid4(),
        "client_id": UUID(rule_context["client_id"]),
        "queue_id": UUID(rule_context["queue_id"]),
        "version": 1,
    }
    revision = {
        "calendar_id": calendar["id"],
        "version": 1,
        "client_id": calendar["client_id"],
        "queue_id": calendar["queue_id"],
        "active": True,
        "name": "Synthetic calendar",
        "timezone": zone.name,
        "windows": [{"weekday": 0, "start_minute": 540, "end_minute": 1020}],
        "holidays": [{"date": "2026-11-10", "label": "Synthetic holiday"}],
        "tzif": zone.tzif,
        "tzif_sha256": zone.sha256,
    }
    policy = {
        "id": uuid4(),
        "client_id": calendar["client_id"],
        "queue_id": calendar["queue_id"],
        "category_id": None,
        "priority": None,
        "version": 1,
    }
    policy_revision = {
        "policy_id": policy["id"],
        "version": 1,
        "client_id": policy["client_id"],
        "queue_id": policy["queue_id"],
        "enabled": False,
        "name": "Synthetic policy",
        "calendar_id": calendar["id"],
        "calendar_version": 1,
        "first_response_minutes": 60,
        "resolution_minutes": 240,
        "approach_minutes": 15,
        "pause_states": ["pending_customer"],
        "authorizer_id": seeded_user,
    }
    with db_engine.begin() as connection:
        insert(connection, "BusinessCalendar", calendar)
        insert(connection, "BusinessCalendarRevision", revision)
        insert(connection, "SlaPolicy", policy)
        insert(connection, "SlaPolicyRevision", policy_revision)
    return calendar, revision, policy, policy_revision, foreign


def reject(engine, model, values, state):
    with engine.begin() as connection, pytest.raises(DBAPIError) as caught:
        insert(connection, model, values)
    assert caught.value.orig.sqlstate == state


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("windows", []),
        ("windows", {}),
        ("windows", [{"weekday": True, "start_minute": 540, "end_minute": 600}]),
        ("windows", [{"weekday": 0.5, "start_minute": 540, "end_minute": 600}]),
        ("windows", [{"weekday": 7, "start_minute": 540, "end_minute": 600}]),
        ("windows", [{"weekday": 0, "start_minute": 600, "end_minute": 600}]),
        ("windows", [{"weekday": 0, "start_minute": 0, "end_minute": 1441}]),
        ("windows", [{"weekday": 0, "start_minute": 0, "end_minute": 60, "code": "forbidden"}]),
        ("windows", [{"weekday": 0, "start_minute": 0, "end_minute": 60}] * 2),
        (
            "windows",
            [
                {"weekday": 0, "start_minute": 0, "end_minute": 60},
                {"weekday": 0, "start_minute": 60, "end_minute": 120},
            ],
        ),
        ("holidays", [{"date": "2026-02-30", "label": None}]),
        ("holidays", [{"date": "2026-11-10", "label": " \t"}]),
        ("holidays", [{"date": "2026-11-10T00:00:00Z"}]),
        ("holidays", [{"date": "2026-11-10", "extra": True}]),
        ("holidays", [{"date": "2026-11-10"}] * 2),
        ("holidays", [{"date": "2026-11-11"}, {"date": "2026-11-10"}]),
        ("tzif_sha256", "0" * 64),
        ("name", " \t"),
        ("name", "Two\nlines"),
    ],
)
def test_native_calendar_rejects_invalid_snapshot_shapes(db_engine, storage, field, value):
    revision = {**storage[1], "version": 2, field: value}
    reject(db_engine, "BusinessCalendarRevision", revision, "23514")


def test_native_calendar_enforces_nested_collection_and_artifact_bounds(db_engine, storage):
    original = storage[1]
    holidays = [
        {"date": (datetime(2020, 1, 1) + timedelta(days=n)).date().isoformat()} for n in range(1001)
    ]
    windows = [
        {"weekday": n // 24, "start_minute": n % 24 * 60, "end_minute": n % 24 * 60 + 30}
        for n in range(29)
    ]
    for changes in [{"holidays": holidays}, {"windows": windows}, {"tzif": b"x" * 262145}]:
        reject(
            db_engine, "BusinessCalendarRevision", {**original, "version": 2, **changes}, "23514"
        )


def test_native_policy_binds_customer_queue_calendar_category_and_null_selector(db_engine, storage):
    calendar, revision, policy, policy_revision, foreign = storage
    reject(db_engine, "SlaPolicy", {**policy, "id": uuid4()}, "23505")
    reject(db_engine, "SlaPolicy", {**policy, "id": uuid4(), "category_id": foreign[2]}, "23503")
    reject(
        db_engine,
        "BusinessCalendarRevision",
        {**revision, "version": 2, "client_id": foreign[0]},
        "23503",
    )
    other_calendar = {**calendar, "id": uuid4(), "client_id": foreign[0], "queue_id": foreign[1]}
    with db_engine.begin() as connection:
        insert(connection, "BusinessCalendar", other_calendar)
        insert(
            connection,
            "BusinessCalendarRevision",
            {
                **revision,
                "calendar_id": other_calendar["id"],
                "client_id": foreign[0],
                "queue_id": foreign[1],
            },
        )
    reject(
        db_engine,
        "SlaPolicyRevision",
        {**policy_revision, "version": 2, "calendar_id": other_calendar["id"]},
        "23503",
    )
    reject(
        db_engine,
        "SlaPolicyRevision",
        {**policy_revision, "version": 2, "calendar_version": 2},
        "23503",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("first_response_minutes", 0),
        ("resolution_minutes", 525601),
        ("approach_minutes", -1),
        ("pause_states", ["open"]),
        ("pause_states", [None]),
        ("pause_states", ["pending_customer", "pending_customer"]),
        ("pause_states", ["pending_customer", "pending_third_party", "pending_customer"]),
    ],
)
def test_native_policy_enforces_finite_targets_and_pause_states(db_engine, storage, field, value):
    reject(db_engine, "SlaPolicyRevision", {**storage[3], "version": 2, field: value}, "23514")


@pytest.mark.parametrize(
    "pause_states", [[], ["pending_third_party"], ["pending_customer", "pending_third_party"]]
)
def test_native_policy_accepts_explicit_pause_choices_and_maximum_targets(
    db_engine, storage, pause_states
):
    with db_engine.begin() as connection:
        insert(connection, "BusinessCalendarRevision", {**storage[1], "version": 2, "holidays": []})
        insert(
            connection,
            "SlaPolicyRevision",
            {
                **storage[3],
                "version": 2,
                "calendar_version": 2,
                "first_response_minutes": 525600,
                "resolution_minutes": 1,
                "approach_minutes": 525600,
                "pause_states": pause_states,
            },
        )
        assert (
            connection.scalar(text("SELECT pause_states FROM sla_policy_revisions WHERE version=2"))
            == pause_states
        )


def test_actual_roles_allow_configuration_insert_but_not_snapshot_or_scope_mutation(
    db_engine, storage
):
    app_url = runtime_url(db_engine)
    worker_url = runtime_url(db_engine).set(username="altvia_worker")
    provision.provision_runtime(
        db_engine,
        app_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    app = create_engine(app_url, hide_parameters=True)
    worker = create_engine(worker_url, hide_parameters=True)
    try:
        with app.begin() as connection:
            assert connection.scalar(text("SELECT current_user")) == "altvia_app"
            insert(connection, "BusinessCalendarRevision", {**storage[1], "version": 2})
            connection.execute(
                text("UPDATE business_calendars SET version=2 WHERE id=:id"),
                {"id": storage[0]["id"]},
            )
        denied = [
            "UPDATE business_calendar_revisions SET active=false",
            "UPDATE business_calendar_revisions SET holidays='[]'",
            "UPDATE business_calendars SET client_id=client_id",
            "UPDATE sla_policies SET priority=priority",
            "UPDATE sla_policy_revisions SET enabled=true",
            *(f"DELETE FROM {table}" for table in sorted(TABLES)),
        ]
        for statement in denied:
            with app.begin() as connection, pytest.raises(DBAPIError) as caught:
                connection.execute(text(statement))
            assert caught.value.orig.sqlstate == "42501"
        readable = {"business_calendar_revisions", "sla_policy_revisions"}
        for table in sorted(TABLES):
            if table in readable:
                # Actual evaluator reads immutable snapshots, never identities or
                # configuration writes. Runtime-role Task3 tests prove its effect.
                with worker.connect() as connection:
                    assert connection.scalar(text(f"SELECT count(*) FROM {table}")) > 0
            else:
                with worker.begin() as connection, pytest.raises(DBAPIError) as caught:
                    connection.execute(text(f"SELECT * FROM {table}"))
                assert caught.value.orig.sqlstate == "42501"
            for verb in ("INSERT", "UPDATE", "DELETE"):
                with worker.connect() as connection:
                    assert not connection.scalar(
                        text(
                            "SELECT has_table_privilege(current_user,:table,:verb)"
                            if verb == "DELETE"
                            else "SELECT has_any_column_privilege(current_user,:table,:verb)"
                        ),
                        {"table": table, "verb": verb},
                    )
        for function in ["valid_business_calendar_windows", "valid_business_calendar_holidays"]:
            with worker.begin() as connection, pytest.raises(DBAPIError) as caught:
                connection.execute(text(f"SELECT public.{function}('[]'::jsonb)"))
            assert caught.value.orig.sqlstate == "42501"
    finally:
        app.dispose()
        worker.dispose()


def test_populated_configuration_downgrade_refuses_before_ddl(db_engine, storage):
    config = Config("apps/api/alembic.ini")
    with pytest.raises(DBAPIError, match="Cannot contract SLA configuration/history"):
        command.downgrade(config, "b46087000030")
    with db_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == ScriptDirectory.from_config(config).get_current_head()
        )
        assert connection.scalar(text("SELECT count(*) FROM business_calendar_revisions")) == 1


@pytest.mark.parametrize(
    "table", ["outbox_events", "audit_logs", "activity_events", "idempotency_records"]
)
def test_configuration_history_alone_prevents_contraction(db_engine, seeded_user, table):
    now, identifier = datetime.now(UTC), uuid4()
    with Session(db_engine) as db, db.begin():
        if table == "outbox_events":
            db.add(
                models.OutboxEvent(
                    aggregate_type="business_calendar",
                    aggregate_id=identifier,
                    aggregate_version=1,
                    event_type="business_calendar.created",
                    schema_version=1,
                    payload={},
                    occurred_at=now,
                    correlation_id="sla_history",
                    next_attempt_at=now,
                )
            )
        elif table == "audit_logs":
            db.add(
                models.AuditLog(
                    actor_id=seeded_user,
                    action="sla_policy.created",
                    resource_id=identifier,
                    occurred_at=now,
                    correlation_id="sla_history",
                    details={},
                )
            )
        elif table == "activity_events":
            source = models.OutboxEvent(
                aggregate_type="identity",
                aggregate_id=identifier,
                aggregate_version=1,
                event_type="identity.user_created",
                schema_version=1,
                payload={},
                occurred_at=now,
                correlation_id="sla_history",
                next_attempt_at=now,
            )
            db.add(source)
            db.flush()
            db.add(
                models.ActivityEvent(
                    event_id=source.event_id,
                    resource_type="identity",
                    resource_id=identifier,
                    event_type="sla_policy.created",
                    aggregate_version=1,
                    actor_id=seeded_user,
                    actor_kind="user",
                    occurred_at=now,
                    correlation_id="sla_history",
                    details={},
                )
            )
        else:
            db.add(
                models.IdempotencyRecord(
                    actor_id=seeded_user,
                    route="sla-calendar-create:" + str(identifier),
                    key="retained",
                    request_hash="0" * 64,
                    status_code=201,
                    result={"calendar_id": str(identifier)},
                    created_at=now,
                    expires_at=now + timedelta(hours=168),
                )
            )
    with pytest.raises(DBAPIError, match="Cannot contract SLA configuration/history"):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000030")


def test_empty_configuration_roundtrip_and_native_metadata_check(db_engine, seeded_user):
    config = Config("apps/api/alembic.ini")
    with Session(db_engine) as db, db.begin():
        management.create_user(db, "legacy-sla@example.invalid", "Legacy identity", TEST_PASSWORD)
    with db_engine.connect() as connection:
        before = {
            table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in ("users", "audit_logs", "outbox_events")
        }
    command.downgrade(config, "b46087000030")
    command.upgrade(config, "head")
    command.check(config)
    with db_engine.connect() as connection:
        assert all(
            connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0 for table in TABLES
        )
        assert before == {
            table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in before
        }
