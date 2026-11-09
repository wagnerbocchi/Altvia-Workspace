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
through ASGI; they are not target-VM or production TLS/load proof.

### Team API publication evidence

Schema commit `030a3f2` and completed API commit `a5ce79a` were pushed directly to
main without PR, under standing authorization. Both hosted Linux workflows passed:

- [API checks 42606303304](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42606303304):
  all 160 tests, Ruff/format/mypy, fresh migrations/drift and wheel/source build.
- [Browser checks 42606303427](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42606303427):
  locked clean installation, Sharp exclusion, OpenAPI/TS drift guard, frontend
  checks/production build, dependency audit and all 7 real HTTPS/PostgreSQL E2E
  tests. No UI code changed or new native dependency was introduced.

Worker/outbox delivery, Redis/Compose/ingress/non-root images, persisted scoped
role/client grants, HTTP account mutation/admin UI, full security/image gates and
actual target-CPU/recovery/load evidence remain open. Phase 1 is not complete.

## Phase 1C-c: persisted team read scopes

2026-11-09. ADR-0010 and the API contract preceded implementation. Storage/service
commit fd92682 adds UUID role bindings, constrained viewer/operations_manager team
scope and restricted transactional grant/revoke. Global platform_admin keeps its
meaning. No role is inferred from roster membership; no real grant was provisioned.

The host CLI now accepts grant-team-role/revoke-team-role with fixed role names,
existing team UUID and account email, requiring both interactive confirmations
before a DB connection. Actual changes atomically revoke all target sessions,
advance auth_version and append audit/outbox. Duplicate/no-op grants add no effect.
Inactive users/teams reject grants; revocation still works after disable/archive.

Team reads use a role-binding SQL subquery before cursor/order/limit. A scoped
reader sees only bound team metadata/rosters, including archived teams. Unbound
IDs return404; no recognized grant returns403. Writes, /users and even previously
saved administrative replay remain identity.manage only. Global capabilities
remain unchanged; scoped-only users receive an empty capabilities array.

### Executed local evidence

- Task 1 RED: 23 missing schema/service failures; GREEN: 183 full API tests.
- Added guarded migration proof: preserve global grants through schema3/4,
  refuse unsupported legacy grants atomically, refuse downgrade with team grants,
  preserve row/version after refusal, explicitly revoke synthetic scope and prove
  roundtrip/drift. Storage/service/migration subset: 24 passed (22.64s).
- Task 2 RED: 16 expected global-only authorization/parser/policy failures and
  27 existing/negative cases passed. Initial focused GREEN: 43 passed (22.38s).
  Added same-actor former-admin replay and duplicate-role pagination coverage.
- Final `uv run --env-file .env.e2e pytest -q --tb=short`: **213 passed**
  (227.50s). Real ASGI/PostgreSQL tests cover both roles, explicit binding without
  membership, membership without binding, interleaved unauthorized IDs before
  pagination, own/other rosters, all write/user-directory denial, former-admin
  replay, session invalidation, targeted revocation, disable/archive, constraints,
  concurrent duplicate grant, atomic rollback and last-global-admin preservation.
- Ruff/check/format, strict mypy (11 source files), `uv build`, Alembic drift and
  `git diff --check` passed. Initial formatting/typing/lint findings were fixed.
- OpenAPI export and TypeScript regeneration produced no contract diff.
  `pnpm web:check`, `pnpm web:build` and `node scripts/check_web_native.mjs` passed.
  No UI implementation or dependency changed; no new native artifact introduced.

Only the explicitly guarded disposable altvia_test DB and synthetic identities
were used. Production downgrade or role provisioning was not performed.

Fresh read-only review of 413a503..ea7f081 inspected source, migrations, tests,
contracts, authorization, locks, parser redaction, pagination and atomicity.
No Critical, Important or Minor defect was identified. The reviewer did not run
DB tests or mutate the checkout. It excluded actual VM/production acceptance and
administrative UI/future client integration, as already bounded by this plan.
Those exclusions do not waive any phase gate or imply those features are complete.

### Team scope publication evidence

Storage/service fd92682, CLI/API ea7f081 and reviewed evidence d59709f were pushed
directly to main under standing authorization, without a PR. On d59709f both
hosted Linux workflows completed successfully:

- [API checks 42611582148](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42611582148):
  fresh migrations/drift, Ruff/format/mypy, **213 passed** (59.09s), wheel/source build.
- [Browser checks 42611582196](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42611582196):
  clean locked install, Sharp exclusion, contract generation/drift, frontend
  checks/build, dependency audit with no known vulnerabilities and **7 passed**
  real HTTPS/PostgreSQL E2E cases (7.7s).

The connector did not return the known workflow runs, so their status and test
summaries were verified using gh. Task-owned PostgreSQL and its local SSH forward
were stopped after validation; volumes and pre-existing user containers were
preserved. This is development/hosted CI evidence, not target-CPU homologation.

Phase 1 remains open: worker/outbox delivery, Redis/Compose/ingress/non-root images,
client/operational grants, HTTP account mutation/admin UI, complete security/image
gates and actual target-VM CPU/recovery/load acceptance are still pending.

## Phase 1C-d: API container runtime candidate

