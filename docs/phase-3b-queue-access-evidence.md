# Phase 3B queue access development evidence

Updated 2026-11-10. Phase 3B development acceptance is complete for source
9e183ef7610c78ac36262ecf433845c928150d62. Phase 3 remains open. Consolidated
target qualification follows remaining MVP development under the user's cadence.

## Delivered behavior and decisions

ADR-0027 contracts in 748c7ec preceded implementation. This bounded increment
delivers persisted explicit queue roles, operational metadata visibility and
browser grant administration for FR-001/005/012. The coordinator chose this
complete access increment before ticket lifecycle to isolate authorization and
migration risk. Actual ticket content enforcement follows its own increment.

Configuration administrators and explicit owning-team operations_manager can
delegate an existing account by known email, review the exact submitted role,
change it or remove direct access. Queue viewer, agent and operations_manager
read only their queue metadata, categories, scoped history and bounded roster.
Customer ceilings, configuration authority and team directories retain their
independent predicates. Account resolution occurs inside the authorized mutation.

Real changes invalidate target sessions, advance queue and auth versions and
commit redacted audit/outbox atomically. Current configuration authority and a
valid If-Match precede saved POST receipt replay. A receipt contains immutable
queue/user IDs and never recreates a grant. No-ops preserve versions and sessions.
Archive preserves reads and removal. New grants require active references.

The browser retains reviewed drafts and original POST intent through uncertain
responses, requires deliberate conflict recovery and blocks edits until queue
and roster refresh succeed with matching versions. Self-target changes require
login again. The surface brief was corrected to describe the actual inherited
stacked sections and desktop identity/action rows. The reviewed UI was preserved.

## Changes and schema

- API ownership remains in queue_registry.py, queue_api.py and queue_schemas.py.
  models.py and strict activity.py projection extend existing representations.
- Migration b46087000014 adds nullable role_bindings.queue_id, RESTRICT FK,
  exact typed-parent CHECK and unique partial account/queue index. Prior scopes
  survive the expand-only migration. The role binding represents queue membership.
- Generated OpenAPI/TypeScript, Service Desk member route/components and transport
  implement the real API. Existing session, paging and recovery primitives remain.
- PostgreSQL/API regression tests, synthetic browser fixtures, queue-access E2E
  and packaged Compose persistence assertions cover this increment. A separate
  project-test correction isolates a manager account from shared fixture sessions.
- Runbook docs/runbooks/queue-access.md covers operations, recovery and rollback.

The API uses existing role-binding privileges. Worker receives no binding-table
access. Exact access-event fields are actor_id, actor_kind, member_user_id and
role_name. Queue events stay out of global identity activity. Downgrade refuses
queue grants or durable access events. Application rollback retains expanded
schema/data and the compatible event consumer.

## Executed local validation and corrections

`python .superpowers/phase1-tests/run.py --api apps/api/tests/test_queue_access.py apps/api/tests/test_ticket_queues.py -q`
passed 31 tests before source review. Full local API passed 554 in 1039.99 seconds
before adding the three reviewed logout regressions. This is historical local
evidence for that revision, while final-source hosted tests cover all 557.

One fresh whole-increment source review found a target logout/access deadlock.
Plain target User FOR UPDATE conflicted with logout audit-FK key-share while
session invalidation waited for logout's SessionRecord. Three deterministic real
HTTP/PostgreSQL interleavings failed with 503 before the correction. Commit
08e8294 reuses the incumbent FOR NO KEY UPDATE lock. Add/change/remove now finish
with correct state, versions/events and session revocation. The affected queue,
queue-access and project-member suite passed 51 in 154.20 seconds. Review found
no Critical or Minor issues. Deterministic regression coverage verifies the fix.

`pnpm web:check`, `pnpm web:build`, `uv run ruff check apps/api scripts`,
`uv run ruff format --check apps/api scripts`, `uv run mypy`, OpenAPI export and
TypeScript regeneration checks passed. The final built UI passed nine focused
browser tests. The Impeccable detector returned no deterministic findings.

Impeccable inspected all 20 desktop/mobile light/dark frames and identified one
material error-truth issue. The 503 refresh state incorrectly claimed the queue
was unavailable to the account. The browser assertion failed before correction.
The UI now reserves that text for 404 and reuses accurate temporary-load failure
and retry copy for other failures. The same reviewer scored the fix resolved with
a bounded ship verdict. Its documenter checked the finished incumbent extension
and preserved DESIGN.md/design.json. Existing empty narrative.rules drift remains
documented separately.

