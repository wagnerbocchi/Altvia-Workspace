# ADR-0039: Explicit same-client ticket/work links

Date2026-11-13. Selected engineering contract after independent builder review;
nothing Important remains before the schema task. This is not runtime proof.
Native schema, protected API and browser panels are implemented and independently
reviewed; packaged relationship proof remains pending. See the feature evidence
page for exact source/checks/limits. The complete master specification was read.
ADR0007/0020/0021/0028 and current customer/queue/project/session policy remain
binding. The user authorizes continuous development and finite engineering
choices, local commits and direct main publication without PR. This contract
adds no production, real-import, retention deletion or target authority.


Scope: one complete manual relationship increment. Incoming-file development is
accepted at62dbeeb with closure6dd5eb2. Current migration head isb46087000027;
this contract reserves ADR0039 and the next migrationb46087000028.

### Decision and authority

Persist explicit relationships between existing customer tickets and existing
work items. A link grants no read/write scope, account membership, note permission,
file access, sender verification or delivery authority. No implicit create-work
mode in this endpoint. Both directions list real links, and unlink deletes only
the relationship. No state, assignee, priority, due date, completion timestamp,
SLA field, message or participant is copied or synchronized.

Read a relationship only if both current endpoints are readable. Reuse
`tickets.visible(actor)` and `project_registry.visible_projects(actor)` SQL
predicates. Internal-project tasks cannot link to customer tickets. Same client
is mandatory, not a configurable policy or an inferred client mapping.

For link/unlink, require existing `tickets.require_update` AND
`work_items.require_update`. Thus a queue operations_manager or current assigned
queue agent must independently be work manager or contributing owner/assignee.
Project membership/contribution alone is insufficient to edit any arbitrary task.
Viewer, platform/configuration administrator, team manager, historical assignee
and an external participant label grant no additional relationship authority.
These are explicit engineering mappings of the existing abstract ticket.link /
work.link actions, not new broad roles. No session invalidation is caused by a link
because authority does not change; all existing revocation still applies.

For new effects use both existing active checks; a closed ticket must be reopened
through its ordinary policy before linking or unlinking. Task terminal state does
not independently prohibit a relationship: existing work content writes do not
impose that restriction. Authorized read, coherent no-op and committed receipt
replay survive archive/closure, following ticket conventions. Current permission
always precedes saved receipt disclosure. No new archive-cleanup exception.

### SQL model and same-client proof

New table `ticket_work_items`, modeled near Ticket/WorkItem:

- PK (ticket_id, work_item_id).
- Non-null ticket_id, work_item_id, client_id, queue_id, project_id.
- relation_type fixed to `related` by CHECK (no invented hierarchy/type taxonomy).
- created_by non-null FK users(id), created_at timestamptz; values server-owned.
- FK (ticket_id,client_id,queue_id) -> tickets(id,client_id,queue_id).
- FK (work_item_id,project_id) -> work_items(id,project_id).
- FK (project_id,client_id) -> projects(id,client_id).
- All FKs restrictive, no update/delete cascade. Existing unique parent keys are
  reused, so no denormalized customer column on WorkItem or new ticket unique key.
- Reverse index (work_item_id,ticket_id); pair PK serves ticket-side UUID paging.
- API SELECT/INSERT/DELETE only on this table; no UPDATE and no worker grants.

All identity columns are NOT NULL. The project FK cannot bypass comparison via
NULL, and an internal project has no matching non-null project/client tuple.
A forged work/project pair, ticket/customer/queue tuple or mismatched customer
fails in PostgreSQL on INSERT and UPDATE. Parent identity changes while linked
are restricted by native referential integrity. Do not use an application-only
comparison, cross-table CHECK, ownership trigger or duplicated customer truth.
A raw DELETE still only removes a link. Application version/audit protocols are
not claimed as owner-superuser enforcement; this follows existing domain patterns.

The new migration follows b46087000027 on the accepted source. Update ORM metadata and provision allowlists together. No dependency or new
service, index engine, storage object, binary or native ISA requirement.

### One lock protocol and two reviewed aggregates

All write entry points use the same canonical direction, including work-side UI:

1. Exact Origin check, identity advisory lock 723504391, authenticate and lock
   session, CSRF check through authenticate_request(write=True).
2. Resolve BOTH readable endpoint scopes without effects; hide absent/foreign
   IDs with 404 before action checks. Require current update authority on both.
3. `tickets.scoped_ticket(...,write=True)` locks customer, queue team, queue,
   ticket in incumbent order. No other queue/project domain is mutated.
4. `work_items.scoped_work(...,write=True)` takes the project's work-graph
   advisory lock, then the work row. Never lock that work row before graph lock.
5. Re-evaluate both current action predicates using refreshed locked rows, and
   same-client equality. Load/delete/insert the natural-key link only after them.

