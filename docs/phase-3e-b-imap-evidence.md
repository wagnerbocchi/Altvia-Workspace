# Phase 3E-b read-only IMAPS development evidence

Updated 2026-11-11. Accepted development source
426d4b826db32c3f7fa6141bbea17da11030dc65 passed all five hosted gates and actual
packaged proof. Phase 3, full native email/MVP and consolidated actual-target
qualification remain open.

## Delivered behavior and decisions

Contracts add42e6 preceded implementation 45a72e1 under ADR-0031. The finite
owner-only collector uses verified implicit TLS and read-only INBOX/EXAMINE/
BODY.PEEK to preserve opaque mail in ADR-0030 quarantine. It performs no flag,
Seen, deletion/EXPUNGE, MIME display, identity grant, ticket promotion or SMTP.
Only controlled synthetic loopback TLS was used; no real provider was contacted.

Namespace binding follows authenticated selection and hashes canonical host/port/
exact username/INBOX without passwords. Failed first certificate/login cannot
bind it. Password rotation preserves namespace; endpoint/account changes cannot
silently remap a source. A 120-second lease and token/expiry checks fence every
checkpoint/reset/capture while network operations hold no DB transaction.

One poll scans at most 1000 UID positions and fetches 25 messages within observed
UIDNEXT-1. Each durable capture/checkpoint/source version/audit/outbox commits
atomically. Failure preserves prior commits without skipping the failed UID.
Empty gaps advance only after an epoch-checked SEARCH. UIDVALIDITY changes reset
the cursor with audit while retaining old receipts; content equality is not proof
of duplication across epochs. Late callers cannot rewind or release newer leases.

Raw literals remain 2 MiB; lines 16384 bytes. Aggregate control responses allow 65536
bytes/no literals; FETCH allows one literal and 2097152+32768 response bytes before
imaplib accumulation. Wire reads/writes share 90 seconds/socket operations 10 seconds.
Platform DNS resolution has its own behavior; expired leases still fence writes.
Current session epoch is checked after SEARCH, including empty, and after FETCH.
Non-literal metadata also has a 65536-byte total poll budget, bounding other
unsolicited response classes retained across multiple commands.

Five design decisions and costs:

1. Finite read-only INBOX polling precedes scheduling/OAuth/folder routing. Later
   provider configuration must extend the collector without reinterpreting receipts.
2. Bind authenticated host/port/exact account/INBOX, excluding rotated passwords.
   Legitimate endpoint migration requires a reviewed new source/resync.
3. Lease/fence remote work instead of holding DB locks. Crash recovery may wait 120s.
4. Fixed raw/line/aggregate/window/batch/time bounds limit resource use. Production
   provider sizing requires Q-21 review rather than a guessed throughput promise.
5. Preserve separate UIDVALIDITY epochs and only proven gaps. Later verified
   promotion must reconcile them without silently deleting captured mail.

Migration b46087000018 adds private mailbox_poll_states with source RESTRICT FK,
consistent nullable initialization, uint32 cursor checks, paired leases and
immutable namespace/forward-progress trigger. Both runtime roles have no table
privileges. Strict checkpoint events contain source/UID/reason metadata only and
are acknowledged without shared activity. Old intake envelopes remain compatible.
Downgrade refuses poll state or checkpoint history; rollback retains expansion
and compatible private event consumption. No dependency, binary pin or ISA changed.

## Actual local checks and review corrections

Missing-module collection RED preceded implementation. A real SQL half-bound
namespace test failed before explicit non-null initialized-state guards fixed
PostgreSQL CHECK/NULL acceptance. First actual TLS/PostgreSQL: 20 passed in 81.09s;
expanded pre-review: 93 passed in 199.19s. These are historical checkpoints, not proof
that the later review findings were absent.

The independent fresh whole-increment reviewer found two Important defects:

- I1: per-literal/line bounds still let imaplib accumulate multiple valid-size
  unsolicited literals before returning a response. Actual TLS FETCH/SEARCH
  regressions failed before cumulative byte/literal budgets were added to the
  wire reader, before another body could be returned for buffering.
- I2: an empty SEARCH carrying a changed UIDVALIDITY could advance the old
  epoch's scan checkpoint. The empty-result regression observed this before
  centralized SEARCH/FETCH epoch validation stopped it.

One correction pass observed targeted 3 RED/1 passing, then 4 GREEN in 15.61s.
The complete affected suite afterward passed 97 in 212.24s, including real TLS,
PostgreSQL, CLI, intake compatibility, activity and runtime privilege regressions.
No Critical, separate Minor or declined judgment remains. No second review was
substituted for executed regression/full-suite proof.

Executed local suite through the task's isolated runner:
python .superpowers/sdd/2026-11-11-readonly-imap-poll/run-local.py --api -q
apps/api/tests/test_imap_poll.py apps/api/tests/test_mail_intake.py
apps/api/tests/test_mail_intake_cli.py apps/api/tests/test_activity.py
apps/api/tests/test_runtime_provision.py. Complete sanitized logs are retained.
Ruff/format across 112 files, mypy across 38 files, wheel/sdist and unchanged OpenAPI/TypeScript export passed.
Local SAST retains four existing LOW findings and zero blockers. No frontend,
asset/token or public API surface changed. Full unchanged browser/API verification
uses exact-source hosted gates rather than duplicating unmodified local runs.

