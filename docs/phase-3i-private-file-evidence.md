# Phase 3I private-file development evidence

Updated 2026-11-12. ADR-0037 and its plan preceded implementation, following the
accepted ADR-0036 incoming conversation. Infrastructure, usable file functionality
and final qualification are separate gates. No production or real-data operation
is implied.

## Task 1: Private storage and scanner infrastructure

Contracts: 0ef1187, with native bucket-list/conditional-operation clarifications
e139f86/c6ce6a8. Initial implementation046eacf; scoped corrections1c4e134.
Pinned VersityGW S3/POSIX, standard botocore and signed vendor ClamAV are present.
There are no attachment tables, HTTP file routes, file UI or MIME2 at this boundary.

Actual isolated local storage tests verified TLS, immutable conditional creation,
integrity before release, API/scanner permissions, administrative/cross-scope
denials, private non-root execution and restart preservation. Native global
ListBuckets honestly returned empty200; actual object enumeration was denied.
Same-scope conditional native copy/multipart completion created new objects;
existing destinations and foreign contexts were refused. The adapter stays PUT/GET.

The initial task passed42 Linux adapter/protocol checks,17 proof/inventory checks,
four XML-refusal cases and six native Go-package checks. The correction passed39
focused checks after eight failing RED cases. Ruff, strict mypy and package build
passed. Source SAST has18 LOW/zero blocking findings; secret scan zero. These have
separate source scopes, not repeated full-application acceptance.

Initial local SCA found an UNKNOWN OpenPGP advisory in an upstream module. The
command did not import that package; the build was also corrected to the exact
verified fixed module. Final pre-review API/storage/ClamAV reports have zero
vulnerabilities on the same retained database. Those historical images do not
qualify later fault-handling/proof source or all seven hosted images.

## Independent review and exact evidence

The first specification/quality review found three Important issues: Windows
output hashes described normalized text rather than saved bytes; timeout/cleanup
could lose command evidence; spool/admin-response faults could escape safe error
handling. Commit1c4e134 addresses them with focused real-child/injected-fault tests.
Scoped independent re-review marked all three ADDRESSED, with no new breakage.
The controller also verified all38 supplemental artifact/five source hashes; the
reviewer independently verified the15 real-child fixture hashes.

The controller verified323 initial evidence hashes and29 source hashes/Git blobs,
then38 correction artifacts and five source hashes/Git blobs. All passed. The old
storage proof's own manifest nevertheless had26 mismatches among42 raw streams;
universal-newline comparison found zero differences. This actual byte-evidence
defect remains historical. Original manifests, failed audit and supplemental
diagnosis are preserved. New capture logic records exact bytes, explicit timeout
outcomes and separate original/sanitized bindings. Controlled tests do not replace
a new actual hosted run.

Private evidence is retained outside Git in this plan's ignored workspace,
.superpowers/sdd/2026-11-12-private-file-core/. It preserves failures, freezes,
stream-capture limitations and reports/reviews. Durable archive/hosted identities
will be recorded after those gates. No raw workbook, secret directory or production
log enters Git.

## First hosted attempt: f171dfa

Source43228875977, images43228875927, browser43228875840 and API43228877537
passed. Results:1098 API in653.43s,154 browser in4.7m,18 LOW source findings/
zero blockers/secrets and seven nonempty zero-vulnerability inventories. Inventory
sizes are API72/PostgreSQL49/ingress70/web43/Redis16/storage107/ClamAV38. The
image-security build identities are separate from packaged runtime identities.

Container run43228876420 failed in the new private-file-runtime job131219039655;
the existing api-runtime job131219040043 passed all its packaged regressions.
The new job passed56 focused tests in6.20s and52 actual storage checks/restart/
Docker storage cgroups. All18 source hashes matched immutable f171dfa Git bytes;
all50 command-stream hashes matched saved artifact bytes. The earlier byte-capture
correction therefore has actual hosted evidence, while AV acceptance failed.

Freshclam command22 exited2 because native log-file opening refuses the configured
/dev/stderr symlink: Symbolic link loop. The corresponding clamd log configuration
requires the same native foreground-console correction. No complete definitions
or actual scan/reload succeeded in this attempt. The intentional pre-bootstrap
command9 exit1 was expected; cleanup commands succeeded.

