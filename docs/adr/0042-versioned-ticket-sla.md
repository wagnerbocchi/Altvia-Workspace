# ADR-0042 Versioned ticket SLA and business time

Date2026-11-14. Status: selected contract after independent builder check;
implementation is in progress; capability acceptance remains pending.
Master FR-011/012 and8.3, ADR0004/0028/0035 and the current security/API/data-model
contracts apply. Real calendars, targets and holidays remain Q-07. The user
delegated continuous MVP development and implementation choices; this contract
does not select production policy or authorize activation/deployment.

The builder's two important questions are resolved below: retain the existing
durable acceptance clock explicitly, and fail a selected archived configuration
instead of silently falling back. These are implementation calls under the
user's delegated scope, not a claim that real operational policy was supplied.

## Decision and alternatives

Extend the existing modular monolith with scoped immutable calendar/policy
revisions, ticket-owned SLA cycles and an atomic database worker evaluator.
Use installed datetime/zoneinfo/PostgreSQL; no service or dependency is added.
Keep task due dates and ticket SLA independent. A general workflow language,
external timer service and notification subsystem are unnecessary for FR-011.

Freeze policy eligibility at actual ticket creation and explicit reopening in
the same native transaction. Evaluate clocks from immutable native status history
and accepted public-delivery facts. Do not infer timing from delayed broker
arrival order, draft creation or a private note. The worker calculates deadlines,
approaching states and once-only breach events; HTTP reads do not mutate clocks.
This keeps network I/O outside SLA write transactions and preserves old events.

No policy is seeded or enabled by migrations/fixtures outside guarded test DBs.
No matching enabled policy means an explicit unconfigured cycle, not a zero
target, success or invented24x7 calendar. Enabling later has no historical scan.
An existing ticket receives current policy at its next real reopening only.
The configuration interface must explain this future-cycle boundary.

## Scope and selectors

Calendars and policies have immutable(queue_id,client_id) ownership. Configuration
requires an active account, customer ceiling and client operations_manager,
explicit queue operations_manager and queue configuration management. Reuse the
existing native client/queue predicates and identity-before-auth lock protocol;
do not give SLA code authority by calling an automation effect or by adding a
parallel grant model. Extract a shared configuration-scope owner only if actual
callers need it. Platform/team/project metadata authority alone is insufficient.

Configuration list/detail uses that same conjunction. Ticket SLA reads require
ordinary current ticket access, including current customer ceiling and queue role.
The ticket reader sees its cycle's explanatory policy/calendar labels, targets,
timezone and timing, not another customer's policy or configuration authority.
Current access precedes paging/cursor construction and protected receipt disclosure.

Each policy has an immutable optional category and optional ticket priority selector.
Category must belong to the same queue. Exactly one policy identity exists for
each canonical(queue,client,category-or-null,priority-or-null), including disabled
identities. Selection order is explicit and deterministic: category+priority,
category-only, priority-only, default. Same-tier ties are structurally impossible.
Select the most-specific enabled selector before checking current reference
eligibility. An archived category or currently inactive calendar on that selected
policy fails creation/reopening with409 sla_configuration_unavailable. Do not
silently fall back to a broader selector or treat it as unconfigured. A manager
must explicitly disable/revise that policy. Policy/calendar labels and
selector priority are visible during review. Current calendar active state gates
new references; an explicitly selected historical math revision remains usable
after that calendar is reactivated. Its former active flag is historical metadata,
not the current eligibility decision. A missing current revision fails503 rather
than disappearing from selection and silently choosing a broader policy.

Policy revisions contain name1..160, enabled(default false on create), exact
calendar identity/revision, first_response_minutes and resolution_minutes each
1..525600, approach_minutes0..525600 and a unique subset of pending_customer /
pending_third_party pause states. No customer hours or pause default is inferred.
Approach is a display state within the remaining business-time budget, not a new
notification service. Targets are independent; neither is forced to exceed the
other. A captured revision remains authoritative after later edits/disable.
The authorizer is provenance, not a recurring permission token: leaving the
company does not itself disable an enabled business policy for new cycles.
Existing cycles continue after reference archival or authorizer deactivation;
evaluation fulfills a recorded obligation and grants no content access. Current
ticket authorization still governs every read. Archival is not an implicit pause.
Priority/category changes during a cycle do not silently replace its target.

