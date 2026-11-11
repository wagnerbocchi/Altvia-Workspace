# ADR-0029 Private ticket notes and explicit queue note access

Date 2026-11-11. Selected before implementation for Phase 3D, FR-006/012.
The fully read master specification, ADR-0004/0005/0027/0028 and user authorization
apply. Consolidated target qualification follows remaining MVP development.

## Decision and authority

Deliver internal notes as a complete persisted browser workflow. Public replies,
transport, files and requester verification retain their subsequent contracts.
Internal notes use their own append-only ticket_notes table. Its fixed private
representation has no recipient, transport or delivery fields. This implements
ADR-0005's structural privacy boundary and avoids premature customer delivery.

Extend the existing queue binding with explicit note_access none|read|write,
default none. Write includes read. Only agent/operations_manager queue bindings
may hold read/write. Viewer and every other binding scope require none. Every
note action also requires current ticket scope and customer ceiling. Assignment
and configuration/team/client/project roles confer no note access. This extends
the owning membership representation instead of adding an overlapping grant ledger.

Configuration managers delegate note access through existing reviewed member
POST/PATCH. Reuse identity-before-auth, team/queue/target locks, target FOR NO KEY
UPDATE, session invalidation, queue/auth versions, protected replay and atomic
redacted event protocol. Note grants add no customer ceiling or content role.
Queue operations_manager alone cannot delegate. Downgrade to viewer/removal
revokes note access atomically. Explicit incompatible viewer grants return422.
Permission-only reductions stay available on inactive accounts/parents. New
permissions and role changes retain ADR-0027's active-reference requirements.

Legacy role-only POST/PATCH preserves existing compatible writer note access.
New bindings default none. Omitted note_access remains omitted from the POST
fingerprint to preserve Phase3B receipts. Explicit none deliberately clears it.
Reject explicit null. Current configuration authority and valid If-Match precede
saved replay. Committed replay returns IDs and never restores permission.

## Persistence, privacy and effects

Persist UUID, ticket_id, author_id, body_text1..10000, ticket_version>1 and UTC
created_at. Strip Unicode whitespace and reject NUL. Store/render plain multiline
text. SQL rejects whitespace-only/oversize bodies, RESTRICT FKs retain parent and
author, unique ticket/version orders notes deterministically. Reuse immutable
audit mutation rejection for SQL UPDATE/DELETE. Inactive author labels remain
readable. API receives SELECT/INSERT; worker receives no note table grant.

Note reads require read/write and append requires write, independently of current
assignment. Readable tickets with denied notes return403. Hidden/absent tickets
and mismatched note parents return404. Every request rechecks current grants.
Actual writes require active customer/team/queue and an editable ticket under
ADR-0028. Closed tickets need reopen. Current write authority and valid protocol
precede replay. Committed receipts survive later archive/closure while authority
persists. A note advances ticket version once and commits note/receipt/audit/outbox
together. It changes no status, assignment, response or resolution timestamps/SLA.
Overflow/event failure rolls back all effects. Fresh repeated text is a new note.

Ticket output adds can_read_notes/can_add_note. Exclude note bodies from ticket
description, inbox FTS, errors and logs. Filter ticket.note_added activity before
pagination unless current note access permits read. Denied callers receive no
note count, ID or event type. Ticket version gaps identify unclassified mutations.
Preserve the existing actor/ticket activity cursor format and prior event shapes.

## HTTP and events

- GET /api/v1/tickets/{id}/notes returns items/next_cursor ordered ascending
  ticket_version, limit1..100/default50, unique limit/cursor parameters and cursor
  bound to actor/ticket. Reuse the bounded version cursor parser from state
  history while preserving its existing wire values.
- GET /tickets/{id}/notes/{note_id} checks parent scope/note permission before
  resolving a matching note. It offers no cross-ticket lookup.
- POST /tickets/{id}/notes accepts strict {body_text}, reviewed Ticket If-Match
  and Idempotency-Key. Return minimal {ticket_id,note_id}, 201/new or200/replay.
  Current authority and header syntax precede replay; fresh effects compare version.
- Existing member POST/PATCH optionally accepts note_access. Member output
  includes its non-null value. Existing required role fields retain their shape.
- ticket.note_added carries actor/ticket/client/queue/note IDs under the ticket
  aggregate. Strict shape forbids body, assignment and transition fields.
- ticket_queue.access_changed optionally carries note_access when it changes.
  Old envelopes remain valid. Viewer/removed cannot carry read/write.

Missing precondition/key428, malformed input/query/header422, stale409 and actual
inactive/closed writes409 reuse existing errors. No note update/delete route exists.

## Browser, rollback and acceptance

Use Impeccable and incumbent Operate composition. Member review/edit captures
role/note_access/version/key and preserves it through uncertainty and failed
parent/list refresh. Existing self-target confirmation/session behavior applies.
Ticket detail mounts note reads only with can_read_notes and composition only
with can_add_note. Keep reviewed body/version/key through focus refetch, response
loss and read failure. Retain acknowledged note ID while authoritative refresh
is pending. Require successful refresh before another write. Conflict recovery
is explicit. Notes remain visibly internal throughout composition and confirmation.

Migration b46087000016 adds default-none capability and private notes, preserving
old bindings/tickets/receipts/events. Downgrade locks affected tables and refuses
notes, permissions, note events or note-access history before contraction.
Application rollback preserves expansion and compatible event consumption.
No dependency or ISA requirement is added. Organizational delegations remain
Q-20 with default none until configured by authorized managers.

Prove default/tier denial, cross-ticket/client/queue bounds, role downgrade/removal,
old fingerprints/envelopes, current authority before replay, archive/closure,
session/logout races, append-only SQL, atomicity/overflow, bounded ordered paging,
activity/FTS exclusion, runtime privileges and guarded migration. Browser proof
includes persistence, uncertain POST, stale/focus review, acknowledged receipt
with failed refresh, role/no-fetch boundaries, keyboard/axe and theme/viewports.
Complete one fresh whole-increment source review, Impeccable review/documentation
and all five exact-source hosted gates with packaged restart/privacy proof.
