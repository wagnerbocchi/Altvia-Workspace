# Attested incoming conversation operations

ADR-0036 publishes one explicitly attested immutable message into a scoped case.
It does not verify a global contact/account or automatically trust From, domain,
subject, headers or a mailbox. Development acceptance uses synthetic messages.
This runbook grants no live mailbox, identity attestation, sending, production
rollout or data-import authorization. Q-03/Q-16 retain those real policy decisions.

## Owner boundary and preparation

Use the existing owner database configuration through restricted secret injection,
never a URL/password in arguments or logs. API/worker credentials cannot perform
owner attestation or read raw/source/poll/preview/origin/evidence tables. Apply the
compatible additive migrations through00027 and provision the reviewed roles.

1. Register the reviewed intake source and perform bounded read-only IMAPS capture
   as described in [imap-poll.md](imap-poll.md). Preserve source, UIDVALIDITY, UID
   and every immutable raw variant. The current raw-message limit remains2 MiB.
2. Select the exact owner-side variant and run parser2 normalization using
   [mail-normalize.md](mail-normalize.md). Historical parser1 is not corrected
   policy. A ready parser result supplies text, never identity proof.
3. Establish trustworthy evidence outside the application for that exact variant,
   client and active contact's current ASCII mailbox. Review the current contact
   version and record only an opaque evidence reference, not credentials or raw
   identifying evidence, in the command below. Contact existence is insufficient.

With owner credentials already configured and actual attestation authorized:

```bash
export ALTVIA_ALLOW_MAIL_CASES=1
python -m altvia.mail_cases_owner attest \
  --variant-id '<reviewed-variant-uuid>' \
  --contact-id '<reviewed-contact-uuid>' \
  --contact-version '<reviewed-positive-version>' \
  --evidence '<opaque-reviewed-evidence-reference>'
unset ALTVIA_ALLOW_MAIL_CASES
```

The minimal receipt contains case_id, state, disposition and replayed. Lost output
is recovered by repeating the same reviewed attestation. Do not reclassify a
variant to bypass refusal. Missing Message-ID is permitted without a fabricated
incoming identifier; malformed present IDs remain quarantined.

## Private incoming file publication

ADR-0038 records extraction version1 on each new case. Complete sets retain
original supported bytes in their wire order, initially quarantined. Empty sets
are complete/count0. Unsupported or malformed sets publish no files and retain
one finite owner-only rejection reason; normalized text interpretation is unchanged.
Existing cases remain version0/legacy, including replay and aliases. No backfill,
sender proof, automatic outbound copy or manual clean-state override is performed.

When actual files need storage, inject ALTVIA_STORAGE_FILE pointing to the
restricted existing API S3 writer configuration, plus its trusted CA. The command
loads it only after current locked preflight. Empty/unavailable sets and existing
case replay/aliases/collisions need no storage configuration. Do not supply root
S3 credentials. The finite Compose tool uses the existing API image and owner DB:

```bash
docker compose -f infra/compose.yaml -f infra/compose.files.yaml \
  --profile mail-cases-owner run --rm --no-deps -T mail-cases-owner attest \
  --variant-id '<reviewed-variant-uuid>' \
  --contact-id '<reviewed-contact-uuid>' \
  --contact-version '<reviewed-positive-version>' \
  --evidence '<opaque-reviewed-evidence-reference>'
```

Run only after compatible migrations and healthy private PostgreSQL/S3 services.
This opt-in profile mounts owner DB, API S3 writer and CA only; ordinary migrate
has no object network or storage secret. No stdin payload is consumed, and no
credential or raw mail belongs in arguments. Failures print only the fixed safe
refusal and acknowledge no still-new case. Repeat the exact reviewed intent to
resolve an uncertain result. A concurrent contradictory origin still commits its
case invalidation even if object staging fails.

Staging runs without DB locks. Final current checks atomically publish case header,
ordered assets, origin, source version and private audit/outbox. Failed final checks
or a concurrent winner can leave private unreferenced objects; retain them without
inventing cleanup or retention policy. Existing scan leases/history and policy1
alone release bytes. Runtime worker receives no case/raw/name privileges.
During producer rollout, global file routes return the same404 for case assets
as absent IDs until the separate authorized case-reader increment is installed.

## Staff review, promotion and replies

Service Desk's incoming list shows only owner-published cases under the current
queue role AND explicit client ceiling. Team membership or platform administration
does not grant this content. Review exact immutable original text and context.
Create uses current creation authority; a safely correlated append/reopen requires
current target write authority. The browser retains the reviewed case version,
target version, body and key until the original protected operation is resolved.

An acknowledged operation is checked against the current case, resulting ticket
and authoritative single incoming read. Detail-only historical receipts support
reload/read-only navigation; another operation's receipt cannot acknowledge a
pending original request. On uncertain HTTP, recover the SAME original intent;
do not invent a fresh key, version, target or body to bypass that uncertainty.
Session/CSRF failure disposes private browser state. API contracts and exact
statuses are documented in [api.md](../contracts/api.md).

Promotion itself neither sends mail nor creates an outbound requester participant.
Before the first SMTP reply, a separately authorized owner operation must attest
the resulting ticket's current requester under ADR-0035:

```bash
python -m altvia.mail_participants attest-requester \
  --ticket-id '<reviewed-ticket-uuid>' \
  --version '<reviewed-ticket-version>' \
  --evidence '<separate-requester-evidence-reference>'
```

Configure the sender through the existing reviewed accounts secret and
register-sender operation. There is one sender per queue; receiving and sending
source IDs may differ within that queue. Never replace sender identity or reset
old delivery records to make a test or retry succeed. Staff explicitly saves and
reviews the public draft, then requests delivery. Private notes remain separate
and are never sent. SMTP acceptance is server acceptance, not inbox delivery.

The first response retains the original eligible incoming root in References;
missing incoming IDs cannot supply that reference. Subsequent incoming messages
need explicit per-variant attestation and safe contextual anchors. Subject/token
alone cannot select a ticket. Closed tickets require an explicitly permitted
reopen with a real reason; receipt retries cannot duplicate incoming history.

## Collisions, restart and compatible rollback

An exact independently attested alias preserves the same case/incoming receipt.
A raw collision on any alias or an owner revocation invalidates fresh effects
and future anchor use while preserving promoted history. The scoped conversation
shows a fixed invalidation warning. Never delete history, edit raw/wire bytes,
clear collision state, adjust recorded times or reset uncertain deliveries.
For delivery uncertainty use ADR-0035's explicit owner reconciliation protocol.

API/PostgreSQL restart must preserve original protected receipts, incoming text,
case/origin linkage, frozen outbound wire/IDs and timestamps. Retain database
volumes and the compatible owner tools. Runtime diagnostics must omit private
text, addresses, routing tokens, evidence and credentials.

Rollback preserves schema expansion and uses a tested promotion-aware API plus
its compatible web client, schema1/2-capable worker/provisioning and version-aware
owner tools. A Task1-only Case reader knows no promoted state and is not a safe
rollback API after promotion. Do not blindly select an older image. Drain
incompatible owner commands before changes; refuse contraction when00023/00024
data or corresponding history exists. Never remove records to force downgrade.
After incoming file publication, retain00027, schema2-aware file consumers and
compatible case-file owner/API tools plus all private objects. Contraction refuses
even version1 count0 cases or corresponding file event/audit history. Drain old
owner writers before enabling the new publication protocol; do not silently
reinterpret a legacy case or select an incompatible older application image.
Changed artifacts still need final integrated actual x86-64-v1 qualification.
