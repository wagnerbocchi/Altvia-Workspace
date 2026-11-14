"""Native bulk reconciliation and real installed database privilege boundaries."""

import json
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from altvia import analytics_queries, provision
from altvia.analytics_schemas import AnalyticsFilters, ScopeFilters, WorkloadFilters
from altvia.models import Project, RoleBinding, Ticket, TicketQueue, TicketWorkItem, WorkItem
from sqlalchemy import delete, event, literal, select
from sqlalchemy.orm import Session
from test_analytics_api import REFERENCE
from test_runtime_provision import runtime_url
from test_team_api import admin_client
from ticket_work_support import make_link_context

__all__ = ["admin_client"]


def clone(connection, model, source_id, **replacements):
    table = model.__table__
    connection.execute(
        table.insert().from_select(
            [column.name for column in table.c],
            select(
                *(
                    literal(replacements[column.name], type_=column.type)
                    if column.name in replacements
                    else column
                    for column in table.c
                )
            ).where(table.c.id == source_id),
        )
    )


def test_bulk_native_reports_use_complete_scopes_and_one_statement(
    admin_client, db_engine, seeded_user, record_testsuite_property
):
    context = make_link_context(admin_client, db_engine, seeded_user)
    work_ids = [uuid4() for _ in range(12000)]
    ticket_ids = [uuid4() for _ in range(2400)]
    hidden_project, hidden_queue = uuid4(), uuid4()
    now = datetime.now(UTC)
    # Bulk data and altered grants remain in this one rollback-only transaction.
    with db_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                delete(RoleBinding).where(
                    RoleBinding.user_id == seeded_user,
                    RoleBinding.scope_kind == "client",
                )
            )
            clone(connection, Project, context.project_id, id=hidden_project, name="Hidden project")
            clone(connection, TicketQueue, context.queue_id, id=hidden_queue, name="Hidden queue")
            connection.execute(
                WorkItem.__table__.insert(),
                [
                    {
                        "id": identifier,
                        "project_id": context.project_id if index < 6000 else hidden_project,
                        "owner_id": seeded_user if index % 2 else None,
                        "title": "Synthetic report work",
                        "status": "todo",
                        "work_type": "one_off",
                        "priority": "medium",
                        "version": 1,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for index, identifier in enumerate(work_ids)
                ],
            )
            original = (
                connection.execute(select(Ticket.__table__).where(Ticket.id == context.ticket_id))
                .mappings()
                .one()
            )
            connection.execute(
                Ticket.__table__.insert(),
                [
                    {
                        **{
                            key: value
                            for key, value in original.items()
                            if key not in {"id", "number"}
                        },
                        "id": identifier,
                        "queue_id": context.queue_id if index < 1200 else hidden_queue,
                        "category_id": None,
                        "assignee_id": seeded_user if index % 2 else None,
                    }
                    for index, identifier in enumerate(ticket_ids)
                ],
            )
            connection.execute(
                TicketWorkItem.__table__.insert(),
                [
                    {
                        "ticket_id": ticket_ids[index],
                        "work_item_id": work_ids[index],
                        "client_id": context.client_id,
                        "queue_id": context.queue_id,
                        "project_id": context.project_id,
                        "created_by": seeded_user,
                        "relation_type": "related",
                    }
                    for index in range(1200)
                ],
            )
            filters = AnalyticsFilters(**REFERENCE)
            statements = []

            def capture(_connection, _cursor, statement, parameters, _context, _many):
                if "analytics_work AS" in statement and not statement.startswith("EXPLAIN"):
                    statements.append((statement, parameters))

            event.listen(connection, "before_cursor_execute", capture)
            metrics = []
            try:
                with Session(bind=connection) as db:
                    for name, run in [
                        ("overview", lambda: analytics_queries.overview(db, seeded_user, filters)),
                        (
                            "workload",
                            lambda: analytics_queries.workload(
                                db, seeded_user, WorkloadFilters(**REFERENCE, limit=1)
                            ),
                        ),
                    ]:
                        samples = []
                        for _ in range(2):
                            previous = len(statements)
                            started = perf_counter()
                            value = run()
                            samples.append((perf_counter() - started) * 1000)
                            assert len(statements) == previous + 1
                            overview = value if name == "overview" else value.overview
                            assert overview.work_item_count == 6001
                            assert overview.ticket_count == 1201
                            assert overview.represented_ticket_count == 1200
                            assert overview.unified_count == overview.active_unified_count == 6002
                            if name == "workload":
                                assert len(value.items) == 1 and value.next_cursor is not None
                        statement, parameters = statements[-1]
                        plan = connection.exec_driver_sql(
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement,
                            parameters,
                        ).scalar_one()[0]
                        metrics.append(
                            {
                                "report": name,
                                "first_ms": samples[0],
                                "warm_ms": samples[1],
                                "plan": plan,
                            }
                        )
            finally:
                event.remove(connection, "before_cursor_execute", capture)
            record_testsuite_property("analytics_native_bulk_plans", json.dumps(metrics))
        finally:
            transaction.rollback()


def test_analytics_runs_under_existing_runtime_role_without_new_grants(
    admin_client, db_engine, seeded_user
):
    from sqlalchemy import create_engine

    context = make_link_context(admin_client, db_engine, seeded_user)
    url = runtime_url(db_engine)
    provision.provision_runtime(db_engine, url.render_as_string(hide_password=False))
    runtime = create_engine(url, hide_parameters=True)
    try:
        with Session(runtime) as db, db.begin():
            filters = AnalyticsFilters(**REFERENCE)
            analytics_queries.validate_timezone(db, filters)
            assert analytics_queries.overview(db, seeded_user, filters).work_item_count == 1
            page = analytics_queries.workload(db, seeded_user, WorkloadFilters(**REFERENCE))
            assert page.overview.ticket_count == 1 and len(page.items) == 1
            projects = analytics_queries.scopes(db, seeded_user, ScopeFilters(kind="project"))
            assert [row.id for row in projects.items] == [context.project_id]
    finally:
        runtime.dispose()
