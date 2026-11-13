# Phase 3I combined packaged file proof

Updated 2026-11-13. Task5 implementation ef6b9f9 is source-reviewed and locally
checked. The combined hosted positive run is PENDING. This document does not
claim successful packaged file restoration, final MVP or target-CPU acceptance.

## Implemented proof and scope

The opt-in `scripts/container_smoke.py --files` extends the existing packaged
owner with actual API/web/worker, private TLS S3 and signed-current ClamAV. Its
new synthetic ticket and files reuse the unchanged existing sender account;
original SMTP/incoming fixtures, frozen wires, clocks and shutdown assertions
remain. No application schema, runtime dependency or architecture changed.

The proof exercises native browser upload, clean download, EICAR rejection,
private-note linking and explicitly reviewed public MIME2 delivery. Pausing the
actual scanner produces eight persisted timeout attempts; only the synthetic
file's due timestamp is accelerated. Protected retry must then obtain an actual
clean result. No successful scan, attempt count or ready state is fabricated.

Current API/worker credentials face table, column and actual-query denials.
Decoded SQL/Redis and child/main/service diagnostics are checked after delivered
and processed events and after service recreation. Intended downloaded/public
MIME bytes are permitted only in those intended channels.

A matching logical snapshot quiesces synthetic writers and exports every
DB-referenced object with length/hash verification. Restore uses separate
project-scoped DB/object volumes, compares object identities, immutable links and
old/new frozen wires, then exercises current public/private HTTP authorization.
Dumps, object exports, sessions and credential files remain private and are not
uploaded. No deletion/prune or production retention policy is introduced.

## Observed local results

| Scope | Actual result |
| --- | --- |
| Affected storage/transport/SMTP/proof controls | 123 passed, 20 explicit skips, 42.81 seconds |
| Final checker and sender coexistence scope | 26 passed, no skips, 21.90 seconds |
| Child-output protection | 3 passed |
| Ruff, formatting, JavaScript syntax and diff whitespace | Passed |
| Independent source review | Approved; zero Critical/Important, two Minor findings |

The 20 skips are three native ClamAV image opt-ins and 17 POSIX-socket checks on
Windows. They are not counted as executed. Final26 includes five actual
PostgreSQL column-only grant drift probes and a sender-coexistence regression
that preserves an old MIME1 wire, message identifier and timestamp. The earlier
123-pass result applies to unchanged surrounding tests, not a full final rerun.

Root independently verified all six committed source files against final frozen
inputs, three unchanged before/after manifests and six sanitized stream hashes.
The local Podman VM remains 2048 MiB and was neither resized nor restarted.
Actual signed combined execution requires the provisioned hosted Docker runner.

## Review observations and remaining gates

Two nonblocking source observations are retained for whole-increment review:
include the timeout file's name in diagnostic canaries, and broaden the hosted
source inventory beyond its current subset of build inputs. The full Git source
archive and broader local frozen maps remain distinct from that subset.

Required next gate:

```sh
ALTVIA_ALLOW_CONTAINER_TEST=1 uv run python scripts/container_smoke.py --files
```

The private-file-runtime CI job now executes that command after the separate
signed-current scanner/update proof. It explicitly uploads bounded file proof,
command/source manifests and storage/scanner inventories; private dump/object
and diagnostic contents are excluded. All five exact-source workflows and their
complete logs/artifacts still require verification before acceptance.

Whole-increment review, a matching logical restore's actual positive result,
separate incoming-MIME attachments and remaining MVP development remain open.
Encrypted backup and compatible image rollback belong to integrated hardening.
Final actual x86-64-v1 qualification follows development. No production rollout,
real import or Zammad retirement is authorized by this evidence.

## First hosted run and transport correction

At source 56fc6d7, API checks passed 1224 cases with 3 explicit native console skips
and 3 Pydantic field-metadata warnings in existing threaded queue tests. Browser
checks passed 175, source/image security passed and the historical packaged job
passed. The separate actual signed-current scanner infrastructure proof also
passed. The new combined child failed, so Task5 is NOT positively accepted.

The retained parent traceback identifies the browser child, but its fixed generic
stderr has no historical phase. Raw locator errors were correctly excluded from
artifacts; this left a diagnostic gap. Do not assign a retrospective phase that
was never recorded. Complete logs and digest-verified ZIPs remain preserved in
`C:/Users/wagne/.codex/state/evidence/private-file-task5-ef6b9f9/ci-56fc6d7-failed.zip`:
24 entries, 1862635 bytes, CRC passed, SHA256
`58828a9f1ec37e2258a3f352ef7eca04aa1377d483f1dd5678730f492053203e`.

A focused actual HTTPS differential reproduced a concrete transport defect:
SPKI-pinned Chromium with the configured hostname mapping succeeds, while the
separate Node APIRequestContext refuses that endpoint. Correction b6e6095 reuses
the existing packaged browser-fetch pattern for the two read probes. Assertions
for actual clean/rejected states, bytes, private linking and public review remain.
The generic transport probe does not emulate a file or successful scanner.

The fix also adds a bounded failure artifact with fixed phase/state enums and
numeric counters. The parent rejects unknown fields, invalid types/enums,
duplicate keys, invalid UTF8 and oversized/recursive JSON. Raw exception text,
identifiers, URLs, names, note/file contents and credentials are excluded; the
original nonzero outcome remains. Actual failed-child tests verify this boundary.

Final focused checks passed 18 Python controls, 2 live HTTPS/projection tests and 3
existing child-output tests. Root verified six final source bindings, unchanged
before/after maps and all six recorded raw streams. The first differential's
transcript observation is labeled separately from the later captured raw channels.
Independent scoped review approved both the diagnostic boundary and transport
correction, with no new Critical/Important findings. A new combined hosted run
remains required before claiming actual file restoration success. Earlier failed evidence
stays failed. No product runtime or target operation was changed.
