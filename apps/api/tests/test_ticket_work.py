"""Protected two-aggregate link intents against real PostgreSQL."""

from uuid import uuid4

import pytest
from altvia.models import AuditLog, OutboxEvent, Ticket, TicketWorkItem, WorkItem
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions
from ticket_work_support import make_link_context

__all__ = ["admin_client"]


def headers(ticket=1, work=1, key=None):
    return {**preconditions(ticket, key), "If-Match-Work-Item": f'"{work}"'}


def path(ctx):
    return f"/api/v1/tickets/{ctx.ticket_id}/work-items"


def link(client, ctx, version=1, work=None, key=None):
    return client.post(
        path(ctx),
        json={"work_item_id": str(ctx.work_item_id)},
        headers=headers(version, version if work is None else work, key),
    )


def unlink(client, ctx, version, key=None):
    return client.delete(path(ctx) + f"/{ctx.work_item_id}", headers=headers(version, version, key))


def snapshot(engine, ctx):
    with Session(engine) as db:
        ticket = db.get(Ticket, ctx.ticket_id)
        work = db.get(WorkItem, ctx.work_item_id)
        return (
            ticket.version,
            work.version,
            tuple(
                getattr(ticket, k)
                for k in ("status", "priority", "assignee_id", "resolved_at", "closed_at")
            ),
            tuple(
                getattr(work, k)
                for k in ("status", "priority", "owner_id", "due_at", "started_at", "completed_at")
            ),
            tuple(row.user_id for row in work.assignees),
            len(list(db.scalars(select(TicketWorkItem)))),
            len(
                list(
                    db.scalars(
                        select(OutboxEvent).where(
                            OutboxEvent.event_type.in_(
                                {
                                    "ticket.work_linked",
                                    "ticket.work_unlinked",
                                    "work_item.ticket_linked",
                                    "work_item.ticket_unlinked",
                                }
                            )
                        )
                    )
                )
            ),
            ticket.updated_at,
            work.updated_at,
        )


def test_link_two_versions_atomic_and_independent_states(admin_client, db_engine, seeded_user):
    ctx = make_link_context(admin_client, db_engine, seeded_user)
    before = snapshot(db_engine, ctx)
    key = uuid4().hex
    result = link(admin_client, ctx, key=key)
    assert result.status_code == 201, result.text
    assert result.json() == {"ticket_id": str(ctx.ticket_id), "work_item_id": str(ctx.work_item_id)}
    after = snapshot(db_engine, ctx)
    assert after[:2] == (2, 2) and after[2:5] == before[2:5] and after[5:7] == (1, 2)
    assert link(admin_client, ctx, key=key).status_code == 200
    assert snapshot(db_engine, ctx) == after
    with Session(db_engine) as db:
        events = list(
            db.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.event_type.in_({"ticket.work_linked", "work_item.ticket_linked"})
                )
            )
        )
        assert len(events) == 2 and events[0].event_id != events[1].event_id
        assert events[0].occurred_at == events[1].occurred_at
        assert events[0].correlation_id == events[1].correlation_id
        assert all(e.aggregate_version == 2 for e in events)
        assert (
            len(
                list(
                    db.scalars(
                        select(AuditLog).where(
                            AuditLog.action.in_({"ticket.work_linked", "work_item.ticket_linked"})
                        )
                    )
                )
            )
            == 2
        )


def test_link_unlink_relink_original_receipts(admin_client, db_engine, seeded_user):
    ctx = make_link_context(admin_client, db_engine, seeded_user)
    a, b, c = (uuid4().hex for _ in range(3))
    assert link(admin_client, ctx, key=a).status_code == 201
    assert unlink(admin_client, ctx, 2, b).status_code == 204
    assert link(admin_client, ctx, 3, key=c).status_code == 201
    current = snapshot(db_engine, ctx)
    retry = unlink(admin_client, ctx, 2, b)
    assert retry.status_code == 204 and not retry.content and "etag" not in retry.headers
    assert snapshot(db_engine, ctx) == current
    assert unlink(admin_client, ctx, 4).status_code == 204
    absent = snapshot(db_engine, ctx)
    assert link(admin_client, ctx, key=a).status_code == 200
    assert snapshot(db_engine, ctx) == absent
    for ticket_version, work_version in [(2, 1), (1, 2)]:
        response = link(admin_client, ctx, ticket_version, work_version, a)
        assert response.status_code == 409 and response.json()["code"] == "idempotency_conflict"
    assert link(admin_client, ctx).status_code == 409
    noop_key = uuid4().hex
    assert unlink(admin_client, ctx, 5, noop_key).status_code == 204
    assert snapshot(db_engine, ctx) == absent
    assert unlink(admin_client, ctx, 5, noop_key).status_code == 204


