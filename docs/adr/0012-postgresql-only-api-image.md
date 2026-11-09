# ADR-0012: PostgreSQL-only API image capabilities

Date: 2026-11-09. Status: selected for Phase 1C-e; executable proof pending.

The API configuration already requires PostgreSQL/psycopg. No application or
migration source uses SQLite. The inherited general-purpose Python image contains
libsqlite3-0 and CPython's optional sqlite3/_sqlite3 modules. Its installed SQLite
version is vulnerable to CVE-2025-7458 and other scanner findings, even though no
current API SQL path reaches it. Lack of a current call path is not risk acceptance.

Decision: remove that unused native package and optional Python module from the
final API image only. Keep the exact Python/bookworm and uv builder digests and
the locked production dependencies. The dependency-builder stage is unchanged.
Remove CPython's sqlite3 package and _sqlite3 extension, then purge libsqlite3-0
using the image's package manager without fetching packages, forced dependency
removal, apt autoremove or an OS-family change. Any unexpected package dependency
must fail the build. Do not delete unrelated standard-library components.

A small standard-library runtime checker verifies module/spec absence, Debian
package status, absent SQLite shared objects and loader discovery. It also
imports the actual API/CLI/migration dependencies and essential native Python
libraries. Run it during build and inside the actual non-root running API in the
existing guarded Compose proof. A reintroduced dependency must fail acceptance.
No new application dependency, HTTP behavior, schema, grant or UI change.

Alternatives: building and maintaining a patched private SQLite would retain an
unused component and introduce compiler/source-verification responsibilities.
Moving all images to a different distro solely to lower scanner counts would
change more native libraries and invalidate established compatibility evidence.
Ignoring the finding based only on PostgreSQL usage leaves vulnerable code
installed. Removing an unused capability is the smallest supported correction.

Compatibility: the container is an Altvia PostgreSQL API runtime, not a general
Python/SQLite environment. SQLite database URLs remain rejected by existing
configuration. A future legitimate SQLite requirement needs a revised capability
contract and a corrected baseline-compatible library; no silent reinstallation.
This does not change host/development Python, the builder, PostgreSQL or ingress.

Acceptance: checker fails against the published stock-derived image, passes on
the pruned image under non-root/read-only execution, and the existing Docker/Linux
Compose tests still prove migrations, login, roles/ACLs, TLS, persistence after
recreation, readiness recovery and SIGTERM. Scan old/new image archives with the
same scanner and vulnerability DB, retaining raw results and their hashes. Only
findings actually eliminated from the installed runtime can be marked remediated.

Security and CPU: no ignore file, blanket unfixed filter or risk acceptance. Keep
remaining native findings open and preserve the separate MiniZip applicability
evidence. No new binary or compiler flag is introduced; x86-64-v1 remains mandatory
and actual guest proof is still unavailable. Local Podman cgroup limits do not
justify weakening Compose; hosted Docker/Linux supplies full runtime acceptance.
Production deployment/provisioning and real data operations remain unauthorized.
