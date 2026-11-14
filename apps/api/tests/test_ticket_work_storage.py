"""Native relationship constraints, least privilege and safe contraction."""

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from altvia.models import (
    ActivityEvent,
    AuditLog,
    Client,
    IdempotencyRecord,
    OutboxEvent,
    Project,
    TicketQueue,
    WorkItem,
)
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_runtime_provision import runtime_url
from test_team_api import admin_client
from ticket_work_support import make_link_context

__all__ = ["admin_client"]

INSERT = text(
    "INSERT INTO ticket_work_items "
    "(ticket_id,work_item_id,client_id,queue_id,project_id,relation_type,created_by) "
    "VALUES (:ticket_id,:work_item_id,:client_id,:queue_id,:project_id,:relation_type,:created_by)"
)
EVENTS = (
    "ticket.work_linked",
    "ticket.work_unlinked",
    "work_item.ticket_linked",
    "work_item.ticket_unlinked",
)
PARENT_GRANTS = text(
    "SELECT grantee,table_name,privilege_type FROM information_schema.table_privileges "
    # These descendants are recreated above28, not incumbent parent tables.
    "WHERE table_schema='public' AND table_name NOT IN ('ticket_work_items',"
    "'automation_rules','automation_rule_revisions','automation_executions','automation_effects',"
    "'automation_assignment_sources') "
    "ORDER BY grantee,table_name,privilege_type"
)


def values(context, actor):
    return {**asdict(context), "relation_type": "related", "created_by": actor}


def alternatives(db_engine, context):
    """Existing foreign identities, including an internal project with real work."""
    with Session(db_engine) as db, db.begin():
        team_id = db.get(TicketQueue, context.queue_id).team_id
        now = datetime.now(UTC)
        customer = Client(name="Other client", created_at=now, updated_at=now)
        queue = TicketQueue(team_id=team_id, name="Other queue")
        db.add_all([customer, queue])
        db.flush()
        foreign = Project(
            name="Other project", scope_kind="client", client_id=customer.id, team_id=team_id
        )
        internal = Project(name="Internal", scope_kind="internal", team_id=team_id)
        db.add_all([foreign, internal])
        db.flush()
        foreign_work = WorkItem(project_id=foreign.id, title="Other work")
        internal_work = WorkItem(project_id=internal.id, title="Internal work")
        db.add_all([foreign_work, internal_work])
        db.flush()
        return customer.id, queue.id, foreign.id, foreign_work.id, internal.id, internal_work.id


def test_native_ticket_work_same_client_and_null_guard(admin_client, db_engine, seeded_user):
    # Missing FKs/NOT NULL must permit neither a forged INSERT nor owner UPDATE.
    context = make_link_context(admin_client, db_engine, seeded_user)
    customer, queue, foreign, foreign_work, internal, internal_work = alternatives(
        db_engine, context
    )
    original = values(context, seeded_user)
    invalid = [
        ({"ticket_id": uuid4()}, "23503"),
        ({"queue_id": queue}, "23503"),
        ({"client_id": customer}, "23503"),
        ({"project_id": foreign}, "23503"),
        ({"work_item_id": foreign_work}, "23503"),
        ({"work_item_id": foreign_work, "project_id": foreign}, "23503"),
        ({"work_item_id": internal_work, "project_id": internal}, "23503"),
        ({"created_by": uuid4()}, "23503"),
        ({"relation_type": "blocks"}, "23514"),
        *[({column: None}, "23502") for column in original],
    ]
    for changes, sqlstate in invalid:
        with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
            connection.execute(INSERT, {**original, **changes})
        assert caught.value.orig.sqlstate == sqlstate
        with db_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM ticket_work_items")) == 0
    with db_engine.begin() as connection:
        connection.execute(INSERT, original)
    for changes, sqlstate in invalid:
        assignments = ",".join(f"{column}=:{column}" for column in changes)
        with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
            connection.execute(text(f"UPDATE ticket_work_items SET {assignments}"), changes)
        assert caught.value.orig.sqlstate == sqlstate
    from altvia.models import TicketWorkItem

    with Session(db_engine) as db:
        row = db.get(TicketWorkItem, (context.ticket_id, context.work_item_id))
        assert row is not None
        assert row.client_id == context.client_id and row.project_id == context.project_id
        assert row.created_by == seeded_user and row.relation_type == "related"
        assert row.created_at.utcoffset() == timedelta(0)


