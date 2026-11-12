# ADR-0035 Verified public response delivery

Date2026-11-11. Selected engineering design for FR006/007/012 in the continuous
MVP sequence. ADR0004/0005/0022/0028/0034 and the master specification apply.
Provider, organizational identity evidence and forwarding policy remain Q03/Q16.
Only synthetic controlled-provider testing is authorized here; this document
does not authorize real verification, sending, provider setup or deployment.

## Ownership and alternatives

Keep immutable public ticket_messages. A separate outbound_messages aggregate
owns one explicit delivery per public message, with frozen envelope, MIME bytes,
stable Message-ID and transport state. Private ticket_notes have no conversion,
foreign-key or delivery path. Reusing an unsent public draft avoids a second body
editor, another public-content owner and accidental private-note copying.

Do not infer verification from contact presence, From/Reply-To, matching domains,
an existing session or a queue role. A restricted owner command records an
operator-attested, ticket-bound requester participant after outside identity
checks. This is explicit recorded attestation, not a claim of cryptographic
verification. An authenticated internal agent can select that active attestation
but cannot create or upgrade it. Real evidence policy must be approved before
production. An email challenge service is unnecessary without that policy and
would itself require outbound trust and abuse decisions.

Reuse the existing Python worker, durable SQL leases and private Redis. A mail
actor consumes only a delivery ID. The activity actor continues its existing
metadata projection; shared activity is never a queue of raw bodies or addresses.
The mail actor receives no raw quarantine, MIME preview or private-note grant.
Use Python's standard email/smtplib/ssl libraries; no new native dependency or
mandatory service, no higher ISA, no per-slice target qualification.

## Trusted configuration and recipients

Owner-managed mailbox sender registration binds an existing mailbox_sources
source and its immutable queue to a validated ASCII From mailbox and SMTP
namespace hash. Namespace includes configured host/port/TLS mode/username/From;
password rotation preserves it. Credentials remain external secret settings.
An owner-selected configuration file contains a bounded mapping of sources to
those settings; an API caller cannot supply hosts, URLs, credentials, headers,
arbitrary envelopes or filesystem paths. Absent/mismatched configuration cannot
claim a delivery or open a connection. Both implicit TLS and mandatory STARTTLS
verify hostname and certificate; authentication and DATA never precede TLS.
The MVP has one registered sender per queue and one active attested requester
per ticket. Choices return those two optional records and can_send, rather than
an unpageable growing directory. Source configurations are bounded to16 entries
and64 KiB; larger deployments require an explicit capacity revision.

ticket_participants stores immutable ticket/contact/email/evidence identity,
operator attestation time, active flag and positive version. This initial
boundary permits only that ticket's current requester contact and exact current
ASCII normalized email. It grants no account, portal, client, queue or note access.
Revocation is explicit, versioned and audit-only. Never overwrite old evidence or
an email snapshot; changed contacts require a new attestation. Lock identity,
client/team/queue, ticket and contact consistently. Reject inactive parents/contact,
cross-client contact, mismatched requester or stale reviewed ticket versions.

Normal ticket readers can read eligible sender/participant choices only through
their currently authorized ticket. An archived contact, changed mailbox, revoked
participant or inactive ancestor is ineligible for a new send. Worker eligibility
is rechecked before DATA; a revocation racing an already transmitting message
cannot retract mail and must never be represented as successful cancellation.

## Queueing and HTTP

GET /api/v1/tickets/{id}/delivery-choices returns bounded eligible sender and
verified requester metadata under current ticket scope. No configuration secret,
attestation evidence reference, raw mail or private note is returned.

POST /tickets/{id}/messages/{message_id}/delivery accepts only participant_id and
source_id, current reviewed If-Match and protected Idempotency-Key. Require the
same manager/currently-assigned-agent authority as public drafting, current
queue/client read scope and valid protocol before saved replay. Fresh effects
require active editable parents, a public message belonging to this ticket,
eligible requester/sender and reviewed version. Atomically save the delivery,
ticket version, minimal receipt, audit and metadata-only event. A different key
cannot create another delivery for the same public message. A known delivery is
not silently resent. Return minimal ticket_id/message_id/delivery_id, 201 fresh
or200 protected replay. Missing protocol428, malformed422, stale/ineligible or
existing conflicting delivery409, action denied403, hidden/mismatched resource404.

