# Foundation identity implementation plan

Execution: native/inline in the existing workspace, per user's authorization to
continue without checkpoints, commit and push main. Contracts: PRD FR-001/012,
ADR-0003 and security policy. This is Phase 1A, not the full Phase 1 gate.

Goal: a runnable PostgreSQL-backed API with secure local identity, revocable
sessions, permission kernel, migrations and real automated integration tests.
No task/ticket feature, mock dashboard or external identity integration in this slice.

## Files and ownership

- `pyproject.toml`, `uv.lock`: supported pinned Python dependencies and checks.
- `apps/api/altvia/config.py`, `database.py`, `models.py`: validated environment,
  database sessions and initial identity/audit/outbox metadata.
- `apps/api/altvia/identity.py`: password hashing, provisioning/session lifecycle.
- `apps/api/altvia/policy.py`: pure resource-policy evaluation, deny by default.
- `apps/api/altvia/main.py`: typed HTTP boundary, consistent errors, CSRF,
  readiness and correlation. No auto-creation of schema or default users.
- `apps/api/altvia/cli.py`: interactive bootstrap with no echoed password.
- `apps/api/migrations/`: initial Alembic identity/session/audit/outbox migration.
- `apps/api/tests/`: real PostgreSQL HTTP integration and pure policy cases.
- `.env.example`, `docs/runbooks/development.md`: reproducible execution, no secrets.

## Global constraints and review focus

x86-64-v1 mandatory; no prohibited search/ISA dependency; no production data;
no public signup; token hashes only; current grants checked on each request;
CSRF + Origin on authenticated mutations; no destructive database setup on startup.
Review inactive/revoked accounts, time boundaries, origin/token mismatch,
database rollback, generic auth failures and concurrent failed logins.

## Task 1: Failing behavioral acceptance

- [x] Install locked project tooling in a local venv; start a new isolated
  PostgreSQL dev container, without touching pre-existing Altvia containers.
- [x] Add tests for login persistence/hash-only storage, wrong/inactive account,
  logout/expiry/revocation, CSRF/origin, invalid body, readiness and safe errors.
- [x] Add policy table cases for explicit client ceilings, manager scope,
  project membership, assigned agents and no administrator content bypass.
- [x] Run tests against a minimal empty app and observe assertion failures.

## Task 2: Implement the boundary and persistence

- [x] Implement `create_app(settings: Settings | None = None) -> FastAPI`; settings require
  PostgreSQL URL, exact HTTPS public origin and secure cookies.
- [x] Model and migrate users/sessions/global roles/audit/outbox/login throttle state.
  Use transactions, random tokens, UTC and Argon2id defaults from ADR-0003.
- [x] Implement POST auth/sessions, GET auth/me and DELETE current session;
  never accept client-supplied roles/actor/version fields.
- [x] Bootstrap through a password-prompting command, no HTTP signup.
- [x] Apply per-IP/account durable rate controls, generic failure, bounded
  login hashing concurrency; record redacted events atomically.
- [x] Run the full API suite, Ruff and mypy; fix causes, not assertions.

## Task 3: Migration/recovery proof and publication

- [x] Upgrade empty DB; test HTTP/API against real PostgreSQL. Validate session
  persistence across app recreation, migration downgrade/upgrade on disposable DB.
- [x] Document exact commands/results, dependency versions, development-only
  container digest, pending target CPU/UI/Compose/worker/CI gates.
- [ ] Independent final code review, address material findings and rerun affected
  suite. Commit intended files only and push main without PR.

Ledger: record executed steps/results in `docs/phase-1-evidence.md`. Phase 1B
uses impeccable for the real frontend, and Phase 1C adds process/deploy/CI. Never
declare FR-001 or Phase 1 complete before those gates and the real VM proof.
