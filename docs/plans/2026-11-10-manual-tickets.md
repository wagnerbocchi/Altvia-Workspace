# Manual ticket lifecycle implementation plan

> Execute inline with superpowers:executing-plans. The user delegated routine
> choices and authorized direct main pushes. Register unresolved business inputs.

**Goal** Operate persisted manual tickets through scoped browser lifecycle.
**Architecture** Extend the existing monolith, explicit queue/customer authority,
identity-before-auth locks, strict version/receipt protocols and transactional outbox.
**Tech stack** Existing FastAPI/Pydantic/SQLAlchemy/PostgreSQL and Next.js/TypeScript.
**Spec** docs/adr/0028-manual-ticket-lifecycle.md and the fully read master spec.

## Global constraints

- Contracts precede implementation. Preserve existing persisted scopes and history.
- Explicit queue role plus customer ceiling on every ticket and linked lookup.
- Agent changes require assignment. Delegation and requester replacement need manager.
- Native identity number, composite reference FKs, append-only state history and outbox.
- Reviewed versions and immutable receipt IDs. Active references for new effects.
- Queue close/reopen flags default false. Actual business policy remains Q-07/Q-19.
- Preserve x86-64-v1 restrictions and current dependencies. No per-slice target SSH.
- Impeccable for UI. One fresh source review and finish/documentation.

## Review focus

- Configuration administrators without ticket role/ceiling must receive no content.
- New ticket reference pickers must stay purpose-bound and avoid directory grants.
- Lost create/claim/transition responses must retain original body/key/version.
- Removed assignee/candidate or archived contact must not block unrelated edits/replay.
- BIGINT numbers and prior queue records must survive browser and migration round trips.

### Task 1 Persisted ticket domain and HTTP

**Files** models.py, ticket_schemas.py, tickets.py, ticket_api.py, policy.py,
activity.py, identity.py, provision.py, queue schema/API validation, migration
b46087000015, test_tickets.py and generated OpenAPI/TypeScript.
**Interfaces** TicketCreate/Patch/Output/Receipt, TicketTransition/TransitionReceipt,
TicketFilters/Page, scoped choice pages, ticket permissions/history/event models.

- [x] Write failing real PostgreSQL/API tests for create/read/edit/assignment/claim,
  complete states and configurable close/reopen, all scope/reference negatives,
  immutable history, strict protocols, replay/revocation/archive/no-op and SQL shape.
- [x] Run the new tests before code. Implement at existing ownership seams with
  SQL scope before paging and inherited lock/version/session protocols. Extend
  policy's ticket branch to explicit queue authority. Support nullable old-assignee
  metadata in the existing event representation without changing legacy shapes.
- [x] Prove transaction rollback, concurrent create/claim/transition/logout, maximum
  number precision/version overflow, true FTS/GIN, least privilege, old queue/receipt
  compatibility and guarded migration. Run focused/full API, lint/format/mypy and
  generated contract checks. Expect all passing. Commit coherent backend batches.

### Task 2 Manual Service Desk browser

**Files** lib/tickets.ts, service-desk ticket screens/components/routes, queue policy
editor, workspace navigation, browser_fixture.py, tests/tickets.spec.ts and surface brief.
**Interfaces** Task 1 DTOs and current session-owned transport, paging and recovery.

- [x] Write real browser lifecycle and role/reference negative tests, uncertain
  create/claim/transition, failed authoritative refresh and stale edits. Run before UI.
- [x] Read Impeccable craft floor and reuse incumbent context. Build paged reference
  selection, explicit create review, scoped inbox/filter/search, detail editing,
  assignment/claim, configurable status transitions and scoped history.
- [x] Run web check/build, feature/full browser suites, keyboard/axe/overflow and
  desktop/mobile light/dark captures. Inspect evidence, complete finish/documentation
  and expect actionable real persistence and all passing checks. Commit.

### Task 3 Acceptance and publication

**Files** packaged smoke, ticket runbook, Phase 3C evidence, roadmap/PRD/ADR/plan
status and task-owned private evidence.
**Interfaces** Exact reviewed source and complete local/hosted/review/image evidence.

- [x] Extend packaged proof with real customer/queue-scoped manual ticket lifecycle,
  SQL/history persistence after service restart and denied inherited configuration.
  Obtain one fresh whole-increment source review. Fix Important findings with
  real RED/GREEN and passing final suites. Keep Impeccable evidence accurate.
- [x] Push checked coherent commits to main. Follow all five exact-source hosted
  gates, retaining full logs, scanner severities, metadata and nonempty inventories.
- [x] Preserve immutable evidence and hashes, record this bounded completion and
  remaining Phase3-6/target gates, publish Markdown closure, verify remote main.

## Acceptance record

Application/test source da7999c passed all five hosted gates with 584 API and
107 browser tests. Both Important source-review findings and both Impeccable
fixes have passing proof. See docs/phase-3c-ticket-evidence.md. Consolidated
actual target qualification follows remaining MVP development.
