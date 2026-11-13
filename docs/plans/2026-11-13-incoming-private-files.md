# Incoming private files implementation plan

> For agentic workers: use superpowers:subagent-driven-development, one implementer
> at a time with independent task review and one final increment review. The user
> already authorizes continuous MVP work/direct main publication without PR.

**State:** Ready for authorized incremental execution. ADR0038's fresh builder
check found nothing important left; finite MIME parameter choices are pinned.
Private-file core's exactc12d6e1 corrected full CI passed:1266 API cases/3 explicit
native console skips,175 browser,both packaged/security jobs and actual signed
recreation/matching4-object restore. H4 source correction is independently approved.
Root recorded the preflight interfaces/conflicts and remains responsible for
each task's independent gates. This plan is a contract, not implemented features.

**Goal:** Supported incoming files survive attested triage and ticket promotion,
with real private storage/scanning, immutable ownership and current scoped access.

**Architecture:** Extend the existing attachment aggregate with one concrete case
parent. The immutable case-to-incoming relationship owns its frozen file set;
reuse current storage, worker, parent authorization and private-download protocols.

**Tech stack:** Existing Python3.12/FastAPI/SQLAlchemy/PostgreSQL/Redis/Next.js,
standard-library MIME, accepted S3/ClamAV adapters. No new dependency/image/daemon.

**Spec:** docs/adr/0038-incoming-private-files.md, master specification and affected
ADR0030-0033/0036/0037. Contracts precede code; real-provider policy stays Q03/Q16.

## Global constraints

- Preserve x86-64-v1. No -march=native, AVX/SSE4.2 requirement or prohibited engine.
- No target-per-slice testing, production rollout, real import or retention delete.
- No raw/source/poll/preview/origin runtime grants, worker filename/parent grant,
  sender proof from mail/file metadata, automatic public copy or invented uploader.
- Current case queue role AND client ceiling, plus resulting-ticket authority
  after promotion, govern every new file projection/download/retry/replay.
- Preserve all old text interpretations, case/promotion fingerprints/receipts,
  strict legacy events, immutable content and already-frozen SMTP bytes.
- Raw2097152 bytes/entities64/depth8, file count20; actual core type/name/byte policy.
- Only actual trusted clean scan releases bytes; reuse generation/DB-clock fencing.
- No network under DB write/authorization/source locks. Recheck after storage I/O.
- No source/fixture/build mutation during tests. Preserve failures/source hashes.
- Impeccable governs frontend; use the accepted Twenty-inspired Operate world.
- User opted out of routine questions; record real policy questions and continue
  safe independent work. Do not invent provider, retention, mapping or SLA policy.

## Review focus

- A storage failure racing a contradictory origin still commits its invalidation;
  source/case locks never span PUT. Task2 owns the actual blocked-transfer test.
- An alias/replay of a legacy case cannot silently gain files or change a receipt.
  Task2 owns legacy0/new1 alias/concurrent publication and immutable-set tests.
- A case invalidated during download prefetch releases zero private bytes. Task3
  owns actual S3 blocking/recheck, including promoted ticket/customer revocation.
- A visible incoming ID never becomes a public outgoing attachment. Task3 owns
  guessed-ID link/send refusal before any S3 prefetch, retaining old MIME wires.
- Reloaded/failed/retried UI uses current file/session state without inventing ACK
  or showing timeless safety. Task4 owns real failed-response/session/browser cases.

## File ownership map

mail_mime.py owns bounded pure interpretation. A focused mail_case_files.py owns
staged object metadata and atomic case-file publication, not API authorization.
mail_cases_owner.py keeps the sole contextual attestation/replay/collision protocol.
attachments.py/attachment_api.py remain the current parent and byte-access owners;
mail case/conversation readers consume their authorized file projections.
Models/provision/migrations enforce concrete ownership/count/immutability/grants.
Existing frontend case/conversation/download owners present the new actual data.

### Task 1: Bounded version1 file interpretation, unchanged parser2 text

