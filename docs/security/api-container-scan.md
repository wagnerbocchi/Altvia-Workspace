# API runtime candidate image scan

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
