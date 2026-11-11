# ADR-0027 Explicit queue access administration

Date 2026-11-10. Selected before implementation for Phase 3B, FR-001/005/012.
The master specification and current user development authorization apply.

## Decision and scope

Extend role_bindings with queue_id and scope_kind queue. One binding per account
and queue has role viewer, agent or operations_manager. This increment delivers
real browser administration and operational queue/category metadata visibility.
Ticket records and lifecycle follow in the next bounded increment. Queue grants
never add customer ceilings, client roles, team membership or platform authority.
Future ticket content must require its explicit customer ceiling and queue role.

Platform configuration administrators and the owning team's explicit
operations_manager administer queue grants. Queue operations_manager is a content
role and confers no configuration or delegation authority. Existing configuration
viewers and explicit queue members can read the bounded roster (account ID,
display name, active flag and queue role), queue metadata, categories and redacted
queue history. Queue membership exposes only its owning team's name/active flag
within that queue response. It supplies no team directory, roster or other queue.

Reuse the existing RBAC representation and project-member HTTP protocol. A second
queue-membership table would duplicate the same authority and require split-pair
repair. Inheriting content rights from configuration/team/client roles would
violate the explicit queue boundary. The additional nullable FK is expand-only.
Older application versions can retain all existing bindings. A rolled-back API
cannot operate queue grants, so preserve the expanded schema and compatible worker.

## Transaction and failure invariants

Take the existing identity write lock before authentication, then owning team,
queue and target account. Target account locks use PostgreSQL FOR NO KEY UPDATE,
matching existing management/project writes and permitting concurrent logout audit
FK key-share locks. Recheck current configuration authority before protected
replay. Actual changes invalidate all target sessions and advance auth_version,
advance the queue aggregate once and atomically emit ticket_queue.access_changed
audit/outbox. No-op writes preserve versions, sessions and events. Actual grants
require active target, queue and team. Removal and coherent no-ops remain possible
with archived references. Absent removal is a no-op without account discovery.
No last-queue-manager guard is needed because configuration authority is separate.
Self-target changes invalidate the current session, while metadata authority stays
independent of the changed queue role.

POST resolves an existing account by known normalized identity email inside the
authorized mutation. Unknown/inactive accounts share 422 invalid_queue_member.
No account discovery or customer lookup is added. Capture If-Match queue version,
email, role and Idempotency-Key together. Check valid precondition syntax and fresh
authority before replay, compare queue version only for a new intent. Save only
immutable queue_id/user_id. Committed replay never regrants or supplies current
metadata. PATCH and DELETE require the reviewed queue version. A missing binding
on PATCH returns 404. Missing precondition 428, malformed 422, stale 409, hidden
queue 404 and readable forbidden write 403 reuse existing error conventions.

## API, persistence and events

- GET /api/v1/ticket-queues/{id}/members returns items, next_cursor, queue_version.
  Verify queue version unchanged around the query. UUID pages bind actor/queue,
  limit 1..100/default50, unique limit/cursor parameters only, no global count.
- POST on that path accepts strict {email,role_name}, If-Match/Idempotency-Key,
  returning minimal {queue_id,user_id}, 201/new intent or 200/committed replay.
- PATCH /api/v1/ticket-queues/{id}/members/{user_id} accepts strict {role_name}.
  DELETE removes its direct grant. Both return 204 and current queue ETag.

Expand the role scope CHECK so exactly one typed parent matches its scope.
Add RESTRICT queue FK and unique partial user_id/queue_id index. No new role name
or runtime table privilege is needed. Worker receives no role binding access.
Event payload has exact actor_id/actor_kind/member_user_id/role_name, where the
role is viewer|agent|operations_manager|removed. Emails, names and client data
never enter event payloads. The strict consumer projects the event once into the
existing ticket_queue activity scope and keeps it outside identity history.

Downgrade locks role_bindings and refuses queue grants or durable access events
before removing the extension. Existing unrelated bindings survive an empty
round trip. Production rollback preserves all expanded data and event support.

## Browser and acceptance

Extend the incumbent Operate design with /service-desk/queues/{id}/members.
Use existing protected-intent and reviewed-version patterns. Add by known email,
freeze exact submitted email/role/version/key for explicit review, then submit.
Uncertain retries preserve the original intent through parent/list failures.
After a receipt, refresh authoritative queue and roster before enabling edits.
Conflicts require explicit reload/review. Removal is confirmed. Explain that
queue access changes end sessions and customer access remains independently
managed. Role labels distinguish the queue manager from configuration authority.

Prove persisted lifecycle, queue-only metadata isolation, no client/configuration
grant, current authorization before replay, inactive/no-op/removal, session
revocation and lock ordering, event atomicity/redaction/strict projection,
concurrency, version overflow, schema constraints and guarded downgrade. Browser
proof includes uncertain committed/uncommitted POST, failed refresh, stale edits,
read-only roles, keyboard/axe, literal text and mobile/desktop light/dark. Use
Impeccable and one fresh whole-increment source review. Run local and hosted
gates. Final target-VM qualification follows remaining MVP development.
