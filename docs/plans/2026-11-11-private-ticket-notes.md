# Private ticket notes implementation plan

> Execute inline with superpowers:executing-plans. The user authorized direct
> main commits/pushes and delegated routine choices. Register business questions.

**Goal** Operate immutable internal ticket notes with explicitly delegated privacy.
**Architecture** Extend queue bindings, ticket scope/locking and transactional
outbox in the monolith. Private notes have independent authority and persistence.
**Tech stack** Existing FastAPI/Pydantic/SQLAlchemy/PostgreSQL and Next.js/TypeScript.
**Spec** docs/adr/0029-private-ticket-notes.md and fully read master specification.

## Global constraints

- Contracts before code. Old bindings default note_access none.
- Explicit queue agent/manager, note permission and customer ceiling on every read/write.
- Identity before auth, reviewed versions, protected IDs, incumbent target locks/sessions.
- Immutable private text, ticket-version order, SQL constraints and redacted events.
- Preserve legacy fingerprints/envelopes. Exclude private activity/count/body/ID and FTS.
- Current dependencies and x86-64-v1. Consolidated target qualification after MVP.
- Impeccable for UI, one fresh source reviewer and finish/documentation.

## Review focus

- Existing writers/platform administration start without note authority.
- Old receipts cannot silently restore note permission after revocation.
- Denied note events/counts/IDs remain absent from ordinary activity/pages.
- Draft body/version/key survive focus refetch, lost response and failed reads.
- Acknowledged creation stays locked through failed authoritative refresh.

### Task 1 Explicit note permission and private persistence/API

**Files** queue_schemas.py, queue_registry.py, queue_api.py, policy.py, models.py,
ticket_schemas.py, tickets.py, ticket_api.py, activity.py, provision.py,
migrations/versions/b46087000016_ticket_notes.py, tests/test_ticket_notes.py,
affected queue/ticket regressions and generated OpenAPI/TypeScript.
**Interfaces** note_access none|read|write; TicketNoteCreate/Output/Page/Receipt;
can_read_notes/can_add_note; GET/POST notes and scoped GET note ID; strict note event.

- [x] Write/run failing PostgreSQL/API tests for explicit grants/default denial,
  note creation/read, filtered activity, strict protocols, replay, old fingerprints/
  envelopes, ordered paging, SQL/runtime boundaries and the five review-focus cases.
- [x] Extend current owners/locking/session/receipt protocol. Reuse state-history
  version cursor parsing. Implement immutable notes, current scope/capabilities,
  private activity filtering and strict redacted projection.
- [x] Prove concurrent note/replay/role/logout, rollback/overflow, archive/closure,
  privileges/guarded downgrade and bounded queries. Run focused/full API, static,
  schema/build and generated contract checks. Commit passing backend batches.

### Task 2 Scoped notes and note-grant browser

**Files** service-desk/members.tsx, lib/ticket-queues.ts, lib/tickets.ts,
tickets/detail.tsx, notes.tsx, reads.tsx, browser_fixture.py,
tests/ticket-notes.spec.ts and surface brief.
**Interfaces** Task1 DTOs, session-owned transport, retained intent/acknowledged ID,
successful authoritative refresh and independent note paging.

- [x] Write/run failing browser grant review/private note tests, including no denied
  fetch/render, uncertain POST, focus/stale version and failed post-receipt refresh.
- [x] Load Impeccable context/craft floor and extend incumbent UI with visibly
  internal plain text, protected intent recovery, fresh-write gating and real states.
- [x] Run web check/build, focused/full browser, keyboard/axe/overflow and light/dark
  desktop/mobile captures. Complete Impeccable review/documentation and commit.

### Task 3 Acceptance and publication

**Files** container_smoke.py, runbooks/ticket-notes.md, Phase3D evidence,
roadmap/PRD/ADR/plan status and private immutable evidence.
**Interfaces** Exact reviewed source and complete local/hosted/security evidence.

- [x] Prove packaged delegation, note restart persistence, ordinary reader denial
  and no outbound mail. Obtain one fresh source review and fix Important findings
  with RED/GREEN and appropriate passing suites.
- [x] Push checked coherent commits to main. Follow five exact-source hosted gates,
  preserving full logs/artifacts, severities and five nonempty image inventories.
- [x] Freeze hashed evidence, document bounded completion/remaining phases, publish
  Markdown closure and verify clean actual remote main and source compatibility.

Acceptance source fb83c03 passed all five hosted gates, local API 612 and browser
116. The source review's Important finding was missing packaged coverage, not an
application defect: expanded privacy assertions now pass on the real stack.
The later test-selector collision has a real Chromium RED/GREEN reproduction.
See docs/phase-3d-note-evidence.md for full results, advisories and remaining scope.
