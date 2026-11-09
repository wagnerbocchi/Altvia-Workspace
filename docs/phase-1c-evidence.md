# Phase 1C execution evidence

Date: 2026-11-09. Phase 1C-a delivers restricted identity administration.
Phase 1 is not complete. No production operation, migration or new dependency.

## Delivered behavior

The existing management service/CLI now provisions ordinary internal users with
no implicit role or client-content access. Operators can enable/disable accounts
and grant/revoke the fixed platform-admin role. Password commands retain hidden
double entry; state/role commands require typed target-email confirmation.
All commands require an interactive terminal and trusted host/DB access.

Actual state/role changes invalidate all previous sessions, increment auth_version
and write audit/outbox in the same caller-owned PostgreSQL transaction. Repeated
unchanged state creates no duplicate effect. Reactivation cannot resurrect prior
tokens. Concurrent deactivation/demotion cannot remove the last active platform
administrator. Inactive accounts cannot receive a new admin grant. Password reset
preserves roles/disabled state and continues to revoke sessions.

The existing advisory lock 723504391 serializes management mutations. User rows
use FOR NO KEY UPDATE because these operations never change keys; audit FK
key-share locks remain compatible while session revocation waits on an active
authenticated request. Bootstrap and reset reuse the same management protocol.

These are restricted host operations, not the planned HTTP administration APIs
or an employee-facing bypass. Audit identifies management_command as actor kind;
named operator attribution still depends on protected host access/audit logs.
Platform admin remains identity.manage only, without customer-content authority.

## Verification

- Task 1 RED: 19 new real-PostgreSQL service tests failed for the absent operations.
  GREEN: full suite 63 passed (43.57s); strict mypy, Ruff/format and source/wheel
  build passed. Coherent service commit: `c8e3920`.
- Task 2 tests first reproduced unsupported commands and unsafe exceptional
  paths. A synthetic password supplied to the existing reset command as an
  unknown flag was echoed by argparse. Engine construction errors also escaped
  the CLI error boundary. Both were fixed and regression-tested; no real secret
  was used in these reproductions.
- CLI parsing now redacts malformed/unknown argument values. Secret arguments,
  weak/mismatched passwords, missing/unexpected fields, noninteractive input,
  confirmation mismatch, EOF/Ctrl+C and insecure getpass fallback are rejected
  before unintended writes. Config/engine/database failures have safe output.
- `uv run --env-file .env.e2e pytest -q apps/api/tests/test_identity_cli.py --tb=short`:
  **20 passed** (12.74s).
- `uv run --env-file .env.e2e pytest -q --tb=short`: **83 passed** (56.70s).
  Includes prior identity/RBAC/HTTP/DB tests plus 39 new administration/CLI cases.
  Covers normalized duplicates/field bounds, real login without privilege,
  revocation/no resurrection, no-op deduplication, last-admin guard (including
  inactive peers), rollback and concurrent demotion or deactivation/demotion.
- `uv run ruff check apps/api`, `uv run ruff format --check apps/api`,
  `uv run mypy` and `uv build`: passed. Initial formatting findings were corrected.
- `uv run --env-file .env.e2e alembic -c apps/api/alembic.ini check`:
  no new upgrade operations. Schema and lockfiles are unchanged.
- `uv run python -m altvia.cli --help`: all seven supported commands listed.
- Fresh read-only review covered the complete service/CLI change from `3e216ff`,
  including lock compilation/interactions, transaction ownership, privilege and
  exceptional paths. No material findings. Runtime proof remains the executed
  tests above, not the reviewer's assertion.

The tests used only the explicitly enabled disposable altvia_test PostgreSQL
database and synthetic identities. The task-owned Podman DB and SSH local
forward were reused; pre-existing user containers/volumes were preserved.
No SSH/host security setting was changed. See browser/development runbooks for
this local connection path and the restricted account commands.

## Publication and remaining gates

Commits `c8e3920` (service) and `2f3298a` (CLI/runbooks) were pushed directly to
main, without PR, under existing authorization. Both Linux workflows passed:

- [API checks 42598033063](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42598033063):
  full API suite, lint/format/mypy, migrations/drift and source/wheel build.
- [Browser checks 42598033094](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42598033094):
  clean locked install, Sharp exclusion, generated-contract drift guard, web
  lint/types/production build, dependency audit and all 7 HTTPS/PostgreSQL E2E tests.

The browser run retained an existing tooling annotation: pnpm/action-setup v4
declares Node 20 and GitHub forces it to Node 24. The action and all required
steps succeeded; updating its declared runtime belongs to CI maintenance. This
does not establish the application runtime's target-VM CPU compatibility.

HTTP account mutation and scoped team roles/client grants, durable worker/outbox
delivery, Redis, Compose/ingress/non-root images, full security/image scanning,
target CPU/native-runtime homologation and recovery/load evidence remain open.
No Phase 2 advancement, production readiness or deployment is claimed.

