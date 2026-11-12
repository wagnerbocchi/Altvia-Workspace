# Public response drafts

ADR-0034 adds shared, unsent plain-text response drafts to the existing ticket
detail. It does not send mail, verify contacts, convert private notes or change
ticket state, assignment, first-response time or SLA. Native delivery follows
its separate verified-recipient and SMTP contracts.

## Use and recovery

Current ticket readers need both their queue role and explicit client ceiling.
An operations manager or currently assigned agent can prepare and save a draft
while the ticket and its parents are eligible. Private note delegation remains
independent. Read-only ticket readers can read public drafts without note access.

Open the ticket, enter text in Preparar resposta, then choose Revisar rascunho.
Review the exact text before Salvar rascunho. Saved responses are immutable and
visibly marked Rascunho - nao enviado. Editing saved text requires a new draft.
No external participant receives anything from these controls.

If the save cannot be confirmed, use Verificar rascunho. The browser reuses the
original text, reviewed ticket version and request key. Do not navigate away if
you need to retain this in-memory intent. Acknowledged saves remain locked until
the authoritative ticket, message receipt and visible message page can be read.
Atualizar chamado retries those reads without creating another draft.

If reassignment removes write authority, the same authenticated reader retains
the original review, disabled, with an explicit access error. Verificar rascunho
still rechecks the original request against current server authority. Once
assignment is restored, a previously committed request returns its old receipt;
an uncommitted request with a stale version conflicts. Recarregar e descartar
edicao explicitly clears the retained intent after a successful current read.
It does not delete a draft already saved on the server.

Actual logout, expired/revoked session or rejected CSRF ends local private state.
The browser never carries text or request keys into another authenticated session.
Losing ticket read scope hides its content; resource permission denial is not a
grant and never bypasses the server's present authorization check.

## HTTP and storage

GET /api/v1/tickets/{id}/messages pages oldest first by ticket version, with
limit1..100/default50 and a cursor bound to the caller and ticket. Detail lookup
also binds message ID to that ticket. POST accepts only body_text, 1..10000 code
points, If-Match and Idempotency-Key. It returns ticket_id/message_id, 201 for a
new draft and 200 for a committed authorized replay. Missing protocol is428;
invalid input422; stale/closed/inactive409; forbidden403; hidden resources404.

Migration b46087000021 preserves immutable public messages separately from
private ticket_notes. The API gets SELECT/INSERT only; the activity worker gets
no table privilege. Ticket version, receipt, audit and metadata-only outbox event
commit atomically. Bodies and addresses never enter those events or request logs.
The delivery_status read projection is draft until an explicit transport
aggregate owns delivery state. There is no edit, delete or send route here.

## Verification and rollback

Use the guarded local browser procedure in browser-development.md and the real
PostgreSQL tests in apps/api/tests/test_ticket_messages.py. The focused browser
selection is `--grep '@messages|@notes'`. Complete browser gates also cover the
shared permission/session transport. The packaged smoke adds a separate ticket,
append/replay and restart/read-only/no-note-grant checks without altering old
private-note fixture versions.

Keep the expanded schema and compatible ticket.message_drafted consumer during
application rollback. Downgrade refuses populated messages or durable drafted
history. Do not delete records or history to force contraction. New images still
require final integrated x86-64-v1 qualification; existing image proof does not
qualify a newly built artifact. No production operation is implied.
