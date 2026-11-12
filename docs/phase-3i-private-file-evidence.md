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

## Outstanding acceptance and continuation

Local2048MiB Podman was not resized/restarted. Controlled socket replies remain
transport evidence, separate from the actual accepted hosted signed profile.

Complete Task 2 hosted acceptance, then concrete content links/reviewed MIME2,
the Impeccable browser flow and packaged restore/
privacy proof. Owner-bounded incoming-MIME files follow under a separate contract.
Final actual x86-64-v1 qualification follows remaining MVP development under the
user's consolidated cadence.
