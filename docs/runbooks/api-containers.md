# API container runtime

Scope: Phase 1C-d, ADR-0011. This packages the existing identity/team API,
PostgreSQL and API-only HTTPS ingress. Web pages, worker/Redis, production ingress
trust, backups/load/security gates and target-VM homologation remain separate.
No real account, production role or deployment is created by this repository.

## Requirements and secrets

Use a Linux amd64 Docker Engine with current Compose supporting health/completed
dependencies and resource limits. Candidate images use immutable amd64 digests.
The Windows Podman machine used during development lacks cgroup memory/pids
controllers: its Compose startup fails at memory.max. Do not remove the checked-in
resource bounds or change that machine to hide the failure. Hosted Linux Docker
is the functional Compose acceptance environment; real target proof stays pending.

Supply an external restricted directory, never a committed env file, with:

| File | Meaning |
| --- | --- |
| postgres_password | Password for the dedicated cluster's altvia_owner login |
| owner_database_url | postgresql+psycopg URL for altvia_owner, host postgres, selected DB |
| runtime_database_url | Same target URL for fixed altvia_app, distinct strong password |
| tls_cert / tls_key | Certificate chain and matching key for the exact HTTPS origin |

Percent-encode URL credentials. Do not pass passwords through shell arguments,
build args or Compose environment. Restrict the parent directory to its operator
(mode0700 or equivalent ACL). File-backed Compose secrets are read-only bind
mounts; Compose cannot reliably remap their UID/mode. Files must be readable by
their non-root container users, for example mode0444 inside that inaccessible
parent directory. Restrict directory traversal, do not publish secret contents.
API receives only runtime URL; migrate receives owner and runtime URLs; ingress
receives only TLS files. Owner password is mounted only into PostgreSQL.

Settings uses Pydantic's file-secret source at /run/secrets when present. Explicit
constructor values and environment still take precedence for existing development
flows; Compose deliberately supplies no ALTVIA_DATABASE_URL environment value.
Do not inject a host owner URL into the long-lived API.

## Build and start after environment authorization

These are operator procedures, not evidence of production deployment. Select a
reviewed application image identifier and real certificate/secret directory first:

```bash
export ALTVIA_SECRET_DIR=/restricted/altvia-secrets
export ALTVIA_PUBLIC_ORIGIN=https://workspace.example.invalid:3444
export ALTVIA_API_IMAGE=altvia-api:reviewed-build
export ALTVIA_DATABASE_NAME=altvia_workspace
docker compose -f infra/compose.yaml config --quiet
docker compose -f infra/compose.yaml build migrate
docker compose -f infra/compose.yaml up -d --wait --wait-timeout 150
docker compose -f infra/compose.yaml ps -a
curl --fail --cacert "$ALTVIA_SECRET_DIR/tls_cert" "$ALTVIA_PUBLIC_ORIGIN/api/v1/health/ready"
```

Only ingress publishes 127.0.0.1:3444 by default. API/Postgres have no host ports;
the database network is internal. External availability requires a separately
authorized infrastructure plan. API-only ingress returns404 for page routes.
Proxy resolves the container engine's DNS again after API recreation, preserves
Host, removes client forwarding headers and never enables arbitrary proxy trust.
TLS verification is required; do not use curl -k as acceptance evidence.

Postgres starts on a named volume. The one-off migrate job applies Alembic, then
provisions runtime privileges. Schema and grants are separate transactions: if
provisioning fails after a migration, API stays stopped; inspect safely and rerun
the job. Do not downgrade or delete the volume to recover. Startup never silently
creates users or migrates schema in the API process.

The cluster must be dedicated to this application. Existing altvia_app ownership,
role memberships, superuser/createdb/createrole/replication/bypassrls are refused.
Unexpected database/schema DDL rights or table/column/PUBLIC grants are also
refused before password or privilege changes, including GRANT OPTION. Table REVOKE
alone is insufficient to remove column ACLs. Operator review is required for an elevated pre-existing
state; the provisioner does not silently adopt it.
Provisioning serializes, resets this role's direct public-schema table grants and
allows CRUD only on the current identity/team tables. Audit/outbox are INSERT
only, Alembic metadata is not readable, and persistent DDL/role management are
denied. Public schema creation and public database privileges are revoked. Future
tables need explicit reviewed grants; worker privileges are not pre-granted.

