# PostgreSQL-only API image implementation plan

> For agentic workers: use superpowers:executing-plans, TDD and one fresh final
> read-only review. User authorizes native main commits/pushes and no PR pause.

Goal: remove the unused vulnerable SQLite runtime capability, prove that removal
cannot regress silently and retain the real PostgreSQL API/container behavior.

Architecture: trim only the final API layer, using its existing package manager
and exact CPython optional-module paths. A standard-library image capability
checker runs during image build and the existing real Compose test.

Tech stack: current digest-pinned Python3.12/bookworm and uv builder; no new
application dependency, schema, HTTP contract or UI. Existing Docker/Linux CI.

Spec: ADR-0012; master specification sections5/10/11/12/13; API image scan report.

## Global constraints

- PostgreSQL-only API; SQLite is an explicitly unsupported container capability.
- Preserve all image digests, lockfiles, non-root/read-only controls and ACLs.
- No forced dpkg removal, apt autoremove, new source build or OS-family migration.
- No secrets/raw workbooks in context, image, scan report or logs.
- No production operation; no target x86-64-v1 homologation claim.
- Retain raw scanner findings; do not ignore unrelated or unfixed CVEs.

## Review focus

1. Removal must not break Python/native imports used by authentication/migrations.
2. A package absent from dpkg but still loadable must fail the guard.
3. Builder caches and the developer's Python remain unaffected.
4. Image-only changes cannot relax origin/CSRF/scope or runtime resource controls.
5. Scan deltas must reflect the same vulnerability DB, not suppression or risk acceptance.

## Task 1: Trim and enforce runtime capabilities

Files: infra/api.Dockerfile, scripts/check_api_runtime.py, .dockerignore,
scripts/container_smoke.py, tests/test_configuration.py if explicit URL coverage
is missing. Checker produces a safe JSON result or fails closed without secrets.

- [x] Add a checker first; run against current image and observe SQLite rejection.
- [x] Remove exactly sqlite3/_sqlite3 and purge libsqlite3-0 in final image only.
  Include checker through the context allowlist, run after production app copy,
  and call the same checker in the running Compose API.
- [x] Build actual Docker-format image; run checker non-root/read-only with dropped
  capabilities and verify positive SSL/compression/Argon2/API/CLI imports.
- [x] Run focused native configuration tests, lint/format/mypy/build and source
  contract stability checks; commit the coherent image capability change.

## Task 2: Scan, real runtime acceptance and publication

Consumes: Task1 actual image and checker. Produces: measured old/new scan delta,
actual Docker/Linux proof, reviewed evidence and published main with all CIs green.

- [x] Scan baseline and new Docker archives with the same immutable Trivy image
  and DB snapshot; compare package inventory and all reported finding identities.
- [x] Record exact image IDs, scanner/DB/report hashes, eliminated SQLite findings,
  remaining CVEs and safe rollback/capability limitations before claiming success.
- [x] Obtain one fresh read-only review; fix material findings with regression
  evidence. Reuse passing unchanged API/UI proof, execute affected container gate.
- [x] Update ADR/runbook/roadmap/evidence and CI integration; commit/push main and
  observe API, browser and container workflows. Stop only task-owned helpers;
  preserve data volumes and private test configuration.

## Pre-flight and rulings

- Task2 consumes Task1's same checked image and capability script; no DTO/schema
  interface changes. Source/image secret allowlists must be extended narrowly.
- The user opted out of intermediate permission questions. Select the bounded
  unused-capability removal; production/security risk acceptance remains excluded.
