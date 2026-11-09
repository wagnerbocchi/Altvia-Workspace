# Development: foundation identity API

Scope: Phase 1A. Python 3.12, uv, PostgreSQL 17. No SQLite fallback. The checked
uv.lock pins the tested dependency versions and hashes. No production account
or database is created automatically. Frontend/worker/Compose are later slices.

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
