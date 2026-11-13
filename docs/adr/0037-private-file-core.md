# ADR-0037 Private files, fail-closed scanning and public-response attachments

Date: 2026-11-12. Engineering selection under the user's continuous MVP/direct-main
authorization, after ADR-0036 development acceptance at36e4642. Master FR006/007/012,
security requirements and existing domain authorization/replay contracts apply.
This is a development contract. Tasks1-3 backend infrastructure, private assets,
scanning, immutable content links and reviewed outbound MIME files are implemented
and development/CI accepted throughdf3c8bb. Browser file workflows and incoming-MIME
file ownership remain pending. The latest user continuation resumes Task4 after
the accepted whole-system redesign, superseding the earlier stop-before-design.
This is not production/CPU acceptance. No target connection, production deployment, real data import or
retention/deletion policy is authorized here.

## Goal and bounded sequence

Deliver real staff uploads, private downloads, file-bearing public drafts/private
notes/work comments and explicitly reviewed SMTP attachments. Preserve independent
ticket/work state and current client/project/queue/note authority. The subsequent
incoming-MIME file contract will extend this working core; no placeholder Case
attachment field or raw-mail runtime grant is introduced here. Until that later
increment, original incoming MIME attachments remain quarantined. Do not call the
complete native mail-file path finished after staff uploads alone.

## Approaches and selected components

1. Reuse a maintained S3 server over the single host's filesystem, a standard S3
   client and a maintained scanner. This fits the master without inventing storage
   or signing protocols. Select VersityGW's POSIX backend, botocore and ClamAV.
2. Garage was examined. Its native Write permission also grants deletion, requiring
   another enforcement boundary; its official configuration discourages a single
   replica outside tests. A fake multi-node cluster on one VM supplies no redundancy.
3. A filesystem-only HTTP adapter would miss the selected S3 contract. A custom
   object server or large distributed storage cluster adds unjustified ownership.

Exact initial development pins:

- VersityGW1.11.0, commit e42ae7ab8107201e64e52ee024824e8cab3683b3. Source archive:
  https://codeload.github.com/versity/versitygw/tar.gz/e42ae7ab8107201e64e52ee024824e8cab3683b3,
  SHA256c15737f351b857273223e5a9a5fd2073a4f90745901baaf363ef3501964cf556.
  Build with the existing patched pinned Go builder if it meets Go>=1.26.0,
  GOTOOLCHAIN=local, GOAMD64=v1 and CGO_ENABLED=0. Verify actual toolchain/build info.
  A content hash proves reproducibility, not an upstream signature.
- botocore1.44.1, normal pure-Python dependency without the optional crt extra.
  Its published wheel SHA256 is7a741074a78e28187c88d9f7f91db18731ea91725455873d863ae63ea35e75f3.
  Resolve and audit all transitive pins through uv; no handwritten SigV4.
- Signed Alpine3.24 x86_64 vendor clamav-daemon/freshclam1.4.6-r0 in a pinned
  minimal image, with actual package-signature verification and package inventory.
  Official upstream identifies1.4.6 as a security-patched supported LTS release.

No component is ISA-qualified by this selection. Inventory, advisories/SCA,
functional resource tests and final actual x86-64-v1 qualification are required.
If a pin cannot pass, record the concrete issue and select a corrected compatible
pin before using it; do not mask a finding, drop a native guard or use -march=native.
Elasticsearch/OpenSearch/Solr/MongoDB/vector engines/local models remain prohibited.

