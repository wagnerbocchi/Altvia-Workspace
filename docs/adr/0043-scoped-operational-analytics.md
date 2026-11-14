# ADR-0043: Scoped operational analytics without stored counters

Date2026-11-14. Status: selected for development under the user's delegated
continuous MVP execution. The master specification was read completely. This
contract implements FR010 and the Overview/Team reporting requirements; it does
not certify implementation, production policy, capacity or final qualification.
ADR0006 source/date precision, ADR0007/0040 representation and all native content
authority remain binding. The remaining sequence is the MVP completion plan.

## Decision and alternatives

Use read-only PostgreSQL aggregates over currently authorized native rows.
Expose overview, paged principal-responsibility workload and paged filter choices.
No new table, grant, worker, counter projection, dependency or service is needed.
Browser page merging misses unloaded records. Stored duplicate counters require
additional invalidation and consistency machinery without a demonstrated need.
Neither is selected. Keep the incumbent My Work API and its personal semantics.

This is a current-state report, not a historical-state reconstruction. Optional
created-in-period filters select current records by their native created_at.
They do not infer source-workbook creation/completion timestamps or throughput.
Do not rank productivity by closures, invent staff capacity, create time entries,
or treat continuous work as an incomplete ordinary task.

## Authority and metadata

Analytics is initially a management read. Work requires the existing
project_registry.visible_projects predicate AND its can_manage expression.
Tickets require tickets.visible AND the existing queue operations_manager role.
The native customer ceiling, direct project membership/inherited client role and
queue role continue to apply before counts, suppression, labels and paging.
Archived parent reads retain their native read semantics. Assignment, a live or
historical link, team metadata/roster, external participant labels and global
platform administration never confer analytics content access.

Derive analytics.read availability in the existing identity capabilities list
from an explicit content-scope management binding: client/queue operations_manager
or project project_manager. This is navigation/operation availability, not a row
grant. A surviving but insufficient binding cannot bypass current membership or
customer ceilings. Requests without that availability return403 after normal
session authentication. Agents retain their existing My Work; viewers and bare
platform administrators receive no new analytics grant. No new persisted grant
administration is introduced. A platform administrator with explicit native
management authority sees only that independently authorized content.

Filter-choice labels derive from managed visible projects and tickets and their
already-readable parent context. Project choices include managed empty projects;
client choices exclude internal projects' null client. Team/client names are not
an unrestricted directory. Responsible-person choices include only actual native
owner/assignee identities in managed visible records, including former/inactive
owners still referenced by records. Return no email, account state, roster,
contact lookup or role information. Null responsibility is an explicit filter
and workload bucket, never a generated user. External labels never become staff.

## Native candidate sets and filters

Compute W from managed visible projects and their work items, T from managed
visible tickets. Each native row appears once. Both datasets independently apply
optional priority, client_id, team_id and responsible_id. Work responsibility is
owner_id; ticket responsibility is assignee_id. This is principal responsibility,
not the personal My Work owner-or-participant predicate. unassigned=true selects
null principals in both domains and conflicts with responsible_id.

project_id narrows W to that managed project. T additionally requires a live link
to work in that currently managed project. The project/link predicate does not
inherit the linked work's priority, owner or creation-period filters; each native
candidate must independently satisfy its common filters. Hidden or merely
viewable but unmanaged projects cannot classify tickets for this report.

Optional created_from and created_before must appear together, are aware ISO
instants and satisfy from < before. Apply the half-open range to each row's own
created_at, not message/source/weekly-note dates. Keep native lifecycle states
separate. All counts below use the complete filtered datasets, never loaded pages.

## Counting and reconciliation

Active W excludes done/cancelled; active T excludes resolved/closed. Ordinary W
has work_type=one_off; ongoing remains orthogonal to lifecycle state.

- work_item_count=|W|; ticket_count=|T|.
- represented_ticket_count counts T having a live link to ANY eligible W.
  standalone_ticket_count=ticket_count-represented_ticket_count.
  unified_count=work_item_count+standalone_ticket_count. Distinct work is never
  collapsed transitively through a ticket or another task.
- active_work_item_count and active_ticket_count use the active subsets.
  active_unified_count repeats full-set suppression using ONLY those active
  subsets. A completed linked task must not hide an active standalone ticket.
- active_no_due_date_count counts active ORDINARY W with due_at null.
  all_missing_deadline_count counts ALL W with due_at null, including terminal
  and ongoing rows. These predicates intentionally differ, as in ADR0006.
- ongoing_work_item_count counts active ongoing W regardless of a stored due.
  Ordinary deadline buckets below exclude ongoing; absence is a fact, not a
  performance fault. Tickets never receive a fictitious task deadline.
- overdue_work_item_count, due_soon_work_item_count and later_due_work_item_count
  partition active ordinary dated W using the explicit reference/window below.
  Their sum + active_no_due_date_count + ongoing_work_item_count equals
  active_work_item_count.
- blocked_work_item_count counts active W with status=blocked. Unassigned work/
  ticket counts use the active subsets. Ticket pending-customer/third-party
  counts use their native states, not work blockage or inferred effort.
- Fixed-key work/ticket lifecycle and priority distributions count their own
  filtered native datasets and reconcile respectively to work_item_count and
  ticket_count. They are not combined effort or deduplicated priority rankings.