**Files:** Modify apps/api/altvia/mail_mime.py. Create
apps/api/tests/test_mail_file_mime.py; reuse test_mail_mime.message/multipart.
No schema, HTTP, owner publication or UI in this pure interpretation task.

**Interfaces:** Produce frozen ExtractedFile(filename:str,media_type:str,content:bytes)
and ExtractedFiles(status:Literal["complete","unavailable"],files:tuple[ExtractedFile,...],
reason:str|None), plus extract_files(raw:bytes)->ExtractedFiles. Reason is exactly
file_structure|file_count|file_size|file_encoding|file_filename|file_type|file_parameter;
complete has no reason, unavailable has no files. No text/body/provenance output.

- [ ] RED accepted raw multipart text + base64 PDF and RFC2231 UTF8 filename:
  assert status==complete; len(files)==1; exact original decoded bytes/name/type;
  normalize(raw) equals its existing parser2 result before/after extraction.
- [ ] RED every supported actual core type/encoding and20/21 candidates; empty
  file, raw2097152/2097153 bytes, depth/entity/header bounds, malformed encodings,
  mixed good/bad set, attached containers and unsupported/unsafe names. Assert
  unavailable/files==() and fixed reason; never partial files or altered text.
- [ ] RED plain/single extended names, allowed charset aliases/language tag,
  invalid percent/bytes, conflicting declarations, raw UTF8 header, RFC2047 and
  continuation rejection. Fixtures stay within the unchanged raw bounds.
- [ ] Implement using existing bounded MIME helpers, stdlib decoding and core
  filename/media validators. Keep normalize/parser2 behavior/version untouched.
- [ ] GREEN `uv run pytest -q apps/api/tests/test_mail_file_mime.py apps/api/tests/test_mail_mime.py`;
  lint/format affected source, record exact freeze/results and commit. Task review.

### Task 2: Immutable case-owned assets and atomic owner publication

**Files:** Create apps/api/migrations/versions/b46087000027_incoming_private_files.py,
apps/api/altvia/mail_case_files.py and apps/api/tests/test_mail_case_files.py.
Extend apps/api/altvia/models.py, provision.py, mail_cases_owner.py and
attachment_scan.py in that same altvia directory; infra/compose.files.yaml,
docs/runbooks/attested-incoming.md, apps/api/tests/test_mail_cases.py and
apps/api/tests/test_attachment_scan.py.

**Consumes:** Task1 extract_files; existing require_owner, exact CaseReceipt and
attestation intent, S3Store.put_new/verified_spool, current scan actor/history.
**Produces:** Frozen PreparedCaseFile(filename:str,media_type:str,bytes:int,
sha256:str,object_key:str) and PreparedCaseFiles(status,files:tuple[PreparedCaseFile,...],
reason) with Task1's fixed complete/unavailable/reason semantics; stage_case_files(extracted,
storage_file:Path|None)->PreparedCaseFiles outside DB and
persist_case_files(db,case,prepared)->tuple[Attachment,...] inside owner transaction.
Extend attest_case's existing positional signature with keyword-only
storage_file:Path|None=None. Text-only/unavailable/existing cases need no S3 config.
CLI reuses optional ALTVIA_STORAGE_FILE through owner-specific DatabaseSettings;
load/validate it only after preflight and only when actual files need storage.

- [ ] RED actual PG checks: exact three-parent/provenance rules, owner-only case
  INSERT, unique ordered positions, deferred count equality/immutability, old
  staff creator requirements and legacy0 defaults; migration preservation/refusal.
- [ ] RED actual worker credentials still claim/finalize a case asset with no
  case-table/parent/name grant; creation-only count/provenance checks must never
  run for ordinary scan updates. Do not repair a trigger by broadening grants.
- [ ] Add case file_extraction_version/file_set_status/file_count/private fixed
  file_rejection_reason
  and attachment case FK/position, creator-null-only-for-case constraints. Reuse
  existing JSON identity guards. No raw grants or extra incoming-link table.
