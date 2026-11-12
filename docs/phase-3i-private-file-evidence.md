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

## Outstanding acceptance and continuation

Actual hosted full/current signed ClamAV definitions, clean/EICAR/encryption/
expanded-limit/stale/refusal controls, signed update/observed reload, Docker
resource/isolation proof, all-seven inventories and full regression gates remain
pending. Local2048MiB Podman was not resized/restarted. Controlled socket replies
are transport evidence only.

After infrastructure acceptance, implement persisted assets/scan leases, concrete
content links/reviewed MIME2, the Impeccable browser flow and packaged restore/
privacy proof. Owner-bounded incoming-MIME files follow under a separate contract.
Final actual x86-64-v1 qualification follows remaining MVP development under the
user's consolidated cadence.