All six full decoded job logs were inspected. Their first URL sanitizer missed
empty-username Redis credentials; the correction and safe review copies are
recorded below. The original console copies remain private historical evidence.
Action deprecation/cache-reservation and disposable local-initdb diagnostics are
nonblocking runner conditions. All four downloaded artifacts matched GitHub ZIP
digests; original incoming/outgoing proof JSON remains retained. The complete
13-entry hosted archive ci-f171dfa.zip is1916945 bytes, SHA256
bf1ffa39668ff1d4d4a395f5cb3b0cdefa9396af29706d8ce83af6cc94c5c081,
at C:/Users/wagne/.codex/state/evidence/private-file-task1-f171dfa/. Its manifest
explicitly records NOT ACCEPTED/H1. Earlier immutable local archives there are
source-f171dfa.zip551 entries/SHA256
cbc3f3105a1eb7338d0aeb79b438d41ba1a5c3c257af945755f4a45c0cbbfd92
and local-evidence.zip376 entries/SHA256
851d4936e031ad552c214eb9a20d776b2408a033ff45a516d6f0e65c44d2fef7.

H1 is corrected in5c722da by leaving the native file log unset and retaining
foreground console logging. Actual pinned-image offline negatives reproduced both
logger failures before the fix. Final15 focused checks, including three native
cases with mounted corrected configuration, passed. Updater initialization reaches
the expected refused loopback download; clamd reaches the expected missing-
definitions refusal; the foreground updater handles bounded TERM. No AV positive
is inferred. Scoped independent re-review marked H1 ADDRESSED/no new breakage.
The controller verified52 supplemental artifacts and three source hashes/Git blobs;
the reviewer independently verified52 artifact hashes. Existing failed hosted
evidence remains immutable. The following new hosted run closes that gate.

## Accepted Task 1 infrastructure: a7628bf

All five exact-source workflows passed: Source43232628427, Images43232628499,
Browser43232628677, Containers43232628402 and API43232628893. API1098 passed/
three explicit opt-in native skips in664.25s; browser154 passed in5.1m. Those three
native logger checks passed locally with the pinned image/final mounted config;
the separate required actual signed-profile job131231670234 also passed. Source
has18 LOW/zero blockers/secrets; seven nonempty inventories retain zero reported
vulnerabilities, with the same named package counts above.

Actual project altvia-files-03988b1e50 verified52 storage checks/restart and real
Docker cgroups/isolation for storage, clamd and updater. Full signed/current
definitions loaded in ClamAV1.4.6: daily28181 dated2026-11-12T06:27:14Z. Clean was
clean, EICAR infected, encrypted and expanded-limit files refused; oversize, stale
clock and stopped-scanner controls refused release. All three vendor database
signature checks reported Verification OK. A real signed daily replacement caused
the daemon to reload3628258 signatures; the same actual scan cases passed after
reload. This is engine/database observation, not cryptographic service attestation.

All18 source hashes matched immutable a7628bf Git bytes; all132 stream hashes from
66 commands matched actual artifact bytes. Expected nonzero commands were only
the pre-bootstrap RED and stopped-scanner refusal. Private readonly/non-root/no-
port controls and real resource limits passed. Updater alone retains definition
egress. Runtime image IDs and independent image-scan IDs are retained separately;
no equality or target-CPU qualification is inferred.

All six full decoded logs and four digest-verified GitHub artifacts are
in the13-entry ci-a7628bf.zip archive,1949704 bytes, SHA256
0d0433e9a6254d4a5d5b59fd9e61c3fbca691c1486fcb8777ab165efdc4cca5e,
beside the earlier immutable evidence. Artifact13951018531 contains136 entries,
including the full new manifest/streams/inventories; ZIP SHA256
2da72829ff07a63c85b5d0a3bb2e0c999b16bff79fa91ef3a6c19f47772b4a47.
The old incoming/outgoing proof JSON and packaged regressions also passed. Task1
is accepted; this is still infrastructure, not the complete file feature.

## Console evidence correction and safe review copies

