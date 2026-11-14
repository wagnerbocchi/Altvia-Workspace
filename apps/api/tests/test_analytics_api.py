"""Native management scope and reconciled reporting, never browser-page counts."""

import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from altvia.models import (
    Client,
    ClientAccessGrant,
    OutboundMessage,
    OutboxEvent,
    Project,
    ProjectMember,
    RoleBinding,
    Team,
    Ticket,
    TicketQueue,
    TicketWorkItem,
    User,
    WorkItem,
)
from sqlalchemy import Engine, delete, event, func, select
from sqlalchemy.orm import Session
from test_automation_rules import rule_context
from test_project_registry import project
from test_team_api import admin_client, preconditions, sign_in
from test_unified_work import connect
from test_work_items import create_work
from ticket_work_support import make_link_context

__all__ = ["admin_client", "rule_context"]

PATH = "/api/v1/analytics/overview"
REFERENCE = {
    "reference_at": "2026-11-14T12:00:00Z",
    "due_through": "2026-11-21T12:00:00Z",
    "timezone": "America/Sao_Paulo",
}
WORKLOAD = "/api/v1/analytics/team-workload"
SCOPES = "/api/v1/analytics/scopes"


def report(client, **filters):
    response = client.get(PATH, params={**REFERENCE, **filters})
    assert response.status_code == 200, response.text
    return response.json()


