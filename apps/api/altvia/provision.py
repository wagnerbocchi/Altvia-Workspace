"""One-off owner-side migrations and least-privilege API login provisioning."""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg import Error as PsycopgError
from psycopg import sql
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from altvia.attachment_scan import RETRY_UPDATES, SCAN_COLUMNS, SCAN_UPDATES
from altvia.attachments import CASE_FILE_COLUMNS
from altvia.config import Settings
from altvia.database import make_engine
from altvia.mail_cases import READ_COLUMNS, ROUTING_COLUMNS

CRUD_TABLES = (
    "users",
    "sessions",
    "roles",
    "role_bindings",
    "teams",
    "team_members",
    "idempotency_records",
    "login_buckets",
    "clients",
    "client_access_grants",
    "operational_areas",
    "projects",
    "project_members",
    "work_items",
    "work_item_assignees",
)


ROLE_PRIVILEGES = {
    "altvia_app": {
        **{table: {"SELECT", "INSERT", "UPDATE", "DELETE"} for table in CRUD_TABLES},
        "client_contacts": {"SELECT", "INSERT", "UPDATE"},
        "project_milestones": {"SELECT", "INSERT", "UPDATE"},
        "ticket_queues": {"SELECT", "INSERT", "UPDATE"},
        "ticket_categories": {"SELECT", "INSERT", "UPDATE"},
        "tickets": {"SELECT", "INSERT", "UPDATE"},
        "ticket_work_items": {"SELECT", "INSERT", "DELETE"},
        "ticket_status_history": {"SELECT", "INSERT"},
        "attachments": {"SELECT", "INSERT"},
        "ticket_notes": {"SELECT", "INSERT"},
        "ticket_messages": {"SELECT", "INSERT"},
        "ticket_message_attachments": {"SELECT", "INSERT"},
        "ticket_note_attachments": {"SELECT", "INSERT"},
        "work_comment_attachments": {"SELECT", "INSERT"},
        "ticket_incoming_messages": {"SELECT", "INSERT"},
        "mail_senders": {"SELECT"},
        "ticket_mail_threads": {"SELECT", "INSERT"},
        "outbound_messages": {"SELECT", "INSERT"},
        "work_item_external_participants": {"SELECT", "INSERT", "DELETE"},
        "audit_logs": {"INSERT"},
        "outbox_events": {"INSERT"},
        "activity_events": {"SELECT"},
        "work_item_comments": {"SELECT", "INSERT"},
        "work_item_status_history": {"SELECT", "INSERT"},
    },
    "altvia_worker": {
        "outbox_events": {"SELECT", "INSERT"},
        "outbound_messages": {"SELECT"},
        "attachment_scan_attempts": {"SELECT", "INSERT"},
        "mail_senders": {"SELECT"},
        "processed_events": {"SELECT", "INSERT"},
        "activity_events": {"SELECT", "INSERT"},
        "audit_logs": {"INSERT"},
    },
}


APP_COLUMN_READS = {
    "mail_triage_cases": READ_COLUMNS | ROUTING_COLUMNS | CASE_FILE_COLUMNS,
    "ticket_participants": {"id", "ticket_id", "contact_id", "email", "active", "version"},
}
APP_COLUMN_UPDATES = {
    "mail_triage_cases": {"state", "version", "ticket_id", "incoming_message_id"},
    "attachments": RETRY_UPDATES,
}
WORKER_COLUMN_READS = {
    # Incoming file publication adds no worker parent/name/case privileges.
    # Creation-only case-set triggers must not run on these scan updates.
    "attachments": SCAN_COLUMNS,
    "users": {"id", "active"},
    "tickets": {"id", "client_id", "queue_id", "requester_id", "assignee_id", "status"},
    "role_bindings": {"user_id", "scope_kind", "queue_id", "role_name"},
    "client_access_grants": {"user_id", "client_id"},
    "clients": {"id", "active"},
    "teams": {"id", "active"},
    "ticket_queues": {"id", "team_id", "active"},
    "client_contacts": {"id", "client_id", "active", "email_normalized"},
    "ticket_participants": {"id", "ticket_id", "contact_id", "email", "active"},
}
DELIVERY_STATUS_COLUMNS = {
    "state",
    "attempts",
    "version",
    "next_attempt_at",
    "lease_token",
    "lease_until",
    "last_error_code",
    "accepted_at",
}
WORKER_STATUS_COLUMNS = {"status", "attempts", "next_attempt_at", "lease_until", "last_error_code"}


