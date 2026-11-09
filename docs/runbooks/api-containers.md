# API container runtime

Scope: Foundation, ADR-0011/0013/0014/0017. This packages the identity/team API,
PostgreSQL, standalone web frontend, same-origin HTTPS ingress and identity
activity worker with private Redis transport. Production ingress trust and
production backup/load policies remain separate.
No real account, production role or deployment is created by this repository.

## Requirements and secrets

Use a Linux amd64 Docker Engine with current Compose supporting health/completed
dependencies and resource limits. Candidate images use immutable amd64 digests.
The Windows Podman machine used during development lacks cgroup memory/pids
controllers: its Compose startup fails at memory.max. Do not remove the checked-in
resource bounds or change that machine to hide the failure. Hosted Linux Docker
is also a functional Compose acceptance environment. The current five-image stack
has now passed on the supplied target VM; exact qualified image IDs and remaining
gates are in [the target report](../target-vm-foundation-evidence.md) and
[Phase 1 closure](../phase-1-closure-evidence.md).

Supply an external restricted directory, never a committed env file, with:

| File | Meaning |
| --- | --- |
| postgres_password | Password for the dedicated cluster's altvia_owner login |
| owner_database_url | postgresql+psycopg URL for altvia_owner, host postgres, selected DB |
| runtime_database_url | Same target URL for fixed altvia_app, distinct strong password |
| worker_database_url | Same target URL for fixed altvia_worker, another distinct strong password |
| redis_password | Random URL-safe ASCII password, 32..128 characters |
| redis_url | redis://:password@redis:6379/0, matching redis_password |
| tls_cert / tls_key | Certificate chain and matching key for the exact HTTPS origin |

Percent-encode URL credentials. Do not pass passwords through shell arguments,
build args or Compose environment. Restrict the parent directory to its operator
(mode0700 or equivalent ACL). File-backed Compose secrets are read-only bind
mounts; Compose cannot reliably remap their UID/mode. Files must be readable by
their non-root container users, for example mode0444 inside that inaccessible
parent directory. Restrict directory traversal, do not publish secret contents.
The guarded smoke test uses umask 077. Its synthetic TLS generator explicitly
applies mode 0444 after writing, so creation-time masking cannot block the non-root
proxy. The private parent stays 0700; do not make that directory public.
API receives only runtime URL; migrate receives owner/runtime/worker URLs; worker
receives only worker/Redis URLs; Redis receives only its password; ingress receives
only TLS files. Owner password is mounted only into PostgreSQL. Web receives none.

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
docker compose -f infra/compose.yaml build migrate postgres ingress web redis
docker compose -f infra/compose.yaml up -d --wait --wait-timeout 150
docker compose -f infra/compose.yaml ps -a
curl --fail --cacert "$ALTVIA_SECRET_DIR/tls_cert" "$ALTVIA_PUBLIC_ORIGIN/api/v1/health/ready"
```

Only ingress publishes 127.0.0.1:3444 by default. API/Postgres have no host ports;
the database network is internal. Web also has no host port or database network,
and receives no credentials. The same HTTPS origin serves the existing login and
account screen at /. External availability requires a separately authorized
infrastructure plan. Proxy resolves DNS again after API or web recreation, preserves
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
tables need explicit reviewed grants. API may SELECT the activity projection,
but may not read audit/outbox. The separate worker role can SELECT outbox and
UPDATE only its processing columns; it can SELECT/INSERT processed/activity rows
and INSERT audit for confirmed replay. It cannot alter users/roles/sessions,
payloads, existing history or schema. Both fixed roles receive the same strict
pre-existing ownership, membership, privilege and column-grant refusal checks.

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
pnpm --filter @altvia/web exec playwright install --with-deps chromium
export ALTVIA_ALLOW_CONTAINER_TEST=1
uv run python scripts/container_smoke.py
```

This creates a fresh random altvia-test-* project, only the altvia_test database,
random synthetic credentials and a synthetic CA-trusted test certificate. It
builds the real API image, including a dirty-context secret canary, and tests TLS
login, Secure/HttpOnly cookies, Origin/CSRF denial, explicit scope isolation, API
and database recreation with session/data survival, failed DB readiness with
healthy liveness, migration rerun, non-root/read-only runtime and graceful SIGTERM.
The actual packaged browser flow verifies login/reload, session survival after
web recreation, logout/revocation, document CSP, no identity in SSR, desktop/mobile
light/dark rendering and axe checks. Chromium accepts only the generated test
certificate's public-key pin and maps only the reserved workspace.altvia.test
name. Separate HTTP probes validate the CA/domain SAN without TLS bypass. Browser
probes use browser fetch, because Playwright's Node APIRequestContext does not
share that DNS/certificate configuration. No machine trust store is modified.
Only synthetic PNG captures under each task's screenshots directory are uploaded;
never upload its parent directory, private logs, secret files or browser state.

The API suite separately exercises real database privilege denial and elevated
role refusal. Logs are checked for the generated credential values.

Only its task-scoped Compose project is stopped/removed in finally. No -v flag
is used: volumes and private test configuration under ignored .superpowers remain
for inspection/recovery. Failure stdout/stderr stays in that private directory;
do not upload it as an artifact or print it without secret redaction. Existing
containers, operational databases and source workbooks are never selected.

## Restart, rollback and limits

### Identity worker and transport recovery