The first controller URL scrubber required a nonempty username and missed
temporary synthetic Redis credentials in the API/browser console logs. Revised
audit found 31 matches per hosted attempt. No credential value was emitted by
that audit, and no production credential exposure is established. The original
console files and ci-f171dfa.zip/ci-a7628bf.zip retain their historical hashes and
are marked private-only. They must not be shared as sanitized review copies.

Use these supplemental archives in the same private evidence directory:

- ci-f171dfa-sanitized-v2.zip: 14 entries, 1918343 bytes, SHA256
  334821c5f3b69e9737151b832f8c96fb0ea36577eaa92c82a94e7044545378ae.
- ci-a7628bf-sanitized-v2.zip: 14 entries, 1951088 bytes, SHA256
  746a7c0a922198d7582ccc035e719c02cab8ac67bbb4536692e4e044ecbe5a58.

Each includes an audit binding the original and corrected hashes and 31 explicit
redactions; the revised URL audit and ZIP CRC pass. Actual command-byte evidence,
source hashes, downloaded GitHub ZIP bytes and all validation outcomes remain
unchanged. Old evidence was preserved rather than rewritten into a false claim.

## Task 2 persisted assets: reviewed local candidate

Contracts 202ea91/4852ba2 and CI-boundary 9b40e75/b0f9f23 preceded source.
Core d9e9412, history/ingress correction 3f3ebbe and CI harness 8c132fd implement
migration 00025, concrete ticket-public/note or work assets, real binary upload,
scoped metadata/download, protected retries and durable scan jobs. File uploads
preserve the parent version. Original receipts survive scan progression; current
resource/action/session rights and actual object integrity still gate every use.
Private events never enter shared activity, and worker grants exclude filenames,
purpose, uploader, note bodies and raw/preview/origin data. No content links,
MIME2, incoming-file owner or UI were introduced at this boundary.

The original full local run had 1054 passes, 76 setup errors and three explicit
native-image skips. All errors were missing OpenSSL: 44 raw exceptions and 32
explicit TLS-fixture guards. Exact 76-node recovery passed after adding only the
matching CLI to the ignored test image; all existing SSL/native packages stayed
unchanged. Two process-clock skew cases then passed. The controller independently
verified 1132 distinct passing nodes, three skips and 215 identical nonprivate
inputs across full/recovery cohorts. The original invocation remains exit 1;
the mandatory current-source hosted full run remains required.

Actual PG/S3/Redis checks cover revocation after transfer, concurrent receipts,
private orphan preservation, two-transfer/body bounds, corrupt zero-byte refusal,
immutable history/runtime column grants, database-clock lease/generation fencing,
late/stop results and definition age after final lock. Actual HTTPS accepts a
32 KiB binary upload while ordinary 32 KiB JSON retains 413. Source SAST has
22 LOW/zero blockers; tracked-source secrets zero. The pre-review API image has
72 inventory entries/zero vulnerabilities on the retained scanner DB. Its outer
Windows text-copy helper failure and byte-exact successful scan are both retained.

Independent review found one Important UTF8-BOM text-signature bypass, fixed in
e7fcefc with five real PG/S3 RED cases and eight focused GREEN checks. The fix
normalizes only the sniffing view; legal BOM text retains exact stored bytes,
digest and receipt. Scoped re-review marked P2 ADDRESSED/no new breakage. A Minor
overbroad route-purpose enum remains explicit next-contract work; runtime guards
already reject owner-incompatible purposes.

Hatch sdist exclusion 88a7563 also resolved an ignored public-template copy in the
source package. Actual content checks preserve the root template/source/00025,
exclude the private tree and prove every wheel member's bytes unchanged. An early
setup log was overwritten by helper filename reuse; the report distinguishes that
limitation from the retained product RED/GREEN and complete full/recovery records.
No package was published.

