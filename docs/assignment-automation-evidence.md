# Assignment automation development evidence

ADR0041's contract and plan are selected after independent builder check. The
automation feature is NOT accepted: configuration/staging, worker effects,
interface and packaged/hosted/final review have separate remaining gates.
This record initially covers the schema foundation only. No production rule,
external policy, real import or final target qualification is implied.

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

Static commands: uv run ruff check apps/api; uv run ruff format --check apps/api;
uv run mypy. Native pytest commands select test_automation_migration.py,
test_ticket_work_storage.py, test_runtime_provision.py and test_activity_migration.py.
Local installed static tools also passed. No new dependency/service/ISA flag or
production/SSH/security configuration change was made.

The matching frozen source map is schema-green03-source.json with the original
schema-green02 tar bytes. Later configuration/staging source is outside this
schema-only proof and requires its own actual execution. This sub-batch does not
claim complete API/browser/worker/hosted acceptance. Native test fixtures are
synthetic; Q-23 real rules/title/status/priority remain unconfigured.
