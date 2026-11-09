# ADR-0013: Vendor-patched service image closure

Date: 2026-11-09. Status: candidate, pending measured acceptance below.
Supersedes the Bookworm image-family selection in ADR-0011 and the package-manager
detail in ADR-0012. Their application, privilege and capability contracts remain.

## Problem and decision

The remaining API findings affect Bookworm packages without vendor fixes. Several
packages are Essential and have Pre-Depends which a scanner dependency list omits.
Forced purging or deleting shared libraries is not a supported correction.
The PostgreSQL and proxy stock images also contain vulnerable components.

Use the official Python 3.12, PostgreSQL 17 and unprivileged nginx Alpine variants,
pinned by amd64 digest. Use signed Alpine packages for proxy fixes. Rebuild the
unchanged gosu 1.19 source with pinned Go 1.27.3, CGO_ENABLED=0 and GOAMD64=v1;
preserve its module/build metadata. Source archive checksum and Go module sums
must verify before compilation. Keep the PostgreSQL entrypoint and PGDATA path.
No private libc, zlib or CPython fork, forced dependency removal or CVE suppression.

The API keeps its locked production Python dependencies, installed from wheels
only. Remove only the optional SQLite modules and sqlite-libs. Replace upstream's
virtual Python runtime dependency set with the identical SO requirements except
SQLite, then use apk's ordinary dependency resolution. All other Python modules
and libraries remain supported. Check package, filesystem and loader absence and
real API/CLI/migration/native imports during the build and running-stack proof.

The enforcement boundary is the complete installed runtime of all three services,
not the application's present call graph. Scan each actual image with one scanner
and DB, including OS, Python and Go components. A scan error or any HIGH/CRITICAL
finding blocks the container CI job. No ignore file or ignore-unfixed filter.
Persist the reports and image identities as CI artifacts. Lower-severity findings
remain visible and are not represented as zero vulnerabilities.

## Compatibility and data safety

No HTTP, schema, role, session, grant, ingress TLS, health, resource-bound or
non-root API/proxy contract changes. PostgreSQL keeps major 17 and its initialization
privilege drop. Its inherited root entrypoint is limited by the existing explicit
capabilities; the daemon runs as postgres. No real deployment is authorized.

Moving from glibc to musl changes collation behavior. Never attach an initialized
Bookworm volume to the new PostgreSQL image. Use logical pg_dump/pg_restore into
a separate fresh volume, preserving the original for rollback. Verify roles,
ownership, constraints, Unicode, indexes, FTS and application data before cutover.
Synthetic cross-libc restore is an acceptance test, not a real data migration.
The image entrypoint refuses initialized PGDATA without its exact runtime-family
marker before calling upstream. Only the official fresh-init hook writes that
marker. Copying a marker into a legacy cluster is prohibited; restore logically.
Rollback uses the original image AND original untouched volume. No automatic
schema downgrade, collation refresh or volume deletion.

Alpine's generic x86_64 compiler defaults and explicit GOAMD64=v1 support the
baseline selection; neither amd64 labels, scans nor modern CI CPUs prove ISA
compatibility. The exact musllinux wheels and runtime images need functional
native-library tests and eventual execution on the actual x86-64-v1 target VM.
Q-01 remains a hard Phase 1 exit gate. No AVX/SSE4.2 requirement is permitted.

## Alternatives and acceptance

Trixie candidates still contain high findings. Distroless would require maintaining
a private CPython/native-library closure and provenance inventory. Alpine provides
supported vendor packages and standard runtime images with less custom ownership.
Rebuilding only gosu updates its vulnerable embedded Go runtime without replacing
the PostgreSQL entrypoint or adopting a second privilege-drop interface.

Acceptance: clean wheel-only build; builder rejection and final runtime checks;
same-DB scans of API/PostgreSQL/proxy with no high/critical findings; actual Linux
Compose TLS/ACL/persistence/readiness/SIGTERM tests; synthetic old-to-new logical
restore; full existing API and browser gates. Actual VM homologation and production
authorization remain separate and must never be inferred from these results.

Primary sources: official docker-library/python 3.12/alpine3.24 Dockerfile;
docker-library/postgres 17/alpine3.24 Dockerfile; tianon/gosu 1.19 source/go.sum;
Alpine v3.24 signed package repositories and aports secfixes; Alpine abuild
default.conf and gcc APKBUILD. Immutable inputs are recorded in the Dockerfiles.
