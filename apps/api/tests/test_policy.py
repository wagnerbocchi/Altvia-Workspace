from uuid import UUID

import pytest
from altvia.policy import Binding, Principal, Resource, can

U, C, P, T, Q, OTHER = (UUID(int=i) for i in range(1, 7))
RESOURCE = Resource(client_id=C, project_id=P, team_id=T, queue_id=Q, owner_id=U)


@pytest.mark.parametrize(
    ("role", "scope", "scope_id", "action", "clients", "projects", "expected"),
    [
        ("operations_manager", "team", T, "work.update", {C}, set(), False),
        ("operations_manager", "team", T, "work.read", set(), set(), False),
        ("operations_manager", "team", OTHER, "work.read", {C}, set(), False),
        ("project_manager", "project", P, "work.update", {C}, set(), False),
        ("project_manager", "project", P, "ticket.reply", {C}, set(), False),
        ("agent", "project", P, "work.update", {C}, {P}, True),
        ("agent", "project", P, "work.update", {C}, set(), False),
        ("viewer", "project", P, "work.read", {C}, set(), False),
        ("viewer", "project", P, "work.update", {C}, set(), False),
        ("platform_admin", "global", None, "work.read", {C}, {P}, False),
        ("agent", "queue", Q, "ticket.reply", {C}, set(), True),
        ("agent", "queue", Q, "role.manage", {C}, set(), False),
    ],
)
def test_policy_requires_action_scope_and_client_ceiling(
    role, scope, scope_id, action, clients, projects, expected
):
    principal = Principal(
        U, True, (Binding(role, scope, scope_id),), frozenset(clients), frozenset(projects)
    )
    assert can(principal, action, RESOURCE) is expected


def test_assigned_work_does_not_grant_a_role():
    assert not can(Principal(U, True, client_ids=frozenset({C})), "work.update", RESOURCE)


@pytest.mark.parametrize(
    "role,scope,member,read,manage",
    [
        ("operations_manager", "client", False, True, True),
        ("viewer", "client", False, True, False),
        ("operations_manager", "team", True, False, False),
        ("viewer", "team", True, False, False),
        ("project_manager", "project", True, True, True),
        ("project_manager", "project", False, False, False),
        ("agent", "project", True, True, False),
        ("viewer", "project", False, False, False),
    ],
)
def test_project_policy_is_not_team_identity_metadata(role, scope, member, read, manage):
    identifier = {"client": C, "team": T, "project": P}[scope]
    principal = Principal(
        U,
        True,
        (Binding(role, scope, identifier),),
        frozenset({C}),
        frozenset({P}) if member else frozenset(),
    )
    assert can(principal, "project.read", RESOURCE) is read
    assert can(principal, "project.manage", RESOURCE) is manage


def test_inactive_manager_cannot_read():
    principal = Principal(U, False, (Binding("operations_manager", "team", T),), frozenset({C}))
    assert not can(principal, "work.read", RESOURCE)


def test_agent_cannot_edit_someone_elses_task():
    principal = Principal(
        U, True, (Binding("agent", "project", P),), frozenset({C}), frozenset({P})
    )
    resource = Resource(C, P, T, owner_id=OTHER)
    assert not can(principal, "work.update", resource)


@pytest.mark.parametrize(
    "role,scope,scope_id,allowed",
    [
        ("viewer", "team", T, True),
        ("operations_manager", "team", T, True),
        ("platform_admin", "global", None, True),
        ("platform_admin", "global", T, False),
        ("viewer", "team", OTHER, False),
        ("viewer", "global", None, False),
        ("agent", "team", T, False),
        ("viewer", "project", T, False),
    ],
)
def test_team_read_policy_is_explicit_metadata_only(role, scope, scope_id, allowed):
    principal = Principal(U, True, (Binding(role, scope, scope_id),), frozenset({C}))
    assert can(principal, "team.read", Resource(None, team_id=T)) is allowed
    assert not can(principal, "team.read", Resource(C, team_id=T))
    assert not can(principal, "team.read", Resource(None))
    assert not can(Principal(U, False, principal.bindings), "team.read", Resource(None, team_id=T))
    assert not can(principal, "identity.manage", Resource(None, team_id=T))
