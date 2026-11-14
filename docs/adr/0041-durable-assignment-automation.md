# ADR-0041: Durable structured assignment automation

Date2026-11-14. Selected engineering contract after independent builder check;
both important contract questions are resolved below. No automation implementation or passing gate is
claimed. Master specification4.2/8.1, ADR0004/0017/0020/0022/0028/0039/0040 and
the current API/security contracts were traced before this decision. The user
delegated implementation choices and continuous development; production rules,
real import, retention deletion and production deployment remain unauthorized.

## Decision and alternatives

Add one disabled-by-default structured ticket.assigned/create_or_link rule per
immutable (queue_id,client_id). A rule owns one immutable server-generated action
UUID for its lifetime. Disable/edit preserves both identities; there is no delete,
replacement-action or arbitrary new-work endpoint in this increment. This is the
smallest useful configurable action; a script editor, generic condition language,
rule graph, notification service and new dependency are unnecessary.

Stage an execution row in the SAME transaction as the actual assignment outbox
event. A separate durable worker consumer owns its execution/lease/effect receipt.
The existing activity consumer acknowledges projection only; attaching a writer
after that receipt could lose work. Scanning delivered events with time watermarks
adds late-commit/revision ambiguity. A privileged enqueue trigger would support
pre-feature producers at the cost of a second privileged owner; these producers
are outside the explicitly defined automation compatibility floor below.

Extend the responsible native assignment event owner, not the generic activity
projector. All current producers converge on ticket_api._assigned: manual create,
patch, claim and native mail create via create_record. identity.record_event may
return its actual OutboxEvent; existing callers ignore the return. Preserve every
manual schema1 envelope, POST fingerprint, transition receipt and zero-rule path.
No historical event scan or backfill occurs when enabling a rule.

## Finite rule and authorization

Rule configuration requires ALL of: current active account; queue configuration
management under ADR0026; explicit queue operations_manager; explicit client
operations_manager AND its customer ceiling. Platform administration, team roster,
queue membership or project membership alone never suffices. This deliberately
narrow first mapping implements the security matrix's scoped operations authority.
Configuration reads use the same conjunction; no customer names/IDs/configuration
are disclosed through queue administration alone.

Strict revision fields: enabled boolean (create fixed false), static title using
native WorkCreate Title1..300, native work priority, and nonempty unique native
ticket_statuses drawn from new/open/pending_customer/pending_third_party/resolved.
No closed state, expression, script, raw SQL, template, URL or external action.
The complete action is visible for review; client default project and current
ticket assignee are its only resolvers. Explicit task priority is configuration,
not an ongoing mirror of ticket priority. Title is plain text; do not copy ticket
subject/description/private notes into work content with a different audience.
No due/SLA, participant, requester or grant is copied. Defaults are disabled, not
a claim that any real title/status/priority policy has been approved.

Each real edit creates an immutable numbered revision and records the actual
configuring account as its authorizer. No-op preserves version/revision/events.
Enabling and editing an enabled rule are explicit protected mutations. Active
queue/team/client required for create or real enabling/action edits; disabling
remains available after archive with current authority. No session or CSRF token
is stored for execution. Worker rechecks current active authorizer and the whole
configuration/content conjunction before any new effect, plus native project
management and current active same-client project/team/client eligibility.

## Resolution and singular effect

Source identity is the actual immutable schema1 ticket.assigned event, not broker
payload. Validate event type/schema/aggregate/context/assignee; its canonical
ticket/client/queue must match native state. Execution snapshots the exact enabled
rule revision under the same identity/queue serialization as the assignment.
Disabling durably fences old new effects even for an older enabled revision. A
monotone rule.cancelled_through_version starts0; every real disable sets it to
the newly committed disabled revision. No later enable/edit reduces it. Execution
with captured rule_version <= that floor must finish cancelled without effect,
including a previously claimed unexpired token delivered after off/on. No scan or
bulk cancellation is required inside the bounded config transaction. Until a
consumer reconciles it, persisted execution state may still be pending/processing;
the rule's cancellation floor is authoritative and the UI explains that boundary.
Effects committed before disable remain historical receipts and are never undone. An
ordinary action edit does not reinterpret staged executions: their immutable
revision remains authoritative, with current authorization/active-state checks.

Before creating anything, compare source new_assignee_id with the current ticket
assignee; a different or missing assignee makes this execution superseded. Check
current ticket status against the captured revision and native closed policy.
Resolve the client's CURRENT default project at effect time; missing/inactive/
foreign/inaccessible project, inactive/ineligible assignee or lost authorizer
authority produces durable private triage with a fixed safe code and no mutation.
The native contributor predicate includes active direct agent/project_manager
membership OR client operations_manager, always within the customer ceiling.

The stable business key is exactly ADR0004's (rule_id,action_id,ticket_id), never
event_id, revision, array position or assignee. Its immutable effect maps to one
work/project. Once committed, every subsequent matching assignment/reopen/retry
observes that receipt without changing ownership, status, priority, due, link or
history. In particular, a manual unlink is never undone and a changed default
project never creates a second task. No automatic ownership transfer occurs even
for todo work; historical executors remain native history.