Rollback of this development increment is Git revert; no schema rollback is
needed. Real administrative changes are stateful security operations: do not
undo them by database rollback or revive revoked sessions. Use an explicit,
audited state/role/password change under the management guard.

## Phase 1C-b: persisted team identity API

The next foundation slice adds team identity/roster administration and safe
internal account selection. ADR-0009 explicitly distinguishes globally managed
identity metadata from scoped operational/client content. Every route requires
current identity.manage. A team membership creates no role or client access.
This does not implement HTTP account/password/role mutation or an admin frontend.

Migration b46087000003 persists teams, team_members and idempotency_records.
Teams retain positive versions, active state and timestamps. Member uniqueness/FKs
and inactive history are enforced. Idempotency namespace is actor/route/key, with
at least 168 elapsed hours of retention independent of DB session DST. The third
revision was corrected before first publication and reapplied only to disposable
synthetic data; no published/production migration was rewritten.

Implemented GET /users, GET/POST /teams, GET/PATCH /teams/{id}, GET/POST
/teams/{id}/members and DELETE /teams/{id}/members/{user_id}. Metadata/roster
writes use exact Origin, CSRF, current session/capability and the shared identity
write lock before session authentication. They atomically update version and
append audit/outbox with actor/target member IDs. No hard-delete endpoint. Archive
preserves rosters; inactive team/account checks prevent unintended activation.

Critical POSTs require Idempotency-Key; matching replay returns the historical
outcome only after current authorization. Replays/no-ops do not duplicate domain
events, and a later membership removal is never undone by replaying its old add.
PATCH/roster writes require If-Match; real stale/concurrent edits reject 409.
Collections have route/team-bound cursors, bounded UUID pagination and reject
unsupported filters. Request JSON is bounded before parsing. Readiness now detects
missing required schema without requiring audit-table data-read permissions.

### Executed evidence and review

- Storage RED: 15 absent-model failures. Full foundation GREEN: 98 passed
  (65.43s), strict mypy/Ruff and Alembic drift. Local schema commit `030a3f2`.
- Guarded disposable downgrade to b46087000002, upgrade head and drift check
  passed. Storage cases rerun after restoration: 15 passed (7.10s).
- HTTP RED: missing GET /users returned404. Initial 53 real ASGI-HTTP/PostgreSQL
  cases passed (116.28s), followed by additional failing cases for unsupported
  filters and missing-schema readiness. Those were corrected and full156 passed.
- A deterministic non-UTC database DST test reproduced a calendar-day retention
  constraint rejecting seven elapsed days. Constraint corrected to 168 hours;
  guarded revision reapplied, DST test and full157 suite passed (190.45s).
- Fresh read-only review inspected source/migration, authorization, lock order,
  atomicity, version/replay isolation, generated schema and exceptional inputs.
  It found a P2 contract mismatch: PATCH schema allowed null/empty objects that
  runtime rejected. Two contract tests failed before the fix; optional fields
  now use SkipJsonSchema[None] and minProperties=1. OpenAPI/TS were regenerated.
  The reviewer scored its finding resolved and independently ran all three pure
  schema contract tests successfully. No concurrent DB tests were run by reviewer.
- Final `uv run --env-file .env.e2e pytest -q --tb=short`: **160 passed**
  (192.09s). Includes 83 prior cases, 16 team-storage, 58 team-HTTP and 3 contract
  cases. Proof covers all eight routes' anonymous/member denial, CSRF/Origin,
  safe account output, metadata/roster lifecycle, no implicit privileges, replay
  after role/account revocation, actor/route namespace separation, concurrent
  identical/conflicting creation and membership retry, stale edits, no-op,
  rollback on failed outbox insert, inactive targets, body/media/query bounds,
  cursor isolation and missing-schema readiness.
- `uv run ruff check apps/api`, `uv run ruff format --check apps/api`, strict
  mypy (11 source files), `uv build` and Alembic drift: passed. Initial formatting
  and model-import typing findings were corrected.
- `uv run python scripts/export_openapi.py`, generated TypeScript, frontend
  type/lint checks and production build passed. No UI implementation changed.
  `node scripts/check_web_native.mjs` passed; no native dependency was added.

All data and DDL failure-injection/roundtrip tests used only guarded altvia_test
and synthetic identities. The tests above exercise real handlers and PostgreSQL
through ASGI; they are not target-VM or production TLS/load proof. Hosted API and
browser publication evidence follows after the completed increment is pushed.

Worker/outbox delivery, Redis/Compose/ingress/non-root images, persisted scoped
role/client grants, HTTP account mutation/admin UI, full security/image gates and
actual target-CPU/recovery/load evidence remain open. Phase 1 is not complete.
