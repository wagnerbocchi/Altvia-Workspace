"""One-off owner-side migrations and least-privilege API login provisioning."""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg import Error as PsycopgError
from psycopg import sql
from pydantic import ValidationError
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from altvia.config import Settings
from altvia.database import make_engine

CRUD_TABLES = (
    "users",
    "sessions",
    "roles",
    "role_bindings",
    "teams",
    "team_members",
    "idempotency_records",
    "login_buckets",
)


def provision_runtime(engine: Engine, runtime_url: str) -> None:
    runtime = make_url(runtime_url)
    owner = engine.url
    if (
        runtime.drivername != "postgresql+psycopg"
        or runtime.username != "altvia_app"
        or not runtime.password
        or owner.username == runtime.username
        or not owner.database
        or (runtime.host, runtime.port or 5432, runtime.database)
        != (owner.host, owner.port or 5432, owner.database)
        or runtime.query != owner.query
    ):
        raise ValueError("Runtime credential must use the fixed role and same database target")
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(723504392)"))
        role = connection.execute(
            text(
                "SELECT oid,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
                "FROM pg_roles WHERE rolname='altvia_app'"
            )
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
        raw = connection.connection.driver_connection
        assert raw is not None and owner.database is not None
        # PostgreSQL role DDL does not accept bind parameters for PASSWORD.
        # psycopg's Literal quotes it safely, without shell or string interpolation.
        statement = (
            "CREATE ROLE altvia_app LOGIN PASSWORD {}"
            if role is None
            else ("ALTER ROLE altvia_app LOGIN PASSWORD {}")
        )
        raw.execute(sql.SQL(statement).format(sql.Literal(runtime.password)))
        raw.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(owner.database))
        )
        raw.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO altvia_app").format(
                sql.Identifier(owner.database)
            )
        )
        connection.execute(text("REVOKE ALL ON SCHEMA public FROM PUBLIC"))
        connection.execute(text("REVOKE ALL ON SCHEMA public FROM altvia_app"))
        connection.execute(text("GRANT USAGE ON SCHEMA public TO altvia_app"))
        connection.execute(text("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM altvia_app"))
        for table in CRUD_TABLES:
            raw.execute(
                sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON {} TO altvia_app").format(
                    sql.Identifier("public", table)
                )
            )
        connection.execute(text("GRANT INSERT ON audit_logs,outbox_events TO altvia_app"))


def main() -> int:
    engine = None
    try:
        settings = Settings()
        runtime_url = Path("/run/secrets/ALTVIA_RUNTIME_DATABASE_URL").read_text().strip()
        engine = make_engine(settings)
        command.upgrade(Config("apps/api/alembic.ini"), "head")
        provision_runtime(engine, runtime_url)
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
