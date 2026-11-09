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

First hosted container gate on7b0a933 failed at the dirty-context canary assertion
before synthetic user provisioning. Negating a parent directory in .dockerignore
had also re-included its children. A local real-image regression reproduced the
copied canary before correction. Each allowed parent now explicitly excludes
children again before individual source-file exceptions. Rebuilt actual image
sha256:769c5489fd0d88348ecc3b7b9af996b978220c5e8eb5017ef4d290be64055ed7
passed canary, source-cache and test exclusion plus production imports. The smoke
also checks absent source __pycache__. Only synthetic test material was used;
no image was published to a registry. Hosted acceptance requires a fresh green run.

### Hosted runtime acceptance

On7df1ebc the corrected actual Docker/Linux stack passed
[Container checks42618799256](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42618799256).
The black-box helper confirmed dirty-context/cache/test exclusion, mounted secrets,
non-root/read-only applications, no DB/API host ports, actual TLS identity for a
domain-only certificate, real persisted identity/team API and scoped ACL, Origin/
CSRF denial, API/Postgres recreation with session/data survival, readiness503 with
liveness200 during DB outage, recovery, owner-job rerun, graceful API SIGTERM and
absence of generated credential values in stack logs. The helper stopped only
its random test project and never requested volume deletion.

[API checks42618799279](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42618799279)
also passed:234 tests (61.16s), fresh migrations/drift, Ruff/format/mypy and build.
[Browser checks42618799430](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42618799430)
passed too: all7 real HTTPS/PostgreSQL E2E tests, frontend check/build, dependency
audit, Sharp exclusion and generated-contract drift guard. No UI code changed.
Code commits63d1fa9/ee70bea/7b0a933/7df1ebc were published directly to main under
standing authorization. All three hosted gates passed on7df1ebc; the failed first
container run remains recorded above rather than counted as successful evidence.

Local task PostgreSQL and its single SSH forward were stopped; pre-existing
containers and all volumes were preserved. The local Podman resource limitation
is an environmental blocker to running this checked-in Compose on that machine,
not a waived or disabled resource limit. Hosted success accepts the bounded API
runtime development increment; it does not approve production, image risk,
x86-64-v1 on the actual guest, backups/restore, capacity or the unfinished worker,
Redis/web ingress and remaining Phase1 functionality.

## Phase 1C-e: remove unused SQLite runtime capability

2026-11-09. ADR-0012 and its plan preceded implementation. Commit 1d8ed76 removes
only the final API image's unused libsqlite3-0 package and optional CPython
sqlite3/_sqlite3 modules. The application already requires PostgreSQL. Builder,
developer Python, base digests, dependency lockfiles, schema and API behavior
remain unchanged. No patched private library, new native dependency, forced
package removal or OS-family change was introduced.

The image build runs scripts/check_api_runtime.py as its non-root user, and the
actual running Compose API runs the same diagnostic. The guarded container test
also verifies that the unchanged dependency-builder stage is rejected for its
SQLite capability. A missing stdin attachment initially produced an empty
program/exit0; commit 1b8ac9a adds -i and the exact rejection/exit1 was observed.
No acceptance was inferred from the empty run.

### Local proof and scan comparison

- RED: checker rejected the published image with the specific installed SQLite
  capability error. GREEN: actual new Docker-format image
  acba1ed82e79aaa7e335dcde023c0935b0c7d741f930ab8fc793345a32b4226f passed the
  module/package/native-object/loader guard under non-root/read-only/cap-drop
  execution, including API/CLI/migration and TLS/compression imports.
- Actual Argon2id hash/verify passed inside the pruned image as UID10001.
- A separate negative probe mounted the original SQLite shared library through
  LD_LIBRARY_PATH into the pruned image. Even with package/modules absent, the
  guard rejected the loadable library. The temporary helper was removed.
- Both explicit unsupported SQLite URL cases pass the existing configuration
  boundary. All9 focused configuration tests passed. API/scripts Ruff/format,
  strict mypy (12 source files), package build and unchanged OpenAPI passed.
  Application logic is unchanged; hosted gates must run the new236-test suite.
- Same-scanner/same-vulnerability-DB comparison removed exactly19 SQLite finding
  identities:1 critical,5 high,9 medium,4 low. Zero added identities. Debian
  inventory105 to104, only libsqlite3-0 removed; all27 Python distributions and
  versions remain identical. Raw counts are now1 critical/35 high/113 medium/105
  low; the remaining critical is the already vendor-classified MiniZip false
  positive for the actual installed binary, whose vulnerable symbol is absent.
  Exact input/report/DB hashes and all eliminated CVEs are in the image scan report.