The first post-implementation browser check served stale .next output. Rebuilding
before the runner corrected that verification error. A capture helper also
incorrectly required a visible roster during a parent read error. Its correction
asserts that the roster is hidden in that state and retains other width checks.

A later full run passed 91 and failed five after the old project recovery test
selected the shared work-reader account as initial project manager. Its retained
screenshot confirms that selection. Project delegation correctly invalidated that
account's preseeded sessions, then failed-test worker restarts exhausted the HTTP
login source budget. Test-only 9e183ef provisions a dedicated target, selects it
through real bounded paging, checks both original/replay targets and verifies
the shared reader session before and after. The final local full browser run
passed all 96 in 5.1 minutes. No cap, timeout, retry or production behavior was
weakened. Earlier Q-17 contact timeout and other unestablished branches remain open.

## Hosted acceptance

Initial application f366f40 passed all five hosted gates with 557 API tests,
96 browser tests, real packaged queue-access/replay/restart/scope proof and five
complete image inventories. Those logs/artifacts are retained independently.
Final test-isolated source 9e183ef passed all five gates with 557 API and
96 browser tests. Hosted API 557 passed in 352.92 seconds and browser 96 in 3.1
minutes. Packaged execution proved grant persistence after API/database
recreation, protected replay, queue-only reads, denied escalation/customer
discovery and the complete existing recovery/native/FTS stack.

| Gate | Exact final-source run |
| --- | --- |
| API checks | [Run 42932792141](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42932792141) |
| Browser checks | [Run 42932792009](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42932792009) |
| Container checks | [Run 42932792278](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42932792278) |
| Service image security | [Run 42932791979](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42932791979) |
| Source security | [Run 42932792216](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42932792216) |

Final five-image scans contain nonempty inventories and zero reported
vulnerabilities across all severities. Source scanning detects zero secrets and
zero blockers. Four pre-existing LOW Bandit findings remain visible in cli.py,
management.py and provision.py. Full logs, metadata and inventories are retained.

| Image | Exact scanned image ID | Packages | Reported vulnerabilities |
| --- | --- | --- | --- |
| api | `sha256:69a1e0e1b3cc213dd94f1eb228b707999b9146c34ccf0e6d3b79b56f4e923cd8` | 66 | 0 |
| postgres | `sha256:a9a250f4c76a5523a4103ae7ad1454e4dd0b610a026f424fc519d62b3c837348` | 49 | 0 |
| ingress | `sha256:be92e85fadecd58506b97ed7cf7b11329258f2602cb2364896a74971e4b8e271` | 70 | 0 |
| web | `sha256:19fe3081e795100eb5f2e09b022ae6bd2e09a0e54210f83b967753304a1d0782` | 43 | 0 |
| redis | `sha256:59f0b0311a676a712e02b32d5c09c858df4c493f57a0e3aac12fb8036f1c2285` | 16 | 0 |

The immutable acceptance archive is stored privately at
`C:/Users/wagne/.codex/state/altvia-workspace/evidence/phase-3b-queue-access-9e183ef/acceptance.zip`.
It contains 171 files and 6774281 bytes. SHA256 is
`3b1af9348c940c069d85da6312c51c554d89d065d25540ef143316b07a469040`.
Every archived entry was checked against its size/hash manifest. Initial/final
hosted results, failed and passing local logs, both regression corrections,
source review, Impeccable review/documentation, 20 final frames and confirmed
project-session interference captures remain distinct. Publication verification
is recorded alongside that immutable archive after the final documentation push.

## CPU, remaining work and rollback

This increment adds no dependency or native binary. Existing x86-64-v1 and banned
engine restrictions remain mandatory. Local/hosted execution supplies development
proof. Changed integrated images require actual final baseline-VM qualification
after remaining MVP development under the deferred qualification milestone.

Ticket creation/assignment/status/history, messages/private notes/files and native
mail transport remain Phase 3 work. Mailbox/provider and verified sender inputs
remain Q-03/Q-16. Phase 4 automation/unified work, Phase 5 SLA/analytics/import and
Phase 6 readiness remain open. Real import and production acceptance retain their
separate approvals. Prior Phase 3A raw SQL whitespace-only-name defense refinement
also remains documented in ADR-0026 and the queue runbook.

## Commit sequence

| Commit | Delivered change |
| --- | --- |
| 748c7ec | Queue access contracts before implementation |
| 8cde51d | Persisted explicit grants, scoped API, events and generated contracts |
| 08e8294 | Reviewed target logout deadlock correction and deterministic regressions |
| f366f40 | Real browser administration, fixtures, packaged proof and runbook |
| 9e183ef | Isolated project-recovery test with shared-session preservation assertions |
