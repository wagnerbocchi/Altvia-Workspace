# External work participants implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task. User delegated decisions and direct main publication.

**Goal:** Persist and operate task-owned external involvement without identity grants.
**Architecture:** Extend existing work DTOs, link persistence, work version/ACL and
redacted events. Use task-owned labels; no client-contact lookup or new service.
**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/PostgreSQL and Next.js/TypeScript.
**Spec:** docs/adr/0025-external-work-participants.md and master specification.

## Global Constraints

- Contracts before code; x86-64-v1 mandatory, no new dependencies or target SSH.
- Identity lock before authentication; project graph then scoped work row lock.
- Manager-only metadata; involvement never grants account/content/customer access.
- Maximum 50 exact case-sensitive trimmed labels, 1..150 code points, no NUL/CR/LF.
- Preserve legacy create fingerprints and transition receipts; no data rewrite.
- Impeccable incumbent Operate extension; original intent and reviewed versions.
- Local/CI development now; consolidated VM qualification only after remaining MVP.

## Review Focus

- Legacy creation keys must replay after DTO expansion without a hash conflict.
- A manager's lost create response must retain its exact external labels and key.
- Assigned agents cannot mutate external labels even by submitting unchanged values.
- Reordering labels must not create a mutation; stale or overflowing writes must
  preserve all existing links, version and events.
- Clearing every link must not make a destructive downgrade discard new event data.

### Task 1: Persisted contracts and protected work writes

**Files:** models.py, work_schemas.py, work_api.py, work_items.py, activity.py,
provision.py; migration b46087000012; tests/test_external_work_participants.py;
generated OpenAPI/TypeScript; affected architecture/contracts.
**Interfaces:** WorkCreate/Patch external_participants list[str]; WorkOutput
external_participants defaults []; WorkExternalParticipant(work_item_id,unresolved_label).

- [ ] Write real SQL lifecycle/constraints/ACL/no-op/replay/stale/race/event tests.
  Assert trimmed sorted labels, one version advance, no external assignment effect.
  Add explicit old canonical request hash and missing-output-field receipt cases;
  populated/cleared-event downgrade refusal and least-privilege tests.
- [ ] Run `python .superpowers/phase1-tests/run.py --api apps/api/tests/test_external_work_participants.py -q`.
  Expected RED: unsupported field/missing table. Implement the smallest work extension
  and b46087000012, reusing current protocols; no contact identity association.
- [ ] Run affected tests plus full API, format/lint/mypy/schema drift and generated
  contracts. Expected all pass. Commit backend with tested durable behavior.

### Task 2: Existing task editor and detail

**Files:** work-items/form.tsx, detail.tsx; work-external.spec.ts; browser_fixture.py
only if incumbent work accounts/sessions do not already suffice; surface brief.
**Interfaces:** Consume Task1 DTOs using current WorkApi and session-owned transport.

- [ ] Write real browser create/edit/clear/reload, literal text, reader/agent,
  uncertain create and stale review tests. Capture create/detail/edit/recovery at
  1440/390px in light/dark using the real theme control, axe and no-overflow checks.
  Run new suite; expect missing controls before implementation.
- [ ] Extend WorkForm with manager-only one-label-per-line input and shared list
  semantics. Detail displays the scoped labels separately from internal contributors.
  Retain exact original POST and reviewed task version; do not resend on read retry.
- [ ] Run check/build/contracts and relevant/full browser suite; finish Impeccable
  review and incumbent-system documentation. Commit intended frontend/tests.

### Task 3: Review and development acceptance

**Files:** docs/phase-2h-external-participant-evidence.md, roadmap/PRD/runbook/ADR/plan.
**Interfaces:** Exact local/hosted source, immutable review evidence, deferred VM gate.

- [ ] One fresh whole-increment source review; Important fixes require RED/GREEN.
  Preserve failures, review fixes and actual source/image/container security outputs.
- [ ] Publish checked coherent commits to main without PR; monitor all five gates.
  Expected full API/browser/container/source/image gates pass without suppression.
- [ ] Preserve evidence, record development complete separately from target pending,
  and audit Phase 2 remaining traceability before any Service Desk implementation.
  Report rulings/costs and deferred minors. No target-server actions.
