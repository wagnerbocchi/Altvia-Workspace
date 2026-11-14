"""Unified personal eligibility is resolved before deduplication and pagination."""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from uuid import UUID, uuid4

import pytest
from altvia import client_registry, identity
from altvia.main import create_app
from altvia.models import RoleBinding, Ticket, TicketQueue, User, WorkItem
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in
from test_work_items import create_work, setup_project
from ticket_work_support import make_link_context

__all__ = ["admin_client"]

PATH = "/api/v1/my-work/unified"


def test_openapi_requires_unified_domain_tags_without_changing_legacy(settings):
    # Generated clients must safely narrow every row without an untagged variant.
    schemas = create_app(settings).openapi()["components"]["schemas"]
    for name in ["UnifiedWorkItem", "UnifiedTicket"]:
        assert "kind" in schemas[name]["required"]
    assert {"linked_tickets", "has_more_linked_tickets"} <= set(
        schemas["UnifiedWorkItem"]["required"]
    )
    assert "kind" not in schemas["MyWorkItem"]["required"]
    item = schemas["UnifiedWorkPage"]["properties"]["items"]["items"]
    assert item["discriminator"]["propertyName"] == "kind"


def listing(client, **params):
    response = client.get(PATH, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def keys(page):
    return [(row["kind"], row["id"]) for row in page["items"]]


def all_pages(client, **params):
    result, cursors = [], set()
    cursor = None
    for _ in range(30):
        page = listing(client, **params, **({"cursor": cursor} if cursor else {}))
        result.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return result
        assert cursor not in cursors
        cursors.add(cursor)
    pytest.fail("Unbounded personal queue")


def connect(client, ticket, work):
    ticket_path, work_path = f"/api/v1/tickets/{ticket}", f"/api/v1/work-items/{work}"
    ticket_version = client.get(ticket_path).json()["version"]
    work_version = client.get(work_path).json()["version"]
    response = client.post(
        ticket_path + "/work-items",
        json={"work_item_id": str(work)},
        headers={**preconditions(ticket_version), "If-Match-Work-Item": f'"{work_version}"'},
    )
    assert response.status_code == 201, response.text


def another_ticket(client, engine, context, **changes):
    with Session(engine) as db:
        row = db.get(Ticket, context.ticket_id)
        body = {
            "client_id": str(row.client_id),
            "queue_id": str(row.queue_id),
            "requester_id": str(row.requester_id),
            "subject": "Outro chamado",
            "priority": "high",
            **changes,
        }
    response = client.post("/api/v1/tickets", json=body, headers=preconditions())
    assert response.status_code == 201, response.text
    return UUID(response.json()["ticket_id"])


def another_work(client, context, user, **changes):
    response = create_work(client, str(context.project_id), owner_id=str(user), **changes)
    assert response.status_code == 201, response.text
    return UUID(response.json()["work_item_id"])


def personal_pair(client, engine, user):
    context = make_link_context(client, engine, user)
    for path, body in (
        (f"/api/v1/tickets/{context.ticket_id}", {"assignee_id": str(user)}),
        (
            f"/api/v1/work-items/{context.work_item_id}",
            {"owner_id": str(user), "assignee_ids": [str(user)]},
        ),
    ):
        response = client.patch(path, json=body, headers=preconditions())
        assert response.status_code == 200, response.text
    return context


def test_personal_union_reuses_full_authorized_work_set(admin_client, db_engine, seeded_user):
    context = personal_pair(admin_client, db_engine, seeded_user)
    legacy = admin_client.get("/api/v1/my-work")
    assert legacy.status_code == 200
    assert [row["id"] for row in legacy.json()["items"]] == [str(context.work_item_id)]
    page = admin_client.get("/api/v1/my-work/unified", params={"limit": 1})
    assert page.status_code == 200, page.text
    assert page.json()["items"][0]["kind"] == "ticket"  # High before medium.
    next_page = admin_client.get(
        "/api/v1/my-work/unified", params={"cursor": page.json()["next_cursor"], "limit": 1}
    )
    assert next_page.status_code == 200
    assert [(row["kind"], row["id"]) for row in next_page.json()["items"]] == [
        ("work_item", str(context.work_item_id))
    ]
    assert next_page.json()["next_cursor"] is None

    linked = admin_client.post(
        f"/api/v1/tickets/{context.ticket_id}/work-items",
        json={"work_item_id": str(context.work_item_id)},
        headers={**preconditions(2), "If-Match-Work-Item": '"2"'},
    )
    assert linked.status_code == 201, linked.text
    page = admin_client.get("/api/v1/my-work/unified", params={"limit": 1})
    assert page.status_code == 200
    assert [(row["kind"], row["id"]) for row in page.json()["items"]] == [
        ("work_item", str(context.work_item_id))
    ]
    assert page.json()["next_cursor"] is None
    assert [row["id"] for row in page.json()["items"][0]["linked_tickets"]] == [
        str(context.ticket_id)
    ]
    assert page.json()["items"][0]["has_more_linked_tickets"] is False
    assert admin_client.get("/api/v1/my-work").json()["items"] == legacy.json()["items"]


def test_linked_work_beyond_first_page_suppresses_ticket_before_paging(
    admin_client, db_engine, seeded_user
):
    context = personal_pair(admin_client, db_engine, seeded_user)
    response = admin_client.patch(
        f"/api/v1/work-items/{context.work_item_id}",
        json={"priority": "low"},
        headers=preconditions(2),
    )
    assert response.status_code == 200
    urgent = another_work(admin_client, context, seeded_user, priority="critical")
    connect(admin_client, context.ticket_id, context.work_item_id)
    rows = all_pages(admin_client, limit=1)
    assert [(row["kind"], row["id"]) for row in rows] == [
        ("work_item", str(urgent)),
        ("work_item", str(context.work_item_id)),
    ]
    assert rows[1]["linked_tickets"][0]["id"] == str(context.ticket_id)


def test_many_to_many_preserves_distinct_tasks_and_shared_origins(
    admin_client, db_engine, seeded_user
):
    context = personal_pair(admin_client, db_engine, seeded_user)
    other_work = another_work(admin_client, context, seeded_user)
    other_ticket = another_ticket(admin_client, db_engine, context, assignee_id=str(seeded_user))
    for ticket, work in [
        (context.ticket_id, context.work_item_id),
        (other_ticket, context.work_item_id),
        (context.ticket_id, other_work),
    ]:
        connect(admin_client, ticket, work)
    rows = all_pages(admin_client, limit=1)
    assert {row["id"] for row in rows} == {str(context.work_item_id), str(other_work)}
    assert len(rows) == 2 and all(row["kind"] == "work_item" for row in rows)
    badges = {row["id"]: [badge["id"] for badge in row["linked_tickets"]] for row in rows}
    assert badges[str(context.work_item_id)] == sorted([str(context.ticket_id), str(other_ticket)])
    assert badges[str(other_work)] == [str(context.ticket_id)]


def test_filters_are_domain_specific_and_can_restore_standalone_ticket(
    admin_client, db_engine, seeded_user
):
    context = personal_pair(admin_client, db_engine, seeded_user)
    connect(admin_client, context.ticket_id, context.work_item_id)
    work_key, ticket_key = (
        ("work_item", str(context.work_item_id)),
        ("ticket", str(context.ticket_id)),
    )
    for params, expected in [
        ({"work_status": "done"}, [ticket_key]),
        ({"ticket_status": "closed"}, [work_key]),
        ({"priority": "high"}, [ticket_key]),
        ({"priority": "medium"}, [work_key]),
        ({"kind": "ticket"}, [ticket_key]),
        ({"kind": "work_item"}, [work_key]),
        ({"q": "servidor"}, [ticket_key]),
        ({"q": "Task"}, [work_key]),
        ({"q": "de e a"}, []),
        ({"client_id": str(context.client_id)}, [work_key]),
        ({"client_id": str(uuid4())}, []),
        ({"team_id": str(uuid4())}, []),
    ]:
        page = listing(admin_client, **params)
        assert keys(page) == expected, params
        if expected == [work_key]:
            assert page["items"][0]["linked_tickets"][0]["id"] == str(context.ticket_id)


def test_distinct_domains_with_same_uuid_and_time_keep_both_cursor_rows(
    admin_client, db_engine, seeded_user
):
    context = personal_pair(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        ticket = db.get(Ticket, context.ticket_id)
        db.add(
            WorkItem(
                id=ticket.id,
                project_id=context.project_id,
                owner_id=seeded_user,
                title="Mesmo UUID",
                status="todo",
                priority=ticket.priority,
                work_type="one_off",
                created_at=ticket.created_at,
                updated_at=ticket.created_at,
            )
        )
    rows = all_pages(admin_client, limit=1)
    assert [(row["kind"], row["id"]) for row in rows] == [
        ("ticket", str(context.ticket_id)),
        ("work_item", str(context.ticket_id)),
        ("work_item", str(context.work_item_id)),
    ]


def test_badge_cap_and_more_ignore_hidden_fourth_queue(admin_client, db_engine, seeded_user):
    context = personal_pair(admin_client, db_engine, seeded_user)
    visible = [context.ticket_id] + [
        another_ticket(admin_client, db_engine, context) for _ in range(2)
    ]
    with Session(db_engine) as db:
        team = db.get(TicketQueue, context.queue_id).team_id
    sign_in(admin_client, "admin@example.test")
    created = admin_client.post(
        "/api/v1/ticket-queues",
        json={"team_id": str(team), "name": "Fila privada de origem"},
        headers=preconditions(),
    )
    assert created.status_code == 201
    queue = created.json()["queue_id"]
    queue_path = f"/api/v1/ticket-queues/{queue}"
    granted = admin_client.post(
        queue_path + "/members",
        json={"email": "employee@example.test", "role_name": "operations_manager"},
        headers=preconditions(),
    )
    assert granted.status_code == 201
    sign_in(admin_client, "employee@example.test")
    hidden = another_ticket(admin_client, db_engine, context, queue_id=queue)
    for ticket in [*visible, hidden]:
        connect(admin_client, ticket, context.work_item_id)
    page = listing(admin_client)
    assert keys(page) == [("work_item", str(context.work_item_id))]
    row = page["items"][0]
    assert [badge["id"] for badge in row["linked_tickets"]] == sorted(
        str(t) for t in [*visible, hidden]
    )[:3]
    assert row["has_more_linked_tickets"] is True
    old_session = admin_client.cookies.get(identity.COOKIE_NAME)
    sign_in(admin_client, "admin@example.test")
    version = admin_client.get(queue_path).json()["version"]
    revoked = admin_client.delete(
        queue_path + f"/members/{seeded_user}", headers=preconditions(version)
    )
    assert revoked.status_code == 204
    admin_client.cookies.clear()
    admin_client.cookies.set(identity.COOKIE_NAME, old_session)
    assert admin_client.get(PATH).status_code == 401
    admin_client.cookies.clear()
    sign_in(admin_client, "employee@example.test")
    page = listing(admin_client)
    row = page["items"][0]
    assert [badge["id"] for badge in row["linked_tickets"]] == sorted(str(t) for t in visible)
    assert row["has_more_linked_tickets"] is False
    assert str(hidden) not in str(page)


def test_hidden_project_does_not_suppress_ticket_after_native_revocation(
    admin_client, db_engine, seeded_user
):
    context = personal_pair(admin_client, db_engine, seeded_user)
    another_work(admin_client, context, seeded_user)
    connect(admin_client, context.ticket_id, context.work_item_id)
    first = listing(admin_client, limit=1)
    assert first["next_cursor"]
    # A legitimate direct-project observer can have a customer ceiling without
    # an inherited client metadata role. This fixture does not add a new grant API.
    with Session(db_engine) as db, db.begin():
        inherited = db.scalar(
            select(RoleBinding).where(
                RoleBinding.user_id == seeded_user,
                RoleBinding.scope_kind == "client",
                RoleBinding.client_id == context.client_id,
            )
        )
        assert inherited is not None
        db.delete(inherited)
    project_path = f"/api/v1/projects/{context.project_id}"
    version = admin_client.get(project_path).json()["version"]
    removed = admin_client.delete(
        project_path + f"/members/{seeded_user}", headers=preconditions(version)
    )
    assert removed.status_code == 204
    assert admin_client.get(PATH).status_code == 401
    sign_in(admin_client, "employee@example.test")
    continued = listing(admin_client, limit=1, cursor=first["next_cursor"])
    assert continued["items"] == [] and continued["next_cursor"] is None
    fresh = listing(admin_client)
    assert keys(fresh) == [("ticket", str(context.ticket_id))]
    assert str(context.work_item_id) not in str(fresh)
    assert admin_client.get("/api/v1/my-work").json()["items"] == []


def test_different_assignees_do_not_suppress_another_persons_ticket(
    admin_client, db_engine, seeded_user
):
    context = personal_pair(admin_client, db_engine, seeded_user)
    project_path = f"/api/v1/projects/{context.project_id}"
    version = admin_client.get(project_path).json()["version"]
    added = admin_client.post(
        project_path + "/members",
        json={"email": "agent@example.test", "role_name": "agent"},
        headers=preconditions(version),
    )
    assert added.status_code == 201
    with Session(db_engine) as db:
        agent = db.scalar(select(User.id).where(User.email_normalized == "agent@example.test"))
    changed = admin_client.patch(
        f"/api/v1/work-items/{context.work_item_id}",
        json={"owner_id": str(agent), "assignee_ids": []},
        headers=preconditions(2),
    )
    assert changed.status_code == 200
    connect(admin_client, context.ticket_id, context.work_item_id)
    assert keys(listing(admin_client)) == [("ticket", str(context.ticket_id))]
    sign_in(admin_client, "agent@example.test")
    page = listing(admin_client)
    assert keys(page) == [("work_item", str(context.work_item_id))]
    assert page["items"][0]["linked_tickets"][0]["id"] == str(context.ticket_id)


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"cursor": "x" * 513},
        {"kind": "everything"},
        {"work_status": "open"},
        {"ticket_status": "todo"},
        {"priority": "urgent"},
        {"client_id": "bad"},
        {"team_id": "bad"},
        {"q": "x" * 201},
        {"q": "bad\0text"},
        {"project_id": str(uuid4())},
        {"due_presence": "dated"},
        [("kind", "all"), ("kind", "ticket")],
        [("q", "one"), ("q", "two")],
    ],
)
def test_strict_query_rejects_unsupported_invalid_or_repeated_input(admin_client, params):
    assert admin_client.get(PATH, params=params).status_code == 422


