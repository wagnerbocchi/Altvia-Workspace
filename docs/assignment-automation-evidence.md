# Assignment automation development evidence

ADR0041's contract and plan are selected after independent builder check. The
automation feature is NOT accepted: interface and packaged/hosted/
final review have separate remaining gates. Task1 native configuration/staging
is complete below, following the schema foundation. No production rule,
external policy, real import or final target qualification is implied.

## Task2 worker and protected recovery verification

The native worker/effect, schema2 activity and execution/retry API passed the broad
affected regression. This accepts Task2 backend development only, not whole-feature
or final target acceptance. Tests use private synthetic
PostgreSQL/Redis fixtures on the user-selected altvia-vm development host.

Shared work_creation now owns actual manual and automated creation/history. Manual
receipts and schema1 envelopes retain their original shape. The second writer
uses current revision-authorizer scope, independent contributor checks, native
ticket-before-project locks, an immutable logical effect and the final database-
clock lease predicate. No private ticket text or implicit project/account/grant
is created. The JSON-only assignment_work actor is registered in the existing
worker, with database-owned attempts/recovery and no broker retry.

Execution pages filter current target visibility before LIMIT/cursor. Protected
retry retains the original source/revision and reviewed version; current authority
precedes even a committed minimal replay receipt. It cannot revive a later
disabled/cancelled execution. Generic activity labels automation truthfully and
omits internal execution IDs; reciprocal link history still requires both scopes.

Migration30 adds only the derived restricted assignment-source view. Actual-role
RED recovery-role-red01 returned503 because the API could not read its source;
the correction grants SELECT only on the assignment-only whitelist view, retaining
denial of general outbox payload/table reads. No previous migration is rewritten.
Its contraction drops derived metadata only, preserving all ledger/source rows;
retain the expanded schema for binary rollback and drain before contraction.

Actual intermediate results:

- effect-green03:65 passed,1 failed in271.89s. The domain writer and manual-pair
  instrumentation correction ran successfully. The remaining failure was a negative
  privilege test querying nonexistent ticket_notes.body (42703), rather than the
  actual body_text; the test was corrected to prove42501, including public-message
  bodies. No privilege was widened for that failure.
- transport-red01:2 actual failures for missing registered assignment actor and
  dispatcher. transport-green01:4 passed in17.75s, including existing transport
  tests, lost Redis message/recovery, committed redelivery, malformed UUIDs, stop
  before claim and persisted publication backoff. Its following static gate failed
  on new test formatting/import order, corrected before the final batch.
- effect-boundaries01:32 passed,2 failed in115.31s. One was the same body-column
  typo; the other was test SQL interpreting a JSON literal colon as a bind name.
  jsonb_build_object fixes the fixture without weakening product validation.
- recovery-red01:3 actual missing-route404 failures. recovery-green01:39 passed,
  2 failed in144.27s: the old malformed test SQL and an expected403 that must be404
  under the native hidden client-configuration scope. The native denial remains.
- recovery-role-green01:9 passed in42.96s; actual API/worker role execution,
  source corruption and strict/current-scope recovery passed. Ruff/check/format,
  mypy75 and the frozen source maps passed.
- worker-final-boundaries01:2 passed in11.45s; ticket version exhaustion rolls back
  every new work/history/link/effect, and a new post-enable assignment uses its new
  revision while the old unexpired token remains cancelled. Static/frozen checks
  passed. This adds tests only after the broad batch's frozen snapshot.
- worker-regression01:222 passed in697.15s, no skips or warnings reported. Complete
  automation rule/schema/effect/recovery/activity modules plus native worker,
  restricted runtime provisioning, work creation/history/external participants,
  review and ticket/work API/storage regressions passed. Ruff/check/format,
  mypy75 and frozen source maps passed. PostgreSQL and Redis stopped; retained
  data volumes were preserved and the verified own empty internal network retired.
- worker-current-authority01:13 passed in58.36s, including the six incumbent
  resolution cases, six additional queue/configuration/client/assignee revocations
  and inactive parents, plus pending old-assignee supersession. Static/frozen gates
  passed. These counts overlap the broad batch and are not summed as unique cases.

The actual installed local export commands ran twice: uv run --offline python
scripts/export_openapi.py and pnpm --filter @altvia/web generate:api. OpenAPI
remained byte-stable; all79 incumbent paths and151 component schemas remain equal.
Only the execution collection and protected retry paths are added. pnpm web:check,
Ruff/check/format and mypy75 passed. Generated contract hashes/commands are retained
in task2-generation.json outside Git. No dependency or native binary was added;
this does not qualify changed production images on x86-64-v1.

Independent read-only backend review found no confirmed Critical/Important issue
in the effect, lease, authorization, ACL, projection and recovery code. It deferred
actual broad/packaged/browser acceptance and the UI explanation of native creation
history: history retains the true authorizer, while schema2 activity supplies the
automation discriminator. Task3 must reconcile both without private IDs.

