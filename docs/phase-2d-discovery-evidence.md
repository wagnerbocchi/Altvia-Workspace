# Phase 2D task discovery evidence

Date: 2026-11-10. Scope: ADR-0021 task filters, native PostgreSQL search,
independently paged project board and task-only personal queue. Source 1c20f48
passed actual target-VM qualification, including native/resource proof and scans
of the exact five executed images.
Phase 2 and production readiness remain open.

## Behavior and boundaries

The existing project task list accepts typed status, priority, work type, owner,
owner-or-participant, unassigned, deadline presence and aware deadline-range
filters. Title and description use Portuguese websearch_to_tsquery with a native
GIN expression index. No service, dependency or ISA requirement was added.
Unknown/repeated query parameters and numeric or timezone-free range timestamps
are refused. Filtered cursors bind the current actor and normalized criteria;
the existing unfiltered project cursor contract remains compatible.

GET /my-work applies the complete visible-project SQL predicate before filtering,
ordering and pagination. Owner OR participant EXISTS selects each task once.
Customer ceilings and both required membership halves remain mandatory. Team
metadata, assignment and platform administration never grant project content.
Project names are returned only within that scope. There are no global counts,
ticket rows or per-result permission queries. Deadline precision is preserved.

The browser deliberately applies native labeled filters, resets paging with each
applied query and supports independent board-column loading, paging and recovery.
Additional filters can be expanded without forcing a full-form scroll to results.
Desktop lanes remain stable for populated and empty states; narrow screens stack.
Existing task detail owns all mutations. Creation stays mounted independently of
filter/page changes, retaining uncertain original intent. Refresh/recovery also
updates creation authority; failed authority reads lock new creation.

Migration b46087000009 changes indexes only. Downgrade preserves task/history data
and restores former owner/participant indexes. The incumbent identity, themes,
tokens and session-owned cache are preserved. Runbook: runbooks/work-items.md.

Contracts preceded implementation in 215eb31. Backend and generated contracts:
4d56e97bfff434b14e121f5508ba1038f1558b7b. Browser and reviewed recovery/visual
fixes:8c1be1d. Packaged proof:9d53841. Navigation acceptance strengthening:
1c20f4893e37158dcc93bba3ab14c3a95cdfdce7. Application behavior did not change
after8c1be1d; later commits strengthen acceptance evidence only.

## Local proof and corrected failures

- Initial missing-behavior API tests failed before implementation. Focused
  discovery/storage proof: 34 passed in 72.26 seconds on real PostgreSQL.
- Complete API: 424 passed in 141.30 seconds. Ruff check/format, strict mypy,
  generated OpenAPI/TypeScript and web checks passed.
- Search proof covers Portuguese words, phrases, exclusions, stopwords, edit
  freshness, range bounds, null deadlines and actual GIN selection over 6000
  synthetic rows. SQL/query-count, scope revocation, platform non-grant,
  owner/participant deduplication, cursor binding and rollback are exercised.
- Fresh source review found one P2 recovery defect: discovery refresh did not
  recover independent creation authority or observe fresh archival there. A
  failing browser regression preceded the fix; the focused four-test suite
  passed afterward in 15.6 seconds. No second source review was substituted.
- The first complete browser run passed 51 of 52 tests. Its existing subtask
  test assumed the principal task was on the first picker page; new synthetic
  discovery tasks made that assumption false. The test now follows actual
  picker pagination. Production paging and timeouts were not weakened.
- The exact-instant directory assertion also assumed a first-page match. It now
  finds its own task across pages, waits for loaded results and checks that row's
  timezone. The corrected instant test passed in the subsequent full attempt.
- Final affected browser suite: all10 work/discovery tests passed in49.8 seconds,
  including real persistence, write recovery, exact instants, personal dedup,
  column paging, authority recovery, accessibility and responsive captures.
  Final web lint/types, production build, Python source/wheel build and packaged
  script syntax/Ruff checks passed.
- Later full Windows attempts encountered an internal axe finishRun JSON.parse
  error on the unchanged account accessibility surface. Worker restarts lost
  in-memory login reuse, causing subsequent 429 source-limit failures. No login
  cap, accessibility rule or production behavior was relaxed. An isolated real
  account diagnostic passed eight scans; a synthetic probe passed60 JSON round
  trips and12 axe scans. These probes do not establish the intermittent cause.
  The complete Linux execution below supplies full-suite acceptance; no passing
  complete local Windows browser run is claimed for this increment.
