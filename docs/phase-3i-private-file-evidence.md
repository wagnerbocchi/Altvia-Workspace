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

All six full decoded job logs were inspected and sanitized before persistence.
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
evidence remains immutable. New actual hosted full-profile acceptance is required.

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
