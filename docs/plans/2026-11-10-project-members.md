# Project member administration implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. User already authorized continued development and direct main publication.

**Goal:** Operate real scoped project membership from the browser.
**Architecture:** Reuse project_registry's access mutation and identity write lock.
Add typed versioned HTTP routes and a dedicated session-owned browser screen.
**Tech Stack:** Existing FastAPI/SQLAlchemy/PostgreSQL and Next.js/TypeScript.
**Spec:** docs/adr/0023-project-member-administration.md; master specification.

## Global Constraints

- Customer ceiling and scoped management on every write/replay; no team/admin bypass.
- No new dependency, migration or ISA requirement beyond x86-64-v1.
- No global account discovery, implicit grant, production deploy or real data import.
- Preserve existing CLI, no-op/session/event protocol and unrelated changes.
- Keep exact reviewed versions/original POST intents; use Impeccable for all UI.

## Review Focus

- Removing the only manager or oneself must remain explicit and recoverable by CLI.
- Removing direct access must not imply removal of inherited customer access.
- A committed POST receipt must never restore revoked access or become current state.
- Failed parent refresh must not destroy an uncertain POST intent or allow a new write.
- Concurrent account/customer revocation must serialize before fresh authentication.

### Task 1: Persisted member HTTP contract

**Files:** project_registry.py; project_api.py; tests/test_project_members.py;
generated OpenAPI/TypeScript contracts; docs/contracts/api.md.
**Interfaces:** POST {email,role_name} -> {project_id,user_id}; PATCH/DELETE ->204
with Project ETag. Shared change_project_access(db,user,project,role,actor_id,
correlation_id)->bool requires identity/project locks.

- [ ] Write real PostgreSQL tests for lifecycle, no-op/inactive, privacy/ACL,
  preconditions/replay, self-session revocation, split pair and concurrent writes.
  Lifecycle asserts new role/membership, Project version, target auth version,
  redacted audit/outbox and immutable minimal replay receipt.
- [ ] Run `python .superpowers/phase1-tests/run.py --api apps/api/tests/test_project_members.py -q`.
  Expected: missing-route failures (404/405), then implement and expect all pass.
- [ ] Extend the responsible domain helper and HTTP schemas/routes. Generate
  contracts using scripts/export_openapi.py and web generate:api convention.
- [ ] Run affected project tests, ruff, mypy and full API suite; commit intended files.

### Task 2: Protected member browser workflow

**Files:** lib/projects.ts; components/project-workspace/members.tsx; project detail;
app/projects/[projectId]/members/page.tsx; browser fixture; tests/project-members.spec.ts.
**Interfaces:** Consumes Task1 generated schemas, session-owned query/write helpers.

- [ ] Add real browser lifecycle/recovery/conflict/self-removal/ACL tests first;
  run the guarded browser runner with explicit project-members.spec.ts.
  Expected: missing member screen; implement then expect pass.
- [ ] Preserve incumbent Operate design and reviewed Project version. Add known-email
  add form, role editor, explicit removal/self-demotion confirmation, current-state
  recovery and immutable uncertain POST retry. No global lookup or email display.
- [ ] Check types/lint/build/contracts and complete browser suite; inspect actual
  desktop/mobile/light/dark captures and axe; perform Impeccable finishing workflow.
- [ ] Commit intended browser/fixture/test/docs files after checks pass.

### Task 3: Review, qualification and evidence

**Files:** Qualification fixture/smoke as needed; docs/phase-2f-member-evidence.md;
docs/roadmap.md and PRD delivery status.
**Interfaces:** Consumes reviewed application source and immutable archive/images.

- [ ] One fresh whole-increment source review; important fixes get RED/GREEN proof.
- [ ] Run required hosted API/browser/container/image/source gates and actual isolated
  baseline-VM membership/replay/session/ACL/recovery proof. Reuse unchanged evidence
  only where runtime inputs are identical. Record exact source/image IDs and results.
- [ ] Publish coherent checked commits directly to main; fast-forward clean remote
  development checkout. Preserve evidence and task volumes; stop task containers.
- [ ] Document exact remaining milestones/external participants; never claim Phase2
  complete or production ready. Final report includes material rulings and blockers.
