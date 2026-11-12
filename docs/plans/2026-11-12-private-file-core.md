# Private file core implementation plan

> Execute with superpowers:subagent-driven-development, one implementer at a time,
> independent task gates and one whole-increment review. User already authorizes
> continuous development/direct main pushes without PR or routine approval pauses.

**Goal:** Staff can upload, scan, read and explicitly attach real private files to
public responses, private notes and work comments under current resource authority.

**Architecture:** Extend the modular monolith with concrete file ownership and
links, durable scan jobs and standard S3/ClamAV adapters. Existing authorization,
protected writes, SMTP frozen wire and browser session owners remain authoritative.

**Tech stack:** Existing Python3.12/FastAPI/SQLAlchemy/PostgreSQL/Redis/Next.js;
botocore1.44.1, baseline-built VersityGW1.11.0 and signed vendor ClamAV1.4.6-r0.

**Spec:** docs/adr/0037-private-file-core.md, master specification and affected
ADR0020/0028/0029/0034/0035/0036 contracts. Read actual owners before modifying them.

## Global constraints

- No production/provider/target operation, real data import or retention deletion.
- Preserve x86-64-v1. No -march=native, mandatory AVX/SSE4.2 or prohibited engines.
- No network I/O while holding DB write transactions/authorization locks.
- Current resource AND action authority, explicit client ceilings and note access
  apply to every upload, linked file, metadata row, download and receipt replay.
- Files never grant accounts/contact trust or inherit access through a ticket/work
  link. Private notes/work files cannot enter public SMTP by guessed identifiers.
- Preserve old omitted-field fingerprints/events and every existing frozen wire.
- Only an actual clean scan with fresh trusted definitions creates ready. Scanner
  failure/staleness never releases unscanned bytes. Policy1 preserves historical
  ready decisions during later scanner outages; current auth/storage integrity
  still gate every download/send. No access-time rescan or timeless-safe claim.
- Contracts before code, relevant real tests, exact source/evidence hashes and
  honest scope. No source/fixture/build mutation during active tests.
- Impeccable governs frontend work; preserve the incumbent Operate world.
- No target-per-slice homologation. Full changed-stack CPU proof follows the MVP.

## Review focus

- Revocation during object transfer must leave no published/downloaded private bytes.
- A prepared object is not a committed asset; lost POST and conflicting concurrent
  replay must retain original bytes/name/purpose/key/parent version and one result.
- Scanner completion after lease expiry/retry/generation change must not release it.
- Old clients cannot unknowingly send new files; no-file wire/fingerprint stays exact.
- Actual Redis/SQL/log/wire checks need channel-specific file/name/hash/credential
  canaries and real event completion, not a metadata guard disconnected from inputs.

### Task 1: Real private S3 and fail-closed scanner infrastructure

**Files:** Create apps/api/altvia/file_settings.py, file_storage.py,
file_scan_transport.py, file_storage_owner.py; tests/test_file_storage.py,
test_file_scan_transport.py; infra/storage.Dockerfile, clamav.Dockerfile,
start-storage.sh, start-clamd.sh, start-freshclam.sh, clamd.conf, freshclam.conf;
scripts/private_file_infra_proof.py and tests/test_private_file_infra_proof.py.
Extend pyproject/uv lock, Compose/secrets/example/runbooks, native guards and
all-service image/security/packaged workflows only where these actual services need it.
No attachment tables, HTTP file capability, UI or raw-MIME change in this task.

**Produces:** StorageSettings/ScannerSettings with strict secret/TLS endpoints;
concrete S3Store(settings), put_new(key:str, source:BinaryIO, *, size:int,
sha256:str)->None and verified_spool(key:str, *, size:int,sha256:str) as a context
manager yielding a verified BinaryIO. ClamClient(settings).scan(source:BinaryIO,
*,db_now:datetime,stop:Event|None=None)->ScanResult; frozen result carries fixed
clean/infected/failed disposition/reason and reported engine/database identity.
Fixed safe transport exceptions, no raw SDK/engine text to callers or logs.

- [ ] RED actual private S3 clients: verified TLS, anonymous/cross-bucket/object-list/
  delete/admin/policy denial, scanner write denial, absent/wrong conditional header,
  duplicate412 preserving bytes, size/hash corruption and credential non-disclosure.
  Use real standard server, not an emulated S3 implementation.
  For global ListBuckets, pinned internal IAM returns200: require empty actual
  buckets/continuation under explicit owned scope and zero service-owned buckets,
  with populated root/foreign negative controls. Never describe that as403 or
  weaken actual object-list/cross-bucket denials.