def test_ticket_work_pair_unique_and_parent_key_restricted(admin_client, db_engine, seeded_user):
    context = make_link_context(admin_client, db_engine, seeded_user)
    customer, queue, _, _, _, _ = alternatives(db_engine, context)
    # No older history FK on this owner-created work can mask the new composite FK.
    with Session(db_engine) as db, db.begin():
        work = WorkItem(project_id=context.project_id, title="Raw linked work")
        db.add(work)
        db.flush()
        context = replace(context, work_item_id=work.id)
    with db_engine.begin() as connection:
        connection.execute(INSERT, values(context, seeded_user))
    with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
        connection.execute(INSERT, values(context, seeded_user))
    assert caught.value.orig.sqlstate == "23505"
    for statement, params, constraint in (
        (
            "UPDATE tickets SET queue_id=:queue,category_id=NULL WHERE id=:id",
            {"queue": queue, "id": context.ticket_id},
            "fk_ticket_work_ticket_context",
        ),
        (
            "UPDATE work_items SET id=:new WHERE id=:id",
            {"new": uuid4(), "id": context.work_item_id},
            "fk_ticket_work_work_project",
        ),
        (
            "UPDATE projects SET client_id=:client WHERE id=:id",
            {"client": customer, "id": context.project_id},
            "fk_ticket_work_project_client",
        ),
        ("DELETE FROM tickets WHERE id=:id", {"id": context.ticket_id}, None),
        ("DELETE FROM work_items WHERE id=:id", {"id": context.work_item_id}, None),
        ("DELETE FROM projects WHERE id=:id", {"id": context.project_id}, None),
    ):
        with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
            connection.execute(text(statement), params)
        assert caught.value.orig.sqlstate == "23503"
        if constraint:
            assert caught.value.orig.diag.constraint_name == constraint
    config = Config("apps/api/alembic.ini")
    with pytest.raises(DBAPIError, match="Cannot contract ticket/work links/history"):
        command.downgrade(config, "b46087000027")
    indexes = inspect(db_engine).get_indexes("ticket_work_items")
    assert any(index["column_names"] == ["work_item_id", "ticket_id"] for index in indexes)
    for foreign_key in inspect(db_engine).get_foreign_keys("ticket_work_items"):
        assert foreign_key["options"] == {"onupdate": "RESTRICT", "ondelete": "RESTRICT"}


