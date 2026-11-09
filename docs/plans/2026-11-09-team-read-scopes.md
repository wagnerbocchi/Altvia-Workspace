# Persisted team read scopes implementation plan

> For agentic workers: use superpowers:executing-plans with TDD and a fresh final
> review. Native work/main commits/pushes are already authorized. No new approval
> pause, real grant provisioning, production deployment or Phase 2 advancement.

Goal: explicit persisted team read grants with safe host administration and
resource-filtered API reads, preserving global administration and client isolation.

Architecture: extend RoleBinding in place with UUID identity and constrained team
FK scope. Reuse the existing identity management transaction protocol. Team API
read queries use a role-binding subquery before pagination; writes stay global.
Existing policy role names are reused, without speculative client/project tables.

Spec: master specification; ADR-0010; team API contract; security scope model.

## Global constraints

- Mandatory x86-64-v1, no new native/dependency service.
- Roles: viewer/operations_manager at team scope; platform_admin only global.
- Roster membership never grants roles; team roles never grant identity.manage.
- Preserve last-active-admin guard and current global auth behavior.
- Actual role changes revoke sessions and atomically append audit/outbox.
- SQL permission filtering precedes pagination; unauthorized IDs reveal no data.
- Only guarded disposable altvia_test for destructive test/migration operations.
- No schema/DTO duplication; no UI edits or client grants in this slice.

## Review focus

1. Multiple same-role team grants must coexist without broadening global rights.
2. Scope revocation must invalidate tokens and immediately remove query results.
3. Filtering after pagination must not skip authorized teams or leak cursors/data.
4. Scoped readers cannot use account lookup or administrative writes/replay.
5. Migration/downgrade and failed mutations must preserve grants/audit atomically.

## Task 1: Scoped storage and management

Files: models.py, fourth Alembic revision, management.py, policy.py;
tests/test_team_role_storage.py and tests/test_team_role_management.py.

Produces: UUID RoleBinding PK, nullable team_id FK with strict scope/role CHECK,
partial global/team uniqueness and indexed user lookup; TEAM_READ_ROLES;
set_team_role(db: Session,email: str,team_id: UUID,role: str,enabled: bool) -> bool.

- [x] Write failing real-DB tests for scope/role/FK/uniqueness, multiple teams,
  inactive grant rejection, idempotent updates, session revocation, atomic
  rollback/concurrent duplicate grants and last-global-admin invariants.
- [x] Observe missing capability/schema failures before implementation.
- [x] Implement constrained migration and service using the existing lock and
  session invalidation; preserve global grants and reject unsafe downgrade.
- [x] Run full API suite, lint/format/mypy, guarded migration preservation/
  refusal/roundtrip and drift checks; commit the coherent storage/service slice.

## Task 2: Restricted CLI and filtered API reads

Files: cli.py, team_api.py, policy.py; tests/test_team_scope_api.py and
tests/test_team_scope_cli.py, test_policy.py; contracts/runbook/evidence/roadmap.

Consumes: Task 1 signature/constraints and existing auth/CSRF/metadata DTOs.
Produces: grant-team-role/revoke-team-role commands with --team-id/--role and
email+scope confirmation; team.read policy; filtered GET teams/detail/members.

- [x] Write failing tests for both fixed roles' API isolation, filter-before-page,
  own/other rosters, ordinary membership denial, all write/user-directory denial,
  revoke/disable behavior, global-admin compatibility and CLI safe confirmations.
- [x] Observe the old global-only denial/parser/policy failures.
- [x] Implement read SQL subquery and typed team.read policy; retain identity.manage
  for all existing writes and /users. Extend the restricted parser without secret
  echo or arbitrary role/scope parameters. Global capability response stays stable.
- [x] Run the complete suite and required checks; export/verify generated contracts,
  obtain fresh read-only review and fix material findings with regression proof.
- [x] Document exact evidence/limits, commit/push main and observe both Linux CIs.

## Rulings and pre-flight

- Ruling: explicit read delegation is the safe bounded foundation increment.
  Operational/client grants, scoped writes and frontend remain separate contracts.
- Pre-flight: Task 2 uses Task 1's fixed roles and set_team_role signature; no
  auth DTO shape change, generic scope setter or conflicting interface.