@pytest.mark.parametrize(
    "ticket_header,work_header,status,code",
    [
        (None, None, 428, "version_required"),
        ("1", None, 422, "invalid_version"),
        ('"1"', None, 428, "work_item_version_required"),
        ('"1"', "1", 422, "invalid_work_item_version"),
        ('"0"', '"1"', 422, "invalid_version"),
        ('"1"', '"2147483648"', 422, "invalid_work_item_version"),
        ('"2147483648"', '"1"', 422, "invalid_version"),
    ],
)
def test_two_header_errors(
    admin_client, db_engine, seeded_user, ticket_header, work_header, status, code
):
    ctx = make_link_context(admin_client, db_engine, seeded_user)
    values = {"Idempotency-Key": uuid4().hex}
    if ticket_header is not None:
        values["If-Match"] = ticket_header
    if work_header is not None:
        values["If-Match-Work-Item"] = work_header
    response = admin_client.post(
        path(ctx), json={"work_item_id": str(ctx.work_item_id)}, headers=values
    )
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def test_header_duplicates_keys_body_origin_and_csrf(admin_client, db_engine, seeded_user):
    ctx = make_link_context(admin_client, db_engine, seeded_user)
    body = {"work_item_id": str(ctx.work_item_id)}
    for header, code in [
        ("If-Match", "invalid_version"),
        ("If-Match-Work-Item", "invalid_work_item_version"),
    ]:
        values = list(headers().items()) + [(header, '"1"')]
        result = admin_client.post(path(ctx), json=body, headers=values)
        assert result.status_code == 422 and result.json()["code"] == code
    for key, status, code in [
        (None, 428, "idempotency_key_required"),
        ("x x", 422, "invalid_idempotency_key"),
    ]:
        values = headers()
        if key is None:
            values.pop("Idempotency-Key")
        else:
            values["Idempotency-Key"] = key
        result = admin_client.post(path(ctx), json=body, headers=values)
        assert result.status_code == status and result.json()["code"] == code
    assert (
        admin_client.post(
            path(ctx), json={**body, "client_id": str(uuid4())}, headers=headers()
        ).status_code
        == 422
    )
    for overrides in [{"Origin": "https://foreign.test"}, {"X-CSRF-Token": "wrong"}]:
        assert (
            admin_client.post(path(ctx), json=body, headers={**headers(), **overrides}).status_code
            == 403
        )
    assert snapshot(db_engine, ctx)[:2] == (1, 1)


@pytest.mark.parametrize("parent", ["client", "queue", "team", "project", "closed"])
def test_active_rules_follow_receipts_and_noops(admin_client, db_engine, seeded_user, parent):
    from datetime import UTC, datetime

    from altvia.models import Client, Project, Team, TicketQueue

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    key = uuid4().hex
    assert link(admin_client, ctx, key=key).status_code == 201
    with Session(db_engine) as db, db.begin():
        if parent == "closed":
            ticket = db.get(Ticket, ctx.ticket_id)
            ticket.status = "closed"
            ticket.resolved_at = ticket.closed_at = datetime.now(UTC)
        else:
            row = (
                db.get(Client, ctx.client_id)
                if parent == "client"
                else db.get(TicketQueue, ctx.queue_id)
                if parent == "queue"
                else db.get(Project, ctx.project_id)
                if parent == "project"
                else db.get(Team, db.get(Project, ctx.project_id).team_id)
            )
            row.active = False
    before = snapshot(db_engine, ctx)
    assert link(admin_client, ctx, key=key).status_code == 200
    assert link(admin_client, ctx, 2).status_code == 200
    assert unlink(admin_client, ctx, 2).status_code == 409
    assert snapshot(db_engine, ctx) == before
    page = admin_client.get(path(ctx)).json()
    assert page["items"][0]["can_unlink"] is False
    choices = admin_client.get(path(ctx).replace("/work-items", "/work-item-choices")).json()
    assert choices["items"] == []
    assert page["can_link"] is (parent == "project")
    assert choices["can_link"] == page["can_link"]


