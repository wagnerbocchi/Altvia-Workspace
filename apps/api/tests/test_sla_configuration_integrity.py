"""Selected calendar eligibility and missing-current-revision failure boundaries."""

from uuid import UUID

import pytest
from altvia import identity, sla_configuration
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_automation_rules import rule_context
from test_sla_configuration import create_calendar, create_policy, patch
from test_team_api import admin_client

__all__ = ["admin_client", "rule_context"]


def test_current_calendar_eligibility_preserves_explicit_historical_math_revision(
    admin_client, rule_context
):
    calendar = create_calendar(admin_client, rule_context, active=False)
    assert patch(admin_client, calendar, active=True).status_code == 200
    policy = create_policy(admin_client, rule_context, calendar, calendar_version=1)
    assert patch(admin_client, policy, enabled=True).status_code == 200
    assert admin_client.get(policy).json()["calendar_version"] == 1


def test_missing_current_policy_revision_fails_closed_instead_of_falling_back(
    admin_client, db_engine, rule_context
):
    refs = rule_context
    calendar = create_calendar(admin_client, refs)
    default = create_policy(admin_client, refs, calendar)
    exact = create_policy(admin_client, refs, calendar, priority="high")
    assert patch(admin_client, default, enabled=True).status_code == 200
    assert patch(admin_client, exact, enabled=True).status_code == 200
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE sla_policies SET version=3 WHERE id=:id"),
            {"id": UUID(exact.rsplit("/", 1)[1])},
        )
    with Session(db_engine) as db, pytest.raises(identity.IdentityError) as error:
        sla_configuration.select_revision(
            db, UUID(refs["client_id"]), UUID(refs["queue_id"]), UUID(refs["category_id"]), "high"
        )
    assert error.value.status == 503 and error.value.code == "sla_configuration_unavailable"