Workload rows group the ACTIVE subsets by their principal UUID, with one null
bucket when necessary. Return separate active_work_item_count/active_ticket_count,
blocked_work_item_count, ongoing_work_item_count, active_no_due_date_count and
ordinary overdue/due-soon/later counts. Do not expose a per-person unified_count:
a ticket assigned A and a linked task owned B have separate responsibilities,
while global representation suppresses their duplicate origin. Primitive domain
and deadline columns reconcile across the COMPLETE workload, not a single page.
The workload response includes the same global overview totals in its statement
snapshot. Separate HTTP reads need not share a snapshot after concurrent writes.

## Time and recorded SLA observations

Required reference_at and due_through are explicit aware ISO instants; require
reference_at < due_through and canonicalize UTC. Reject numeric timestamp
coercions, naive values and nonrepresentable UTC conversion. Required timezone
is a bounded exact installed PostgreSQL timezone name, validated before querying.
The response echoes normalized parameters and server observed_at.

Use the stored native deadline boundary. For DateDue, overdue means
due_at <= reference_at: the prior local business date has ended. For InstantDue,
overdue means due_at < reference_at: exact equality is on time. A nonoverdue
ordinary dated item is due_soon when due_at <= due_through, otherwise later.
Do not reinterpret a saved date in the viewer timezone, round away microseconds,
or compute local-day boundaries in browser SQL replacements. ADR0006 remains
the date owner. No company SLA hours or implicit due-soon threshold is created.

SLA metrics are explicitly RECORDED observations in each filtered ticket's most
recent native tracked cycle. legacy/unconfigured/configured ticket counts form
an exhaustive partition of T. A legacy ticket has no tracked cycle; an
unconfigured cycle has no captured policy. Count distinct configured tickets with
a recorded breached event, and its subset with a recorded correction. Preserve
observed breaches after a correction. sla_last_observation_at is nullable max
occurred_at across those current-cycle SLA events. These are persisted history
facts observed now, not recalculated current SLA risk, a browser timer, or a
historical SLA result at reference_at. No native cycle/clock/read freshness
algorithm is duplicated. The UI must label the distinction and link to real
ticket outcomes where appropriate. Hidden ticket history contributes nothing.

## HTTP contract

All reads authenticate the normal current session and forbid unsupported or
repeated query keys with422. No writes, protected POST, receipt or event is added.

- GET /api/v1/analytics/overview: required reference_at,due_through,timezone;
  optional priority,client_id,team_id,project_id,responsible_id,unassigned,
  created_from,created_before. Return AnalyticsOverview with observed_at,
  normalized reference/window/timezone, the documented scalar counts and fixed
  native lifecycle/priority distributions. Unassigned defaults false.
- GET /api/v1/analytics/team-workload: same filters plus limit1..100/default50
  and optional cursor<=320. Return {items,next_cursor,overview}; each item has
  user_id/name nullable as a pair and the documented principal workload counts.
  No empty roster row, capacity, email, hidden count or productivity score.
- GET /api/v1/analytics/scopes: kind=client|project|team|responsible required,
  limit1..100/default50 and optional cursor<=320. Return {items,next_cursor},
  items {id,name} with bounded native labels. These choices are actor-scoped
  management contexts/identities, independent of report filters; choosing one
  never grants access or promises positive counts. A separate unassigned control
  represents null. Do not load all pages or infer a complete roster from one page.

Workload ordering is null principal first, then nonnull UUID ascending. Scope
choices sort by UUID. Cursors are strict URL-safe base64 without padding of
version, SHA256(actor+canonical filters/collection), null rank and UUID. Scope
choices use their kind instead of report filters. Scope-choice rows are nonnull;
workload's null rank uses a fixed zero UUID only inside the cursor and rejects
inconsistent pairs. A real zero UUID remains distinct under nonnull rank.
Bind normalized UTC instants and all effective filters, excluding limit/cursor.
Reject malformed/mismatched cursors422. Recheck current authority on every page;
cursor/as_of is never a grant or a cross-request snapshot. Empty unauthorized
resource filters are indistinguishable from empty nonexistent filters.

Each report uses one PostgreSQL statement snapshot for eligibility, complete-set
suppression, counts, workload selection and labels. Use fixed query count and
bounded output; never load every underlying record into Python/JavaScript. Native
statement timeouts and503 handling remain; failure never becomes a zero result.
No read updates a domain aggregate, audit/outbox, timer, history or receipt.
Normal authenticated session last-seen updates remain permitted.

## Browser and verification boundaries

One real /analytics workspace surface, available through analytics.read, extends
the accepted Twenty-inspired Operate world with Impeccable. Provide actual report
filters and paged permitted choices, summary/reconciliation facts and the paged
active principal table. Use the viewer's explicitly displayed local timezone and
instants, with an editable reference/window; these are view filters, not company
policy. Retain selected ID/label off-page and during pending/error reads. Do not
display draft filters as if applied to an old response. Provide truthful empty,
loading, error, permission, recovery and current-session behavior.

Proof requires manager/client/project/queue conjunctions and non-grants; revoked/
archived/empty scope and hidden labels; full-set N:N suppression and independent
filters; active/terminal/ongoing/null responsibility; DateDue/InstantDue equality,
DST/offset and microseconds; strict queries/cursors and same-statement coherence;
recorded corrected SLA history; representative native aggregate EXPLAIN/latency
and fixed query count; real browser keyboard/recovery/privacy/theme/width checks;
packaged persistence/revocation/reconciliation; fresh whole-increment review and
all exact-source hosted gates. Preserve prior APIs/generated schemas. Final
target qualification follows the remaining MVP, with no production or real import.
