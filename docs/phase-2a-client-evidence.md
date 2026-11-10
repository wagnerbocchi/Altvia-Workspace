# Phase 2A client registry evidence

Date: 2026-11-09. Status: Phase 2A client registry qualified. Phase 2 remains open.
User authorized incremental development and direct main publication without PR.
No production deployment, customer provisioning, real-data import or Zammad cutover.

## Delivered behavior

Persisted client create/list/detail/rename/archive/restore and scoped history reuse
the modular monolith, PostgreSQL, current sessions and durable activity worker.
Both an explicit customer ceiling and a client role are required for every read;
platform administration and team membership never bypass this boundary. SQL filters
before pagination; hidden and absent UUIDs both return 404.

An identity.manage operator explicitly selects an active initial manager. Creation
grants that account access and invalidates its sessions atomically. No creator
grant is implied. The protected create/replay receipt includes only client and
manager UUIDs, never current customer metadata; replay never repeats delegation.
Further grant/update/revoke operations use typed email/client UUID confirmation in
the restricted CLI. Metadata changes use If-Match; session replacement disposes
browser intents. Client history is excluded from global identity activity.

The browser supplies an actual bounded directory and manager picker, detail,
confirmations, archive/restore, scoped history, independent read recovery,
uncertain-create verification and deliberate stale-edit discard. It reuses existing
session-owned caches, controls and semantic themes. No project/area/task/contact
placeholder or speculative default project was introduced.

## Changes and rollback

- 06537b2: contracts, ADR and implementation plan before code.
- 4a9a954: registry, scope, migration, CLI and activity backend.
- 24d534b: reviewed coherent inactive-grant no-op correction.
- 7092456: real client browser flow, form-button regression and fixture isolation.
- 11b5043: actual packaged client persistence/ACL/browser proof.
- dc091de: test account isolation and delegated-account version expectation.

Migration b46087000006 adds client/grant tables, exclusive client role scope and
client activity constraint while preserving existing identity/team/history rows.
Populated clients/history refuse destructive downgrade. No new dependency, native
version, external engine or ISA requirement was introduced. All mandatory native
build flags and x86-64-v1 constraints remain unchanged. The actual changed images
passed target execution as recorded below.

Rollback preserves expanded data and a compatible worker. An older identity-only
consumer would dead-letter client events: keep the new compatible worker or stop
it until a compatible version resumes. Never remove history/grants, reset volumes
or force downgrade. Operational commands: docs/runbooks/client-registry.md.

## Review and regression proof

Fresh source review found two material issues, both reproduced before fixes:

1. Paging and read-recovery native buttons inside the create form defaulted to
   submit. Real candidate retry unexpectedly created a client (POST 201). Explicit
   type=button on shared controls prevents the unintended mutation; both retry and
   candidate-pagination browser cases verify no create request occurs.
2. Inactive-target checks preceded coherent grant no-op detection. Archived-client
   and deactivated-account repeat tests returned 409. Coherent no-ops now return
   before active-target validation; actual new grants/repairs remain denied.

Initial fixtures also exposed shared login buckets and the original last-active-
administrator invariant. The client suite now starts with its own ordinary account
and elevates it through the real protected API only after the one-admin account
tests. Production throttling and last-admin protection are unchanged.

On 11b5043 hosted browser checks passed 36/37: a late team-session test reused the
ordinary account's exhausted login bucket (429). It now creates its own ordinary
replacement subject through the protected API. Full local 37 passed afterward.
Hosted container proof reached account persistence but expected version 10 after
explicit manager delegation had correctly advanced it to 11; dc091de updates that
assertion. Neither failure required a production behavior or privilege change.

Fresh Impeccable full finish review: disposition ship, no material fixes after
11 final light/dark desktop/mobile/detail/directory/confirmation/uncertainty/conflict
captures. Documenter compared the implementation and all captures to the incumbent
system and preserved DESIGN.md and .impeccable/design.json. PRODUCT.md receives only
factual capability corrections. Preexisting empty sidecar narrative.rules drift
was reported and left untouched. No new visual world, raster assets or comp.

## Executed local checks

- Full API: 316 passed in 363.78 seconds against disposable real PostgreSQL/Redis.
- Full browser: 37 passed in 1.9 minutes; repeated after dc091de test isolation,
  again 37 passed in 1.9 minutes, real HTTPS/API/PostgreSQL/Redis/worker.
- Final client spacing captures: three focused browser flows passed in 14.6 seconds,
  with axe/overflow checks. No application UI change followed the final review.
- Ruff check/format, strict mypy (20 source files), Python wheel/source build,
  generated OpenAPI/TypeScript, pnpm web:check and production build passed.
- dc091de targeted validation: pnpm web:check, full browser suite,
  Ruff check/format on container_smoke.py and git diff --check passed.

