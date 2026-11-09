# Residual runtime findings implementation plan

Execute inline under the existing fix/development and main-push authorization.
Base3f20106. Contract: ADR-0013, with this bounded capability supplement.

The installed-image boundary includes global Python, ensurepip's bundled wheel
and embedded Go modules, even when the API virtual environment hides them.
Keep the builder general-purpose. The final API is an immutable PostgreSQL
service, not an installer environment: pip/ensurepip are unsupported capabilities.
Update required zlib through signed Alpine1.4-r0 in API/PostgreSQL. Do not remove
it. Rebuild existing gosu source with pinned moby/sys/user0.4.1 and x/sys0.44.0;
commit full module checksums, verify with the existing Go1.27.3/v1 toolchain.
Ruling: select moby/sys/user0.5.0 instead of0.4.1 after the latter's official
cap-read tests failed. Upstream0.5.0 corrects invalid NUL padding in those tests
and preserves the called API. Do not omit or patch around the failing tests.

1. RED: actual current-image installer absence fails for ensurepip; existing
   unfiltered raw scans reproduce the10 residual occurrences. Independent
   read-only investigation verifies global/bundled copies and gosu call contracts.
2. Extend scripts/check_api_runtime.py with a separately callable installer
   capability guard covering active/base site-packages, entrypoints and bundled
   wheels. Add actual builder installer rejection to scripts/container_smoke.py.
   Change only owning Dockerfiles and pinned infra/gosu.go.mod/go.sum inputs.
3. Build actual images; verify native compression roundtrip and gosu's named/
   numeric user/group/HOME/error paths. Scan all services using one vulnerability
   DB without filters. Preserve all raw evidence through managed security storage.
4. One fresh read-only bypass/regression candidate review, then relevant local
   lint/build/guard checks and full hosted API/browser/Compose/recovery/security
   gates. Commit coherent source changes and push main; record exact results.

Stop this slice when all10 residual findings are absent and legitimate paths
pass. No schema, credentials, public API or production migration. The actual
target-VM gate remains open. Continue web ingress as a separate contracted slice.

Execution complete on683e34d: tasks1-4 passed. Fresh independent candidate review
found no surviving bypass/regression. All four hosted gates passed:244 API tests,
7 E2E, actual Compose/recovery and zero-finding scans. Exact links and managed
artifact references are in docs/phase-1c-evidence.md. No actual VM/production claim.
