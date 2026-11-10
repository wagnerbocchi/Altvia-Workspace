# Service Desk queue configuration implementation plan

> Execute inline with superpowers:executing-plans. The user delegated routine
> choices and direct main publication. Continue independent development while
> recording unresolved external inputs in the roadmap.

**Goal** Operate persisted scoped queues and categories through the real browser.
**Architecture** Extend the existing metadata registry, identity-before-auth
serialization, protected receipts, versioned writes and redacted activity worker.
**Tech stack** Existing FastAPI/Pydantic/SQLAlchemy/PostgreSQL and Next.js/TypeScript.
**Spec** docs/adr/0026-service-desk-queue-configuration.md and master specification.

## Global constraints

- Contracts precede product code. Preserve x86-64-v1 and existing dependencies.
- Configuration reads/writes require platform or explicit team metadata scope.
- Team roster, client roles and configuration never supply customer ticket grants.
- Identity lock before auth, then team, queue, category. Preserve immutable parents.
- Bounded names, unique archived names, protected POST, exact reviewed versions.
- Local/CI development now. Final target qualification follows remaining MVP.
- One fresh source review and Impeccable finish/documentation. No PR is requested.

## Review focus

- Lost POST responses retain original team/name/key through independent paging.
- A saved receipt is hidden after scope/session revocation, including global admin.
- Child changes conflict with an already reviewed queue version and cannot escape
  through a different parent URL or an inactive ancestor.
- Unicode names round-trip through unrelated edits with the same strip semantics.
- Queue metadata and events reveal no customer content or internal roster.

### Task 1 Persisted scoped queue and category contracts

**Files** queue_registry.py, queue_api.py, queue_schemas.py, models.py, main.py,
activity.py, provision.py, migration b46087000013, test_ticket_queues.py and
generated OpenAPI/TypeScript. Existing modules remain at their established paths.
**Interfaces** QueueCreate(team_id,name), QueuePatch(name?,active?), CategoryCreate(name),
CategoryPatch(name?,active?), QueueOutput with team metadata/can_manage,
CategoryOutput with immutable queue_id/version, ID creation receipts and pages.

- [ ] Write real SQL/API tests before code. Cover queue/category persisted
  lifecycle and no-op/stale/duplicate names, parent immutability, scope and roster
  negatives, independent creation authority, protected replay/revocation/archive,
  cross-parent and cursor binding, input bounds and missing protocol headers.
- [ ] Run `python .superpowers/phase1-tests/run.py --api apps/api/tests/test_ticket_queues.py -q`.
  Expect RED for absent routes/tables. Implement the selected metadata extension.
  Prove atomic event failure, concurrent writes, version overflow, safe migration
  preservation/refusal and API/worker least privilege using real PostgreSQL.
- [ ] Run focused and full API, ruff/format/mypy, Alembic drift and generated
  contract checks. Expect all passing. Commit tested backend and generated DTOs.

### Task 2 Queue workspace browser

**Files** lib/ticket-queues.ts, components/service-desk queue screens/forms,
app/service-desk/queues routes, workspace navigation, tests/ticket-queues.spec.ts,
browser_fixture.py and a surface brief.
**Interfaces** Consume Task 1 generated DTOs using existing session-owned transport.

- [ ] Write real browser lifecycle, scoped viewer and denied cases, uncertain
  create and stale edit recovery cases. Run new tests before implementation.
  Expect RED for missing queue route or controls.
- [ ] Implement independently paged team choice/list, explicit queue creation,
  queue/category lifecycle and scoped history. Preserve reviewed drafts and
  original POST intents through recovery. Read Impeccable craft floor immediately
  before editing UI and reuse incumbent visual context.
- [ ] Run web check/build, feature and full browser suites. Capture list/detail/
  category-edit/recovery at 1440/390 in light/dark using actual theme control,
  axe and overflow assertions. Inspect frames and complete finish/documentation.
  Expect all checks pass. Commit intended UI and fixtures.

### Task 3 Development acceptance and publication

**Files** packaged smoke assertions, queue runbook, Phase 3A evidence, roadmap,
PRD/ADR/plan status and task-owned private evidence.
**Interfaces** Exact reviewed source, local/hosted logs/scans and deferred VM gate.

- [ ] Extend existing packaged fixture to prove queue/category persistence after
  API/PostgreSQL recreation. One fresh whole-increment source review. Regrade and
  fix Important findings with real RED/GREEN and passing affected/full suites.
- [ ] Push coherent checked commits to main and follow all five hosted gates.
  Expect full API/browser/container/source/image checks pass without suppression.
- [ ] Preserve immutable evidence with hashes, exact CI runs and all severities.
  Record this bounded Phase 3A completion and remaining ticket/message/mail work.
  Publish documentation, verify clean actual remote main and preserve final ledger.