Project/team/customer archive and role writes are already serialized by the
identity lock; work.active flags must be read fresh, not retained from an earlier
request. Do not add a second lock convention or broaden parent locks casually.
A future worker/owner automation writer must explicitly adopt this protocol or
receive a reviewed compatible ordering before reuse. Current owner tools that
write work rows outside it are not automatically made concurrency-safe by this
proposal. No account target lock is needed for a relationship. Existing logout
and FOR NO KEY UPDATE account conventions remain intact.

A real insert/delete advances BOTH ticket and task versions once using existing
advance helpers, then writes both events and a protected receipt atomically.
No-op leaves both versions/timestamps/events unchanged. Overflow of either,
constraint failure or event/receipt failure rolls back every change. Both versions
are reviewed to prevent stale work-side intents even when ticket version is fresh.
No new relationship aggregate version or tombstone table is necessary.

### Concrete HTTP contract and replay resolution

All below are `/api/v1`, strict typed schemas and existing origin/CSRF/session rules.

| Route | Selected request and result |
| --- | --- |
| GET /tickets/{id}/work-items | Parent-authorized page of readable linked work summaries; items,next_cursor; fresh parent capability independent of page |
| GET /work-items/{id}/tickets | Parent-authorized page of readable linked ticket summaries; same paging semantics |
| GET /tickets/{id}/work-item-choices | Requires current ticket update authority; bounded eligible same-client work summaries across the full authorized project set, before paging |
| POST /tickets/{id}/work-items | Strict {work_item_id}; If-Match (ticket), If-Match-Work-Item (task), Idempotency-Key; 201 inserted, 200 existing/replay; minimal {ticket_id,work_item_id} |
| DELETE /tickets/{id}/work-items/{work_id} | No JSON body; same two version headers plus Idempotency-Key; 204 deleted/already absent/committed replay; internal minimal pair receipt |

`If-Match-Work-Item` is an explicit extension, same quoted positive-int
syntax/range as If-Match. Do not silently reinterpret If-Match as task version on
work-side UI. Add a narrowly parameterized parser or local parser without changing
legacy missing/malformed header errors. OpenAPI documents both preconditions.

This preserves the documented POST and DELETE paths. The future POST wording
`work.link/create` narrows to link-existing in this increment; task creation stays
at its existing endpoint. DELETE remains 204, but receives protected replay because
a delayed retry must not unlink a later relink. No POST /unlink alias is required.

Parse both header syntaxes before receipt lookup. New route namespaces distinguish
link vs unlink and include canonical ticket identity (unlink also work identity).
Fingerprint body + canonical IDs + BOTH original reviewed versions; exclude key
and CSRF. Do not modify legacy POST fingerprints. `_operation` is method-agnostic
and can store DELETE intent using the existing IdempotencyRecord table; `_remember`
can store its minimal pair result with status204 although no response body is sent.

Order: fresh auth and both action scopes, parse headers, lookup protected intent,
matching saved receipt return with no state/version/active-state reapplication.
Only a new intent compares both current versions, then checks presence. Existing
POST or absent DELETE with matching reviewed versions records a no-op receipt;
otherwise an actual effect must pass active/closed checks. Mismatched key/body or
original version is 409. Missing required header428, malformed422, stale409,
readable-but-forbidden403, hidden/absent404; same-client mismatch409 with a bounded
code and no foreign labels. SQL rejects the same invariant independently.

Receipt replay confirms historical commitment, not current existence. Example:
link A, unlink B, retry A -> original pair receipt, no recreated link; unlink B,
relink C, retry B ->204, C remains. After receipt retention expires, old version
preconditions still prevent stale recreation/removal; versions never decrement.
Refresh both endpoint detail and link collections after acknowledgment. Do not
return a stale historical ETag as a claim about current aggregate versions.

### Lists, choices and metadata privacy

Use current SQL authorization before search, LIMIT+1, cursor emission and any
optional capability. UUID ascending by counterpart ID, default50/max100, no total
count. Bind cursors to actor, parent, direction and normalized filters, preserving
legacy collections unchanged. Reject repeated/unsupported query keys. Do not load
one authorized-project page and filter work in Python. Choice filters: optional
project_id and bounded existing work q semantics; parameterized native FTS only.
Candidate query includes same customer, current work-update eligibility and active
project/team/customer; excludes already linked visible candidates. Inactive/closed
ticket has can_link=false and no actionable candidates. Selection still requires
fresh detail/version review before a write; choices never establish a grant.

Summaries expose only counterpart ID, authorized title/subject, native state,
priority, version and authorized navigation context (work project ID/name or
string ticket number). No requester email, note metadata, comments, descriptions,
attachment counts, account directory, raw mail data or hidden-link counts.
Fresh can_unlink is the intersection of BOTH current update permissions and
new-effect eligibility, not inferred from a page or persisted assignment. Do not
return IDs or placeholder badges for hidden counterparts. No summary propagates
private-note/file permission. Opening the detail/download rechecks its own ACL.

