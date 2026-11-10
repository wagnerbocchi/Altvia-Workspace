# ADR-0023: Scoped project member administration

Date: 2026-11-10. Status: selected before implementation.
Scope: Phase 2F, completing the browser member workflow of FR-002.

## Decision and alternatives

Extend ADR-0019's existing project access service and HTTP write protocol.
Managers add an existing account by its known email, choose a project role,
and may later change that role or remove direct access. There is no account
discovery endpoint or global directory for project managers. Exact-email lookup
followed by a separate grant would introduce a discovery surface and an extra
stale selection; team-only candidates would incorrectly exclude cross-team work.
The add operation resolves the email inside the authorized transaction instead.

No new table, migration, dependency, native binary, global role or customer
ceiling is introduced. Keep the restricted CLI as the recovery mechanism.

## Invariants and transaction

Every write acquires the identity advisory lock before session authentication,
checks Origin/CSRF and fresh scoped project management, and locks the project.
Client projects still require the separate customer ceiling and either inherited
client operations_manager or explicit project_manager plus membership. Platform
administration and owning-team metadata never bypass this boundary.

Reuse one domain helper for both CLI and HTTP: change membership and project
binding together, invalidate target sessions/auth version, advance project version
and emit the existing redacted project.access_changed audit/outbox atomically.
Coherent same-state is a no-op, including inactive references. Real grants/role
changes require active account/project/client and an existing customer ceiling.
Removal works with inactive references and repairs either half of an access pair.
Removing an absent pair is a no-op without exposing whether an arbitrary UUID
exists globally. No last-manager guard is added; CLI recovery remains explicit.
Self-demotion/removal is allowed and invalidates the caller's current session.
Historical task assignments remain intact and never grant access themselves.
Inherited client access is not revoked by removing a direct project membership.

## HTTP contract

All paths use /api/v1, no-store transport and strict bodies.

| Route | Contract |
| --- | --- |
| POST /projects/{id}/members | {email,role_name}; If-Match Project and Idempotency-Key; 201 minimal {project_id,user_id}, replay200 |
| PATCH /projects/{id}/members/{user_id} | {role_name}; If-Match Project; 204 and current Project ETag; existing access pair required |
| DELETE /projects/{id}/members/{user_id} | If-Match Project; 204/current Project ETag, absent pair no-op |

Roles are viewer, agent, project_manager. Email uses existing identity strip/
casefold normalization, bounded to 254 characters and its existing syntax policy.
Unknown, inactive or customer-ineligible add targets return the same 422
invalid_project_member; inactive project/client return 409. No email is returned
or persisted in event payloads/receipts. Member pages add project_version, verified
unchanged before and after the roster query; a concurrent change returns409. The
browser uses this reviewed version for writes, and disables changes while parent
and page versions disagree. Read snapshots never take project locks after auth.

Authorize and parse a syntactically valid If-Match before consulting a saved POST
receipt. A committed replay returns only the original IDs, even after role change,
removal or target inactivity, and never repeats a grant. Fresh POST compares the
reviewed project version before resolving the target. Same key with different
normalized intent is 409. Stale version409, missing precondition428, malformed422,
hidden/absent parent404, readable forbidden write403, anonymous401. PATCH targets
without either project-access record return404. DELETE absent UUID is204.

## Browser contract and acceptance

A dedicated /projects/{id}/members screen keeps session-owned add intent mounted
across parent/list refresh failures. The project detail links there. Capture
email, role, project version and key together; uncertain POST retries only that
original intent. Replayed receipt confirms submission only: refresh current
project/members before permitting another edit. Never infer a role/version from
receipt IDs. Member edits/removals capture the reviewed project version and
member identity; conflicts require explicit reload/review, never automatic rebase.
Warn that access changes end target sessions, direct removal preserves inherited
client access, and changing one's own access requires login again. Confirm removal
and self-demotion, preserve history, restore keyboard focus and lock pending writes.
All known-email grants first freeze and show the exact email, role, version and key
for explicit confirmation; this covers self-targets under the existing Unicode
identity normalization without relying on browser casefold matching.

Prove real persistence/ACL, stale/replay/session invalidation, inactive/no-op,
split-pair repair, concurrent writes, event redaction and no global identity grant.
Browser proof covers lifecycle, uncertain committed/uncommitted POST, failed refresh,
conflict review, read-only scope, self-removal, keyboard/axe and light/dark mobile/
desktop. Apply Impeccable, fresh source review, hosted gates and actual target-VM
qualification before labeling this slice complete.

## Phase 2 traceability and rollback

Phase 2A-E cover clients/areas/project registry, tasks/subtasks, internal owners/
participants/comments/history/deadlines/blocks, list/Kanban/filters/FTS/My Work,
contacts and ticket-default configuration. This increment closes browser member
administration only. Master sections 6/7/8.3 still require basic persisted project
milestones and external work participants in subsequent bounded slices. Advanced
calendar/Gantt/dependencies remain FR-016/P2 backlog. Phase 2 is not closed here.

Rollback to the previous application preserves all existing membership/access
records and events; CLI remains compatible. No downgrade, data deletion, real
account provisioning, production deployment or SSH/security change is authorized.