Fresh read-only review of 4141cb5..1b8ac9a found no actionable Critical, Important
or Minor issue. The reviewer recalculated report/DB hashes and the finding/package
delta; all matched the documented evidence. It did not mutate/re-execute
containers or databases. Actual hosted API/browser/Compose results remain the
acceptance gate; prior hosted results are not substituted for new runtime proof.

Local full Compose remains blocked by the existing Podman VM's missing cgroup
controllers. No production resource/security setting was weakened. This work did
not start PostgreSQL or alter data volumes. No frontend/UI code or real data
operation occurred. Remaining35 high findings, other service images, actual
x86-64-v1 guest, capacity/recovery and all production gates stay open. No risk
acceptance or complete clean-image claim is made.

### SQLite removal publication evidence

Code 1d8ed76, measurement evidence 95c0fdb, probe correction 1b8ac9a and reviewed
evidence 3b96e2f were published directly to main under standing authorization.
All three hosted Linux workflows passed on 3b96e2f:

- [API checks 42623615363](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42623615363):
  **236 passed** (66.86s), Ruff/format/mypy, fresh migration/drift and package build.
- [Browser checks 42623615304](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42623615304):
  **7 passed** (9.0s), frontend check/build, Sharp exclusion, dependency audit and
  generated-contract stability. No UI implementation changed.
- [Container checks 42623615225](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42623615225):
  actual pruned-image build, rejection on unchanged builder, runtime capability
  guard, production imports and real TLS/ACL/persistence/readiness/secret/SIGTERM
  flow passed. The API's PostgreSQL behavior survived the capability removal.

Only task-owned ephemeral helpers were started locally; no PostgreSQL service,
data volume or forwarding process was changed in this increment. The black-box
helper stopped only its random test stack and did not delete volumes. Raw scan
comparison and its DB snapshot are retained under ignored .superpowers/container-tests
for audit/reproduction; the DB folder is sqlite-removal-vulndb-20261109.
Remaining 35 high findings and all actual-guest/production gates stay open.

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

## Phase 1C-f: vendor-patched images, security enforcement and logical recovery

2026-11-09. ADR-0013 defines the compatibility and data contract before code.
Bookworm vendor fixes were unavailable for Essential/native packages. The API,
PostgreSQL17 and unprivileged nginx now use official Alpine inputs; proxy fixes
come from signed vendor packages. Gosu1.19 source/checksum/module sums are verified
and its embedded runtime is rebuilt with Go1.27.3 and GOAMD64=v1. No forced package
removal, private libc/zlib fork, ignore file or blanket unfixed suppression.
The API retains locked production packages and removes only unsupported SQLite.

Local actual candidate image IDs (sha256):

| Service | Image ID | Critical/high | Other package occurrences |
| --- | --- | --- | --- |
| API | 509114cfc40b5e82e1b236c81b86551e2553f163df7411f6e982d870051c077d | 0/0 | 6 medium, 1 low |
| PostgreSQL | 479c5673fde6fdf5adfaaa2e187f63ae7c2760edcdf3d6e424cd839b1c410433 | 0/0 | 2 medium, 1 unknown |
| Ingress | ceceb02516f57252873b4ec55a65cf1ee6f87a4408bd0ed53bfaa21e9743797b | 0/0 | none reported |

Python3.12.16, PostgreSQL17.11, nginx1.30.6. Immutable input manifests are in the
three Dockerfiles. Scanner Trivy0.75.0 digest af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa;
DB updated2026-11-09T12:54:37Z, SHA256 e67b76d3c9fdab89365ccaec6e03aa2060dede721b346fe9e7aeb4f59d7f71c1.
No Python production dependency version changed. The musllinux artifacts differ
from previous manylinux wheels; actual native behavior was revalidated.

Raw evidence is retained through Codex Security managed persistent storage for
this repository, collection artifacts-8bf4d992d29be3151dd575511ea4b51a7c874bf1601dd402bb42743b50abce49,
under artifacts/service-image-remediation/. Manifest SHA256
dd8106b6619f70a4871b5bbd914cffc221b8ebe7cde6a3af73ad552394edbc9d.
It binds image IDs, report hashes, complete lower-severity counts and the DB hash.
Files api.json/postgres.json/ingress.json contain actual scanner bytes. The prior
Bookworm API/PostgreSQL/ingress reports and linux-api-suite.log are also retained.
The same-DB Bookworm API still reports35 high and1 raw critical (the previously
documented MiniZip non-applicability); PostgreSQL reports75 high/4 critical and
ingress135 high/11 critical. All three corrected installed images report0/0,
without relying on that applicability exception or filtering unfixed findings.
Hosted CI publishes portable reports/image identities on every run and weekly.

