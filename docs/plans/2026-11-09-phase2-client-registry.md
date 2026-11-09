# Phase 2A client registry implementation plan

> Use superpowers:executing-plans inline with TDD and one final fresh source review.
> User authorized direct main commits/pushes and routine decisions without pauses.

**Goal:** Operate a persisted client registry with explicit customer authorization.
**Architecture:** Existing modular monolith, separate client ceilings and scoped
roles, transactional audit/outbox and shared durable activity transport.
**Tech stack:** Current locked FastAPI/SQLAlchemy/PostgreSQL/Next.js stack.
**Spec:** ADR-0018 and master FR-002/FR-012; security-requirements.md.

## Constraints and review focus

- No new dependencies/native ISA, external engine, real import or production deploy.
- Customer ceilings apply to platform administrators and every cursor/replay/feed.
- User opted out of routine design approval pauses; record decisions and unknowns.
- Preserve existing identity/session/admin protocol and unrelated changes.
- Check initial-manager selection, revocation races, cross-client cursor reuse,
  new event visibility and populated migration rollback before publication.

## Task 1: Registry, explicit grants and scoped HTTP/history

Files: models.py, policy.py, client_registry.py, client_api.py, cli.py,
activity.py/activity_api.py, provision.py, main.py; migration b46087000006;
tests/test_client_registry.py and affected migration/role/worker/contract tests.
Consumes current authentication, identity write lock and admin_http protocols.
Produces Client/ClientAccessGrant, management access changes, typed client routes
and strict client event projection without global identity-feed leakage.

- [ ] Write focused real PostgreSQL API/service tests; observe missing routes RED.
- [ ] Implement schema, exclusive role scope, filtered reads and metadata writes.
- [ ] Implement explicit initial delegation, restricted CLI and session invalidation.
- [ ] Extend strict activity validation and scoped feed; prove identity isolation.
- [ ] Prove ACL/ceiling halves, repeat/revoke/race/version/migration preservation.
- [ ] Run focused tests, full API, Ruff/format/mypy/build and generated contracts.
- [ ] Commit the independently tested backend slice.

## Task 2: Real browser client workflow

Files: client directory/detail routes and components; shared account navigation,
generated API types and a real client browser test. Reuse session-owned private
caches, auth transport, form controls, version conflict and safe read recovery.
Consumes Task 1 routes; produces usable client CRUD/archive and scoped history.

- [ ] Apply Impeccable context/rules; persist a focused incumbent surface brief.
- [ ] Write a failing browser test and observe RED before interface implementation.
- [ ] Implement bounded directory, explicit-manager creation and scoped detail.
- [ ] Prove login after self-grant, independent errors, stale writes and no retry.
- [ ] Run browser suite/build/check/contracts/audit and theme/mobile/axe captures.
- [ ] Complete fresh source review and Impeccable finish/documentation handoffs.
- [ ] Commit reviewed changes and evidence.

## Task 3: Packaged validation and publication

Files: packaged browser/smoke checks, runbooks, evidence and roadmap.
Consumes actual client workflow; produces reproducible release-slice proof.

- [ ] Extend packaged test to client write, scoped denial, projection and restart.
- [ ] Run appropriate container/source/image security and all five hosted gates.
- [ ] Request target SSH authentication asynchronously if required; never store
  a password or bypass a closed master. Continue independent safe work meanwhile.
- [ ] Record exact executed evidence and any remaining target gate; never claim
  Phase 2 or native qualification from mocks or unexecuted tests.
- [ ] Push authorized coherent commits directly to main, without PR.

Stop at the completed client slice. Projects/areas/tasks remain later Phase 2 work.
