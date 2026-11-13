# ADR-0038 Incoming private files on attested mail cases

Date2026-11-13. Selected engineering contract after private-file core acceptance
at exactc12d6e1: all five required hosted gates,1266 API cases/3 explicit native
console skips,175 browser cases and actual signed scanning/MIME/recreation/
matching4-object restore passed. A fresh read-only builder check found nothing
important left before planning. Implementation follows
docs/plans/2026-11-13-incoming-private-files.md and is not claimed by this contract.
No production mailbox, deployment, real import, retention deletion or target
operation is authorized.

The master specification was read completely. FR006/007/012, ADR0030-0033/0036/
0037 and existing customer/queue/session/lock contracts remain binding. The user
delegated engineering decisions and requested continuous development without
routine approval pauses. The selections below are engineering calls, not claimed
user choices. Real receiving identity/provider policy remains Q03/Q16.

## Intent and alternatives

An attested incoming message retains supported original file bytes through scoped
triage and its immutable incoming conversation. Every file uses existing private
S3, scan jobs, clean-only release, current resource checks and protected download.
Mail headers, files and known contacts never prove identity or grant access.

Selected: add concrete mail-case ownership to the existing attachment aggregate.
The immutable case already owns incoming text and its promoted incoming record;
it can own one frozen ordered file set through that same relationship. Reuse
the scanner and current incoming composition. No duplicated incoming-link table
is needed because a case has one immutable incoming receipt and its set cannot
change after publication. Cost: one actual third parent and truthful owner-tool
provenance, with compatible SQL, event, authorization and output expansion.

Post-promotion-only extraction would prevent triage file access and introduce a
second publication that could silently alter immutable incoming content. A
separate incoming-file/scanner subsystem duplicates integrity/fencing ownership.
Neither fits the selected existing owners as directly. No generic owner registry,
new long-running service, dependency, HTML renderer or forwarding feature is added.

## Bounded extraction, separately versioned from text

Preserve every parser1/parser2 result and exact current parser2 text/rejection
behavior. A ready parser2 result counts skipped parts; it is not extraction proof.
File extraction version1 is a distinct finite interpretation recorded on NEW
cases. Existing cases remain version0/legacy forever in this increment, including
aliases and protected replay. No background backfill or silent file insertion.

Reuse mail_mime's bounded header/boundary/charset ownership and Python standard
MIME/transfer decoders. Preserve raw2097152 bytes, entities64, depth8, headers16384
bytes/2048-byte physical lines/100 fields and existing multipart structure rules.
Do not expand archives, attached message/rfc822 or attached multipart entities,
decode images, fetch resources or render HTML. Traverse all accepted inline
multipart branches in wire order; do not deduplicate files by name or bytes.

An attachment candidate uses the same attachment-looking/non-text predicate as
the current normalizer. Accept at most20 candidates, each1..10485760 decoded bytes,
aggregate decoded file bytes<=2097152. The raw cap still bounds actual incoming
files more tightly than staff uploads. Keep exact decoded original bytes, with
strict base64/quoted-printable and7bit/8bit/binary handling; no repaired or truncated
content. Reuse attachments.validate_filename/media_type for actual accepted name,
extension and byte policy: PDF, PNG, JPEG or UTF8 plain .txt/.log only.

Names must be present, unambiguous and strict. Reuse stdlib parameter parsing,
reject duplicate/conflicting filename/name declarations and malformed percent/
transfer encodings. Before any broad charset fallback, restrict RFC2231 filename
charsets to the existing UTF8/ASCII/ISO8859-1/Windows1252 canonical allowlist and
decode strictly. Raw header names/values remain ASCII with encoded international
names; do not accept surrogate/replacement recovery. Preserve the accepted decoded
Unicode filename without trimming/normalizing it. Unsupported obsolete encodings
or parameter forms remain quarantined and receive a fixed unavailable result.
Version1 accepts one plain ASCII filename/name parameter or one single RFC2231
extended filename*/name* parameter. The extended language tag is empty or
[A-Za-z0-9-]{1,35}; percent escapes are strict. Continuation parameters and RFC2047
encoded-word filenames are unavailable in this version, with original raw data
preserved. A same-header plain plus extended declaration is ambiguous; when
Content-Type name and Content-Disposition filename both exist, decoded names must
agree. These finite compatibility choices were left to the builder check and
are recorded here as engineering calls.

