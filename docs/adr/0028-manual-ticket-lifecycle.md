# ADR-0028 Manual ticket lifecycle and customer boundary

Date 2026-11-10. Selected before implementation for Phase 3C, FR-005/012.
The master specification, ADR-0004/0022/0026/0027 and current user authorization apply.

## Decision and alternatives

Implement a complete manual ticket path in the existing modular monolith using
the explicit queue bindings established in Phase 3B. A ticket belongs to one
immutable customer and queue in this increment. It references a same-customer
requester, an optional same-queue category and an optional internal assignee.
Managers may replace the requester within that customer. Transfers/customer
reclassification require a subsequent contract revalidating both boundaries.
Messages, files, transport, SLA, linked work and automation remain later slices.

Extend existing typed HTTP, session, version, receipt and outbox patterns. Keep
ticket rows/history in their owning module. Reusing work_items as ticket state
would conflate independent lifecycles. Requiring a general client role for every
support agent would distort the explicit queue-plus-customer policy. Ticket-only
reference pickers therefore expose the minimum necessary scoped references.

## Authority and reference access

Every ticket list, detail, history, activity and mutation requires both an
explicit client_access_grant ceiling and viewer|agent|operations_manager in its
queue. Platform administration, team/configuration roles, project membership,
requester identity and historical assignment alone confer no ticket content.
SQL applies these predicates before filtering/pagination. Hidden and absent
resources share404. Readable forbidden actions return403.

Queue viewer reads. Queue agent creates, reads and explicitly claims an unassigned
ticket for self. Agents change subject/description/priority/category and transition
only their current assignments. Queue operations_manager additionally delegates
assignment, replaces the requester and manages any permitted ticket in that queue
and customer ceiling. Submitted assignment/requester PATCH fields require manager
authority even for no-op values. Agent create permits unassigned or explicit self
only. Assignments retain historical references after access/account revocation.
New assignments require active account, queue agent/manager and that customer's
ceiling. No team roster or client role is substituted for that eligibility.

Ticket creation/reference routes first require the explicit queue writer role.
Their customer choices expose only ceiling-bound active customer ID/name. Their
requester choices expose only active same-customer contact ID/name/email and its
unverified state. Manager-only assignment choices expose eligible account ID/name.
These purpose-bound lookups confer no general client/contact/account directory
access. Ticket reads may resolve only their persisted requester/category/assignee
labels, including archived historical references. Contacts remain unverified and
the manual flow supplies no communication or identity-verification effect.

## Fields, lifecycle and queue policy

Persist UUID, unique positive BIGINT identity number, client_id, requester_id,
queue_id, nullable category_id/assignee_id, stripped single-line subject1..300,
plain description0..20000, priority low|medium|high|critical, source manual, status,
resolved_at/closed_at, positive version and UTC created_at/updated_at. Server owns
number/source/status/timestamps/version. HTTP represents number as a decimal string
to preserve the full BIGINT range in JavaScript. Reject NUL in free text. SQL
checks include Unicode-whitespace-only subjects, enums and state/time consistency.
Composite FKs enforce requester/customer and category/queue. Referenced rows use
RESTRICT. API receives SELECT/INSERT/UPDATE on tickets and SELECT/INSERT on immutable
ticket_status_history. Worker consumes outbox without ticket/reference table grants.

Graph follows the master contract. new -> open. open -> pending_customer,
pending_third_party or resolved. Either pending -> open or resolved. resolved ->
closed or open. closed -> open. Entering a pending/resolved state and reopening
requires stripped nonblank reason1..2000. Initial creation records null -> new.
Same-state authorized requests are no-ops. Real transitions append immutable
actor/from/to/reason/version/time history. Resolving sets current resolved_at,
closing preserves it and sets closed_at, reopening clears both current timestamps.
Historical cycles survive in the immutable history for later SLA integration.

Add fixed booleans allow_manual_close and allow_reopen to queue configuration,
both default false for existing/new queues. Existing configuration managers change
them using reviewed Queue If-Match and redacted queue.updated changed fields.
Resolved closure requires queue operations_manager and allow_manual_close.
Resolved reopen requires manager or assigned agent and allow_reopen. Closed reopen
requires manager and allow_reopen. Current policy is rechecked for new effects.
Manual flags define no automatic timer, grace period or SLA promise. Actual
business policy stays Q-07/Q-19. Closed tickets require reopening for actual edits
or new assignment. Active customer/queue/team is required for every real ticket
mutation. Authorized reads, coherent no-ops and committed receipt replay survive
archive. Only new linked references require active requester/category/candidate.