def test_native_manager_overview_reconciles_linked_work_without_domain_writes(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    connect(admin_client, context.ticket_id, context.work_item_id)

    def source():
        with Session(db_engine) as db:
            return (
                db.scalar(select(func.count()).select_from(OutboxEvent)),
                db.get(Ticket, context.ticket_id).version,
                db.get(WorkItem, context.work_item_id).version,
            )

    before = source()
    value = report(admin_client)
    assert value["work_item_count"] == value["ticket_count"] == 1
    assert value["represented_ticket_count"] == 1
    assert value["standalone_ticket_count"] == 0
    assert value["unified_count"] == value["active_unified_count"] == 1
    assert value["active_work_item_count"] == value["active_ticket_count"] == 1
    assert value["active_no_due_date_count"] == value["all_missing_deadline_count"] == 1
    assert value["work_status_counts"] == {
        "todo": 1,
        "in_progress": 0,
        "blocked": 0,
        "done": 0,
        "cancelled": 0,
    }
    assert value["ticket_status_counts"] == {
        "new": 1,
        "open": 0,
        "pending_customer": 0,
        "pending_third_party": 0,
        "resolved": 0,
        "closed": 0,
    }
    assert value["sla_unconfigured_ticket_count"] == 1
    assert value["sla_recorded_breach_ticket_count"] == 0
    assert datetime.fromisoformat(value["observed_at"]).tzinfo is not None
    assert datetime.fromisoformat(value["filters"]["reference_at"]) == datetime(
        2026, 11, 14, 12, tzinfo=UTC
    )
    assert source() == before


def test_active_projection_does_not_hide_ticket_behind_completed_work(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    connect(admin_client, context.ticket_id, context.work_item_id)
    with Session(db_engine) as db, db.begin():
        work = db.get(WorkItem, context.work_item_id)
        work.status, work.completed_at = "done", datetime.now(UTC)
    value = report(admin_client)
    assert value["unified_count"] == 1
    assert value["active_unified_count"] == 1
    assert value["active_work_item_count"] == value["active_no_due_date_count"] == 0
    assert value["active_ticket_count"] == value["all_missing_deadline_count"] == 1


def test_ongoing_missing_and_terminal_deadlines_are_distinct_populations(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    for due in [None, {"precision": "instant", "instant": "2001-01-01T00:00:00Z"}]:
        response = create_work(admin_client, str(context.project_id), work_type="ongoing", due=due)
        assert response.status_code == 201, response.text
    result = create_work(admin_client, str(context.project_id))
    assert result.status_code == 201
    with Session(db_engine) as db, db.begin():
        row = db.get(WorkItem, UUID(result.json()["work_item_id"]))
        row.status, row.completed_at = "done", datetime.now(UTC)
    value = report(admin_client)
    assert value["work_item_count"] == 4 and value["active_work_item_count"] == 3
    assert value["ongoing_work_item_count"] == 2
    assert value["all_missing_deadline_count"] == 3
    assert value["active_no_due_date_count"] == 1
    assert value["overdue_work_item_count"] == 0
    assert (
        sum(
            value[name]
            for name in [
                "active_no_due_date_count",
                "ongoing_work_item_count",
                "overdue_work_item_count",
                "due_soon_work_item_count",
                "later_due_work_item_count",
            ]
        )
        == value["active_work_item_count"]
    )


def test_priority_and_native_creation_period_filter_each_domain_independently(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    connect(admin_client, context.ticket_id, context.work_item_id)
    with Session(db_engine) as db:
        ticket_at = db.get(Ticket, context.ticket_id).created_at
        work_at = db.get(WorkItem, context.work_item_id).created_at
    assert ticket_at < work_at
    for fields, expected in [
        ({"priority": "high"}, (0, 1)),
        ({"priority": "medium"}, (1, 0)),
        ({"created_from": ticket_at.isoformat(), "created_before": work_at.isoformat()}, (0, 1)),
        (
            {
                "created_from": work_at.isoformat(),
                "created_before": (work_at + timedelta(seconds=1)).isoformat(),
            },
            (1, 0),
        ),
    ]:
        value = report(admin_client, **fields)
        assert (value["work_item_count"], value["ticket_count"]) == expected
        assert value["unified_count"] == 1 and value["represented_ticket_count"] == 0
    value = report(admin_client, project_id=str(context.project_id), priority="high")
    assert value["work_item_count"] == 0 and value["ticket_count"] == 1
    assert value["standalone_ticket_count"] == 1


@pytest.mark.parametrize(
    "removed,expected",
    [("ceiling", (0, 0)), ("queue_manager", (1, 0)), ("project_manager", (0, 1))],
)
def test_operation_availability_never_substitutes_for_current_resource_scope(
    admin_client, db_engine, seeded_user, removed, expected
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        if removed == "ceiling":
            db.execute(delete(ClientAccessGrant).where(ClientAccessGrant.user_id == seeded_user))
        elif removed == "queue_manager":
            role = db.scalar(
                select(RoleBinding).where(
                    RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "queue"
                )
            )
            role.role_name = "viewer"
        else:
            db.execute(
                delete(RoleBinding).where(
                    RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "client"
                )
            )
            role = db.scalar(
                select(RoleBinding).where(
                    RoleBinding.user_id == seeded_user, RoleBinding.project_id == context.project_id
                )
            )
            role.role_name = "viewer"
    assert "analytics.read" in admin_client.get("/api/v1/auth/me").json()["capabilities"]
    value = report(admin_client)
    assert (value["work_item_count"], value["ticket_count"]) == expected


def test_retained_hidden_link_and_task_ownership_never_grant_analytics_work(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db:
        from altvia.models import Project

        team_id = db.get(Project, context.project_id).team_id
    sign_in(admin_client, "admin@example.test")
    created = project(admin_client, seeded_user, str(team_id), customer=str(context.client_id))
    assert created.status_code == 201, created.text
    hidden_project = UUID(created.json()["project_id"])
    sign_in(admin_client, "employee@example.test")
    created = create_work(admin_client, str(hidden_project), owner_id=str(seeded_user))
    assert created.status_code == 201, created.text
    hidden_work = UUID(created.json()["work_item_id"])
    connect(admin_client, context.ticket_id, hidden_work)
    with Session(db_engine) as db, db.begin():
        db.execute(
            delete(RoleBinding).where(
                RoleBinding.user_id == seeded_user,
                (RoleBinding.scope_kind == "client") | (RoleBinding.project_id == hidden_project),
            )
        )
    assert admin_client.get(f"/api/v1/work-items/{hidden_work}").status_code == 404
    value = report(admin_client)
    assert value["work_item_count"] == value["ticket_count"] == 1
    assert value["represented_ticket_count"] == 0 and value["unified_count"] == 2
    assert report(admin_client, project_id=str(hidden_project))["ticket_count"] == 0
    assert report(admin_client, project_id=str(uuid4()))["work_item_count"] == 0


@pytest.mark.parametrize(
    "day,zone,boundary",
    [
        ("2026-03-08", "America/New_York", "2026-03-09T04:00:00Z"),
        ("2026-11-01", "America/New_York", "2026-11-02T05:00:00Z"),
        ("2026-11-13", "America/Sao_Paulo", "2026-11-14T03:00:00Z"),
    ],
)
def test_stored_date_end_is_overdue_while_equal_instant_is_on_time(
    admin_client, db_engine, seeded_user, day, zone, boundary
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    for due in [
        {"precision": "date", "date": day, "timezone": zone},
        {"precision": "instant", "instant": boundary},
    ]:
        response = create_work(admin_client, str(context.project_id), due=due)
        assert response.status_code == 201, response.text
    through = datetime.fromisoformat(boundary) + timedelta(days=1)
    value = report(
        admin_client, reference_at=boundary, due_through=through.isoformat(), timezone="UTC"
    )
    assert value["overdue_work_item_count"] == value["due_soon_work_item_count"] == 1
    assert value["active_no_due_date_count"] == 1 and value["active_work_item_count"] == 3


def test_microseconds_and_inclusive_due_through_are_not_rounded_away(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    reference = datetime.fromisoformat(REFERENCE["reference_at"])
    through = datetime.fromisoformat(REFERENCE["due_through"])
    for instant in [
        reference - timedelta(microseconds=1),
        reference,
        through,
        through + timedelta(microseconds=1),
    ]:
        result = create_work(
            admin_client,
            str(context.project_id),
            due={"precision": "instant", "instant": instant.isoformat()},
        )
        assert result.status_code == 201, result.text
    value = report(admin_client)
    assert value["overdue_work_item_count"] == 1
    assert value["due_soon_work_item_count"] == 2
    assert value["later_due_work_item_count"] == 1


@pytest.mark.parametrize("email", ["agent@example.test", "viewer@example.test"])
def test_native_ticket_reader_receives_no_management_analytics(
    admin_client, db_engine, seeded_user, email
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    user = sign_in(admin_client, email)
    assert "analytics.read" not in user["capabilities"]
    assert admin_client.get(f"/api/v1/tickets/{context.ticket_id}").status_code == 200
    response = admin_client.get(PATH, params=REFERENCE)
    assert response.status_code == 403 and "work_item_count" not in response.text


def test_bare_platform_admin_has_no_analytics_grant(admin_client):
    assert "analytics.read" not in admin_client.get("/api/v1/auth/me").json()["capabilities"]
    assert admin_client.get(PATH, params=REFERENCE).status_code == 403


def test_analytics_requires_a_current_session(client):
    assert client.get(PATH, params=REFERENCE).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"q": "unsupported"},
        {"reference_at": "1700000000"},
        {"reference_at": "2026-11-14T12:00:00"},
        {"due_through": REFERENCE["reference_at"]},
        {"timezone": "UTC\x00"},
        {"timezone": "x" * 101},
        {"responsible_id": "not-a-uuid"},
        {"responsible_id": str(uuid4()), "unassigned": "true"},
        {"created_from": REFERENCE["reference_at"]},
        {"created_before": REFERENCE["reference_at"]},
        {"created_from": REFERENCE["due_through"], "created_before": REFERENCE["reference_at"]},
    ],
)
def test_strict_report_query_rejects_unknown_coercions_and_ambiguous_ranges(admin_client, changes):
    assert admin_client.get(PATH, params={**REFERENCE, **changes}).status_code == 422


def test_timezone_lookup_and_repeated_fields_do_not_fall_back(admin_client, db_engine, seeded_user):
    context = make_link_context(admin_client, db_engine, seeded_user)
    assert (
        admin_client.get(PATH, params={**REFERENCE, "timezone": "Mars/Olympus"}).status_code == 422
    )
    params = [
        *REFERENCE.items(),
        ("client_id", str(context.client_id)),
        ("client_id", str(context.client_id)),
    ]
    assert admin_client.get(PATH, params=params).status_code == 422


def test_recorded_sla_breaches_corrections_and_latest_cycle_are_not_reference_time_history(
    admin_client, db_engine, rule_context
):
    from altvia import mail_delivery
    from test_sla_acceptance import capture, queued
    from test_sla_cycles import change
    from test_sla_execution import owner, tracked

    path, _, _, _ = tracked(admin_client, db_engine, rule_context)
    claim = queued(admin_client, db_engine, path, rule_context)
    assert mail_delivery.finalize(db_engine, claim.delivery_id, claim.token, "data_unknown")
    evidence_at = datetime.now(UTC)
    change(admin_client, path, "open")
    change(admin_client, path, "resolved")
    assert owner().evaluate_due(db_engine) == 1
    old_reference = {
        "reference_at": "2000-01-01T00:00:00Z",
        "due_through": "2000-01-02T00:00:00Z",
        "timezone": "UTC",
    }
    before = report(admin_client, **old_reference)
    assert before["sla_configured_ticket_count"] == before["sla_recorded_breach_ticket_count"] == 1
    assert before["sla_corrected_ticket_count"] == 0
    with Session(db_engine) as db, db.begin():
        row = db.get(OutboundMessage, claim.delivery_id)
        mail_delivery.reconcile(
            db,
            row.id,
            row.version,
            "accepted",
            "synthetic-analytics-correction",
            workers_drained=True,
            accepted_at=evidence_at,
        )
    assert capture(db_engine) == 1 and owner().evaluate_due(db_engine) == 1
    after = report(admin_client, **old_reference)
    assert after["sla_recorded_breach_ticket_count"] == after["sla_corrected_ticket_count"] == 1
    assert datetime.fromisoformat(after["sla_last_observation_at"]) >= evidence_at
    queue_path = "/api/v1/ticket-queues/" + rule_context["queue_id"]
    current = admin_client.get(queue_path).json()
    assert (
        admin_client.patch(
            queue_path, json={"allow_reopen": True}, headers=preconditions(current["version"])
        ).status_code
        == 200
    )
    change(admin_client, path, "open")
    current = report(admin_client)
    assert current["sla_configured_ticket_count"] == 1
    assert current["sla_recorded_breach_ticket_count"] == current["sla_corrected_ticket_count"] == 0
    assert current["sla_last_observation_at"] is None


def test_workload_has_real_null_principal_bucket_and_global_reconciliation(
    admin_client, db_engine, seeded_user
):
    make_link_context(admin_client, db_engine, seeded_user)
    response = admin_client.get("/api/v1/analytics/team-workload", params=REFERENCE)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["next_cursor"] is None
    assert len(value["items"]) == 1
    row = value["items"][0]
    assert row["user_id"] is row["name"] is None
    assert row["active_work_item_count"] == row["active_ticket_count"] == 1
    assert row["active_no_due_date_count"] == 1
    assert value["overview"]["active_unified_count"] == 2
    assert "unified_count" not in row


def test_scope_discovery_contains_actual_managed_project_not_an_unrestricted_directory(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    response = admin_client.get("/api/v1/analytics/scopes", params={"kind": "project", "limit": 1})
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["next_cursor"] is None and len(value["items"]) == 1
    assert value["items"][0]["id"] == str(context.project_id)
    assert set(value["items"][0]) == {"id", "name"}


def principal_rows(admin_client, db_engine, seeded_user):
    """Referenced real zero UUID must never collapse into the unassigned bucket."""
    context = make_link_context(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        source = db.get(User, seeded_user)
        db.add(
            User(
                id=UUID(int=0),
                email_normalized="former@example.test",
                display_name="Former owner",
                password_hash=source.password_hash,
                active=False,
                created_at=datetime.now(UTC),
            )
        )
        db.flush()
        db.get(WorkItem, context.work_item_id).owner_id = UUID(int=0)
        db.get(Ticket, context.ticket_id).assignee_id = seeded_user
    for owner in [None, str(seeded_user)]:
        response = create_work(admin_client, str(context.project_id), owner_id=owner)
        assert response.status_code == 201, response.text
    connect(admin_client, context.ticket_id, context.work_item_id)
    return context


def test_workload_pages_null_zero_and_cross_domain_principals_without_local_deduplication(
    admin_client, db_engine, seeded_user
):
    principal_rows(admin_client, db_engine, seeded_user)
    response = admin_client.get(WORKLOAD, params={**REFERENCE, "limit": 1})
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["items"][0]["user_id"] is None
    assert first["items"][0]["active_work_item_count"] == 1
    assert first["items"][0]["active_ticket_count"] == 0
    assert first["overview"]["active_unified_count"] == 3
    # Limit is not bound; equivalent UTC instants must bind to the same cursor.
    second = admin_client.get(
        WORKLOAD,
        params={
            **REFERENCE,
            "reference_at": "2026-11-14T09:00:00-03:00",
            "cursor": first["next_cursor"],
            "limit": 2,
        },
    )
    assert second.status_code == 200, second.text
    value = second.json()
    assert value["next_cursor"] is None
    assert [row["user_id"] for row in value["items"]] == [str(UUID(int=0)), str(seeded_user)]
    assert value["items"][0]["name"] == "Former owner"
    assert value["items"][1]["active_ticket_count"] == 1
    rows = first["items"] + value["items"]
    for name in ["active_work_item_count", "active_ticket_count", "active_no_due_date_count"]:
        assert sum(row[name] for row in rows) == value["overview"][name]
    assert sum(row["active_work_item_count"] + row["active_ticket_count"] for row in rows) == 4
    filtered = admin_client.get(WORKLOAD, params={**REFERENCE, "unassigned": "true"})
    assert filtered.status_code == 200, filtered.text
    assert len(filtered.json()["items"]) == 1
    assert filtered.json()["overview"]["ticket_count"] == 0
    assert report(admin_client, responsible_id=str(seeded_user))["represented_ticket_count"] == 0


def test_workload_cursor_is_bound_and_current_scope_is_rechecked(
    admin_client, db_engine, seeded_user
):
    principal_rows(admin_client, db_engine, seeded_user)
    first = admin_client.get(WORKLOAD, params={**REFERENCE, "limit": 1}).json()
    cursor = first["next_cursor"]
    for changes in [
        {"priority": "high"},
        {"timezone": "UTC"},
        {"unassigned": "true"},
        {"due_through": "2026-11-22T12:00:00Z"},
    ]:
        assert (
            admin_client.get(
                WORKLOAD, params={**REFERENCE, "cursor": cursor, **changes}
            ).status_code
            == 422
        )
    with Session(db_engine) as db, db.begin():
        db.execute(delete(ClientAccessGrant).where(ClientAccessGrant.user_id == seeded_user))
    response = admin_client.get(WORKLOAD, params={**REFERENCE, "cursor": cursor})
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [] and response.json()["next_cursor"] is None
    assert response.json()["overview"]["active_work_item_count"] == 0


def test_scope_pages_include_empty_managed_contexts_but_only_referenced_people(
    admin_client, db_engine, seeded_user
):
    context = principal_rows(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db:
        team_id = str(db.get(Project, context.project_id).team_id)
    sign_in(admin_client, "admin@example.test")
    created = project(admin_client, seeded_user, team_id, customer=str(context.client_id))
    assert created.status_code == 201, created.text
    empty_project_id = created.json()["project_id"]
    sign_in(admin_client, "employee@example.test")
    first = admin_client.get(SCOPES, params={"kind": "project", "limit": 1})
    assert first.status_code == 200, first.text
    first = first.json()
    assert first["next_cursor"] is not None
    second = admin_client.get(SCOPES, params={"kind": "project", "cursor": first["next_cursor"]})
    assert second.status_code == 200, second.text
    assert second.json()["next_cursor"] is None
    ids = [row["id"] for row in first["items"] + second.json()["items"]]
    assert ids == sorted([str(context.project_id), empty_project_id])
    assert (
        admin_client.get(
            SCOPES, params={"kind": "team", "cursor": first["next_cursor"]}
        ).status_code
        == 422
    )
    for kind, expected in [
        ("client", [str(context.client_id)]),
        ("team", [team_id]),
        ("responsible", [str(UUID(int=0)), str(seeded_user)]),
    ]:
        response = admin_client.get(SCOPES, params={"kind": kind})
        assert response.status_code == 200, response.text
        assert [row["id"] for row in response.json()["items"]] == expected
        assert all(set(row) == {"id", "name"} for row in response.json()["items"])
    with Session(db_engine) as db, db.begin():
        db.execute(delete(ClientAccessGrant).where(ClientAccessGrant.user_id == seeded_user))
    for kind in ["project", "client", "team", "responsible"]:
        response = admin_client.get(SCOPES, params={"kind": kind})
        assert response.status_code == 200, response.text
        assert response.json() == {"items": [], "next_cursor": None}


def test_workload_labels_counts_and_overview_share_one_statement_snapshot(
    admin_client, db_engine, seeded_user
):
    context = principal_rows(admin_client, db_engine, seeded_user)
    reports = []

    def concurrent_change(
        connection, cursor, statement, parameters, execution_context, executemany
    ):
        if "analytics_overview AS" not in statement:
            return
        reports.append(statement)
        with Session(db_engine) as db, db.begin():
            db.get(User, UUID(int=0)).display_name = "Changed after snapshot"
            db.get(WorkItem, context.work_item_id).owner_id = seeded_user
            db.execute(delete(TicketWorkItem).where(TicketWorkItem.ticket_id == context.ticket_id))

    # The HTTP app has its own engine; observe the real report statement there.
    event.listen(Engine, "after_cursor_execute", concurrent_change)
    try:
        response = admin_client.get(WORKLOAD, params=REFERENCE)
    finally:
        event.remove(Engine, "after_cursor_execute", concurrent_change)
    assert response.status_code == 200, response.text
    assert len(reports) == 1
    before = response.json()
    assert len(before["items"]) == 3
    assert before["items"][1]["name"] == "Former owner"
    assert before["items"][1]["active_work_item_count"] == 1
    assert before["overview"]["active_unified_count"] == 3
    after = admin_client.get(WORKLOAD, params=REFERENCE).json()
    assert len(after["items"]) == 2
    assert after["items"][1]["active_work_item_count"] == 2
    assert after["overview"]["active_unified_count"] == 4


@pytest.mark.parametrize("path,params", [(WORKLOAD, REFERENCE), (SCOPES, {"kind": "project"})])
def test_management_collection_endpoints_deny_bare_admin_and_anon(admin_client, path, params):
    assert admin_client.get(path, params=params).status_code == 403
    admin_client.cookies.clear()
    assert admin_client.get(path, params=params).status_code == 401


@pytest.mark.parametrize("cursor", ["!", "abc", "v1=", "a" * 321, ""])
def test_strict_collection_cursors_are_not_ignored(admin_client, db_engine, seeded_user, cursor):
    make_link_context(admin_client, db_engine, seeded_user)
    for path, params in [(WORKLOAD, REFERENCE), (SCOPES, {"kind": "project"})]:
        response = admin_client.get(path, params={**params, "cursor": cursor})
        assert response.status_code == 422, response.text


def test_collection_cursors_cannot_cross_current_authorized_actors(
    admin_client, db_engine, seeded_user
):
    context = principal_rows(admin_client, db_engine, seeded_user)
    workload_cursor = admin_client.get(WORKLOAD, params={**REFERENCE, "limit": 1}).json()[
        "next_cursor"
    ]
    scope_cursor = admin_client.get(SCOPES, params={"kind": "responsible", "limit": 1}).json()[
        "next_cursor"
    ]
    with Session(db_engine) as db, db.begin():
        admin = db.scalar(select(User).where(User.email_normalized == "admin@example.test"))
        db.add(
            ClientAccessGrant(
                user_id=admin.id,
                client_id=context.client_id,
                granted_by=admin.id,
                created_at=datetime.now(UTC),
            )
        )
        db.add(
            RoleBinding(
                user_id=admin.id,
                scope_kind="client",
                client_id=context.client_id,
                role_name="operations_manager",
            )
        )
        db.add(
            RoleBinding(
                user_id=admin.id,
                scope_kind="queue",
                queue_id=context.queue_id,
                role_name="operations_manager",
            )
        )
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(WORKLOAD, params=REFERENCE).status_code == 200
    assert (
        admin_client.get(WORKLOAD, params={**REFERENCE, "cursor": workload_cursor}).status_code
        == 422
    )
    assert (
        admin_client.get(SCOPES, params={"kind": "responsible", "cursor": scope_cursor}).status_code
        == 422
    )


def test_cursor_rank_uuid_shape_cannot_confuse_null_with_real_zero_uuid(
    admin_client, db_engine, seeded_user
):
    principal_rows(admin_client, db_engine, seeded_user)
    for path, params in [(WORKLOAD, REFERENCE), (SCOPES, {"kind": "responsible"})]:
        original = admin_client.get(path, params={**params, "limit": 1}).json()["next_cursor"]
        fields = base64.urlsafe_b64decode(original + "=" * (-len(original) % 4)).decode().split("|")
        corruptions = (
            [(0, "v2"), (2, "2"), (3, str(seeded_user))] if path == WORKLOAD else [(2, "0")]
        )
        for index, replacement in corruptions:
            changed = fields.copy()
            changed[index] = replacement
            encoded = base64.urlsafe_b64encode("|".join(changed).encode()).decode().rstrip("=")
            assert admin_client.get(path, params={**params, "cursor": encoded}).status_code == 422


def test_many_links_and_same_uuid_in_separate_domains_do_not_collapse_native_work(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    standalone_id = uuid4()
    with Session(db_engine) as db, db.begin():
        original = db.get(Ticket, context.ticket_id)
        for identifier in [context.work_item_id, standalone_id]:
            db.add(
                Ticket(
                    id=identifier,
                    client_id=context.client_id,
                    queue_id=context.queue_id,
                    requester_id=original.requester_id,
                    subject="Native independent ticket",
                    priority="medium",
                )
            )
        db.add(
            WorkItem(
                id=context.ticket_id, project_id=context.project_id, title="Native independent work"
            )
        )
    connect(admin_client, context.ticket_id, context.work_item_id)
    connect(admin_client, context.ticket_id, context.ticket_id)
    connect(admin_client, context.work_item_id, context.work_item_id)
    value = report(admin_client)
    assert value["work_item_count"] == value["represented_ticket_count"] == 2
    assert value["ticket_count"] == value["unified_count"] == 3
    assert value["standalone_ticket_count"] == 1
    assert value["sla_unconfigured_ticket_count"] == 1
    assert value["sla_legacy_ticket_count"] == 2
    with Session(db_engine) as db, db.begin():
        work = db.get(WorkItem, context.work_item_id)
        work.status, work.completed_at = "done", datetime.now(UTC)
    current = report(admin_client)
    assert current["active_work_item_count"] == 1 and current["active_ticket_count"] == 3
    assert current["active_unified_count"] == 3 and current["unified_count"] == 3


def test_project_membership_and_manager_binding_are_both_required_despite_team_metadata(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        team_id = db.get(Project, context.project_id).team_id
        db.execute(
            delete(RoleBinding).where(
                RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "client"
            )
        )
        db.execute(
            delete(ProjectMember).where(
                ProjectMember.project_id == context.project_id, ProjectMember.user_id == seeded_user
            )
        )
        db.add(
            RoleBinding(
                user_id=seeded_user,
                scope_kind="team",
                team_id=team_id,
                role_name="operations_manager",
            )
        )
    value = report(admin_client)
    assert value["work_item_count"] == 0 and value["ticket_count"] == 1
    response = admin_client.get(SCOPES, params={"kind": "project"})
    assert response.status_code == 200 and response.json()["items"] == []


def test_archived_managed_contexts_remain_readable_without_turning_inactive_metadata_into_a_grant(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        project_row = db.get(Project, context.project_id)
        project_row.active = False
        db.get(Team, project_row.team_id).active = False
        db.get(Client, context.client_id).active = False
        db.get(TicketQueue, context.queue_id).active = False
    value = report(admin_client)
    assert value["work_item_count"] == value["ticket_count"] == 1
    response = admin_client.get(SCOPES, params={"kind": "project"})
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == [str(context.project_id)]


def test_nonzero_native_distributions_and_workload_reconcile_without_state_conflation(
    admin_client, db_engine, seeded_user
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    now = datetime.now(UTC)
    with Session(db_engine) as db, db.begin():
        for status, priority, owner, ongoing, overdue in [
            ("in_progress", "high", seeded_user, False, True),
            ("blocked", "critical", seeded_user, False, False),
            ("done", "low", None, False, False),
            ("cancelled", "low", None, False, False),
            ("in_progress", "critical", None, True, False),
        ]:
            db.add(
                WorkItem(
                    project_id=context.project_id,
                    title="Synthetic status boundary",
                    status=status,
                    priority=priority,
                    owner_id=owner,
                    work_type="ongoing" if ongoing else "one_off",
                    due_at=datetime(2000, 1, 1, tzinfo=UTC) if overdue else None,
                    due_precision="instant" if overdue else None,
                    completed_at=now if status == "done" else None,
                    blocked_reason="Dependency" if status == "blocked" else None,
                )
            )
        original = db.get(Ticket, context.ticket_id)
        for status, priority, owner in [
            ("open", "high", seeded_user),
            ("pending_customer", "medium", seeded_user),
            ("pending_third_party", "low", None),
            ("resolved", "critical", None),
            ("closed", "critical", None),
        ]:
            db.add(
                Ticket(
                    client_id=context.client_id,
                    queue_id=context.queue_id,
                    requester_id=original.requester_id,
                    subject="Synthetic ticket state",
                    status=status,
                    priority=priority,
                    assignee_id=owner,
                    resolved_at=now if status in {"resolved", "closed"} else None,
                    closed_at=now if status == "closed" else None,
                )
            )
    value = report(admin_client)
    assert value["work_item_count"] == value["ticket_count"] == 6
    assert value["active_work_item_count"] == value["active_ticket_count"] == 4
    assert value["all_missing_deadline_count"] == 5
    assert value["unassigned_work_item_count"] == value["unassigned_ticket_count"] == 2
    assert value["active_no_due_date_count"] == 2
    assert value["ongoing_work_item_count"] == value["overdue_work_item_count"] == 1
    assert value["blocked_work_item_count"] == value["pending_customer_ticket_count"] == 1
    assert value["pending_third_party_ticket_count"] == 1
    assert value["unified_count"] == 12 and value["active_unified_count"] == 8
    assert value["work_status_counts"] == {
        "todo": 1,
        "in_progress": 2,
        "blocked": 1,
        "done": 1,
        "cancelled": 1,
    }
    assert value["ticket_status_counts"] == {
        "new": 1,
        "open": 1,
        "pending_customer": 1,
        "pending_third_party": 1,
        "resolved": 1,
        "closed": 1,
    }
    assert value["work_priority_counts"] == {"low": 2, "medium": 1, "high": 1, "critical": 2}
    assert value["ticket_priority_counts"] == {"low": 1, "medium": 1, "high": 2, "critical": 2}
    workload = admin_client.get(WORKLOAD, params=REFERENCE)
    assert workload.status_code == 200, workload.text
    rows = workload.json()["items"]
    assert len(rows) == 2
    for name in [
        "active_work_item_count",
        "active_ticket_count",
        "blocked_work_item_count",
        "ongoing_work_item_count",
        "active_no_due_date_count",
        "overdue_work_item_count",
        "due_soon_work_item_count",
        "later_due_work_item_count",
    ]:
        assert sum(row[name] for row in rows) == value[name]