def test_cursor_binding_and_strict_grammar(admin_client, db_engine, seeded_user):
    personal_pair(admin_client, db_engine, seeded_user)
    first = listing(admin_client, limit=1)
    cursor = first["next_cursor"]
    assert cursor and keys(listing(admin_client, limit=100, cursor=cursor))
    assert keys(listing(admin_client, limit=100, cursor=cursor, q="   ", kind="all"))
    assert admin_client.get(PATH, params={"cursor": cursor, "priority": "high"}).status_code == 422
    parts = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode().split("|")
    for index, value in [
        (0, "v2"),
        (1, "wrong-scope"),
        (2, "4"),
        (2, "00"),
        (3, "2026-11-13T12:00:00"),
        (4, "not-uuid"),
        (5, "all"),
    ]:
        bad = parts.copy()
        bad[index] = value
        encoded = base64.urlsafe_b64encode("|".join(bad).encode()).decode().rstrip("=")
        assert admin_client.get(PATH, params={"cursor": encoded}).status_code == 422
    for value in ["not-base64!", "a", cursor + "=", "", "YQ"]:
        assert admin_client.get(PATH, params={"cursor": value}).status_code == 422
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(PATH, params={"cursor": cursor}).status_code == 422
    assert listing(admin_client)["items"] == []


