# Operational analytics implementation plan

> For agentic workers: use superpowers:executing-plans inline, task by task.
> Do not spawn implementers. Obtain one fresh whole-increment review at the end.

Goal: scoped real overview and principal workload that reconcile native tickets,
work, typed deadlines, continuous work and recorded SLA observations.

Architecture: read-only SQL over native managed resource predicates, full-set
suppression and one-statement aggregates/pages. Extend the existing capability
availability and authenticated Operate surface. No new persistence or worker.
Stack: installed FastAPI/Pydantic, SQLAlchemy/PostgreSQL and Next.js/TypeScript/
TanStack Query. Spec: ADR0043, master FR010 and ADR0006/0007/0040. The user's
delegated continuation supersedes routine approach/design approval pauses.
Base for the final whole-increment review: d040b04. SLA's exact final hosted gates
remain independently tracked; planning does not declare them complete.

## Global constraints

- x86-64-v1; no -march=native, mandatory AVX/AVX2/SSE4.2 or new native dependency.
- No Elasticsearch/OpenSearch/Solr/MongoDB/vector/local-model runtime.
- Customer ceiling and native management predicates precede all metadata/counts.
- Platform administration/team roster/assignment/link/external label is no grant.
- Preserve prior public APIs, receipts, native event envelopes and domain state.
- No stored counters, capacity/productivity claims or historical-state invention.
- Explicit aware reference/window/timezone; preserve DateDue/InstantDue precision.
- Impeccable and incumbent Twenty-inspired Operate for frontend work.
- Local commits/direct main pushes authorized; no PR, production or real import.
- Relevant local/CI checks continue; final target qualification follows the MVP.
- Preserve source workbook/private logs/secrets outside Git. Record policy questions.

## Review focus

1. Empty management contexts and coarse capability availability must not grant a
   customer, roster, project or queue label; test insufficient/mismatched bindings.
2. A completed linked task must not suppress an active ticket's active-unified
   count; suppression must use its own complete filtered active candidate sets.
3. An ongoing undated row is not an ordinary undated fault; all-missing and active
   ordinary no-due counts intentionally differ and must remain reconcilable.
4. DateDue equality is overdue at its exclusive next-day boundary, while
   InstantDue equality is on time; DST/offset/microsecond cases must stay exact.
5. Current recorded SLA corrections and old source dates cannot be presented as
   a historical-state snapshot at a caller's reference instant.

## Task 1: Native management reports and bounded discovery

Files: create apps/api/altvia/analytics_schemas.py, analytics_queries.py and
analytics_api.py; extend identity.py and main.py. Tests: test_analytics_api.py,
test_analytics_queries.py; generate docs/contracts/openapi.json and the existing
web api.generated.ts. No migration/provision/model change is required.

Interfaces: AnalyticsFilters(reference_at,due_through,timezone,priority?,client_id?,
team_id?,project_id?,responsible_id?,unassigned=false,created_from?,created_before?);
WorkloadFilters adds limit=50(1..100),cursor<=320. ScopeFilters(kind required,
limit=50,cursor<=320). Strict unknown/repeated/naive/numeric/NUL/range rejection.
AnalyticsOverview and workload/scope DTOs are pinned in contracts/api.md.

Queries: identity.analytics_available(db,user_id) -> bool supplies coarse
operation availability and is reused by identity.capabilities. managed_projects native
SQL, W/T bounded-column CTEs, all/active suppression, scalar/distribution aggregate
owner, latest-cycle recorded-SLA projection, principal aggregation and UUID cursor
owner. overview(db,actor_id,filters) -> AnalyticsOverview;
workload(db,actor_id,filters,cursor) -> AnalyticsWorkloadPage;
scopes(db,actor_id,filters,cursor) -> AnalyticsScopePage. No ORM row-per-record loop.
Current session auth remains a normal transaction; never enable a read-only DB
transaction incompatible with last_seen updates. JSON output is bounded and typed.

- [ ] RED a real native overview with managed/hidden rows before route/source.
  Expected: missing GET404 or missing query effect, not a fixture failure.
- [ ] Prove global admin/team metadata/agent/viewer non-grants, current ceiling/
  membership/queue manager conjunction, partial scope, archived reads and revoked
  session/cursor. Coarse capability alone must return no unauthorized data/labels.
- [ ] Prove zero/one/many N:N links, cross-owner responsibilities, hidden or
  filtered work, same UUID across domains, completed work versus active ticket,
  independent priority/project/creation filters and before-page suppression.
- [ ] Prove ordinary/ongoing/terminal/blocked/null responsibility; all scalar
  identities and fixed-key distributions. Never add personal row counts together
  as global effort or infer work participants as principal owners.
- [ ] Prove typed deadline equality, UTC offsets, DST DateDue boundaries,
  microseconds, explicit window endpoints, paired creation period and strict
  malformed/repeated/unknown query/cursor/timezone input.
