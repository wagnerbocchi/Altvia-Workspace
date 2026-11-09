# Target VM qualification: current Foundation stack

2026-11-09. The owner explicitly authorized Docker/Compose installation and
isolated qualification, with application listeners restricted to loopback.
The current four-image Foundation stack passed on the supplied VM. This does not
complete the remaining product modules or establish production capacity/readiness.
Raw host addresses, credentials, test secrets and operational logs remain outside Git.

## Target and host preparation

Observed guest: Ubuntu 26.04.1 LTS, kernel 7.0.0-43-generic, KVM, x86_64,
8 vCPUs, QEMU Virtual CPU version 2.5+, 31.3 GiB RAM and a 500 GiB virtual disk.
Raw CPU flags include sse/sse2/pni/cx16 and omit ssse3/sse4_1/sse4_2/avx/avx2/fma/bmi2.
These describe the actual guest, not the physical host CPU.

Existing signed Ubuntu repositories supplied the reviewed five-package plan:

| Package | Installed version |
| --- | --- |
| docker.io | 29.1.3-0ubuntu4.1 |
| docker-compose-v2 | 2.40.3+ds1-0ubuntu1 |
| docker-buildx | 0.30.1-0ubuntu1 |
| containerd | 2.2.2-0ubuntu1.2 |
| runc | 1.4.0-0ubuntu1 |

APT simulation preceded installation; no existing package was upgraded or removed.
Docker/containerd are active and enabled for boot. Docker reports AppArmor,
built-in seccomp and cgroups v2 enabled. No SSH server configuration, host key
or manual firewall rule was changed. Docker manages its own container
network rules. The recorded rollback preserves all data and removes only newly
installed packages if later requested. A host reboot was not performed.

Authentication used an existing trusted server key and the owner's password entered
directly in a terminal. A task-scoped Linux OpenSSH ControlMaster in the existing
local WSL environment reused one authenticated connection. Its private temporary
client directory held only the trusted public host key/control socket. The master
was checked and closed after evidence retrieval; no SSH login password or SSH
private key was stored or added to the VM.

## Reproduction and corrected setup failures

Application input was f6307c1; Git archive SHA256
3a10a049cb8a59ec0be2da25db7fda1dc5825176cd33d9b470dbcdf5b7575477.
The two test helpers were updated to the exact contents committed in 358e027.
Production application files, runtime inputs and lockfiles did not change.

The transfer initially combined private umask 077 with Python's data tar filter,
which created source subdirectories as 0700. The non-root migration user could not
traverse versions/, so Alembic discovered no heads and provisioning refused the
missing tables. A root/non-root probe established this cause. Restoring the tracked
source directory to 0755 made head b46087000004 visible; secret directories stayed 0700.
The transfer helper now normalizes only tracked code directories after extraction.

The next startup exposed a distinct test-helper bug: Node's file creation mode 0444
was masked to 0400 by umask 077, preventing non-root nginx from reading its synthetic
certificate. 358e027 explicitly applies chmod 0444 after writing both synthetic TLS
files, within the caller's private 0700 parent. The smoke harness now selects umask 077
after its explicit opt-in, so CI exercises the same regression. The full target
test passed with this restrictive umask; no runtime privilege or healthcheck was waived.
Independent source review found no actionable issue in the targeted correction.

The host's Node 22.22.1/system Python 3/httpx 0.28.1/pnpm 11.25.0 and locked Playwright
dependencies are test drivers. The application's actual runtimes remained the
selected image versions: Python 3.12.16, Node 24.22.1 and PostgreSQL 17.11.
The native web probe also confirmed zlib 1.4/Brotli 1.2.1/OpenSSL 3.5.9, full runtime
contract checks and absent Sharp/installers. API SQLite/installers remained absent.

## Actual target acceptance

All four multistage images, including the native frontend build, compiled on the
guest. The existing guarded command ran against these actual Docker images:

```bash
ALTVIA_ALLOW_CONTAINER_TEST=1 python3 scripts/container_smoke.py
```

