# API container runtime implementation plan

> For agentic workers: use superpowers:executing-plans with TDD and one fresh
> final read-only review. Native main commits/pushes are already authorized.

Goal: exercise the current API behind real HTTPS using non-root, reproducible
containers, persistent PostgreSQL and separated migration/runtime credentials.

Architecture: extend existing Settings with native mounted-secret discovery;
restricted provisioning beside identity CLI; one API image reused by migration
job and runtime. Compose owns topology; black-box smoke owns acceptance.

Tech stack: Python3.12/bookworm, locked uv dependencies, PostgreSQL17/bookworm,
nginx-unprivileged/bookworm, Compose. No new application dependency or UI change.

Spec: master specification sections5/10/11/12/13; ADR-0011; security requirements.

## Global constraints

- x86-64-v1 mandatory; no new higher-ISA dependency or CPU homologation claim.
- No real data, production deployment, remote security or existing user containers.
- Mounted secrets never copied/logged; no long-lived migration credentials in API.
- Runtime identity/team behavior, origin/CSRF and scoped ACL remain unchanged.
- Test mutation requires explicit opt-in, altvia_test and task-owned project scope.
- No worker/Redis/web scaffolding or idle/fake event consumers in this slice.

## Review focus

1. Runtime DB role must not own schema, mutate audit or inherit elevated roles.
2. Secret source precedence, unreadable/invalid files and failure output stay safe.
3. Dirty build contexts must not include .env, raw workbook, keys or development deps.
4. Restart must retain DB state/session and report unready DB without killing liveness.
5. Only HTTPS ingress is published; cleanup never deletes unrelated resources/volumes.

## Task 1: Mounted secrets and restricted runtime provisioning

Files: config.py, provision.py; tests/test_runtime_provision.py, test_configuration.py.
Produces: native fixed file-secret discovery and provision_runtime(engine, runtime_url)
with fixed altvia_app login, same-target validation, elevated-role rejection,
explicit CRUD table privileges, audit/outbox INSERT only and no DDL grants.

- [x] Write tests first: runtime credentials load from mounted source without
  disclosure; invalid/missing files fail closed; privilege matrix and duplicate
  provisioning; reject mismatched target and elevated/inherited runtime roles.
- [x] Observe RED before implementation; implement narrow settings/provision logic.
- [x] Run real DB permission/API proof and full API suite, lint/types/build; commit.

## Task 2: Container image, HTTPS stack and black-box proof

Files: infra/api.Dockerfile, infra/compose.yaml, infra/nginx.conf, .dockerignore;
scripts/container smoke/fixture; container CI; runbook/evidence/roadmap.
Consumes: Task1 secret convention/provision function; existing API/CLI/migrations.
Produces: runnable non-root API image, one-off migration job, private DB/API and
TLS ingress, guarded smoke with persistence/negative ACL/credential/privilege proof.

- [x] Define black-box checks before stack code; observe absent artifact failure.
- [x] Implement digest-pinned multi-stage image and Compose with file secrets,
  separate roles, health, bounded resources, volumes and no API/DB host ports.
- [ ] Build/run actual images; prove TLS login/team ACL/CSRF, DB permission matrix,
  migration rerun, container recreation and session/data survival, readiness503,
  non-root/read-only runtime, SIGTERM and absence of build-context secrets.
- [ ] Add hosted Docker Compose gate, verify generated contracts unchanged,
  obtain fresh read-only review; correct material findings with regression proof.
- [ ] Document commands/artifacts/results/limits, commit/push main, observe all CIs;
  stop only task-owned services, preserve volumes and record remaining Phase1 gates.

## Rulings and pre-flight

- User opted out of approval pauses; execute the selected bounded runtime increment.
- Task2 consumes Task1's fixed role, file names and unchanged Settings interface.
- Use actual existing services as smoke data path; no synthetic production seed.