Primary references: [VersityGW](https://github.com/versity/versitygw/tree/v1.11.0),
[ClamAV release](https://blog.clamav.net/2026/08/),
[botocore configuration](https://docs.aws.amazon.com/botocore/latest/reference/config.html).
Private research snapshots are provenance, not an implementation dependency.

## Storage and infrastructure boundary

Use one non-root S3/POSIX service with --fsync, private durable named volume,
verified TLS, no host port, web UI, public bucket, external backend or standalone
IAM service. Keep symlink buckets/ownership-changing modes disabled. Use fixed
bucket altvia-files and independent opaque256-bit object keys, never customer,
filename, address or hash in a key. API and worker never receive root/admin keys.

Owner-only finite bootstrap uses restricted secret files/stdin and standard SDK
signing for the real native admin API. Never place secrets in argv or output.
Create ordinary non-owner/non-admin API and scanner accounts. Native bucket policy
allows API GetObject/PutObject and scanner GetObject on objects/* only. Require
If-None-Match=* for every runtime PUT; explicitly deny destructive/administrative
actions, object listing, ACL/policy changes and other buckets. Test missing/wrong headers,
copy/multipart variants, overwrites and actual anonymous/cross-bucket requests.
An unsupported policy must fail qualification, not silently broaden credentials.
Pinned internal IAM permits global ListBuckets without an identity-policy layer;
its explicit owned scope returns only buckets owned by the caller. Runtime users
must own NONE. Permit only HTTP200 with an actually empty bucket list, no other
owner/continuation/bucket metadata; record that result honestly, never as403.
Pin list-buckets-scope=owned and prove emptiness even with populated root/foreign
buckets and their normal object policy. ListObjects/V2/versions/uploads and all
actual object enumeration still require denial. Reject any visible bucket or
ownership drift. Adding another IAM service merely to turn this empty response
into403 would not improve the actual data boundary.
S3 CopyObject/completed multipart share PutObject authorization. A native copy
creating a NEW immutable object may succeed only under the same permitted source/
destination and If-None-Match=* constraints. Record that as a conditional creation,
not a method denial. Missing/wrong preconditions, existing destinations and foreign
scope must fail. Unsupported x-amz-copy-source policy conditions are not used.
The application adapter still exposes bounded single PUT/GET only; it does not
add copy/multipart functionality merely because the server supports those forms.
Existing initialization is inspected and refused on incompatible identity/policy;
bootstrap must not reset existing credentials or delete data to look idempotent.

botocore uses explicit credentials, endpoint, CA, SigV4, path-style addressing,
payload signing, connect timeout2s, read timeout5s and total_max_attempts1. No ambient
metadata credential lookup, URL from HTTP input, disabled TLS or opaque SDK retries.
Use bounded single PUT/GET, no transfer-manager/multipart scaffold. ETag alone is
not an integrity proof. A conditional duplicate never overwrites original bytes.

Clamd and signature updater share only a restricted definitions volume. Only the
updater has definition-download egress; only the worker reaches clamd's private
socket/network. No scanner/storage/public admin port is published. Retain non-root,
read-only roots, dropped capabilities, bounded writable paths/resources and health
checks. New image scans must include actual Go dependency build information and
nonempty AV/native package inventories. Existing five-service scans are extended.

The current local Podman VM has2048 MiB; do not stop/reconfigure it or claim full
standard-definition scanner capacity there. Local bounded fixtures/negative
controls remain distinct from actual production-profile signed-definition tests
on adequately provisioned hosted Docker and final target. No synthetic daemon or
unsigned tiny database substitutes for that real positive acceptance gate.

## File bounds and upload protocol

Policy1:1..10485760 bytes per file; at most20 distinct attachments per message,
note or work comment. Allow PDF/.pdf, PNG/.png, JPEG/.jpg|.jpeg and UTF8 plain
text/.txt|.log. Check actual bounded bytes and extension together, never browser
MIME alone. Reject control/bidi/path separators, dot paths and names over255 UTF8
bytes; preserve accepted original name and exact bytes. No HTML/SVG/executable/
archive type, image decoding, thumbnail dependency, active rendering or fetch.
Sniffing plus scanning is not a claim that every accepted byte is harmless.

Upload routes are POST /tickets/{id}/attachments and /work-items/{id}/attachments,
raw application/octet-stream, reviewed filename and purpose in strict unique query
fields. Strict UTF8 query decoding rejects malformed encoding instead of
replacement. Ticket purpose is public|note; work purpose is work. Require original
If-Match of the parent, Idempotency-Key, X-File-Bytes and lowercase64-hex
X-File-SHA256. Reject repeated/unknown fields. Hash/count actual streamed bytes;
claimed size/digest are expectations, not trusted facts. Max body lifetime60s;
at most2 active upload/download transfers per API process, immediate busy refusal.
Scope any ingress body-size/streaming change to these upload routes.

First perform current scope/action/session/CSRF checks, then release transactions
before bounded private spooling/network. Hash and type checks precede PUT. Recheck
protected replay after hashing: an existing matching receipt needs no second PUT.
Otherwise PUT to a new private key outside DB locks, then take identity-before-auth,
current parent locks and repeat scope/action/session/version checks before atomic
metadata, private audit/outbox and receipt. Fingerprint owner/purpose/name/size/
actual digest AND original parent version. No parent version is advanced for an
unlinked asset; content creation later owns its version. Interrupted/stale final
writes may leave private unreferenced objects; preserve and report them, never
invent automatic cleanup or retention. Concurrent matching requests publish once.

Receipt: owner_type, owner_id, attachment_id, bytes, sha256 and initial version.
The digest is for original-uploader acknowledgement only; ordinary metadata/list
responses omit hashes, object keys and scanner diagnostics. Original-intent replay
plus authoritative scoped metadata confirms upload; a GET alone never acknowledges
an uncertain original POST. Session changes dispose all private File/Blob state.
Replay requires current original-action authority; fresh active/version eligibility
is checked only for a new effect. Inactive or progressed scan state does not erase
an otherwise currently authorized saved receipt.

Policy1 scans on upload. A ready result records a successful scan under the
reported engine/definitions that were fresh at that time. Later scanner downtime
or definition age does not revoke that historical decision or add scanner I/O to
every download/send preparation. Current resource authority and actual stored
byte integrity remain mandatory at access. Unscanned/non-clean files remain
blocked whenever scanning is unavailable. No UI claims timeless malware freedom.
No expiry, ready-file reclassification or access-time rescan is invented here;
Q-22 records whether production requires that different versioned policy. This
is an explicit engineering baseline, not company approval of production policy.

## Ownership, persisted scanning and download

attachments has exactly one concrete ticket_id or work_item_id FK and matching
purpose. No speculative third owner. Immutable filename/media/size/hash/key/creator/
creation context, positive version and policy_version1 are persisted. States are
quarantine, scanning, ready, rejected or failed. Scan generation/attempt history,
lease token/expiry, next attempt and bounded fixed results belong to this aggregate.
There is no runtime path that manually marks a file clean.

Reuse actual domain owners: public writes require ticket require_update; note
writes require current note_access=write, not assignee authority; work-comment
writes require active project contribution, not item-owner update authority.
Reads use current parent authority plus note read/write for note assets, including
administrators. Hidden/foreign/private-purpose file IDs return indistinguishable404,
without name/ID/count/activity disclosure. Ticket/work links confer no file grant.

Existing outbox/worker owns durable scan publication, bounded broker backlog and
recovery. File operational events carry strict IDs/state only and are acknowledged
without shared activity. Worker gets only required object/scan columns, no original
filename, note body, raw mail, preview or origin grant. Claim under a file lock,
use DB clock for a60s lease, close transactions for network work and require the
current unexpired token/generation before publishing a result. Monotonic process
timeouts never substitute for DB expiry. Stop/retry/late results cannot publish
ready after loss of ownership. Use8 attempts per generation with bounded exponential
backoff (30 * 2^(attempt-1) seconds, capped at3600); a currently authorized protected retry of failed starts a new generation
while immutable attempt history remains. Rejected malware is not manually released.

Before scanning, GET/hash/count the private object in a bounded spool. Clamd uses
strict bounded VERSION and INSTREAM framing, no filename/path, max network phase30s
and per-I/O timeout5s. Pin the expected engine; compare reported definition version/
date before and after scan and fail/retry on change. Require current loaded daily
definitions no older than48h or more than5min in the future, measured against DB
time. Production clamd explicitly uses OfficialDatabaseOnly yes, signed bytecode
only, FailIfCvdOlderThan2, AlertEncrypted yes, AlertExceedsMax yes and
ConcurrentDatabaseReload no. Stream/File limit10MiB, total expanded scan20MiB,
MaxScanTime10000ms, recursion8, threads2/queue4. Verify exact supported directives.
Startup checks require complete valid signed vendor definitions; signature updates
must actually verify/replace/reload them. Only exact clean output can yield ready.
Unavailable/stale/unsigned/changed/timeout/limit/encrypted/error/truncated output
never releases bytes. Record the reported engine/database identity, not an invented
cryptographic attestation of the entire running service.

GET parent attachments uses actor/parent/filter-bound cursor, limit1..100/default25.
Detail gives real state/version and current can_download/can_retry_scan. Protected
scan-retry uses the FILE If-Match and original full retry intent. Download first
authorizes, spools/verifies actual object length/hash, then reauthorizes immediately
before any client byte. No transaction/lock spans network. Stream only ready bytes
with attachment disposition, safe UTF8 filename, application/octet-stream,
nosniff/no-store and no reusable direct object URL. Corruption/missing storage
fails closed with a fixed infrastructure error, never user401 or raw SDK output.

## Task 2 exact HTTP contract

Routes are under /api/v1. Upload remains POST /tickets/{id}/attachments and
POST /work-items/{id}/attachments. GET on those same parent collections requires
the explicit unique purpose query: public|note for tickets, work for work items.
Only purpose, limit and cursor are accepted on a list. Limit1..100/default25;
cursor binds actor, exact parent and purpose. An unauthorized note-purpose list
is404, not a mixed list with a hidden-note count. The envelope is items,
next_cursor and can_upload, computed from current parent/action authority
independently of pagination. Creation authority never follows from page contents.

Global detail GET /attachments/{id} and content GET /attachments/{id}/content
resolve the concrete parent, then apply current parent/purpose authority. There
is no account-wide file catalogue. Hidden/foreign/private-purpose IDs are404.

Ordinary attachment metadata: id, owner_type(ticket|work_item), owner_id, purpose,
filename, media_type, bytes, state, policy_version, version, created_at,
can_download and can_retry_scan. No creator directory lookup, hash, object key,
engine/database identity, lease, attempt history or diagnostic string is exposed.
Use strict typed models and UTC timestamps. Detail ETag represents the file
version. States remain quarantine|scanning|ready|rejected|failed.

Upload receipt: owner_type, owner_id, attachment_id, bytes, sha256 and version.
Its version is the immutable initial file version1, not a promise that the scan
has not progressed. Upload returns201; a currently authorized protected replay
returns200 with the original receipt. Its ETag is the receipt's file version,
never a new parent version. Parent If-Match is part of the original upload intent.
The ordinary metadata read used for ACK compares immutable upload identity;
current scan version/status may have advanced. GET alone cannot acknowledge POST.

POST /attachments/{id}/scan-retries has strict empty JSON object {}, FILE If-Match,
Idempotency-Key and the existing Origin/CSRF/session protocol. No client result,
generation or engine parameter is accepted. Fresh successful retry returns201;
protected replay200. Receipt is attachment_id and version, preserving the version
created by that retry even after subsequent scanning. ETag matches that receipt.
Fresh retry requires failed state and current original-purpose write eligibility;
rejected malware has no manual release. Reuse current authority before replay,
checking fresh active/version/state eligibility only for a new effect. No parent
version advance. Generation/attempt history remains internal and immutable.

Reuse existing problem/error conventions for auth, origin/CSRF,404, protected
header/version/replay validation. Distinguish oversized413, unsupported request
media415, malformed byte/digest/query/name/type validation422 and bounded body
timeout408. Busy/unavailable/corrupt storage fails with fixed503/Retry-After;
never return an infrastructure fault as a user401 or expose SDK/path text.
Authorized not-ready downloads return409 without bytes. Malformed/repeated
payload-specific headers and malformed percent/UTF8 query input are refused.
Ordinary HTTP headers remain supported; unknown query fields do not.

## Concrete content links and outbound compatibility

Add optional attachment_ids (unique UUIDs, <=20) to existing public-message,
private-note and work-comment creation. Preserve old omitted-field fingerprints
and exact old events. Create content and immutable links atomically under identity,
parent and sorted file locks; validate ready, same exact parent and correct purpose.
Concrete composite FKs and deferred count constraints bind each link to its actual
message/note/comment parent. Store attachment_count at content creation, immutable
with its body, so a later INSERT cannot silently change an existing content set.
Legacy content has count0. No cross-context relinking or automatic public copy.

Public delivery review explicitly includes the exact saved public attachment IDs.
Omission retains the old no-file fingerprint; it cannot silently send attached
files an old client never reviewed. Protected replay needs no S3 refetch. A fresh
send preliminarily authorizes and prefetches/verifies selected public files OUTSIDE
DB transactions; final current authorization/version/link checks and wire freeze
are atomic. Notes/work files cannot enter SMTP by guessed ID. Preserve every
already-frozen wire, ID, receipt, timestamp and uncertainty/retry behavior.

New file-bearing wire_format2 uses standard-library MIME, exact saved file bytes,
safe filenames and encoded total<=26214400 bytes, one preparation per API process.
Legacy text-only format1 keeps its exact262144-byte cap and build_wire behavior.
Version the actual schema/immutability guards, not a future placeholder. Worker
transmits frozen bytes through the existing owner; no S3 network enters a DB
transaction or live SMTP DATA stage. First incoming root and current requester
reference rules stay exact. SMTP acceptance remains server acceptance only.

## Validation, rollback and continuation

### Task 3 exact content and delivery contract

TicketMessageCreate, TicketNoteCreate and CommentCreate accept attachment_ids as
an optional ordered list of at most20 unique UUIDs. Omission means legacy no-file
intent: exclude ONLY this new field from the old canonical request. Explicit []
is a distinct protected empty intent; null is422. Existing body requirements stay.
Current original-action authority and protected replay precede fresh file checks.
Fresh links require ready policy1 files on the same exact ticket/work item with
purpose public/note/work respectively. Hidden, foreign or wrong-purpose IDs are
indistinguishable404; visible non-ready assets are409. Lock identity before
authentication, then existing parent locks, then files in sorted UUID order.
Selection order is persisted separately from lock order. Files confer no grants.

Content reads add immutable attachment_count and ordered attachments summaries,
each strictly id, filename, media_type and bytes. Legacy content reads count0/[];
summaries inherit the full current content/parent/purpose read authority. Denied
note readers receive no summary or count. Ticket/message and ticket/note creation
receipts remain exactly their old ID fields. Work-comment creation retains its
existing content receipt with additive count/summaries; historical stored receipts
remain unchanged and deserialize absent new output fields as0/[]. Content body,
count and ordered concrete links are immutable. Count is0..20, positions0..count-1,
IDs unique per content. Composite FKs bind both content and files to their concrete
parent/purpose; deferred guards reject missing/extra links at commit. Existing
message_drafted/note_added/commented events remain byte-shape compatible even
when files are selected; no filenames/counts/IDs are added to those envelopes.

DeliveryCreate adds the same optional ordered attachment_ids review. Omission
keeps the exact old canonical request and permits only a message with no files;
explicit [] deliberately reviews no files, null is422. A fresh request must match
the saved public links in exact order or409 delivery_attachment_review_required.
Duplicate/over20 IDs are422. DeliveryReceipt/DeliveryOutput stay unchanged. Current
public-send authority, original headers and cached protected receipt precede any
storage access. Saved replay does not fetch files, regardless of later parent
activity/version, while current original-action/session authority remains needed.

A fresh send first validates current authority, parent version, sender/requester,
links/ready status and absence of another delivery. Reject raw totals>26214400
before fetching. At most one fresh file-bearing preparation per API process;
busy/storage failure/corruption gives fixed503 with Retry-After5, no partial
delivery/receipt/version/event. Verify each actual object length/hash through
S3Store.verified_spool outside ALL DB transactions. Reacquire identity/auth/parent/
sorted file locks and repeat all current authority/version/review/eligibility
checks before atomic freeze. No live scanner I/O is introduced. A revoked session,
grant or requester during prefetch prevents freezing. Cleanup spools on every exit.

Persist wire_format1 (default for every existing snapshot and all new text-only
messages) or2 (actual file-bearing MIME only). Format1 calls the unchanged
build_wire and retains its262144-byte bound. Format2 uses standard email MIME:
multipart/mixed, the same plain UTF8 quoted-printable body and contextual headers,
then base64 attachment parts in saved order, accepted original UTF8 filenames and
stored media types, exact decoded bytes. Encoded total<=26214400, including all
headers/boundaries. Wire format and wire bytes are frozen together; SMTP worker
continues sending only frozen bytes with existing lease/one-DATA/uncertainty/
timestamps. Existing incoming root/current requester reference rules apply.
Migration00026 refuses contraction with links, nonzero content counts or format2
history. Runtime API alone gains link SELECT/INSERT; worker gets no link table
or file-name grants. Upload/list request schemas advertise ticket public|note
and work work; ordinary metadata Purpose remains the context-wide union.

Actual private S3 authorization/conditional PUT/TLS/fsync/restart, real production-
profile signed/current ClamAV clean/EICAR/limits/encryption/update/refusal, streamed
API/session/CSRF/IDOR/note privacy, replay/races/atomic rollback, scan fencing/stop,
integrity before bytes, old/new real MIME and original wire regressions are required.
Use controlled fault endpoints for negatives, never a fabricated clean UI/endpoint.
Impeccable governs actual browser upload/selection/download/recovery and captures.
Extend complete packaged/resource/network/security/inventory/artifact proof. Prove
matching DB/object logical restore without assuming a retention/prune policy.

Additive migrations refuse contraction with file/link/attempt/history. Rollback
retains file-aware API/web/worker/provisioning, old formats and all durable objects;
older text-only writers must not silently drop attachments. No deletion to force
downgrade. Integrated hardening later exercises a compatible application pair and
encrypted consistent backup/restore. Final changed artifacts require actual target
qualification after the remaining MVP; Q02/Q09/Q11 retain real sizing/retention/
production storage decisions. Continue next with the separate incoming-MIME file
contract, then ticket/work links, automation, SLA, analytics and guarded import.

Policy1 scan outcome mapping: exact clean alone becomes ready. Known immutable
policy failures (infected, encrypted or limit) become terminal rejected with no
manual release. Transport, timeout, protocol, database and other unclassified
failures retry with the bounded generation budget, then become failed. A protected
failed retry creates a new generation; immutable prior attempts remain.
