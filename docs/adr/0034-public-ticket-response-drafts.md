# ADR-0034 Public response drafts separated from private ticket notes

Date2026-11-11. FR006/007/012, Service Desk conversation increment. Master spec
reread completely; ADR0004/0005/0028/0029/0033 apply. The user authorizes continued
MVP development/direct main publication; no live mailbox or production deployment.

## Decision and authority

Add a persisted public-response draft collection to ticket detail. Keep the
private ticket_notes structure and explicit note_access unchanged. Drafts are
clearly unsent, never mutate ticket status/assignment/resolution/first response,
never imply verified requester and cannot create outbound delivery in this slice.
SMTP queueing and trusted incoming correlation follow their explicit contracts
immediately in the remaining completion sequence; do not declare native email done.

Read requires existing ticket visibility: current queue role plus explicit client
ceiling, including for platform administrators. Draft content is shared with those
authorized internal ticket readers; no external portal access exists. Write uses
existing ticket contribution authority: operations_manager or currently assigned
agent, with active client/team/queue and an editable non-closed ticket. Note_access
does not grant public response writing; message authority does not grant notes.

Reuse identity-before-auth, ordered parent/ticket locks, reviewed If-Match,
protected Idempotency-Key and atomic ticket-version/receipt/audit/outbox. Current
authority and valid protocol precede replay; a committed receipt returns IDs
after later closure/archive while authority persists. New effects check version
and current write eligibility. New request keys with identical text create new
drafts. No body, subject, email or recipient appears in audit/outbox/logs/activity.

## Storage and HTTP

Migration b46087000021 adds append-only ticket_messages: UUID, ticket_id, author_id,
body_text1..10000, ticket_version>1, created_at, fixed visibility public and
direction outbound. The read projection reports delivery_status draft; transport
state belongs to the later delivery aggregate, not a redundant immutable column.
RESTRICT parent/author FKs, unique
ticket/version, SQL text/state checks and immutable update/delete trigger. Future
transport will use a separate explicit delivery aggregate, not a private-note
conversion or implicit send. API role SELECT/INSERT only; worker no message grant.

- GET /api/v1/tickets/{id}/messages returns items/next_cursor ascending by ticket
  version, limit1..100/default50. Cursor binds actor/ticket; no unscoped lookup.
- GET /tickets/{id}/messages/{message_id} requires matching ticket ownership and
  normal read scope, returning404 for absent/hidden/mismatched parent.
- POST /tickets/{id}/messages accepts strict body_text only, If-Match and
  Idempotency-Key; minimal ticket_id/message_id, 201 fresh or200 protected replay.
- Ticket output adds can_add_message based on current authority/active state.
- ticket.message_drafted has actor/ticket/client/queue/message IDs only. Extend
  strict ticket event validation, preserving all existing event field sets. This
  public draft event is visible to current ticket readers, unlike private notes.

Reuse428 missing protocol,422 malformed input/query,409 stale/closed/inactive and
403/404 scope errors. No update/delete/send route, no caller-selected visibility,
recipient, From, thread token or transport status. Render escaped plain text.

## Browser, alternatives and acceptance

Use the incumbent ticket-detail Operate layout and Impeccable. Add a separate
Respostas section, chronological bounded pages, clear Rascunho - nao enviado
state, plain multiline editor and explicit review before saving. Preserve original
body/key/version through uncertain responses, failed reads and focus refresh.
Keep acknowledged IDs while awaiting authoritative refresh; refresh before the
next write. Conflict recovery is explicit. Private notes stay in their own labeled
component and must never be prefilled/copied into a public composer automatically.

A single notes/messages table would require privacy transitions and risks note
delivery; separate public draft ownership makes that impossible by construction.
Immutable saved drafts cost a new draft for revised text; deletion/retention and
send/cancel transitions need later explicit contracts rather than guessed behavior.

Downgrade locks messages/tickets/audit/outbox/activity and refuses message or
drafted history. Rollback keeps expansion and compatible event handling. No new
dependency/image/ISA requirement. Prove real PostgreSQL/API scope and write
negatives, replay/race/session revocation, SQL/migration/provisioning, metadata-only
events/private-note independence, browser uncertainty/refresh/accessibility and
actual packaged persistence. Keep full email/MVP/target qualification separate.
