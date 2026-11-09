# ADR-0017: Foundation worker and identity activity

Date: 2026-11-09. Status: accepted for implementation.
Master phase boundary: complete Phase 1, stop before Phase 2.

## Scope and choices

Phase 1 still requires the worker/Redis runtime and configuration/CI proof. Use
Dramatiq 2.2.1 with its Redis broker and default JSON encoder, redis-py 8.1.0
without native extras, and Redis 7.4.12 compiled for x86-64-v1 on pinned Alpine.
Redis is transport only; PostgreSQL remains event and business truth. Reuse the
hardened API image for the worker, rather than another Python dependency graph.
No pickle, dynamic function name, expression or code from an event is executable.

The first real consumer projects existing identity/team outbox events into a
durable administrative activity feed. Audit logs remain immutable forensic truth;
the separate read projection lets the API retain insert-only audit/outbox grants
and expose bounded, allowlisted activity without reading operational queue state.
This implements current identity history, not ticket automation or notifications.
Existing global identity.manage authorizes all activity reads; team read roles
and roster membership do not grant them. Historical actor authorization is not
reinterpreted as authority to perform a new action: projection grants nothing.

## Durable processing

The dispatcher leases due pending events or expired processing leases with
FOR UPDATE SKIP LOCKED, advances attempts and commits before broker publication.
Each message contains only an event UUID for one registered identity actor. The
consumer rereads authoritative PostgreSQL data, locks the outbox row, validates
type/schema/payload and transactionally inserts processed_events + activity_events
and marks delivered. Replay after commit has no second effect. Never trust a
serialized event body or actor as authorization. Current identity event types are
explicitly allowlisted; unknown/malformed schema enters logical dead-letter.

Dispatch in bounded batches; leases 30 seconds; at most 8 attempts; exponential
backoff starting at 5 seconds, capped at 15 minutes, with jitter. Publication
failure updates only the still-owned processing lease. Redis loss, worker crash
before/after publication and redelivery after effect commit recover from outbox.
No automatic purge. Dead events have a fixed safe error code. Restricted CLI
status and typed-UUID-confirmed replay expose operational recovery without an
arbitrary job or SQL interface. Broker middleware retries are disabled so durable
PostgreSQL owns retries; expired leases recover failures whose database update
also failed. Redis-only acknowledgements never establish delivered status.

One worker process runs two consumer threads and a bounded dispatcher loop.
SIGTERM stops dispatch and drains consumers within the configured grace period.
Health checks require fresh loop heartbeat and DB/Redis connectivity. API remains
available during Redis outage because identity writes still commit durable events.
Readiness must not falsely require the queue for synchronous identity operations.

## Schema, credentials and read contract

Expand-only migration adds outbox last_error_code, indexed activity_events and
processed_events. Existing outbox/audit data is preserved and projected on first
worker start. Downgrade refuses while new durable rows exist; never erase history
to roll back. Old API remains compatible with the expanded schema.

API uses existing altvia_app, adding SELECT on activity_events only. Worker uses
separate altvia_worker credential: SELECT/UPDATE outbox_events, SELECT/INSERT
processed_events/activity_events, no user/role/session mutation, audit access,
schema/database creation or role administration. Migrations alone use owner.
Redis and worker secrets stay in external read-only files; API/web get no Redis
or worker credential. Redis has no host port, runs non-root in a private queue
network with authentication, memory bound and no persistence assumption.

GET /api/v1/identity-activity requires fresh identity.manage. Cursor is bound to
occurred_at DESC + event_id DESC; limit 1..100, default 50. Response fields: event_id,
resource_type, resource_id, event_type, occurred_at, actor_id nullable, actor_kind,
aggregate_version, correlation_id and allowlisted non-secret details. No names,
emails, passwords, hashes, tokens, payload dumps or queue exception text. Browser
adds a bounded recent-history section inside existing account administration,
using the current session-owned cache and established Impeccable visual system.

## Remaining closure proof

Add safe JSON request/worker logs with correlation IDs, excluding bodies, raw URLs,
tokens and exception text. Add maintained SAST and tracked-source secret scanning
to CI, alongside existing dependency/image gates. No unapproved production
retention, capacity/SLA promise, OIDC provider, real account provisioning or deploy.
OIDC integration remains deferred under ADR-0003 until issuer/claims are supplied.

Prove PostgreSQL/Redis integration, concurrent consumers, crash/redelivery,
unavailable/lost Redis, DLQ/replay, least-privilege DB roles, migration preservation,
HTTP ACL/pagination/log redaction, real UI recovery and all hosted gates. Build and
scan every actual service image, then execute the same changed artifacts on the
supplied target CPU. Phase 6 production capacity/backup policy/pilot gates remain
separate; Phase 1 closes only after its requirements have executed evidence.