For a first effect, inspect live manual links in the selected default project.
Exactly one readable, native-update-eligible link is adopted without modifying
work or ticket. Any other existing link in that project, including one the
authorizer cannot use, yields generic existing_work_needs_review rather than
creating another task or revealing hidden candidates. Multiple candidates are
triage; never choose an arbitrary first. Links in other projects remain separate.
With no link in that project, create a one_off/todo task owned by the current
eligible assignee with configured title/priority, empty description and no due,
then insert the native related link. Work creation, link/version/history, effect,
execution result and audit/outbox commit atomically. No project/account/grant is
created; ticket and work lifecycles remain independent.

## SQL model and migration boundary

Reserve migration b46087000029 after manual links b46087000028. Add four tables:

- automation_rules: UUID id; immutable client_id/queue_id/action_id; positive
  version; cancelled_through_version0..version; created/updated UTC. Disable floor
  and version never decrease under the native write owner. Unique(queue_id,client_id), including disabled
  records, and unique(id,action_id,client_id,queue_id). No physical-delete API.
- automation_rule_revisions: PK(rule_id,version); restrictive parent FK;
  immutable enabled/title/priority/ticket_statuses/authorizer_id/created_at.
  SQL enforces title/native enums/nonempty unique bounded statuses and positive
  version. Rule version selects its matching revision; native writer inserts both
  atomically and fails closed if that revision is absent. No circular current-
  revision FK or nullable half-created pointer is needed.
- automation_executions: UUID id; rule/action/client/queue tuple FK to rule;
  (rule_id,rule_version) FK to revision; source_event_id restrictive outbox FK;
  (ticket_id,client_id,queue_id) native composite ticket FK. Unique(rule_id,
  action_id,source_event_id). State pending|processing|succeeded|triage|superseded|
  cancelled|dead; attempts0..8, positive version, paired lease_token/lease_until,
  next_attempt_at, safe error_code nullable and created/updated UTC. CHECK pairs
  processing with a lease and nonprocessing with no lease. Operational updates
  cannot replace immutable source/rule context. Due-state/UUID index owns dispatch;
  ticket/created_at/id index owns scoped history.
- automation_effects: PK(rule_id,action_id,ticket_id); immutable work_item_id,
  project_id,client_id,queue_id,origin_execution_id, mode created|adopted,created_at.
  Composite rule/ticket/work/project/customer FKs enforce all native scopes, not
  application-only equality. A composite execution FK binds origin, rule/action,
  ticket/client/queue to the same execution. All identity columns non-null. There
  is deliberately no FK to the removable live link. A restrictive work FK retains
  the logical receipt after unlink. No count/materialized projection is added.

Every FK is restrictive. Revisions/effects are runtime insert-only; no purge.
Schema1/manual history is untouched. Downgrade locks these tables and refuses any
row or durable automation/provenance history before DDL; it never erases data.
Allow empty-schema roundtrip and preserve all older rows/grants/receipts.

## Locks, leases and least privilege

API config uses exact Origin, identity advisory lock723504391 before session auth,
CSRF, current configuration/content checks, then client/team/queue, rule and the
reviewed versions. Rule changes advance the queue aggregate too. Protected create
uses queue If-Match + Idempotency-Key; rule PATCH reviews queue AND rule versions.
Replay rechecks current authority before its minimal receipt and never enables a
rule again. Serialize configuration in the SAME client-before-team/queue order as
native ticket writes, not queue-before-client. Identity serialization also fences
default-project/archive/grant changes.

Dispatcher uses bounded SKIP LOCKED claims;30s leases,8 attempts,5s initial
exponential delay,900s cap and jitter, matching existing durable policy. Persist
claims before publishing only execution UUID+lease token to one registered actor.
Consumer locks identity first, then native current client/team/queue/ticket, rule,
execution/current unexpired token, then project graph and work row. This preserves
ADR0039's ticket-before-work-graph order. Refetch locked state before policy checks;
no graph-first acquisition followed by ticket lock. Claim transactions never hold
domain locks, and effects contain no network I/O. Account locks, if required,
use FOR NO KEY UPDATE. Expired/stale tokens cannot write a result or effect.
Use database clock_timestamp(), not a caller/broker instant, for authoritative
lease validity. Recheck the token/expiry in the final result write; losing that
fence rolls back the complete task/link/effect transaction, even after slow locks.

Crash before commit rolls back every effect; after commit redelivery sees the
logical receipt. Redis failure does not fail synchronous ticket writes. Attempts
exhaustion becomes dead; authorization/resolution ambiguity becomes triage, not
unbounded retry. Bounded fixed codes only, no exception text, ticket text or emails.
Scoped replay requires a fresh protected intent, current management/content
authority and reviewed execution version; it resets attempts on triage/dead only,
retains original revision/source and never removes the effect. Disabled rule or
superseded source cannot be forced by replay. Replay itself is audited.