PostgreSQL is durable truth. Redis stores only registered JSON messages containing
event UUIDs, has no persistence requirement and exposes no host port. Its internal
queue network is shared only with the worker. The API commits synchronously during
Redis outage; activity catches up when transport recovers. Redis uses 64 MiB
maxmemory/noeviction under a 128 MiB container bound, and disables runtime config,
ACL/module administration and database flush commands. Do not add arbitrary tasks
or treat queue acknowledgements as evidence of a committed projection.

```bash
docker compose -f infra/compose.yaml exec worker python -m altvia.worker health
docker compose -f infra/compose.yaml exec worker python -m altvia.worker status
docker compose -f infra/compose.yaml logs --since 10m worker
docker compose -f infra/compose.yaml stop -t 30 worker
docker compose -f infra/compose.yaml start worker
```

The dispatcher claims at most 25 events with 30-second leases. Delivery and
processed-event deduplication commit together. Failures retry from PostgreSQL
with exponential backoff/jitter, at most eight attempts, then remain dead with
a fixed error code. Logs contain safe structured metadata, never payload dumps,
credentials or raw exception text. There is no automatic purge.

SIGTERM stops further sends between events, leaves unpublished leases recoverable,
and drains two consumer threads. Redis connections have one-second connect and
two-second operation timeouts with zero implicit connection retries; each of
Dramatiq's two thread-join phases has a five-second budget. The packaged test
blackholes Redis while a real batch is claimed, proves exit 0 before the 30-second
grace, restarts the consumer and verifies all 27 interrupted test events project.

Inspect a dead event under authorized database operations before replay. Replay
is an interactive recovery command requiring the exact typed UUID confirmation:

```bash
docker compose -f infra/compose.yaml exec worker python -m altvia.worker replay --event-id EVENT_UUID
```

Replace EVENT_UUID with the reviewed event UUID. A confirmed replay atomically
resets the dead event and appends an audit record; it neither edits historical
payloads nor creates arbitrary executable work. Unknown/invalid schemas remain
dead until the responsible implementation is corrected. Never reset attempts
with ad hoc SQL or delete deduplication rows to force an effect.

Migration b46087000005 expands outbox metadata and adds projection/deduplication
tables. Existing events survive. A downgrade refuses when durable new rows exist;
rollback selects the previous compatible application image while preserving the
expanded database. Do not delete history, downgrade automatically or erase volumes.

### Mandatory image-family transition (ADR-0013)

The current images use Alpine/musl; previous deliveries used Bookworm/glibc.
Do not run the normal restart sequence below against a Bookworm data volume with
the new PostgreSQL image. The new entrypoint refuses any initialized PGDATA
without its exact Alpine runtime-family marker. Only fresh initdb writes it.
Never add that marker to old data to bypass the check. A stock Alpine cluster
without the marker is also refused: its provenance must not be guessed.

Before any authorized real transition, take and verify an approved encrypted
logical backup with the matching old image/Compose definition. Keep that original
project and volume untouched. Create a different destination Compose project
(therefore a fresh postgres_data volume), with a distinct test ingress port and
matching restricted secrets. Start only its postgres service first. Restore the
logical schema/data into its empty application database with pg_restore's
--no-owner --no-acl --exit-on-error options, using the destination altvia_owner.
Do not restore old cluster roles or copy physical PGDATA. Re-run the normal
migrate/provision job afterwards to establish the destination's explicit runtime
grants, then start API/ingress. Existing Alembic history is restored with the data.

Verify row counts/checksums, constraints/indexes, chosen locale/collation policy,
Portuguese FTS, ownership/runtime grants, login/session/negative ACL behavior and
restart recovery before any separately authorized cutover. Logical restore
rebuilds indexes under the destination libc; it does not guarantee identical
locale sorting. Rollback selects the old image and original untouched volume,
never the destination volume under a different libc. No automatic downgrade or
volume deletion. Backup recipients, retention and real cutover remain operator
decisions (Q-09); this document does not authorize production operations.

The guarded container test exercises a synthetic Bookworm dump into a separate
fresh Alpine database, Unicode/checksum/primary-key/FTS preservation, and explicit
unmarked-volume refusal. It is not a real data migration or backup RPO/RTO claim.

### Restart within an already validated image family

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
ADR-0017's expand-only migration and populated-downgrade refusal apply to the
activity increment described above. No operational backup policy or resource
capacity is claimed from the provisional Compose memory/CPU bounds.
The API uses one worker, preserves the secure session policy and treats the proxy
as the direct login source until a reviewed trusted-ingress configuration exists.
Foundation guest/native-ISA, image scans and isolated recovery passed in the
linked closure report. Production load, backup policy and release gates remain open.

## PostgreSQL-only runtime capability

ADR-0012 removes unused SQLite from the final API image. ADR-0013 preserves that
contract on Alpine: sqlite-libs and CPython's optional sqlite3/_sqlite3 modules
are absent. The original Debian implementation removed libsqlite3-0.
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

The final service also excludes pip and ensurepip, including base Python's hidden
global installer and bundled wheel. Dependencies are supplied by a reviewed image
rebuild with uv and the committed lockfile. Do not install packages into a running
service or use it to bootstrap another Python environment. The builder/developer
environment remains general-purpose. The diagnostic additionally reports
package_installers=absent and zlib=1.4 and exercises native compression.

Measured same-DB image scans removed all 19 SQLite findings, including the
applicable installed critical, while keeping all 27 Python dependency entries
unchanged. Remaining image findings and exact hashes are in
docs/security/api-container-scan.md. Production image security is still gated.
Rollback to an earlier SQLite-containing image reintroduces this component and
needs security review; no schema downgrade or data-volume reset is involved.
