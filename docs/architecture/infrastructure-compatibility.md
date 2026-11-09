# Infrastructure and x86-64-v1 compatibility

Status: requirement and executable validation plan, **not homologated**.
Source: master specification section 11; no SSH/guest/container test was run
in Phase 0. Local Windows tooling cannot establish Ubuntu compatibility.

## Reported guest baseline

Ubuntu 24.04.5 LTS, x86_64, 12 vCPUs, KVM/QEMU, guest CPU
`QEMU Virtual CPU version 2.5+`, virtual BIOS RHEL 7.6/i440FX. Specification
reports sse/sse2/pni/cx16/nx, and no ssse3/sse4_1/sse4_2/avx/avx2/fma/bmi2.
This approximates x86-64-v1, not a diagnosis of the physical host CPU.
RAM, persistent disk/IOPS/free space, mailbox traffic and active users are unknown.
Hypervisor changes are outside this workflow and are not prerequisites assumed.

No mandatory binary may require AVX/AVX2/AVX-512/SSE4.2/FMA/BMI2 or v2/v3/v4.
Also do not assume SSSE3/SSE4.1 from the amd64 image label. No Elasticsearch,
OpenSearch, Solr, MongoDB, vector engine or local embedding/AI runtime in MVP.
Search is PostgreSQL FTS + GIN. Native dependencies are audited per artifact.

## Capture on target, after access is supplied

Retain complete stdout/stderr, exact command, exit status, date, OS and artifact
digest. Redact credentials/customer content before storing evidence. The
specification's publication-ready diagnostic commands are preserved verbatim:

```bash
uname -m
lscpu
lscpu | grep -E 'Architecture|Model name|CPU\(s\)|Hypervisor'
grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' \
  | grep -E '^(sse2|pni|ssse3|sse4_1|sse4_2|avx|avx2|fma|bmi2)$' || true
```

The final `|| true` belongs only to the optional flag filter; it must never
mask failing runtime/startup/functional tests. Also record `/etc/os-release`,
memory, disk/volume layout, Docker/Compose versions and security configuration.
If multiple SSH commands are needed, use a task-scoped verified ControlMaster,
ControlPath and ControlPersist, reuse channels and close the master at completion.
Do not change sshd/hypervisor settings as a throughput workaround.

## Candidate manifest, all unapproved

| Component | Starting reference only | Digest | Required exercise |
| --- | --- | --- | --- |
| web/SSR | node:24-bookworm-slim | not selected | Next build, server start, SSR and actual native SWC/image path |
| API/worker | python:3.12-slim | not selected | FastAPI, Pydantic core, Argon2, SQL driver/TLS/MIME imports and operations |
| database | postgres:17 | not selected | Start on persistent volume, transaction/rollback, migrations, FTS/GIN and restore |
| queue/cache | redis:7 | not selected | Start, authenticated enqueue/dequeue, reconnect/loss/replay |
| private files | local adapter initially; S3 product undecided | not selected | Upload/quarantine/authorized download/restart/backup/restore |
| reverse proxy | product/version undecided | not selected | TLS, origin routing, body limits, headers and readiness |
| scanner/native libraries | undecided | not selected | Representative allowed/malicious file, fail-closed, CPU/memory |

Node 24/Python 3.12/Postgres 17/Redis 7 are specification test references,
not patch-version or security recommendations established on 2026-11-08.
Resolve a currently supported patch release, license and advisories before use.
Record source tag, platform amd64 manifest digest, image digest, base distro,
glibc, lockfiles/SBOM, native artifacts/ISA and vulnerability result. Deployment
uses the tested immutable image, never a newly resolved mutable tag.
No `-march=native` in portable builds. Optional acceleration is allowed only
when the baseline execution path is demonstrated without unsupported ISA.

## Original preliminary commands

Run on actual target, first replacing selection with reviewed artifact versions
or digests when available. These original commands are retained as examples:

```bash
docker run --rm --entrypoint node node:24-bookworm-slim -v
docker run --rm --entrypoint python python:3.12-slim python -V
docker run --rm --entrypoint postgres postgres:17 postgres --version
docker run --rm --entrypoint redis redis:7 redis-server --version
```

The Python example includes an extra `python` after `--entrypoint python` and
therefore attempts to open a file named python. Preserve the original for
traceability, but the executable version check is:

```bash
docker run --rm --entrypoint python python:3.12-slim -V
```

Any SIGILL/Illegal instruction/nonzero exit fails the test. Preserve output,
identify failing executable/library/build/ISA and choose a supported artifact.
Never suppress errors or disable healthchecks to pass a gate.

## Functional and recovery gate

Version output alone is insufficient. With the production images and isolated
persistent test volumes on the guest:

1. Start proxy, web, API, worker, PostgreSQL, Redis and selected storage/scanner.
   Prove readiness, restarts and resource limits, without exposing internal ports.
2. Run migrations on empty/disposable DB; verify constraints and transaction
   commit/rollback. Create a user/client/project/work item and verify after restart.
3. Execute Portuguese FTS with authorization predicates and GIN query plan.
   Exercise optional pg_trgm only if introduced through migration.
4. Execute outbox enqueue/dequeue, worker restart, replay/race and Redis loss;
   verify protected effects remain singular and no committed event disappears.
5. Exercise actual native password hashing, sanitization, upload/scan/download,
   MIME/TLS, SWC/SSR and image-processing paths selected in the final build.
6. Run login/negative RBAC and the current end-to-end slice on the guest.
7. Run representative concurrent workload; measure CPU, RAM, IO, queue age and
   p95. Establish limits from actual RAM/disk/traffic, not 12 vCPUs alone.
8. Restore database + matching attachment manifest/objects/config into isolation;
   verify checksums/FKs/private downloads. Time measured RPO/RTO and demonstrate
   schema-compatible deployment rollback using the same baseline.

| Gate | Current evidence |
| --- | --- |
| Raw guest flags/OS resources captured | pending access |
| Supported artifacts and immutable digests approved | pending build/selection |
| All images/native paths start without SIGILL | not executed |
| Functional DB/Redis/API/web/worker/storage/FTS | not executed on guest |
| Negative authorization/E2E on production images | not executed |
| Load and recovery measured | not executed |
| No prohibited dependency or native ISA | architecture prohibits; artifact proof pending |

Phase 1 can develop and test locally while access is missing. Its VM gate
remains open. No production compatibility, performance or availability claim
is permitted until these checks produce real evidence.
