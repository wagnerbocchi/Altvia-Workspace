# Client Contacts and Default Project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Configure external contacts and a same-client default project with real persistence and scoped browser workflows.

**Architecture:** Extend client registry ownership and its protected HTTP/event
protocol. Contacts remain separate from accounts. A composite PostgreSQL FK owns
same-client default integrity; current authorization and active-state checks own
assignment eligibility. No ticket/email behavior or new dependency.

**Tech Stack:** Existing FastAPI/Pydantic, SQLAlchemy/PostgreSQL, Next.js/TypeScript,
TanStack Query and existing integration/browser/container harnesses.

**Spec:** docs/adr/0022-client-contacts-and-default-project.md; master FR-002;
ADR-0018/0019; docs/contracts/api.md and architecture/data-model.md.

## Global Constraints

- x86-64-v1 mandatory; no new search engine, native dependency or -march=native.
- Customer ceiling AND client role on every parent/child; assignment grants nothing.
- Reuse identity lock before authentication, protected POST and reviewed versions.
- No production deployment, real import, email send or account/contact identity merge.
- Use Impeccable for all frontend work; preserve incumbent DESIGN.md.
- Main commits/pushes authorized; no PR. Preserve unrelated changes and secrets.

## Review Focus

- Same email in two clients or an internal account never links identities or access.
- Saved POST receipts cannot bypass fresh parent authorization or reveal edited email.
- A stale contact/default form cannot overwrite another successful write.
- Project archival retains configuration but never guarantees future ticket eligibility.
- Contact events expose IDs/field names only and never enter identity/project activity.

## Task 1: Persisted scoped contact/default API

Files: models.py, new migration b46087000010_client_contacts.py,
new client_contacts.py and contact_api.py; client_api.py, activity.py, main.py,
provision.py; new tests/test_client_contacts.py and test_contact_storage.py;
generated OpenAPI/TypeScript and client-registry runbook.
Consumes scoped_client(db,user_id,client_id,write=False), visible_projects(user_id),
authenticate_request and _operation/_remember. Produces ContactCreate/Patch/Output/
Page/Creation and the four ADR routes, default_project_id on ClientPatch/Output.

- [x] Write PostgreSQL/API tests for scoped CRUD, email normalization/uniqueness,
  receipts/revocation, no implicit User/grant, parent/contact versions and defaults.
- [x] Run `uv run python .superpowers/phase1-tests/run.py --api apps/api/tests/test_client_contacts.py -q --tb=short`; expect missing-route/field failures.
- [x] Implement exact ADR data, schema, domain validation, routes and client events;
  reuse existing locks, transactions, pagination and HTTP helpers.
- [x] Add direct SQL composite-FK/uniqueness, migration preserve/refuse/roundtrip,
  duplicate races, redacted projection/dedup/feed isolation and runtime privilege tests.
- [x] Run focused tests, Ruff/format/mypy, Alembic drift and generated contracts;
  expect exit0. Run full API suite and web check; then commit.

## Task 2: Scoped browser configuration

Files: client-workspace components, new contact screens/routes, lib/clients.ts,
clients browser tests and PRODUCT context. Consumes Task1 DTOs/receipts and
existing scoped project list. Produces client contacts list/create/detail edits
and independent versioned default-project configuration.

- [ ] Apply Impeccable context/craft workflow; record incumbent extension.
- [ ] Add real browser regressions for CRUD/default persistence, paging, uncertain
  POST replay, stale versions, hidden/readonly scope and session cache ownership.
- [ ] Run affected browser tests; expect missing controls/routes.
- [ ] Implement accessible labeled forms, paged authorized choices, reviewed
  intents and explicit retry/reload under existing identity boundary.
- [ ] Run affected browser and web check/build; inspect theme/mobile/keyboard/axe
  captures. Apply prescribed finishing/documentation and commit.

## Task 3: Review and qualification

Files: packaged proof helpers, evidence/roadmap/compatibility/README/PRD.
Consumes exact Task1/2 application source and existing five-image stack.
Produces honest exact-artifact qualification and remaining product gates.

- [ ] One fresh whole-increment source review with Review Focus; fix important
  findings with RED/GREEN proof and relevant complete suites, no second review.
- [ ] Execute all five hosted gates including full API/browser/source/image proof.
- [ ] Extend packaged smoke to contacts/default/reference/ACL/recreation, execute
  exact archive in a unique private target directory with loopback-only ingress.
- [ ] Verify actual native/cgroup/worker/recovery and exact five-image security
  bindings; retain sanitized evidence outside Git and preserve older environments.
- [ ] Update current status/decisions/remaining gates, commit and push authorized main.
