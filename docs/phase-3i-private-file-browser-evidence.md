# Phase 3I private-file browser evidence

Updated 2026-11-12. Task 4 under ADR-0037 extends the accepted Twenty-inspired
Operate interface. Implementation c5c668c and reviewed corrections 039a631 are
locally verified. Exact-final hosted gates are pending. This is not final MVP,
production, signed-scanner end-to-end or target-CPU acceptance.

## Behavior and ownership

Native file selection and real binary uploads now serve public responses,
private ticket notes and work comments. Current scoped metadata shows quarantine,
scanning, ready, rejected and failed states. Ready files can be downloaded through
the authenticated API and explicitly selected in order for immutable content.
Public email review displays the saved files and sends their exact ordered IDs.

An uncertain upload retains its original File, filename, digest, purpose, key and
reviewed parent version. Original protected replay plus current single metadata
must confirm it; refreshing a list cannot acknowledge the write. Downloads and
asynchronous completion remain fenced to the current session. File readers and
requests abort on disposal; local Blob URLs are revoked. No persistent browser
file storage or public object URL is introduced.

Existing generated contracts, session/query owners and protected-write helpers
remain authoritative. Current parent/action/client/note rights govern every path;
files grant no access. Upload does not advance the parent version, while scan
retry uses the file version. No migration, new runtime dependency or ISA change
is introduced by this browser increment.

## Executed local proof

| Scope | Actual result |
| --- | --- |
| Web lint, strict types and optimized build | Passed on final corrected source |
| OpenAPI and generated TypeScript | Repeated generation unchanged |
| Python fixture lint/format | Passed |
| Affected conversation/work/file browser regression | 53 passed, no skips |
| Full browser baseline at c5c668c | 175 passed, no failures or skips, 12.5 minutes |
| Final 039a631 correction subset | 9 browser cases passed, no skips, 47.5 seconds |
| Committed child-output protection | 3 actual-child/chunk/bounded-output tests passed |
| Source/evidence bindings | 18 final files match scoped inputs; before/after maps equal |

Commands include `pnpm web:check`, `pnpm web:build`,
`uv run ruff check scripts`, `uv run ruff format --check scripts`,
`uv run python scripts/export_openapi.py`, `pnpm --filter @altvia/web generate:api`
and `node --test apps/web/scripts/test-output.test.mjs`.
The guarded browser harness is `uv run node apps/web/scripts/browser-test.mjs`;
the ignored local wrapper supplies fresh private PostgreSQL/Redis/real S3 and
records commands, source/output hashes, status and cleanup.

Coverage includes actual TLS S3 bytes, protected replay and failed metadata reads,
authorization loss/restoration, private-note denial, immutable ordered content,
MIME2 SMTP bytes/order, failed-scan retry, session-ending upload/download disposal,
work-comment conflict recovery, keyboard, axe, both themes and mobile overflow.
The full 175 result belongs to c5; the later copy/test-output correction has its
own 9-case proof and is not relabeled as a full 039 run.

The scanner fixture exercises real ClamClient framing, S3 spooling, claims,
leases and persisted attempts against a controlled socket. Eight actual protocol
failures use an explicit disposable scheduling fault to reach terminal failure.
No manual clean flag or mocked HTTP status endpoint is used. This is browser
integration/fault proof, not signed production-profile ClamAV acceptance.
Task 5 retains that integrated gate on sufficiently provisioned hosted Docker.
The local 2048 MiB Podman VM was not resized or restarted for this work.

## Failures and independent review

Retained failures include missing native selection (RED), a Windows AF_UNIX
fixture limitation, metadata interception races and a session-test trigger that
did not request real authentication revalidation. Linux fixture execution,
explicit failed-read observation and an actual 401 boundary corrected those causes.
The affected 53 run exposed a local S3 healthcheck DNS alias omission despite
functional TLS requests; corrected full runs record native healthy storage.

The first full run was 174 passed/1 failed: an existing comment assertion matched
both retained form text and committed list before replay acknowledgement. It now
awaits the cleared composer and checks scoped saved content. Its fresh full rerun
passed 175. Earlier failures remain preserved.

Independent source review found a hosted logging gap: Playwright failure output
can contain temporary synthetic Cookie/CSRF values. The committed runner now
protects both child streams before forwarding, preserving ordinary bytes, exit
status and diagnostics. Split chunks, EOF, ANSI, invalid bytes and a 4 MiB line have
actual failure-process proof. Oversized lines receive an explicit bounded omission.
No production compromise was demonstrated. Historical header-bearing originals
remain restricted outside Git and the sanitized evidence archive.

Source re-review approved I1/P2 and M1 as addressed with no new findings. Existing
standalone-start/color notices remain nonblocking runner observations for later
cleanup. Impeccable inspected 64 state captures and requested capability-accurate
read-only instructions. Eight recaptures resolved that finding; its final `ship`
verdict covers the scored fix alongside the retained original full review.

## Evidence and remaining gates

The private implementer manifest verifies 264 sanitized files, SHA256
`5ef24939afde94f30a9e48511d5684bf3d5053a6321d77e8390a356e447f5a6c`.
Root independently verified all entries, 64 initial capture hashes and 18 final
source bindings. A bounded check of 124 available synthetic credential values
found zero matches in indexed text artifacts; this is not universal secret proof.
Mutable log aliases and restricted/private originals are excluded. Original and
sanitized stream hashes remain distinct.

Remaining: exact-final hosted CI/security/image gates; Task 5 actual packaged files
with signed/current ClamAV, recreation/privacy and matching DB/object restore;
separate incoming-MIME attachment ownership; remaining MVP stages; consolidated
actual x86-64-v1 qualification. No production rollout, real import, retention
deletion or Zammad retirement is implied.
