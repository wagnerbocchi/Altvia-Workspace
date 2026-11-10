from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in
from test_work_items import create_work, setup_project

__all__ = ["admin_client"]


def test_work_storage_exists_before_invariants(db_engine, seeded_user):
    assert {
        "work_items",
        "work_item_assignees",
        "work_item_comments",
        "work_item_status_history",
    } <= set(inspect(db_engine).get_table_names())


def test_raw_concurrent_parent_changes_cannot_create_cycle(admin_client, seeded_user, db_engine):
    project_id = setup_project(admin_client, seeded_user)
    identifiers = [create_work(admin_client, project_id).json()["work_item_id"] for _ in range(2)]
    start = Barrier(2)

    def change(pair):
        try:
            with db_engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout='5s'"))
                # Both transactions hold their own row before competing for the
                # project graph lock; this guarantees actual overlapping writes.
                connection.execute(
                    text("SELECT id FROM work_items WHERE id=:id FOR UPDATE"),
                    {"id": UUID(pair[0])},
                )
                start.wait(timeout=5)
                connection.execute(
                    text("UPDATE work_items SET parent_id=:parent WHERE id=:id"),
                    {"parent": UUID(pair[1]), "id": UUID(pair[0])},
                )
            return "committed"
        except DBAPIError as error:
            assert error.orig.sqlstate in {"23514", "40P01"}
            return "refused"

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(change, [identifiers, list(reversed(identifiers))]))
    assert sorted(results) == ["committed", "refused"]
    with Session(db_engine) as db:
        from altvia.models import WorkItem

        rows = list(db.scalars(select(WorkItem)))
        assert sum(row.parent_id is not None for row in rows) == 1


def test_history_and_comments_are_append_only_and_downgrade_refuses(
    admin_client, seeded_user, db_engine
):
    project_id = setup_project(admin_client, seeded_user)
    assert create_work(admin_client, project_id).status_code == 201
    with pytest.raises(DBAPIError, match="append-only"), db_engine.begin() as connection:
        connection.execute(text("UPDATE work_item_status_history SET to_status='done'"))
    config = Config("apps/api/alembic.ini")
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable work data exists"):
        command.downgrade(config, "b46087000007")
    command.check(config)


def test_raw_cross_project_parent_fk_for_insert_and_update(admin_client, seeded_user, db_engine):
    first = setup_project(admin_client, seeded_user)
    parent = create_work(admin_client, first).json()["work_item_id"]
    sign_in(admin_client, "admin@example.test")
    second = setup_project(admin_client, seeded_user)
    child = create_work(admin_client, second).json()["work_item_id"]
    for statement in (
        "UPDATE work_items SET parent_id=:parent WHERE id=:child",
        "INSERT INTO work_items (id,project_id,parent_id,title,description,status,work_type,"
        "priority,version) VALUES (:new,:project,:parent,'Raw','','todo','one_off','low',1)",
    ):
        with pytest.raises(DBAPIError) as caught, db_engine.begin() as connection:
            connection.execute(
                text(statement),
                {
                    "parent": UUID(parent),
                    "child": UUID(child),
                    "new": uuid4(),
                    "project": UUID(second),
                },
            )
        assert caught.value.orig.sqlstate == "23503"
        assert caught.value.orig.diag.constraint_name == "fk_work_parent_project"


@pytest.mark.parametrize("table", ["work_item_comments", "work_item_status_history"])
@pytest.mark.parametrize("operation", ["update", "delete"])
def test_raw_work_history_rewrite_is_denied(admin_client, seeded_user, db_engine, table, operation):
    project_id = setup_project(admin_client, seeded_user)
    identifier = create_work(admin_client, project_id).json()["work_item_id"]
    response = admin_client.post(
        f"/api/v1/work-items/{identifier}/comments",
        json={"body": "Durable"},
        headers=preconditions(),
    )
    assert response.status_code == 201
    statement = f"DELETE FROM {table}" if operation == "delete" else f"UPDATE {table} SET id=id"
    with pytest.raises(DBAPIError, match="append-only") as caught, db_engine.begin() as connection:
        connection.execute(text(statement))
    assert caught.value.orig.sqlstate == "42501"


def test_raw_incomplete_deadline_is_refused(admin_client, seeded_user, db_engine):
    project_id = setup_project(admin_client, seeded_user)
    assert create_work(admin_client, project_id).status_code == 201
    with pytest.raises(DBAPIError), db_engine.begin() as connection:
        connection.execute(text("UPDATE work_items SET due_at=now(),due_precision=NULL"))


@pytest.mark.parametrize(
    "event_type,extra",
    [
        ("work_item.created", {"title": "Must not project"}),
        ("work_item.assigned", {"changed_fields": "description"}),
        ("work_item.completed", {"from_status": "blocked", "to_status": "done"}),
        ("work_item.status_changed", {"from_status": "todo", "to_status": "done"}),
    ],
)
def test_work_worker_rejects_mismatched_event_semantics(db_engine, seeded_user, event_type, extra):
    from datetime import UTC, datetime
    from uuid import uuid4

    from altvia.activity import consume_event
    from altvia.models import OutboxEvent

    now = datetime.now(UTC)
    with Session(db_engine) as db, db.begin():
        row = OutboxEvent(
            aggregate_type="work_item",
            aggregate_id=uuid4(),
            aggregate_version=1,
            event_type=event_type,
            schema_version=1,
            payload={
                "actor_id": None,
                "actor_kind": "management_command",
                "project_id": str(uuid4()),
                **extra,
            },
            occurred_at=now,
            next_attempt_at=now,
            correlation_id=uuid4().hex,
        )
        db.add(row)
        db.flush()
        identifier = row.event_id
    assert not consume_event(db_engine, identifier, now)
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, identifier).last_error_code == "invalid_event"
