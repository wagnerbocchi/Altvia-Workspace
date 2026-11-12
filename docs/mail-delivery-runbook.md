# Optional verified public mail delivery

ADR-0035 owns this boundary. No real provider, requester attestation or production
send has been selected or authorized by these examples. Q03/Q16 remain open.
The default worker has no SMTP account file and continues identity processing.

## Configuration and network

Keep the account JSON outside Git in the restricted external secret directory.
`infra/smtp-accounts.example.json` contains synthetic values only. Replace them
only under the separate provider/identity policy authorization. The worker loads
`ALTVIA_SMTP_ACCOUNTS_FILE` once at startup; restart drained workers after changes.
The file accepts at most16 unique source UUIDs and65536 bytes. Each source binds
an already owner-registered sender. Host, port, TLS mode, username and From must
match that sender's immutable namespace; mismatches do not claim or connect.
Password and CA rotation preserve the namespace and frozen message identity.

Use `implicit` with the provider's implicit TLS port, or `starttls` with mandatory
STARTTLS. Both verify the certificate chain and hostname and require TLS1.2 or
later. STARTTLS requires a fresh EHLO after encryption. Authentication and DATA
never occur before verified TLS. A null `ca_file` uses the system trust store;
a private controlled test CA needs an explicit read-only mount and its container
path in the external account file. Never disable certificate validation.

The optional overlay is selected explicitly with the usual base-stack settings:

```sh
docker compose -f infra/compose.yaml -f infra/compose.smtp.yaml config --quiet
docker compose -f infra/compose.yaml -f infra/compose.smtp.yaml up -d worker
```

These are operator procedures, not authorization to run a provider or deployment.
The overlay gives only the worker an outbound network and read-only account
secret. Database and Redis remain on their private networks. It preserves the
base nonroot user, resource limits, read-only filesystem, secret references and
30-second stop grace. Make the external file readable only by its operator and
the container's UID10001, using the host's supported secret-file permissions;
Compose file-backed secrets do not reliably implement requested UID/GID/mode.
Do not print `compose config` with secret contents, credentials or account JSON.

## Attempt lifecycle and recovery

Queueing a saved public response freezes its MIME, envelope and Message-ID once.
Redis carries delivery UUIDs only. SQL claims the exact due UUID under a finite
120-second lease. The dispatcher publishes at most2 wakeups per10-second global
window and stops at8 outstanding broker messages. Duplicate messages and broker
loss leave SQL authoritative. A matching account is required even for publication.

Each SMTP attempt has an absolute budget of at most60 seconds, with at most5
seconds for each socket operation. Greeting, DNS wait, connect, handshake, AUTH,
multiline replies and DATA all share that deadline. Reply limits are64 lines,
2048 bytes per line and16384 bytes per reply. At most2 abandoned OS DNS lookups
can remain in daemon resolver threads; callers return by their deadline and
further lookups fail safely until a slot becomes available. No new service or
dependency is involved. Worker sessions alone have5-second SQL statement and
3-second lock timeouts, without changing server/API/owner settings.

Current authorizing-user, parent, requester and sender eligibility is checked
again before DATA. SQL commits `transmitting` before DATA starts. Only an explicit
final250 records `accepted`, meaning server acceptance, not recipient delivery.
The connection closes directly afterward; no QUIT round-trip can reverse it.
Definite4xx/5xx permit bounded retry/terminal failure. Lost, malformed, oversized
or unexpected positive final replies become `uncertain`. Never automatically
retry an uncertain attempt or create another public delivery to bypass it.

Shutdown cancels active sockets before joining worker threads. Preparing failures
are safe to retry with backoff; cancelled transmitting attempts are uncertain.
After a crash, expired preparing leases requeue within the8-attempt limit and
expired transmitting leases become uncertain. A persistence failure leaves the
lease for that same SQL recovery, never broker-side retry. Backoff starts at30
seconds and doubles, capped at1 hour. Frozen bytes/Message-ID survive safe retries.

Delivery creation, due times, leases, recovery, finalization and reconciliation
use the PostgreSQL wall clock by default. Process wall-clock skew must not expire
a live lease or delay a newly queued response; SMTP duration budgets remain
monotonic. Frozen historical MIME, Date, creation time and Message-ID are never
rewritten to correct a clock discrepancy.