def test_query_count_is_constant(admin_client, db_engine, seeded_user):
    context = personal_pair(admin_client, db_engine, seeded_user)
    connect(admin_client, context.ticket_id, context.work_item_id)
    counts = []

    def count(*_args):
        counts.append(1)

    event.listen(Engine, "before_cursor_execute", count)
    try:
        assert len(listing(admin_client)["items"]) == 1
        baseline = len(counts)
        assert baseline > 0  # Observe the actual API Engine, not an idle fixture Engine.
    finally:
        event.remove(Engine, "before_cursor_execute", count)
    for _ in range(4):
        another_work(admin_client, context, seeded_user)
    counts.clear()
    event.listen(Engine, "before_cursor_execute", count)
    try:
        assert len(listing(admin_client)["items"]) == 5
        assert len(counts) == baseline
    finally:
        event.remove(Engine, "before_cursor_execute", count)


@pytest.mark.parametrize(
    "due",
    [
        {"precision": "date", "date": "2026-11-13", "timezone": "America/Sao_Paulo"},
        {"precision": "instant", "instant": "2026-11-13T18:00:00Z"},
    ],
)
def test_task_deadline_value_remains_independent_of_ticket(
    admin_client, db_engine, seeded_user, due
):
    context = personal_pair(admin_client, db_engine, seeded_user)
    updated = admin_client.patch(
        f"/api/v1/work-items/{context.work_item_id}", json={"due": due}, headers=preconditions(2)
    )
    assert updated.status_code == 200
    rows = listing(admin_client)["items"]
    task = next(row for row in rows if row["kind"] == "work_item")
    ticket = next(row for row in rows if row["kind"] == "ticket")
    assert task["due"] == updated.json()["due"]
    assert task["due_at"] == updated.json()["due_at"]
    assert "due" not in ticket and "due_at" not in ticket


