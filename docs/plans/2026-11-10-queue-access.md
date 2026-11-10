# Explicit queue access implementation plan

> Execute inline with superpowers:executing-plans. The user delegated routine
> choices and authorized direct main publication. Record unresolved external inputs.

**Goal** Administer persisted queue access and expose operational metadata only
within explicit queue membership.
**Architecture** Extend existing role_bindings and queue registry with the
identity-before-auth lock, immutable receipts, reviewed queue versions and outbox.
**Tech stack** Existing FastAPI/Pydantic/SQLAlchemy/PostgreSQL and Next.js/TypeScript.
**Spec** docs/adr/0027-queue-content-access.md and the master specification.

## Global constraints

- Contracts precede code. Preserve existing scopes, data and x86-64-v1 restrictions.
- Configuration authority administers grants. Queue roles never create customer access.
- One queue binding per account. No duplicated membership table or global directory.
- Identity lock before auth, then team, queue, target account. Protected replay and ETag.
- Real local/CI persistence and security proof. Final target qualification after MVP.
- Reuse incumbent Impeccable context. One fresh source review and finish/documentation.

## Review focus

- Queue-only roles must expose neither other queues nor team/client directories.
- Parent and roster refresh errors must keep writes disabled after a receipt.
- Removed target/inactive parents must not change committed-replay semantics.
- Downgrade tests must use old-schema SQL before restoring the current mapped model.
- An obsolete session waiting for the identity lock must fail before delegation.

### Task 1 Persisted access and API

**Files** models.py, queue_registry.py, queue_schemas.py, queue_api.py, activity.py,
migration b46087000014_queue_access.py, tests/test_queue_access.py, generated contracts.
**Interfaces** QueueMemberRole(role_name), QueueMemberAdd(email,role_name),
QueueMemberReceipt(queue_id,user_id), QueueMemberPage(items,next_cursor,queue_version).

- [ ] Write failing PostgreSQL/API tests for all ADR invariants, including queue-only
  read scope, strict role checks, archived no-ops, atomic rollback, lock races and
  migration preservation/refusal. Run the new tests before product code.
- [ ] Extend existing registry and DTOs. Use known-email lookup inside authorized
  POST, exact queue version protocol and the existing session invalidation helper.
  Add strict event validation without broadening legacy event shapes.
- [ ] Run focused/full API, ruff/format/mypy, Alembic drift and OpenAPI generation.
  Expect passing tests and unchanged existing behavior. Commit coherent backend.

### Task 2 Browser access administration

**Files** service-desk members route/components, lib/ticket-queues.ts, queue detail
link, browser_fixture.py and tests/queue-access.spec.ts.
**Interfaces** Task 1 DTOs and existing session-owned transport, paging/recovery.

- [ ] Write real browser lifecycle, viewer/queue-only isolation, stale writes,
  original POST retry and failed-refresh tests. Run before UI for missing controls.
- [ ] Read Impeccable craft floor, implement the incumbent admin patterns, explicit
  grant review and removal confirmation. Keep original drafts immutable through errors.
- [ ] Run web check/build and focused/full browsers. Capture desktop/mobile light/dark,
  inspect frames and run axe/overflow. Complete Impeccable finish/documentation.
  Expect passing tests and actionable controls backed by real persistence. Commit.

### Task 3 Acceptance and publication

**Files** packaged persistence assertions, runbook, Phase 3B evidence, roadmap/ADR/plan.
**Interfaces** Exact source and preserved local/hosted logs, scans and review evidence.

- [ ] Extend packaged smoke with real access persistence and denied escalation.
  Obtain one whole-increment source review. Fix Important findings with RED/GREEN.
- [ ] Push checked coherent commits to main, follow all five hosted gates and collect
  complete logs/artifacts/image inventories and all severities. Expect all pass.
- [ ] Record bounded completion, deferred integrated VM qualification and remaining
  ticket lifecycle/messages/email. Commit/push evidence, verify actual remote main.