Reuse altvia_worker with explicit grants needed by the second real domain writer:
new ledger SELECT/INSERT and operational execution UPDATE only; native task/history/
link INSERT; ticket/work UPDATE only version/updated_at; narrow metadata/grant/
membership SELECT and parent-lock-required UPDATE columns. No task owner/status/
content UPDATE, grant/account/session mutation, DELETE on links, notes/messages/
raw mail/MIME preview/file grants, audit reads or owner credential. Native scoped
owners need an explicit metadata-only loading profile so eager user/contact/text
relationships never demand password_hash or private content grants. Same native
authorization/lock predicates must serve API and worker; no copied permission SQL.
Prove actual runtime roles with real PostgreSQL negative privilege tests.

## Truthful events and read privacy

Keep every manual schema1 envelope byte-shape compatible. For automated native
work_item.created, ticket.work_linked and work_item.ticket_linked, emit schema2
with actor_id null, actor_kind automation, authorizer_id and execution_id, plus
the exact existing domain fields. A small typed AutomationOrigin at the native
event owner distinguishes execution from a UI click. WorkStatusHistory.actor_id
and link.created_by retain the real revision authorizer as authorization provenance,
not a fabricated service user; schema2 activity explicitly labels automation.
The execution/effect record ties history to its source/revision. Current history
readers must explain automated creation, not present it as a human click.

Migration29 also expands ActivityEvent's ck_activity_actor to accept automation
only for these three known event types with null actor_id. Retain user and
management_command rows unchanged. Extend the strict consumer by version/type;
never reinterpret schema1. Validate provenance against its committed execution
and effect context, not a broker-supplied authorizer.
Automated reciprocal link events retain both current endpoint visibility filters
before paging, including after unlink. Private rule/execution metadata events are
strictly acknowledged without shared identity/client/queue activity. No new feed
audience or event detail leaks hidden IDs, counts or more/cursors.

Rule routes are queue+client scoped. Execution history on a ticket requires its
current read scope; a mapped target additionally requires its CURRENT work scope
before row inclusion, IDs, counts or pagination. Missing project triage has no
target ID and still requires current source read. Mutation/replay capability
requires the stronger config/content conjunction. No worker lease token or raw
event payload enters HTTP. The internal execution_id in activity is never exposed
by generic activity DTO details; work-only readers may see automated creation and
its authorizer without a hidden source/execution ID. Reciprocal source fields
still require both native scopes. Detailed HTTP fields are pinned in the implementation
plan before source; generated OpenAPI/types remain the only browser DTO source.

## Compatibility, UI and acceptance

Activation floor is an automation-capable API producer, worker consumer and
privacy-aware web/history reader with this schema2 protocol. Before enabling a
rule, drain ALL pre-feature producers/workers, including owner mail promotion
tools, deploy the compatible set and verify readiness/worker health. Pre-feature
API binaries do not enforce a generic build floor and cannot stage executions;
pre-feature workers can dead-letter new events. They are NOT compatible rollback
images once automation is enabled. Expanded-schema retention alone does not fix
that. Disable/drain pending execution before replacing with an explicitly tested
compatible pair, retaining version-aware event tools. No claim of mixed old/new
support. Actual compatible-image rollback remains consolidated qualification.

Use Impeccable and current Twenty-inspired Operate patterns for a real rule form,
explicit disabled/enabled state, version review, immutable revision identity and
scoped execution outcomes/triage/retry. Native configuration choices only; loading,
empty/error/recovery/keyboard/390/1440/light/dark/axe and session disposal are
acceptance. No fake metrics or decorative scripts editor.

Prove actual native migration/ACL/effect atomicity, source staging through every
producer, wrong/old lease rejection, multiworker race, crash/redelivery/Redis loss,
reassign/reopen/manual unlink/default-project change, adopted/ambiguous links,
missing project/current grant revocation, native text privacy and both history
audiences. Preserve manual contracts/tests. Run full hosted API/browser/container/
source/image gates and one independent whole-increment review; retain failures.
This contract introduces no dependency/service/ISA requirement above x86-64-v1.
Final integrated VM qualification follows remaining development, per user cadence.
Real titles/status policy/rule scopes are Q-23; develop with synthetic fixtures
only and leave production unconfigured.

## Builder-check resolution

The fresh independent check found only two important planning questions. The
monotone disable-revision floor resolves delayed off/on without discarding
ordinary captured revisions or unbounded cancellation writes. Its cost if wrong
is an unintended effect after disable; native delayed-token/off-on tests are
mandatory. The target-only creation projection retains truthful automation and
the real authorizer, but withholds execution_id and any source identifiers from
generic activity DTOs. Its cost if wrong is a private execution leak or lost
legitimate task history; native current-scope/activity-before-paging and real
work-only browser tests are mandatory. These are executor engineering decisions,
not new user policy answers. No other important planning question was found.
