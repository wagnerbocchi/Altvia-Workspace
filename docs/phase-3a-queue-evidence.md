# Phase 3A queue configuration evidence

Development acceptance complete on e3a79c2, 2026-11-10. All five hosted gates
passed. Target qualification follows remaining MVP development under the user's
cadence.

## Delivered behavior

Contracts 0f9059d preceded backend 7ef3a7a and browser 30e337e. ADR-0026 adds scoped team-owned queues
and queue-owned categories, with real name/active/version persistence, archive
and restore, protected creation, deliberate reviewed-version editing and scoped
history. Configuration uses global platform or explicit team metadata authority.
The SQL visibility predicate runs before cursor/order/limit. Creation authority
is calculated independently of the current list page. Team roster and customer
configuration cannot supply missing queue configuration roles.

Migration b46087000013 is additive, adds FK/unique/name/version/page constraints
and expands the activity resource allowlist. Queue and category parents are
immutable in HTTP contracts. Writes take identity lock before authentication,
then team, queue and category. Real child changes advance the child and queue
aggregate. Audit/outbox share that transaction. Strict redacted worker events
project once and remain outside identity history. Runtime API privileges are
SELECT/INSERT/UPDATE, and the worker receives no queue/category table access.

## Executed local checks

- Initial API RED had 13 missing-route failures in 21.06s. The first green run
  passed 12 and failed one projected-activity write because the migration had
  not expanded ck_activity_resource. The corresponding model/migration constraint
  was corrected using the existing expansion protocol. Final focused tests passed
  17 in 46.35s. The complete local API suite passed 540 in 949.56s.
- API lint/format/mypy, generated OpenAPI/TypeScript and web check/build passed.
  Generated pre-existing API schemas remain semantically unchanged according to
  the source review's parsed comparison against the prior revision.
- Browser RED had six absent-route failures. First implementation passed five
  of six. The lifecycle test sent its next queue action before the category
  restoration and parent refresh completed, correctly receiving 409. After
  synchronizing those sequential test steps, six tests passed in 14.5s.
- The fresh source review correctly identified the same race as a real operator
  issue on delayed reads. A deterministic delayed-parent-GET regression then
  failed on enabled queue controls. The fix uses existing TanStack mutation and
  read state to block dependent metadata controls through reconciliation and
  failed reads. Eight feature tests then passed in 17.2s, including actual
  keyboard operation and Unicode no-op preservation.
- The first complete browser run passed 86 and failed one test in 4.5m. The
  successful delayed-parent variant removed its interception while the handler
  was still continuing the released request, producing Playwright's Route is
  already handled error. The failed-refresh variant passed. After waiting for
  the actual response to finish before removing interception, all nine affected
  browser tests passed in 19.9s. The final complete local rerun passed all 87
  tests in 4.6m.

The browser fixture reuses real password-backed disposable work sessions, a
separate scoped team and 12 actual queue rows for pagination. It adds no new
functional HTTP-login budget. All local databases/Redis are disposable and the
only tunnel is the local Podman loopback. No target-server connection occurred.

## Reviews, limits and decisions

The sole immutable source review artifact has SHA256
df54aa4e0a1fd870c596071dd91f03a9df957f57c2f435b227cc8586c591f72d,
covering a443432 plus contracts/backend and the staged increment. It reported
one Important stale-version UI issue and one Minor raw SQL whitespace check gap.
The Important issue was fixed in one regression-tested pass. The Minor is deferred
and documented in the runbook. HTTP input validation rejects tab/NBSP-only names,
while direct SQL btrim checks currently recognize ordinary spaces only.

Source inspection also distinguishes coverage from executions. The current
domain tests do not separately prove every combination of client-only principal,
global-admin receipt revocation, cross-parent PATCH, archived-team no-op/edit,
child overflow or interleaved multi-team paging. Existing foundation tests and
reviewed shared protocols remain relevant. No exhaustive or load-proof claim
is made from the focused cases. The final affected frontend run also covers
keyboard operation and Unicode round-trip behavior.

Impeccable's full-surface review inspected all 16 directory/detail/category-edit/
recovery captures at desktop 1440/mobile 390 in light/dark and returned ship with
no material fixes. The helper uses the actual theme control, browser color-scheme,
axe and overflow checks. Root opened all 16. The variable desktop plane width
was assessed and accepted in that review. After the source fix, the reviewer
directly checked all 16 final frames and returned ship again at that correction's
scope. The documenter verified the incumbent system and its unchanged artifacts.
Existing empty sidecar narrative.rules drift remains recorded for separate work.

Selected team-owned configuration permits shared routing across customers when
later ticket authorization is implemented. Exact archived-name uniqueness means
operators restore records or choose another name. The established registry
composition reuses the incumbent Operate world and session-owned recovery.