The controller verified 291 initial artifacts/all 26 changed source hashes/Git
blobs/report, then 27 fix artifacts/two changed sources/report. Initial immutable
source-88a7563.zip and 301-entry initial-local-evidence.zip remain at
C:/Users/wagne/.codex/state/evidence/private-file-task2-88a7563/; their hashes are
f96f47444d28741fc6ae09c3bc86645adbb4457f4244c9ab90cff224df4126ef and
0a0b48c8a97add8a08a7e3843364c30afd8c5a28f277cbbfad7b726147a3207e.
The initial archive explicitly records the pre-fix review status. Final exact-
source hosted gates and the real new S3/full-suite CI harness remain pending.
Reviewed source-e7fcefc.zip has 561 entries/SHA256
e99a67876ecbb9590f7c2286a9eb4f14c8aa2d3f0ac19921593e90af4cd48fa3;
35-entry fix-1-evidence.zip has SHA256
86c9e3c42a981453bb0cca15cae24f3d0b81aad9e46a669b08ed8875ee6152df.
Both preserve the pending-hosted scope and the deferred Minor explicitly.

## Task 2 hosted startup failure and reviewed H2 correction

Source 515d379 passed Source43254378386, Images43254378335,
Browser43254378524 and Containers43254378343. Browser154 passed in5.4m;
source22 LOW/zero blockers/secrets and all seven nonempty inventories reported
zero vulnerabilities. Existing packaged regressions and the actual signed/current
ClamAV producer/reload proof passed. These do not substitute for the API gate.

API43254378356/job131308515614 failed before pytest: Docker command5 exited125
because a static endpoint requires a user-configured subnet. No API test ran.
The subsequent absent-container stop1 is benign idempotent cleanup. The controller
inspected all six complete decoded logs, verified197 failed-API source hashes and
14 raw streams, plus18 signed-infrastructure source hashes and132 raw streams.
The revised credential-URL audit found zero remaining matches in sanitized logs.

Five digest-verified downloaded artifacts and those logs are retained in
ci-515d379.zip at the Task2 evidence directory above:13 entries,1936532 bytes,
SHA256 b10d31d5a01d2da45d0c6cd2874a5b579264b518480f177c8f52b72b6cf0b86e.
Its status remains NOT ACCEPTED/H2. Failed API artifact13959848806 has15 entries,
SHA25699f96239b21b0046105928c93d8dfd49b69669937fb68094d96cf071ad5013e9.

Fix cb49780 inspects existing native network subnets, selects a nonoverlapping
private /24, explicitly requests an internal bridge/subnet and verifies the created
boundary before assigning its TLS endpoint. Only known overlap races retry,
with fresh inventory and at most three creates. No host/daemon network, DNS, SSH,
published port, dependency or production configuration changed.

Five new construction/preflight RED cases failed before implementation; ten
focused GREEN controls and Ruff/format passed. Actual Podman private S3 startup,
verified IP-SAN TLS, native bootstrap and original27-byte PUT/GET passed using the
accepted prebuilt storage image. This is Podman evidence, not Docker acceptance.
Independent scoped review marked H2 ADDRESSED, specification/quality PASS and no
new breakage. Root verified52 artifact hashes, two source hashes/Git blobs,
seven frozen runs and the report digest. Source has only CRLF/LF checkout
normalization relative to the exact committed Git blobs.

Reviewed source-cb49780.zip:561 entries,1355338 bytes,SHA256
d70709ab558de18697d467e358af93296949c5a171957299558dd549535c8774.
fix-2-evidence.zip:60 entries,265179 bytes,SHA256
74d55a8c1d32db151d9845caac602a6feee27d216eb92949cad1b0887dec19e6.
Both CRC pass and explicitly retain the pending hosted-Docker/full-API gate.
Actual cb49780 hosted validation is recorded below; Task2 stays open.

## Task 2 hosted native-inventory failure and H3 correction

All four non-API cb49780 workflows passed: Source43259514648,
Images43259514902, Browser43259514747 and Containers43259515676. Browser154
passed in4.6m; source22 LOW/zero blockers/secrets and all seven named nonempty
inventories retain zero vulnerabilities. Actual signed/current scanner/update/
reload and existing packaged regressions passed. Root verified18 infrastructure
source hashes and132 raw command streams, including expected pre-bootstrap and
stopped-scanner refusal outcomes.

