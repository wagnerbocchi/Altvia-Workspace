# Phase 1 execution evidence

Phase 1 is now closed: [final Foundation acceptance](phase-1-closure-evidence.md).
The following records preserve the earlier slices and their historical limits.

Phase 0 published as `996aeb3`. Phase 1A delivers the identity API according to
`docs/plans/2026-11-08-foundation-identity.md`. Not a completed Phase 1.

Ruling: native execution on main follows the user's explicit instruction. No
worktree/PR approval pause is needed. Future frontend uses impeccable. Pending
VM access blocks CPU homologation, not local safe implementation.

Ruling: initial discovery found no Docker CLI but later found a working Podman
connection. Use a new isolated development Postgres container; preserve existing
Altvia containers. Local container success is not real target-VM evidence.

## Delivered behavior and boundaries

PostgreSQL-backed users, hashed opaque sessions, local Argon2id login, current
identity, idempotent logout, revocation/idle/absolute expiry, current account
auth_version checks, strict Origin and session-bound CSRF. Generic auth errors,
bounded credential bodies, durable account/IP rate buckets and bounded concurrent
hashing. Management commands provide one-time bootstrap and password reset,
without password arguments/default credentials. Password reset revokes sessions.

Audit and outbox commit with identity mutations; a deliberate outbox constraint
failure in the isolated test DB proves the session/audit roll back together.
Audit UPDATE/DELETE trigger prevents ordinary history rewriting. Deployment must
still restrict DDL/TRUNCATE/trigger privileges and use a separate migration role.

Ruling: persist only global platform roles in this slice; client/team/project/
queue binding FKs and permission administration arrive with those domains.
The pure policy kernel is tested against the Phase 0 predicates. This does not
claim resource-endpoint authorization or full RBAC administration is implemented.
The platform capability is identity.manage only, with no customer-content bypass.

## Executed checks

- `uv sync --python 3.12`: local Python 3.12.16 venv created and locked packages
  installed. Key versions: FastAPI 0.162.2, SQLAlchemy 2.0.57, Alembic 1.20.1,
  psycopg 3.3.8, Argon2-cffi 25.1.0, Pydantic 2.14.3. Native transitive wheels
  are not yet approved for target x86-64-v1.
- TDD: first minimal app/policy run 7 failed/10 passed. After typed fixtures,
  auth routes produced 16 expected assertion failures/15 passing policy cases.
  Management bootstrap/reset tests failed before implementation. Logout replay
  and audit immutability regressions failed before their fixes.
- Linux private test runner: `pytest -q --tb=short`, **44 passed**, no warnings,
  covering real Postgres persistence, cookie/CSRF/origin, lifecycle, rate limit,
  private errors, management commands, audit/outbox atomicity and policy rules.
- `uv run mypy`: no issues in 10 source files, rerun after the configuration fix.
- `uv run ruff check apps/api --output-format concise`: passed. Formatter also
  checked. Initial formatting/typing findings were corrected, not suppressed.
- `uv build`: source distribution and wheel built successfully.
- Disposable DB: Alembic downgrade to base, upgrade head and check succeeded;
  no new upgrade operations detected. Tests rerun after restoration.
- `uv tool run pip-audit --path .venv/Lib/site-packages --progress-spinner off`:
  no known vulnerabilities in auditable dependencies. Cache deserialization
  warnings were ignored by the audit tool, not security findings. Local Altvia
  package is not on PyPI and was not audited as a third-party distribution.
- SHA-pinned API CI workflow added for main pushes: lint/format/typecheck,
  PostgreSQL migrations/drift/tests and build. Hosted run
  [42553136561](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42553136561)
  passed all steps for implementation commit `57f94c2`. This is not full
  SAST/secret/container scanning yet. GitHub's separate uv dependency-graph
  update run also succeeded.

## Independent review and fix

The reviewer confirmed one material finding: invalid Settings validation could
render a raw connection URL/password. A short synthetic URL reproduced the
leak; long inputs could be truncated and hide it from an overly broad test.
The regression was corrected to exercise the short case, observed failing, then
passed after hide_input_in_errors and sanitized CLI configuration handling.
Final suite: 44/44. No live credential was used or displayed in this regression.

## Development-only infrastructure evidence

- PostgreSQL 17.11 initialized and accepted connections in new task-owned
  container `altvia-workspace-phase1-db`. Initialization's temporary local
  server shutdown and logical-replication-worker exit were normal initdb steps;
  the final server started and remained ready.
- Postgres digest: `sha256:73bedc9eaa0121b92b9b26bb52e5141b3f6f37479c7ef913c0160455763ca80a`.
- Python runner digest: `sha256:05a994d2344eb364cc186910f4fc8786a38215f39f00d0acc25bff33a08f4177`.
- First container creation failed with unavailable pids cgroup. A distinct
  task-owned container with cgroups disabled ran successfully. Windows host
  forwarding remained unreachable; private sidecar tests avoided changing host
  networking. These are development constraints, not target-VM results.
- Hash-locked Linux dependencies were installed into the disposable runner.
  Its root user/tooling mount is not a production container configuration.
- Existing user Altvia containers and all volumes were preserved. Env files,
  generated test requirements, venv, source workbook and build outputs are ignored.

## Remaining gates and next delivery

Phase 1B now adds the real login/session UI described below.
Phase 1C: persisted scoped identity administration/teams, Redis/outbox worker,
Compose/proxy/non-root images, complete CI security gates, structured logs and
trusted ingress rate identity. Then actual guest CPU/native-library/runtime,
restart/load and recovery tests. No production deployment, data import or Zammad
change has been made. Q-01..Q-13 remain in roadmap, without invented answers.