## Hosted acceptance

All five gates passed on exact e3a79c227403291284a4e8a663a6f46449b34699.
Full run logs, job/artifact metadata and downloadable artifacts were collected
separately from the initial 30e337e runs. The packaged extension creates actual queues and
a category after the 27-event outage proof, then checks version/state, scoped
reads, hidden queue and denied writes after API/PostgreSQL recreation.

Test-only e3a79c2 refreshes the existing reader CSRF header after reader login and
asserts problem.code forbidden on the packaged queue PATCH. This distinguishes
the tested authorization refusal from an unrelated CSRF failure. It adds no login
or account and changes no application behavior.

The initial hosted browser run on 30e337e passed 86 and failed the pre-existing
contact lifecycle test waiting for its created-contact heading. Logs show no
contact POST in that failed interval. Full error-context files were not uploaded
by that workflow, so the cause remains unestablished. Current local 87 and final
hosted 87 on e3a79c2 passed with unchanged contact implementation. This observation
extends Q-17's runner-reliability investigation. No timeout/retry was relaxed and
no contact root-cause correction is claimed. Original full logs remain retained.

| Gate | Exact run | Result |
| --- | --- | --- |
| API | [42919395807](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42919395807) | 540 passed in 272.29s, lint/format/mypy/migrations/build |
| Browser | [42919395847](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42919395847) | 87 passed in 2.8m, types/lint/build/contracts/audit/native guard |
| Containers | [42919395832](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42919395832) | Actual queue/category scope and recreation proof, packaged HTTPS/browser/worker/recovery and logical restore |
| Service images | [42919395887](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42919395887) | Five complete inventories, zero reported vulnerabilities at every severity |
| Source | [42919395789](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42919395789) | Zero detected secrets/blocking SAST findings, four existing LOW metadata findings retained |

Each image report was read, its SHA256 checked against the manifest and its
installed package inventory confirmed nonempty. Scanner database SHA256 is
cf7fa3086682e8f77298ca8178419a530f97d7c4bd3ac203a64f2977f82e94a6,
UpdatedAt 2026-11-10T19:01:23.081219346Z. These are the current hosted scanned
artifacts. Packaged functional testing performs a separate build of the same
source. Final target qualification must use exact target-tested image identities.

| Service | Scanned image ID | Packages |
| --- | --- | --- |
| API | sha256:3c0239afef7112f99725f44d5870a276b2c84d62905288f50f905ef963a385c0 | 66 |
| PostgreSQL | sha256:a9cc8d52af7cded88d6b8d7cceef8affb2acc3b00ee0bbd75c5a867758aad4de | 49 |
| Ingress | sha256:eab1685baa46f56eac6c7de2baf0cc9b342458d6c4807614b400724bf97f44a5 | 70 |
| Web | sha256:c2e80461394bfc48d1cdfa957d17900864abe3e1c232daf307da3818db7cc2f8 | 43 |
| Redis | sha256:c00871808cf436205d2333b8ef981fd5aea2f491c3d7396ceec1ee4a17c37289 | 16 |

Source metadata retains cli.py B105/B101, management.py B101 and provision.py B101
at LOW severity. The direct SQL whitespace follow-up is the separate source-review
Minor described above. Full logs distinguish negative SQL constraint/grant/
downgrade refusals and the accepted raw concurrent graph deadlock from failures.
Existing action/runtime deprecation and harness warnings remain visible.
No gate, cap, timeout, retry or suppression policy was relaxed.

## Remaining scope and rollback

Private durable acceptance artifact is phase-3a-queues-e3a79c2/acceptance.zip,
159 files and 5914356 bytes. Its SHA256 is
e8fb4deecb9d97e1cf2cf9ff603a66b70fc5e51da08520dc038226e7ac7d0d46.
Every file size/hash and ZIP integrity were verified. It retains complete initial
and final local/hosted runs, source/image reports and inventories, exact artifact
metadata, the immutable source review and regression fix, original/final visual
captures, Impeccable review/recheck/documentation and design context. Final ledger
and publication verification are retained separately from the immutable archive.
Only Markdown documentation follows the final tested source. Credentials, source
workbooks, real customer data and production logs stay outside Git.

Phase 3 ticket lifecycle and queue content-role administration follow this slice.
Messages, private attachments and native mail transport remain subsequent work.
Mailbox/provider policy stays Q-03/Q-16 and final baseline-VM qualification stays
pending. Production data import and live Service Desk cutover remain separate
owner decisions. Preserve expanded data and a queue-event-compatible worker on
rollback. This increment alone does not close Phase 3.
