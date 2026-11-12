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
compatible additive migrations through00024 and provision the reviewed roles.

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
Changed artifacts still need final integrated actual x86-64-v1 qualification.