- [ ] Prove configured/unconfigured/legacy latest cycles, retained breach and
  correction counts, hidden SLA records and current-history labels independent
  from reference_at. Do not execute or duplicate the SLA timing engine.
- [ ] Implement one-statement overview/workload snapshots, no N+1 enrichment,
  current actor-bound page cursors and visible context-only scope choices.
  Prove null bucket versus a real zero UUID, off-page eligible suppression and
  concurrent link/role changes without mixed snapshot output or stale grants.
- [ ] Native benchmark: bulk synthetic 6000 eligible and6000 hidden work rows,
  linked tickets and multiple principals, rolled back afterward. Retain EXPLAIN
  ANALYZE/BUFFERS, fixed query count and cold/warm times. Acceptance budget2s per
  representative statement on the isolated development host; this is not a
  production capacity promise. Inspect plans before adding any index/migration.
- [ ] Run affected reports/native identity/unified/ticket-work/SLA read regressions,
  Ruff/check/format/mypy and package build. Generate API/types twice, compare every
  old path/component exactly and run web check. Expected: real tests pass, stable
  new artifacts, every prior operation/schema unchanged. Commit persisted-data
  read capability and proof without claiming the interface complete.

## Task 2: Real Operate overview and principal table

Files: lib/analytics.ts; components/analytics/{screens,filters,overview,workload}.tsx
as required by actual ownership; apps/web/src/app/analytics/page.tsx;
workspace-navigation.tsx and scoped styles only if
needed. Tests: apps/web/tests/analytics.spec.ts and scripts/browser_analytics_fixture.py.
The app uses direct route directories, without a workspace route group. Do not
scaffold unused files.

Consume generated DTOs through the incumbent authenticated transport. One route
offers actual overview plus a paged active principal table. Explicit draft/applied
filters own server query keys. All choice lists are paged; retained ID/name survives
paging/loading/error. Dates/window are editable viewer-local instants with a
displayed timezone/offset; reject nonexistent local roundtrips. A view default is
not company policy. Show only server counts, native separate domain/state names,
ordinary no-due versus ongoing, recorded SLA observations and global deduplication.

- [ ] Start Impeccable context/local-extension workflow at actual frontend work;
  inspect incumbent visual truth and create the surface brief before UI edits.
- [ ] RED the missing real overview/control with HTTP/PG fixtures. Prove a
  manager and denied identity, selected resource scopes, empty managed scope,
  native persisted counts and actual drill/filter behavior.
- [ ] Implement the smallest complete read interface, real submit/refresh/paging,
  unapplied-filter distinction, per-domain reconciliation and permitted choices.
  No decorative chart, fake capacity, client-side full-page count or new asset.
- [ ] Prove browser timezone/local gap handling, applied reference/window, correct
  counts and selected off-page labels; page/filter changes restart the right cursor.
- [ ] Prove failure/retry, pending choice/report, identity replacement, current
  capability loss, delayed private callbacks, keyboard/focus and empty state.
  Parent errors own parent recovery; no ineffective nested retry or zero fallback.
- [ ] Run both themes at390/1440, axe/overflow and captures with real data/long
  names. Open actual renders, complete Impeccable review/fix/documentation using
  the existing system and relevant regression gates. Expected: passing complete
  module, web check/build/Sharp guard and review acceptance. Commit scoped UI.

## Task 3: Installed reconciliation and capability acceptance

Files: dedicated scripts/packaged_analytics_proof.py through container_smoke's
existing synthetic/recreation boundary; workflows artifact path as needed;
docs/operational-analytics-evidence.md, roadmap and completion ledger.

- [ ] Explicit synthetic manager, project/work/ticket/link data via native APIs.
  Retain fixed reference/window; assert actual full-set counts and principal
  columns before/after API/PG/Redis/worker recreation. No source workbook import.
- [ ] Prove current authority after revocation and no labels/counts for an
  unauthorized actor. Preserve all incumbent canaries and the SLA/SMTP proof;
  use the existing isolated helper command without changing daemon limits/checks.
- [ ] Run full packaged/static/native gates and freeze source/dependency/config/
  image identities. Inspect complete success/failure/cleanup logs. Reuse unchanged
  passing evidence; do not label a timeout, skipped gate or mocked result passed.
- [ ] Obtain one fresh whole-increment review from BASE through final source.
  Grade by user effect, fix Important/Critical in one actual RED/GREEN pass and
  run appropriate regressions. Record any Minor or unresolved policy limitation.
- [ ] Publish authorized main commits and observe all five exact-source hosted
  workflows, both Container jobs and seven nonempty image inventories.
- [ ] Accept only the development capability after required gates. Continue the
  guarded importer under its own selected contract; real mapping/apply policy,
  integrated hardening and final target qualification remain separate.