2026-11-09. ADR-0011 and its plan preceded implementation. Commit63d1fa9 adds
native file-secret discovery and a restricted one-off owner-side provisioner.
No schema migration or HTTP capability changed. The fixed runtime login has CRUD
on current identity/team tables and INSERT only on audit/outbox. DDL, role
management, audit reads/modification and Alembic reads are denied. Existing
ownership, inherited roles and elevated attributes are refused, not normalized.

Task1 evidence: missing provision module RED; native Pydantic file source already
existed and was reused. Focused16 passed; final full suite **227 passed** (235.86s),
including real runtime-credential login/logout and administrative team write,
permission denials, quoted-password handling, duplicate provisioning, same-target
checks and elevated/membership/ownership refusal. Ruff/format, strict mypy12 source
files and wheel/source build passed. All mutation used guarded altvia_test.

The runtime candidate includes a multi-stage API image, separated migrate service,
persisted PostgreSQL and unprivileged API-only TLS ingress. File-secret mounts,
private DB networking, loopback-only published HTTPS, health/dependency gates,
resource bounds, read-only applications and dropped capabilities are explicit.
No startup seed, browser UI change, idle worker or fake event acknowledgement.

Task2 RED: black-box smoke failed with "API container artifact missing" before
the stack was implemented. Image build then passed locally; imageID
sha256:fba4a5bc974f4a45c7ed048dc7dfead94f56d996134325bb2c4f209b5f460d47,
199315443 bytes. A direct read-only/cap-drop/no-new-privileges container confirmed
UID10001, production imports, absent pytest/tests and no copied uv.lock/build tool.
Shell syntax/ShellCheck, Python scripts/API Ruff/format, strict mypy, API package
build, JS syntax and unchanged OpenAPI all passed.

Local Compose created only its random altvia-test-* project, but startup failed
with crun "open memory.max for writing: No such file or directory". The existing
Windows Podman VM lacks the cgroup controller. The checked-in resource controls
were preserved; no VM/security setting was changed. Finally removed only that
test project's containers/networks and retained its volume/private synthetic
configuration. Local HTTPS/recreation acceptance is therefore not claimed.
The new hosted Linux Docker Compose gate must supply that proof before this
runtime slice is accepted. Review, scan and hosted results follow when observed.

### Review corrections and final local checks

Fresh read-only review of f412fd5..ee70bea identified three Important defects:
residual column/PUBLIC ACLs, existing direct database CREATE/TEMP and TLS health
verification against loopback instead of the configured certificate name. Six
real DB regressions failed before the ACL fix; an additional GRANT OPTION case
also failed before grantability checks. Provisioning now refuses these states
before password or privilege changes. Focused18 passed (24.83s); final full suite
**234 passed** (249.89s), including persistent schema and temporary DDL denial.

An isolated actual nginx/container TLS regression used a domain-only certificate:
original IP health command failed with curl60, hostname-aware local --connect-to
passed with exit0 and no TLS bypass. Read-only startup also reproduced missing
fastcgi temporary-directory failure; all HTTP module temporary paths now use/tmp.
The black-box fixture now uses only the reserved workspace.altvia.test DNS SAN,
with host resolution scoped to the test process. This is TLS regression evidence,
not full API/Compose acceptance or production DNS configuration.

Podman's default OCI build discarded HEALTHCHECK metadata (observed null).
Explicit --format=docker preserved the actual healthcheck; final local imageID
sha256:e38f8a86d098c3c81155f12c0bd4aa6431e67053b551d786d9745cc8e6dad2b5.
The smoke helper now selects that format for Podman. Actual Argon2id hash/verify
passed inside this non-root/read-only/cap-drop image. Compose config validation,
API/scripts Ruff/format, strict mypy, package build, shell syntax/ShellCheck and
JS syntax passed. No second reviewer was dispatched; regression/full-suite proof
verifies the single final review's correction pass. No Minor finding was deferred.

Trivy successfully scanned the original candidate's Docker archive:2 critical,
40 high,122 medium,109 low package occurrences. Vendor evidence shows the flagged
MiniZip code is absent from the installed zlib binary. SQLite remains a vulnerable
installed package without a current API SQL path; its release disposition and all
high findings remain open, without risk acceptance. Exact artifact, raw-report
hash, vendor sources and actions are in docs/security/api-container-scan.md and
Q-14. Functional CI cannot waive this production image-security gate.

Candidate amd64 platform artifacts, resolved2026-11-09:

| Component | Source/version observed | Immutable manifest |
| --- | --- | --- |
| API base | python:3.12-slim-bookworm; Python3.12.16 | sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4 |
| Build-only dependency tool | ghcr.io/astral-sh/uv; uv0.13.7 | sha256:c7db1d63057f268a8b6da8af9077850a60461f98d23db23c676a82089a050c91 |
| Database | postgres:17-bookworm; PostgreSQL17.11 | sha256:73bedc9eaa0121b92b9b26bb52e5141b3f6f37479c7ef913c0160455763ca80a |
| API ingress | nginxinc/nginx-unprivileged:stable-bookworm; nginx1.28.0 | sha256:10bf30f80ce9af183b2db50a91ea59cea5eb5e4106820656bac8cd369ed14904 |

These are locally executable candidates, not approved production/CPU artifacts.
Nginx reports Debian gcc12.2.0, -O2/stack protector/fortify/PIC and no -march=native
in its configure options; that is not proof of every linked library's ISA.
Q-01, actual guest tests, image/security triage, backup/restore and load remain
open. Worker/Redis/web ingress and the rest of Phase1 are still unfinished.