# Literal expectations distinguish membership halves, contribution, inherited
# manager scope and non-grant administration from the native policy oracle.
@pytest.mark.parametrize(
    "project_role,member,client_role,ceiling,involvement,ticket_role,assigned,want",
    [
        ("project_manager", True, None, True, None, "operations_manager", False, 201),
        ("project_manager", False, None, True, None, "operations_manager", False, 404),
        (None, True, None, True, "owner", "operations_manager", False, 404),
        ("project_manager", True, None, False, None, "operations_manager", False, 404),
        ("viewer", True, None, True, "owner", "operations_manager", False, 403),
        ("agent", True, None, True, None, "operations_manager", False, 403),
        ("agent", True, None, True, "owner", "operations_manager", False, 201),
        ("agent", True, None, True, "assignee", "operations_manager", False, 201),
        ("agent", True, None, True, "former", "operations_manager", False, 403),
        (None, False, "operations_manager", True, None, "operations_manager", False, 201),
        (None, False, "viewer", True, "owner", "operations_manager", False, 403),
        ("project_manager", True, None, True, None, "viewer", True, 403),
        ("project_manager", True, None, True, None, "agent", False, 403),
        ("project_manager", True, None, True, None, "agent", True, 201),
        ("agent", True, None, True, "assignee", "agent", True, 201),
        ("agent", True, None, True, "owner", "agent", False, 403),
    ],
)
def test_native_update_policy_and_candidate_parity(
    admin_client,
    db_engine,
    seeded_user,
    project_role,
    member,
    client_role,
    ceiling,
    involvement,
    ticket_role,
    assigned,
    want,
):
    from altvia import identity, tickets, work_items
    from altvia.models import ClientAccessGrant, ProjectMember, Role, RoleBinding, WorkAssignee
    from sqlalchemy import delete
    from sqlalchemy.dialects.postgresql import insert

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        db.execute(
            delete(RoleBinding).where(
                RoleBinding.user_id == seeded_user,
                RoleBinding.scope_kind.in_({"project", "client"}),
            )
        )
        db.execute(delete(ProjectMember).where(ProjectMember.user_id == seeded_user))
        for scope, role in [("project", project_role), ("client", client_role)]:
            if role:
                db.execute(insert(Role).values(name=role).on_conflict_do_nothing())
                db.add(
                    RoleBinding(
                        user_id=seeded_user,
                        scope_kind=scope,
                        role_name=role,
                        project_id=ctx.project_id if scope == "project" else None,
                        client_id=ctx.client_id if scope == "client" else None,
                    )
                )
        if member:
            db.add(ProjectMember(project_id=ctx.project_id, user_id=seeded_user))
        if not ceiling:
            db.delete(db.get(ClientAccessGrant, (seeded_user, ctx.client_id)))
        binding = db.scalar(
            select(RoleBinding).where(
                RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "queue"
            )
        )
        binding.role_name = ticket_role
        db.get(Ticket, ctx.ticket_id).assignee_id = seeded_user if assigned else None
        if involvement == "owner":
            db.get(WorkItem, ctx.work_item_id).owner_id = seeded_user
        if involvement == "assignee":
            db.add(WorkAssignee(work_item_id=ctx.work_item_id, user_id=seeded_user))
    with Session(db_engine) as db:
        try:
            item, access = tickets.scoped_ticket(db, seeded_user, ctx.ticket_id)
            work, permission = work_items.scoped_work(db, seeded_user, ctx.work_item_id)
            tickets.require_update(item, access, seeded_user)
            work_items.require_update(work, permission, seeded_user)
            native = 201
        except identity.IdentityError as error:
            native = error.status
        assert native == want
        work_allowed = False
        try:
            work, permission = work_items.scoped_work(db, seeded_user, ctx.work_item_id)
            work_allowed = work_items.can_update(work, permission, seeded_user)
        except identity.IdentityError:
            pass
    choices = admin_client.get(path(ctx).replace("/work-items", "/work-item-choices"))
    if choices.status_code == 200:
        assert bool(choices.json()["items"]) == work_allowed
    result = link(admin_client, ctx)
    assert result.status_code == want, result.text
    assert snapshot(db_engine, ctx)[:2] == ((2, 2) if want == 201 else (1, 1))