Calendar revisions contain explicit active boolean, name1..160, IANA timezone,
1..28 ordered nonoverlapping weekly windows, each weekday0..6 and
start_minute0..1439/end_minute1..1440 with
start<end, plus at most1000 unique holiday dates with optional plain label1..160.
Cross-midnight availability is expressed as two windows. Reject overlaps and
duplicates; canonical validation coalesces touching windows. A holiday removes all windows
on that local civil date. The UI supplies explicit timezone/window/holiday inputs,
never a preselected claim about Altvia's hours.

Snapshot the selected trusted installed TZif bytes and SHA256 in every immutable
calendar revision, bounded to256KiB, using stdlib zoneinfo.from_file on read.
Only a validated installed IANA name selects bytes; callers cannot upload files,
paths or TZif. This small persisted artifact prevents a tzdata/image upgrade
from changing historical clock math. Calendar labels/bytes cannot be mutated in
place. New policy revisions may deliberately select a newer calendar revision.
Preserve both artifacts in backups and binary rollback.

## Business time and cycle truth

All instants are aware UTC and elapsed values use integer microseconds internally.
Weekly/holiday decisions use the frozen zone's local civil time. Half-open working
intervals include opening and exclude closing. Intersect those intervals with the
requested UTC range; never subtract two local datetimes across DST. Repeated local
minutes count each real occurrence if in the window; missing minutes count none.
Test non-hour shifts, skipped local dates and boundaries within a minute, not only
one-hour US DST. Standard-library UTC traversal/interval coalescing can implement
this without relying on a private zoneinfo transition API. Cache only immutable,
bounded day results, with an explicit memory cap and representative benchmark.

Supported cycle instants are2000-01-01 through2100-01-01 exclusive. No existing
source workbook timestamp is used to backfill SLA. Deadline search is bounded by
that range; an unrepresentable deadline yields calculation_unavailable, never a
fabricated timestamp, false fulfillment or hot retry. Long evaluation must advance
through bounded persisted progress so one old cycle cannot block ordinary work.
Exact algorithm/progress bounds belong to the implementation plan and its native
performance proof before source implementation; they are not a production SLA.

Each actual new ticket starts cycle1. resolved/closed -> open starts the next
cycle; resolved -> closed does not. No-op/replayed transitions create no cycle.
An unconfigured cycle is retained too, so enable/reopen behavior is explainable.
Native manual and approved-mail creation/reopen converge on the same owner.
Cycle policy/calendar references, start time and initial selector are immutable.
Resolving ends a cycle at the exact native history instant; closing retains it.

For each goal, running business time excludes configured paused status intervals
from immutable status history and stops at resolution. Pausing preserves elapsed
time, hides an advancing deadline and records the explicit reason/state already
required by native history. Resuming restores the remaining business budget.
Compute the response clock and resolution clock independently. Response becomes
fulfilled only on the earliest accepted public outbound delivery whose saved
message belongs to that cycle and whose accepted_at lies within it. A previous
cycle's delayed draft/send does not satisfy the new cycle. No draft/queued/failed/
uncertain delivery, incoming message, private note, task update or public draft
posting satisfies this goal. Accepted means accepted by the SMTP server, not
delivered to the recipient. Owner-reconciled acceptance is eligible only with its
validated accepted_at; a reconciliation decision alone is not acceptance.

No response by resolution is reported unfulfilled if still under budget, or
breached when over budget; resolution never invents a response. Exact budget
fulfillment at the deadline is on time. A running unfulfilled goal breaches when
business elapsed exceeds its target; downtime outside working windows is not
elapsed. Once due, the worker records the actual deadline as occurred_at and its
own observed time separately. Later worker execution never moves the deadline.