API43259514813/job131326705384 failed before network creation or pytest. Native
Docker inspect succeeded but returned IPAM.Config:null for its valid built-in
host/none networks. The inventory parser refused that shape. Docker commands0..3
all exited0; absent-container cleanup stop1 is benign. No API tests ran. Root
verified197 immutable source hashes and10 raw streams in the11-entry failed
artifact13962842894, ZIP SHA256
32ce7b4b744007bb22dcba7c5eb52fa5451fb39c631c7ad4c821a70c3b458d1f.

All six complete decoded/sanitized job logs and five digest-verified artifacts
remain in ci-cb49780.zip:13 entries,1989060 bytes,SHA256
181dc95abe4c27cb1ab118a0dee62d7b27089e137f211d8a0b665835112f4661.
Its immutable manifest explicitly says NOT ACCEPTED/H3; revised credential-URL
audit found zero remaining matches. Action deprecations and disposable initdb
diagnostics are benign runner conditions, separate from the actual parser failure.

Correction160c886 accepts null IPAM configuration only for exact native built-in
host/none name/driver pairs with default IPAM driver. All actual configured
subnets still contribute to overlap avoidance; unknown, missing or malformed
inventory remains refused. The existing explicit internal subnet, bounded retry,
TLS, no-port and runtime-security controls are preserved. Two retained-native-shape
RED cases reproduce the actual failure; all21 focused GREEN tests and Ruff/format
pass. Root verified17 artifacts, two source hashes/Git blobs, five frozen runs and
the report digest. Scoped independent review marks H3 ADDRESSED/specification
and quality PASS/no new breakage. Actual hosted Docker/full API acceptance
remains pending; no application/DTO/dependency/image/scanner code changed.

source-160c886.zip:561 entries,1356066 bytes,SHA256
aad929648fa936ed4d69caa7849b9f13b7ea51c21b55c16cc69bc5bf465d30f1.
fix-3-evidence.zip:25 entries,190389 bytes,SHA256
f70285367507bef7124a5e7793da9655a321aacb14e4a0616ff873239121e624.
Both CRC pass and retain the reviewed-fix/pending-hosted scope. Root-owned public
documentation edits stayed separate from the implementer's two-file correction.

## Task 2 hosted optional-gateway failure and reviewed H4 correction

Source033c8ac again passed the other four hosted workflows: Source43262106645,
Images43262106934, Browser43262106688 and Containers43262107246. Browser154
passed in6.2m; source22 LOW/zero blockers/secrets, all seven nonempty image
inventories with zero vulnerabilities, actual signed/current scanner/update/
reload and old packaged regressions passed. API43262107056/job131335855151
failed before container creation or pytest. Docker successfully created and
inspected the requested explicit internal bridge, but the valid immediate native
IPAM response omitted Gateway. The owner incorrectly required that optional field.
Commands0..5 exited0; absent-container stop1 is benign. No API test ran.

Root verified197 failed-API source hashes/14 raw streams and18 signed-infrastructure
source hashes/132 raw streams. All six complete sanitized logs and five
digest-verified artifacts remain in ci-033c8ac.zip:13 entries,1946977 bytes,SHA256
835125a79e261c64ca6b5dc5e661e668ffe74add66cfc84e7a75f0c7758be692.
Status remains NOT ACCEPTED/H4. Failed API artifact13963998611 has15 entries,
SHA256 f7b8d8df1de041535702ae7e14e3e90912fb41a68f9acb656ef4a8b0f2233170.
The revised credential-URL audit finds zero remaining matches in sanitized logs.

Reviewed correction65e3712 accepts a missing Gateway only after the same exact
owned-name/internal-bridge/subnet checks. Present gateway values must still be
usable distinct hosts in the verified subnet; null, malformed, foreign, network,
broadcast and endpoint-colliding values are refused. No guessed gateway or
outbound route is added. Native IPAM still reserves the endpoint when the existing
container starts; actual service connectivity remains a required hosted proof.
The static IP/TLS SAN, no-port, bounded retry, secret and runtime-security
boundaries remain unchanged.