Select all-or-nothing extraction of the file SET. Missing names, unsupported
types/attached containers, malformed parts or file/count limits yield unavailable
with one fixed owner-only reason and no published assets. Valid text triage may
continue with a fixed honest file warning. Do not label dropped parts imported.
Valid supported files publish as quarantine and keep individual scanning/ready/
rejected/failed states. Malware or scanner failure cannot release bytes and does
not change the immutable text or original file identity.

Fixed unavailable reasons are file_structure, file_count, file_size,
file_encoding, file_filename, file_type or file_parameter. They contain no input.

## Concrete persistence and truthful provenance

Add immutable mail_triage_cases fields file_extraction_version(0|1),
file_set_status(legacy|complete|unavailable), file_count(0..20) and a nullable
finite owner-only file_rejection_reason. Historical/default0 means legacy/count0;
new version1 is complete or unavailable; unavailable has count0 and fixed reason.
Complete permits count0 and no reason. Text and routing versions remain unchanged.

Extend attachments with nullable mail_case_id RESTRICT FK and file_position.
Exactly one ticket/work/case parent is permitted. Case files have purpose incoming,
creator_id NULL, parent_version1 and a unique nonnegative position within the
case's immutable set. Staff owners still require their real creator and existing
purposes/versions; no account is fabricated or external contact impersonated.
Case/position plus primary raw variant and extraction version identify the exact
ordered part. Existing immutable identity guards cover the new columns as well.

Only the actual table owner may INSERT a case-owned asset, enforced in SQL as
well as the finite owner command. The API never gains case-file INSERT authority
through an HTTP path. Deferred guards require exactly file_count case rows with
positions0..count-1 and forbid assets for legacy/unavailable cases. Existing case
update guards keep the set/header immutable; promotion, alias or invalidation
cannot change it. No extra incoming-link table or generic origin registry.

Count/provenance checks run at creation of the case/set, not on ordinary scan
updates. Actual worker claim/finalize must still succeed without case-table or
case-parent-column privileges; no new trigger may force broader grants.

Reuse attachment_scan claim/history/finalize/recovery, its DB-clock leases,
8 attempts/generation and exact clean/current-definition policy1. Worker scan
columns and raw/source/poll/preview/origin/name/parent denials remain unchanged.
An invalidated case may retain private scan history; current parent validity still
blocks download and fresh retry. Do not give the worker raw/case/name grants.

Owner creation emits file.uploaded schema2 with exactly actor_id=null,
actor_kind=management_command, attachment_id and state=quarantine. Preserve exact
schema1 user/file_worker envelopes and existing case published/alias/collision/
promotion events. Only this owner-created uploaded variant uses schema2; existing
worker scan changes and staff retries retain their old schema1 shapes. Consumer
validates/deduplicates privately without shared activity. No filename, raw ID,
hash, storage key, file bytes, address or evidence enters operational metadata.

## Owner publication, network and collision ordering

Keep the existing owner-only ALTVIA_ALLOW_MAIL_CASES=1 command/protected intent.
It still requires the original variant/contact/version/evidence and parser2 ready
text. Preserve old replay receipts and contextual raw-byte alias/collision rules.

Use one responsible locked publication helper for both preflight and finalization:
identity, client/team/queue, source, sorted case(s), contact as in ADR0036. Existing
origin replay, exact aliases and contradictory origins finish before storage I/O;
they retain the existing case/set/receipt. For a genuinely new case, return a
private preparation without advancing source/case or publishing an event.

Extract/validate outside transactions. Stage supported complete-set objects with
the existing create-only S3 writer and opaque keys outside every DB/authorization
lock. Then repeat the SAME current locked publication checks before committing
case/header/assets, primary origin, source version, audit/outbox atomically. A
concurrent winner becomes the existing replay/alias/collision, never another set.
Network work is never performed while source/identity/case locks are held.

If staging fails, repeat the locked existing-origin/collision path before returning
a fixed storage error for a still-new publication. A concurrent contradictory
origin must be recorded/invalidate the existing case even during S3 failure;
storage availability cannot conceal that case transition. Any unused staged
objects remain private unreferenced objects, as in staff uploads; no deletion or
production retention policy is invented. No new acknowledgement on DB failure.

Use a finite owner-tool Compose profile with the existing API image, owner DB
credentials and the restricted existing S3 create-only writer/CA. Keep raw-mail
and root S3 credentials away from runtime actors. Do not add S3 privileges/network
to ordinary migration tasks merely to run this tool. No new image or daemon.

