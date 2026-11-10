# Product requirements

Status: Phase 0 design baseline for review, 2026-11-08. Source: master
specification v1.1 sections 1-4,7,12-14. Later user authorization permits
incremental implementation and direct publication to main, without PR.

## Problem, users and success

Altvia needs to replace spreadsheet consolidation with persistent operational
work, projects and native email support. Employees need one authorized queue
of their tickets and tasks. Operations managers need actual workload and
deadlines within their teams/clients. Project managers need scoped planning.
Agents need support conversations, private notes and SLA visibility. Viewers
need read-only access to explicitly granted resources. Platform administrators
manage configuration, not implicit unrestricted access to customer content.
External contacts are email identities only in the MVP.

Success means a real employee can receive and answer email, update persistent
work, and see correctly consolidated My Work; a manager can reproduce source
totals and explain divergences; the same production images run on the target
x86-64-v1 VM. No real user count, mailbox traffic or benchmark is yet known.

Plane informs navigation and density. Zammad informs support capabilities.
Altvia has original code/assets/UI and no production dependency on either.
Existing Zammad remains operational until a separate approved cutover.

## Scope and acceptance traceability

All criteria below require persisted data, server authorization, error handling,
automated verification and real UI when applicable. Phase numbers refer to
`docs/roadmap.md`; P1 features can follow core MVP acceptance.

| Requirement | Delivery | Verifiable acceptance |
| --- | --- | --- |
| FR-001 Identity, teams, sessions, RBAC P0 | 1 | Login succeeds with valid account, expires/revokes; negative cross-client reads and writes fail |
| FR-002 Clients, areas, projects P0 | 2 | Scoped CRUD and milestone lifecycle persist after restart; multiple projects per client; internal projects need no fake client |
| FR-003 Work/subtasks/owners P0 | 2 | Create/assign/block/complete, owner and participants distinct; cycles and stale writes rejected |
| FR-004 Kanban, list, filters, FTS, My Work P0 | 2,4 | Authorized paginated results; consistent filtering; N:N consolidation verified in Phase 4 |
| FR-005 Tickets/queues/history P0 | 3 | Unique human number; requester, assignee, state and audit survive restart |
| FR-006 Messages/private notes/files P0 | 3 | Public reply and private note distinct; unauthorized body/download rejected |
| FR-007 Native email P0 | 3 | New mail creates triage/ticket, authorized reply correlates, public response queues and records delivery |
| FR-008 N:N ticket/work P0 | 4 | Both endpoints authorized and same client; no cascading state change |
| FR-009 Assignment automation P0 | 4 | Retry, reopen and concurrent assignment create at most one logical task per configured rule/action |
| FR-010 Operational analytics P0 | 5 | Counts reconcile with underlying authorized rows and explicit date/timezone |
| FR-011 SLA P0 | 5 | First-response/resolution calendar, pause and reopening scenarios pass, with preserved policy revision |
| FR-012 Audit/activity P0 | 1-5 | Every mutation records actor/resource/correlation; sensitive payload redacted |
| FR-013 Notifications P1 | 5+ | Assignment, mention, blocked, overdue and breach honor recipient scope/preferences |
| FR-014 Time tracking P1 | 5+ | Authorized positive-minute entries total once, ticket/task relationship does not duplicate effort |
| FR-015 CSV/XLSX export P1 | 5+ | Export uses same ACL as reads; dangerous formula prefixes neutralized |
| FR-016 Advanced planning P2 | backlog | Calendar/Gantt/dependencies beyond baseline after core workflows stabilize |
| FR-017 Portal/knowledge P2 | backlog | Separate design and external identity/security review |
| Source import | 5 | All 34 rows accounted for, 19 weekly updates and 8 notes preserved; approved mappings and replay tested |
| CPU and recovery | 1,6 | Runtime and functional tests on actual guest; consistent database/file restore and rollback |