def test_sql_lists_choices_and_cursor_privacy(admin_client, db_engine, seeded_user):
    import base64

    from altvia.models import ProjectMember, RoleBinding
    from sqlalchemy import delete
    from test_work_items import create_work

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    ids = [str(ctx.work_item_id)]
    for title in ["Task segundo", "Task terceiro"]:
        result = create_work(admin_client, str(ctx.project_id), title=title)
        assert result.status_code == 201
        ids.append(result.json()["work_item_id"])
    choices_path = path(ctx).replace("/work-items", "/work-item-choices")
    first = admin_client.get(choices_path, params={"limit": 1, "q": " Task "})
    assert first.status_code == 200, first.text
    page = first.json()
    assert page["can_link"] and len(page["items"]) == 1 and page["next_cursor"]
    cursor = page["next_cursor"]
    assert (
        len(cursor) <= 250
        and "Task" not in base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    )
    second = admin_client.get(
        choices_path, params={"limit": 100, "q": "Task", "cursor": cursor}
    ).json()
    assert len(second["items"]) == 2 and second["next_cursor"] is None
    assert [page["items"][0]["work_item_id"]] + [
        row["work_item_id"] for row in second["items"]
    ] == sorted(ids)
    assert (
        admin_client.get(choices_path, params={"q": "different", "cursor": cursor}).status_code
        == 422
    )
    assert admin_client.get(path(ctx), params={"cursor": cursor}).status_code == 422
    assert admin_client.get(choices_path, params={"project_id": str(uuid4())}).json() == {
        "items": [],
        "next_cursor": None,
        "can_link": True,
    }
    for suffix in ["?limit=1&limit=2", "?extra=private", "?cursor=bad", "?limit=101"]:
        assert admin_client.get(choices_path + suffix).status_code == 422
    assert link(admin_client, ctx).status_code == 201
    listed = admin_client.get(path(ctx)).json()
    assert len(listed["items"]) == 1 and listed["items"][0]["can_unlink"]
    assert set(listed["items"][0]) == {
        "work_item_id",
        "project_id",
        "project_name",
        "title",
        "status",
        "priority",
        "version",
        "can_unlink",
    }
    reverse = admin_client.get(f"/api/v1/work-items/{ctx.work_item_id}/tickets").json()
    assert len(reverse["items"]) == 1 and reverse["items"][0]["ticket_id"] == str(ctx.ticket_id)
    assert isinstance(reverse["items"][0]["number"], str)
    assert len(admin_client.get(choices_path).json()["items"]) == 2
    with Session(db_engine) as db, db.begin():
        db.execute(
            delete(RoleBinding).where(
                RoleBinding.user_id == seeded_user,
                RoleBinding.scope_kind.in_({"project", "client"}),
            )
        )
        db.execute(delete(ProjectMember).where(ProjectMember.user_id == seeded_user))
    assert admin_client.get(path(ctx) + "?limit=1").json() == {
        "items": [],
        "next_cursor": None,
        "can_link": True,
    }
    assert admin_client.get(choices_path + "?limit=1").json() == {
        "items": [],
        "next_cursor": None,
        "can_link": True,
    }


@pytest.mark.parametrize(
    "failure", ["ticket_overflow", "work_overflow", "second_event", "constraint", "receipt"]
)
def test_either_version_overflow_and_second_event_failure_rollback(
    admin_client, db_engine, seeded_user, monkeypatch, failure
):
    from altvia import identity, ticket_work_api
    from altvia.models import IdempotencyRecord

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    versions = [1, 1]
    if failure.endswith("overflow"):
        index = 0 if failure == "ticket_overflow" else 1
        versions[index] = 2147483647
        with Session(db_engine) as db, db.begin():
            db.get(
                Ticket if index == 0 else WorkItem,
                ctx.ticket_id if index == 0 else ctx.work_item_id,
            ).version = 2147483647
    before = snapshot(db_engine, ctx)
    record = identity.record_event

    def fail_event(db, actor, resource, event, *args, **kwargs):
        if event == "work_item.ticket_linked":
            db.flush()  # Prove rollback after the first audit/outbox/versions reached SQL.
            if failure == "constraint":
                db.add(
                    TicketWorkItem(
                        ticket_id=ctx.ticket_id,
                        work_item_id=ctx.work_item_id,
                        client_id=ctx.client_id,
                        queue_id=ctx.queue_id,
                        project_id=ctx.project_id,
                        created_by=actor,
                    )
                )
                db.flush()
            raise RuntimeError("Injected second event failure")
        return record(db, actor, resource, event, *args, **kwargs)

    def fail_receipt(db, *args):
        db.flush()
        raise RuntimeError("Injected receipt failure")

    if failure in {"second_event", "constraint"}:
        monkeypatch.setattr(identity, "record_event", fail_event)
    if failure == "receipt":
        monkeypatch.setattr(ticket_work_api, "_remember", fail_receipt)
    if failure.endswith("overflow"):
        result = link(admin_client, ctx, *versions)
        assert result.status_code == 409 and result.json()["code"] == "version_exhausted"
    elif failure == "constraint":
        assert link(admin_client, ctx).status_code == 503
    else:
        with pytest.raises(RuntimeError):
            link(admin_client, ctx)
    assert snapshot(db_engine, ctx) == before
    with Session(db_engine) as db:
        assert (
            list(
                db.scalars(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.route.startswith("ticket-work-")
                    )
                )
            )
            == []
        )


