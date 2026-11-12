# ADR-0036 Attested incoming mail and scoped conversation promotion

Date2026-11-12. Selected after ADR0035 acceptance c47fd8a. FR006/007/012,
master specification, ADR0004/0005/0028/0030-0035 and AGENTS apply. User authorizes
continuous MVP development/direct main publication. Provider/forwarding and real
identity evidence remain Q03/Q16. Only controlled synthetic tests are performed.

## Decision and alternatives

Retain unclassified raw mail, poll state and parser previews as owner-only.
An explicit owner command attests the sender/client/contact of ONE immutable
variant and publishes its parser2 text into a scoped mail triage case. Internal
staff can review/create/append/reopen only under current queue/customer/action
authority. Headers and known contacts never create identity proof. The case is
not a global verified contact, account, content grant or ticket participant.

Select this classified projection over a general unclassified-mail content role
because no organizational triage policy has been selected. It also avoids owner
commands impersonating staff during normal ticket promotion. Cost: per-message
owner attestation/classification is required until a separately approved receiving
gateway can supply equivalent trustworthy evidence. This is a functional manual
trust boundary, not automatic production sender verification. Real-provider
acceptance remains separate; the safe synthetic flow is implemented now.

## Owner publication, contextual identity and immutable storage

mail_triage_cases owns one immutable normalized subject/body and routing/context
snapshot: source/queue/client/contact/current ASCII email, routing_version1,
nullable Message-ID, In-Reply-To, References, optional thread token, trusted local
received_at, publication time, state ready/promoted/collision/revoked and positive
version. It also owns the minimal promoted ticket/incoming-message receipt.
Use narrow API column grants; runtime never receives raw/source/poll/preview/
origin/evidence grants. Keep routing tokens/identifiers out of response DTOs unless
explicitly required by the safe UI; no token/evidence in logs or shared activity.

Copy exact ready parser2 text once across this publication boundary. Keep its
998-character/3992-byte subject and1..65536-byte UTF8 body bounds. Do not reparse
or reinterpret historical parser1 as corrected policy. mail_case_origins is
owner-only immutable provenance: unique variant, envelope/source, SHA256, case,
attested sender/context, opaque evidence, actual attestation time and disposition.
It distinguishes first origin, exact alias and conflicting origin. Existing raw
bytes remain authoritative and unchanged; origin hashes/evidence are never API
fields. Future routing interpretation changes require a version, not overwrite.

The contextual partial unique key is source_id/client_id/contact_id/email_snapshot/
Message-ID when an ID exists. Preserve ID case exactly; normalize mailboxes using
the existing ASCII contact rules. Re-attesting a variant in another context or
with another reviewed intent refuses. Identical raw bytes and routing interpretation
under the same key may add an independently attested alias to the existing case.
Different opaque evidence references do not make equivalent routing conflict.
Changed bytes/routing under that same key permanently contradict the case, block
fresh promotion/anchor use and preserve a private conflicting origin. This is
deliberately conservative: changed Received headers can require operator review.
Body equality alone is never deduplication proof.

After promotion, an identical independently attested alias retains the SAME case,
incoming row and immutable promotion receipt; it cannot create another message.
Its private mail.case_aliased event uses explicit schema2 with state promoted and
the same bounded metadata fields. Existing schema1 ready-alias envelopes remain
exact. Revocation/collision after promotion preserves the incoming receipt/history
and supplies the fixed historical invalidation warning, never a destructive undo.

The same claimed Message-ID in another attested client/contact/email context is
independent. It cannot reveal, invalidate or deduplicate the first context. An
incoming primary ID equal to an existing server-generated outbound ID in its OWN
context rejects that incoming claim, regardless of that delivery's current state;
it cannot rewrite or poison the reserved outbound row. Only accepted outbound
rows provide routing anchors. Refusal publishes no case or classification;
the raw receipt remains quarantined.
Missing Message-ID permits primary-UID-only creation or a safely anchored append,
with no cross-UID dedup or future incoming-ID anchor. Malformed present IDs never
become missing IDs. An ID-less first request cannot supply a reply reference;
do not invent an incoming Message-ID to hide that protocol limitation.

