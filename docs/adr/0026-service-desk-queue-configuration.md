# ADR-0026 Service Desk queue and category configuration

Date 2026-11-10. Selected before code for Phase 3A, FR-005 configuration and FR-012.
The master specification and the user's standing development authorization apply.

## Decision

Add persisted ticket_queues and queue-owned ticket_categories in the existing
modular monolith. A queue belongs to one immutable team. Routing across customers
will happen at ticket level with the explicit customer ceiling. Categories belong
to one immutable queue. Each record has UUID, name, active, integer version and UTC
created_at/updated_at. Archive and restore preserve references and history.

Queue configuration is operational metadata. Global platform administrators may
configure it. Explicit operations_manager team bindings manage that team's queues
and categories. Explicit viewer team bindings read their configuration. Team
roster membership alone supplies no authority. Existing client/project bindings
do not authorize this metadata. All collection authorization precedes pagination.
Future customer ticket content will additionally require its own queue permission
and customer ceiling. Configuration authority never supplies those content grants.

This is the first independently usable slice of Phase 3. Ticket lifecycle,
requesters, messages, attachments, queue content-role administration and mail
transport follow as separately contracted slices. Their tables are created when
their behavior is implemented. Existing contact and project policies remain the
boundary for later linked references.

## Alternatives and tradeoffs

The selected team-owned queue supports one operational inbox across customers.
Binding each queue to a customer would duplicate routing configuration for teams
serving multiple customers. Global unrestricted metadata would disclose other
teams' configuration. Explicit queue-role administration will own future ticket
content grants, while this slice reuses existing team configuration scope.
The cost is that configuring a queue alone does not make it usable for ticket
content until that subsequent authorization contract is implemented.

## Schema and write invariants

Names are Python-stripped Unicode strings of 1..150 code points. Reject embedded
NUL, CR and LF. Enforce nonblank single-line names and positive versions in SQL.
Exact case-sensitive names are unique within team for queues and within queue
for categories, including archived records. Use UUID in navigation and receipts.
FKs use RESTRICT. Queue team and category queue are immutable in HTTP contracts.

Reuse authenticate_request(write=True), taking the identity lock before session
authentication. Then lock the owning team, queue and category in that order.
Recheck present authority before replay. Active parent references are required
for new records and actual edits. Reads, coherent no-ops and committed creation
receipt replay remain possible after archive. A queue can itself be renamed,
archived or restored if its team is active. Category edits require active queue
and team. Queue archive preserves category active flags for deliberate restoration.

Protected POST uses the incumbent actor/route/key and canonical request hash.
Save only immutable ID receipts. Same-key different intent conflicts. PATCH
requires the record's reviewed If-Match and returns ETag. Real edits advance
exactly once. No-ops keep version/history. Version exhaustion rolls back all
effects. Category changes also advance the owning queue's aggregate version so
its ordered history and concurrent queue edits remain coherent.

## API and events

- GET/POST /api/v1/ticket-queues lists or creates configuration.
- GET/PATCH /api/v1/ticket-queues/{queue_id} reads or changes queue metadata.
- GET /api/v1/ticket-queues/{queue_id}/activity reads queue-scoped history.
- GET/POST /api/v1/ticket-queues/{queue_id}/categories operates its category list.
- GET/PATCH /api/v1/ticket-queues/{queue_id}/categories/{category_id} operates one
  correctly parented category.
- GET /api/v1/ticket-queue-teams supplies independently paged readable team
  metadata and can_manage for creation selection. It exposes no roster.

Pages use existing bound cursor helpers, limit 1..100/default 50, unique query
parameters and current actor/resource scope. List failures never discard a
protected creation's original intent. Queue responses contain team_id/team_name,
team_active and can_manage. Team selection is explicit on creation. Lists and
detail are read-only for viewers, including an archived-reference explanation.

Atomic audit/outbox use aggregate ticket_queue and event types
ticket_queue.created/updated/category_created/category_updated. Payloads contain
actor ID/kind and optional category_id/allowlisted changed_fields only. The worker
validates the exact event-specific shape and projects deduplicated activity.
Names and free text never enter events. Queue events stay out of identity history.
The API gets SELECT/INSERT/UPDATE on both metadata tables. The worker gets no
table access and consumes only the existing outbox interface.

## Browser and proof

Use Impeccable to extend the established Operate world at /service-desk/queues and
/service-desk/queues/{id}. Provide real list/create/detail/rename/archive/restore,
category lifecycle and history, with session-owned transport/cache. Reuse current
protected-intent, conflict-recovery, paging and activity primitives. Verify real
SQL lifecycle, scope/roster/client negatives, replay/revocation/archive, constraints,
atomic rollback, races, overflow, least privilege and strict event projection.
Browser proof covers keyboard, literal text, persisted reload, roles, stale and
uncertain recovery, desktop/mobile light/dark, axe and overflow. Retain failed and
passing evidence, one whole-increment source review and Impeccable finish proof.
Run local and all five hosted gates. Consolidated target qualification follows
remaining MVP development under the user's current cadence.

## Rollback

Migration b46087000013 is expand-only. Downgrade locks queue/category tables and
refuses durable rows or ticket_queue audit/outbox/activity. Preserve expanded
data and a worker that validates the new events during application rollback.
Production mailbox/provider selection stays Q-03/Q-16. No transport is exercised
by configuring metadata.
