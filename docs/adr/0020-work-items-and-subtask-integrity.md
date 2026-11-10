# ADR-0020: Persisted work items and subtask integrity

Date: 2026-11-09. Status: implemented and qualified on 2026-11-10.
Scope: FR-003 and its scoped FR-012 history; project task list, not Kanban/My Work.
User authorized continuation, routine decisions and direct main publication.
Exact source/image evidence: docs/phase-2c-work-evidence.md.

## Decision and alternatives

Extend the existing modular monolith, scoped project reads, session-owned browser
queries, protected POST receipts and versioned writes. Reuse PostgreSQL and the
durable activity consumer. No new dependency, engine, service or native version.
An independent task ACL would duplicate project scope; implicit team inheritance
would contradict ADR-0019. Assignment never grants access. Do not build boards,
search, ticket coupling, scheduling, imports or time tracking in this increment.

### Authority

Every work read first requires the actual ADR-0019 project read predicate, including
the customer ceiling and both direct binding/membership halves. Team metadata and
global administration never bypass it. Client operations_manager and explicit
project_manager manage tasks. Explicit member agents may create, comment and read;
only the current owner/participant agent may update content or transition. Viewers
read only. Only managers change parent/owner/participants; agents create self-owned
tasks with no delegated participants. Candidate lookup returns bounded active
project contributors (manager/agent, including inherited client managers), IDs and
display names only. It must never expose the global account directory.

Existing assignments may outlive account/access revocation as historical IDs;
they do not retain content authority. New/replacement assignments must have current
active contributor access. Managers can clear stale assignments. Names in task
responses are not resolved through unrestricted account lookup. Archived project,
customer or owning team permits reads but refuses every new task mutation.

### State, hierarchy and dates

Immutable project_id. Title trims to 1..300, plain-text description <=20000,
priority low/medium/high/critical, type one_off/ongoing. New ordinary work starts
todo; ongoing starts in_progress. Status changes use a dedicated transition POST,
never PATCH. Apply the transition graph in docs/contracts/api.md. Blocked requires
nonblank reason <=2000; leaving blocked clears it. Done sets UTC completed_at;
reopen clears the current completion while retaining immutable history. Ongoing
done requires explicit end_operation=true plus a reason. Cancelled restore is
manager-only. Terminal reopens require a reason. Same-state requests are no-ops
after current authorization/version checks. No recurrence generation.

Owner is nullable and participants are distinct, bounded to 50. Changing either
does not change grants/sessions. Parent may be null, must exist in the same
authorized project and cannot create cycles. A composite FK, self CHECK and DB
cycle trigger enforce hierarchy. Every graph write acquires a transaction-scoped
project advisory lock before traversal; application locks before any task row
lock. Identity write lock remains first, before authentication. The trigger locks
the project too, serializing raw concurrent parent changes. No dependency graph
or parent-completion cascade in this slice; parent/child status is independent.

Due is null, {precision:date,date,timezone} or {precision:instant,instant}. Date
precision retains the date/zone and exclusive next-local-midnight UTC boundary
under ADR-0006; timezone must be a known IANA zone and skipped local dates are
rejected. Instant requires a timezone-aware ISO timestamp. No inferred deadlines
or stored days_remaining. PostgreSQL owns IANA-zone validation and conversion
using its existing timezone database; API images need no new zone package.
The shared SQL function altvia_work_day_start resolves an ambiguous midnight to
its first occurrence. It observes native zone offsets within two days, selects
the earliest exact midnight, or bisects the offset-bracketed forward gap to one
microsecond. This covers midnight gaps and skipped days without a second tzdb.
Both API and trigger use it; a skipped source date is refused. This costs native
timezone calculations on date writes and avoids inconsistent application rules.
Browser instants display the actual device zone. Independent edits preserve the
original instant including submillisecond precision and a repeated-clock occurrence.
Intentional changes accept milliseconds; repeated local clocks require explicit
UTC entry. Retained historical assignments do not block independent maintenance;
only new owner/participant links must satisfy active candidate validation.
New live completions have known timestamps; import precision
remains a later contract. estimated_minutes is nullable/nonnegative.

### HTTP and persistence

- GET /work-items requires project_id, bounded UUID cursor bound to project.
  Returns task records and fresh can_create/can_manage independent of pagination.
- POST /work-items uses Idempotency-Key; returns minimal {work_item_id,project_id}.
  Recheck current project/create authority before receipt replay; do not revalidate
  mutable candidate/reference state or repeat effects when returning a receipt.
- GET/PATCH /work-items/{id} return ETag; strict nonempty PATCH accepts title,
  description, priority, parent_id, owner_id, assignee_ids, due, estimated_minutes.
  Assignment/parent fields require management even if their submitted value matches.
- POST /work-items/{id}/transitions uses If-Match plus Idempotency-Key. Recheck
  current action authority before replay, but do not repeat the old transition.
- GET/POST /work-items/{id}/comments: internal plain text <=10000, bounded cursor;
  POST protected by If-Match and Idempotency-Key, advances task version.
- GET /work-items/{id}/activity authorizes the parent before scoped history.
- GET /work-items/{id}/status-history returns immutable scoped transitions/reasons,
  in descending version order. Comments use chronological timestamp/ID pagination.
- Task owner/participant display names come only from persisted assignment links,
  including former contributors; no account-directory authority is implied.
- GET /projects/{id}/work-candidates requires work.create; bounded contributor IDs.

Migration b46087000008 adds work_items, assignees, comments and immutable status
history. Constraints cover enums, dates, version and state timestamps. Runtime
gets operational DML, comments/history SELECT+INSERT only; worker no task-table
access. Audit/outbox commit with mutations. Payloads include safe IDs, changed
field names and state names only, never titles/descriptions/comments/reasons.
Strict work event-family validation and work-only history preserve all existing
identity/client/project feed boundaries. Downgrade refuses durable work/history.
Rollback preserves expanded schema/data and a compatible worker; never reset
volumes or dead-letter new event types with an old worker.

## Acceptance and boundary

Prove real creation/edit/assignment/subtask/transition/comment and recreation,
cross-client and membership-half denial, assigned-agent limits, stale candidate
denial, independent parent state, concurrent cycles, atomic replay/history,
strict payloads, deadline midnight/DST/null semantics, archived refs, migration
preservation/refusal and runtime privileges. Browser must operate the same API
with original-intent recovery, conflicts, session disposal, mobile/themes/axe and
visible keyboard focus. Apply Impeccable, full source review, five hosted gates
and actual baseline-VM qualification. Stop at qualified task core; Phase 2 remains
open for Kanban/filter/search/My Work and later client contracts.