Owner publication requires explicit opt-in and owner role, current active queue/
team/client/contact and exact current contact mailbox, non-collided receipt and
ready parser2 result. The owner records external identity proof for this variant;
it is never inferred from From, Reply-To, session, domain, Authentication-Results
or contact existence. Retain evidence outside runtime. A source/table mutation,
collision or stale reviewed version rolls back the entire publication.

## Bounded routing interpretation

Reuse existing bounded root-header extraction before standard-library parsing:
16384-byte root block,2048-byte physical lines and100 fields. Routing version1
accepts a finite ASCII angle-address Message-ID<=320 characters with dot-atom
local part and DNS domain; spell the exact grammar/limits in the implementation
plan and test it. No whitespace/control/header injection or unbounded registry
lookup. One primary ID, at most one In-Reply-To, at most64 References and one
optional64-lowercase-hex X-Altvia-Thread. Reject duplicate/ambiguous singleton
headers and malformed present fields. Unknown references grant no authority.
This conservative grammar may quarantine valid obsolete/quoted/domain-literal
forms; preserve raw bytes and document compatibility rather than truncate/coerce.

Require exactly one From mailbox and consistent optional Sender/Reply-To mailboxes
matching the externally attested contact. Display names come from the authorized
contact snapshot, not hostile header presentation. To is never identity/client
proof. Auto-Submitted other than no, null Return-Path and DSN/report forms remain
quarantined; no auto-reply or inbound promotion itself sends mail. No network
fetch, HTML rendering or attachment extraction is introduced.

## Scoped references and resource authority

Resolve references within the attested queue/client/contact/email context FIRST.
Intake and outgoing sender source IDs may differ within that same queue; each
source's duplicate identity stays source-specific. Recognized incoming anchors
are promoted cases; recognized outbound anchors have actual accepted state and
matching frozen recipient/contact context. Resolve every recognized contextual
anchor before filtering current action eligibility. They must agree on one
ticket, including currently invalid or ineligible anchors; a contradicted own
anchor or two own tickets fail closed. Foreign/unknown strings neither route,
invalidate nor produce existence-specific errors. Own anchor plus foreign or
unknown ancestors may append to the one eligible own ticket.

At least one own known anchor is required to append; subject and token alone
never route. A supplied thread token only corroborates the already-selected
ticket, compared without globally resolving foreign tokens or returning them.
Current target queue/client/requester, active matching ticket requester participant
and current manager/assigned-agent write authority are required after resolution.
New-ticket creation instead reuses the existing creation authority and agent
self/unassigned limitations. Platform administration and team metadata are not
content grants. All reads require current explicit client ceiling plus queue role.

New-ticket promotion never creates an outbound participant through API privileges.
The existing owner-only requester attestation remains required before first SMTP
reply. This separate operation is visible in the runbook and synthetic workflow.
Extend outbound reference selection to eligible promoted incoming IDs and accepted
outbound IDs, at most16 in persisted chronological order. Preserve exact existing
outbound-only ordering and all previously frozen bytes/IDs/receipts. The first
reply must include the original eligible incoming ID when one exists.

Reference selection for a new freeze is also bounded to the current queue/client/
contact/frozen-recipient-email context. Changing a requester never includes the
previous requester's ancestor IDs in a new wire. Preserve the exact created_at/id
ordering of eligible outbound-only histories and every previously frozen wire.
On a context's first reply (no accepted outbound there), retain its earliest
eligible incoming ID plus the latest other15 eligible references, in chronological
order. This first-reply root retention takes precedence over an unqualified
latest16 truncation when more than16 incoming records precede that reply. Later
replies use the latest16 eligible references. Missing IDs remain absent. Cover
both many-incoming-before-first-reply and changed-requester negatives explicitly.

## Locks, collisions, versions and protected effects

Owner publication/revocation locks identity, ordered client/team/queue, source,
case(s in stable ID order), then contact. Those owner case commands do not mutate
or lock tickets. API writes take the identity lock BEFORE session authentication,
then client/team/queue, all relevant cases in stable ID order, ticket, contact.
Relevant cases include the reviewed input and every recognized contextual incoming
anchor, so a raw-collision invalidation cannot race an unlocked anchor check.
Resolve contextual ambiguity and current invalidation again after those locks.
Owner publication is excluded by the same identity lock; raw capture can change
existing case state but cannot insert new independently attested anchors. API
never locks a private source. Recheck proof/contact/parents after locks; no network
I/O in transactions.