## Hosted acceptance and remaining scope

All five exact-source gates succeeded on 426d4b8. Complete run logs, jobs, log ZIPs
and artifacts were collected and inspected. ZIP integrity, every image report
hash, nonempty inventories and zero findings at every image severity were checked.
The actual packaged command against controlled TLS passed in an owner-only
container: opaque byte capture/resume, PostgreSQL recreation, durable released
cursor state and API/worker privilege denial all passed.

| Gate | Actual result | Run |
| --- | --- | --- |
| API checks | 682 passed, 2 warnings, 411.29s; lint/types/generated contracts/build passed | [43121515542](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43121515542) |
| Browser checks | 116 passed in 3.9m | [43121515455](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43121515455) |
| Container checks | Actual TLS/read-only poll, capture/resume, recreated DB cursor and runtime denial passed; existing full packaged proof passed | [43121515447](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43121515447) |
| Source security | Four existing LOW Bandit findings, zero blockers, zero detected secrets | [43121515486](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43121515486) |
| Service image security | Eight report tests passed; five nonempty inventories, zero vulnerabilities at all severities | [43121515443](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43121515443) |

The two Pydantic UnsupportedFieldAttributeWarning advisories concern aliases
limit in test_queue_access_concurrent_reviewed_writes_one_wins and body in
test_queue_atomic_failure_overflow_and_competing_versions. They are retained,
not suppressed or described as failures. Full logs contain deliberate negative
SQL checks: denied private-table privileges, invalid constraints/foreign keys,
immutable namespace/cursors, guarded downgrade and injected event rollback.
The pre-existing work-parent concurrency test's deliberately induced database
deadlock also remains visible; no Python traceback, failed step or workflow error
occurred. No advisory or SQL negative is treated as production acceptance.

Exact security-scanned images (API build is separate from the container job's
build; do not infer identical IDs or native qualification):

| Image | Packages | Image ID |
| --- | ---: | --- |
| API | 66 | sha256:976d036583b18b2d78853a813ed2c60bea9a926fc3b905937f81293912a710a9 |
| PostgreSQL | 49 | sha256:4f97bb221ef159f0e49099406c20a71b0c184661ee6e5b17746d5bbec66a03bc |
| Ingress | 70 | sha256:0b3796e1c5291283e5c407b08021b59b07edb3a7ab051be7681b2094b9fbd5e1 |
| Web | 43 | sha256:9ca02de44924267d51ccb89817ac0452f1a79d112429638db36234c4386d7b76 |
| Redis | 16 | sha256:dd4f175a9bdbdf85012c763ed9006bf95e3c398027bb68ec29e3c36544ca1fc5 |

Trivy database SHA-256:
400e7b60cf78b5ceba57f9ed02cd98603dd89b57516f648f829a6f6a42843be4.

Sanitized immutable local archive: phase-3e-b-imaps-426d4b8/acceptance.zip under
the workstation's Codex state evidence directory. It preserves reviewed source,
independent review, RED/GREEN/local logs and complete original/intermediate/final
hosted evidence. All 201 entries passed ZIP and entry hash verification; archive
size 7740521 bytes; SHA-256
b1fea45b6b6e8851e82624a4a304e3cfe8f88f537a107f04d8a78090156ba8fd.
The receipt is outside the archive to avoid self-reference. Scratch is retained;
no cleanup retry or external evidence publication is part of this closure.

First candidate 45a72e1 passed packaged TLS/checkpoint/restart/runtime-denial,
116 browser tests in 3.8 minutes and both security gates. Its API run had 650
passed, one Pydantic queue_id alias warning in a concurrent test and 31 certificate
fixture setup errors. The API-only job has no frontend packages; its Node-based
selfsigned test issuer therefore could not resolve its dependency. A clean
API-only dependency reproduction confirmed the failure. The backend fixture now
uses installed system OpenSSL, or Git for Windows OpenSSL, with explicit synthetic
configuration. No frontend dependency was added to API CI or production. All 35
actual IMAPS cases passed in 130.35 seconds after this test-only correction,
committed in 18788f9. The complete failed run/warning remains preserved; final
all-gate acceptance still requires the corrected exact-source execution.
Intermediate 18788f9 then passed all five gates, including 681 API tests in
465.89 seconds with one retained advisory and 116 browser tests in 3.9 minutes.
A final regression refined the same I1 fix across command boundaries: imaplib
could retain other untagged metadata classes throughout a batch. The controlled
header-burst test observed RED before a total non-literal metadata budget was
added. All 36 actual IMAPS cases then passed in 136.21 seconds. Source 426d4b8
includes this refinement; the final complete API execution passed 682 tests.

MIME parsing/sanitization, verified sender/thread correlation, authorized promotion,
public replies/SMTP and scanned private attachments retain subsequent contracts.
Provider/identity/retention/size policy remains Q-03/Q-09/Q-16/Q-21. Later automation,
SLA/analytics/import and final hardening remain open. No production deployment,
real import, live mailbox use or Zammad retirement is implied. Actual x86-64-v1
qualification follows remaining MVP development under the user's cadence.