- Impeccable's full finish review requested compact filters and stable desktop
  lanes. All twelve same-size theme/viewport recaptures were inspected; its
  round-1 verdict scored both fixes resolved with disposition ship. This verdict
  covers those scored fixes. The prescribed documenter verified the incumbent
  extension and the updated PRODUCT.md. DESIGN.md and sidecar remain unchanged;
  preexisting empty narrative.rules drift is reported without repair.

## Hosted acceptance

All five hosted gates passed on9d53841:424 API tests in203.18 seconds,52 browser
tests in1.3 minutes, source security, five-image security and actual packaged
Docker/HTTPS proof. Complete logs and synthetic packaged captures were inspected.
The packaged workflow executed personal deduplication, scope, five states,
persisted search and transaction-rolled-back native GIN selection, plus mobile
board/personal navigation and existing restore/worker/recovery checks.

Visual inspection of the packaged personal capture showed an empty search field.
The test could fill the outgoing project's identical control before the soft
navigation completed and still find the single personal task. Acceptance now
waits for the personal heading and asserts the retained search text. The local
personal regression passed in 3.3 seconds; 1c20f48 passed all five hosted gates.
Its corrected packaged captures were inspected: the personal search retains its
exact query and the matching task, and the board preserves the blocked task.
This is a test synchronization correction, not a product-state workaround.

Final exact acceptance source: 1c20f4893e37158dcc93bba3ab14c3a95cdfdce7.

| Hosted gate | Executed result |
| --- | --- |
| [API 42816514798](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42816514798) | 424 passed in 201.63 seconds; migrations/drift, Ruff/format/mypy and Python build passed |
| [Browser 42816517741](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42816517741) | 52 passed in 1.7 minutes; locked build/types/contracts/native guard and dependency audit passed |
| [Containers 42816514847](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42816514847) | Actual Docker/HTTPS, native task GIN, personal/filter/search persistence, restore, ACL and worker/Redis/replay/readiness/SIGTERM proof passed |
| [Images 42816514764](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42816514764) | Eight scan-unit tests and all five image reports passed; zero reported vulnerabilities |
| [Source 42816514924](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42816514924) | No secrets or blocking SAST; complete low-severity metadata retained |

Both sets of five hosted image reports have nonempty package inventories, matching
manifest/report SHA256 and zero reported vulnerabilities across all severities.
Source scanning reports no secrets or blocking SAST; four existing low-severity
CLI/assert metadata findings remain visible. Hosted image IDs do not establish
target-VM runtime/image identity. The local Windows axe limitation remains
recorded; a passing complete Linux run does not claim that cause is resolved.
Existing action-level url.parse/punycode deprecation notices and disposable
PostgreSQL local-init authentication warnings were benign test infrastructure
messages; they did not require changing product or production security settings.

## Actual target qualification

The exact source archive was uploaded and built on the supplied QEMU/KVM guest
in /root/altvia-discovery-1c20f48-123229/source. Immutable source 1c20f48 has archive
SHA256
e27f1829cd4d612532f7359db832e00db6b3affa525535a2892db4637064a804.
Client upload wrappers pin that revision independently of later documentation
commits. The previous /root/altvia-work-core-d5ae972-040512 environment and its
volumes were preserved. Only synthetic data and loopback application ingress
were used. Complete packaged smoke ran from 14:06:30Z to 14:10:14Z on 2026-11-10,
exit 0. Native/resource verification and actual-image scanning also exited 0.

The guest advertises SSE2/pni/cx16 but no SSSE3, SSE4.1, SSE4.2, AVX, AVX2, FMA or
BMI2. Python 3.12.16/Argon2/imports, Node 24.22.1/ICU/TLS, PostgreSQL 17.11,
Redis 7.4.12 and nginx 1.30.6 ran successfully. Runtime guards confirmed no SQLite
in API, no Sharp in web and no package installers in either. No new dependency, service or ISA
requirement was introduced by discovery.

| Target proof | Executed result |
| --- | --- |
| Packaged behavior | Persisted filtered/search/personal queries, deduplication, scope denial, five task states, HTTPS and real mobile board/personal flows passed |
| Native search | 6000 synthetic rows inside a rolled-back transaction; ix_work_search Bitmap Index Scan, one match; 3.328ms execution, 3.174ms planning |
| Recovery | Cross-libc logical restore/Unicode/FTS/constraints, recreation, migrations, replay and scoped worker projection passed |
| Broker loss | Worker exited 0 in 6.408 seconds with Redis blackholed; all 27 events recovered |
| Resources/isolation | Actual memory.max, cpu.max and pids.max matched Compose; read-only roots, dropped capabilities, no-new-privileges, private DB/queue networks and loopback-only ingress verified |
| Visual inspection | Native mobile board retains its blocked task and query; My Work retains its query and matching scoped task; filtered empty list and existing task-detail captures retained |
| Cleanup | No task containers running; task volumes and previous qualified environment retained |