An additive SQL trigger on an envelope becoming collision invalidates every case
linked by ANY origin of that exact receipt, including aliases, in stable ID order.
Capture already holds source; the trigger acquires cases only, never identity/
customer/team/queue/ticket locks. It advances invalidation/version atomically and
covers old capture binaries without changing old event envelopes. Collision first
blocks promotion; promotion first leaves immutable history plus a scoped fixed
contradiction warning. Revocation similarly blocks fresh effects and preserves
historical messages; never silently erase or republish another client context.

Promotion is a strict create/append union with original If-Match case version,
Idempotency-Key and full reviewed intent. Append includes target ticket/version,
explicit reopen choice and reason. New creation emits ticket/history version1,
then incoming message version2. Append takes next ticket version. A permitted
explicit reopen uses existing targets/transition at next version, then incoming
message takes the following version in the SAME transaction. Closed append needs
permitted explicit reopen; resolved append without reopen retains status. No new
automatic reopen policy is invented. A recognized thread cannot be bypassed with
an arbitrary new ticket to evade scope, closure or the reviewed target.

Atomically commit immutable incoming row, ticket/history, case receipt/version,
audit and strict ticket.message_received metadata. Actor is current staff;
external sender and trusted local receipt time are distinct immutable fields.
No body/address/evidence/header/token enters shared metadata. Preserve old
ticket/note/draft/delivery fingerprints and exact event field sets.

Saved create replay checks current case creation authority, the original
self/other-assignee restriction and resulting ticket READ scope. It must not
require update authority on a newly created unassigned ticket. Saved append
replay checks current case scope and resulting ticket manager/assigned-agent
authority. Both validate protocol before minimal200; do not repeat fresh
eligibility after a recorded promotion, collision or revocation. The protected
fingerprint includes the original reviewed case version and complete body
(including append ticket version/reopen reason). A new key cannot create another incoming row
for that case.201 is fresh,200 protected replay;428 missing protocol,422 invalid,
409 stale/ineligible/conflict,403 action denied,404 hidden/mismatched resources.

## HTTP, browser and rollback

Provide paged scoped case list/detail and a protected promotion POST. Unclassified
mail remains owner-only; do not add a broad triage content role. List omits bodies,
evidence and routing internals; detail gives authorized immutable text, bounded
review choices and honest current eligibility. Return no hidden target identity.
The scoped list/detail projection includes current client_name and queue_name
through those authorized parent joins. Staff with case read authority need no
separate client-registry role or creation-only choice lookup just to read those
labels; no additional client metadata or registry authority is granted.

One ticket conversation union read combines incoming records and existing public
outbound messages by ticket version with actor/ticket-bound cursors. Existing
/messages remains outbound-only and private notes remain independently authorized.
A scoped single incoming-message read confirms exact acknowledged receipts even
when that record lies beyond the visible conversation page. It checks both
parents and returns404 for hidden/mismatched records.
Reuse existing send/composer/status owners rather than duplicate their protocols.
Impeccable governs scoped triage and conversation UI, escaped text, explicit review,
original-intent/receipt recovery, real errors, keyboard/axe/themes/responsiveness.
Files stay quarantined until the later fail-closed private object-storage stage.

Additive schema, immutable guards, composite same-ticket/client/queue ownership,
positive/version-exhaustion checks and explicit least-privilege grants. Contraction
refuses cases/origins/incoming/email tickets or corresponding history. Rollback
retains expansion/compatible consumers and owner tools; drain incompatible tools,
never delete history to force downgrade. No new dependency/service/native tuning.

Acceptance: actual PG/API spoofing/scope/protocol/replay/races/atomic failure,
contextual dedup/aliases/late collision/foreign-ID DoS/missing IDs/long text and
legacy message/note/SMTP compatibility. Actual browser and packaged synthetic
IMAPS->parser2->owner attestation->scoped HTTPS creation->requester attestation->
TLS first reply references->verified incoming reply->explicit permitted reopen,
restart/privacy. Exact CI/security/archive evidence. Real policy remains open and
actual x86-64-v1 qualification follows the complete remaining MVP.
