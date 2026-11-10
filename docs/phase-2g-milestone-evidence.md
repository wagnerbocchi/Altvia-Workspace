# Phase 2G project milestone evidence

Status: Phase 2G development, review and local/hosted acceptance complete on
2026-11-10, application 011e0a5347b13e097aa2c5d871f93e9d00976be7.
Target-VM qualification is deferred until
remaining MVP development is complete, following the user's 2026-11-10 instruction.
This report does not close Phase 2 or authorize production deployment.

## Scope and implementation

Contracts, ADR-0024 and the implementation plan preceded code in 83c0858.
Backend 14bee57 adds project-owned milestones through expand-only migration
b46087000011, scoped HTTP routes, own versions/ETags, minimal protected creation
receipts and redacted project activity. Milestones start planned; conclude or
cancel them, then explicitly reopen before choosing another terminal state.
There is no deletion, task-state synchronization, access grant or invented progress.

Identity serialization precedes authentication; writes then lock the scoped Project
before the milestone. Actual changes require active project/team/customer references
and atomically advance both versions with audit/outbox. Fresh management precedes
creation replay. A cross-project child ID is never readable through another parent.
Runtime API receives SELECT/INSERT/UPDATE, never DELETE; worker gets no table access.

Shared altvia.deadlines retains existing work date/instant validation, local-day
boundaries and DST behavior, with compatible work re-exports. The browser preserves
untouched exact instants, including sub-millisecond precision, and reviewed versions.
An uncertain creation retains its original body/key across independent read failures.
Browser delivery is 128a718. Records and empty pages expose scoped
project_writable eligibility separately from
management authority. Archived references remain readable without enabling new writes.

No dependency or ISA requirement was added; existing vendor library updates below
retain the selected image families. No target SSH, production deployment, real
data import or server/security change occurred in this delivery.

## Local evidence

- `python .superpowers/phase1-tests/run.py --api -q`: 500 passed in 840.37s after
  shared deadline extraction. This run started before the final writability response
  refinement; the latest affected suite below and final hosted suite cover that change.
- `python .superpowers/phase1-tests/run.py --api apps/api/tests/test_project_milestones.py -q`:
  latest 20 passed in 65.26s. Initial missing-route RED had 18 failures; missing
  project_writable also failed before implementation. Real SQL tests cover lifecycle,
  deadline boundaries/precision, ACL, replay/no-op, stale races, event redaction,
  least privileges and data-preserving/refused destructive downgrade.
- Initial browser RED found the missing project link. Initial five milestone
  workflows passed in 11.8s. Desktop width then failed with a 616px wrapper inside
  a 1440px main; the existing feature-scoped full-width pattern corrected it.
- Complete browser suite passed 72 in 4.0m after the width correction. Final
  reviewed corrections were followed by all five milestone tests passing in 13.0s
  and another complete 72 passing in 4.0m.
- Ruff/format (87 files), mypy (30 source files), generated OpenAPI/TypeScript,
  web check/build and dependency audit passed. No known dependency vulnerabilities
  were reported; no new dependency or Sharp was introduced.

The runner creates disposable local PostgreSQL/Redis containers and a localhost
Podman tunnel. It does not access the target server. Existing next-start standalone
and NO_COLOR warnings are development-harness warnings, not failed product checks.

## Source and visual review

One fresh whole-increment source review found no Critical or Important issue.
Its Minor wrong-resource paging labels were also a material Impeccable copy finding
and were corrected. The review did not assess deferred target-VM qualification.

Impeccable reviewed 16 actual directory/detail/edit/confirmation captures across
desktop 1440px/mobile 390px and light/dark. Every capture checks axe, overflow and
readable desktop width. It requested two material corrections: milestone paging
labels and the dark native calendar affordance. Both regression checks failed first:
missing Marcos anteriores and computed color-scheme light under a manually added
dark class. The latter was a capture defect: next-themes still owned an inline light
native scheme. Driving the actual theme button and asserting computed color-scheme
corrected the evidence without changing product CSS or native input semantics.

After one batch, rebuild and all five real milestone workflows passed. The same
reviewer reopened all 16 valid refreshed captures and scored both fixes resolved.
Its ship verdict covers those two fixes, not a new whole-surface review. The
incumbent code-led direction has no separate QUALITY BAR card or approved comp;
the reviewer judged against DESIGN.md and the recorded inherited direction.
The fresh documenter checked the finished extension and preserved DESIGN.md and
its sidecar. Existing empty narrative.rules drift was reported without repair;
no new system rule, raster or visual identity was introduced. No review Minor
remains deferred for this milestone increment.

## Hosted gates

