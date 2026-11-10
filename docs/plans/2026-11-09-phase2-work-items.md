# Phase 2C work items implementation plan

> Execute inline with superpowers:executing-plans and TDD, then fresh whole-source
> review. User opted out of routine approval pauses and authorized direct main.

**Goal:** Operate real tasks/subtasks, owners/participants, dates and internal history.
**Architecture:** Existing monolith/project ACL/protected HTTP/activity projection;
DB hierarchy enforcement and identity-then-project write locks. No new service.
**Tech Stack:** Locked FastAPI/SQLAlchemy/PostgreSQL/Next.js; native PG timezone data.
**Spec:** ADR-0020, ADR-0006, ADR-0019 and master FR-003/FR-012.

## Global constraints and review focus

- Preserve all identity/client/project data and native versions; x86-64-v1 required.
- No team/admin content bypass, assignment grants, ticket state or production import.
- Recheck authority before saved POST receipt; mutable version/candidate state must
  not prevent safe replay of an already committed original intent.
- Test two concurrent opposing parent changes and composite-FK project crossing.
- Test stale assigned identity, ceiling revocation and both missing scope halves.
- Test date boundaries/DST/skipped dates and aware instants; missing remains null.
- Test uncertain transitions/comments preserve keys and do not duplicate history.
- Stop after qualified task core; boards/search/My Work remain the next increment.

## Task 1: Persisted work domain and typed API

Files: new work_items.py/work_api.py/work_schemas.py, models.py, policy.py,
activity.py, main.py, provision.py; migration b46087000008; test_work_items.py,
test_work_storage.py, test_policy.py and migration assertions as needed.
Consumes scoped_project/visible_projects, authenticate_request(write=True),
_operation/_remember/_expected_version, record_event and activity_page.
Produces create_work_router(engine,settings), typed WorkCreate/Patch/Transition/
Output/Page, scoped task reads and contributor selection. No public task service
abstraction beyond the actual shared route/domain ownership seam.

- [x] Write real API tests test_work_lifecycle_and_replay,
  test_subtask_and_assignment_boundaries, test_agent_and_viewer_authority;
  assert201/ETag, original POST replay200, stale409, denied403/404 and persisted state.
- [x] Run harness focused tests; observe absent route/schema RED before code.
- [x] Add migration/models/domain/API and correct generic work policy to match
  ADR-0019, with no metadata team grants. Add candidate/deadline/status validation.
- [x] Add storage tests for composite FK/self/cycle/concurrent reparent, immutable
  history, exact date precision and populated rollback refusal; observe meaningful
  failures before each missing invariant, then implement the responsible layer.
- [x] Extend strict worker events and exact family tests; prove replay once and
  feed isolation. Prove same-state no-op and one version winner under races.
- [x] Run focused/full API, migration drift/preservation, Ruff/format/mypy/build;
  generate OpenAPI and TS contracts. Expected all pass; commit coherent backend.

Run: uv run python .superpowers/phase1-tests/run.py --api apps/api/tests -q
Expected: all API tests pass on disposable real PostgreSQL/Redis.

## Task 2: Real project-task browser flow

Files: web work transport/components/routes, project detail navigation,
tests/work-items.spec.ts; PRODUCT factual update only.
Consumes Task1 generated schemas, project authority, protected writes and private
session cache. Produces project task directory and /work-items/{id} detail.

- [x] Load Impeccable context once for new task surface, inspect incumbent truth
  and retain a narrow Operate brief. Read craft-floor immediately before UI edits.
- [x] Write real browser lifecycle/subtask/agent/reader tests, observe absent-route
  RED, implement task creation/list/detail/assignment/parent/due/state/comment/history.
- [x] Prove pending/error/empty/success, uncertainty and version conflicts without
  auto-resend or lost intent on pagination; session changes dispose private state.
- [x] Inspect desktop/mobile light/dark captures, keyboard/axe and no overflow.
  Run web check/build/full browser; fresh source review and material fixes with RED/GREEN.
- [x] Complete Impeccable review/documentation workflow, preserve incumbent identity;
  commit reviewed frontend. Expected all required checks pass.

Run: uv run python .superpowers/phase1-tests/run.py
Expected: complete browser suite passes with real HTTPS/API/PostgreSQL.

## Task 3: Packaged task qualification and evidence

Files: packaged smoke/browser/fixtures; evidence/runbook/roadmap/contract/security
and data-model docs. Consumes Task1/2 exact source/images and existing test helpers.

- [x] Extend packaged persistence/task ACL/subtask/event/browser proof; run script
  lint/syntax and all five hosted gates after direct main publication.
- [x] Reuse authenticated SSH mux if present; otherwise request terminal login
  asynchronously while independent checks continue. Qualify exact images on target,
  compare native/cgroup/scanned IDs and inspect actual packaged captures.
- [x] Preserve all original raw evidence outside Git. Stop task containers, retain
  volumes and close task master. No server/SSH policy or production change.
- [x] Record exact results/failures/images/rollback/limits; docs checks and coherent
  publication. Do not claim closed task acceptance while any required gate fails.

## Executed completion

Qualified application source d5ae972 on 2026-11-10: 403 API/48 browser tests,
all five hosted gates and actual baseline-VM packaged/native/cgroup/same-image
security proof passed. Five source findings addressed; Impeccable scored its zone
fix resolved/disposition ship and documented the retained system. Task containers
stopped, database volume retained, task SSH master and local keeper closed.
Exact source/archive/images, observed failures/corrections, evidence hashes and
limits: docs/phase-2c-work-evidence.md. Phase 2 remains open; stop at this slice.