Rollback of this development slice is Git revert. Database downgrade to base
is destructive and was proven only on the dedicated disposable test DB; do not
use it on operational data. Production rollback requires a compatible prior
image/schema plus backup/restore, as required by Phase 0.

## Phase 1B browser identity (2026-11-09)

Implemented Next.js 16.4.5/React 19.3.1 with strict TypeScript, Tailwind,
shadcn-style button composition, React Hook Form/Zod and TanStack Query.
FastAPI exports OpenAPI without database access or secret configuration;
openapi-typescript generates browser DTOs. The browser calls the actual API over
the same HTTPS origin. Login, reload/current account, server expiry and logout
use persistent PostgreSQL sessions. There are no mocked business screens, demo
counts, public signup or unimplemented password-reset links.

Only theme preference persists in browser storage; identity/CSRF stay transient
and the session cookie remains Secure/HttpOnly/SameSite=Lax. Visibility
revalidation checks server state without polling away the idle timeout. A failed
logout explicitly warns the session may remain active. Error/loading/rate states,
field validation, password reveal, responsive layout and dark/light are present.
Document CSP uses fresh nonces with dynamic SSR, no production unsafe-eval;
API Origin and CSRF protections remain unchanged.

### Local evidence

- `pnpm install --frozen-lockfile`: clean installation passed. A separate offline
  verification first lacked pnpm metadata; online metadata verification then
  succeeded. This was a tooling-cache condition, not a waived security check.
- `node scripts/check_web_native.mjs`: passed. Sharp absent after clean install.
  An earlier in-place install retained an orphan optional link; only task-created
  module directories were moved to a temporary backup and regenerated. No user
  data or existing application dependencies were deleted.
- `pnpm web:check`: ESLint with zero warning tolerance and strict tsc passed.
- `pnpm web:build`: production build passed; nonce-bearing pages render
  dynamically. No build/type/lint errors are ignored.
- `uv run python scripts/export_openapi.py` and
  `pnpm --filter @altvia/web generate:api`: passed.
- `uv run ruff check scripts` and `uv run ruff format --check scripts`: passed.
- `pnpm audit --audit-level=moderate`: no known vulnerabilities in the resolved
  dependency tree. The initial minimatch advisory was corrected with a narrow
  override, then lint/build/generation rerun. Registry audit is not SAST or a
  container/runtime security assessment.
- `uv run --env-file .env.e2e node apps/web/scripts/browser-test.mjs`:
  **7/7 Playwright tests passed**, production Next server, real FastAPI and real
  PostgreSQL over an ephemeral local HTTPS gateway. Tests exercised generic
  credential failure, keyboard validation/reveal, real login/reload/logout,
  DB-forced server expiry, network recovery, failed logout, rejected foreign
  Origin/missing CSRF, secure cookie flags, no auth localStorage, CSP/cache headers,
  disabled image optimizer, pending/rate UI and theme persistence. Intercepted
  network/429 states test recovery only; backend limiter evidence remains in 1A.
- axe WCAG A/AA checks passed on light/dark 1440x900 and 390x844 login views and
  mobile authenticated account. Seven actual screenshot captures were inspected,
  including credential and offline errors at 1280x880. This is bounded automated
  and visual evidence, not complete assistive-technology certification.
- Windows test harness cleanup was corrected to close venv child process trees;
  the final runs rejected occupied ports and left no task API/web listener.

### Independent visual review

Applied impeccable v4.8.0. Product truth, provisional direction and Q-13 were
recorded before interface code. The user explicitly directed continued work
without interview pauses; no corporate visual approval is claimed. The detector
ran once and returned `[]`. Fresh independent review inspected all seven valid
captures and source, requested one material keyboard-focus correction on logout
and connection-error replacement. That correction was implemented with browser
assertions; the same captures were refreshed. The reviewer scored the sole fix
resolved, disposition `ship`. This verdict pass covers the scored fix, not a
second whole-surface review. No separate approved QUALITY BAR comp was supplied;
the code-led Operate rules and direction were the available benchmark.
The independent documenter extracted source-backed tokens to DESIGN.md and
.impeccable/design.json, validated YAML/JSON references and schema structure,
and preserved the provisional-brand status. No shipping raster assets exist.

### Hosted publication evidence

Implementation commit `88d945c` was pushed directly to main under the user's
authorization, without PR. Both Linux workflows passed:

- [Browser checks 42556327634](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42556327634):
  clean locked installation, Sharp absence guard, Python script checks,
  generated-contract drift check, frontend lint/types/production build,
  dependency audit and all 7 real HTTPS/PostgreSQL Playwright tests.
- [API checks 42556327651](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42556327651):
  unchanged API lint/format/mypy, real PostgreSQL migration/drift checks, all
  44 tests and wheel/source build.

These hosted runs validate the application/tool chain on Ubuntu GitHub runners,
not the target VM CPU or production topology. No required step was skipped.

### CPU and remaining acceptance limits

Sharp's upstream Linux x64 prebuilts require SSE4.2. It is an optional Next
dependency, explicitly excluded, with image optimization disabled and tested 404.
See ADR-0008 and the infrastructure compatibility record. No Elasticsearch,
OpenSearch or higher-ISA mandatory runtime was intentionally added. Actual
Linux Node/SWC/Tailwind native artifacts still require the target-VM gate.

This browser slice adds no migration and does not finish Phase 1. Identity/teams
administration, Redis/outbox processes, hardened Compose/ingress/non-root images,
full security scanning and actual target CPU/recovery/load validation remain.
No production deploy, operational data import or Zammad change is authorized by
these results. Frontend rollback is Git revert; database contents are unchanged
by application schema (only guarded disposable test fixtures are created).
