# Development: foundation identity API

Scope: Phase 1A. Python 3.12, uv, PostgreSQL 17. No SQLite fallback. The checked
uv.lock pins the tested dependency versions and hashes. No production account
or database is created automatically. The Phase 1B browser runbook is
`docs/runbooks/browser-development.md`. Worker/Compose remain later slices.

## Local API

```powershell
uv sync --locked --python 3.12
Copy-Item .env.example .env
```

Edit the ignored `.env`: a dedicated PostgreSQL database/credential and exact
HTTPS public origin. Use a migration-owner credential only for migrations;
production runtime must have least-privilege DML, no DDL/TRUNCATE/trigger bypass.
Credential provisioning/production grants are a pending deployment gate.

```powershell
uv run alembic -c apps/api/alembic.ini upgrade head
uv run alembic -c apps/api/alembic.ini check
uv run python -m altvia.cli bootstrap-admin --email admin@example.invalid --name Administrator
uv run uvicorn altvia.main:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers
```

The bootstrap command prompts twice without echo, accepts no password argument,
requires a terminal and refuses a second platform bootstrap. No credential is
shipped in the repo. CLI reset invalidates all prior sessions:

```powershell
uv run python -m altvia.cli reset-password --email admin@example.invalid
```

## Restricted account administration (Phase 1C-a)

The CLI is for an operator with trusted host access and the management database
credential. It is not an HTTP endpoint or an alternative login for employees.
Restrict that host/credential and retain operator access logs. Management audit
events identify the actor as `management_command`; they do not claim a named
employee actor. No real account operation was performed during development.

Provision an ordinary internal account with no role/content grants:

```powershell
uv run python -m altvia.cli create-user --email employee@example.invalid --name "Employee Name"
```

This prompts twice without echo, uses the same Argon2id policy and requires an
interactive terminal. Passwords must be at least 14 characters and no more than
1024 UTF-8 bytes. Never pass a password as an argument, pipe, environment variable
or shell-history entry. Insecure getpass fallback is refused. Invalid arguments,
configuration/engine errors and cancellation have safe output.

State/privilege commands require typing the target account email to confirm:

```powershell
uv run python -m altvia.cli disable-user --email employee@example.invalid
uv run python -m altvia.cli enable-user --email employee@example.invalid
uv run python -m altvia.cli grant-admin --email employee@example.invalid
uv run python -m altvia.cli revoke-admin --email employee@example.invalid
```

Grant only to an active account. Every actual state or privilege change revokes
all prior sessions and advances auth_version. Reactivation never restores an old
token. Repeating an unchanged state creates no second audit/outbox effect.
The last active platform administrator cannot be disabled or demoted, including
concurrent operations. First establish another active administrator if replacing
one. A platform role grants identity management only; client content still needs
explicit scoped grants. Password reset preserves disabled state and roles.

Account/role/session/audit/outbox writes commit together. A shared transaction
advisory lock serializes management operations; all future identity-management
writers must reuse this service protocol. No schema migration is added here.
CLI success means the transaction committed; rejected/aborted operations do not
apply a partial change. The team metadata API is documented in team-api.md.
HTTP account/role mutation and administrative UI remain future Phase 1 work.
Use these commands only against the intended configured database.

Delegate read access to one existing team's metadata and roster:

```powershell
uv run python -m altvia.cli grant-team-role --email employee@example.invalid --team-id TEAM_UUID --role viewer
uv run python -m altvia.cli revoke-team-role --email employee@example.invalid --team-id TEAM_UUID --role viewer
```

Replace TEAM_UUID with the exact existing team ID. Both commands require typing
the target email and team UUID before opening a database connection. Only viewer
and operations_manager are accepted; both provide the same metadata read scope
in the current API. These flags are rejected on other commands. No password is
requested. New grants require active user/team; revocation works after disable
or archive. Existing grants remain readable after archive. Same role on multiple
teams is supported; revoke affects only the exact user/team/role combination.
Actual changes revoke all target sessions and atomically advance auth_version,
audit and outbox. No-op repeats have no second effect. Team roles cannot write
teams/rosters, enumerate /users, replay administrative writes or grant client
content access. Team membership alone grants nothing. No real grant was provisioned.

Expose the API through an HTTPS reverse proxy at ALTVIA_PUBLIC_ORIGIN before
browser use. Keep cookies secure in development too. Until a trusted proxy
configuration is explicitly provided, do not trust client X-Forwarded-For.
The per-source login limiter sees the direct peer (proxy in a proxied setup);
per-account limits remain independent. Trusted ingress IP extraction is a
Phase 1C task. All login requests send JSON and exact Origin. Later authenticated
mutations also send X-CSRF-Token from login or GET `/api/v1/auth/me`.

Health: `/api/v1/health/live`, `/api/v1/health/ready`. OpenAPI: `/openapi.json`.
API does not create schema on startup. Ready requires database/users schema.
Private API responses are no-store. No auth token/password is logged by this code.

## Checks and disposable database safety

```powershell
uv run ruff check apps/api
uv run ruff format --check apps/api
uv run mypy
uv build
```

Integration tests truncate fixture tables. Only use a dedicated disposable
database named **altvia_test**, with explicit `ALTVIA_ALLOW_TEST_DB=1`.
Never point tests at operational data or reuse a production credential.
Set ALTVIA_DATABASE_URL and ALTVIA_PUBLIC_ORIGIN=https://testserver in a separate
ignored `.env.test`, and ALTVIA_ALLOW_TEST_DB=1 in the shell/test process.

```powershell
$env:ALTVIA_ALLOW_TEST_DB='1'
uv run --env-file .env.test pytest -q
```

The test fixture upgrades the disposable DB before tests. Migration rollback
proof is performed only on that same isolated fixture database, then upgraded
again before rerunning tests. Never downgrade operational data to base.

## Windows Podman workaround used in this session

Existing user containers were preserved. A new isolated Postgres container used
`--cgroups=disabled` because the WSL Podman VM lacked the pids cgroup controller.
This is a development-only workaround, not production configuration. Its host
forwarding was unreachable from Windows, so a Python sidecar ran tests on the
same container network namespace. No host/sshd/network security settings changed.

The sidecar mounted the repository at `/workspace`, installed hash-locked
requirements exported from uv.lock and used its own Linux Python dependencies,
not the Windows venv. Database and runner images are recorded in Phase 1 evidence.
Secret env files remained ignored. Exact executed test commands:

```powershell
uv export --quiet --locked --format requirements-txt --no-emit-project --output-file .requirements.test.txt
podman exec altvia-workspace-phase1-api-test python -m pip install --require-hashes -r .requirements.test.txt --quiet --root-user-action ignore --disable-pip-version-check
podman exec --env PYTHONPATH=/workspace/apps/api --env ALTVIA_ALLOW_TEST_DB=1 altvia-workspace-phase1-api-test pytest -q --tb=short
podman exec --env PYTHONPATH=/workspace/apps/api altvia-workspace-phase1-api-test alembic -c apps/api/alembic.ini check
```

The runner is a disposable tooling container running as root; it is not the
production API image. Application non-root Dockerfiles, Compose resource limits,
Redis/worker delivery and target VM evidence remain pending. When work is over,
stop only task-owned containers. Retain database volumes unless deletion is
explicitly authorized. Do not alter pre-existing Altvia containers.
