# Unified personal work implementation plan

Goal: implement ADR0040 and ADR0007's real personal queue while preserving the
existing task-only HTTP contract and advanced task view. This is a plan, not
implementation or a passing gate. Closure2026-11-14: all tasks below completed;
development accepted at1f7d5ab with exact evidence in docs/unified-work-evidence.md.
Current manual-link Task4 validation remains
separately tracked in docs/ticket-work-link-evidence.md.

Architecture: reuse native PostgreSQL visibility/FTS predicates and N:N links in
the modular monolith. SQL eligibility and anti-join precede ordering/keyset paging.
No new schema, worker, privilege, dependency or materialized counter. Contracts
precede code. Use executing-plans inline, one final independent whole-increment
review, small coherent local commits and authorized direct main publication.
Existing user continuity supersedes routine approval/execution-choice pauses;
record unresolved real-world policy without blocking independent safe work.

## Constraints and review focus

1. Full-set suppression: a linked eligible task beyond page one suppresses its
   ticket; a hidden or filtered-out task never does. Task1.
2. Distinct domains may use the same UUID and creation instant. The last cursor
   tie-breaker must retain both rows across limit1 pages. Task1.
3. Badge cap3 and has_more use visible links only; a hidden fourth link contributes
   neither metadata nor a positive more flag. Task1/Task2.
4. Switching domain/status filters cannot reuse a previous cursor or silently
   apply a task enum to a ticket. Legacy /my-work remains byte/schema compatible.
   Task1/Task2.
5. Revocation/session replacement hides cached origins and prevents old actor
   queries from settling into the new private workspace. Task2/Task3.

No link grants resource scope. Ticket and work state, ownership, due/SLA and
history remain independent. No arbitrary scripts, production deployment, real
import, retention deletion, search service or ISA requirement above x86-64-v1.
Do not use -march=native. Finish development before consolidated qualification.

## Task 1: Native read projection and strict API

Files: create apps/api/altvia/unified_work_schemas.py, unified_work.py and
unified_work_api.py; create apps/api/tests/test_unified_work.py; register the
router in apps/api/altvia/main.py. Modify existing predicate owners only if a
small extraction is needed to reuse exactly their behavior. Leave /my-work,
MyWorkPage, its native ordering/cursor and worker grants unchanged.
The scalar SQL projection reuses deadlines.due_value(precision, instant,
local_date, timezone); deadlines.due_output keeps its existing ORM signature and
delegates to that same pure value formatter. No deadline policy is duplicated.

Interfaces: UnifiedWorkFilters, LinkedTicketBadge, UnifiedWorkItem, UnifiedTicket,
UnifiedWorkPage from ADR0040; create_unified_work_router(engine: Engine,
settings: Settings) -> APIRouter; page(db: Session, actor_id: UUID,
filters: UnifiedWorkFilters, last: UnifiedCursor | None) -> UnifiedWorkPage.
UnifiedCursor is an immutable tuple/dataclass with priority_rank, created_at,
identifier and kind. Keep cursor encode/decode private to this feature, using
ADR0040's exact grammar and native IdentityError422 invalid_cursor behavior.

- [x] Write real PostgreSQL/API tests before production code. Arrange synthetic
  grants through existing native owners; fixture truncation requires a dedicated
  database named altvia_test and ALTVIA_ALLOW_TEST_DB=1. Never share it with another
  running suite, print credentials or use production.
- [x] Prove standalone/owner+participant/different-assignee/shared-task and N:N
  behavior. Assert the union of all returned page keys has exactly expected
  (kind,id) keys and no repeated work. Limit1 must not cause a represented ticket
  to reappear on later pages. A nonqualifying linked task must leave its ticket.
- [x] Prove same UUID/instant/domain tie, exact priority/creation/key order,
  status/kind/q/client/team filtering and cursor actor/filter/grammar rejection.
  Assert both current unauthorized and nonexistent scopes return empty metadata.
- [x] Prove badge3/more using4 visible links, then hide the fourth and assert
  false/no hidden ID. Revoke queue/client/project scope between pages, require
  old-session401 where the native writer invalidates it, then authenticate the
  same actor and check current independent eligibility. Include platform/team
  non-grants and unassigned/history-only participation non-eligibility.
- [x] Implement one responsible query owner. Reuse complete eligible W in the
  NOT EXISTS anti-join; no result-page Python deduplication. Use bounded windowed
  enrichment over returned work IDs with both current visibility predicates.
  Fetch at mostlimit+1 rows and at most4 visible badge candidates per returned
  work. Do not cause ORM N+1. Reuse existing task due formatting semantics.
  Select candidates and bounded badges in one PostgreSQL statement snapshot;
  prove a concurrent native unlink cannot lose the represented ticket. Keep
  the incumbent authentication transaction isolation and session lock protocol.