Late owner acceptance evidence can revise the current derived response outcome;
it cannot erase an observed breach event. Retain an explicit append-only outcome
correction with source evidence reference and recorded_at. Current metrics must
distinguish corrected outcome from historical observed alerts. Status-history
changes never rewrite or delete older cycles. No unreviewed rebaseline/reset API.

Builder-check ruling: use the existing durable OutboundMessage.accepted_at as
the authoritative acceptance instant, preserving ADR0035 and all transport/API
contracts. Ordinary accepted_at is the database finalization time after the SMTP
acceptance; owner-reconciled accepted_at is the explicitly validated external
evidence time. This is deliberately a durable system clock metric, not a claim
to measure the instant a network250 was observed. A slow finalization can affect
timeliness or cycle eligibility; expose that definition in the SLA UI/evidence.
Do not silently backdate an ordinary delivery or introduce a second, inferred
network timestamp. If operations requires wire-observation timing, it requires
a separate explicit transport-evidence contract and new-cycle policy revision.

## Persistence, transactions and worker

Reserve migration31 after b46087000030 for the four configuration tables. Add
cycle/event storage in32 with its actual evaluator, rather than empty scaffolding.
Tables:

- business_calendars: UUID, immutable customer/queue, positive version and UTC
  created/updated, composite unique(id,client_id,queue_id).
- business_calendar_revisions: PK(calendar_id,version), immutable active/name/timezone/
  windows/holidays/TZif/hash and created_at, constrained parent context. Holidays
  are bounded canonical date/label values in this immutable JSONB snapshot.
- sla_policies: UUID, immutable customer/queue/selector, positive version,
  canonical null-aware selector uniqueness and restrictive same-queue category FK.
- sla_policy_revisions: PK(policy_id,version), immutable enabled/name/calendar
  revision/targets/approach/pause fields/authorizer/created_at; same-scope composite
  FKs bind calendar and policy. Revision values select no user/session/grant.
- ticket_sla_states: PK(ticket_id,cycle_number), immutable same-ticket client/queue,
  start/history/policy revision references (or explicit unconfigured), initial
  selector, derived end/response facts, bounded progress, next_check_at, positive
  evaluator version and safe error. FK/checks forbid partial configured snapshots.
- ticket_sla_events: immutable cycle/goal/type/source identity and exact occurrence/
  observation metadata. Unique logical breach(ticket,cycle,goal); separate unique
  correction evidence key. No body, email address, raw exception or account hash.
- ticket_sla_goals: exactly the configured cycle's two fixed response/resolution
  progress records, restrictive cycle FK and unique(ticket,cycle,goal). Native
  scalar columns own elapsed/history/actual and future-deadline continuation,
  avoiding duplicated prefixed columns or mutable opaque JSON. This is private
  evaluator state, not a new configurable goal type or user-facing resource.
- ticket_sla_acceptances: immutable validated same-cycle public acceptance facts,
  bound to the native delivery and source event. Acknowledging an invalid event
  never inserts a fact. This keeps validation separate from a processed receipt
  and avoids reinterpreting malformed acknowledged metadata as proof later.

Storage ruling before migration source: own holidays inside the immutable
calendar revision, like weekly windows. A separate insert-only holiday child
table would still allow appending to an old revision, and enforcing the1000-row
limit would require extra cross-row locking/triggers. One SQL-validated bounded
snapshot preserves atomic immutability without a second write protocol. Holiday
remains a domain value; no independent holiday resource is required. Future
cross-calendar holiday reporting can project these values without copying them.

Indexes own scoped configuration pages and due-cycle evaluation. New FK parents
are restrictive, with same-client/queue composite keys enforced in SQL. Mutable
derived columns are not the source of historical facts; history/delivery evidence
and captured revision remain authoritative. The data-model update must name every
counter/progress invariant and atomic retry boundary before migration source.