Local commands and evidence:

- podman build --format=docker for all three Dockerfiles: passed. API wheel-only
  synchronization installed all27 production entries without a compiler.
- uv run ruff check scripts apps/api; format checks; uv run mypy; uv build;
  git diff --check: passed. Image-gate regression tests: 8 failed before enforcement,
  then8 passed, covering non-OS HIGH/CRITICAL and incomplete/unrecognized evidence.
- Actual final non-root/read-only API checker: passed; actual untrimmed builder
  rejection: expected status1 with unsupported SQLite capability.
- Full244 API tests, fresh Alembic upgrade and drift check: passed inside Linux
  Python/Alpine against the actual patched PostgreSQL on a dedicated task network.
  Test-only locked pytest/httpx wheels were downloaded/hashed on the host because
  this Podman task network timed out reaching PyPI. One httpx-to-httpx2 deprecation
  warning arose in that deliberately minimal dev harness; production packages
  were unchanged. No test was skipped. Task containers/network were removed.
- uv run python scripts/scan_service_images.py --engine podman with managed
  --output-dir, shared --cache-dir and --skip-db-update: passed all three images.
  No service Compose resource/security bound was changed for local scanning.
- Fresh independent candidate review identified legacy PGDATA reuse. Reproduced
  refusal-test failure, then added an entrypoint guard and fresh-init-only marker;
  the actual image refusal test passed. The runbook requires separate destination
  project/volume and logical restore, preserving the old volume for rollback.

The continued Foundation delivery adds a blocking all-service image-security
workflow and guarded synthetic Bookworm-to-Alpine logical recovery tests. Full
Docker/Linux Compose/TLS/ACL/recreation/readiness/SIGTERM/recovery acceptance and
hosted API/browser/security results passed as recorded below. No schema,
account grants, API contracts or UI changed; no real migration/deployment occurred.
Actual target-VM/x86-64-v1, lower-severity follow-up, worker/Redis/web ingress,
capacity and production backup/load acceptance remain open. Phase1 is not closed.

### Service-image remediation publication evidence

Code27b0bcb was pushed directly to main under standing authorization. All four
hosted Linux workflows passed on that exact revision:

- [API checks42630904890](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42630904890):
  244 tests passed (55.60s), lint/format/mypy, fresh migration/drift and package build.
- [Browser checks42630904953](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42630904953):
  7 E2E passed (9.2s), frontend build/check, native dependency exclusion, generated
  contracts and dependency audit. No frontend implementation changed.
- [Container checks42630904852](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42630904852):
  actual Docker builds/Compose protections, capability and legacy-volume guards,
  TLS/login/CSRF/team ACL, session/data survival across API/database recreation,
  DB-loss readiness, migration replay and SIGTERM all passed. Synthetic old-to-new
  logical restore, Unicode checksums, Portuguese FTS and primary key passed.
- [Service image security42630904985](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42630904985):
  all three actual Docker-built images scanned with zero HIGH/CRITICAL, with the
  same DB SHA256 as the local comparison. Complete reports and image identities
  are in its service-image-security-27b0bcbac11772c1010aa00c59088359d896d302 artifact.
  Exact bytes are also retained in managed hosted-27b0bcb evidence.

Hosted image IDs differ from local build IDs; use each run's manifest. The counts
agree. Third-party action Node20/URL deprecation warnings are benign toolchain
metadata warnings; no container/test gate failed. The earlier reported installed
high/critical findings no longer reproduce. Residual lower severities and all
actual VM/production gates remain explicit. No real cluster or account changed.

## Phase1C-g: residual runtime findings

2026-11-09. Corrected the8 MEDIUM/1 LOW/1 UNKNOWN remaining occurrences through
owning image inputs: signed zlib1.4-r0 for API/PostgreSQL; complete pip/ensurepip
capability removal from the final API; gosu's pinned corrected moby/sys/user0.5.0
and x/sys0.44.0 modules. ADR-0013's supplement explicitly narrows the immutable
runtime capability, preserving developer/builder behavior and all required APIs.