def provision_runtime(engine: Engine, runtime_url: str, worker_url: str | None = None) -> None:
    # Both credential updates/grant sets share one transaction. Any refused
    # elevation or malformed second credential rolls back the complete operation.
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(723504392)"))
        _provision_role(connection, engine, runtime_url, "altvia_app")
        if worker_url is not None:
            _provision_role(connection, engine, worker_url, "altvia_worker")


def _provision_role(connection: Connection, engine: Engine, login_url: str, name: str) -> None:
    runtime = make_url(login_url)
    owner = engine.url
    if (
        runtime.drivername != "postgresql+psycopg"
        or runtime.username != name
        or not runtime.password
        or owner.username == name
        or not owner.database
        or (runtime.host, runtime.port or 5432, runtime.database)
        != (owner.host, owner.port or 5432, owner.database)
        or runtime.query != owner.query
    ):
        raise ValueError("Runtime credential must use the fixed role and same database target")
    privileges = ROLE_PRIVILEGES[name]
    role = connection.execute(
        text(
            "SELECT oid,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
            "FROM pg_roles WHERE rolname=:name"
        ),
        {"name": name},
    ).one_or_none()
    if role is not None:
        inherited = connection.scalar(
            text("SELECT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=:oid)"),
            {"oid": role.oid},
        )
        owns = connection.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_shdepend WHERE "
                "refclassid='pg_authid'::regclass AND refobjid=:oid AND deptype='o')"
            ),
            {"oid": role.oid},
        )
        if any(role[1:]) or inherited or owns:
            raise ValueError("Existing runtime role is elevated; explicit review required")
        ddl = connection.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_database d, LATERAL aclexplode(d.datacl) a "
                "WHERE d.datname=current_database() AND a.grantee=:oid "
                "AND a.privilege_type IN ('CREATE','TEMPORARY')) OR "
                "EXISTS(SELECT 1 FROM pg_namespace n, LATERAL aclexplode(n.nspacl) a "
                "WHERE a.grantee=:oid AND a.privilege_type='CREATE')"
            ),
            {"oid": role.oid},
        )
        if ddl:
            raise ValueError("Existing runtime role has DDL privileges; explicit review required")
    # Table REVOKE does not revoke column grants. Check both ACL sources,
    # including PUBLIC, before rotating a credential or changing any grant.
    grants = connection.execute(
        text(
            "WITH grants AS ("
            "SELECT c.relname,a.grantee,a.privilege_type,a.is_grantable,NULL::name AS column_name "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace, "
            "LATERAL aclexplode(c.relacl) a WHERE n.nspname='public' UNION ALL "
            "SELECT c.relname,a.grantee,a.privilege_type,a.is_grantable,col.attname "
            "FROM pg_attribute col "
            "JOIN pg_class c ON c.oid=col.attrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace, "
            "LATERAL aclexplode(col.attacl) a WHERE n.nspname='public') "
            "SELECT * FROM grants WHERE grantee=0 OR grantee=:oid"
        ),
        {"oid": role.oid if role is not None else -1},
    )
    if any(
        g.grantee == 0
        or g.is_grantable
        or not (
            g.privilege_type in privileges.get(g.relname, set())
            or (
                name == "altvia_app"
                and (
                    (
                        g.privilege_type == "SELECT"
                        and g.column_name in APP_COLUMN_READS.get(g.relname, set())
                    )
                    or (
                        g.privilege_type == "UPDATE"
                        and g.column_name in APP_COLUMN_UPDATES.get(g.relname, set())
                    )
                )
            )
            or (
                name == "altvia_worker"
                and (
                    (
                        g.privilege_type == "SELECT"
                        and g.column_name in WORKER_COLUMN_READS.get(g.relname, set())
                    )
                    or (
                        g.privilege_type == "UPDATE"
                        and g.column_name
                        in (
                            {
                                "outbox_events": WORKER_STATUS_COLUMNS,
                                "outbound_messages": DELIVERY_STATUS_COLUMNS,
                                "attachments": SCAN_UPDATES,
                            }.get(g.relname, set())
                        )
                    )
                )
            )
        )
        for g in grants
    ):
        raise ValueError("Unexpected runtime/PUBLIC table or column ACL; explicit review required")
    raw = connection.connection.driver_connection
    assert raw is not None and owner.database is not None
    # PostgreSQL role DDL does not accept bind parameters for PASSWORD.
    # psycopg's Literal quotes it safely, without shell or string interpolation.
    statement = (
        "CREATE ROLE {} LOGIN PASSWORD {}" if role is None else "ALTER ROLE {} LOGIN PASSWORD {}"
    )
    raw.execute(sql.SQL(statement).format(sql.Identifier(name), sql.Literal(runtime.password)))
    raw.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(owner.database))
    )
    raw.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(owner.database), sql.Identifier(name)
        )
    )
    raw.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM PUBLIC"))
    raw.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(sql.Identifier(name)))
    raw.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(name)))
    raw.execute(
        sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(sql.Identifier(name))
    )
    for table, allowed in privileges.items():
        raw.execute(
            sql.SQL("GRANT {} ON {} TO {}").format(
                sql.SQL(",".join(sorted(allowed))),
                sql.Identifier("public", table),
                sql.Identifier(name),
            )
        )
    if name == "altvia_app":
        for table, columns in APP_COLUMN_READS.items():
            raw.execute(
                sql.SQL("GRANT SELECT ({}) ON {} TO altvia_app").format(
                    sql.SQL(",").join(sql.Identifier(c) for c in sorted(columns)),
                    sql.Identifier("public", table),
                )
            )
    if name == "altvia_app":
        for table, columns in APP_COLUMN_UPDATES.items():
            raw.execute(
                sql.SQL("GRANT UPDATE ({}) ON {} TO altvia_app").format(
                    sql.SQL(",").join(sql.Identifier(c) for c in sorted(columns)),
                    sql.Identifier("public", table),
                )
            )
    if name == "altvia_worker":
        raw.execute(
            sql.SQL("GRANT UPDATE ({}) ON public.attachments TO altvia_worker").format(
                sql.SQL(",").join(sql.Identifier(c) for c in sorted(SCAN_UPDATES))
            )
        )
        for table, columns in WORKER_COLUMN_READS.items():
            raw.execute(
                sql.SQL("GRANT SELECT ({}) ON {} TO altvia_worker").format(
                    sql.SQL(",").join(sql.Identifier(c) for c in sorted(columns)),
                    sql.Identifier("public", table),
                )
            )
        raw.execute(
            sql.SQL("GRANT UPDATE ({}) ON public.outbound_messages TO altvia_worker").format(
                sql.SQL(",").join(sql.Identifier(c) for c in sorted(DELIVERY_STATUS_COLUMNS))
            )
        )
        raw.execute(
            sql.SQL("GRANT UPDATE ({}) ON public.outbox_events TO altvia_worker").format(
                sql.SQL(",").join(
                    sql.Identifier(column) for column in sorted(WORKER_STATUS_COLUMNS)
                )
            )
        )


def main() -> int:
    engine = None
    try:
        settings = Settings()
        runtime_url = Path("/run/secrets/ALTVIA_RUNTIME_DATABASE_URL").read_text().strip()
        engine = make_engine(settings)
        command.upgrade(Config("apps/api/alembic.ini"), "head")
        worker_path = Path("/run/secrets/ALTVIA_WORKER_DATABASE_URL")
        worker_url = worker_path.read_text().strip() if worker_path.is_file() else None
        provision_runtime(engine, runtime_url, worker_url)
    except (SQLAlchemyError, PsycopgError, ValidationError, ValueError, OSError):
        print(
            "Migration or runtime-role provisioning failed; inspect configuration safely.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print("Migrations and runtime-role provisioning completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