Retained-native-shape RED has3 failures; focused GREEN38/Ruff/format/diff checks
pass. Independent scoped review marks H4 ADDRESSED/specification and quality
PASS/no new breakage. Root verifies seven frozen command records,14 raw streams,
two source Git blobs, exact full retained native-row equality, the report digest
and26 retained artifact hashes. No local native Docker or Podman run is claimed.
No application/DTO/dependency/image/scanner code changed.

source-65e3712.zip:561 entries,1359218 bytes,SHA256
fbacc0c170afebca8d31022d77f1bbfcf252e53021e2cef2721306730b0f261f.
fix-4-evidence.zip:33 entries,406410 bytes,SHA256
962c733ce3831e609e0b69fe4d0f2cc920f3fbce4348267404ebf7b1b008c8a9.
Both CRC pass and explicitly retain pending actual hosted Docker/full API
acceptance. Task2 stays open until that required current-source gate executes.

## Accepted Task 2 persisted assets and scan lifecycle: 65e3712

All five exact-source workflows passed: Source43264489462, Images43264489241,
Browser43264489151, Containers43264489671 and API43264489836. Actual Docker
created the explicit internal network, allocated its static endpoint, passed the
verified TLS/native bootstrap/health/no-published-port controls and stopped its
own container successfully. All16 native command records exited0. Root verified
197 source hashes against immutable65e3712 Git bytes, equal before/after source
hashes and32 raw command streams.

The single complete API invocation passed1173 cases in835.07s, with zero errors
or failures and three explicit opt-in native-image skips. The required real-S3
attachment modules actually executed37 passing cases (21 upload/access and16 scan
cases), independently reconciled from JUnit and confirmed by the mandatory suite
guard. Build/static/migration and cleanup steps passed. Two redundant Pydantic
alias-metadata warnings appeared in existing concurrent queue tests; both tests
passed with no observed contract failure. They remain nonblocking observations
for final review, rather than hidden failures or a reason to expand this fix.

Browser154 passed in5.7m. Source has22 LOW/zero blockers/secrets. All seven nonempty
image inventories have zero vulnerabilities: API72/PostgreSQL49/ingress70/web43/
Redis16/storage107/ClamAV38. Both old packaged regressions and actual signed/current
ClamAV producer/update/reload passed. The producer verified three vendor signatures
and observed3628258 signatures reloaded; storage/clamd/updater resource/isolation
controls passed with updater-only definition egress. Root verified18 producer
source hashes and130 raw streams;65 commands reflect one fewer polling iteration
than earlier attempts, not an omitted required control.

All six full decoded/sanitized logs and five digest-verified artifacts remain in
ci-65e3712.zip:13 entries,1917672 bytes,SHA256
d20e32d879b4ae431aaf42d331eb85d523d41ebcae5b22fba39156d8ea1c0932.
Revised credential-URL audit finds zero remaining matches and ZIP CRC passes.
API artifact13966891460 has34 entries,SHA256
b52ea3d20f212d9756e16becdb9f50d47205cc16fcf981f6a98f33765e8cdc1b.
Expected SQL constraint-negative diagnostics, disposable local initdb trust and
action deprecations are separate benign test/runner conditions. Every historical
failed invocation and pre-acceptance archive retains its original failed/pending
status; this new actual complete run supplies the accepted full-suite evidence.

Task2 is accepted. This delivers real private persisted assets and durable scans,
not yet content links, reviewed MIME2, incoming-file ownership or browser upload.
The deferred request-purpose enum Minor passes to Task3's affected contract work.
No current image inherits older target-CPU qualification.

## Accepted Task 3 backend: content links and reviewed MIME2

Contractfaf705a preceded implementation8b3a187 and generated contractsdf3c8bb.
The backend creates immutable ordered links/counts on public messages, private
notes and work comments under their distinct current action authority. Concrete
composite FKs, immutable content and deferred SQL guards seal the committed set.
Omitted attachment_ids retain exact old fingerprints/events; explicit empty and
null behavior follows ADR0037. Delivery requires the exact reviewed public file
IDs, verifies real S3 bytes outside DB transactions and repeats current scope/
version/link checks before freezing. Saved replay never fetches files again.
Legacy format1 remains byte-compatible and bounded262144; actual file-bearing
format2 uses standard MIME with ordered original bytes/names and encoded cap26214400.
The restricted worker continues sending only frozen public wire.