def test_internal_and_other_client_mismatch_and_administration_no_grant(
    admin_client, db_engine, seeded_user
):
    from dataclasses import replace
    from uuid import UUID

    from altvia.models import Project
    from test_client_registry import created
    from test_project_registry import project
    from test_team_api import sign_in
    from test_work_items import create_work

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db:
        team_id = str(db.get(Project, ctx.project_id).team_id)
    for customer_kind in ["internal", "other"]:
        sign_in(admin_client, "admin@example.test")
        customer = (
            None
            if customer_kind == "internal"
            else created(admin_client, seeded_user, name="Other")
        )
        result = project(admin_client, seeded_user, team_id, customer)
        assert result.status_code == 201
        sign_in(admin_client, "employee@example.test")
        result = create_work(admin_client, result.json()["project_id"])
        assert result.status_code == 201
        foreign = replace(ctx, work_item_id=UUID(result.json()["work_item_id"]))
        rejected = link(admin_client, foreign)
        assert (
            rejected.status_code == 409 and rejected.json()["code"] == "ticket_work_client_mismatch"
        )
        assert "Other" not in rejected.text and str(foreign.work_item_id) not in rejected.text
    sign_in(admin_client, "admin@example.test")
    assert (
        link(admin_client, ctx).status_code == 404
    )  # Platform/queue config authority is no content grant.
    assert snapshot(db_engine, ctx)[:2] == (1, 1)


def wait_for_blocker(engine, pid):
    from time import monotonic, sleep

    from sqlalchemy import text

    deadline = monotonic() + 5
    while monotonic() < deadline:
        with engine.connect() as monitor:
            if monitor.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                    "WHERE :pid=ANY(pg_blocking_pids(pid)))"
                ),
                {"pid": pid},
            ):
                return
        sleep(0.02)
    pytest.fail("No real PostgreSQL waiter observed")


def test_many_to_many_and_hidden_links_do_not_contribute_cursor(
    admin_client, db_engine, seeded_user
):
    from dataclasses import replace
    from uuid import UUID

    from altvia.models import Project, RoleBinding
    from sqlalchemy import delete
    from test_project_registry import project
    from test_team_api import sign_in
    from test_tickets import ticket
    from test_work_items import create_work

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db:
        team_id = str(db.get(Project, ctx.project_id).team_id)
        row = db.get(Ticket, ctx.ticket_id)
        refs = {
            "client_id": str(ctx.client_id),
            "queue_id": str(ctx.queue_id),
            "requester_id": str(row.requester_id),
            "category_id": str(row.category_id),
        }
    other_ticket = UUID(ticket(admin_client, refs).rsplit("/", 1)[1])
    sign_in(admin_client, "admin@example.test")
    other_project = project(admin_client, seeded_user, team_id, str(ctx.client_id)).json()[
        "project_id"
    ]
    sign_in(admin_client, "employee@example.test")
    other_work = UUID(create_work(admin_client, other_project).json()["work_item_id"])
    assert link(admin_client, ctx).status_code == 201
    assert link(admin_client, replace(ctx, work_item_id=other_work), 2, 1).status_code == 201
    assert link(admin_client, replace(ctx, ticket_id=other_ticket), 1, 2).status_code == 201
    assert link(admin_client, replace(ctx, ticket_id=other_ticket), 2, 3).status_code == 200
    assert (
        len(admin_client.get(f"/api/v1/work-items/{ctx.work_item_id}/tickets").json()["items"]) == 2
    )
    hidden_work, visible_work = sorted([ctx.work_item_id, other_work], key=str)
    hidden_project = ctx.project_id if hidden_work == ctx.work_item_id else UUID(other_project)
    with Session(db_engine) as db, db.begin():
        db.execute(
            delete(RoleBinding).where(
                RoleBinding.user_id == seeded_user,
                (RoleBinding.scope_kind == "client") | (RoleBinding.project_id == hidden_project),
            )
        )
    result = admin_client.get(path(ctx) + "?limit=1")
    assert result.status_code == 200, result.text
    assert [row["work_item_id"] for row in result.json()["items"]] == [str(visible_work)]
    assert result.json()["next_cursor"] is None
    assert str(hidden_work) not in result.text


