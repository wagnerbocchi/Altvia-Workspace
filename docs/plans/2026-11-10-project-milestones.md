# Project milestones implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline; user delegated execution and direct main publication.

**Goal:** Operate real project milestones with scoped persistence and browser recovery.
**Architecture:** Extend project-owned SQL/ACL, share existing deadline semantics,
and keep project-bound redacted activity. No task synchronization or new service.
**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/PostgreSQL and Next.js/TypeScript.
**Spec:** docs/adr/0024-project-milestones.md and master specification.

Status: development complete on 2026-11-10, final application 011e0a5. Local
500 API/72 browser and all five hosted gates passed. Initial image findings
received exact vendor patches under ADR-0013 and same-DB zero-finding revalidation.
Source and Impeccable reviews completed; final target-VM qualification remains
deferred until remaining MVP development ends. See the Phase 2G evidence report.

## Global Constraints

- Contracts before code; no new dependency or ISA beyond x86-64-v1.
- Identity lock before authentication; scoped Project then milestone locks.
- Explicit customer ceiling; no platform/team bypass or membership grant.
- Preserve source work deadlines and exact untouched instant values.
- Local/CI validation now; no target-VM homologation until remaining MVP is complete.
- Use Impeccable for frontend; keep raw data/secrets out of Git.

## Review Focus

- Concurrent project/account revocation must precede authentication or deny writes.
- A milestone UUID under another project must never leak or mutate that resource.
- Lost POST responses must retain original intent despite parent/list errors.
- Editing a title must preserve an exact historical instant and reviewed version.
- Cancelled/done milestone history must survive rollback and explicit reopening.

### Task 1: Persisted milestone contracts and activity

**Files:** models.py; deadlines.py; work_schemas.py/work_items.py compatible
re-exports; milestone_api.py; main.py; activity.py; provision.py; migration11;
tests/test_project_milestones.py; generated contracts; affected docs.
**Interfaces:** Due/DateDue/InstantDue and set_due/due_output retain existing
behavior. MilestoneCreate{title,due?}, Patch{title?,due?,state?}, Output with own
version/ETag; minimal receipt{project_id,milestone_id}. Project activity carries
milestone ID and update field names only.

- [x] Write real PostgreSQL tests for lifecycle/deadlines/ACL/replay/no-op,
  invalid bodies/states, concurrent stale writes, event redaction/projection,
  migration preservation/refusal and least runtime privileges. Assert planned1,
  done2, reopen3, cancelled4; replay never resets state or increments versions.
- [x] Run `python .superpowers/phase1-tests/run.py --api apps/api/tests/test_project_milestones.py -q`.
  Expected missing-route/model failures; implement smallest compatible domain/API.
- [x] Run new tests and existing work deadline/project/migration checks, ruff,
  mypy, schema drift and contract generation. Expected all pass. Commit API slice.

### Task 2: Actual browser milestone workflow

**Files:** lib/projects.ts; project-workspace/milestones.tsx and screens/detail;
app/projects/[id]/milestones routes; browser_fixture.py; milestones.spec.ts.
**Interfaces:** Consume Task1 DTOs and existing session-owned write/query transport.

- [x] Write real browser lifecycle, immutable uncertain create, stale edit,
  exact-instant preservation, reader/hidden ACL and theme/keyboard/axe tests first.
  Run explicit milestones.spec.ts; expect missing screen before implementation.
- [x] Implement directory/detail forms, shared deadline DTOs, explicit transitions,
  retained original POST intent and reviewed versions. Preserve incumbent design.
- [x] Run check/build/contracts and relevant browser tests, inspect actual captures,
  finish Impeccable review/documentation. Commit intended UI/fixtures/tests.

### Task 3: Review, CI and development closure

**Files:** docs/phase-2g-milestone-evidence.md, roadmap/PRD/runbook and plan status.
**Interfaces:** Reviewed source, actual local/hosted evidence, deferred target gate.

- [x] Run full API/browser suites and required source/image/container CI. One fresh
  whole-increment source review; Important fixes receive RED/GREEN regressions.
- [x] Publish coherent checked commits to main without PR. Preserve exact commands,
  failures/corrections, scans and visual proof. No target SSH/homologation.
- [x] Record development complete separately from final VM qualification pending;
  keep external participants/remaining MVP scope explicit. Final report includes
  material rulings and any deferred minors.
