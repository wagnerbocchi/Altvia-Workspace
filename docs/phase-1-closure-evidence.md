# Phase 1 Foundation closure evidence

Date: 2026-11-09. Status: Phase 1 closed; all Foundation gates passed.
Boundary: master specification Phase 1 only; stop before Phase 2.
User authorized direct publication to main without PR and isolated target testing.

## Delivered behavior and ownership

Existing real identity/session/account/team administration now has an actual
durable background consumer. The same modular monolith runs as a separate worker
process, reusing the API image. PostgreSQL owns event truth, leases, attempts,
deduplication and the administrative activity projection. Authenticated private
Redis carries only JSON event UUIDs for the registered identity actor.

The restricted activity API and account-directory history show committed account,
team and access changes with cursor pagination, local timestamps and independent
read-error recovery. They require fresh identity.manage; roster membership and
team read grants never confer administrative access. Immutable audit remains
separate and API audit/outbox access remains INSERT only.

The selected implementation and fixed bounds are in ADR-0017. This is identity
history, not ticket automation, notifications or a Phase 2 project interface.
Local authentication has a replaceable identity boundary; actual OIDC integration
remains explicitly deferred under ADR-0003 until issuer/client/claims are known.
No speculative adapter, simulated SSO or claimed MFA is included.

## Changes, schema and rollback

Contracts preceded code in 3fba9a0; backend/worker c9dfb26; real browser history
410abe2; private Redis/runtime/security CI 6e655f5; reviewed corrections c4252eb;
restricted runtime-test credential correction 2a80c60; observed Redis health
recovery 7851794/29f1e4e.
Redis vendor zlib correction: 2f6ba60.

Principal files: apps/api/altvia/{activity,activity_api,worker,observability,
config,models,provision}.py; activity migration b46087000005; generated OpenAPI
and TypeScript contracts; apps/web/src/components/user-admin/activity.tsx;
infra/{compose.yaml,redis.Dockerfile,start-redis.sh,redis-health.sh};
scripts/{container_smoke,scan_service_images,summarize_source_security}.py;
scripts/ci_redis.sh and the five CI workflows. Relevant integration tests accompany
each boundary. Source workbooks, credentials, production data and raw logs are
excluded from Git.

Migration b46087000005 expands processing metadata and adds activity_events and
processed_events. Existing events are preserved. A populated projection prevents
destructive downgrade. API gets SELECT only on projection; worker gets SELECT
outbox, UPDATE only status columns, SELECT/INSERT projection/deduplication and
INSERT audit for confirmed replay. Elevated pre-existing role/table/column grants
are refused. No schema, user/session/role or payload write authority is added.

Rollback retains the expanded schema and chooses a compatible prior image.
Never delete history/deduplication rows, force downgrade or reset a volume.
Replay requires authorized inspection and interactive typed UUID confirmation;
the operation is audited. See docs/runbooks/api-containers.md for exact procedures.

## Review findings and causes

Fresh independent source review found two issues. Both reproduced before fixes:

1. Clean pinned Trivy 0.75.0 reports omit Results. The sanitizer incorrectly
   required that array. It now accepts the authentic clean report with scanner
   and filesystem metadata, rejects malformed/incomplete data and retains all
   findings without raw matches/code. Scanner execution failure still blocks CI.
2. A 25-event dispatch batch ignored SIGTERM between sends and inherited Redis
   retries. It now checks cancellation between publications, leaves unsubmitted
   leases recoverable, uses explicit zero Redis retries and bounded socket/join
   times within Compose's 30-second grace. Real Redis cancellation regression
   and packaged unavailable-broker shutdown/recovery are required evidence.

Actual target build also exposed a Redis upstream recursive-make race: separate
parallel top-level goals linked redis-cli before hdr_histogram's library existed.
One make -C src invocation owns both goals; the corrected build passed on target.
No compiler error was suppressed and baseline CPU flags remain unchanged.