Before owner reconciliation, stop and drain all relevant mail workers, account
for any in-flight operation and inspect external evidence using the stable
Message-ID. Use the existing owner-only `altvia.mail_participants reconcile`
command with the reviewed delivery version, `--workers-drained` and an opaque
evidence reference. Accepted evidence also requires the aware provider acceptance
timestamp. Explicit confirmed non-acceptance is the only route to requeue an
uncertain delivery; SMTP or Message-ID alone does not prove deduplication.

Rollback must drain senders and retain expanded state, event readers and owner
recovery tools. Do not drop queued/uncertain messages or remove schema guards.
No worker receives note, raw quarantine, private MIME preview, attestation
evidence, credential-table or sender/attestation mutation grants. Logs/events
contain fixed safe error codes and identifiers, never SMTP reply text or wire.

## Operator drain and reviewed reconciliation

Run these procedures only for an independently authorized installation, with its
existing external settings and exact Compose overlays. First stop every mail
worker sharing that database/account, including any workers on other hosts. For
the single-stack SMTP configuration above:

```sh
docker compose -f infra/compose.yaml -f infra/compose.smtp.yaml stop -t 30 worker
docker compose -f infra/compose.yaml -f infra/compose.smtp.yaml ps -a worker
```

Verify stopped containers and their actual exit status; a forced kill or missing
worker does not prove clean drain. Account for outstanding network operations
and check the provider using the stable Message-ID. SQL state and the presence
of that ID alone do not prove acceptance or non-acceptance. Keep all senders
stopped while selecting and committing the reviewed decision.

Set DELIVERY_ID, DELIVERY_VERSION and EVIDENCE_REF to the reviewed delivery UUID,
current positive delivery version and bounded opaque evidence reference. Keep
provider replies, addresses and message bodies out of those values. For proven
acceptance, ACCEPTED_AT must be the actual aware provider acceptance timestamp,
within the delivery's recorded lifetime. Execute the owner command through the
existing owner-secret-only migrate service:

```sh
docker compose -f infra/compose.yaml -f infra/compose.smtp.yaml run --rm --no-deps migrate \
  python -m altvia.mail_participants reconcile \
  --delivery-id "$DELIVERY_ID" --version "$DELIVERY_VERSION" \
  --decision accepted --evidence "$EVIDENCE_REF" \
  --workers-drained --accepted-at "$ACCEPTED_AT"
```

Only independently confirmed non-acceptance permits the same command with
`--decision not_accepted` and without `--accepted-at`. It requeues the same frozen
delivery; it does not create a second public response. An inconclusive provider
result remains uncertain. The flag records the operator's drain assertion; it
does not stop or discover workers. Read the resulting persisted state before
restarting workers with the exact configuration above. A version conflict or
refusal requires renewed review, never an invented evidence reference.

Historical rows created by an advanced API clock can have a recorded creation
time after genuine provider acceptance. The existing creation-to-current-DB-time
evidence bound safely refuses that timestamp. Keep such a row uncertain, retain
the immutable snapshot and seek a separately reviewed evidence/recovery procedure.
Do not invent an acceptance timestamp, rewrite creation/MIME, or requeue/create
another delivery to bypass the refusal. Clock correction changes new writes;
it does not authorize automatic repair of historical acceptance evidence.

## Controlled local validation

`apps/api/tests/test_smtp_transport.py` creates fresh TLS keys under ignored
temporary paths and exercises loopback-only TLS SMTP, hostile replies and
deadlines. `test_smtp_worker.py` adds real disposable PostgreSQL/Redis, restricted
worker credentials, duplicate actors, broker loss, current authority revocation,
safe retries and uncertain recovery. No real provider or recipient is contacted.
The browser uses the actual PostgreSQL/API/Redis/worker and a disposable TLS
relay, with exact saved-body review, server-acceptance wording and protected
recovery. The packaged smoke adds independent synthetic delivery tickets, real
worker-main processes under worker-only secrets/privileges, final250/lost/held
DATA replies, restart without another DATA and active SIGTERM timing. Its
sanitized mail-delivery-proof.json is the only new container artifact retained
alongside screenshots; account files, TLS keys and raw command logs stay private.
Executed results belong to the increment's acceptance evidence, not this runbook.
Final actual x86-64-v1 qualification remains separate after MVP development.