- [ ] RED real PG/S3 new complete/unavailable/empty publication, legacy replay,
  exact alias, conflicting bytes, concurrent one result/set, contact/version
  change, event/count rollback and private orphans after failed final checks.
- [ ] Refactor the EXISTING locked attestation protocol into its shared preflight/
  final helper. Existing replay/alias/collision finishes before storage. A new
  preparation has no DB effect. Stage objects outside locks; final checks repeat
  current context and commit case/header/assets/origin/version/audit/outbox once.
- [ ] Construct the immutable file header on the NEW case before its first INSERT/
  flush, then persist ordered assets/events. Never update a flushed case to add
  its header or disable an identity/count guard to make publication succeed.
- [ ] RED block actual S3 PUT and concurrently create contradictory context;
  include failing PUT/configuration. Assert invalidation/origin commits even when
  storage fails; still-new storage failure acknowledges no case. No timed guess.
- [ ] Emit only owner file.uploaded schema2 (null actor/management_command/file ID/
  quarantine); retain exact schema1 user/worker events and existing case events.
  Prove strict private consumption/dedup/no activity and unchanged narrow worker
  columns plus table/column/actual-query denials. Reuse actual scan lifecycle.
- [ ] Add one finite owner-tool Compose profile using existing image, owner DB,
  restricted API S3 writer/CA and internal networks; ordinary migrate stays without
  those extra credentials. Validate Compose/resources and fixed CLI error/stdin
  discipline; no root S3 credential, new daemon or dependency.
- [ ] GREEN affected real PG/API/S3/worker and migration/CLI tests plus existing
  mail case/normalizer/scan regressions. Record exact boundaries, commit and task
  source/spec/quality gate before Task3. No manual ready/production claim.

### Task 3: Current case/ticket authority and additive file projections

**Files:** Extend apps/api/altvia/attachments.py, attachment_schemas.py,
attachment_api.py, mail_case_api.py, mail_case_schemas.py and mail_promotion.py in
that altvia directory; docs/contracts/openapi.json and
apps/web/src/lib/api.generated.ts. Create apps/api/tests/test_mail_case_file_api.py;
extend apps/api/tests/test_attachment_delivery.py and test_attachment_links.py.

**Consumes:** Actual case-owned assets/header, existing scoped_case/readable_receipt,
ticket visible/scoped/write authorities and ready-file download/retry owners.
**Produces:** CaseFileSet(extraction_version:0|1,status:legacy|complete|unavailable,
items:list[AttachmentOutput]) and case_file_sets(db,actor_id,case_ids)->dict[UUID,
CaseFileSet], bounded/batched using current case and resulting-ticket queries.
Optional files block on CaseDetail and IncomingMessageOutput, not CaseSummary.
Use explicit actor_id in incoming projection helpers. Suppress entire hidden
block/count; no direct raw/private-reason lookup or new collection route.

- [ ] RED current case queue+client ceiling, platform-admin negatives, promoted
  ticket scope, private-purpose/cross-ID errors and legacy/unavailable fixed states.
  Assert existing list shape, receipt/fingerprint/event/wire compatibility.
- [ ] Extend read DTO owner/purpose with mail_case/incoming while keeping upload
  inputs/filters/receipts staff-only. Refactor internal Parent to authorized
  owner-ID/version/capability values so case reads never hydrate private ORM
  columns. Explicitly handle all three parents, no work-item fallthrough.
- [ ] Implement batched projections (bound query growth with multiple cases),
  global detail/content resolution and current invalidation checks before AND
  after object prefetch. Visible invalidated content is409/no bytes; hidden404.
- [ ] RED actual S3 revocation/collision during download, original receipt replay,
  integrity failure and session loss; assert zero private bytes. Keep legacy
  ready-file outage policy and transfer limits; no access-time scan or direct URL.
- [ ] RED manager-only current case failed retry and protected FILE protocol,
  denied agent/viewer/inactive/invalidated/closed/promoted hidden targets, revoke
  on saved replay and unchanged generation/history/fencing. No malware release.