The first blackhole test used the API credential to inspect outbox leases and
correctly failed permission denied for table outbox_events. The test now inspects
leases with the separately restricted worker credential. Application privileges
were preserved. Failed runs remain diagnostic evidence, not successful acceptance.
The next test failure was a Compose dependency-state race after unpause:
Compose --wait refuses an already unhealthy service immediately. The corrected
test polls the actual bounded Redis health state before restarting the worker;
it does not bypass a dependency or weaken a healthcheck.

The first full target scan reported CVE-2026-4738, MEDIUM, in Redis's inherited
zlib 1.3.2-r1. Alpine's [3.23 security database](https://secdb.alpinelinux.org/v3.23/main.json),
consulted 2026-11-09, explicitly maps this finding to zlib 1.4-r0. The runtime now
installs that exact signed vendor revision, matching the other service images.
The pre-fix unfiltered evidence is retained separately; no suppression or risk
acceptance is used. A new exact-image target run and scan establish the correction.

## Executed local and browser evidence

- uv run ruff check .: passed.
- uv run ruff format --check apps/api scripts: passed, 55 files.
- uv run mypy apps/api/altvia: passed, 18 source files.
- uv build: wheel/source distribution passed.
- Guarded real PostgreSQL/Redis full pytest: 290 passed in 310.79 seconds.
- Earlier full real HTTPS/API/PostgreSQL/Redis/worker browser suite: 31 passed.
  Unchanged product frontend reused this evidence; capture-only test correction
  reran @activity and passed 1 test in 6.3 seconds.
- pnpm web:check and existing production frontend build passed. Generated
  contract drift, dependency audit and locked Linux builds also run in hosted CI.

Fresh Impeccable finish full review returned ship for the history extension,
after replacing invalid mobile captures caused by locator screenshot scrolling.
All eight authoritative desktop/mobile light/dark full-page/history captures are
settled and unobscured; axe and overflow checks passed. Detector returned [].
No product styling was altered to repair captures. Independent documenter checked
the implementation and preserved incumbent DESIGN.md/.impeccable/design.json:
no durable system change. Existing empty sidecar narrative.rules drift is recorded
without canonizing or repairing unrelated design-system data.

## Hosted gates and target acceptance

Final source revision: 2f6ba60a92a9e75b56acce64196ac59b5db881ef.
Archive SHA256: b51f00334bea090ef527681b0b3cf83a6732ffba18ae06e6326a7825579ceea7.
Actual target run: 22:58:21 through 23:01:12 UTC, exit 0. Isolated project
altvia-test-d62aa86b7f. Source was extracted into a private task directory on the
supplied Ubuntu/KVM guest; no public application listener was opened. Complete
packaged TLS/account/team/ACL/persistence/replay/browser/restore/readiness checks
passed. Seven packaged browser captures were opened and inspected.

During a real claimed batch with Redis paused, SIGTERM exited 0 in 7.742433756
seconds, without OOM or SIGKILL; after Redis health recovered and the worker
restarted, all 27 test events projected. This proves the source-review shutdown
fix with unavailable established sockets, rather than an idle process only.

Separate target verification passed all seven service/job memory/CPU/PID bounds,
actual cgroup files, read-only roots, capabilities/no-new-privileges, private
database/queue networks, loopback-only ingress, non-root runtime and native import/
binary checks. Worker uses exactly the tested API image. Task containers stopped,
volumes preserved and task-scoped authenticated SSH master closed.

The source-built Redis is 7.4.12, libc allocator, -O2 -march=x86-64 -mtune=generic.
Source archive SHA256 324ab63d55c607639b419f547b213c62ae39ff50e09870e450a11c272567b84f;
pinned Alpine amd64 base 644c1ad8fc45cc581ab1b5ea7ec1bebc9b037fd4801ad697ca124deb3f9c9332.
Real guest flags remain sse/sse2/pni/cx16, without SSSE3/SSE4.1/SSE4.2/AVX/AVX2/FMA/BMI2.
No mandatory ISA beyond x86-64-v1, Sharp, Elasticsearch or OpenSearch was added.