GET /tickets/{id}/messages/{message_id}/delivery returns current status, attempts,
fixed safe error code, stable Message-ID and accepted_at when present, after
checking both parents and current ticket scope. It never returns wire bytes,
credentials, evidence or raw SMTP diagnostics. Message list/detail delivery_status
joins its delivery aggregate, defaulting to draft for historical unsent messages.
Old public-draft/private-note event envelopes and idempotency fingerprints remain
unchanged. Delivery creates neither a ticket transition nor an SLA success.

## Durable sending and uncertainty

States are queued, preparing, transmitting, accepted, failed and uncertain.
Persist a finite unguessable attempt lease before network I/O. All attempt
updates compare the current token and expiry. Network I/O never runs inside a
database transaction. Freeze bytes once: bounded plain-text MIME, no HTML or
attachments in this increment, no caller-supplied From/Reply-To/References.
Generate one stable Message-ID under the configured sender domain. Preserve
existing accepted thread references with finite bounds. A private random ticket
thread token is never an API field or an identity proof on its own.

Connect/EHLO/TLS/auth/MAIL/RCPT failures before DATA cannot deliver a message.
Classify definitive 4xx for bounded backoff and 5xx for terminal failure; never
log server response text. Mark transmitting durably under the live lease before
DATA. An explicit final250 records accepted, not recipient delivery. A definitive
DATA rejection can safely fail/retry according to its status class. Connection
loss, timeout, process crash or unknown result after entering DATA means uncertain.
Expired preparing attempts can be retried; expired transmitting attempts become
uncertain and never automatically requeue. Stable Message-ID does not prove
provider deduplication or exactly-once delivery.

Use bounded reply lines, total wire bytes, per-socket timeout and total attempt
deadline. Limit retries to8 with increasing delay capped at1 hour. Retry exhaustion
is visible failed state. Never put credentials, MIME, addresses or free-form
provider text in logs, audit, outbox, Redis messages or activity. Only fixed error
codes and identifiers cross those boundaries.

Uncertain reconciliation is owner-only, with reviewed delivery version and
recorded external evidence. Drain relevant mail workers before deciding, and
verify provider acceptance using the stable Message-ID. An explicit accepted
decision records accepted_at; explicit confirmed non-acceptance may requeue the
same immutable delivery. Never present a general retry button for uncertain mail.
The operator must account for in-flight SMTP, which SQL fencing cannot retract.

## Browser, events and acceptance

Use Impeccable and the incumbent ticket Operate layout. Each eligible unsent public
draft offers an explicit send review with its exact saved text, recipient and
sender, separate from private notes. Require deliberate confirmation; retain the
original message/recipient/source/key/version across uncertain HTTP results and
ownership changes. Read actual delivery status after acknowledgement before a
new action. Accepted means Aceito pelo servidor de e-mail, never Entregue.
Show waiting, failure and uncertain reconciliation clearly without inert controls.

Queueing emits ticket.delivery_queued with actor/ticket/client/queue/message/
delivery IDs. Attempt transitions emit strict delivery metadata including state,
safe error code and accepted_at when applicable. They carry no body, address,
participant evidence, provider reply or token. Activity retains ordinary ticket
authorization and does not alter private-note filtering. Accepted events form
future SLA evidence; queueing/drafting/reconciliation without acceptance do not.

Prove real PostgreSQL/API cross-scope denial, review/replay/races/atomic rollback,
participant revocation/contact change, unique delivery and exact old envelopes.
Use a controlled local TLS SMTP server to prove actual MIME/envelope, TLS failure,
auth failure, 4xx/5xx, connection loss before/after DATA, final250 loss, lease
expiry/fencing, restart, bounded malicious replies and owner reconciliation.
Prove private-note non-delivery, real browser review/status/recovery/ACL/axe/themes
and packaged persistence. Run full local/hosted/security gates; final integrated
actual-target qualification remains after MVP development.

New tables/constraints are additive. Runtime grants are explicit: API may read
eligible metadata and insert a delivery; activity/mail worker may read public
delivery/recipient eligibility and update only owned attempt-state columns.
Neither runtime role gets owner attestation writes, sender configuration writes,
raw/MIME-preview or note-reading grants. Preserve immutable snapshots with SQL
guards. Downgrade refuses delivery/participant/sender or corresponding durable
history. Stop/drain senders on application rollback; keep compatible expanded
state/event readers. Do not drop queued or uncertain mail to force contraction.