def test_internal_work_needs_no_ticket_or_customer_grant(admin_client, seeded_user):
    project = setup_project(admin_client, seeded_user)
    created = create_work(admin_client, project, owner_id=str(seeded_user))
    assert created.status_code == 201
    page = listing(admin_client)
    assert keys(page) == [("work_item", created.json()["work_item_id"])]
    assert page["items"][0]["linked_tickets"] == []
    assert page["items"][0]["has_more_linked_tickets"] is False


def test_concurrent_unlink_preserves_ticket_representation(admin_client, db_engine, seeded_user):
    context = personal_pair(admin_client, db_engine, seeded_user)
    connect(admin_client, context.ticket_id, context.work_item_id)
    selected, release = Event(), Event()

    def pause(_connection, _cursor, statement, _parameters, _context, _executemany):
        if "eligible_personal_work" in statement:
            selected.set()
            assert release.wait(8), "Concurrent unlink did not finish"

    # Independent authenticated sessions let the writer commit while the reader
    # holds its own native session lock after selecting the personal queue.
    with TestClient(admin_client.app, base_url=str(admin_client.base_url)) as writer:
        writer.headers["Origin"] = admin_client.headers["Origin"]
        sign_in(writer, "employee@example.test")
        event.listen(Engine, "after_cursor_execute", pause)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                reader = executor.submit(listing, admin_client)
                try:
                    assert selected.wait(8), "Personal query did not execute"
                    removed = writer.delete(
                        f"/api/v1/tickets/{context.ticket_id}/work-items/{context.work_item_id}",
                        headers={**preconditions(3), "If-Match-Work-Item": '"3"'},
                    )
                    assert removed.status_code == 204, removed.text
                finally:
                    release.set()
                page = reader.result(timeout=8)
        finally:
            release.set()
            event.remove(Engine, "after_cursor_execute", pause)
    standalone = ("ticket", str(context.ticket_id)) in keys(page)
    represented = any(
        badge["id"] == str(context.ticket_id)
        for row in page["items"]
        if row["kind"] == "work_item"
        for badge in row["linked_tickets"]
    )
    assert standalone or represented, "Concurrent unlink lost the assigned ticket"
    fresh = listing(admin_client)
    assert set(keys(fresh)) == {
        ("ticket", str(context.ticket_id)),
        ("work_item", str(context.work_item_id)),
    }
    assert next(row for row in fresh["items"] if row["kind"] == "work_item")["linked_tickets"] == []


