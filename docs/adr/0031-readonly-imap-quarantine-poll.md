# ADR-0031 Read-only IMAPS quarantine polling and fenced checkpoints

Date 2026-11-11. Phase 3E-b, FR-007/012. Master specification previously read in
full; ADR-0004/0005/0030 apply. Standing authorization covers development and
direct main publication, not live mailbox use, real import or deployment.

## Decision

Extend the owner-only quarantine boundary with one finite IMAPS poll command.
Use Python imaplib/ssl, verified certificates/hostname and implicit TLS; no
plaintext fallback, STARTTLS downgrade, HTTP route or runtime privilege grant.
Connect only to the operator's external configuration. Tests connect exclusively
to controlled loopback TLS fixtures. Real provider policy remains Q-03/Q-16.

The first connector selects INBOX with EXAMINE/read-only and fetches BODY.PEEK[].
It never STOREs flags, marks Seen, deletes, EXPUNGEs or acknowledges by changing
the server. Raw bytes still go to ADR-0030 quarantine, with no MIME display,
customer/participant proof, correlation, ticket promotion or SMTP side effect.

Settings inherit DatabaseSettings: imap_host (bounded ASCII DNS name/IP), port
1..65535/default993, secret username/password (bounded printable ASCII), optional
imap_ca_file. Secrets use existing protected environment/secret files, never CLI
arguments or logs. Quote LOGIN fields safely. CLI requires explicit
ALTVIA_ALLOW_IMAP_POLL=1 and --source-key only. Output source/UID/counter metadata;
all argument/config/protocol/TLS/database errors use a fixed safe diagnostic.

## Namespace, leases and persistence

Migration b46087000018 adds owner-only mailbox_poll_states: source PK/RESTRICT FK,
nullable namespace SHA256/UIDVALIDITY, last_uid0..4294967295 and paired lease
token/until. SQL enforces initialized-field consistency and immutable namespace.
Namespace hashes canonical host/port/exact username/INBOX, excluding password.
Bind only after authenticated TLS selection yields valid UIDVALIDITY and UIDNEXT.
A failed first login/certificate check cannot permanently bind the source.
Once bound, endpoint/account changes require a new reviewed source; password
rotation preserves its namespace. No credential or hostname is stored in events.

Acquire a source-serialized 120-second operational lease before connecting.
Network I/O occurs outside database transactions. A token and current expiry
fence every checkpoint/reset/capture transaction. Late old polls cannot advance,
rewind or release a replacement lease. Always release the caller's own token in
finally. A crashed process is recoverable after expiry without changing raw data.
Use a 90-second monotonic wire read/write budget and 10-second socket operations;
DNS remains subject to the platform resolver. Expired leases fail closed even
when a platform connection operation outlasts its normal timeout.

Strictly parse uint32 UIDVALIDITY/UIDNEXT. On a changed UIDVALIDITY, atomically
reset last_uid to0 and record the epoch change; preserve all previous raw variants.
No content/Message-ID deduplication across epochs. Do not silently rewind a cursor
when UIDNEXT contradicts its current epoch. Session epoch changes stop the poll.

## Bounded scan and atomic progress

Scan at most one UID window of 1000 positions per command, ending no later than
the selected UIDNEXT-1. Fetch at most25 returned UIDs. Validate SEARCH identities
as distinct uint32s inside that exact range. Filter no reversed star range: use
explicit numeric endpoints. Fixed bounds remain provisional under Q-21.

For each FETCH require exactly one bounded literal and the requested UID, allowing
UID before/after BODY[] metadata. Reject extra/missing fields, mismatched identity,
oversize/truncated literals, malformed lines and unexpected responses. Enforce the
2 MiB raw limit before imaplib allocates/reads the literal, not from a trusted
RFC822.SIZE claim. Bound wire lines to16384 bytes and buffered reads as well.
Cap aggregate control responses at65536 bytes with no literals; FETCH permits one
literal and at most2097152+32768 total response bytes. Enforce these budgets in
the wire reader before imaplib retains unsolicited frames. Check session epoch
immediately after SEARCH, including empty results, and after each FETCH.

Capture raw receipt and advance its checkpoint in one transaction, reusing the
existing source lock, replay/collision rules and audit/outbox owner. A failure
preserves earlier committed messages but never skips the failed UID. If every UID
returned for a window is durably captured, a separate audited scan checkpoint may
advance over proven absent UID positions up to that window's UIDNEXT-bound end.
If a searched UID vanishes before FETCH, stop; a later fresh SEARCH can establish
the gap. If more than25 UIDs were returned, retain the last captured UID so the
remaining messages are scanned next time. No network action occurs inside these
transactions. A lost completion output is safe to resume from the durable cursor.

Private mailbox.poll_checkpointed metadata contains source ID, canonical decimal
UIDVALIDITY/last_uid and reason initial|epoch_changed|message_captured|range_scanned.
Source aggregate version advances with actual checkpoint changes. Old intake
event envelopes remain byte-shape compatible; the existing strict consumer
acknowledges new metadata without shared activity or raw-table SELECT.

## Alternatives, costs and acceptance

Read-only finite polling is selected before scheduling/OAuth/folder routing;
provider-specific operations remain subsequent configuration work. Namespace
binding prevents silent mailbox remapping; legitimate endpoint migration costs
a reviewed new source/resync. Leases plus fencing avoid holding DB locks over
remote I/O; crash recovery may wait120 seconds. Bounded raw/window/batch handling
limits resource use; production sizing needs Q-21 approval. UID resets preserve
separate quarantine data rather than guessing deduplication; later verified
promotion must reconcile it without silently deleting receipts.

Downgrade locks poll/source/audit/outbox tables and refuses poll rows or durable
checkpoint history. Application rollback retains expansion and compatible private
event consumption. No dependency, image pin or ISA requirement changes. Actual
target qualification remains deferred until MVP development is complete.

Prove actual local TLS protocol, certificate/hostname/auth failure, read-only/PEEK,
binary persistence, resume, gaps/batches, UID reset/namespace/password rotation,
literal/line/UID bounds, partial failure, event rollback, expired-token fencing,
no DB locks during network reads, runtime denial, strict private events and
guarded migration. Complete independent source review and exact-source hosted
API/browser/container/security gates, with synthetic packaged persistence proof.
No frontend is introduced; full native email and Phase3/MVP acceptance remain open.
