# Public ticket response drafts implementation plan

> Execute inline using superpowers:executing-plans; continuous MVP sequence is
> docs/plans/2026-11-11-mvp-completion.md. Do not stop after this slice to re-ask.

**Goal:** Operate real public response drafts without sending private notes.
**Architecture:** Existing ticket scope/lock/version/replay owner, separate
append-only public message model, strict redacted events and incumbent UI.
**Tech stack:** Existing FastAPI/SQLAlchemy/PostgreSQL/Next.js/TypeScript.
**Spec:** docs/adr/0034-public-ticket-response-drafts.md and master specification.

## Constraints and review focus

- No transport, requester verification, inferred identity, note conversion or state/SLA coupling.
- Reads require queue role and client ceiling; write requires manager/assigned agent.
- Current authority/protocol before saved replay; closed/inactive only blocks fresh effects.
- Atomically persist draft/ticket version/receipt/audit/outbox under existing locks.
- Old ticket/note event envelopes and frontend protected intents remain unchanged.
- No dependency/ISA change; no per-slice target connection or production action.

### Task1 Persisted authorized API and event ownership

Files: models.py, ticket_schemas.py, tickets.py, ticket_api.py, activity.py,
provision.py, migration00021, tests/test_ticket_messages.py.
Interface: message DTO/list/detail/create and can_add_message; message_drafted
strict public metadata while note_access remains independent.

- [x] Write/run actual PostgreSQL/API RED for missing routes, then scope/current
  assignment, linked parent denial, protected replay, version/event failure,
  private-note independence, pagination/cursor and immutable SQL/migration tests.
- [x] Implement owning contracts/model/migration/privileges and reuse ticket locks,
  helpers and exact event validation. No draft transport or clock side effects.
- [x] Run focused API/domain/static/contracts/build checks and commit coherent source.

### Task2 Real browser response composer and recovery

Files: apps/web/src/components/tickets/messages.tsx, detail.tsx, lib/tickets.ts,
generated API types, browser tests and existing ticket surface context.
Interface: separate public draft section with reviewed original body/key/version,
receipt/refresh recovery, escaped persisted pages and clear unsent state.

- [x] Read incumbent UI/Impeccable context and craft floor before UI edits. Keep
  private notes isolated; no visual redesign or inactive send controls.
- [x] Implement real API reads/writes and errors/loading/empty/read-only states.
  Add actual browser persistence/uncertainty/ACL/keyboard/axe/light/dark/mobile proof.
- [x] Use required Impeccable review/document workflow and fix scored defects;
  run frontend checks, generated-contract comparison and package proof additions.

### Task3 Acceptance and immediate continuation

- [x] Obtain one fresh whole-increment source review; fix Important findings
  with RED/GREEN and full affected suite. Preserve minor dispositions explicitly.
- [ ] Publish checked commits to main; inspect all five exact-source gates/full
  logs, packaged restart/privacy and complete security/image inventories.
- [ ] Preserve sanitized hashed evidence, close docs, verify remote/clean tree.
  Update the continuous completion ledger and start verified outbound work next.
