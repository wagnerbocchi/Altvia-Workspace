# Operational analytics development evidence

ADR0043 and contracts6298a47 preceded runtime implementation. This checkpoint
covers the read API and generated contracts. The analytics browser interface,
installed integrated proof, whole-increment review, exact-source hosted gates
and final target qualification are not accepted by this checkpoint.

## Native reporting boundary

The three reads use current native project-management and ticket-management
predicates, with the customer ceiling retained. The coarse analytics.read
capability never substitutes for row authority. Queries reuse bounded native
columns and PostgreSQL aggregates; no new table, runtime grant, dependency,
counter worker or domain write was introduced.

Overview and workload use one statement snapshot for eligible datasets,
full-set representation, active representation, distributions, recorded latest-
cycle SLA observations, principal labels and bounded workload pages. Principal
columns keep task and ticket responsibility separate. Scope choices include
managed empty projects and actual referenced identities, not an account roster.

Typed deadline boundaries, ordinary versus ongoing work, terminal states,
null principals versus a real zero UUID, independent domain filters, strict
actor/filter-bound cursors and current scope are covered by native PostgreSQL
fixtures. Concurrent ownership/unlink changes occur after the actual report
statement; the original response remains internally coherent and the next read
reflects the change. Existing altvia_app credentials execute all three reads
without any additional provision privilege.

## Executed evidence

Private immutable source maps, complete command results and evidence are under
.superpowers/sdd/2026-11-14-operational-analytics, outside Git. Development uses
the authorized isolated host; these runs do not qualify the final target stack.

- report-red01: initial real overview GET404, after valid native setup;7.56s.
- report-green01:1 passed8.03s, native Ruff/format/mypy89 passed.
- boundaries-red01:29 passed/2 expected absent collection-route GET404;103.24s.
- scopes-green01:30 passed/1 workload503;102.03s. A SQLAlchemy column named items
  collided with the column collection method. Explicit key lookup corrected it.
- scopes-green02:41 passed/1 test-observer failure;144.70s. The observer used the
  fixture engine, while HTTP owns another engine. Observing Engine fixed the
  test; snapshot-green01 passed1 in8.22s with native static gates.
- actor-green01:1 passed/1 fixture failure;12.94s. The synthetic customer grant
  lacked required created_at. Fixture metadata was completed; no product change.
- extra-green01:4 passed21.35s, Ruff passed, mypy failed2. Concrete cursor typing
  exposed bare Python tuple_ arguments. Typed SQL literal binding fixed the
  type errors while preserving keyset behavior.
- bulk-green01:2 passed18.44s; native Ruff/format/mypy89 passed.
- final-api-green01:49 passed185.98s,0 skips; native Ruff/format/mypy89 passed.
  Inputs stayed frozen; task PostgreSQL stopped and its empty network removed.
  This includes the corrected fixtures and final typed cursor binding.

- states-green01: the additional nonzero-state/priority/workload reconciliation
  case passed8.00s; native Ruff/format/mypy89 passed. It is separate from the49.
- backend-green01:156 affected cases passed541.67s with native Ruff/format/mypy89.
  This earlier source includes44 analytics cases plus112 native identity,
  unified-work, ticket/work and SLA-read regressions. Its analytics cases overlap
  the final49; do not add the cohorts as distinct tests. The later final49 and
  additional state case prove the final runtime source and all50 analytics cases.

## Volume and privilege proof

Rollback-only fixtures contain12000 additional work rows and2400 additional
tickets. Half belong to an unmanaged project/queue. Two principal buckets and
1200 links reconcile to6001 eligible work items,1201 tickets,1200 represented
tickets and6002 unified records, even with workload limit1. Each invocation
executes exactly one reporting statement. No synthetic bulk row is committed.

The final-api-green01 JUnit retains full EXPLAIN ANALYZE/BUFFERS JSON. Actual
first/warm/EXPLAIN execution times in milliseconds:

| Report | First | Warm | EXPLAIN |
| --- | --- | --- | --- |
| Overview |340.882|288.929|396.119|
| Workload |418.971|294.503|397.822|

Every measurement is below the selected2000ms isolated-development budget. First
means first invocation in that process, not a flushed OS/PostgreSQL cache. These
measurements make no production capacity promise. The observed plans required
no new index or migration. A separate native test proved all three queries and
timezone validation under the existing restricted application database role.

## Contracts and local gates

OpenAPI export repeated identically, preserving all87 prior paths and172 prior
schemas exactly. Three new analytics paths and their DTOs were added. Generated
TypeScript repeated identically. pnpm web:check, uv build, whole-API Ruff check/
format223 and mypy89 passed. Earlier bare system Python lacked Ruff/mypy; the
existing project .venv supplied them without installing another toolchain.

## Remaining acceptance

The read API checkpoint is verified; complete the real Impeccable Operate
interface, packaged recreation/revocation
proof, fresh whole-increment review and all five exact-source hosted workflows.
Only then accept analytics development. Continue the guarded importer and
integrated hardening before final consolidated x86-64-v1 qualification. Actual
mapping/SLA/provider policy, production rollout and real import remain separate.
