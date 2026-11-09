# Phase 1 execution evidence

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
- `uv run mypy`: no issues in 10 source files before final configuration fix;
  final full checks are rerun before publication.
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
  PostgreSQL migrations/drift/tests and build. Hosted outcome is verified after
  publication; this is not full SAST/secret/container scanning yet.

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

Phase 1B: real login/session UI using impeccable and generated API contracts.
Phase 1C: persisted scoped identity administration/teams, Redis/outbox worker,
Compose/proxy/non-root images, complete CI security gates, structured logs and
trusted ingress rate identity. Then actual guest CPU/native-library/runtime,
restart/load and recovery tests. No production deployment, data import or Zammad
change has been made. Q-01..Q-12 remain in roadmap, without invented answers.

Rollback of this development slice is Git revert. Database downgrade to base
is destructive and was proven only on the dedicated disposable test DB; do not
use it on operational data. Production rollback requires a compatible prior
image/schema plus backup/restore, as required by Phase 0.
