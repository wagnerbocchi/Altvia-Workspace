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

Publication evidence follows after pushing the completed increment and observing
the API/browser Linux workflows. Direct main publishing is already authorized.

HTTP administration and scoped teams/client grants, durable worker/outbox
delivery, Redis, Compose/ingress/non-root images, full security/image scanning,
target CPU/native-runtime homologation and recovery/load evidence remain open.
No Phase 2 advancement, production readiness or deployment is claimed.

Rollback of this development increment is Git revert; no schema rollback is
needed. Real administrative changes are stateful security operations: do not
undo them by database rollback or revive revoked sessions. Use an explicit,
audited state/role/password change under the management guard.