The successful run completed on 2026-11-09, 17:03:25-17:05:18 America/Sao_Paulo
with warm build caches. This elapsed test time is not a performance/SLA claim.
Raw timestamps remain UTC in the private report. Exit status was 0; no SIGILL or
unsupported-instruction bypass was observed.

Passed: migrations and restricted runtime grants; non-root/read-only API/web/edge;
file-secret and builder-canary checks; TLS with exact domain SAN/CA validation;
Origin/CSRF/negative scope checks; login/logout/session persistence; database/API/web
recreation and database-loss readiness recovery; persisted team/roster browser
lifecycle; logical Bookworm-to-Alpine restore with Unicode/checksum/PK/FTS/constraints;
and graceful stop (API 0, native Next 143 without OOM). Six actual packaged-browser
captures were inspected: desktop/mobile light/dark login, admin account and archived
team with a persisted member. Existing browser/axe checks passed on this guest.

A separate short verification reused the same test stack and image IDs, read the
actual kernel cgroup files, and checked Docker configuration:

| Service | Memory MiB | CPU quota | PID limit |
| --- | --- | --- | --- |
| API | 512 | 1 | 128 |
| PostgreSQL | 512 | 1 | 128 |
| Web | 512 | 1 | 128 |
| Ingress | 64 | 0.5 | 64 |
| Migration job | 256 | 1 | 64 |

Read-only filesystems, dropped capabilities and no-new-privileges passed. Only
ingress bound a host application port, exactly 127.0.0.1; API/web/PostgreSQL had none.
The database network was internal. Kernel memory.max/cpu.max/pids.max matched the
declared bounds for running services. The migration job's stopped configuration
matched its bounds. Final Compose down left no running task containers and retained
the synthetic volumes. Docker/Compose remain installed; no public app was deployed.

## Actual-image security and immutable identity

The scanner consumed Docker archives of the exact four tested images, without
rebuilding or substituting CI images. All four full reports contained zero reported
vulnerabilities at every severity, without ignores or an unfixed filter. One fresh
Trivy DB was used: UpdatedAt=2026-11-09T19:03:15Z, SHA256
8c808b8e2b45da2b9849fab569412fd5b0a59455d3335ea0321f0179bcd86130.
The retained manifest binds image IDs, rootfs layers and report hashes. The image
IDs were also checked against the separate resource/native verification.

| Service | Actual tested image ID (sha256) |
| --- | --- |
| API | bc421aa7e481aa9db8a1a675f94cee279630c8d796d35803b9860d49e9c2e9be |
| PostgreSQL | 302b4b96a5b09bf17c3257cb339d84d4f0097caea612f3148e2d1c89bd73fab4 |
| Web | d77380932381cd8fcf41de1c1982e2ef83195056ad9f22939f1083355b311a67 |
| Ingress | 54cfc7402f66a4658305bee5b74bcefd17f0ee34b7817e6b56b69832afb4e04f |

Managed artifacts/target-vm/2026-11-09/final/ retains the evidence bundle, full raw
scan JSON/manifest, resource/native results, source/patch hashes, setup correction
and screenshots. Initial inventory, installation/simulations and the first failed
attempt remain separately retained. Earlier failed-attempt tags are diagnostic
artifacts; only the recorded successful image IDs have this acceptance evidence.

All four hosted gates also passed on 358e027:

- [API 42689738826](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42689738826): 244 tests (51.20s), lint/format/mypy/migrations/build.
- [Browser 42689738906](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42689738906): 21 tests (28.7s), types/build/contracts/audit.
- [Containers 42689738900](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42689738900): full isolated Compose proof under umask 077.
- [Images 42689739034](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42689739034): four-image security gate.

## Scope of closure

Q-01 is satisfied for these selected four-image Foundation artifacts and executed
native paths on the supplied VM. Repeat qualification for changed mandatory native
artifacts and future worker/Redis/storage/scanner components. Representative load,
IOPS, production backup/retention, operational RPO/RTO, external ingress trust and
production deployment remain separate gates. Account/role browser administration
and the remaining Foundation work are not completed by this infrastructure proof.
