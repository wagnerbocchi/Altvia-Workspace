# Phase 2B project and operational-area registry evidence

Date: 2026-11-09. Scope: ADR-0019 registry slice. Qualification complete.
No work items, production deployment, real membership import or Zammad cutover.

## Behavior, changes and ownership

Real internal/customer projects now persist with explicit initial-manager
delegation, owning team, optional operational classification, scoped metadata
lifecycle, actual members and project-only activity. Areas have a shared
authenticated catalog and protected create/rename/archive/restore. Classification
is not a permission. Project scope/customer/team cannot be changed by PATCH.

Customer projects require the independent customer ceiling, then either inherited
client viewer/operations_manager or a project role plus membership. Internal
projects require the explicit role/member pair. Team metadata roles and global
administration never bypass content scope. Metadata writes require client
operations_manager/project_manager. Further member/role changes use confirmed
host CLI, never an implicit customer grant. Sessions invalidate and audit/outbox
commit in the same identity-serialized transaction. Creation/replay returns only
project/manager UUIDs and rechecks authority before exposing a stored receipt.

The interface uses real bounded selectors, explicit delegation/relogin, directory,
detail, area assignment/clear, members and scoped history. Existing private cache,
session fencing and protected-write hooks own recovery. Creation authority comes
from the API and remains observed across list pagination; unrelated reads cannot
discard an uncertain original body/key. No counters or placeholder boards/tasks.

Contracts and plan preceded code in fa14b3f. Backend caa9deb; fresh creation
authority 7172128; browser c40198e; packaged proof 5faa866. Exact qualified
application source is 5faa866301934865926db127e5a6b701ba473500. Archive SHA256
0bf1e72e6a3c5210d5332024f59b0651f2e31d2d771f9f1ec3b159d7366c3662.

Migration b46087000007 adds areas/projects/members and exclusive project role
scope, plus project/area activity types. It preserves existing data and refuses
populated downgrade before DDL. API gets required operational table DML; worker
gets no project/area table authority. No dependency/native version, service,
search engine or ISA requirement was added. Keep expanded data and a compatible
worker on rollback; stop an incompatible worker rather than dead-letter new types.
Never force downgrade, delete history or reset volumes. Commands and limits:
docs/runbooks/project-registry.md.

## Review, failures and corrections

Fresh whole-source review found no additional material source bug after the
event-family fix, but required direct DB/API authorization evidence. The expanded
matrix proves inherited-only client roles, all three direct project roles, either
membership/binding half missing, actual team-only/admin-only denial, forbidden
viewer writes and scoped replay after creation-authority downgrade.

An event-family regression test reproduced acceptance of identity.user_created
with aggregate_type=project. Exact event-family/resource matching now rejects it,
alongside malformed payload/role/field tests. Existing worker lease/deduplication
and unknown-event behavior remain unchanged. The first full API run passed 348
and failed only an older migration test hardcoded to head 6; its head-preservation
assertion now resolves the current migration head and passed independently.

Impeccable full review returned fix: hide creation for readers without creation
authority and update PRODUCT truth. The reader browser regression reproduced an
unrelated team403/access challenge caused by unconditional provisioning queries.
The API now computes can_create independently of bounded client/project pages.
A bounded source follow-up then found that tying form mounting to the current
page's pending data lost its protected intent on cursor changes. A real lost-POST
plus 11-project pagination test reproduced the missing verification control. A
stable observed authority query now keeps the form mounted across paging/errors,
while explicit fresh false and session changes still remove it. Original key/body
matched on replay 200. A separate test fixture timeout selected a new team outside
the first bounded page; the test now pages the real selector and waits for its
response rather than assuming the first page.

Impeccable verdict pass scored both listed fixes resolved, disposition ship;
this is the scope of that verdict. The source reviewer scored the intent-loss
finding resolved. Documenter preserved the incumbent system; PRODUCT received
only capability facts. Preexisting empty sidecar narrative.rules drift remains
unrepaired. Fifteen supplied light/dark desktop/mobile/reader/recovery captures
were inspected; no new world, assets, comp or detector rerun was introduced.

## Executed local validation

- Full API: 358 passed in 438.78 seconds on real disposable PostgreSQL/Redis.
- Latest API gate adjustment: 25 project API tests passed in 61.44 seconds; worker/
  event/migration focused suite 17 passed after exact-family correction.
- Full browser before final visibility gate: 41 passed in 2.2 minutes. First 42-test
  run passed 41 and exposed the bounded-team fixture timeout, corrected above.
- Final five project flows passed in 19.2 seconds, including real uncertain POST,
  pagination/recovery and reader gating. Final complete browser 42 passed in 2.3 minutes.
- Ruff check/format, strict mypy 22 source files, generated OpenAPI/TypeScript,
  pnpm web:check, production web build and Python source/wheel build passed.
- Packaged script Ruff and node --check passed before publication.

Commands: uv run python .superpowers/phase1-tests/run.py --api apps/api/tests -q;
uv run python .superpowers/phase1-tests/run.py; uv run ruff check apps/api scripts;
uv run ruff format --check apps/api scripts; uv run mypy; uv build;
uv run python scripts/export_openapi.py; pnpm --filter @altvia/web generate:api;
pnpm web:check; pnpm web:build; node --check scripts/container_browser.mjs.
Task-local helpers retain sanitized outputs outside Git and reset only their
explicitly disposable databases. Production rate controls were not weakened.