@pytest.mark.parametrize("revoke", ["ticket_action", "work_action", "ceiling", "project"])
def test_current_authority_precedes_saved_receipt(admin_client, db_engine, seeded_user, revoke):
    from altvia.models import ClientAccessGrant, RoleBinding
    from sqlalchemy import delete

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    key = uuid4().hex
    assert link(admin_client, ctx, key=key).status_code == 201
    with Session(db_engine) as db, db.begin():
        if revoke == "ticket_action":
            db.scalar(
                select(RoleBinding).where(
                    RoleBinding.user_id == seeded_user, RoleBinding.queue_id == ctx.queue_id
                )
            ).role_name = "viewer"
        elif revoke == "ceiling":
            db.delete(db.get(ClientAccessGrant, (seeded_user, ctx.client_id)))
        else:
            db.execute(
                delete(RoleBinding).where(
                    RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "client"
                )
            )
            binding = db.scalar(
                select(RoleBinding).where(
                    RoleBinding.user_id == seeded_user, RoleBinding.project_id == ctx.project_id
                )
            )
            if revoke == "project":
                db.delete(binding)
            else:
                binding.role_name = "viewer"
    before = snapshot(db_engine, ctx)
    result = link(admin_client, ctx, key=key)
    assert result.status_code == (404 if revoke in {"ceiling", "project"} else 403), result.text
    assert snapshot(db_engine, ctx) == before


def test_terminal_task_and_legacy_transition_fingerprint(admin_client, db_engine, seeded_user):
    ctx = make_link_context(admin_client, db_engine, seeded_user)
    work_path = f"/api/v1/work-items/{ctx.work_item_id}/transitions"
    assert (
        admin_client.post(
            work_path, json={"target_status": "in_progress"}, headers=preconditions(1)
        ).status_code
        == 200
    )
    key = uuid4().hex
    result = admin_client.post(
        work_path, json={"target_status": "done"}, headers=preconditions(2, key)
    )
    assert result.status_code == 200
    # Existing transition fingerprints deliberately omit original versions.
    replay = admin_client.post(
        work_path, json={"target_status": "done"}, headers=preconditions(999, key)
    )
    assert replay.status_code == 200 and replay.json() == result.json()
    before = snapshot(db_engine, ctx)
    assert link(admin_client, ctx, 1, 3).status_code == 201
    after = snapshot(db_engine, ctx)
    assert after[:2] == (2, 4) and after[2:5] == before[2:5]


@pytest.mark.parametrize("role", ["viewer", "operations_manager"])
def test_team_metadata_role_and_roster_do_not_grant_work_links(
    admin_client, db_engine, seeded_user, role
):
    from altvia.models import Project, RoleBinding, TeamMember
    from sqlalchemy import delete

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        db.execute(
            delete(RoleBinding).where(
                RoleBinding.user_id == seeded_user,
                RoleBinding.scope_kind.in_({"project", "client", "team"}),
            )
        )
        team_id = db.get(Project, ctx.project_id).team_id
        db.add(RoleBinding(user_id=seeded_user, scope_kind="team", team_id=team_id, role_name=role))
        db.add(TeamMember(team_id=team_id, user_id=seeded_user))
    assert link(admin_client, ctx).status_code == 404
    choices = admin_client.get(path(ctx).replace("/work-items", "/work-item-choices"))
    assert choices.json() == {"items": [], "next_cursor": None, "can_link": True}
    assert snapshot(db_engine, ctx)[:2] == (1, 1)