Initial application 128a718 passed API (500 in 294.15s), browser (72 in 2.1m),
container and source gates. Its service-image gate failed, so those four passing
gates did not close development acceptance. The full failed scan and all reports
are preserved, alongside the subsequent correction evidence.

[The initial image run failed](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42891895110).
It reported 50 installed occurrences: 36 HIGH, 12 MEDIUM and 2 UNKNOWN, across
API/PostgreSQL/ingress. Web and Redis had zero. All affected occurrences belonged
to krb5-libs 1.22.2-r1 or libxslt 1.1.43-r3. The configured signed Alpine 3.24
repository advertised krb5-libs 1.22.3-r0 and libxslt 1.1.43-r4.

Following ADR-0013, the correction pins those vendor updates in the three affected
Dockerfiles. It preserves image-family digests, PostgreSQL major/data family,
entrypoints, privileges, resource bounds and GOAMD64=v1; no suppression or unsafe
library removal is used. Vendor correction 011e0a5 passed the local five-image
rebuild/scan: API 66, PostgreSQL 49, ingress 70, web 43 and Redis 16 inventoried
packages, with zero vulnerabilities at every severity. Its exact scanner DB matches
the failed hosted run: SHA256
cf7fa3086682e8f77298ca8178419a530f97d7c4bd3ac203a64f2977f82e94a6,
UpdatedAt 2026-11-10T19:01:23.081219346Z. Before/after package inventories change only
the intended libraries and the generated API virtual-dependency build timestamp.
The first disposable package probe encountered the already known local Podman
cgroup-controller limitation; the retry used --cgroups=disabled only for that
ephemeral development probe. Service Compose limits remain enforced by hosted CI.

The corrected hosted image gate passed with the same scanner DB and zero reported
vulnerabilities in all five complete inventories. These are scanned hosted images,
not target-VM-qualified artifacts:

| Service | Scanned image ID | Packages |
| --- | --- | --- |
| API | sha256:32c01ee495bfdff3a7705d0618fd9a592c3da16fa46d546eeb4664324c53a5b8 | 66 |
| PostgreSQL | sha256:98388adecb53a63708e6b1039b585c04a5040be4be1f6c65b4cccd34e2698d29 | 49 |
| Ingress | sha256:3b5b484e126892044654656abd340925d6e3339adb06b2790f242933bd4db3d1 | 70 |
| Web | sha256:44a7a694dfc52eb72021a8ff211b3913e7ab625278ef178c89e538d3b7a29afd | 43 |
| Redis | sha256:cf89c6800cc31b2ada118e93dd0c5a4e91d296e3076d565ba2c7c601d48ef9b4 | 16 |

All five final hosted gates passed on exact
011e0a5347b13e097aa2c5d871f93e9d00976be7. Complete logs, metadata and downloadable
artifacts were retained. No gate, timeout or suppression policy was relaxed.

| Gate | Exact run | Result |
| --- | --- | --- |
| API | [42893353157](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42893353157) | 500 passed in 347.36s; format/lint/mypy/migrations/build |
| Browser | [42893353135](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42893353135) | 72 passed in 2.5m; types/lint/build/contracts/audit/native guard |
| Containers | [42893353319](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42893353319) | Corrected-image packaged HTTPS/browser/ACL/persistence/worker/recovery and logical restore |
| Service images | [42893353160](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42893353160) | Five complete inventories; zero reported vulnerabilities, same DB as initial failure |
| Source | [42893353122](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42893353122) | Zero detected secrets/blocking findings; four existing LOW SAST metadata findings retained |

## Preserved evidence

Private durable artifact: phase-2g-milestones-011e0a5/acceptance.zip,
116 files, 4165948 bytes. SHA256
05c65190970d75b3440436fa25350571a9fb7d291a7036a7aadd23eae1dc157e.
All file sizes/hashes and ZIP integrity were checked. It retains initial failures,
final local/hosted logs and scans, before/after package inventories, source review,
Impeccable review/verdict/documentation, and the 16 exact reviewed captures.
Source workbooks, credentials, private keys and production data/logs remain outside Git.
The final documentation commit and publication check are recorded separately;
only Markdown documentation follows the verified application source.

## Rollback and remaining scope

Keep expanded schema, all milestone/audit/outbox/activity records and volumes.
Migration downgrade refuses populated or event-bearing data before DDL. Application
rollback must retain a worker supporting project.milestone_created/updated, or stop
the worker until a compatible version resumes. Never force downgrade or erase history.

Reusing work deadline semantics avoids a second timezone policy; incorrect shared
behavior would affect both domains, so existing work regressions remain required.
Final integrated baseline-VM qualification stays pending under the requested cadence;
local/CI proof does not establish CPU compatibility of changed images. External work
participants remain the next bounded Phase 2 slice; advanced dependencies remain P2.
