# Phase 1 closure implementation plan

> Execute inline with superpowers:executing-plans and TDD; user authorized direct
> main publication and routine design decisions without approval pauses.

**Goal:** Close the master specification's Foundation/identity phase and stop.
**Spec:** ALTVIA_WORKSPACE_SPEC_CODEX.md, ADR-0017, existing ADR-0003/0004/0016.
**Architecture:** Same modular monolith; PostgreSQL outbox, JSON-only Dramatiq/Redis,
durable restricted identity activity, existing admin UI and hardened images.

## Global constraints and review focus

- Preserve current identities, grants, sessions, audit and pending outbox events.
- x86-64-v1, no Elasticsearch/OpenSearch or -march=native, no production deployment.
- Redis outage never loses events or prevents synchronous account/session writes.
- Delayed publishers/consumers cannot overwrite a newer lease or repeat effects.
- Unknown job data cannot execute a function or disclose credentials in logs.
- Revoked identity.manage closes activity reads and session-owned browser state.
- Worker DB credentials cannot modify identities/audit or elevate themselves.
- No destructive downgrade, retention purge, fabricated capacity or corporate SSO.

## Task 1: Durable worker and activity read

Files: models/migration, activity.py/worker.py/worker_config.py, provision.py,
activity_api.py/main.py, dependency lock and real PostgreSQL/Redis integration tests.
Consumes: existing outbox rows and identity guards. Produces: ADR-0017 projection,
bounded HTTP DTO, worker status/replay CLI and separate restricted worker login.

- [x] Write failing persistence/replay/lease/DLQ/ACL/migration/provisioning tests;
  observe RED on a fresh explicitly disposable altvia_test DB and isolated Redis.
- [x] Implement the narrow domain/transport/migration/security changes.
- [x] Prove duplicate delivery, concurrent claims/consumers, stale publisher,
  after-commit redelivery, Redis outage/loss, replay and role refusals.
- [x] Run full API suite, lint/format/mypy, Alembic checks and generated contracts.
  Expected: all pass with real services; existing behavior preserved. Commit.

## Task 2: Visible administrative history and observability

Files: generated client, account admin history section, HTTP/worker safe logging,
browser tests and Impeccable surface contract.
Consumes: Task1 projection; produces: real bounded timeline and secret-safe logs.

- [x] Prove browser history/paging/recovery, HTTP ACL/empty states and log redaction.
- [x] Implement within incumbent forms/list/session boundaries; no visual redesign.
- [x] Run full browser suite, build/types/lint/audit, themes/keyboard/axe/captures.
- [x] Fresh source review plus Impeccable reviewer/documenter, address material
  findings with regression proof. Expected: useful persisted history, no fake rows.

## Task 3: Complete Foundation runtime and closure

Files: Redis Dockerfile/start script, Compose, runtime checks, packaged smoke,
image security scan, CI security checks and runbooks/phase closure matrix.
Consumes: tested worker/API/UI. Produces: isolated five-image/six-service proof
(worker reuses API image), SAST/secret gates and exact target acceptance.

- [x] Build pinned baseline Redis, harden private network/secrets/resources/health.
- [x] Add SAST and tracked-source secret scanning without weakening current gates.
- [x] Exercise full packaged enqueue/dequeue/replay/recovery, application persistence,
  resource isolation/limits and clean shutdown. Scan all actual service images.
- [x] Requalify new mandatory artifacts on real target VM using existing approved
  multiplexed SSH and loopback-only task stacks; retain raw evidence securely.
- [x] Direct push main and observe all hosted gates. Record exact evidence against
  every Phase1 master requirement; mark closed only if all Phase1 rows pass.

Production deployment, real scope/provisioning, capacity/retention/RPO/RTO approval,
mail/storage and Phase2+ domain features remain their own later gates. The optional
ChatGPT SSH-host setup is documented as feasible; testing Codex CLI baseline and
authenticating that integration does not block independent Foundation development.

Completed 2026-11-09. Final implementation 2f6ba60 passed all five hosted gates,
290 API/31 browser tests and actual target five-image/native/cgroup/scan proof.
All original findings addressed; Impeccable full extension review returned ship
and documentation review completed. Exact evidence: docs/phase-1-closure-evidence.md.
Phase 2 has not started.
