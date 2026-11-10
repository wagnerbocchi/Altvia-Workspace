# Phase 2F project member administration evidence

Status: Phase 2F implemented, reviewed and qualified on 2026-11-10.
This report does not close Phase 2 or authorize production deployment.

## Scope and implementation

ADR-0023 and plan docs/plans/2026-11-10-project-members.md preceded product code
in 32e5a78. Persisted HTTP membership writes and generated contracts are 619f94c;
deterministic revocation/roster race evidence is ce15847. Browser/packaged delivery
is d55a4b2; host-only smoke expectation correction is b179695. Managers add an existing
account by known email, change its direct role and remove direct access. No global
directory or customer ceiling grant is introduced. The browser confirms every
known-email grant before submission and retains the original uncertain intent.

Shared domain ownership keeps membership/binding changes, session invalidation,
Project version and redacted audit/outbox in one transaction. Identity write lock
precedes authentication. Reads/writes/replays retain current customer/project ACL.
Member pages verify their Project version unchanged around the roster query. The
browser never combines an old roster with a fresh parent's write version.

No new migration, real data import, dependency or ISA requirement is added. Changed
application images were rebuilt and executed on the actual target, as listed below.
Rollback preserves all existing data/events and the compatible CLI; no downgrade
or volume deletion is needed. No production deployment or security/SSH change.

## Local evidence

- `python .superpowers/phase1-tests/run.py --api -q`: final 480 passed in 709.17s.
  Earlier full 476 passed in 691.38s; affected project/CLI/member suite then 40
  passed in 97.17s after the roster-version extension.
- Missing membership routes: 13 new tests failed 405 before implementation.
- Version-field regression failed KeyError before implementation.
- Distinct-session account/customer revocation tests observed actual advisory-lock
  waiters before authentication, then 401/no access/version/event effect. Both
  failed when serialization was temporarily removed. Roster interleaving failed
  200-versus-409 with its guard removed. Restored sources: 3 passed in 10.14s.
- Browser initial six workflows passed; full 66 passed in 3.5m. Mobile readable-width
  regression failed before reusing the existing responsive member-row pattern.
- Source review identified the add-form self-demotion confirmation gap and the
  inadequate concurrent-request proof. Explicit confirmation test failed before
  correction; all 7 member browser tests passed in 17.3s afterward. After final
  spacing correction, members plus existing task workflows passed all 11 in 35.1s.
  No critical/minor source findings or declined behaviors remained.
- Ruff/format/mypy, generated OpenAPI/TypeScript, web check/build, native dependency
  guard and dependency audit passed. No new dependency or Sharp is present.
- Sixteen real desktop/mobile/light/dark captures cover directory, reviewed grant,
  role editing and removal. They have zero axe violations and no horizontal
  overflow; mobile member identity width is tested. Impeccable found one material
  confirmation-spacing defect. Existing 24px action spacing fixed it; the reviewer
  scored that fix resolved across all 12 affected captures and validated all 16.
  This ship verdict covers that fix list, not a new whole-surface review. The fresh
  documenter checked and preserved DESIGN.md/sidecar; no drift repair or raster.

One later complete Windows run passed 66/67: the existing real task lifecycle
test timed out at 30 seconds with the connection-error screen. Complete run logs
and failure context were inspected; the cause is not established. Its focused
reexecution above, complete hosted 67/67 and actual packaged target workflow pass.
Do not describe the Windows intermittency or the older axe failure as fixed.

## Hosted gates

All following runs passed on exact b179695ca90c22386de9073556beb2631e6c6994.
Complete logs and metadata/artifacts are preserved; no workflow gate was relaxed.

| Gate | Exact run | Result |
| --- | --- | --- |
| API | https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42875671581 | 480 passed in 274.88s, format/lint/mypy/migrations/build |
| Browser | https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42875671462 | 67 passed in 1.8m, types/lint/build/contracts/audit/native guard |
| Containers | https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42875671270 | Full packaged HTTPS/browser/ACL/member/session/replay/recovery proof |
| Service images | https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42875671333 | Blocking image gate passed, full severity metadata retained |
| Source | https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42875673347 | Zero detected secrets/blocking findings; four existing LOW SAST metadata findings retained |

