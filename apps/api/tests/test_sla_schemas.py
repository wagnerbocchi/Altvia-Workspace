"""Reject hostile SLA inputs before native configuration ownership."""

from uuid import uuid4

import pytest
from altvia.sla_schemas import CalendarCreate, CalendarPatch, PolicyCreate, PolicyPatch
from pydantic import ValidationError


def calendar(**changes):
    return {
        "client_id": str(uuid4()),
        "name": "Calendar",
        "active": True,
        "timezone": "UTC",
        "windows": [{"weekday": 0, "start_minute": 540, "end_minute": 1020}],
        "holidays": [],
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " \t"},
        {"name": "x\ny"},
        {"name": "x\x00y"},
        {"name": "x" * 161},
        {"active": 1},
        {"active": "true"},
        {"timezone": "../UTC"},
        {"timezone": "/UTC"},
        {"timezone": "a//UTC"},
        {"timezone": "a\\UTC"},
        {"tzif": "uploaded"},
        {"windows": []},
        {"windows": [{"weekday": True, "start_minute": 0, "end_minute": 1}]},
        {"windows": [{"weekday": 0, "start_minute": "0", "end_minute": 1}]},
        {"windows": [{"weekday": 0, "start_minute": 2, "end_minute": 1}]},
        {"windows": [{"weekday": 0, "start_minute": 0, "end_minute": 60}] * 2},
        {"holidays": [{"date": "2026-02-30"}]},
        {"holidays": [{"date": "2026-11-10T00:00:00Z"}]},
        {"holidays": [{"date": 1794268800}]},
        {"holidays": [{"date": "2026-11-10"}] * 2},
        {"holidays": [{"date": "2026-11-10", "label": "x\x00y"}]},
        {"holidays": [{"date": "2026-11-10", "label": " "}]},
        {"holidays": [{"date": "2026-11-10", "unknown": True}]},
    ],
)
def test_calendar_rejects_coercion_paths_raw_artifacts_and_ambiguous_civil_time(changes):
    with pytest.raises(ValidationError):
        CalendarCreate.model_validate(calendar(**changes))


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"active": None},
        {"holidays": None},
        {"timezone": None},
        {"client_id": str(uuid4())},
        {"version": 2},
        {"tzif_sha256": "0" * 64},
    ],
)
def test_calendar_patch_preserves_scope_and_requires_nonempty_nonnull_intent(body):
    with pytest.raises(ValidationError):
        CalendarPatch.model_validate(body)


def policy(**changes):
    return {
        "client_id": str(uuid4()),
        "name": "Policy",
        "calendar_id": str(uuid4()),
        "calendar_version": 1,
        "first_response_minutes": 60,
        "resolution_minutes": 240,
        "approach_minutes": 15,
        "pause_states": [],
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": True},
        {"authorizer_id": str(uuid4())},
        {"calendar_version": True},
        {"calendar_version": 2147483648},
        {"first_response_minutes": 0},
        {"resolution_minutes": 525601},
        {"approach_minutes": -1},
        {"first_response_minutes": "60"},
        {"resolution_minutes": 1.5},
        {"pause_states": [None]},
        {"pause_states": ["open"]},
        {"pause_states": ["pending_customer"] * 2},
        {"priority": "urgent"},
    ],
)
def test_policy_rejects_activation_grants_coercion_and_unbounded_targets(changes):
    with pytest.raises(ValidationError):
        PolicyCreate.model_validate(policy(**changes))


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"enabled": None},
        {"enabled": 1},
        {"calendar_id": str(uuid4())},
        {"calendar_version": 1},
        {"category_id": str(uuid4())},
        {"priority": "high"},
        {"pause_states": None},
    ],
)
def test_policy_patch_requires_reviewed_calendar_pair_and_immutable_selector(body):
    with pytest.raises(ValidationError):
        PolicyPatch.model_validate(body)


def test_canonical_calendar_and_explicit_patch_field_presence():
    output = CalendarCreate.model_validate(
        calendar(
            windows=[
                {"weekday": 0, "start_minute": 60, "end_minute": 120},
                {"weekday": 0, "start_minute": 0, "end_minute": 60},
            ],
            holidays=[{"date": "2026-11-11"}, {"date": "2026-11-10", "label": None}],
        )
    )
    assert [w.model_dump() for w in output.windows] == [
        {"weekday": 0, "start_minute": 0, "end_minute": 120}
    ]
    assert [h.date for h in output.holidays] == ["2026-11-10", "2026-11-11"]
    assert CalendarPatch(name="Name").model_dump(exclude_unset=True) == {"name": "Name"}
    assert CalendarPatch(timezone="UTC").model_dump(exclude_unset=True) == {"timezone": "UTC"}
    assert (
        PolicyCreate.model_validate(
            policy(first_response_minutes=525600, resolution_minutes=1, approach_minutes=525600)
        ).resolution_minutes
        == 1
    )