## Schema foundation

Migration b46087000029 expands the native schema with rules, immutable revisions,
source executions and stable effect receipts. Composite FKs bind native customer/
queue/ticket/project/work and the exact origin execution. Rule/action identities
and source-event identity remain separate from the business effect key. The live
N:N edge is deliberately not the effect receipt's parent; unlink retains receipt.
Rules start disabled, and no rule is inserted by migration. Every downgrade refuses
durable rows, private history/provenance or protected intents before DDL.

The API gets explicit rule/revision/execution SELECT/INSERT, effect SELECT only
and rule version/update/cancellation-floor column UPDATE. No identity/scope column
UPDATE or effect/revision mutation is granted. The worker receives no premature
automation table or native domain-writer privilege in this sub-batch. Its actual
second writer will require separately tested exact column grants in Task2.

Activity's actor CHECK permits automation only with null actor_id and one of the
three contracted creation/link event types, preserving every older actor shape.
No new producer emits those schema2 events yet. Runtime/application manual state,
events and UI remain unchanged by the schema foundation.

## Actual native schema proof

Private local evidence root .superpowers/sdd/2026-11-14-assignment-automation;
remote /root/altvia-workspace-dev/.superpowers/assignment-automation-20261114 on
the user-selected altvia-vm. Tests use fresh private altvia_test databases,
ALTVIA_ALLOW_TEST_DB=1, internal networks, no public port, read-only source mounts,
bounded CPU/memory and unchanged input manifests. This is isolated development,
not final integrated server qualification.

- schema-red01: actual native missing-four-table assertion failed in2.65s.
- schema-green01: all10 initial schema cases passed in24.73s; native Ruff/check/
  format and mypy68 passed. Includes actual composite origin/context failures,
  strict status arrays, source uniqueness, half-lease rejection, privilege denials,
  unlinked receipt retention, history refusal and native Alembic metadata check.
- schema-nearest01:21 failed/24 passed in112.38s. Twenty failures were a fixed
  historical head28 expectation after a correctly rejected downgrade retained29.
  One compared new29 descendants' grants as if they were pre28 parent grants,
  despite intentionally recreating descendants during the empty roundtrip. No
  contraction guard failed. Full relevant run was inspected before correction.
- The incumbent test now derives Alembic's actual head and excludes only the four
  new descendants from its original parent ACL map. All earlier parent tables,
  exact row counts, unique keys, FK/refusal assertions and grant comparisons remain.
  Three additional protected-create/patch/retry receipt guards were added.
- schema-green02 stopped at Docker address-pool exhaustion before product checks.
  Only four verified task-owned internal networks with zero endpoints were removed;
  containers and volumes were retained. Exact record is network-cleanup01.json.
- schema-green03:13 schema cases plus all45 incumbent ticket-work storage/runtime
  provisioning/activity-migration cases passed,58 total in133.98s. Native Ruff,
  formatting and mypy68 passed, frozen input maps unchanged. Includes actual
  downgrade/upgrade and Alembic metadata check. No failed run is counted as passed.

Native container entrypoints ran ruff check --no-cache apps/api, ruff format
--check --no-cache apps/api and mypy --cache-dir=/tmp/mypy-cache. Native pytest
commands select test_automation_migration.py,
test_ticket_work_storage.py, test_runtime_provision.py and test_activity_migration.py.
Local installed static tools also passed. No new dependency/service/ISA flag or
production/SSH/security configuration change was made.

The matching frozen source map is schema-green03-source.json with the original
schema-green02 tar bytes. Later configuration/staging source is outside this
schema-only proof and requires its own actual execution. This sub-batch does not
claim complete API/browser/worker/hosted acceptance. Native test fixtures are
synthetic; Q-23 real rules/title/status/priority remain unconfigured.

## Native configuration and atomic staging (Task1)

Actual queue/client-scoped rule create/read/patch/list is persisted, disabled on
creation, conjunctively authorized and protected by queue/rule versions and
immutable POST/PATCH intent receipts. Edits retain rule/action identity. Every
disable advances a monotone revision floor, preserved after reenable. The rule
authorizer is explicit; no session, CSRF or implicit grant is stored.

identity.record_event now returns its actual OutboxEvent without changing any
manual envelope. The native ticket assignment owner flushes its real event and
stages a matching enabled rule revision in that same transaction. Create, patch,
claim and native mail promotion converge on that owner. Failed staging rolls back
the ticket/history/event/receipt, rather than losing the assignment's work intent.
The activity consumer strictly acknowledges private rule metadata without shared
activity. No background work creation or fake successful effect is implemented yet.