## Transactions and HTTP

Identity advisory lock precedes authentication/CSRF. Then lock customer, owning
team, queue, ticket and new linked references in that order. Target-user locks use
the incumbent FOR NO KEY UPDATE pattern, permitting concurrent logout audit FKs.
Recheck current content authority before replay. Preserve existing account/role
administration lock/session protocol. Ticket updates never grant permissions.

- GET/POST /api/v1/tickets list/create. Strict create accepts client_id, queue_id,
  requester_id, subject, priority and optional description/category_id/assignee_id.
  Protected create returns minimal {ticket_id}, 201/new or200/committed replay.
- GET/PATCH /tickets/{id} return current typed data/capabilities and ETag. Strict
  nonempty PATCH accepts subject, description, priority, category_id, assignee_id,
  requester_id. Explicit null clears category/assignee only. Status is a dedicated
  transition. Client/queue/number/source/version are forbidden input.
- POST /tickets/{id}/claim accepts strict empty object, reviewed If-Match and
  Idempotency-Key. Current queue writer authority precedes replay. New effects
  compare version, require unassigned or existing self, and persist self assignment.
  Assignment to another account conflicts. Return200 minimal {ticket_id}.
- POST /tickets/{id}/transitions accepts {target_status,reason?}, reviewed If-Match
  and Idempotency-Key, returning200 minimal {ticket_id,history_id nullable}.
  Parse precondition and current action authority before replay. A saved receipt
  never repeats history, state, assignment or timestamps. Fresh requests alone
  compare version and apply current active/policy/state eligibility.
- GET /tickets/{id}/status-history reads immutable descending version history.
  GET /tickets/{id}/activity reuses the redacted activity projection.
- GET /ticket-choices/queues returns explicit queue-role choices and independently
  computed can_create. GET /ticket-choices/{queue_id}/clients and nested
  /clients/{client_id}/requesters or /assignees provide the bounded references above.

Lists use unique query parameters, limit1..100/default50 and actor/filter/resource
bound cursors. Ticket inbox sorts created_at/id descending. Filters are queue_id,
client_id, status, priority, assignee_id, unassigned and stripped q<=200, ANDed.
Reject assignee_id combined with unassigned. Native Portuguese PostgreSQL FTS
indexes subject/description with GIN and bound websearch input. Creation authority
is computed independently of filter/page contents. No global totals are returned.

Missing protocol header428, malformed/body/query422, stale version409 and invalid
transition/policy/active state409 reuse current errors. Ineligible assignment or
requester/category input returns bounded422 without foreign names. Version
exhaustion or event failure rolls back all effects. Durable events use aggregate
ticket and strict ticket.created/updated/assigned/status_changed models. Payloads
carry actor/ticket/customer/queue IDs, allowlisted changed fields and transition
or assignment IDs only. Assigned events contain explicit nullable old assignee
and non-null new assignee, including initially assigned creation. Clearing an
assignment is ticket.updated. Reasons, subjects, descriptions and emails stay out
of logs/audit/outbox/activity. Ticket events stay outside other aggregate feeds.

## Browser, migration and acceptance

Use Impeccable and incumbent Operate context at /service-desk/tickets, /new and
/{id}. Provide persisted inbox/filter/search, independently paged reference choices,
reviewed create, ticket editing, assignment/claim, explicit transitions, history
and queue workflow configuration. Preserve original POST intent through uncertain
responses and all read failures. After minimal receipts, refresh authoritative
ticket data before permitting another edit. Reviewed conflicts require explicit
reload/review. Render plain text, accessible native controls, loading/empty/error/
success/read-only/inactive states and desktop/mobile light/dark without inert UI.

Migration b46087000015 expands queues, composite reference keys, tickets/history
and activity scope. Downgrade locks affected tables and refuses ticket data/events
or configured workflow/history before contraction. Empty round trips retain all
previous queues/grants. Application rollback preserves the expanded schema and
compatible worker. No new dependency or ISA requirement is introduced.

Prove real PostgreSQL/API lifecycle, all scope/linked negatives, assigned-agent
limits, independent choices, replay after change/revocation/archive, immutable
history, SQL constraints, BIGINT precision, atomicity, races, overflow, FTS and
runtime privileges. Browser proof includes actual persistence and recovery,
keyboard/axe/overflow, roles and theme/viewport captures. Complete one fresh source
review, Impeccable finish/documentation and all five hosted gates. Consolidated
target qualification follows remaining MVP development under current cadence.