## Resource authority, HTTP and immutable conversation

Case file reads require current mail_promotion.scoped_case authority (queue role
AND explicit client ceiling). For a promoted case, additionally require current
read authority on its immutable resulting ticket. Platform administration, team
metadata and file ownership never bypass those checks. Hidden/foreign IDs are404
without file/name/count disclosure. Public/note/work scope stays unchanged.

Return one optional files block on authorized CaseDetail and IncomingMessageOutput:
extraction_version, status and ordered existing attachment metadata/capabilities,
max20. Case summary/list stays unchanged. If resulting-ticket authority is absent,
suppress the entire block, including count; a global file read is404. Legacy shows
a fixed informational unprocessed state, never a claim of an empty imported set.
Unavailable shows a fixed warning with no hostile names/reasons/part count.
No new collection/upload endpoint or mutable incoming-link table is required.

The case version/ETag remains the promotion intent version. Individual scan state
uses the file's own version and current no-store reads; case version alone never
certifies cached readiness or acknowledges a retry.

Existing global attachment detail/content/scan-retry routes resolve a third
explicit concrete parent; never fall through to work ownership. Keep staff upload
request/filter/receipt owner and purpose unions staff-only. Case/read DTOs may
express mail_case/incoming; HTTP upload cannot choose them. Incoming files cannot
enter public drafts, notes, work comments or SMTP by guessed ID or automatic copy.

Invalidation preserves authorized historical metadata/text and the existing fixed
warning, but can_download is false and content is409 with no bytes before S3.
Otherwise exact ready state and verified object integrity/current authorization
before client bytes use the existing download owner. Collision/revocation during
prefetch must fail final authorization with zero private bytes. No direct S3 URLs.

Fresh incoming failed-scan retry is queue-operations-manager only, with current
client ceiling, active queue/team/client and ready/promoted valid case. After
promotion also require current ticket write scope and a nonclosed ticket. Viewer,
agent-only and invalidated/inactive contexts cannot retry. This is a narrow
engineering authority choice, not a new role/content grant. Preserve existing
FILE If-Match/key/receipt protocol/current authority on replay; worker generation
and history stay with the existing scan owner. No malware manual release.

Reuse the scoped case and incoming conversation readers, immutable case-to-incoming
relationship and batched file reads. Existing promotion request fingerprints,
minimal stored receipts, ticket versions and old frozen MIME wires remain exact.
No body/case rewrite, default outbound asset or new sender/requester attestation.

## Interface, rollback and acceptance boundaries

Impeccable is mandatory for the actual frontend stage. Reuse the accepted Twenty-
inspired Operate world, current private-session/download owners and honest scan
states. Show original safe names, pending/rejected/failed/ready states and current
download/retry actions on triage and incoming conversation. No inline file render,
thumbnails, decorative progress, new visual world or persistent browser storage.

Use additive migration(s), exact same-parent/count guards and explicit API column
grants only for needed file projection. Runtime raw/source/poll/preview/origin and
worker name/case-parent denials remain real table AND column/query tests. Retain
expansion on rollback, version2-aware consumer, case-file-aware API/web/owner tools
and durable objects. Drain incompatible writers before enabling new owner writes.
Contraction refuses new case interpretation/assets or corresponding event/audit
history, even a version1 zero-file case. Never delete history to force downgrade.

Prove parser2 exact regressions, supported binary/Unicode filenames, malformed/
oversize/unsupported all-or-nothing sets, no expansion/fetch, raw/context aliases,
legacy replay, concurrent publication/orphans and collision during staging/error.
Use actual PG/API/S3 for integrity, rollback, SQL provenance/count/immutability,
current scopes/revocation, least privilege, retry fencing and migration refusal.
Real browser proof covers triage -> promotion -> incoming file/download, blocked
states, loss/retry/current sessions, keyboard/axe/themes/mobile. Reuse the real
signed scanner and packaged matching restore for a new synthetic incoming context;
preserve all existing fixtures/wires/auth invalidation assertions. Bind exact
source/security/image/complete logs; no source mutation during tests.

Actual x86-64-v1 qualification follows remaining MVP development. Production
identity/provider/retention/sizing policy, encrypted backup/compatible-image
rollback and real data import remain their separately tracked gates. This draft
does not expand them or call the current core/MVP complete.
