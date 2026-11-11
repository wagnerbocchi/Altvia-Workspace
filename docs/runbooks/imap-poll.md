# Restricted read-only IMAPS quarantine poll

ADR-0031 adds one finite owner-only poll. Development uses controlled loopback
TLS only. Real mailbox use/import needs separate operational authorization.
This command supplies no verified sender, ticket promotion, MIME display,
attachment extraction or SMTP response.

## Configuration and execution

Apply migration b46087000018 with the existing owner. API/worker roles have no
poll-state/raw-table privileges. Supply ALTVIA_DATABASE_URL, ALTVIA_IMAP_HOST,
ALTVIA_IMAP_USERNAME and ALTVIA_IMAP_PASSWORD through protected secret files or
environment injection, outside Git and command history. Optional settings are
ALTVIA_IMAP_PORT (default 993) and ALTVIA_IMAP_CA_FILE for an approved private CA.
Certificate/hostname verification and implicit TLS are mandatory, without a
plaintext/STARTTLS fallback. Only INBOX and printable ASCII login values are
supported initially; actual provider/authentication policy remains Q-03/Q-16.

Register the reviewed source using ADR-0030 first. In the owner environment,
only with separately authorized mailbox access:

```bash
export ALTVIA_ALLOW_IMAP_POLL=1
python -m altvia.imap_poll --source-key reviewed-source
```

Never put passwords, hostnames, message content or recipients in arguments.
EXAMINE/BODY.PEEK[] neither mark Seen nor STORE/delete/EXPUNGE. Output contains
source/UID/counter metadata only. A failure prints fixed safe text; earlier
committed entries remain preserved. Retry the same source after lost output.

## Namespace, resume and limits

The namespace hashes canonical host/port/exact username/INBOX after successful
TLS login/selection. First failed authentication cannot bind it. Password rotation
preserves identity; endpoint/account changes require a reviewed new source/resync.
No connection identity or header proves a customer participant.

A 120-second lease and token/expiry checks fence every state write. Late callers
cannot advance/rewind progress or release a newer lease. Crash recovery may wait
for expiry. Do not clear tokens manually. Network I/O holds no DB transaction.

Each poll scans at most 1000 UID positions and fetches 25 messages, bounded by
observed UIDNEXT-1. Partial batches resume after the last durable capture. Gaps
advance only after a valid epoch-checked SEARCH. Missing/malformed/oversize FETCH
stops without skipping that UID; fresh SEARCH may establish its later absence.
Changed UIDVALIDITY resets progress with audit and retains every old receipt.
Body equality never deduplicates across epochs or sources.

Raw literals are limited to 2 MiB and lines to 16384 bytes. Aggregate control
responses allow 65536 bytes/no literals; FETCH permits one literal and at most
2097152+32768 response bytes before imaplib can retain unsolicited data. Epoch
validation follows SEARCH, including empty results, and every FETCH. Non-literal
metadata also has a 65536-byte total poll budget across commands. Socket operations
use 10 seconds; wire reads/writes share a 90-second monotonic budget.
DNS uses the platform resolver; expired tokens still reject late writes. Actual
production traffic/size/storage bounds need Q-21 approval.

## Recovery and validation

Capture/collision/replay, checkpoint, source version and private audit/outbox
commit atomically. Their consumer produces no shared activity or identity grant.
Never edit raw variants, remap namespaces, rewind progress or delete history.
Q-09 retention remains open; no purge job is introduced. Application rollback
preserves expanded state and a compatible private event consumer. Downgrade
refuses poll rows or durable checkpoint history. Back up raw receipts together
with PostgreSQL cursors/namespaces and prove isolated restore before production.

Validation uses actual controlled TLS, disposable PostgreSQL, malicious frame/
epoch/partial failure tests, lease fencing, runtime denial, SQL/migration checks,
actual command output and rebuilt packaged persistence. All five hosted gates
remain required. Actual x86-64-v1 qualification follows remaining MVP development.