def test_created_unassigned_and_external_label_records_are_not_personal_work(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    updated = admin_client.patch(
        f"/api/v1/work-items/{context.work_item_id}",
        json={"external_participants": ["Test Employee"]},
        headers=preconditions(),
    )
    assert updated.status_code == 200
    assert admin_client.get(f"/api/v1/tickets/{context.ticket_id}").status_code == 200
    assert admin_client.get(f"/api/v1/work-items/{context.work_item_id}").status_code == 200
    assert listing(admin_client)["items"] == []


def test_native_customer_revocation_removes_both_domains(admin_client, db_engine, seeded_user):
    context = personal_pair(admin_client, db_engine, seeded_user)
    connect(admin_client, context.ticket_id, context.work_item_id)
    with Session(db_engine) as db, db.begin():
        assert client_registry.set_client_access(
            db, "employee@example.test", context.client_id, None
        )
    assert admin_client.get(PATH).status_code == 401
    sign_in(admin_client, "employee@example.test")
    page = listing(admin_client)
    assert page["items"] == [] and page["next_cursor"] is None
    assert str(context.ticket_id) not in str(page)
    assert str(context.work_item_id) not in str(page)


def test_archived_project_and_completed_task_keep_independent_ticket_origin(
    admin_client, db_engine, seeded_user
):
    context = personal_pair(admin_client, db_engine, seeded_user)
    connect(admin_client, context.ticket_id, context.work_item_id)
    for status in ["in_progress", "done"]:
        path = f"/api/v1/work-items/{context.work_item_id}"
        version = admin_client.get(path).json()["version"]
        changed = admin_client.post(
            path + "/transitions", json={"target_status": status}, headers=preconditions(version)
        )
        assert changed.status_code == 200
    project_path = f"/api/v1/projects/{context.project_id}"
    version = admin_client.get(project_path).json()["version"]
    archived = admin_client.patch(
        project_path, json={"active": False}, headers=preconditions(version)
    )
    assert archived.status_code == 200
    page = listing(admin_client)
    assert keys(page) == [("work_item", str(context.work_item_id))]
    assert page["items"][0]["status"] == "done"
    assert page["items"][0]["linked_tickets"][0]["status"] == "new"
    assert keys(listing(admin_client, work_status="todo")) == [("ticket", str(context.ticket_id))]


def test_representative_full_set_query_plan_is_bounded(
    admin_client, db_engine, seeded_user, record_testsuite_property
):
    context = personal_pair(admin_client, db_engine, seeded_user)
    now = datetime.now(UTC)
    identifiers = sorted(uuid4() for _ in range(6000))
    # Only the explicitly disposable integration database receives synthetic rows.
    with db_engine.begin() as connection:
        connection.execute(
            WorkItem.__table__.insert(),
            [
                {
                    "id": identifier,
                    "project_id": context.project_id,
                    "owner_id": seeded_user,
                    "title": f"Carga autorizada {index}",
                    "status": "todo",
                    "priority": "low",
                    "work_type": "one_off",
                    "created_at": now,
                    "updated_at": now,
                    "version": 1,
                }
                for index, identifier in enumerate(identifiers)
            ],
        )
    # This linked work is beyond the first page. Its urgent ticket must disappear
    # before LIMIT, although its own low-priority work row is not loaded yet.
    connect(admin_client, context.ticket_id, identifiers[-1])
    captured = []

    def capture(_connection, _cursor, statement, parameters, _context, _executemany):
        if "eligible_personal_work" in statement:
            captured.append((statement, parameters))

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        page = listing(admin_client, limit=100)
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
    assert len(page["items"]) == 100 and page["next_cursor"]
    assert all(row["kind"] == "work_item" for row in page["items"])
    assert len(captured) == 1
    statement, parameters = captured[0]
    with db_engine.connect() as connection:
        plan = connection.exec_driver_sql(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
        ).scalar_one()[0]
    assert plan["Plan"]["Actual Rows"] == 101
    record_testsuite_property(
        "unified_native_plan",
        json.dumps(
            {
                "eligible_work_rows": 6001,
                "returned_rows": 100,
                "execution_ms": plan["Execution Time"],
                "planning_ms": plan["Planning Time"],
                "root_node": plan["Plan"]["Node Type"],
                "root_actual_rows": plan["Plan"]["Actual Rows"],
            }
        ),
    )
