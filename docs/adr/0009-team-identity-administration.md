# ADR-0009: Team identity metadata and membership administration

Date: 2026-11-09. Status: selected for Phase 1C-b; implementation proof pending.

Context: foundation needs real teams and employee rosters before projects. The
existing identity contract permits identity.manage for teams, while the security
matrix groups operational team content with client/project management. Resolve
that distinction explicitly before introducing endpoints.

Decision: platform administrators may administer team identity metadata/rosters
and list internal account summaries. This conveys no client, project, ticket or
work permission. Ordinary team membership is organizational, never a role or a
client ceiling. No scoped team delegation is introduced in this slice. Existing
resource RBAC rules remain mandatory when resource modules are implemented.

Persist teams (UUID, name, active, positive version, created/updated timestamps)
and team_members (team/user composite PK, active, created/updated timestamps).
Names are 1..150 trimmed characters; UUIDs are identity, so duplicate display
names do not merge teams. Archive through active=false, preserving the roster.
No hard-delete endpoint. Inactive teams cannot receive new members, and new or
reactivated memberships require an active account. Removal retains inactive
membership history. Account deactivation does not silently rewrite team history.

Every team or membership write requires the secure session, exact Origin,
session-bound CSRF and current identity.manage capability. Reuse the identity
management advisory lock before taking the session row lock; recheck privileges
inside the write transaction. This serializes writes with account/role changes
and prevents stale privilege/member-activation races. Team/user row mutations
never change keys and use NO KEY UPDATE. Mutation, version, audit, outbox and
idempotency outcome commit together.

POST /teams and POST /teams/{id}/members require Idempotency-Key. Store actor,
canonical route/key, normalized request hash (including If-Match for membership),
original safe result/status and timestamps in idempotency_records. Replay with
the same hash returns 200 and the original outcome after current authorization;
a different hash returns 409. No new domain/audit/outbox effect on replay. Records
are retained for at least 168 elapsed hours, independent of DB session timezone;
no purge/reuse job is added while retention
is unresolved. A replay is historical outcome, so refetch current state before
another edit. Unique DB keys and serialized writes protect concurrent retries.

PATCH and membership writes require the team's quoted positive If-Match version:
missing 428, malformed 422, stale 409. A real roster or metadata change increments
the team once. A no-op retains the version and emits no event. A fresh mutation
uses current version; a matching idempotent replay precedes version comparison.
GET detail and mutation responses include ETag. PATCH fields are optional but
not nullable, and require at least one supplied field in both runtime and schema.
Lists use fixed UUID order,
bounded limits and route-scoped opaque cursors; no shared identity cache.

Consequences: identity metadata is globally administrative but resource content
remains scoped. No team can be used as an implicit permission grant. HTTP account
mutation, scoped role binding, client grants and frontend administration remain
later work. No new native dependency or target-CPU compatibility claim.

Proof: real DB migration/constraints/restart-independent persistence, authorized
HTTP lifecycle, unauthorized/CSRF/Origin tests, concurrent retries/stale versions,
no-op/replay/rollback, inactive account/team cases and generated-contract checks.