### Reciprocal events and history privacy

One effect produces TWO distinct strict events: ticket.work_linked/unlinked under
ticket aggregate and work_item.ticket_linked/unlinked under work aggregate.
Use the same operation time/correlation and each parent's newly advanced version.
Separate event UUIDs fit the existing one-event/one-resource projection and
ProcessedEvent idempotency; do not change ActivityEvent PK or synthesize dual rows
from one event. Both audit/outbox records are in the same mutation transaction.

Dedicated exact-field payload models contain actor_id/kind, ticket_id,
work_item_id,client_id,queue_id,project_id and fixed relation_type. Validate event
family, own aggregate ID/type/version, UUIDs and fixed relation_type. No subject,
title, descriptions, reasons, names, contact data or body. Do not weaken existing
TicketEventPayload/WorkEventPayload allowed-field sets or change old envelopes.
No generic updated/assigned event is emitted, so this increment triggers no work
creation, notification, assignment, state or delivery behavior.

The current generic activity_page is not a sufficient authorization boundary:
callers must add a SQL predicate before it. For each new link event, require a
currently readable counterpart with matching ticket/work/customer context before
selecting the row. Correlate IDs in validated JSON details using safe string UUID
comparisons or guarded casts; malformed data must not become a query error/oracle.
Suppress the ENTIRE event when counterpart is hidden, including its ID, timestamp,
actor, correlation, counterpart identifiers and cursor contribution. Preserve
existing note filtering and all ordinary events. Never post-filter a page.

History authorization uses current endpoint rows, NOT an existing link: legitimate
unlink history and old linked events remain visible to an actor who can still
read both endpoints. A revocation hides them on subsequent reads even after
projection. Current same-client/context equality also fails closed if future
scope transfer changes the relation of historical endpoints. No names need to be
resolved from event payload. Identity/client/project feeds remain scoped as today.

### Browser increment and rollback

Future implementation must run Impeccable context workflow before frontend work.
Use the current Twenty-inspired Operate details, no redesign. Ticket detail gets
linked work and paged selection/review; work detail gets reciprocal tickets and
unlink review with navigation to ticket detail for adding links. This avoids a
second mutation route/picker policy. Native accessible controls, separate domain
status labels, plain text, loading/empty/failure/read-only/inactive states, keyboard
focus, mobile and both themes are required.

Reuse useTeamWrite/WriteRecovery and session-owned queries; retain original IDs,
both versions, operation and key through uncertain POST/DELETE responses and failed
refreshes. Extend only relationship transport for the second header. Fresh typed
DTOs come from OpenAPI -> api.generated.ts. Explicit conflict review/reload may
replace an intent; ordinary list paging or a failed refresh may not. Discard all
local intent/cached customer data on session replacement. After acknowledgment
keep writes disabled until both authoritative versions and relationship lists
refresh; failed refresh exposes retry, not optimistic success/current-state claims.
Invalidate both parents' detail/activity and link collections. No My Work changes.

Application rollback must retain expanded schema and a worker that understands
new event families; an older consumer would dead-letter them. A pre-link API is
also unsafe after projection because its existing activity endpoints expose any
parent event without counterpart filtering. Retain a compatibility API with the
new event privacy predicate (writes may be disabled), not an arbitrary old image.
Do not purge events/receipts to permit rollback. Downgrade acquires locks and refuses
if any link OR link event/audit/activity history OR protected link/unlink receipt
exists, including after every relationship has been deleted. Empty migration
roundtrip preserves all preexisting keys, mail/file records and privileges. Do not
drop parent composite keys owned by earlier migrations. Final target qualification
remains consolidated after development; no VM operation belongs in this increment.

## Execution and acceptance

Execute docs/plans/2026-11-13-ticket-work-links.md after the recorded builder
check and controller preflight. Contracts precede source. Five review-focus
cases pin replay after relink, privacy before pagination, native same-client
constraints, concurrent authority/lifecycle and acknowledged paired-read recovery.
No automation, task creation or unified My Work is implemented here. ADR0007
retains full-set deduplication for its later increment.

Feature acceptance requires real PostgreSQL/API/browser and packaged recreation
with current ACL, source/visual reviews and exact-source hosted/security gates.
Minimum compatible API and worker sources must retain link-history privacy and
new event readers. Actual compatible-image rollback rehearsal and encrypted
backup remain required consolidated integrated-hardening gates. Recreation is
not image rollback. Final actual x86-64-v1 qualification follows remaining MVP.
Unknown provider, mappings, retention and SLA policy remain registered; no new
organizational answer is needed for this bounded engineering increment.