- [ ] Build the exact pinned Go source/hash and signed AV packages; actual version/
  native inventory, non-root/read-only/private volumes/networks/resource checks.
  Use native bucket policy and --fsync; validate conditional create-only semantics
  and restart. Standard-SDK owner bootstrap uses secret files/stdin, no argv keys
  or destructive reset. Unsupported required policy fails, never grants broader access.
- [ ] Implement strict VERSION/INSTREAM clients and production configuration from
  ADR0037. Pin engine, compare definition version/date before/after, reject stale/
  future/missing/malformed response and all non-clean outcomes. Actual signed current
  complete definitions/real clean+EICAR/limit/encrypted/update/refusal acceptance runs
  on adequately provisioned hosted Docker; controlled socket faults/unsigned fixtures
  do not substitute for it. Do not resize/restart the2048 MiB local Podman VM.
- [ ] GREEN focused adapters/proof guards; actual infra proof plus package/SCA/native/
  source/static gates. Preserve raw failures and scope. Commit; independent task
  spec/quality gate, archive and authorized publication; no target operation.

### Task 2: Persisted assets, streamed HTTP and durable scan lifecycle

**Files:** Create apps/api/migrations/versions/b46087000025_private_attachments.py,
apps/api/altvia/attachments.py,
attachment_schemas.py, attachment_api.py, attachment_scan.py and actual API/
runtime/worker/replay/race tests. Extend models/provision/main/config/activity/
worker, generated OpenAPI/TS and affected packaged fixture only as necessary.
No content-link or MIME-format placeholders before Task3.

**Consumes:** Task1's concrete store/scanner adapters, existing identity-before-auth
and parent lock/action owners, durable outbox/worker publication/recovery pattern.
**Produces:** actual Attachment/ScanAttempt ownership/state, typed paged parent
metadata/detail/download, binary upload receipt and protected scan-retry. Exact
routes/protocol/limits/DTO fields and state transitions are in ADR0037.

- [ ] RED real PG/API: strict streamed size/hash/type/name and duplicate headers,
  current client/project/note authority including admin negatives, current session/
  CSRF before body and after network, revoked transfer zero bytes, exact protected
  replay/body conflict/concurrent one result and atomic event failure/private orphan.
- [ ] Implement only ticket public/note and work contexts with concrete FKs,
  immutable key/hash/content metadata, file version and private strict operational
  events. No parent version advance for an unlinked asset. Upload fingerprint
  includes full actual content metadata and original parent version; receipt digest
  supports uploader ACK, never ordinary metadata hash/key exposure.
- [ ] Durable file_scan actor/backlog/recovery mirrors the real mail worker pattern.
  DB-clock60s token/generation fencing,8 attempts with bounded backoff, immutable
  history and protected failed-generation retry. Test stop/blackhole/skew/late clean,
  duplicate dispatch and restart. Grant only necessary object/scan columns, no note
  body/name or mail raw/preview/origin privileges. Preserve old worker events.
- [ ] Actual S3 spool/hash before scan and before client bytes. Strict clean alone
  becomes ready. Current authorization again before download; no direct URLs,
  unsafe filename/header, partial corrupt release, SDK errors or bytes in logs.
- [ ] GREEN affected real PG/API/worker/static/contracts/migration roundtrip+refusal/
  security/build gates, frozen hashes and fault/positive external-service evidence.
  Commit and independent task gate before Task3.

### Task 3: Concrete immutable content links and reviewed MIME2 delivery

**Files:** Create apps/api/migrations/versions/b46087000026_attachment_content_links.py
and apps/api/altvia/attachment_links.py;
extend ticket/work models/schemas/services/APIs, mail_delivery/API/schemas/transport
and real tests; regenerate contracts. Keep unrelated source owners intact.

**Consumes:** Task2 actual ready assets, scoped File receipt/detail, existing
message/note/comment creation and immutable public-delivery intent/freeze owners.
**Produces:** optional attachment_ids creation, ordered concrete FK links and
immutable attachment_count, authorized response summaries; explicit selected file
IDs in delivery intent and actual wire_format2. No incoming Case owner yet.

