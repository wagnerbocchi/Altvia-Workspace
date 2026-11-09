# ADR-0011: Reproducible API container runtime

Date: 2026-11-09. Status: implemented and development-tested for Phase 1C-d.
Actual Docker/Linux evidence is in docs/phase-1c-evidence.md. Production image
security and target-VM homologation remain open; this is not deployment approval.

Intent: run the existing persisted identity/team API through a real HTTPS proxy,
without granting its long-lived database connection schema or audit modification
rights. This is an incremental runtime slice; it does not complete Phase 1.

Decision: package the current Python API and Alembic in one immutable candidate
image, with locked production dependencies, explicit copy paths and a non-root
user. A separate one-off migrate service uses the same image and owner credential.
It applies migrations and provisions the fixed altvia_app database login with an
explicit table privilege list. The API receives only that runtime credential.
Audit/outbox are insert-only for the API. Public schema creation is revoked.
Do not grant ownership, DDL, role management, audit reads or future table privileges.
Existing elevated runtime roles are refused instead of silently normalized.
Refusal includes direct database/schema DDL, unexpected table/column/PUBLIC ACLs
and grant options, before password rotation or partial grants. A table REVOKE
does not remove column grants and is not used as the sole elevation check.

Compose includes postgres, migrate, api and an unprivileged nginx HTTPS ingress.
Only ingress publishes a loopback-bound HTTPS port by default; API/Postgres have
no host ports. Postgres uses a named persistent volume. Mounted external files
provide credentials and TLS material; no credentials in image/build args/Compose.
Pydantic's existing file-secret source loads /run/secrets/ALTVIA_DATABASE_URL.
Existing explicit constructor/env configuration precedence is retained. Startup
never creates schema. Health/readiness, resource bounds, read-only application
filesystems, dropped capabilities and no-new-privileges are enforced.

The proxy forwards only API paths, preserves Host and never enables arbitrary
forwarded-IP trust. TLS 1.2/1.3; no access logs containing URLs, cookies or bodies.
Its healthcheck connects locally while validating the configured origin's TLS
hostname, including certificates without a loopback IP SAN. All nginx temporary
directories live on /tmp so a read-only root filesystem can start successfully.
No browser UI change or new auth capability. Web ingress, worker/Redis and storage
remain later increments; do not add idle services or acknowledge events without
a real consumer. Outbox business/event contracts remain ADR-0004.

Alternatives: a full topology with idle workers and mock consumers would obscure
unfinished behavior; first packaging only the API without TLS or separated DB
credentials would leave the runtime trust boundary untested. Reuse of the current
FastAPI factory, Alembic, settings and identity services avoids a second backend.

Acceptance: clean image build; real TLS login/CSRF/team ACL flow; runtime DDL and
audit mutation denied; account/team/session persistence after process/container
recreation; failed DB readiness is503 with liveness intact; graceful SIGTERM;
no exposed DB/API host ports; credentials/raw sources absent from build context
and image; rerunnable migrations; safe cleanup preserving volumes. A dedicated
synthetic stack and explicit test opt-in are required for mutation proof.

Candidate amd64 image digests are recorded with runtime versions and scan results
after actual verification. Debian bookworm families only, no -march=native or new
higher-ISA dependency. Local/hosted CI success never proves x86-64-v1 compatibility
on the unavailable VM. Production deployment, real role provisioning and remote
security changes remain unauthorized; Q-01 and all production gates remain open.