- [ ] RED visible incoming asset cannot link/send as public/note/work; assert
  refusal before S3 and exact prior frozen wires. No automatic forwarding.
- [ ] GREEN affected auth/projection/SMTP/scan tests and generated contracts,
  lint/format/type/migration gates. Commit and independent task review.

### Task 4: Real triage/conversation UI and consolidated incoming-file proof

**Files:** Extend apps/web/src/components/mail-cases/detail.tsx,
apps/web/src/components/tickets/messages.tsx, apps/web/src/components/attachments.tsx,
apps/web/src/lib/attachments.ts and apps/web/src/lib/mail-cases.ts; use existing
generated API types, apps/web/tests/mail-cases.spec.ts and
apps/web/tests/attachments.spec.ts. Extend scripts/browser_incoming_fixture.py,
scripts/container_smoke.py and scripts/packaged_file_proof.py's shared snapshot;
add a focused scripts/packaged_incoming_file_proof.py if needed to extend the
actual native incoming context without duplicating packaged_smtp_proof.py's
existing ownership. Use current session/protected-write/query owners. No new world.

**Consumes:** Task3 scoped files blocks/capabilities and existing global byte/retry
routes. Core actual storage/scanner/browser/MIME/restore owners remain the seam.

- [ ] Impeccable context/brief/craft workflow first in accepted Operate world.
  Add read-only incoming file sets with safe original names and honest per-file
  state, current download and manager-only failed retry. No case upload/inline
  renderer, count inference, persistent File/Blob cache or decorative progress.
- [ ] RED real PG/Redis/API/S3 browser: raw multipart -> owner attestation ->
  triage files -> promotion -> same immutable incoming set -> exact download;
  pending/rejected/failed/unavailable/legacy, current denied roles and session
  disposal. Original protected retry replay plus current read acknowledges intent;
  a GET alone cannot acknowledge an uncertain POST. Cover keyboard/axe/themes/mobile.
- [ ] Add a NEW packaged synthetic incoming-file context under --files using
  existing owner tool and actual signed-current scanner. Preserve all old contexts,
  root references, wires, identities, clocks and deliberate session invalidations.
  Reuse core's known fresh actor-bound proof session rather than stale cookies.
- [ ] After actual delivered/processed file events and recreation, check every
  incoming name/bytes/hash/key/credential canary in decoded metadata/diagnostics
  and exact API/worker table AND column/query denials. No raw channels in artifacts.
- [ ] Extend the EXISTING matching snapshot/restore owner with concrete case file
  identity/header and immutable incoming relationship. Verify every referenced
  object/link/wire/current ACL after isolated restore, with unchanged old401/fresh
  session requirements. No duplicate snapshot protocol or production retention.
- [ ] GREEN scoped then full relevant browser/build/contracts/security/native
  gates; exact hosted signed combined evidence with hashes and complete logs.
  Local controlled faults stay distinct from signed-profile success; no local2GiB
  VM resize or per-slice target operation. Independent source and Impeccable finish
  reviews, one increment review/fix disposition, docs/roadmap update and publication.
- [ ] Record incoming-file development acceptance separately from final CPU/
  encrypted backup/compatible rollback/real-provider gates. Then continue actual
  ticket/work links and remaining MVP without asking whether to continue.

## Planning self-check and execution boundary

All ADR0038 sections map to one task: pure interpretation1; concrete persistence,
owner/collision/events/rollback2; authority/HTTP/compatibility3; UI/native integrated
acceptance4. Each review-focus condition has a named owning test above. No future
provider, retention, public forwarding or policy framework is introduced.
Exact source values/types travel in each task brief; use existing real disposable
PG/Redis/S3 launchers, not invented credentials or mocked status endpoints.

The private-file core gate and builder check are closed. Root must initialize/
verify this plan's own SDD workspace, reconfirm its recorded preflight and extract
Task1 brief before dispatch. Builder-delegated finite choices are in ADR0038. No
fresh human approval is needed for this already authorized development sequence;
real unresolved organizational policies remain registered and unexecuted.
