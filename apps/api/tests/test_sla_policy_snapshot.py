"""Activation review reads the exact selected calendar, never a newer revision."""

from test_automation_rules import rule_context
from test_sla_configuration import create_calendar, create_policy, patch
from test_team_api import admin_client, sign_in

__all__ = ["admin_client", "rule_context"]


def test_policy_calendar_snapshot_is_frozen_scoped_and_distinguishes_current_eligibility(
    admin_client, rule_context
):
    calendar = create_calendar(admin_client, rule_context)
    original = admin_client.get(calendar).json()
    policy = create_policy(admin_client, rule_context, calendar)
    assert (
        patch(admin_client, calendar, name="Later calendar", active=False, holidays=[]).status_code
        == 200
    )
    response = admin_client.get(policy + "/calendar-snapshot")
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot == {
        "policy_version": 1,
        "calendar_id": original["id"],
        "version": 1,
        "name": original["name"],
        "timezone": original["timezone"],
        "windows": original["windows"],
        "holidays": original["holidays"],
        "calendar_active": False,
    }
    assert admin_client.get(policy + "/calendar-snapshot?revision=2").status_code == 422
    assert patch(admin_client, calendar, active=True).status_code == 200
    assert admin_client.get(policy + "/calendar-snapshot").json()["calendar_active"] is True
    sign_in(admin_client, "viewer@example.test")
    assert admin_client.get(policy + "/calendar-snapshot").status_code == 404