Actual memory/CPU/PID limits are API/PostgreSQL/web 512 MiB/1 CPU/128,
worker/migration 256 MiB/1 CPU/64, Redis 128 MiB/0.5 CPU/64 and ingress
64 MiB/0.5 CPU/64. PostgreSQL starts through its existing privilege-dropping
entrypoint; API/web/worker/Redis/ingress use their declared non-root accounts.

| Actual target image | Docker image ID | Inventoried packages | Reported vulnerabilities |
| --- | --- | --- | --- |
| API, also worker/migration | sha256:07508787d0e9e854b8dcfc624feb8dd5a157ae70b072b63bdd5a87d70cd1e701 | 66 | 0 |
| PostgreSQL | sha256:030526216a757e65f001c37624b8b8d5d4cf5e66958d45d16e3890039fc982a9 | 49 | 0 |
| Web | sha256:cdbe776946e76d2fb9c942f1a343aa2e9396b995f87fd7c85ae6ba64cc2cbed0 | 43 | 0 |
| Ingress | sha256:d699b69148333067ce388102fed4737b029cf574f6aff75e0aa002985505b928 | 70 | 0 |
| Redis | sha256:f7668e5a73c59af1dd235f4485e8da506e454ed793e73a0e788c029ccf3aa4bb | 16 | 0 |

Trivy 0.75.0 used the fresh available database snapshot updated
2026-11-09T19:03:15Z, next update 2026-11-10T19:03:15Z; database SHA256
8c808b8e2b45da2b9849fab569412fd5b0a59455d3335ea0321f0179bcd86130.
Reports retain every severity and package inventory, with no ignore file or
unfixed filter. Verification matched each resource-tested Docker image ID to
the scan manifest, plus each unique archive tag, ordered DiffIDs, configured
user and report SHA256. Trivy archive Metadata.ImageID is not assumed to equal
Docker's runtime image ID. Exact manifests and complete reports are retained.

The owner separately authorized public-key registration and remote Codex setup.
Fresh Windows SSH connections now authenticate through the loaded user agent
with password/interactive prompts disabled and strict known-host verification.
Native Windows ControlMaster failed its client probe, so each stage reused one
authenticated SSH connection for all its sequential commands; connections closed
when stages finished. No sshd/firewall setting was changed. The dedicated remote
development project is /root/altvia-workspace-dev; its registration does not
prove native development build/test-toolchain readiness. The old task-local WSL
keeper had already exited; no unrelated process was stopped.

Reproduction sequence: prepare frozen dependencies, run
`ALTVIA_ALLOW_CONTAINER_TEST=1 python3 scripts/container_smoke.py` on the exact
archive, restart its unique Compose project with `--no-build`, execute retained
native/cgroup checks, stop it preserving volumes, scan its five `docker save`
archives, transfer evidence and run the retained binding verifier. Commands,
exit codes and native-probe stdout/stderr are in the target archive below.

This qualifies the exercised discovery paths. Synthetic GIN timing is neither
a production latency target nor a capacity benchmark. Future native artifacts,
contacts/default ticket projects, ticket consolidation, retention and production
readiness remain separate gates. The recorded Windows axe cause remains open.
No production deployment, real import or Zammad retirement is authorized here.

## Retained evidence

Complete sanitized local outputs, failed-run history, source/finish/documentation
reviews and twelve synthetic captures are retained outside Git in the Codex
Security target artifact store:

- artifacts/phase2-discovery-local/local-proof.zip, SHA256
  d37ab2cbc88f7a075e36c0ca7fdd83e82fba3ca28080e42c648ffea5099da406.
- artifacts/phase2-discovery-hosted-evidence.zip, SHA256
  c03adacab5dc229f240f847324a65ef8f285c45a450e7fb90fbb6bc92e9c46ca.
- artifacts/phase2-discovery-vm/target-proof.zip, SHA256
  202949ca7239a45b23b15fa349443f20dced925e370457e2d9cf7d9f2da707d3.

The hosted archive preserves both exact-revision run manifests, complete logs,
five-image JSON reports and hash/package verification, source summaries and
packaged synthetic captures. Its final capture supersedes the earlier personal
navigation evidence; the earlier capture remains for audit. Runtime secrets,
source workbook and production logs are excluded. Later documentation-only commits
reuse the recorded passing application/proof checks. The target archive preserves
the final source/state/resource/scan manifests, complete JSON reports, native
search plan, outage proof, fourteen synthetic captures, stage outputs, helper
scripts, reviewed decisions and successful binding verification. It establishes
actual-target qualification without claiming the Windows axe cause is resolved.
