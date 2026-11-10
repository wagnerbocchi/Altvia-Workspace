# Phase 2E contact/default-project evidence

Date: 2026-11-10. Scope ADR-0022. Implementation in progress; final source review,
complete hosted gates and actual changed-artifact VM qualification remain open.
No production deployment, email transport or real-data import.

Contracts preceded code in 3f0d1f1. Migration b46087000010 expands contacts and
nullable same-client defaults; a composite FK owns customer integrity. External
contact identities remain unverified and independent of internal accounts. All
nested resources require the parent customer ceiling plus client role. Real
writes reuse the identity lock before authentication, optimistic versions,
protected POST receipts and redacted transactional client audit/outbox.

## Executed local proof

- Missing-route API RED: 404 instead of201. After implementation, 29 tests passed
  before the missing worker allowlist caused the expected projection failure.
  After strict event handling, focused contacts/storage: 35 passed in78.82s.
- `uv run python .superpowers/phase1-tests/run.py --api apps/api/tests -q --tb=short`:
  459 passed in654.13s. Covers inherited tests, real PostgreSQL, preserved migration
  rollback refusal/drift, scope, concurrent uniqueness, versions/replay and events.
- Later runtime DELETE denial test failed before restricting the new table to
  SELECT/INSERT/UPDATE. `test_api_contact_runtime_privilege_and_worker_denial`
  plus complete test_runtime_provision.py passed21 tests in45.39s afterward.
  Worker has no contact-table read privilege. Final hosted full API proof remains
  required for this final grant refinement.
- Ruff check/format, strict mypy, source/wheel build, regenerated OpenAPI/TypeScript,
  web lint/types and production build passed. No runtime dependency was added.
- Browser initially failed on the absent contact link. The initial integrated
  run revealed delayed frame-scheduled field focus moving email input into name;
  mount-time layout focus fixed that behavior. All four contact browser tests
  then passed in13.9s, including persisted create/edit/archive/restore/default/
  clear, committed-create lost response with identical replay body/key,
  stale contact/default conflict recovery, viewer and hidden-account boundaries.
  Sixteen actual synthetic desktop/mobile/light/dark captures include axe and
  overflow checks. Impeccable final review/documentation remain pending.

Subsequent review/validation supersedes that pending visual status:

- Impeccable's owning-client context and default-selector/cancel focus findings
  were reproduced RED and fixed. Complete Windows browser suite: 58 passed in3.2m.
  The same reviewer inspected all sixteen recaptures plus four focused-editor
  captures, scored both fixes resolved and returned ship at that fix scope.
  Documenter updated PRODUCT.md; DESIGN.md/sidecar remain unchanged, including
  preexisting narrative.rules drift. Actual source hooks reported no deterministic
  issues; this is not a whole-design approval.
- One fresh source review found two P2 email-contract defects: Zod's generic email
  predicate rejected API-supported dot-atom addresses and blocked name-only edits;
  API casefold converted some unsupported Unicode mailboxes into different ASCII
  addresses. Both were reproduced before correction. Browser now validates the
  bounded ASCII dot-atom policy inline; API rejects raw non-ASCII before casefold.
  Rejected Unicode create/PATCH leaves contact/client versions and events intact.
- After those source fixes, contacts/storage39 passed in84.28s and affected browser8
  passed in19.5s, covering slash/exclamation mailboxes in both create and name-only
  edits. Ruff/format/mypy and web check/build passed. No second source review.
  Final-source complete hosted suites and actual-target qualification remain open.

## Infrastructure and remaining gates

An initial Windows test harness failed while decoding child CP1252 output as
UTF-8. The ignored local runner now sets child Python UTF-8 output; the repeated
test then demonstrated the actual missing behavior. A PowerShell unquoted
@contacts filter also selected no tests; only the repeated explicit-file failure
counts as RED. No production policy or test assertion was weakened.

The existing baseline VM/image evidence qualifies Phase2D only. This increment
still needs its own exact-archive packaged/native/cgroup/image-binding proof.
The current four passing browser tests are not a claim that the complete browser
suite or prior Windows axe issue is resolved. Phase2 and later product phases
remain open. Q-16 retains future verification/international-mailbox decisions;
registry work does not infer sender trust or permit email-only client selection.