Commands: uv run python .superpowers/phase1-tests/run.py --api apps/api/tests;
uv run python .superpowers/phase1-tests/run.py; pnpm web:check; pnpm web:build;
uv run ruff check apps/api scripts; uv run ruff format --check apps/api scripts;
uv run mypy; uv run python scripts/export_openapi.py;
pnpm --filter @altvia/web generate:api. Disposable helper paths are local evidence
wrappers, not required application dependencies. Private logs remain outside Git.

## Hosted and target gates

Exact tested source: dc091de300956f3bf0ff814206bb12598a7c2d14. Source archive
SHA256 78bbf872ccd1cd110e3216c1a28abdde6600c1612080e4318eb60dc290fd6f3c.
Subsequent documentation-only changes do not change these application artifacts.

All five hosted workflows passed on that revision:

- [API 42726532642](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42726532642): 316 tests in 90.78 seconds, lint/format/mypy, migrations/drift and Python build.
- [Browser 42726532782](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42726532782): 37 tests in 1.1 minutes, locked build/types/contracts/native guard and dependency audit.
- [Source 42726532347](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42726532347): source SAST/secret gate passed.
- [Images 42726532464](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42726532464): five service-image security gate passed.
- [Containers 42726532362](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42726532362): real Docker/HTTPS/ACL/clients/recovery/packaged-browser and ShellCheck passed.

Target execution ran from 2026-11-10T00:14:34.188294+00:00 to
2026-11-10T00:18:01.707864+00:00 (2026-11-09 local date) in a distinct private
Phase 2 workspace, preserving all earlier qualification directories. The source
built all five images on the supplied guest. Its flags still lack ssse3, sse4_1,
sse4_2, avx and avx2. No SSH/server policy, firewall or Windows execution policy
was changed. Password authentication stayed in the user's interactive terminal;
all commands reused one authenticated multiplexed client master.

The packaged proof exercised logical Bookworm-to-Alpine restore/Unicode/FTS,
real HTTPS/cookies/CSRF/non-root/secret boundaries, team/account behavior,
explicit customer delegation, admin-without-ceiling denial, two-client isolation,
scoped activity and API/PostgreSQL recreation with persisted customer data.
Actual browser self-delegation revoked the session, required relogin and passed
client archive/reload/restore/history/axe. All eight packaged PNGs were opened
and inspected, including client-mobile.png. Worker SIGTERM during blackholed
Redis exited 0 in 8.680857534 seconds and all 27 events recovered.

Resource/native checks verified each service's actual cgroup memory/CPU/PID limits,
read-only root, dropped capabilities, no-new-privileges, private database/queue
networks and only a loopback ingress listener. API imports/Argon2/TLS paths passed;
API runtime reports Python 3.12.16, zlib 1.4, no SQLite or package installers.
Web runtime reports Node 24.22.1, zlib 1.4, Brotli 1.2.1, OpenSSL 3.5.9, standalone
present, Sharp/package installers absent. These are exercised native paths,
not a representative load or production-capacity guarantee.

| Actual target image | SHA256 image ID | Reported vulnerabilities |
| --- | --- | --- |
| API / worker / migrate | d86ec9b6a78e8666a4f49702ba8a04cef117da7aecb424eee8016a0bab410d41 | 0 |
| PostgreSQL | 1a21146ad27f53e2f4b46c3f010f8adfa01ca0d97a5bde773a4aa020571c0969 | 0 |
| Web | ce660d42428d60495d20ead80404fee4321cf2171cd711e846ee44846c60a331 | 0 |
| Ingress | d4c5662c9effa8168ff77b29c59e9d8af59b32c8f48de3b55fd834c552e7d024 | 0 |
| Redis | 597cca3cc88668e3e7251f79ca6d3e16ea03cee2c92ab526053996a4cb4c9ae1 | 0 |

Pinned Trivy 0.75.0 scanned all five unfiltered images with database SHA256
8c808b8e2b45da2b9849fab569412fd5b0a59455d3335ea0321f0179bcd86130.
Scanned IDs exactly equal the resource/native-tested IDs; worker uses the API ID.
Raw reports, source hash, exact command outputs, native/cgroup checks, outage proof
and screenshots are retained outside Git through the security artifact tool in
artifacts/phase2-clients/qualified-target-evidence.tar, SHA256
719e33bd1b07d36e68147784828c282633c3bb4df4aaecb53fbe914942aeaf76.
Fresh review/documentation disposition is retained in the same namespace.
The 11 reviewed local captures, sanitized final browser output and design handoff
are retained in local-browser-evidence.zip, SHA256
03248819c5abfd33640b072e8f90f9568c6f2fbbcd939b27e8181fa3a6d4340b.
Task containers were stopped, volumes preserved and SSH master closed.

Projects, areas, contacts, work items, Kanban/search/My Work and all subsequent
phases remain separate work. Registry delivery alone does not complete FR-002
or Phase 2; real membership/mappings and production readiness remain Q-04/Q-05
and the roadmap's existing gates.