- [ ] RED same-parent/correct-purpose/ready guards, duplicate/max20/order, cross-IDOR,
  ordinary note writer and work contributor cases, atomic receipt+links+event
  rollback and SQL deferred count/immutability. Preserve all old omitted-field POST
  fingerprints, legacy counts0 and event envelopes exactly.
- [ ] Implement strict message/note/comment creation links under identity, parent,
  sorted file locks. Concrete composite FKs and deferred count guards prevent
  later inserts from changing an immutable content set. No copy/relink ACL shortcut.
- [ ] RED actual TLS old text-only wire equality and new MIME decoded file bytes/
  filenames/order, private-purpose refusal, expected original incoming root/current
  requester context, max encoded26214400 bytes, and unauthorized S3-prefetch denial.
  Old format1 remains262144 bytes. A client omitting a file review cannot send files.
- [ ] Prefetch ready public objects outside transactions, then repeat current
  authority/version/link checks and freeze atomically. Saved replay does not fetch
  S3 again. Existing worker sends frozen wire, preserving one DATA, uncertain/retry/
  stop/restart semantics and old timestamps. Test revoke during prefetch, lost ACK,
  storage failure/corruption and mixed-lock concurrency without a network lock.
- [ ] GREEN affected real domain/SMTP/migration/runtime/static/contract gates;
  independent task source review and checked commit. Do not mark full incoming-MIME
  file support complete; that is the following separate contract.

### Task 4: Real file browser flow in the incumbent interface

**Files:** Add web attachment client/components and real browser tests; extend
ticket public-message/note and work-comment owners plus guarded fixtures. Use
generated types and existing session/protected-write/review/query owners.

**Consumes:** actual Task2/3 routes/DTOs/capabilities, mutable scan status and
immutable content-link lists; Task3 actual outgoing MIME/send review.

- [ ] Impeccable context/brief/craft floor first. Native file selection, honest
  sending/quarantine/scanning/ready/rejected/failed states, error/retry/readonly/
  empty states, current download and explicit attachment review. No decorative
  progress/ETA, hardcoded status, public object URL or new visual world.
- [ ] Retain original File/Blob, digest/name/purpose/key and reviewed version across
  uncertain HTTP and read recovery. Protected replay plus current single metadata
  read confirms it; historical GET alone cannot ACK an original operation. Dispose
  blobs/object URLs/private caches on session changes; no browser persistent storage.
- [ ] Real PG/Redis/API/S3 browser upload/download/draft/note/comment/review/send,
  malicious/pending/denied/private-note/revoked roles, failed read/replay and native
  keyboard/axe/themes/mobile overflow. Controlled scanner fault protocols are
  explicitly distinguished from actual signed production-profile ClamAV acceptance;
  no mocked HTTP file-status endpoints or manual clean flags prove that acceptance.
- [ ] Relevant check/build/generated gates, frozen affected then full browser once;
  no source/fixture/build mutation during tests. Root owns independent Impeccable
  finish/documentation and source reviews, fixes, archive and publication.

### Task 5: Packaged files, restoration and immediate incoming-file continuation

- [ ] Extend existing packaged owners with a NEW synthetic file context, actual
  S3/TLS/production-profile current signed ClamAV and real browser/worker upload/
  clean+EICAR/timeout/retry/private note/public MIME2 flow. Preserve all old fixtures,
  incoming root, exact old wires, clock, role and active-SMTP shutdown assertions.
- [ ] Actual current credentials/table AND column denials, decoded JSON/Redis and
  child/main/service diagnostics with channel-specific canaries AFTER relevant
  delivered+processed events and after API/PG/S3/worker recreation. Check filename,
  file bytes, hash, key, secret and private-note leakage; do not ban expected public
  bytes from intended downloaded/MIME channels.
- [ ] Matching DB/object logical snapshot and isolated restore verifies every
  referenced length/hash, links/current ACL and frozen wire. No destructive prune
  or retention assumption. Full encrypted backup/compatible image rollback remains
  the later integrated-hardening gate, explicitly tracked and not called tested here.
- [ ] Whole-increment independent review, one consolidated fix wave/scoped verdict,
  exact all-service inventories/security/full CI logs and sanitized hash-bound
  artifacts including the new proof JSON. Local2GiB limitations remain honest;
  actual new images do not inherit older CPU qualification. No target SSH.
- [ ] Record accepted core separately from incoming-MIME attachments. Immediately
  select/implement the owner-bounded incoming-MIME file contract using these actual
  interfaces, then continue remaining MVP. No continuation question or final-MVP claim.