@pytest.mark.parametrize("competitor", ["revoke", "archive", "reassign", "transition", "logout"])
def test_link_current_authority_and_concurrent_lifecycle(
    admin_client, db_engine, seeded_user, settings, monkeypatch, competitor
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from altvia import ticket_work
    from fastapi.testclient import TestClient
    from sqlalchemy import text
    from test_team_api import sign_in

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    entered, release = Event(), Event()
    pids = []
    change = ticket_work.change_link

    def observed(db, *args, **kwargs):
        pids.append(db.scalar(text("SELECT pg_backend_pid()")))
        entered.set()
        assert release.wait(10)
        return change(db, *args, **kwargs)

    monkeypatch.setattr(ticket_work, "change_link", observed)
    with TestClient(
        admin_client.app,
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as other:
        if competitor == "logout":
            other.cookies.update(admin_client.cookies)
            other.headers["X-CSRF-Token"] = admin_client.headers["X-CSRF-Token"]
        else:
            sign_in(other, "employee@example.test")
        work_path = f"/api/v1/work-items/{ctx.work_item_id}"
        with ThreadPoolExecutor(2) as pool:
            pending = pool.submit(link, admin_client, ctx)
            try:
                assert entered.wait(5)
                if competitor == "revoke":
                    second = pool.submit(
                        other.delete,
                        f"/api/v1/projects/{ctx.project_id}/members/{seeded_user}",
                        headers=preconditions(1),
                    )
                elif competitor == "archive":
                    second = pool.submit(
                        other.patch,
                        f"/api/v1/projects/{ctx.project_id}",
                        json={"active": False},
                        headers=preconditions(1),
                    )
                elif competitor == "reassign":
                    second = pool.submit(
                        other.patch,
                        work_path,
                        json={"owner_id": str(seeded_user)},
                        headers=preconditions(1),
                    )
                elif competitor == "transition":
                    second = pool.submit(
                        other.post,
                        work_path + "/transitions",
                        json={"target_status": "in_progress"},
                        headers=preconditions(1),
                    )
                else:
                    second = pool.submit(other.delete, "/api/v1/auth/sessions/current")
                wait_for_blocker(db_engine, pids[0])
            finally:
                release.set()
            assert pending.result(timeout=10).status_code == 201
            result = second.result(timeout=10)
            assert (
                result.status_code
                == {
                    "revoke": 204,
                    "archive": 200,
                    "reassign": 409,
                    "transition": 409,
                    "logout": 204,
                }[competitor]
            ), result.text
    assert snapshot(db_engine, ctx)[:2] == (2, 2)
    assert snapshot(db_engine, ctx)[5:7] == (1, 2)


def test_locked_pair_refreshes_work_and_assignments_after_initial_read(
    admin_client, db_engine, seeded_user, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from altvia import work_items
    from altvia.models import RoleBinding, WorkAssignee
    from sqlalchemy import delete, text

    ctx = make_link_context(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        db.execute(
            delete(RoleBinding).where(
                RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "client"
            )
        )
        binding = db.scalar(
            select(RoleBinding).where(
                RoleBinding.user_id == seeded_user, RoleBinding.project_id == ctx.project_id
            )
        )
        binding.role_name = "agent"
        db.add(WorkAssignee(work_item_id=ctx.work_item_id, user_id=seeded_user))
    entered, release = Event(), Event()
    original = work_items.scoped_work

    def observed(db, actor, identifier, *, write=False):
        result = original(db, actor, identifier, write=write)
        if not write:
            assert work_items.can_update(*result, actor)
            entered.set()
            assert release.wait(10)
        return result

    monkeypatch.setattr(work_items, "scoped_work", observed)
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(link, admin_client, ctx)
        try:
            assert entered.wait(5)
            # A current owner tool is not assumed to participate in HTTP's
            # identity lock. Explicit graph-before-row order is required.
            with Session(db_engine) as owner, owner.begin():
                owner.execute(text("SET LOCAL lock_timeout='3s'"))
                owner.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
                    {"scope": "altvia:work-graph:" + str(ctx.project_id)},
                )
                item = owner.scalar(
                    select(WorkItem)
                    .where(WorkItem.id == ctx.work_item_id)
                    .with_for_update(of=WorkItem)
                )
                owner.execute(
                    delete(WorkAssignee).where(WorkAssignee.work_item_id == ctx.work_item_id)
                )
                item.title = "Concurrent owner content"
                item.version += 1
        finally:
            release.set()
        response = pending.result(timeout=10)
        assert response.status_code == 403, response.text
    state = snapshot(db_engine, ctx)
    assert state[:2] == (1, 2) and state[4:7] == ((), 0, 0)
