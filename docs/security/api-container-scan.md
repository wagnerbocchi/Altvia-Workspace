# API runtime candidate image scan

Current candidate status (2026-11-09): ADR-0013 replaces these Bookworm images.
Actual API/PostgreSQL/ingress scans now contain zero HIGH/CRITICAL findings.
The following historical observations remain for traceability; see the Phase1C-f
entry in docs/phase-1c-evidence.md for current image identities, residual lower
severities, retained raw evidence and runtime acceptance. No risk waiver or
target-VM homologation is implied by the corrected scan results.

Observed2026-11-09. Development candidate only; no production risk acceptance.
Asset: local API image sha256:fba4a5bc974f4a45c7ed048dc7dfead94f56d996134325bb2c4f209b5f460d47.
Python3.12.16/bookworm manifest0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4,
Debian12.15, locked production dependencies. Subsequent application-only source
fixes do not change this package inventory; this report identifies its exact scan.

Scanner: Trivy0.75.0 image
sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa,
fresh vulnerability DB, vulnerability scanner only, actual Docker image archive.
Raw report SHA256:58c5f2d75b4bced9ac02242f4b82af209921b093a344ca9163b41de703d6bb6e.
Initial OCI-archive input was unsupported and failed; no result was inferred from
that failure. Re-exporting docker-archive and rescanning succeeded.

Raw package occurrences: **2 critical, 40 high, 122 medium, 109 low**. No Python
package high/critical finding appeared. No high/critical vendor fixed version
was supplied by this report. These are scanner ratings, not application CVSS
recalculation or a statement that every installed component is exploitable.
Nothing is suppressed by an ignore file and no exception is accepted.

## Critical applicability

| Finding/asset package | Evidence and confidence | Disposition/action | Owner and deadline |
| --- | --- | --- | --- |
| CVE-2025-7458, libsqlite3-0 3.40.1-2+deb12u2 | Installed vulnerable package; Debian marks bookworm vulnerable. Advisory requires arbitrary crafted SQLite SELECT. Current API/migrations use PostgreSQL only; source search found no SQLite calls. High confidence in package finding; no current API path found. | Confirmed package finding, release triage open. Select a baseline-compatible corrected/removed component or document validated applicability before release; re-scan and run API/container proof after a package change. No blanket exception. | Engineering/security role, responsible person to be assigned before production; must close production gate. |
| CVE-2023-45853, zlib1g 1:1.2.13.dfsg-1 | Debian explicitly states contrib/minizip is not built by this bookworm source. Actual libz lookup found no zipOpenNewFileInZip4_64 symbol. Application has no MiniZip call path. High confidence in non-applicability for this installed binary. | Not affected by this MiniZip CVE on the observed binary; preserve raw finding and vendor rationale. Re-evaluate if MiniZip/pyminizip or the base artifact changes. No general zlib security approval. | Engineering/security owns recheck on image/dependency change. |

Vendor sources retrieved2026-11-09:

- https://security-tracker.debian.org/tracker/CVE-2025-7458
- https://security-tracker.debian.org/tracker/CVE-2023-45853

## High findings requiring release triage

The40 package occurrences below reduce to15 CVE identifiers. No broad
not-affected or risk-accepted determination has been made. Engineering/security
must assign an owner, verify each vendor/backport/path, choose remediation or
request explicit bounded risk acceptance, then rescan the selected immutable
artifacts before production. No automatic OS-family change or unsafe -march
selection is justified to obtain a lower scanner count.

| CVE | Installed package instances |
| --- | --- |
| CVE-2025-69720 | libncursesw6, libtinfo6, ncurses-base, ncurses-bin |
| CVE-2026-9538 | perl-base |
| CVE-2026-11822, CVE-2026-11824, CVE-2026-119373, CVE-2026-119374, CVE-2026-119379 | libsqlite3-0 |
| CVE-2026-16742 | libsystemd0, libudev1 |
| CVE-2026-41992 | gzip |
| CVE-2026-53613, CVE-2026-53615, CVE-2026-78410 | bsdutils, libblkid1, libmount1, libsmartcols1, libuuid1, mount, util-linux, util-linux-extra |
| CVE-2026-54369 | libacl1 |
| CVE-2026-76844, CVE-2026-85091 | zlib1g |

