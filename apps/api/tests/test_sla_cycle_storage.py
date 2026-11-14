"""Native cycle constraints, guarded contraction and unchanged incumbent schema."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia.models import AuditLog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_automation_rules import rule_context
from test_sla_execution import tracked
from test_team_api import admin_client

__all__ = ["admin_client", "rule_context"]


def test_native_cycle_foreign_keys_and_progress_bounds(admin_client, db_engine, rule_context):
    tracked(admin_client, db_engine, rule_context)
    cases = [
        ("UPDATE ticket_sla_states SET queue_id=:foreign", "23503"),
        ("UPDATE ticket_sla_states SET policy_version=1234", "23503"),
        ("UPDATE ticket_sla_states SET start_version=1234", "23503"),
        ("UPDATE ticket_sla_states SET cycle_number=0", "23514"),
        ("UPDATE ticket_sla_states SET first_response_at=now()", "23514"),
        ("UPDATE ticket_sla_goals SET last_history_version=1234", "23503"),
        ("UPDATE ticket_sla_goals SET elapsed_us=-1", "23514"),
        ("UPDATE ticket_sla_goals SET outcome='success'", "23514"),
        ("UPDATE ticket_sla_goals SET search_remaining_us=0", "23514"),
    ]
    for statement, code in cases:
        with db_engine.begin() as connection, pytest.raises(DBAPIError) as error:
            connection.execute(text(statement), {"foreign": uuid4()})
        assert error.value.orig.sqlstate == code
    with pytest.raises(DBAPIError, match="Cannot contract ticket SLA snapshots/history"):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000031")
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "b46087000032"


def test_rejected_acceptance_audit_alone_refuses_contraction(db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        db.add(
            AuditLog(
                actor_id=None,
                action="sla.acceptance_rejected",
                resource_id=uuid4(),
                occurred_at=datetime.now(UTC),
                correlation_id=uuid4().hex,
                details={"error_code": "source_invalid"},
            )
        )
    with pytest.raises(DBAPIError, match="Cannot contract ticket SLA snapshots/history"):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000031")


def test_empty_cycle_roundtrip_preserves_incumbent_identity_and_metadata(db_engine, seeded_user):
    with db_engine.connect() as connection:
        before = connection.scalar(text("SELECT count(*) FROM users"))
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000031")
    command.upgrade(config, "head")
    command.check(config)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM users")) == before
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_states")) == 0


def test_legacy_fixture_never_removes_a_configured_obligation(
    admin_client, db_engine, rule_context
):
    from sla_migration_support import pre_sla_ticket

    path, _, _, _ = tracked(admin_client, db_engine, rule_context)
    with pytest.raises(AssertionError):
        pre_sla_ticket(db_engine, path)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_states")) == 1
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_goals")) == 2