## Actual x86-64-v1 target

Source b179695ca90c22386de9073556beb2631e6c6994 was uploaded as an immutable Git
archive, SHA256 3cfa400d11dad52b14309f25e624f6358ddcd983191a0ef8fe589d112198736b.
Source directory: /root/altvia-members-b179695-182915/source.
Synthetic Compose project: altvia-test-7075ce6224. Smoke ran 18:29:31-18:32:42 UTC,
exit 0. No production configuration, SSH/security setting or real data was changed.

The first d55a4b2 smoke failed at an old account-version assertion: the new grant,
role change and removal correctly added three session invalidations, moving 12 to
15. Test-only b179695 corrected that expected value, preserving product/runtime
inputs. The failed evidence and task volumes remain available; the corrected
immutable source then ran the complete smoke, not only the failed assertion.

Actual native proof includes HTTP grant/no-op/role/removal/replay, target session
401, cross-client ceiling denial, unchanged replay effect and persisted final
Project version 4 after API/PostgreSQL recreation. The actual packaged browser
also added/changed/removed an account and verified persistence, axe and readable
mobile identity. Six project.access_changed events were delivered/projected once.
Worker shutdown under a blackholed Redis exited 0 in 7.608181s and recovered all
27 events. Native Portuguese FTS/GIN over 6000 rolled-back rows and logical
Bookworm-to-Alpine restore/integrity proof passed.

All 38 resource/native commands passed. Actual cgroup memory/CPU/PID controls,
non-root/read-only/drop-capability settings, private database/queue networks and
loopback-only ingress were verified. Guest flags omit SSSE3/SSE4.1/SSE4.2/AVX/AVX2/
FMA/BMI2. The five native-tested images below match the scanned IDs and rootfs
layers exactly; reports include nonempty inventories and zero reported
vulnerabilities at this scan snapshot. Worker/migrator reuse the API image.

| Image | Exact native-tested image ID | Packages | Vulnerabilities |
| --- | --- | --- | --- |
| API | sha256:6837db2467d8012613c57232a6f4cf14647fd95e9f9e29b926a33761dfddc8f9 | 66 | 0 |
| PostgreSQL | sha256:72abb47c7c51a3944829133e7cdf6917fc82e83e4b3d09584a54f1a65ab0661c | 49 | 0 |
| Web | sha256:e9e1936ba3441e345adda44fe697176505c8bcd8d28b34c601610ee96d40d996 | 43 | 0 |
| Ingress | sha256:d0a80db867aaf07da7855097a13e8da083892f608b4fe57b3451c5bdbae63834 | 70 | 0 |
| Redis | sha256:f7f4c08c98b4db676f91d3adec334f79470e9a17cf3619a57e3bcadc52033f1e | 16 | 0 |

Task containers are stopped; volumes are preserved. Agent-backed strict SSH stages
closed their authenticated connections. The separate remote development checkout
was verified clean and fast-forwarded to qualified b179695.

## Preserved evidence

Private durable artifact: phase-2f-members-b179695/acceptance.zip, 130 files,
4646640 bytes. SHA256 6fc86b4b7acedc3fcf588883dcc821dbf9ea2550d82806df386f3fc471eedc47.
It retains per-file hashes, complete native/image/resource/search/worker/member
reports, hosted logs/artifacts, local failures and passes, source-review/mutation
and Impeccable records and actual captures. Source workbooks, secrets, private keys,
runtime secret configuration and raw production data are excluded from Git.

## Decisions and practical limits

- Known-email transactional addition avoids a new global account lookup surface;
  a mistaken approved address needs an explicit audited correction.
- Stable version around the roster read avoids project/session lock inversion;
  concurrent changes may require manual refresh.
- Every known-email grant receives explicit review, including Unicode self-targets;
  ordinary additions incur one extra confirmation.

Basic project milestones and external work participants remain subsequent Phase 2
slices. Advanced dependency planning remains FR-016/P2 backlog. Real account/client
provisioning, retention/capacity and production acceptance remain separate gates.
