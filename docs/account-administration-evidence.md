# Account administration acceptance evidence

Date: 2026-11-09. Foundation increment, ADR-0016. No production deployment.

## Delivered and reviewed

- d0773bb: contracts and implementation plan before product code.
- 207c203: strict persisted account/security HTTP, shared administration protocol,
  service attribution, version bounds and generated OpenAPI/TypeScript.
- 30c577d: linked account directory/detail, private credential intents, inline
  confirmations, constrained team read grants and session-aware recovery.
- 515f9f1: actual packaged account HTTP/browser/replay/persistence proof.
- 7e0e66b: reviewed form-spacing correction, observed visual regression RED/GREEN.

Accounts can be created, enabled/disabled, have passwords reset and receive/revoke
platform administration or existing viewer/operations_manager team read roles.
No profile editor, arbitrary role, implicit roster grant or customer-scope bypass.
No schema or dependency change. Existing restricted CLI remains supported.

Fresh source reviewer reported no actionable findings or declined judgments.
Impeccable inspected ten valid desktop/mobile light/dark and recovery/confirmation
captures. Its single material spacing finding was fixed; the verdict pass scored
it resolved, disposition ship at that fix's scope. Fresh documenter checked the
finished extension against incumbent tokens/components and all ten captures:
no durable system change, DESIGN.md/design.json preserved. Pre-existing sidecar
narrative.rules drift remains reported and outside this work.

## Local and hosted checks

Local fresh disposable PostgreSQL: full API 270 passed in 286.78s, including 26new
account tests. Full real HTTPS/browser/API/PostgreSQL suite30 passed in 1.8m.
Build, strict TypeScript, ESLint, Ruff check/format, mypy, generated contracts and
native dependency guard passed. pnpm audit reported no known vulnerabilities.

Tests cover real lifecycle, attribution, concurrent create replay, original-version
replay, costly secret fingerprints, no credential metadata leakage, fresh replay
authorization, last administrator, inactive grants, version exhaustion, body/media
limits, role paging, lost password replies plus read recovery, stale confirmation,
self-session disposal, denied UI queries, themes, keyboard/focus and axe.

An initial combined browser run hit the existing account login throttle because
test suites reused one ordinary fixture. Isolating the new denied-access fixture
resolved it without relaxing limits. Roster tests now traverse bounded fixture
pages rather than assuming a particular account falls within the first 20 rows.
The first UI check also exposed a ZodPipe method/type error and a ref/render lint
boundary; both were corrected before acceptance. A premature harness launch before
successful build was rejected, not counted as runtime evidence.

All four hosted workflows passed on 7e0e66b:

- [API 42703634781](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42703634781): 270 tests in 91.89s; lint/format/mypy/migration/build.
- [Browser 42703635305](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42703635305): 30 tests in 48.6s; types/build/contracts/audit.
- [Containers 42703635077](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42703635077): actual updated Compose/browser/recovery proof.
- [Images 42703635209](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42703635209): all-service image security gate.

## Exact target qualification

Reused the already authorized VM and Docker/Compose setup from
docs/target-vm-foundation-evidence.md. No OS package, SSH server or public ingress
change. One password-authenticated Linux client master was reused for all channels;
the password stayed in the user's visible terminal. Master closed after transfer.

Final source 7e0e66b, archive SHA256
8d4f95fecc69c201415c1880c10ba120c7359255d21168f2da742f40eac93486,
isolated /root/altvia-accounts-final-20261109/source. Actual smoke exited0 between
21:32:28 and 21:34:39 UTC. Initial 515f9f1 also passed before the visual correction;
only the final image identities below certify the delivered artifact.

Executed python3 scripts/container_smoke.py with explicit isolated-test opt-in.
Passed real account creation/password/status/global role/team role HTTP changes,
historical POST replay, packaged browser account create/reset/disable/enable,
reload persistence, existing team/roster ACL, strict certificate/CSP/CSRF checks,
API/PostgreSQL/web recreation, readiness failure/recovery, cross-libc logical
restore/Unicode/FTS, runtime/native guards and graceful shutdown.

Separate target proof matched actual cgroup memory/CPU/PID bounds, read-only
filesystems, dropped capabilities and no-new-privileges. Only ingress bound a host
application port, at 127.0.0.1; database network internal. Task project stopped,
synthetic volumes retained; no running task containers after cleanup.

Trivy scanned Docker archives of the exact tested/resource-verified images, with
zero reported findings at every severity, no ignores/unfixed filter. All four used
DB UpdatedAt 2026-11-09T19:03:15Z, SHA256
8c808b8e2b45da2b9849fab569412fd5b0a59455d3335ea0321f0179bcd86130.

| Service | Tested image ID, sha256 |
| --- | --- |
| API | 9309859699511b7ffb37ef71e2c4de15ee13e006c430b20a5fc7eee7fac000a6 |
| PostgreSQL | f5b12d70f21021731c37f6e0bfc89209c34bbde01820a6d7d47055d40d645796 |
| Web | c4239fd8f4cd94075d7863a25d4d5d294989e4e96de29fb9d8316f5e73c8374a |
| Ingress | 6b53b7c97045f32596f7390cd7a7b101020b0e1686ea7393269d24d74968a5c7 |

Managed artifacts/accounts-vm/2026-11-09/final/ retain the raw bundle, revision,
smoke stdout/stderr/state, resource checks, full four-image scan reports/manifest
and packaged account screenshot. artifacts/accounts-browser/2026-11-09/ retain
local results, full sanitized final browser output, review/documentation outcome
and ten empty/cleared-credential captures. No source workbook or credentials saved.

Remaining Foundation and production gates stay in docs/roadmap.md: representative
capacity/IOPS, backup/retention and RPO/RTO policy, real scope provisioning and a
durable worker/Redis consumer when justified. No Phase 2 or production-ready claim.