## Final hosted and target qualification

All five hosted workflows passed on the exact application revision above:

- [API 42734246619](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42734246619): 358 tests in 151.48 seconds, lint/format/mypy, migrations/drift and Python build.
- [Browser 42734246403](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42734246403): 42 tests in 1.3 minutes, locked build/types/contracts/native guard and dependency audit.
- [Source 42734246761](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42734246761): source SAST/secret gate passed.
- [Images 42734246376](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42734246376): five service-image security gate passed.
- [Containers 42734246864](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42734246864): real Docker/HTTPS/ACL/projects/areas/recovery/packaged-browser and ShellCheck passed.

Actual target smoke ran from 2026-11-10T01:14:06.503851+00:00 to
2026-11-10T01:17:41.452652+00:00 (2026-11-09 local date), exit 0. Private directory
/root/altvia-project-registry-5faa866-011352 preserves earlier qualification
directories. Task project altvia-test-67b56b9320 built/executed the five images
on the supplied guest, whose flags still lack ssse3, sse4_1, sse4_2, avx and avx2.
No SSH server, firewall or Windows execution policy changed. Commands reused the
user-authenticated task-scoped SSH master, with no credential storage or fallback.

Packaged proof passed logical Bookworm-to-Alpine restore/Unicode/FTS, real
HTTPS/session/CSRF/non-root/secret boundaries, explicit project delegation/relogin,
internal/customer isolation, safe members and scoped activity. API/PostgreSQL
recreation preserved project/area metadata; browser area/project lifecycle,
history and axe passed. Worker SIGTERM during blackholed Redis exited 0 in
8.783825911999884 seconds and all 27 events recovered.

Actual cgroups verified memory/CPU/PID limits for every service; read-only roots,
dropped capabilities, no-new-privileges, private database/queue networks and only
loopback ingress passed. Native API checks report Python 3.12.16/zlib 1.4, SQLite
and package installers absent. Web reports Node 24.22.1/zlib 1.4/Brotli 1.2.1/
OpenSSL 3.5.9, standalone present, Sharp and installers absent. This qualifies
exercised paths and exact artifacts, not representative load or production capacity.

| Actual target image | SHA256 image ID | Reported vulnerabilities |
| --- | --- | --- |
| API / worker / migrate | 13e68b447a776184822e66d450bff04e960f6e03eac991469bcbef875f703fc8 | 0 |
| PostgreSQL | 67ad558c83136509547412dae5b2d81dd6888dee62ad98ecd1e86f82857dcd33 | 0 |
| Web | 314523d0b88d2d2dd4e717649f3e6ba69895328e96d92eb88866eb8dff2bc3ec | 0 |
| Ingress | d0c4c2c01038f2121fe7dc73781bbd8143ed60a1f08124597db39fd1347f4b6c | 0 |
| Redis | d46aa9c8e052262ae2b21d2d99a70730bc5d85556d3e399f430c7ef28572a81f | 0 |

Pinned Trivy 0.75.0 scanned all five unfiltered images using DB SHA256
8c808b8e2b45da2b9849fab569412fd5b0a59455d3335ea0321f0179bcd86130.
Scanned IDs exactly match resource/native-tested IDs; worker uses the API ID.
Zero findings describes that scanner/database snapshot, with no suppression or
risk acceptance. Future artifacts must repeat the target/native/security gate.

All ten actual packaged PNGs were opened and inspected. project-mobile.png
showed an unfocused fixed skip link over the archive control in the full-page
capture. A controlled same-image diagnostic on the actual packaged login/CSS
reproduced the capture artifact by changing only the diagnostic DOM main height.
At scrollY=700, the link bounds remained -78..-34 before/after the full capture;
the actual viewport and top-of-page full capture omitted it. Keyboard focus exposed
the link at 10..54, and Enter focused main. All four diagnostic captures were
inspected. No product CSS, application image or database mutation was needed.
The original project screenshot remains retained with this explicit limitation.

Raw evidence is retained outside Git through the security artifact tool under
artifacts/phase2-projects/ in persistent storage:

- qualified-target-evidence.tar: source/state, exact outputs, native/cgroup checks,
  outage proof, actual-image reports and ten packaged captures; SHA256
  64ec95d6fd77f7e2367dd326b680896c0a4f37a0881f16141f0fb78e4587b70c.
- local-browser-evidence.zip: fifteen reviewed local captures, sanitized final
  browser log, surface brief and documenter evidence; SHA256
  0cb7523c079755b73d2277258247f12eacfe7abdc2f5c6ca7216d47491031265.
- capture-diagnostic.tar: same-image capture/keyboard report and four PNGs; SHA256
  e490ccb1c4495ff8e64f145885a9100ea70f41ea757b1ef5f18b39d49f2fbf67.
- hosted-gates.json and review-disposition.md retain final CI metadata and a
  summarized review disposition, distinct from an original reviewer transcript.

Task containers were stopped after qualification and again after the diagnostic;
volumes remain preserved. The authenticated task SSH master was closed. Subsequent
documentation-only commits do not change qualified application/image identities.

Projects/areas registry is not the Phase 2 gate: tasks/subtasks, owners/assignees,
comments, deadlines, graph constraints, Kanban/list/search and My Work remain later
increments. Contacts/default ticket projects/member browser writes are also later
contracts; no production membership matrix or workbook mapping is invented.
