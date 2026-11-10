# Work Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Operate authorized tasks through filters, PostgreSQL search, paged Kanban and a deduplicated personal task queue.

**Architecture:** Extend work_api and project_registry.visible_projects. One task
query owner applies typed filters and FTS. Existing detail owns every mutation;
the board links to it. Session-owned browser state reuses the incumbent system.

**Tech Stack:** FastAPI/Pydantic, SQLAlchemy/PostgreSQL, Next.js/TypeScript,
TanStack Query, existing test harnesses. No new dependency.

**Spec:** docs/adr/0021-work-discovery-and-personal-queue.md;
ALTVIA_WORKSPACE_SPEC_CODEX.md FR-004; ADR-0006/0007/0019/0020.

## Global Constraints

- Mandatory baseline x86-64-v1; no Elasticsearch/OpenSearch or -march=native.
- Current resource authority on every result and linked name; assignment is no grant.
- Protected state mutations remain owned by ADR-0020; no import or deployment.
- Use Impeccable for all frontend work and preserve incumbent DESIGN.md.
- Commit coherent checked batches; direct main push is authorized.
- No raw workbook, credentials, production logs or customer data in Git.

## Review Focus

- An actor who loses project access must lose personal/search matches on the next read.
- Owner and participant overlap must not duplicate or skip rows across pages.
- A filter/search change must not reuse old cursors or display old matching rows.
- Null/date-only/instant deadlines must retain existing precision at filter boundaries.
- Board failures in one column must not imply other columns or total counts are complete.

## Task 1: Authorized query and native search

Files: new altvia/work_queries.py, tests/test_work_discovery.py and migration9;
modify work_api.py, work_schemas.py, models.py and generated OpenAPI/types.
Consumes visible_projects(user_id), work.access/output and existing UUID cursors.
Produces WorkFilters, MyWorkFilters and MyWorkPage; GET /my-work and expanded
GET /work-items per ADR-0021. No change to write DTOs or state behavior.

- [x] Write real PostgreSQL/API tests for exact ADR filters/search, scoped cursor
  reuse, personal owner/participant overlap and revoked/partial access.
- [x] Run `uv run python .superpowers/phase1-tests/run.py --api apps/api/tests/test_work_discovery.py -q --tb=short`; expect missing behavior failures.
- [x] Implement typed query/filter ownership, authorized personal SQL join and
  index-only migration, preserving unfiltered list compatibility.
- [x] Extend tests for no per-result query growth, search index/edit freshness,
  migration downgrade preserving data, strict/repeated input and deadline bounds.
- [x] Run the focused command; expect all passing. Run `uv run ruff check apps/api`,
  `uv run ruff format --check apps/api`, `uv run mypy`; expect exit0.
- [x] Regenerate OpenAPI/types, run web check and full API suite, then commit.

## Task 2: Real list/board and personal queue

Files: work-items directory/screens and new discovery components; lib/work-items.ts,
app/my-work/page.tsx, account navigation, globals.css and browser tests.
Consumes Task1 DTOs/API and existing WorkDetail mutations. Produces filterable
project list/board and task-only My Work under the existing identity boundary.

- [x] Run Impeccable context workflow; record incumbent Operate extension decisions.
- [x] Add browser tests for real filter/search persistence, independent column
  paging/retry, My Work deduplication/linking and keyboard/mobile/session state.
- [x] Run focused browser tests; expect missing control/route failures.
- [x] Read craft-floor, implement accessible form, page keys, independent columns,
  task summary links and route using Task1 API; preserve creation intent recovery.
- [x] Run browser tests, web check/build and inspect actual light/dark/mobile
  captures. Expect passing behavior, axe and no overflow.
- [x] Apply prescribed Impeccable finishing review/documentation; commit.

## Task 3: Review and exact-artifact qualification

Files: packaged proof/runbook/evidence and roadmap; test helpers where needed.
Consumes Task1/2 exact application revision. Produces bounded evidence and status.

- [x] Request one fresh source review of the complete increment, including Review
  Focus above. Fix important findings with RED/GREEN proof and relevant suites.
- [x] Run full API/browser and required hosted source/image/container gates.
- [ ] Extend packaged proof to task search, scope, columns/personal query and
  persistence. Build/test the exact source in a new private target directory,
  loopback-only ingress, existing authenticated task SSH multiplexing.
- [ ] Execute native FTS/GIN and representative query/resource checks on actual
  x86-64-v1 images; retain exact tested image/scan identity evidence.
- [x] Update evidence/runbook/roadmap without overclaiming remaining Phase2;
  commit/push authorized main. Record any external authentication gate precisely.

## Current execution evidence

Contracts 215eb31; backend 4d56e97; reviewed browser 8c1be1d; packaged proof
9d53841; final navigation acceptance correction 1c20f48. All five hosted gates
passed on 1c20f48 with 424 API/52 browser tests and zero reported vulnerabilities
in all five hosted images. Local affected browser10/10 passed; the Windows full
suite's internal axe error remains recorded rather than hidden. Full Linux proof
and exact commands/results are in docs/phase-2d-discovery-evidence.md.

Task3 remains incomplete for actual changed-artifact target-VM execution, native
resource/image identity proof and authentication. The pinned archive is prepared;
no upload or production deployment occurred. Preserve the task ledger/evidence
for continuation rather than marking the increment qualified.
