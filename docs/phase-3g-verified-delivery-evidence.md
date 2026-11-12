# Phase 3G - verified public delivery development acceptance

Date2026-11-12. Accepted runtime source:
`c47fd8a741aec73f592a2aa908957aa1bc09e64f`.
Development and controlled CI acceptance complete. Native incoming promotion,
private files, remaining MVP and consolidated actual-target qualification remain
open. No live provider, production identity attestation/send or rollout occurred.

## Behavior, ownership and commits

ADR-0035 and its implementation plan preceded code. Owner-selected sender
registration and ticket-bound requester attestation permit an authorized staff
member to review exact saved public text/From/To and deliberately queue it.
SQL freezes MIME/envelope/Message-ID, owns leases/retries/uncertainty and records
metadata events atomically. The actual worker uses verified implicit TLS or
mandatory STARTTLS. Positive final250 means server acceptance, never recipient
delivery. Ambiguous DATA is uncertain and never automatically resent.

Private notes remain structurally separate. Current queue/customer/action scope
and session/protocol checks precede replay. Current eligibility is checked before
DATA. Worker grants exclude notes, raw mail, MIME previews, evidence, credentials
and sender/attestation writes. Default delivery times use the database clock;
network duration uses a total60-second monotonic budget within the120-second
lease. Optional SMTP configuration is absent by default.

| Commit | Result |
| --- | --- |
| c67a43b /181469d | Selected delivery contract/plan |
| 5c6da0d | Persisted sender/requester/delivery and protected API |
| 1f9b191 | One formatting correction, unchanged runtime AST |
| 6ae7e4f | Bounded TLS SMTP and real worker integration |
| e58c786 | Exact send review, actual states and protected browser recovery |
| 51ad72a | Database/monotonic clock correction, regressions and operator runbook |
| c47fd8a | Packaged SMTP/privacy/restart/shutdown proof and negative controls |

Migration00022 is additive: sender/participant/thread/delivery identity, constraints,
immutable snapshot guards and narrow explicit runtime privileges. Downgrade
refuses expanded data/history. Rollback drains senders and retains compatible
schema/events/recovery tools; it never drops queued or uncertain messages.

## Executed local and independent checks

- Persistence:132 affected checks passed502.50s. Long-domain Message-ID bounds
  and ORM/migration drift were corrected with actual RED/GREEN and scoped review.
- SMTP/worker:104 affected checks passed271.17s, real PG/Redis/TLS, hostile replies,
  namespace/eligibility, duplicate wake-ups, restart, cancellation and SQL bounds.
- Browser: final142 passed7.5m, focused11 passed1.4m, web check/build/generated
  comparison and fixture lint/format passed. Actual TLS accepted/failed/uncertain,
  original HTTP replay, ownership recovery, real401/CSRF403 and receipt-read
  failures were covered. Keyboard/axe/390/1440/light/dark passed.
- Impeccable initially found misleading unsent wording after acknowledgement.
  Actual RED reproduced it. The qualified pending notice and nearby recovery
  passed independent scoring of12 fixed captures; disposition ship. Source
  review passed and documenter preserved the incumbent system.
- Fresh whole-increment review found R1 mixed clocks, R2 JSON-escaped multiline
  leak-proof false negatives and Minor R3 column-grant proof gaps. All three
  were fixed in one consolidated wave and independently scored ADDRESSED/PASS,
  with no remaining source finding. R2/R3 were proof deficiencies, not an observed
  application leak or actual broadened production grant.
- Final frozen affected201 passed706.44s, exit0, no warnings/skips/failures.
  All47 raw hashes and all9 scoped correction hashes matched before/after.
  Lint/format137, mypy46, Bandit9 LOW/zero blockers, wheel/sdist and embedded
  command compilation passed. Unchanged browser evidence was reused locally;
  exact final-source CI reran it.

## Exact-source hosted acceptance

All five runs use the accepted SHA above and completed successfully:

| Gate | Result | Run |
| --- | --- | --- |
| API |894 passed523.18s; migrations/check/lint/types/package passed |[43165934424](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43165934424) |
| Browser |142 passed5.6m; build/contracts/audit passed |[43165934276](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43165934276) |
| Packaged Docker |Full existing smoke plus actual new SMTP proof passed |[43165934277](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43165934277) |
| Source security |9 LOW,0 blocking,0 secrets |[43165934427](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43165934427) |
| Image security |5 nonempty inventories,0 reported vulnerabilities |[43165934267](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43165934267) |

Root retained complete logs/jobs/artifacts, verified all42 raw hashes, every image
report hash and nonempty package inventory. The nine LOW are recorded internal
assert/type invariants and the pre-existing CLI inventory, not zero findings.
The pinned artifact/pnpm actions emitted Node20 deprecation annotations while
being forced onto Node24; jobs passed. This is CI action metadata, not the
application runtime or a failed native-CPU check.

