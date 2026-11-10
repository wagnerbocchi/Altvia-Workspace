# Infrastructure and x86-64-v1 compatibility

Status: current five-image Foundation stack **qualified on the supplied VM**;
future native components and production capacity/readiness gates remain open.
See [actual target evidence](../target-vm-foundation-evidence.md).
Final Phase 1 worker/Redis qualification, corrected zlib, exact five image IDs,
zero reported vulnerabilities, cgroup/isolation and unavailable-broker shutdown
are in [the closure evidence](../phase-1-closure-evidence.md). Earlier four-image
results below remain historical evidence for their distinct artifacts.
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

## Original Phase 0 candidate manifest, superseded by runtime ADRs

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

### Phase 1B native dependency decision

Next.js 16.4.5 lists Sharp as optional. Its Linux x64 prebuilt artifacts require
SSE4.2 according to [Sharp installation prerequisites](https://sharp.pixelplumbing.com/install/).
The workspace explicitly excludes optional `sharp` installation and sets
`images.unoptimized=true`. No image optimizer is required or used by this slice;
the browser integration checks that `/_next/image` is unavailable. Do not remove
this exclusion without a separately proven baseline-compatible replacement.

Node 24.21.0, Next SWC/Turbopack, Tailwind Oxide and remaining native dependencies
are development-tested only. Their exact Linux artifacts, glibc requirements,
baseline execution paths and real guest behavior remain Phase 1C acceptance
gates. Windows success and npm's `cpu: x64` metadata do not prove baseline ISA.

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
| Raw guest flags/OS resources captured | captured on supplied VM, 2026-11-09 |
| Supported artifacts and immutable digests approved | current four tested image IDs recorded; production deployment remains separate |
| All images/native paths start without SIGILL | current four-image build/runtime paths passed on target; future artifacts require revalidation |
| Functional DB/Redis/API/web/worker/storage/FTS | PostgreSQL/API/web/ingress/FTS passed; future worker/Redis/storage/scanner remain unimplemented |
| Negative authorization/E2E on production images | current packaged identity/team slice passed on target; no production deployment |
| Load and recovery measured | synthetic logical restore/restart passed; representative load and operational RPO/RTO remain pending |
| No prohibited dependency or native ISA | selected artifacts passed target build/runtime and unfiltered image scans; repeat for changed native artifacts |

Phase1C-d records actual bookworm amd64 API/PostgreSQL/ingress candidates in
docs/phase-1c-evidence.md. Non-root/read-only imports, Argon2id and a domain-name
TLS regression ran locally. Full Compose resource proof uses hosted Docker/Linux
because the existing local Podman VM lacks cgroup controllers; no resource limit
was removed. Trivy findings/dispositions are in docs/security/api-container-scan.md:
production image-security acceptance remains blocked. These observations do not
change any actual guest gate above or approve a different ISA baseline.

ADR-0013 replaces the Bookworm runtime family with official pinned Alpine Python
3.12/PostgreSQL17/unprivileged nginx candidates and signed vendor fixes. Gosu1.19
is rebuilt with Go1.27.3, CGO_ENABLED=0 and GOAMD64=v1; production Python packages
use only locked musllinux/pure wheels. No -march=native or mandatory higher ISA.
All244 API tests passed on Linux/Alpine against the candidate PostgreSQL; imports,
Argon2/TLS paths and no-SQLite guard passed. Three same-DB image scans have zero
HIGH/CRITICAL findings. This replaces the earlier image-security observation,
not the actual guest gates. Source defaults and modern workstation/CI execution
remain insufficient to homologate the unavailable x86-64-v1 VM. PostgreSQL libc
changes require a fresh-volume logical restore; the image refuses unmarked data.

Phase 1 can develop and test locally while access is missing. Its VM gate
remains open. No production compatibility, performance or availability claim
is permitted until these checks produce real evidence.

ADR-0014 adds the actual standalone web runtime: signed Alpine Node24.22.1-r1,
full ICU for pt-BR, shared zlib1.4/Brotli1.2.1/OpenSSL3.5.9 and Sharp exclusion.
Pinned builder/runtime inputs are in infra/web.Dockerfile. Local actual SSR,
static assets, read-only/non-root native guard and SIGTERM cleanup passed; all
four installed-image scans report zero findings. This does not close any guest
gate. The Alpine nodejs APKBUILD uses generic compiler flags and shared-library
switches; SIMD-enabled libraries still require functional tests on the actual VM:
https://github.com/alpinelinux/aports/blob/3.24-stable/main/nodejs/APKBUILD.

## Actual target inventory, 2026-11-09

The owner supplied password-based SSH access after updating the VM. Read-only
inventory completed with SSH exit 0 and strict verification against the existing
known-host key. No package, service, SSH setting, firewall rule or application data
was changed. Target address and complete raw results remain in private managed
artifacts/target-vm/initial-inventory-2026-11-09/, outside Git.

The current observed guest differs from the original reported baseline above:

| Item | Observed result |
| --- | --- |
| OS/kernel | Ubuntu 26.04.1 LTS; 7.0.0-43-generic |
| CPU | x86_64; 8 vCPUs; KVM; QEMU Virtual CPU version 2.5+ |
| Relevant flags | sse, sse2, pni, cx16; no ssse3, sse4_1, sse4_2, avx, avx2, fma or bmi2 |
| RAM | 33,635,188,736 bytes, approximately 31.3 GiB |
| Storage | 500 GiB virtual disk; ext4 root; 497,031,471,104 bytes available at collection |
| Docker/Compose | Executables absent; version/info/runtime probes recorded exit 127 |

The raw inventory is evidence of actual guest resources and advertised CPU flags,
not of application/native artifact compatibility. Runtime, functional, recovery
and load gates remain open. Docker/Compose installation and an isolated test stack
require host-change authorization; that next action is pending. Check repository
package candidates and simulate dependencies before installing, and retain exact
versions and command outcomes. Keep application test listeners on loopback and
preserve all existing VM data. Do not substitute OS metadata for execution proof.

### Authorized installation and native qualification completed

After the inventory, the owner authorized Docker/Compose installation and isolated
qualification. Docker 29.1.3, Compose 2.40.3 and Buildx 0.30.1 were installed from
the existing signed Ubuntu repositories after simulation. The four current images
then built and passed real runtime, TLS, resource ACL, persistence/restart, logical
restore, FTS and packaged browser tests on this guest. Kernel cgroup files confirmed
the declared memory/CPU/PID limits; only the proxy bound a loopback application port.
The exact tested image IDs have zero reported vulnerabilities in one fresh-DB scan.

Q-01 is satisfied for those artifacts and exercised native paths. Earlier pending
statements above describe the historical observations of their respective slices;
the current acceptance and precise limits are in the linked target evidence.
Test containers were stopped and volumes preserved; SSH control session was closed.
No remaining product feature, future native artifact or production capacity/readiness
gate is implicitly completed by this result.

### Current Phase 2A qualification

The Foundation worker/Redis increment and subsequent client registry supersede
the historical four-image observations above. Source dc091de built/executed the
five-image/six-service registry stack and migration job on the same baseline guest,
with no new native dependency or ISA requirement. Real customer delegation,
cross-client denial, persistence, scoped activity and packaged browser flows passed.
Native/cgroup checks passed and the exact same five scanned IDs report zero
vulnerabilities. The guest still lacks SSE4.2/AVX/AVX2. See
docs/phase-2a-client-evidence.md for immutable source/image IDs, commands, dates,
retained reports and limits. Representative load, production readiness and future
mandatory native artifacts remain separate gates.