- [x] Run uv run pytest apps/api/tests/test_unified_work.py and nearest affected
  discovery/ticket-work modules against the dedicated actual database. Run
  uv run ruff check apps/api, uv run ruff format --check apps/api, uv run mypy,
  and existing migration-head/contract gates. Expected: all pass, explicit skip
  limits retained. Inspect query counts/plans on representative synthetic data;
  introduce no index until its measured need and reversible contract are recorded.
- [x] Export OpenAPI and generated types using uv run python scripts/export_openapi.py
  and pnpm --filter @altvia/web generate:api. Assert all legacy /my-work examples,
  response schema and unfiltered/filtered cursor behavior remain valid. Commit
  intended API/tests/generated contracts as feat: unify authorized personal work.

## Task 2: Actual personal queue in the existing interface

Files: add apps/web/src/lib/unified-work.ts and
apps/web/src/components/work-items/unified.tsx; extend
apps/web/src/components/work-items/discovery.tsx only at the PersonalWork owner;
add apps/web/tests/unified-work.spec.ts and extend scripts/browser_fixture.py.
Update incumbent discovery/packaged tests only to explicitly select their existing
task view, preserving every functional assertion. No redesign/token change.

Interfaces: createUnifiedWorkApi(csrf: string, onAuthError: (error: unknown) => void)
returns list(cursor, signal, filters): Promise<UnifiedWorkPage> using generated
types and existing authenticated transport. UnifiedPersonalWork consumes that
transport and owns its filter/paging state inside the current private session.

- [x] Run Impeccable context workflow once for this surface; read current brief,
  DESIGN.md and craft floor before source. Preserve the Twenty-inspired Operate
  world. Select the real labeled Fila unificada/Somente tarefas button group.
- [x] First add actual browser tests for default consolidation, origin badges,
  hidden linked resources, all-page suppression, independent statuses, changing
  filters/reset, read failure/retry and old-session disposal. Observe RED on the
  missing behavior before implementing the real interface.
- [x] Add generated-type transport and current API queries, actual detail links,
  bounded visible origins and explicit domain/deadline labels. Keep existing
  TaskFilters/results in their separate keyed subtree. No client-side join,
  synthetic counts, privileged directory lookup or stale cached rows after denial.
- [x] Run the new and affected discovery/browser modules through the repository's
  real HTTPS/API/PG launcher. Check keyboard,390/1440 both themes, overflow and
  axe in a shared render batch; inspect actual captures. Run pnpm web:check,
  pnpm web:build and installed native-dependency guards. Independent source/visual
  findings must be resolved. Commit as feat(web): show unified personal work.

## Task 3: Persistence, acceptance and next boundary

Files: extend scripts/packaged_ticket_work_proof.py at its existing legitimate
actor boundaries without changing incumbent version/count assertions; add
docs/unified-work-evidence.md; update ADR status, roadmap and continuous ledger.

- [x] Read actual unified responses before and after the existing API/PG
  recreation for the Task4 dedicated pair. Before native queue revocation, assert
  one work row with its represented ticket; after old401 and same-actor login,
  require readable work and no hidden ticket origin/standalone row. Preserve the
  native pair/history receipts and existing exact singleton canaries. Make no new
  writes solely to fit a result count.
- [x] Run relevant packaged proof/static gates. Preserve exact source, commands,
  outcomes, failures, raw hashes and narrow evidence limits. Source review before
  publication, then observe all five exact-source hosted/security workflows,
  including both Container jobs. Reuse unchanged valid evidence appropriately;
  no unexecuted gate is labeled passed.
- [x] Obtain one final independent whole-increment review after exact gates.
  Record all findings and corrected proofs. Commit source and evidence in small
  batches, direct push main under existing user authorization; no PR.
- [x] Mark this read-only development increment accepted only after its required
  evidence. Keep actual compatible-image rollback/encrypted restore and final
  integrated x86-64-v1 qualification pending. The next separate contract is
  structured durable automation; SLA, analytics, import and integrated hardening
  remain open. Never infer whole-MVP/production completion from this projection.

## Self-review

ADR0007 coverage maps SQL full-set eligibility/suppression and page ties toTask1;
real filter/origin/recovery/session behavior toTask2; persistence/current ACL and
exact acceptance toTask3. Both legacy task capabilities and domain independence
are explicit. Query/DTO/cursor names agree across tasks. Each review focus has
native/browser/packaged proof at its owning step. No migration, broad worker role,
notification subsystem or generic reporting framework is presumed.