Configuration locks identity before authentication, then client/team/queue and
calendar/policy; reviewed writes advance their aggregate and queue version once.
Ticket hooks retain native identity/client/team/queue/ticket order, then SLA cycle.
The evaluator follows that same order; never cycle-before-ticket. Its transaction
contains no network I/O. It uses bounded native DB due work and atomic unique
event/outbox writes; no Redis timer durability claim or new lease is necessary
for a bounded, entirely transactional evaluation. Competing workers must prove
once-only breach/correction and crash/restart behavior. Poison rows retain a safe
failure state and do not starve the next cycle.

The existing worker gets only exact configuration/history/public-acceptance
metadata reads and derived SLA/event writes needed by executed owners. It gains
no note/message/raw/file body, password, permission mutation or ticket-state
writer. Prefer a narrow derived acceptance view to exposing public message bodies.
API gets configuration writes, initial cycle INSERT and scoped state/event reads;
it does not impersonate worker completion. Preserve every old manual/schema1
envelope and protected intent fingerprint. New SLA events have their own validated
allowlist and native ticket authorization before activity pagination. Metadata
configuration events remain private, not identity activity.

Downgrade refuses any SLA snapshot, revision, historical event or protected receipt
before DDL. Binary rollback retains expanded schema/history and drains the newer
writer; do not contract populated tables or claim old binaries maintain new cycles.
Integrated rollback must prove that limitation explicitly.

## HTTP and frontend boundary

Use existing authenticated transport, strict typed models, generated OpenAPI/TS,
exact Origin/CSRF, reviewed versions and durable protected intents:

- GET/POST /ticket-queues/{queue_id}/business-calendars; required unique client_id
  on GET. POST uses queue If-Match and Idempotency-Key;201/minimal receipt,200 replay.
- GET/PATCH detail under that collection. PATCH retains immutable scope, creates
  an immutable complete revision and requires calendar If-Match,If-Match-Queue
  and Idempotency-Key. A no-op records its intent without an extra revision.
- Equivalent scoped sla-policies collection/detail, fixed disabled creation and
  explicit reviewed enable/edit/disable. Immutable selector changes require a
  distinct identity, never reinterpret an existing policy's history.
- GET /tickets/{ticket_id}/sla: server evaluated_at, current cycle and paged
  preserved cycle outcomes. Never expose another scope, total, raw evidence or
  claim current clocks when evaluation is stale/failed. Exact DTO/paging fields
  and safe codes are selected in the implementation plan before source.

All lists limit1..100/default50 with actor/parent/client-bound cursor and unique
known queries. Hidden404, readable forbidden403, missing precondition428,
invalid422 and stale409 follow incumbent owners. Read/current authority precedes
even committed replay. Original versions/body/key survive uncertain writes.
Acknowledged writes retry reads without resending. Archiving blocks new policy
effects/configuration edits while preserving authorized reads, disable and replay.

Impeccable extends the existing Twenty-inspired Operate queue/ticket screens.
Explain future cycles, selector order, frozen calendar revision, paused/stale/
unconfigured/unavailable and corrected outcomes. No invented countdown or target.
Preserve keyboard/focus, both themes and390/1440 layouts with actual browser proof.

## Acceptance before capability completion

Prove native migration/FKs/grants/refusal, full conjunction and protected replay,
calendar timezone/DST/holiday/window exactness, pauses, first acceptance rather
than draft/queue/private note, resolution and repeated reopen, priority/revision
immutability, late evidence corrections, concurrent workers, poison isolation,
current ticket privacy before page/cursor and API/worker credential boundaries.
Benchmark representative shared and distinct calendars, long cycles and hostile
bounds with actual DB/runtime. Export stable contracts and preserve old ones.
Run real HTTPS/API/PG/Redis browser configuration/outcomes, packaged restart and
once-only breach/correction. Finish with an independent whole-increment review,
all five exact-source hosted gates and retained private evidence. Final integrated
x86-64-v1 qualification remains after the MVP; this document establishes no pass.