Same-DB scans of all three actual images report zero vulnerabilities at every
severity, with no ignore or unfixed filter. Local API image SHA256
f922fdd0dedbc88e535294fed55a36fb06e430c86769ac2511403866e7e66117;
PostgreSQL1dba65f0d1b47737ef1afcd8dfd181a2d65c7d8a567511ffd17c55334a1ed3de;
ingress is unchanged. Actual report bytes and image/DB provenance are retained
through managed Codex Security artifacts/residual-runtime-findings/, manifest
SHA256 bde881f27a9057bcb6b3029bd2a320bae4ac4af8a8de29ef01324a1723c2c002.

Global/base Python pip and stdlib ensurepip absence probes failed before removal.
Final non-root/read-only guard passed, including base/venv files, bootstrap wheel,
entrypoints, required imports and native zlib1.4 compression roundtrip. Independent
installer rejection on the actual untrimmed builder passed. Existing SQLite
negative control remains separate. No Python production package version changed.

Gosu's upstream moby/user0.4.1 tests initially failed because their read-cap fixture
used invalid NUL padding and an overlong line. Upstream0.5.0 corrects that fixture;
its full tests passed without skipping/patching tests. Recorded module hashes
verify before readonly build with Go1.27.3/CGO0/GOAMD64=v1. Actual named/numeric
UID/GID, explicit group, HOME and unknown-user denial controls passed. The Windows
x/sys finding was removed from inventory without inventing Linux exploitability.

Ruff/format, mypy, image-gate tests and diff checks passed. Fresh independent
candidate review found no concrete surviving bypass/regression. All four hosted
gates passed on683e34d: [API244 tests42634012848](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42634012848),
[Browser7 E2E42634012844](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42634012844),
[Compose/recovery42634012879](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42634012879)
and [zero-finding image security42634012896](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42634012896).
No schema, volume-family or real account change.
Q-01/actual target-VM homologation and production readiness remain open.

## Phase1C-h: packaged same-origin frontend

2026-11-09. ADR-0014 established contracts before implementation. The existing
Impeccable identity interface is packaged as Next standalone and routed through
the same real HTTPS proxy as /api/v1/. No new business UI, auth store, backend or
schema. Shared edge forwarding rules cover both upstreams; web has no direct port,
DB network or credential mounts. Read-only/non-root/capability/resource controls
are preserved. The default still publishes HTTPS on loopback only.

Official Node24.22.2 Alpine builder, locked pnpm11.25.0/Next16.4.5, signed vendor
Node24.22.1-r1 on pinned Alpine3.24 runtime. Shared native libraries report zlib1.4,
Brotli1.2.1 and OpenSSL3.5.9. No npm/corepack/yarn, build/test tools or Sharp in the
actual standalone image. The locale probe failed with English-only ICU; installing
vendor full ICU data restored pt-BR without a private native build. The guard
checks that capability too. Immutable manifests are in infra/web.Dockerfile.

Local pnpm web:check and pnpm web:build passed on Windows; the actual Linux
multistage image built successfully. Its non-root/read-only/cap-drop/no-network
HTTP probe passed dynamic SSR, nonce CSP, no-store and real static assets. Native
Next16.4.5 closes HTTP/Next resources then exits143 on SIGTERM; source inspection
and a local cleanup-finished diagnostic proved that behavior. The initial exit0
test expectation failed and was corrected to preserve framework semantics, not
normalize exit codes. Forced137/OOM/unexpected exits remain failures.

Same-DB local scans of all four actual images report zero findings at every
severity, with no suppressions. Web image SHA256
07dd573216d5eddd85c8ed9e2baddf05340ccf63a38293760939d6adcb43b58a;
raw reports/manifest are retained through managed security artifacts/web-ingress/.
Stock Node24.21 retained vulnerable embedded/installer copies; distroless Node24
retained unfixed Debian occurrences. The vendor shared-library model avoids both.
Alpine nodejs APKBUILD uses generic flags and shared native dependencies; this
source evidence and modern local execution do not homologate the real target VM.

Fresh read-only final review found that Playwright's Node APIRequestContext does
not inherit Chromium's reserved-host DNS mapping or SPKI pin. Independent DNS and
self-signed-certificate reproductions confirmed failure. Same-origin probes now
use actual browser fetch/cookies, while the existing strict-CA Python probe owns
forged-Origin denial. No other important source-backed review finding. Full
hosted packaged-browser/Compose/API/security acceptance remains pending below.
No real deployment, user provisioning or data/volume migration. Phase1 stays open.
