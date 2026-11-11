# ADR-0030 Durable native mail quarantine intake

Date 2026-11-11. Phase 3E-a, bounded foundation for FR-007/012. Master specification
read completely; ADR-0004/0005 and the existing development authorization apply.
Real mailbox/provider/verification policy stays Q-03/Q-16. No live connection or
real import is authorized by this increment.

## Decision and boundaries

Implement an owner-only operator intake that durably captures bounded opaque
RFC822 bytes under explicit mailbox source and IMAP UIDVALIDITY/UID. Every captured
message remains quarantined, with no ticket/client/contact/participant association,
MIME rendering, extracted attachments, outbound delivery or checkpoint advancement.
Malformed and hostile bytes are preserved without parsing or executing them.
The next connector/parser increments must use these receipts after commit and
must not infer identity from From, Reply-To, subject or Message-ID.

The source is an immutable routing identity: UUID, unique ASCII key1..64 matching
[A-Za-z0-9_-]+, explicit queue FK, positive version and UTC creation time. Register
only an existing active queue/team. Registration uses the incumbent identity
lock, then team/queue locks. It grants no content authority. Capturing quarantine
does not depend on continued queue activity, so archive cannot silently lose mail.

An envelope has UUID, source FK, positive uint32 UIDVALIDITY and UID, state
quarantine|collision, UTC creation time and unique(source,UIDVALIDITY,UID).
Variants have UUID, envelope FK, raw bytes1..2097152, SHA256, UTC creation time
and unique(envelope,hash). SQL verifies the hash against bytes. Variants are
append-only with RESTRICT references. Maximum 16 distinct variants per identity;
overflow refuses acknowledgement, with no checkpoint effect or silent drop.

Serialize capture on the source row. Equal identity and identical bytes replay
the same IDs without version/audit/outbox duplication. Different bytes retain
both variants and permanently mark the envelope collision. A replay of either
variant still reports collision. Equal content on another UID/source/UIDVALIDITY
is a separate receipt: content or Message-ID alone never establishes duplication.
New variants advance source version and atomically commit receipt/audit/outbox.
Version exhaustion, variant overflow or event failure rolls back every effect.

Raw bytes live in bounded PostgreSQL BYTEA initially, providing one atomic durable
write without filesystem orphans or a new storage binary. Moving larger raw mail
to private object storage later requires a compatible migration and manifest.
Attachments remain a separately scanned/storage-authorized future contract.

## Restricted execution, privacy and events

Provide python -m altvia.mail_intake register-source --source-key KEY --queue-id ID
and capture --source-key KEY --uid-validity N --uid N. Capture reads bounded binary
stdin; never accept message content, credentials or filenames as arguments.
Require ALTVIA_ALLOW_MAIL_INTAKE=1 and owner database credentials. Use existing
DatabaseSettings; errors never print input, connection details or database errors.
Output minimal source/receipt/variant IDs, state and replay status. No HTTP route,
browser surface or permission grant is introduced. API and current worker roles
receive no SELECT/INSERT/UPDATE/DELETE on these three private tables.

mailbox_source.created and mailbox.message_quarantined events use mailbox_source
aggregate and management_command actor, null actor ID. Payload contains source ID
and, for capture, envelope ID/variant ID/state only. No raw bytes, hash, key,
header, address, queue/client label or preview enters audit/outbox/logs. The
existing consumer strictly validates these metadata envelopes, transactionally
acknowledges/deduplicates them and intentionally creates no shared ActivityEvent.
Ordinary identity/team/queue/ticket feeds cannot reveal intake IDs or counts.

## Alternatives, costs and acceptance

Chosen over direct ticket append because sender proof is unresolved; later
verified promotion must integrate these quarantined receipts. Chosen over local
files/S3 for bounded raw intake because PostgreSQL already supplies atomicity;
larger volumes need measured storage migration. Owner-only CLI avoids assigning
unclassified customer mail to platform or queue roles; a later triage UI needs
its own explicit security policy. The fixed 2 MiB/16-variant bounds are provisional
engineering protection, not a production provider promise; Q-21 records review.

Migration b46087000017 expands three tables and append-only triggers. Downgrade
locks them and refuses sources, receipts or durable intake event/audit history.
Application rollback retains expansion and the compatible event consumer. No
dependency or ISA requirement changes. Actual target qualification stays deferred.

Prove capture/replay/collision, UID reset/source isolation, malformed bytes,
limits/hash/immutability/FKs, atomic rollback/overflow, concurrent retry, least
privilege, redacted consumption/no activity, guarded migration and restricted
CLI stdin/error handling on real disposable PostgreSQL. Hosted exact-source
gates and packaged synthetic restart proof precede development completion.
This does not claim working IMAP polling, MIME triage, trusted correlation,
public replies or SMTP delivery; Phase 3 and the MVP remain open.