Independent specification/quality review approved33d63bd..df3c8bb with no
Critical/Important/Minor findings. Task2 M1 is resolved: request schemas now expose
ticket public|note and work work, retaining the ordinary metadata union. The only
web-tree change is generated API TypeScript; no interface/design/UX implementation
was started. The user's explicit stop was recorded separately in9887136.

Local affected validation passed265 cases, including25 new cases, with no errors,
failures or skips. A prior257-pass/8-failure invocation remains failed historical
evidence: its inherited development PG volume lacked exactly the prior attempt
guard function, BEFORE INSERT trigger and closed reason CHECK despite its revision
label. The old volume was preserved, not repaired. All13 affected modules were
rerun on fresh correctly migrated Task3 PG; the265-case complete fresh invocation
supplies the accepted evidence. Old/fresh schema dumps and the exact delta remain.
Static checks,61-module mypy, repeated generated contracts, package audit and the
actual nonroot/read-only/network-none API image passed. Initial generator lookup/
console-copy failures and an OCI healthcheck warning remain distinguished from
the successful repeated generators and final Docker-format image with healthcheck.

Root independently verified163 artifact hashes,49 command records/98 raw streams,
212 final input hashes,22 changed Git files, the report digest and package members/
new source bytes.47 commands preserved identical before/after inputs; the two
intentional first contract generations changed only their corresponding output
file, and the final repeats were byte-identical. source-df3c8bb.zip has565 entries,
1379023 bytes,SHA256f1f042f260ca8bf76a6102374873011f9350d42f6d1d7d8573ff4eb49800025d.
reviewed-local-evidence.zip has174 entries,1921369 bytes,SHA256
d2128990ef1300069b55f43176eb45c862e4750875403181d2c81d87c3b2ace6.
Both CRC pass and preserve their original pending-hosted status at creation.
Task3 archives are at C:/Users/wagne/.codex/state/evidence/private-file-task3-df3c8bb/.

All five exact-df3c8bb workflows passed: Source43291545079, Images43291544980,
Browser43291544853, Containers43291545091 and API43291545034. The complete API
invocation passed1198 cases in803.97s, zero failures/errors, with three explicit
opt-in native-image logger skips. Actual execution includes all25 new Task3 cases
(16 delivery/9 links) and37 existing required file cases. Separate mandatory actual
signed/current ClamAV proof passed; the three skips do not substitute for it.
Browser154 passed in6.6m. Source22 LOW/zero blockers/secrets and all seven nonempty
inventories report zero vulnerabilities (72/49/70/43/16/107/38 by the names above).
Old packaged regressions and actual signed update/reload3628258 signatures passed.
Root verified201 API source hashes/32 raw streams and18 producer source hashes/
132 streams against immutable Git/artifact bytes; three vendor signatures verified.

Six complete sanitized job logs and five digest-verified artifacts are retained
with controller verification in ci-df3c8bb.zip:15 entries,2004276 bytes,SHA256
cc208d76683bd4e5f4bc6ca8b09086ed6575982c2f8e558ef31ff9a7571f91dc.
ZIP CRC and revised credential-URL audit pass with zero remaining matches.
API artifact13977797770 has34 entries,SHA256
a08a9f84132589a82f02cc2b3e3e462c7c731f7b3f60cb50fbcc837a6de23e34.
Expected SQL constraint/role-negative diagnostics, disposable local initdb trust
and action deprecations remain benign test/runner conditions. No required gate
failed. Task3 backend is accepted; no incoming-file/UI/target claim is inferred.

## User-requested stop and outstanding acceptance

Local2048MiB Podman was not resized/restarted. Controlled socket replies remain
transport evidence, separate from the actual accepted hosted signed profile.

STOP before design, UI, UX or Task4, per the user's latest explicit instruction.
The next planned browser file workflow remains unstarted pending a new user
instruction. Packaged end-to-end file/restore/privacy proof and owner-bounded
incoming-MIME files remain subsequent incomplete work, not accepted by Task3.
Final actual x86-64-v1 qualification follows remaining MVP development under the
user's consolidated cadence.
