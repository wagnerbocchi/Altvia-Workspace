# Phase 2C task-core evidence

Date: 2026-11-10. Scope: ADR-0020 tasks/subtasks and scoped internal history.
Qualification complete for this task-core slice. Phase 2 and production readiness
remain open.

## Behavior and architecture

The existing project workspace now operates real persisted tasks, optional owner,
distinct participants, same-project subtasks, priority, description, estimate,
explicit date/instant deadlines, strict transitions and internal comments. Ongoing
work requires explicit completion; parent and child states remain independent.
No board, search, My Work, ticket, scheduler, import or external message was added.

Every task and child-route read requires actual project access. Customer ceilings
and direct role/membership halves remain mandatory. Assignment, team metadata and
global administration never grant content. Managers manage task fields; agents
create self-owned work, comment within scope and update/transition assigned work.
Viewers read. Archived references prohibit new writes while current authority can
still expose committed receipts. Revoked authority is checked before replay.

Migration b46087000008 expands four tables. Composite parent/project FK, self and
cycle guards, identity/project/task lock order, versions and append-only history
protect persistence. API gets operational DML and history SELECT/INSERT; worker
gets no task tables. Audit/outbox commit with mutations. Exact event families
carry safe IDs, field names and states, never task/comment/reason prose.

Dates retain source precision, date and zone; null stays null. One native PG helper
resolves repeated midnight to its first occurrence, forward gaps to the first
valid instant and rejects skipped source days. API and trigger share the function.
Browser labels expose actual display zone; unrelated edits preserve raw instants.
Deliberate repeated-clock edits require UTC. No dependency, service, native version
or ISA requirement changed. Operational use and rollback: docs/runbooks/work-items.md.

Contracts preceded code in 6d16545; backend 3c7707f, browser 334e780, packaged proof
faf5a33, backend review fixes 7232b85 and browser review fixes d5ae972.
Exact application source: d5ae9723c7aee7220a39f9f01ede8d63c07a2be4. Archive SHA256:
6163d0edd47f29ae0ad6236f119dac0899e3f722af4dbf62bbe01b65c0dbd0b5.
Previous image qualification is not reused as evidence for changed images.

## Review and corrected failures

Fresh source review found five P2s: exact-instant loss, stale assignment validation,
ambiguous next-midnight selection, dropped actor/change details and acceptance
proof gaps. Real RED tests reproduced the first four; missing proofs were added
against already-required invariants. Only new assignment links now require active
candidates; unchanged historical links remain usable without conferring access.

The review's 2026 Havana example passed on the test PG timezone data. The historical
2025-11-01 case reproduced 05Z instead of 04Z and passed after the shared boundary
fix. Both years, ordinary dates, midnight gaps and skipped following dates are in
the regression matrix. The original finding and explicit fixture correction were
retained in the reviewer report. The focused follow-up accepted all five fixes
and test design with no new source blocker; execution/qualification remained gates.

Impeccable required explicit instant zone labels. All eight real instant captures
show the device IANA zone and abbreviation across directory/detail, both themes
and viewports. Its verdict pass returned disposition ship for that scored fix.
Documenter preserved the incumbent system. Existing empty narrative.rules drift
was reported, unrepaired. No new world, comp, assets or second detector was added.

One earlier full browser run failed after the local Podman/WSL machine stopped;
subsequent HTTP503/tunnel failures were infrastructure evidence. Restarting that
machine and a task-scoped foreground keeper restored the full 46-test suite. No product
or host-policy patch was made for that incident. External SSH was reauthenticated
and its verified client master reused; no server SSH settings changed.

The expanded 48-test browser run reached the existing global login-source cap of 40.
Dedicated review accounts alone did not remove repeated source charges. Tests
now reuse real authenticated sessions in worker memory; production limits remain
unchanged and no session cookie is written to evidence.

## Executed local proof

- Focused work/storage/runtime/review API: 64 passed in 148.75 seconds.
- Final complete API: 403 passed in 547.77 seconds on real disposable PostgreSQL/Redis.
- New exact-instant and two-contributor browser regressions: 2 passed in 10.2 seconds.
- Ruff check/format, strict mypy 25 sources, wheel/source build, production web
  build, web lint/types, generated OpenAPI/TypeScript and packaged node syntax passed.
- Final complete browser suite: 48 passed in 2.7 minutes, with the unchanged
  account/source login caps and real in-memory session reuse.

Commands are retained in the task plan and runbook. Original absent-route/schema
and browser RED observations preceded implementation. Raw outputs, reports and
synthetic screenshots stay outside Git; only sanitized conclusions belong here.

## Hosted and actual target qualification

All five hosted workflows passed on the exact application source above:

- [API 42753564545](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42753564545):
  403 tests in 135.10 seconds, migrations/drift, Ruff/format/mypy and Python build.
- [Browser 42753564582](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42753564582):
  48 tests in 1.3 minutes, locked build/types/contracts/native guard; dependency
  audit reported no known vulnerabilities.
- [Source 42753564896](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42753564896):
  SAST and tracked-source secret gates passed.
- [Images 42753564591](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42753564591):
  five service-image security gate passed.
