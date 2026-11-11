# Private ticket notes

ADR-0029 defines the private-note contracts. Apply migration b46087000016 with
owner credentials, then run the existing runtime provisioner. The API receives
SELECT/INSERT on ticket_notes; the worker receives no note-table privilege.
The expanded schema and strict event consumer must precede note-enabled writes.

## Delegate and operate

Every old or new queue binding starts with note_access none unless explicitly
configured. Queue configuration managers use Service Desk > Filas > Membros.
Select an existing account, review its queue role and independent note tier, then
save. Tiers are no access, read, or write including read. Only agent and queue
operations_manager roles may receive read/write. Viewer downgrade and removal
clear note access. Target sessions end on actual permission changes.

Customer ceilings and queue roles remain required. Configuration, platform,
team, client and project administration do not bypass the boundary. Real business
delegations remain Q-20; synthetic test grants are not operational defaults.
Permission-only reductions remain available on archived parents/inactive targets.
Role changes and increased permission require active references.

Open an authorized ticket to read chronological pages of Notas internas. With
explicit write permission and editable active ticket parents, compose plain text
under Registrar nota interna. The warning identifies internal-only content and
immutable storage. No recipient, delivery, outbound mail, edit or delete exists.
Closed tickets require reopening. Notes do not change lifecycle or SLA timestamps.
Bodies remain outside inbox full-text search and event metadata. Denied callers
receive no note fetch, ID, count or private activity event.

## Recovery and preservation

The browser captures the ticket version when drafting starts. Background refresh
does not replace that reviewed version. An uncertain POST retains the exact
body, Idempotency-Key and If-Match; use Verificar nota interna. Do not create a
new key to resolve an uncertain result. Current permission precedes replay.

After acknowledgement the browser retains the note ID and blocks every ticket
mutation until authoritative ticket, note and active note-page reads succeed.
Use Atualizar chamado after a read failure. A stale conflict offers deliberate
reload/discard. Read-only note pages offer their own retry and bounded paging.

Application rollback preserves schema expansion and compatible event handling.
Schema downgrade refuses durable notes, note permissions, private events or
note-permission history. Never discard these records to force contraction.

## Validation

Run real disposable PostgreSQL tests, rebuilt HTTPS browser tests and existing
static/generated-contract gates. The packaged smoke proves default queue-manager
denial, explicit delegation, session invalidation, protected replay and note
persistence after API/PostgreSQL recreation. A separate ordinary ticket reader
then reads the ticket but receives denial on both populated note routes; paged
activity excludes private events. Owner-side metadata inspection verifies
redaction and absence of outbound events without widening runtime privileges.
Five exact-source hosted workflows
and complete image inventories remain the publication evidence. Actual x86-64-v1
qualification occurs after remaining MVP development under the user's cadence.
