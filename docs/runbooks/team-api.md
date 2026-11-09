# Team identity administration API

Scope: Phase 1C-b, ADR-0009. Team metadata and rosters are available through the
real API; the browser currently provides login/account/logout only. Account
provisioning, passwords and platform-role mutation retain the restricted CLI.
No real team or workbook row is seeded by application startup.

Authenticate through the existing HTTPS session flow. Requests use the same
configured origin and cookie; never put a session or CSRF token in a URL or
browser storage. Writes include the exact Origin and X-CSRF-Token from the
current authenticated /api/v1/auth/me response. Only identity.manage is allowed
in this slice; ordinary roster membership grants no administration/content role.

## Supported routes

| Method/path | Input and result |
| --- | --- |
| GET /api/v1/users | Safe internal {id,display_name,email,active} summaries for account selection |
| GET /api/v1/teams | Team summaries, including archived teams |
| POST /api/v1/teams | {name}, Idempotency-Key; 201 team or 200 historical replay |
| GET /api/v1/teams/{id} | Team detail and ETag |
| PATCH /api/v1/teams/{id} | Nonempty subset of {name,active}, If-Match; 200 detail |
| GET /api/v1/teams/{id}/members | Active roster entries {user_id,display_name,account_active} and team ETag |
| POST /api/v1/teams/{id}/members | {user_id}, If-Match, Idempotency-Key; 201 membership change or 200 no-op/replay |
| DELETE /api/v1/teams/{id}/members/{user_id} | If-Match; mark membership inactive, 204 and team ETag |

Use the account UUID from GET /users, never a source alias or fabricated user.
Team names are trimmed, 1..150 characters. Different UUIDs may have the same
display name; no implicit name merge. PATCH fields are optional but cannot be
null; at least one known field is required. Extra fields are rejected.

Collections accept limit 1..100 (default 50) and next_cursor verbatim from the
previous response. Order is ascending UUID; pagination is live. Cursors are
bound to users, teams or that specific team's members. Unsupported filters/sort
parameters return 422 instead of silently broadening the returned list.

## Concurrency and retry

Send the team's quoted ETag as If-Match, for example `If-Match: "2"`. Every real
metadata/roster change increments the team once. Repeating an unchanged value
with a current version is a no-op, with no duplicate audit/outbox event. A stale
precondition returns 409; refetch before another edit, without overwriting it.

Generate a unique Idempotency-Key per intended POST, and reuse it for retries of
that same normalized request. Allowed characters: ASCII letters/digits, period,
underscore, colon and hyphen, length 1..128. Membership request identity includes
the original If-Match. A matching replay returns 200 and the original safe
result/version, which may now be historical. It does not restore a subsequently
removed membership. Refetch current state before continuing. Changed body or
precondition with the same key returns 409. A failed validation/version check
does not consume a new key.

Records persist at least 168 elapsed hours; no expiry purge/key-reuse job exists.
Authorization is checked again before every replay. Revoked or inactive actors
cannot retrieve stored outcomes. Metadata, version, audit/outbox and outcome
commit together; a failed transaction leaves none of the partial effect.
Outbox delivery remains a later Phase 1 task.

## State and operational limits

Archive a team using PATCH active=false; this preserves its roster and history.
Archived teams reject new membership operations. New/reactivated membership
requires an active account. Account deactivation preserves roster history while
account_active=false makes that state explicit. Membership does not activate an
account or confer a client grant, scoped role or platform capability.

JSON writes are bounded to 16 KiB before parsing and require application/json.
Missing required headers return 428; invalid body/query/header input 422; version
or idempotency conflict/inactive target 409; absent target 404; unauthenticated
401; forbidden/Origin/CSRF 403. Database/schema unavailability returns safe 503.
Private responses are no-store and errors do not echo credential/body values.

Readiness checks the required table/column structure through PostgreSQL catalog
reflection and probes user-table read access. It does not require granting read
access to insert-only audit tables. Missing team schema fails readiness while
liveness remains healthy. This is not a complete migration/security audit.

Migration b46087000003 is additive. The completed application can be reverted
while retaining added tables; do not downgrade an operational database to remove
teams/rosters/idempotency history. Downgrade/upgrade proof used only the explicitly
enabled disposable altvia_test database. Production rollback requires reviewed
schema compatibility and backup. No deployment or target-VM homologation occurs
in this slice. See docs/phase-1c-evidence.md for actual acceptance evidence.