- [Containers 42753565001](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42753565001):
  real Docker/HTTPS/persistence/task/browser and ShellCheck proof passed.

Actual target smoke ran 2026-11-10T04:05:33.617453Z to 04:09:20.542954Z, exit 0.
Private directory /root/altvia-work-core-d5ae972-040512 and task project
altvia-test-fa4cebf616 preserve earlier qualification directories and volumes.
The guest flags still lack ssse3, sse4_1, sse4_2, avx and avx2. No SSH server,
firewall or host execution/security policy changed. Commands reused the verified
user-authenticated task master, with no credential storage or fallback.

Packaged proof covered real task creation/edit/owner/participant/date/subtask,
protected transition/comment replay, cycle refusal, customer/internal/private
scope, safe activity and persistence after API/PostgreSQL recreation. Browser
proof operated the same packaged API, blocked/commented/reloaded a task and
explicitly completed ongoing child work without cascading parent state. Existing
logical Bookworm-to-Alpine restore/Unicode/FTS, HTTPS/session/CSRF, identity/client/
project boundaries, secret exclusion and shutdown proof remained passing.

Native/cgroup verification passed for all services and the migration job: actual
memory/CPU/PID limits, read-only roots, dropped capabilities, no-new-privileges,
private database/queue networks and only loopback ingress. API reports Python
3.12.16/zlib 1.4 with SQLite/installers absent. Web reports Node 24.22.1/zlib 1.4/
Brotli 1.2.1/OpenSSL 3.5.9, standalone present, Sharp/installers absent. Worker uses
the API image; SIGTERM during blackholed Redis exited 0 in 9.485292135 seconds and
all 27 events recovered. This establishes exercised paths, not representative load.

| Actual target image | SHA256 image ID | Reported vulnerabilities |
| --- | --- | --- |
| API / worker / migrate | a8c589ed043fe4099bed327ce8773c1e38dd90f90698731ad7e0e469b7459273 | 0 |
| PostgreSQL | 7b771e57b5010073e24f18478b5fae05ea129a13ae59913e1499e569922ffa1a | 0 |
| Web | 03f9148ef7aa15db3cf8c4f569008ba64bfeb27384937c6f90624c341906c65c | 0 |
| Ingress | aea5fbb905663469eb4b1e94f35da957c8719c30b9793779d17028116eac2241 | 0 |
| Redis | 5ff0d0b743bf540801fd30af50d4aec84ba267e9936ed54c92b0fde2a5d3c634 | 0 |

Pinned Trivy 0.75.0 scanned all five unfiltered images, with no suppression or risk
acceptance. DB UpdatedAt 2026-11-09T19:03:15.276467525Z, SHA256
8c808b8e2b45da2b9849fab569412fd5b0a59455d3335ea0321f0179bcd86130.
Scanned IDs exactly match resource/native-tested IDs. Zero findings describes
that scanner/database snapshot; future artifacts must repeat qualification.
The comparison above uses Docker runtime IDs recorded in the scan manifest.
A supplemental evidence check initially equated those with Trivy's internal
archive ImageID and failed. These fields differ on this export path. The trace
also verifies each unique task tag/reference, ordered filesystem DiffIDs,
configured user, report SHA256 and nonempty package inventory (66 API, 49 PG,
43 web, 70 ingress, 16 Redis packages). Both identifier sets remain in the raw
evidence; no mismatch was hidden by rewriting scanner output.

All 12 actual packaged PNGs were opened and inspected, including task directory
and persisted task detail with author IDs. Captures waited for loaded states and
started at the document top, avoiding the prior long-page skip-link artifact.
The 19 local theme/viewport/reader/recovery/instant captures and layout measurements
remain distinct from actual packaged captures.

Raw evidence was saved outside Git through the security artifact tool:

- artifacts/phase2-work/qualified-target-evidence.tar: revision/state, exact target
  outputs, native/cgroup checks, outage proof, image reports and 12 PNGs. SHA256
  96f36195d65ec4c77d573a9e3a6f65a067c166a289097a887fd7701b72035093.
- artifacts/phase2-work/local-browser-evidence.zip: 19 reviewed local captures,
  layout measurements, surface brief and documentation. SHA256
  e7b7d30c87c11e2099456026d454eaa4922c49cc358e6bdeba42b82de764bffb.
- artifacts/phase2-work/hosted-gates.json: five exact-source success records.
- artifacts/phase2-work-local/: sanitized final API/browser outputs, original
  login-cap failures, source-review transcript/addendum and Impeccable verdict.

Final verification found no running task containers and retained
altvia-test-fa4cebf616_postgres_data. The task SSH master was closed, then the
temporary local WSL keeper was stopped. Earlier directories/volumes are untouched.
Subsequent documentation-only commits do not change qualified source/image IDs.

## Remaining scope

Stop at qualified task core. Kanban, richer filters/search/My Work, external client
contacts/default ticket-project contracts, service desk and later integrations
remain on the roadmap. This slice does not establish production capacity, backup
policy, retention approval, actual data mappings, email-provider settings or pilot
acceptance. No production workload, real source workbook or Zammad was changed.