def test_ticket_work_runtime_privileges(admin_client, db_engine, seeded_user):
    from altvia.provision import provision_runtime

    context = make_link_context(admin_client, db_engine, seeded_user)
    api_url = runtime_url(db_engine)
    worker_url = runtime_url(db_engine).set(username="altvia_worker")
    provision_runtime(
        db_engine,
        api_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    for url in (api_url, worker_url):
        engine = create_engine(url, hide_parameters=True)
        try:
            with engine.connect() as connection:
                assert not connection.scalar(
                    text(
                        "SELECT has_any_column_privilege(current_user,'ticket_work_items','UPDATE')"
                    )
                )
                if url == worker_url:
                    # Assignment execution is now a real native second writer;
                    # grant reads/inserts, never arbitrary mutation or removal.
                    assert connection.scalar(
                        text(
                            "SELECT has_any_column_privilege("
                            "current_user,'ticket_work_items','SELECT')"
                        )
                    )
            if url == api_url:
                with engine.begin() as connection:
                    connection.execute(INSERT, values(context, seeded_user))
                    assert connection.scalar(text("SELECT count(*) FROM ticket_work_items")) == 1
                denied = [
                    "UPDATE ticket_work_items SET relation_type='related'",
                    "TRUNCATE ticket_work_items",
                ]
            else:
                with engine.begin() as connection:
                    connection.execute(INSERT, values(context, seeded_user))
                    assert connection.scalar(text("SELECT count(*) FROM ticket_work_items")) == 1
                denied = [
                    "UPDATE ticket_work_items SET relation_type='related'",
                    "DELETE FROM ticket_work_items",
                    "TRUNCATE ticket_work_items",
                ]
            for statement in denied:
                with pytest.raises(DBAPIError) as caught, engine.begin() as connection:
                    connection.execute(text(statement))
                assert caught.value.orig.sqlstate == "42501"
            if url == api_url:
                with engine.begin() as connection:
                    connection.execute(text("DELETE FROM ticket_work_items"))
                    assert connection.scalar(text("SELECT count(*) FROM ticket_work_items")) == 0
        finally:
            engine.dispose()


@pytest.mark.parametrize("history", ["outbox", "audit", "activity", "link", "unlink"])
@pytest.mark.parametrize("event_type", EVENTS)
def test_downgrade_refuses_unlinked_history_or_receipt(
    admin_client, db_engine, seeded_user, history, event_type
):
    # Every durable family/receipt must block contraction without any live join.
    context = make_link_context(admin_client, db_engine, seeded_user)
    with db_engine.begin() as connection:
        connection.execute(INSERT, values(context, seeded_user))
        connection.execute(text("DELETE FROM ticket_work_items"))
    now = datetime.now(UTC)
    resource_type = "ticket" if event_type.startswith("ticket.") else "work_item"
    resource_id = context.ticket_id if resource_type == "ticket" else context.work_item_id
    details = {key: str(value) for key, value in asdict(context).items()}
    details.update(relation_type="related", actor_kind="user", actor_id=str(seeded_user))
    with Session(db_engine) as db, db.begin():
        if history in {"outbox", "activity"}:
            event = OutboxEvent(
                aggregate_type=resource_type,
                aggregate_id=resource_id,
                aggregate_version=2,
                event_type=event_type if history == "outbox" else "ticket.created",
                schema_version=1,
                payload=details,
                occurred_at=now,
                next_attempt_at=now,
                correlation_id=uuid4().hex,
            )
            db.add(event)
            db.flush()
            if history == "activity":
                # Neutral outbox ensures this independently tests the activity guard.
                db.add(
                    ActivityEvent(
                        event_id=event.event_id,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        event_type=event_type,
                        occurred_at=now,
                        actor_id=seeded_user,
                        actor_kind="user",
                        aggregate_version=2,
                        correlation_id=event.correlation_id,
                        details=details,
                    )
                )
        elif history == "audit":
            db.add(
                AuditLog(
                    actor_id=seeded_user,
                    action=event_type,
                    resource_id=resource_id,
                    occurred_at=now,
                    correlation_id=uuid4().hex,
                    details=details,
                )
            )
        else:
            route = f"ticket-work-{history}:{context.ticket_id}"
            if history == "unlink":
                route += f":{context.work_item_id}"
            db.add(
                IdempotencyRecord(
                    actor_id=seeded_user,
                    route=route,
                    key=uuid4().hex,
                    request_hash="a" * 64,
                    status_code=201 if history == "link" else 204,
                    result={
                        "ticket_id": str(context.ticket_id),
                        "work_item_id": str(context.work_item_id),
                    },
                    created_at=now,
                    expires_at=now + timedelta(days=7),
                )
            )
    config = Config("apps/api/alembic.ini")
    with pytest.raises(DBAPIError, match="Cannot contract ticket/work links/history"):
        command.downgrade(config, "b46087000027")
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            ScriptDirectory.from_config(config).get_current_head()
        )


def test_empty_roundtrip_preserves_existing_parent_keys(admin_client, db_engine, seeded_user):
    context = make_link_context(admin_client, db_engine, seeded_user)
    inspector = inspect(db_engine)
    tables = inspector.get_table_names()
    parents = ("projects", "work_items", "tickets")
    keys = {table: inspector.get_unique_constraints(table) for table in parents}
    with db_engine.connect() as connection:
        counts = {
            table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables
        }
        grants = list(connection.execute(PARENT_GRANTS))
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000027")
    assert "ticket_work_items" not in inspect(db_engine).get_table_names()
    command.upgrade(config, "head")
    for table in parents:
        assert inspect(db_engine).get_unique_constraints(table) == keys[table]
    with db_engine.connect() as connection:
        assert {
            table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables
        } == counts
        assert list(connection.execute(PARENT_GRANTS)) == grants
        assert (
            connection.scalar(
                text("SELECT id FROM tickets WHERE id=:id"), {"id": context.ticket_id}
            )
            == context.ticket_id
        )
    command.check(config)