Delivery status 2026-11-10: Foundation is closed. Phase 2A delivers only the client
registry portion of FR-002 and its scoped FR-012 activity, qualified on the actual
baseline VM (docs/phase-2a-client-evidence.md). Phase 2B adds persisted internal/
customer projects, explicit managers/members, shared operational areas and scoped
project activity, qualified on the same baseline VM with 358 API/42 browser tests
and all five hosted gates (docs/phase-2b-project-evidence.md). Phase 2E below adds
FR-002 client contacts and default ticket projects. Phase 2C now delivers
the ADR-0020 task core of FR-003 and scoped FR-012: persisted tasks/subtasks,
owners/participants, deadlines, transitions, internal comments and attributable
history. Source d5ae972 passed 403 API/48 browser tests, all five hosted gates and
actual x86-64-v1 qualification; same-ID image reports contain zero vulnerabilities.
See docs/phase-2c-work-evidence.md. Phase 2D delivers the task portion of FR-004:
typed filters, native PostgreSQL FTS, independently paged Kanban and task-only
My Work. Source 1c20f48 passed 424 API/52 browser tests, all five hosted gates and
actual x86-64-v1 qualification; the same five tested images report zero
vulnerabilities. See docs/phase-2d-discovery-evidence.md. Phase 2E now delivers
external contacts and same-client default ticket projects under ADR-0022,
without account linkage, verification or ticket/email side effects. Application
334d477 passed actual x86-64-v1 qualification; test-only c722de2 passed all five
hosted gates with 463 API/60 browser tests. Exact native-tested image reports have
zero vulnerabilities. See docs/phase-2e-contact-evidence.md. Phase 2F now delivers
scoped browser member grants/roles/removal under ADR-0023, with session invalidation,
immutable grant confirmation/replay and reviewed versions. Exact b179695 passed
all five hosted gates with 480 API/67 browser tests and actual x86-64-v1 member/
ACL/browser/recovery/native/resource proof. The same five target-tested images
report zero vulnerabilities; see docs/phase-2f-member-evidence.md. Phase 2G adds
basic persisted milestones under ADR-0024: optional date/instant deadlines,
conclude/cancel/explicit reopen, scoped activity and reviewed-version browser
recovery. Local 500 API/72 browser passed; initial hosted image findings received
vendor correction 011e0a5. That exact source passed all five hosted gates with
500 API/72 browser and zero reported vulnerabilities in all five scanned images,
using the same scanner DB as the failed scan. Development is complete; evidence
is recorded in docs/phase-2g-milestone-evidence.md. Final integrated
target qualification is deferred until remaining MVP development ends, following
the user's updated cadence. Phase 2H now adds bounded task-owned external labels
under ADR-0025: manager-only writes, plain-text attribution without identity/grants,
and legacy replay compatibility. Contracts 6a03689 preceded backend a4c456d and
browser f5b4e2a. Exact f5b4e2a passed all five hosted gates with 523 API/78 browser
tests, packaged label persistence/recovery, zero blocking source findings and
zero reported vulnerabilities in all five scanned images. Phase 2 development
is complete; see docs/phase-2h-external-participant-evidence.md and
docs/phase-2-development-closure.md. Final integrated target qualification remains
pending. Phase 3 Service Desk is next; ticket consolidation remains Phase 4 and
production acceptance remains separate.

Non-goals: SaaS billing/subscriptions, marketplace, local AI/embeddings, external
search cluster, advanced ITIL/CMDB, advanced Gantt and native mobile applications.
No speculative scaffolding for these capabilities.

## Functional decisions

Ticket and task are independent aggregates. Tickets can have zero or many tasks;
tasks can have zero or many tickets. Assignment emits an event but creation of
work is a rule, not an inevitable side effect. No default fake project, no
implicit ownership transfer on reassignment, no task completion on ticket closure.
SLA timers and task deadlines are separate. Continuous work is an active work
type, not completed work or an automatically repeated schedule (ADR-0006).

My Work counts distinct eligible tasks and tickets not already represented by
those tasks. Linked ticket badges retain origin without duplicating task effort.
The full authorization/filter projection precedes pagination (ADR-0007).
Metrics expose source ticket/task counts separately from unified row count.

No production records or user memberships may be inferred from source labels.
Import retains original text, status, date precision and provenance; ambiguities
go to review. Lack of a historical timestamp remains unknown.

## Experience contracts

Frontend work uses `impeccable`, explicitly requested by the user. At frontend
start load skill context against the actual repo; choose Operate for work
surfaces, establish PRODUCT/DESIGN context as directed, and inspect rendered
results. This planning phase does not claim an implemented design system.

Navigation: Overview, My Work, Projects, Service Desk, Team, Planning, Analytics,
Settings. Only implemented, authorized actions appear as active controls.
Each surface has loading, empty, error and success states; keyboard navigation,
visible focus, labels, contrast and responsive behavior. Target WCAG 2.2 AA,
with automated checks plus keyboard/manual review. Preserve entered data after
recoverable errors. A stale version offers reload/reconcile, not silent overwrite.

My Work identifies origin, priority, state, deadline and links. Service Desk
distinguishes private note/public response before send and during confirmation.
Team views expose blocked/undated work without ranking productivity solely by
closed-ticket counts. Views support light/dark mode and original Altvia branding.

## Nonfunctional targets and definition of done

Proposed, not measured: usual paginated read p95 <500 ms; availability 99.5%;
RPO <=24 h; RTO <=4 h. Benchmark against representative volume and actual
CPU/RAM/disk before adopting them as promises. Observe request/job latency,
outbox age, mailbox errors, SLA breaches, queue depth and resource use.

A slice is done when migrations/constraints, domain behavior, typed API,
authorization, real-data UI, failure handling, relevant tests and documentation
are verified. Show actual commands/results; identify skipped gates. No mock
dashboard, inactive button or untested container counts as delivered functionality.
Production requires secret injection, HTTPS, backup/restore, rollback, scanning,
retention approval and x86-64-v1 evidence. Phase 0 satisfies design/discovery only.