## Actual packaged outcomes

Three independent tickets each contain a persisted private note and immutable
public draft. HTTPS201 queue/200 original replay yields one delivery/attempt/DATA.
Owner setup runs in migrate; each probe uses the actual worker service image,
worker-only secrets/private networks/nonroot/resource bounds and a real
`python -m altvia.worker run` child with a loopback verified-TLS relay.

| Synthetic result | Persisted state | DATA/final250 | Initial SIGTERM exit0 | Restart SIGTERM exit0 |
| --- | --- | --- | --- | --- |
| Positive final250 |accepted |1/1 |0.464s |1.316s |
| Lost final reply |uncertain |1/0 |2.118s |1.768s |
| Held final reply; SIGTERM during active DATA |uncertain |1/0 |1.116s |1.467s |

Fresh restart heartbeats precede12-second no-second-DATA observations. Exact
wire/envelope/decoded text/Message-ID, single-part MIME, effective table AND
column grants, private/public canaries, Redis/events/audit/diagnostic exclusion
and HTTPS projections passed. Frozen state/hashes survived API/PostgreSQL
recreation. Historical eight-event note and separate unsent-draft proofs passed.
Timing above measures the real worker-main child under packaged restrictions;
the ordinary Compose worker shutdown is independently checked by the base smoke.

## Images, CPU and evidence archive

No mandatory dependency/service/native tuning or lockfile changed. Security job
image identities below were built from the same pinned source independently of
the packaged job; this is not a claim those two jobs produced identical IDs.

| Image | Scanned image ID | Packages/findings |
| --- | --- | --- |
| API |sha256:365d3a89b4ca67ff651bb278732658bbe317de412838bb0a459c4cb62b3863a0 |66/0 |
| PostgreSQL |sha256:e4a20fd9a59681ac2d32f0fe1e40e1dc468b8ca9b3ed66dc2f1dbb88778f9b1c |49/0 |
| Ingress |sha256:add53750004f57a2e748d4a8bc230b10193762b1df2a11ed37b72108647c0193 |70/0 |
| Web |sha256:eac910d385629ca392a7f89ceea35d57b7b4f417ec1a30cf4d5d87b52c27482b |43/0 |
| Redis |sha256:ec155ecab2c88cf60b9561be6bcd2edca5012782faffd7ea282442f733d60681 |16/0 |

Scanner DB SHA256719de0cb21fdbc1bf3cb433f7ea57f68910c9d1771f8334026035f5fb11ff325.
Restrictions x86-64-v1 and prohibited search/AI dependencies remain mandatory.
No target SSH/CPU qualification was run; these changed artifacts inherit no older
VM qualification. Final actual-target testing/scans follow remaining development.

Immutable sanitized archive:
`C:/Users/wagne/.codex/state/evidence/verified-public-mail-c47fd8a/acceptance.zip`.
252 entries,11055038 bytes, SHA256
`8a7308d20b5e6622b9b9ea7d64fd6ec810190a634df048ddeaa1c972fa75fca3`.
ZIP integrity and every archived entry hash passed.95 ephemeral CI credential
occurrences were redacted from log copies. Manifest retains original/archived
hashes and distinguishes upstream raw inventory. No account/key/session/env or
private command workspace was allowlisted. Reports/ledger inside retain their
historical pending/failure states; final run artifacts and this record establish
acceptance. Raw originals remain private for audit.

## Preserved failures, decisions and remaining gates

The first local full container attempt failed with Podman EOF during web build,
before stack startup; it never proved SMTP. Full hosted Docker later passed.
The first correction suite had195 passing/3 failing tests because disposable
roles lacked schema USAGE after provisioning revoked PUBLIC access; explicit
USAGE only for those temporary roles fixed the test precondition. Transport
clock and canary/column checks have retained original RED and final GREEN logs.
No interrupted, pre-fix or failing run is presented as success.

Engineering rulings: one sender per queue/active attested requester per ticket
bounds recipient selection; larger/multiple-recipient flows need a later contract.
Bounded daemon DNS callers may finish after a caller deadline; no more than2
can remain. Positive250 closes directly without QUIT so cleanup cannot undo
acceptance. Worker-only SQL timeouts are5s/3s. Historical clock-skewed immutable
rows remain untouched: impossible evidence bounds require separate review and
stay uncertain, never invented acceptance times or another delivery as a bypass.
These costs are recorded in the runbook and archived ledger.

Q03/Q16 actual provider/identity policy, production authorization and final
integrated target acceptance remain separate. Next: ADR-0036 attested incoming
triage/correlation/conversation, then private files, N:N links, automation/unified
work, SLA, analytics, dry-run/import capability and integrated hardening. Do not
stop this authorized completion sequence after the outbound increment.