Medium/low findings also remain in the raw report for later triage. The raw scan
is retained under ignored .superpowers/container-tests/api-runtime-scan-20261109.json;
binary build archives are disposable. Do not commit archives or runtime secrets.
Functional CI, non-root/read-only controls and absence of a current attack path
never substitute for vulnerability triage or actual x86-64-v1 guest validation.

## Phase 1C-e remediation: remove the unused SQLite capability

Observed 2026-11-09; ADR-0012. The API has always required PostgreSQL. The final
API image now removes CPython's optional sqlite3/_sqlite3 modules and purges
libsqlite3-0 without fetching packages, forced dependencies, apt autoremove,
private SQLite compilation or a base/lockfile change. The general-purpose builder
and developer Python are unchanged. This is capability removal, not an upgraded
SQLite version or a risk exception.

Compared actual Docker-format artifacts with Trivy 0.75.0 using the scanner image
above. The first scan refreshed one private cache; the second used --skip-db-update
against the same DB. No ignore file, severity filter or unfixed filter was used.

| Artifact | Image ID | Raw report SHA256 |
| --- | --- | --- |
| Published baseline | 769c5489fd0d88348ecc3b7b9af996b978220c5e8eb5017ef4d290be64055ed7 | 55306809134dbb817bd2e774f0c6777890b1d7aae7896cc5438bd63c7e7acad1 |
| SQLite-free runtime | acba1ed82e79aaa7e335dcde023c0935b0c7d741f930ab8fc793345a32b4226f | 6ac3804f4b5303ef9f4cffb5de04892ce610c1183bfa606af6bba62e737d271c |

Vulnerability DB schema 2, UpdatedAt 2026-11-09T06:57:06.372182267Z,
SHA256 3f021611ab6c0b94ca9f4fb630fb583c200663e8cae430446f89ded1b99fdb29.
Debian inventory changed from 105 to 104 packages: only
libsqlite3-0:amd64 3.40.1-2+deb12u2 was removed; no other package/version delta.
Both images have the same 27 Python distribution entries, inventory SHA256
3a203a6cb87c98a8130bd72d901ee388b6c6042bd9c4cc9efd0c85c30eed9e76.

| Raw package occurrences | Baseline | Remediated runtime | Removed |
| --- | ---: | ---: | ---: |
| Critical | 2 | 1 | 1 |
| High | 40 | 35 | 5 |
| Medium | 122 | 113 | 9 |
| Low | 109 | 105 | 4 |

All 19 removed finding identities belonged to libsqlite3-0; zero new identities
appeared. Exact eliminated CVEs:

```text
CVE-2021-45346 CVE-2025-29088 CVE-2025-70873 CVE-2025-7458 CVE-2025-7709
CVE-2026-11822 CVE-2026-11824 CVE-2026-119371 CVE-2026-119372
CVE-2026-119373 CVE-2026-119374 CVE-2026-119375 CVE-2026-119376
CVE-2026-119377 CVE-2026-119378 CVE-2026-119379 CVE-2026-119591
CVE-2026-50812 CVE-2026-50813
```

SQLite findings are remediated for this installed runtime by removal. Positive
guard/import/Argon2 proof passed non-root/read-only; the unchanged builder is
rejected. A separate negative probe mounted the original shared library through
LD_LIBRARY_PATH without installing its package: the guard still rejected the
loadable library. That temporary helper was removed. Scanner/package absence
alone was not accepted as proof of native capability absence.

The remaining raw critical is CVE-2023-45853. Rechecking the new image found no
zipOpenNewFileInZip4_64 symbol; the unchanged vendor applicability evidence above
still applies. The 35 high occurrences and all other native-image release triage
remain open. No production risk is accepted and no blanket clean-image claim is
made. Raw comparison reports are retained under ignored
.superpowers/container-tests/sqlite-removal-{baseline,trimmed}-20261109.json.
Actual guest x86-64-v1, other service images, SAST/SCA coverage and release gates
remain separate. Reintroducing SQLite requires a revised corrected capability
contract and a fresh scan/retest, not disabling the guard.
