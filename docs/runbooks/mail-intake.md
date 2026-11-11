# Restricted native mail quarantine intake

ADR-0030 implements a bounded owner-side capture ledger, not a live IMAP/SMTP
connector. Use synthetic mail for development. Real imports and provider access
still need their operational authorization and Q-03/Q-16 policy decisions.

Apply migration b46087000017 with the existing migration owner. Provisioning keeps
API and worker roles without privileges on mailbox_sources, inbound_mail_envelopes
and inbound_mail_variants. No application role, customer ceiling, contact identity
or shared activity audience is granted by registering a source.

## Register a source and capture

Run inside the existing owner/migration environment, where DatabaseSettings reads
the protected database secret. Do not place a database URL/password in commands,
mail content in arguments, or source/raw files in Git. Set QUEUE_ID to a reviewed
existing active queue UUID. The immutable source key identifies one mailbox/UID
namespace; never reuse it for a different mailbox or silently change its queue.

```bash
export ALTVIA_ALLOW_MAIL_INTAKE=1
python -m altvia.mail_intake register-source --source-key synthetic-support --queue-id "$QUEUE_ID"
python -m altvia.mail_intake capture --source-key synthetic-support --uid-validity 1 --uid 1 < synthetic.eml
```

Registration prints the source ID. Capture prints only source/envelope/variant
IDs, current quarantine/collision state and replayed. The receipt is printed after
transaction commit. No sender, subject, header, raw bytes, hash or connection
details are printed. An error returns nonzero with a generic safe diagnostic.
An uncertain/lost receipt is recovered by the same source/UIDVALIDITY/UID/bytes;
never assign a new UID to manufacture a successful retry.

Raw stdin is read as bytes, maximum 2097152 bytes plus one overflow sentinel.
Empty/oversize input and invalid uint32 UID identities are refused without an
acknowledgement. At most 16 different raw variants fit one identity. These are
provisional engineering bounds under Q-21, not provider throughput promises.

## Preservation and identity

Every input, including malformed bytes, remains opaque in private PostgreSQL
storage. There is no MIME parser, rendered HTML, extracted file, message-to-ticket
promotion, outbound delivery or mailbox checkpoint advancement in this increment.
Queue archive does not prevent preserving input for an already registered source.

An identical identity and identical bytes replay existing IDs without another
audit/event/version. Different bytes on that identity retain both variants and
permanently mark collision. Replaying the original afterward also returns
collision. Identical bytes under another UID/UIDVALIDITY/source remain distinct.
Do not use From, Reply-To, subject, Message-ID or body equality as identity proof.
Quarantine and collision never authorize delivery, customer association or reads.

Audit/outbox contain strict IDs/state only. Their consumer acknowledges them
without any shared activity record. Raw rows are invisible to API/worker roles.
Only an owner with separately authorized operational access can inspect storage;
there is no triage browser/API or inferred platform-administrator content grant.

## Recovery, migration and validation

PostgreSQL commits source version, envelope, immutable variant, audit and outbox
atomically. Failure/overflow rolls everything back. Keep source identity and
variant bytes unchanged. Do not delete, edit or manually clear collisions.
No cleanup/retention job is introduced while Q-09 remains unresolved.

Application rollback preserves the expanded schema and a consumer that recognizes
the private event envelopes. Schema downgrade refuses sources, receipts or durable
intake history. Backups must preserve this private raw data with PostgreSQL; later
object-storage migration requires a compatible manifest and restore proof.

Validation uses disposable PostgreSQL, real CLI binary stdin and synthetic
packaged restart/replay. Full API/worker/privilege regressions and all five hosted
gates remain required. Native IMAP polling, MIME validation, verified promotion,
public response/SMTP and target qualification after MVP development remain open.
