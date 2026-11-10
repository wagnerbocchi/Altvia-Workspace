# Phase 2B projects and operational areas implementation plan

> Execute inline using superpowers:executing-plans and TDD, then one fresh full
> source review. Standing authorization covers direct main commits/pushes and
> routine decisions; user explicitly opted out of routine approval pauses.

**Goal:** Operate persisted internal/customer projects with real areas and members.
**Architecture:** Current monolith; explicit customer ceiling, scoped project roles,
protected writes and reused durable activity projection. No team metadata escalation.
**Tech stack:** Existing locked FastAPI/SQLAlchemy/PostgreSQL/Next.js stack.
**Spec:** ADR-0019, master FR-002/FR-012 and existing security contracts.

## Constraints and review focus

- No new dependencies/native ISA, forbidden engines, real import or production deploy.
- No customer metadata through configuration receipts, cursors or linked labels.
- Existing team grants remain metadata-only; internal projects require explicit scope.
- Scoped POST replay must recheck authority before returning a saved receipt.
- Test missing ceiling/member/binding halves, archived refs, explicit-null area,
  direct scope mutation, changed session/subject and new-event feed isolation.
- Stop after qualified registry/areas; tasks and boards remain subsequent work.

## Task 1: Persisted areas, projects and scoped access

Files: models.py, project_registry.py, project_api.py, activity.py/activity_api.py,
cli.py, policy.py, main.py, provision.py; migration b46087000007; tests.
Consume existing Client/ClientAccessGrant, identity lock, HTTP replay/version and
activity_page; produce typed area/project/member/history routes and trusted grants.

- [x] Write failing real DB/API tests for area lifecycle, explicit-manager creation,
  internal/customer isolation, safe members, scope halves and denied linked refs.
- [x] Observe absent route/schema RED, then implement schema/domain/HTTP/CLI.
- [x] Prove role/ceiling revoke, no-op/inactive changes, replay, version/concurrency,
  archive/reference checks, migration preservation/refusal and runtime privileges.
- [x] Extend strict worker payloads/projection and prove global-feed isolation.
- [x] Run focused/full API, Ruff/format/mypy/build and regenerate contracts; commit.

## Task 2: Real area/project browser flow

Files: web project transport, projects/operational-areas routes and components,
existing account navigation; browser tests. Reuse current controls/session-owned
queries/mutations; no new visual world or shared-cache bypass.

- [x] Apply existing Impeccable context and a narrow incumbent extension brief.
- [x] Observe real absent-screen browser RED; build real bounded selectors/list,
  explicit-manager form, scoped detail, area clear/change and safe member/history.
- [x] Prove self-delegation relogin, lifecycle/reload, uncertainty/conflict/recovery,
  session disposal, mobile/light/dark/axe and no overflow.
- [x] Run build/check/full browser; fresh source review, fixes and regression proof.
- [x] Finish Impeccable reviewer/documenter handoffs; commit reviewed slice.

## Task 3: Packaged qualification and publication

Files: scripts/container_smoke.py, scripts/container_browser.mjs, evidence/runbooks,
roadmap and relevant model/security/product docs. Reuse isolated target tooling.

- [x] Extend packaged persistence/ACL/projection/browser checks for projects/areas.
- [x] Pass all five hosted workflows and actual target smoke/native/cgroup checks.
- [x] Scan the same actual five images, compare tested IDs and inspect packaged PNGs.
- [x] Retain raw evidence outside Git; stop task containers/preserve volumes/close SSH.
- [x] Document exact proof/limits/rollback and publish coherent main commits, no PR.

## Completion evidence

Registry/area slice qualified on source 5faa866. All three tasks complete; exact
commands, failures/corrections, 358 API/42 browser results, five hosted gates,
actual target image IDs and retained proof: docs/phase-2b-project-evidence.md.
Task containers stopped, volumes preserved, SSH master closed. No tasks/boards,
real import or production deployment started. Final publication is documentation-only.