| Actual target image | Image ID (sha256) | Reported vulnerabilities, all severities |
| --- | --- | --- |
| API / worker / migrate | 7b1d2ec3ba4e9a72e96ed35a2587f4fd72490a989ad59e307befc93474d35246 | 0 |
| PostgreSQL | fb23fd346aabb3a19994749553690511ff3a1178b5b196647f11c03c8f7632ee | 0 |
| Web | 417f6e09e3846ea948cd929eacfd18a97a7eddb28568427aba0d7a1e601a1014 | 0 |
| Ingress | 2bf923fa3d544e9331555f5dbb3f6cc98bf2a24f761ab82fba126616d9397022 | 0 |
| Redis | 703f1e0b34d4c634580f6c296f3cd88a88c522312edfafbd9c6fc462e4b3048d | 0 |

All five scans use pinned Trivy 0.75.0, unfiltered reports and the same database
SHA256 8c808b8e2b45da2b9849fab569412fd5b0a59455d3335ea0321f0179bcd86130.
The scanned IDs exactly match resource/native-tested IDs. The new Redis report
contains no CVE-2026-4738. Raw reports, manifest, source hash, exact stdout/stderr,
resource commands/results, outage proof and PNGs are retained outside Git in
managed artifacts/phase1-closure/qualified-target-evidence.tar, SHA256
9ce2dac8124e609cdf93407296281f48a9f66758ed9211d77b8c5a574591e1ec.
The pre-zlib bundle and failed task directories remain separately preserved.

Source security on the final revision passed: four LOW Bandit metadata findings,
zero blocking SAST and zero detected secrets. The LOW rows are the CLI's empty
password initializer and internal non-authorization assertions in CLI, management
and provisioning; no credential is hardcoded and no access check relies on assert.
Complete severity metadata is retained without blanket exclusions. All-service
image scanning separately blocks HIGH/CRITICAL and preserves every severity.

Hosted final-source runs:

- [API 42716580794](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42716580794): passed; 290 tests in 79.16 seconds, lint/format/mypy, migration upgrade/drift and build.
- [Browser 42716580342](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42716580342): passed; 31 tests in 39.5 seconds, locked build/types/contracts, Sharp guard and dependency audit.
- [Source 42716580415](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42716580415): passed; complete safe SAST/secret metadata.
- [Images 42716580772](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42716580772): passed; five actual images.
- [Containers 42716580284](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42716580284): passed; actual packaged Docker/worker/outage/HTTPS/recovery/browser proof and ShellCheck.

## Master Phase 1 acceptance matrix

| Requirement | Evidence and current disposition |
| --- | --- |
| Web/API/worker and Compose | Passed: persisted identity UI/API plus real registered consumer and packaged execution |
| PostgreSQL/Redis/configuration | Passed: fixed database roles, file secrets, private authenticated bounded queue and actual durable recovery |
| Migrations | Empty upgrade, preservation, drift and guarded downgrade refusal exercised by full suite and hosted API checks |
| Local auth, sessions and OIDC boundary | Argon2id, opaque hashed server sessions, expiry/revocation/CSRF/rate controls; ADR-0003 defers actual corporate OIDC |
| RBAC/users/teams | Existing real management plus fresh resource authorization and negative ACL/race/replay tests; no roster-based content grant |
| CI/security | Passed: all five workflows on final source, zero reported image vulnerabilities, zero blocking source findings |
| Actual baseline CPU | Passed: final five-image/six-service stack plus migration job executed on supplied guest; exact IDs scanned and resource/native-tested |
| Functional login/API/database/tests | Passed: 290 API, 31 browser and final packaged/hosted proof |

## Limits and next delivery

Phase 2 has not started. No production deployment, real account provisioning,
customer import, mailbox setup, external listener or Zammad retirement occurred.
Production workload/IOPS, retention, RPO/RTO, corporate identity claims, real scope
matrices, mail/storage providers and pilot approval remain later decision gates.
The conservative cgroup bounds establish isolation, not representative capacity.

Optional ChatGPT SSH environment integration was investigated as feasible in
official OpenAI documentation. Codex CLI was absent on the VM; it was not installed
or authenticated and its actual baseline compatibility is unproven. This optional
integration is separate from application Foundation acceptance.