Initial account provisioning still requires authorized host access and hidden
interactive input, using the runtime connection and existing management protocol:

```bash
docker compose -f infra/compose.yaml exec api python -m altvia.cli bootstrap-admin --email admin@example.invalid --name "Identity Administrator"
```

Do not use the automated test fixture for real accounts. Other account/team role
commands are documented in development.md. File/secret parse errors and provisioning
failures must be inspected without copying URLs, passwords or raw file contents.

## Black-box proof

With Node/pnpm installed and locked dependencies synchronized:

```bash
uv sync --locked
pnpm install --frozen-lockfile
export ALTVIA_ALLOW_CONTAINER_TEST=1
uv run python scripts/container_smoke.py
```

This creates a fresh random altvia-test-* project, only the altvia_test database,
random synthetic credentials and a synthetic CA-trusted test certificate. It
builds the real API image, including a dirty-context secret canary, and tests TLS
login, Secure/HttpOnly cookies, Origin/CSRF denial, explicit scope isolation, API
and database recreation with session/data survival, failed DB readiness with
healthy liveness, migration rerun, non-root/read-only runtime and graceful SIGTERM.
The API suite separately exercises real database privilege denial and elevated
role refusal. Logs are checked for the generated credential values.

Only its task-scoped Compose project is stopped/removed in finally. No -v flag
is used: volumes and private test configuration under ignored .superpowers remain
for inspection/recovery. Failure stdout/stderr stays in that private directory;
do not upload it as an artifact or print it without secret redaction. Existing
containers, operational databases and source workbooks are never selected.

## Restart, rollback and limits

```bash
docker compose -f infra/compose.yaml stop
docker compose -f infra/compose.yaml up -d --wait --wait-timeout 150
```

Reuse the same project, volume and matching secrets. Changing an initialized
Postgres password file does not automatically rotate the database password.
Provisioning can update altvia_app's password from its supplied URL; coordinate
any actual rotation separately. Owner credentials never belong in runtime.

Before upgrades, identify the real volume, back up and validate schema/image
compatibility. Rollback selects the previous immutable API image only while its
schema/privilege contract is compatible; never automatically run downgrade.
This slice does not change schema. No backup/restore acceptance or operational
resource capacity is claimed from the provisional Compose memory/CPU bounds.
The API uses one worker, preserves the secure session policy and treats the proxy
as the direct login source until a reviewed trusted-ingress configuration exists.
Actual guest/native-ISA, SCA/image, load and recovery release gates remain open.

## PostgreSQL-only runtime capability

ADR-0012 removes unused SQLite from the final API image: the native Debian
libsqlite3-0 package and CPython's optional sqlite3/_sqlite3 modules are absent.
The general-purpose builder and developer Python still support their original
capabilities. This is not a general-purpose Python/SQLite container; alternative
SQLite database URLs were already rejected by the application configuration.

The image build runs a standard-library capability/import checker as its final
non-root user. The Compose smoke verifies rejection on the unchanged actual
builder stage and success inside the running API. The same diagnostic is available
without credentials or schema changes:

```bash
docker compose -f infra/compose.yaml exec api python check_api_runtime.py
```

It must report sqlite=absent and api_imports=passed. It checks modules, package
status, shared-object presence and loader discovery, plus required API/CLI,
migration, TLS and compression imports. Do not reinstall SQLite, override its
library search path or bypass the check to accommodate an unsupported script.
A real future requirement needs a reviewed corrected library/capability contract.

Measured same-DB image scans removed all 19 SQLite findings, including the
applicable installed critical, while keeping all 27 Python dependency entries
unchanged. Remaining image findings and exact hashes are in
docs/security/api-container-scan.md. Production image security is still gated.
Rollback to an earlier SQLite-containing image reintroduces this component and
needs security review; no schema downgrade or data-volume reset is involved.