- rules-red01: the real authorized POST failed404 in6.05s before implementation.
- rules-green01:22 initial rule/schema cases passed in57.06s; native Ruff and
  mypy71 passed, with unchanged source maps.
- rules-green02:108 new/affected cases passed in377.33s, including13 schema cases,
  full ticket/mail-promotion/reciprocal-history modules, native assigned mail
  promotion/replay, create/claim replay singular staging, archive/no-op and queue
  version-overflow rollback. Native Ruff/check/format/mypy71 passed; frozen maps
  unchanged. No failures/skips/warnings reported by this pytest run.
- rules-replay01: the additional original-review/current-authority protected
  create-replay case passed; static/frozen checks passed. This is an intermediate
  focused proof, superseded for that case by boundaries02 below.
- rules-boundaries01 did not execute product checks: network pools were exhausted.
  network-cleanup02.json records only four additional retired task-owned internal
  zero-endpoint networks removed, with containers/volumes retained.
- rules-boundaries02:3 final focused cases passed in13.39s: create replay preserves
  later enabled state and rejects changed intent/current revoked scope; platform
  configuration alone cannot read/manage customer rules; six corrupted/unknown
  private event shapes enter safe dead state without activity or execution. Ruff,
  mypy71 and frozen inputs passed. This private runner also removes its verified
  own empty internal network after stopping PostgreSQL, preventing pool growth.
- queue-nearest01: both complete incumbent queue/category/access modules passed,
  34 cases in82.36s; native static/frozen checks passed. Two Pydantic
  UnsupportedFieldAttributeWarning messages named identifier and client_id while
  the existing competing-queue test constructed apps concurrently. The complete
  warning block was inspected. Both aliases equal their native parameter names;
  generated legacy contracts and actual strict/current-scope query tests pass.
  This is another manifestation of the retained app-factory/schema warning, not
  evidence establishing its root cause. No suppression or warning-free claim;
  retain the schema-owner investigation for integrated hardening.

The108-case batch precedes only additional tests, generated outputs and evidence
docs, not a runtime change. The3 final cases separately cover those new checks.
No failed/setup-only run is included in the passing counts.

generation01 used locked offline dependencies and the actual installed generator.
It ran uv sync --locked --offline; uv run python scripts/export_openapi.py;
pnpm --filter @altvia/web generate:api; repeated both exports with unchanged bytes;
then pnpm web:check passed. Output transfer hashes were verified from its saved
manifest. All77 incumbent path objects and146 incumbent component schemas compare
equal as JSON; only the two rule path templates are added. No manual DTO change.
Generated output/native manifests and complete commands remain private evidence.

Task1 is development complete. Task2's current-authority worker/effect/lease and
truthful schema2 history, Task3's real interface and Task4's packaged/hosted/final
review remain open. The schema-only eb9eb76 hosted checks are separate from this
new configuration runtime; no result is transferred as proof of unexecuted code.

The final Task1 native collect01-proof.tar.gz archive has SHA256
8623d942f3c7a19d9b61d7d071dc614f7649861a6de106d9ce57b6ccd73787a5.
All306 manifest file hashes were verified after transfer;12 owned fixture
credential canaries matched no collected file. Audit/manifest metadata add two
archive entries. Source/commands, successful and failed raw outputs, static logs,
complete warnings and repeated generation evidence remain private, outside Git.

## Hosted schema-foundation baseline eb9eb76

All five workflows passed for eb9eb76249007a317924fbdade415c344e6d253d:

| Gate | Actual result | Run |
| --- | --- | --- |
| API | 1615 passed,3 explicit skips,1 warning;1206.14s;0 failures/errors | [43557845184](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43557845184) |
| Browser | 214 passed in10.6m | [43557845194](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43557845194) |
| Containers | api-runtime and private-file-runtime both passed | [43557845188](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43557845188) |
| Source security | Passed | [43557845207](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43557845207) |
| Image security | Seven nonempty inventories;0 vulnerabilities | [43557845182](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43557845182) |

Complete logs/metadata, actual API JUnit and image reports are retained in
ci-eb9eb76. JUnit has1618 cases,0 failures/errors and3 explicit native ClamAV
foreground-console opt-in skips. The separate private-file runtime job passed.
The one Pydantic alias warning names body in the incumbent competing queue-access
test. This predates the new rule router; combined with the native observations
above it reinforces retaining the concurrent app-factory investigation, not
inventing a proved cause or suppressing output. No warning-free claim is made.
API/ClamAV/ingress/PostgreSQL/Redis/storage/web inventories respectively have
72/38/70/49/16/107/43 packages and zero vulnerabilities. No ignore added.

This exact hosted baseline covers the schema foundation only. Native Task1
configuration/staging has its own matching-source proof above; its subsequent
hosted runs and the entire worker/browser feature remain separate acceptance.
