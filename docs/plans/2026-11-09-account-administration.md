# Account administration implementation plan

> For agentic workers: use superpowers:executing-plans inline. User authorized
> continued implementation and direct main publication without approval pauses.

**Goal:** Operate real account security and existing scoped roles in the browser.
**Architecture:** Extend management services, share existing administrative HTTP
protocols, add account router and incumbent linked directory/detail UI.
**Tech stack:** Existing FastAPI/Pydantic/SQLAlchemy/PostgreSQL and Next/React stack.
**Spec:** ALTVIA_WORKSPACE_SPEC_CODEX.md and docs/adr/0016-account-administration.md.

## Global constraints

No production data/deployment; no new dependencies; x86-64-v1 mandatory.
No Elasticsearch/OpenSearch or -march=native. Preserve unrelated work and CLI.
Exact Origin/CSRF, fresh authorization, global lock before session authentication,
last-active-admin, transactional audit/outbox and secret exclusion are mandatory.

## Review focus

- Replaying a password receipt after later reset must not reset again or log out a new session.
- Changed-account/session callbacks must never update the later session's cache.
- Independent read retries must not discard a credential intent whose reply was lost.
- Grants to inactive accounts/teams and concurrent removal of final admin stay denied.
- Long Unicode credentials must honor byte limits without exposure in errors or state.

## Task 1: Persisted account administration HTTP

Files: management.py, shared admin_http.py, user_api.py, team_api.py, http.py,
main.py; tests/test_user_api.py; generated OpenAPI/TypeScript.
Consumes: existing management services and IdempotencyRecord.
Produces: ADR-0016 endpoints/DTOs and preserved GET/users summary.

- [ ] Write lifecycle/security/replay tests against real disposable PostgreSQL.
- [ ] Run tests first; expect missing routes/behavior failures.
- [ ] Extend service attribution and version bounds, share HTTP guards/paging/replay,
  implement strict account routes and bounded credential-safe request handling.
- [ ] Run focused then full API suite, Ruff/mypy and generated contract checks.
  Expected: all pass; no plaintext/fast credential verifier in persisted metadata.
- [ ] Commit coherent API/contracts slice on main.

## Task 2: Account directory/detail browser

Files: user-admin components, /admin/users routes, API transport types, account
navigation, browser fixture and account-admin.spec.ts; Impeccable surface brief.
Consumes: Task1 contract plus existing session-owned query client/layout/forms.
Produces: linked account lifecycle/security/role controls, no secret cache/state.

- [ ] Add browser lifecycle, lost acknowledgement, self-revocation, last-admin,
  denied-access, paging and secret-state checks; run and observe missing UI failure.
- [ ] Implement in incumbent Operate world with private intent refs and fenced
  callbacks; all writes share one busy/recovery boundary per account.
- [ ] Run full browser suite, build/types/lint, desktop/mobile light/dark/axe and
  screenshot inspection. Expected: real persisted behavior, existing tests green.
- [ ] Fresh source reviewer and Impeccable finish reviewer/documenter handoffs;
  fix material findings with reproducing tests. Commit implementation.

## Task 3: Packaged proof and publication

Files: relevant existing smoke tests and phase evidence/roadmap.
Consumes: reviewed Task1/2 source; produces exact runtime/hosted validation evidence.

- [ ] Build/scan changed actual images, run packaged Compose proof.
- [ ] Repeat isolated loopback target qualification with existing approved SSH
  multiplexing workflow; human types password locally if authentication needed.
- [ ] Update evidence with exact results and unresolved gates; direct push main,
  observe all hosted workflows to completion. Do not claim unexecuted VM proof.

No blocking product question for this slice. Capacity, corporate identity,
production provisioning/retention/mail policy remain existing roadmap questions.
