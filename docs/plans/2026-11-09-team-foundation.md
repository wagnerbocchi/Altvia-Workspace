# Team foundation implementation plan

> For agentic workers: use superpowers:executing-plans with TDD and a fresh final
> review. Native/main execution and publishing are already user-authorized.

Goal: persisted team/roster administration through the real secure API, with
safe account lookup, optimistic concurrency and idempotent critical POSTs.

Architecture: extend the existing SQLAlchemy/Alembic identity foundation. Add a
bounded team-administration router, consolidate Origin/CSRF checks in HTTP, and
reuse the management write lock. No frontend or new dependency in this slice.

Spec: ALTVIA_WORKSPACE_SPEC_CODEX.md; docs/contracts/api.md;
docs/adr/0009-team-identity-administration.md; security requirements.

## Global constraints

- Mandatory x86-64-v1; no new native dependency or prohibited search engine.
- Secure same-origin session, current identity.manage, exact Origin and CSRF.
- Team roster membership never creates content grants or platform privileges.
- Team names 1..150 trimmed characters; UUID identity, no implicit merging.
- Version/If-Match on PATCH and roster changes; audit/outbox atomic with writes.
- Idempotency-Key on critical POSTs; replay 200, mismatched request 409.
- Only explicitly enabled disposable altvia_test for destructive test fixtures.
- Direct main commits/pushes allowed; no real team/user provisioning or deploy.

## Review focus

1. A revoked/deactivated administrator must not replay stored private outcomes.
2. Concurrent identical POSTs must create one team/membership and one event.
3. Membership changes must detect a stale team version and inactive user/team.
4. No-op, replay or failed transaction must not create duplicate/partial events.
5. Ordinary members must not read/administer other teams or gain content access.

## Task 1: Team and idempotency storage

Files: models.py, a third Alembic revision, tests/conftest.py and
tests/test_team_storage.py.

Produces: Team, TeamMember, IdempotencyRecord SQLAlchemy models, team/member
version/active/name/FK constraints and the unique actor/route/key record.

- [x] Add failing real-DB tests for persistence, positive versions/nonempty names,
  member FK/uniqueness and idempotency actor/route namespace isolation.
- [x] Observe failures before adding models/migration.
- [x] Implement schema and update only the guarded disposable fixture reset.
- [x] Run full API suite, lint/format/mypy, Alembic drift and disposable third-
  revision downgrade/upgrade; commit the coherent schema increment.

## Task 2: Authorized team API

Files: new altvia/team_api.py and tests/test_team_api.py; main.py, http.py,
management.py; generated OpenAPI/TypeScript; docs/evidence/runbook.

Consumes: Task 1 models; existing authenticate/capabilities/record_event.
Produces GET /users, GET/POST /teams, GET/PATCH /teams/{id}, GET/POST
/teams/{id}/members and DELETE /teams/{id}/members/{user_id}.

- [x] Write failing real-HTTP/DB tests for lifecycle/account lookup and all five
  review-focus cases, body/media bounds, cursor isolation, If-Match syntax,
  idempotency hash conflict, authorization-before-replay and rollback safety.
- [x] Observe absent-endpoint failures.
- [x] Implement router-owned transactions, bounded typed DTOs, shared HTTP guards,
  public lock_identity_writes helper, route-bound cursors, ETag and replay records.
  All write transactions acquire the identity lock before session authentication.
- [x] Run all API tests, lint/format/mypy/build, migration checks, export OpenAPI
  and generate/verify TS contracts; obtain fresh review and fix material defects.
- [x] Record exact evidence/limits, commit/push main and observe both Linux CIs.

## Rulings and ledger

- Ruling: this extends foundation identity metadata, not Phase 2 operational
  resources. Platform administration still has no client-content bypass.
- Ruling: identity.manage controls every route here; scoped team delegation is
  deferred until persisted scoped-role contracts are implemented.
- Pre-flight: Task 2 consumes the three Task 1 models without changing their
  signatures. Existing auth DTOs remain stable; generated files change only by
  export/generation. No UI edits require an impeccable design round.
- Final local proof: 160 tests passed; strict checks, build, migration roundtrip/
  drift and generated contracts passed. Independent review P2 schema finding
  resolved; see Phase 1C evidence for precise scope and commands.
- Task 2 complete: a5ce79a, published with schema commit030a3f2. Hosted API
  42606303304 and browser42606303427 passed. No phase-completion/VM claim.
