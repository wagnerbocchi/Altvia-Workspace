# Attested incoming conversation evidence

ADR-0036 extends the accepted outbound base c47fd8a with explicitly owner-attested
incoming mail, scoped staff triage/promotion and one incoming/outgoing conversation.
Local implementation and independent source/UI reviews are complete at d6c3469.
Final publication36e4642 passed all five hosted gates. Remaining MVP,
actual final target qualification and production acceptance are separate gates.
No provider, real attestation/import or production deployment was performed.

## Contracts, source and independent review

| Boundary | Source | Executed evidence |
| --- | --- | --- |
| Owner cases, contextual routing, private origins and alias-aware collision | 711d4b0 | 420 affected tests in1083.10s, clean independent specification/quality review |
| Protected create/append/reopen, incoming records, references and receipt reads | 7c198c8 | 484 affected tests in1397.78s, clean independent specification/quality review |
| Scoped triage and combined browser conversation; detail historical receipt | f7f71e6/931c28c | 191 API in918.09s,154 full browser in10.2m; corrected visual candidate12 incoming scenarios in1.9m/all36 captures |
| Actual packaged incoming proof and retained legacy scenarios | e91bcc5 | 19 focused tests in17.79s, actual IMAPS/HTTPS/TLS SMTP/role/recreation proof |
| Complete Redis/worker privacy proof | d6c3469 | Saved12-failure RED,56 passing focused tests in18.74s and one actual packaged flow in152.0s |

These affected suites overlap; do not sum them as a full-suite total. The four
final visual corrections changed only the surface brief, scoped CSS, toolbar
class and capture assertions. All backend bytes remained unchanged. Independent
Impeccable finish review resolved the mobile grouping and honest FORM annotation;
the documentation review found no material gap and preserved the incumbent system.
Both original36 and corrected36 captures/metrics are retained.

The whole-increment architectural review covered c47fd8a..040931f and found no
application correctness, authorization, history or wire defect. Its one Important
finding was an acceptance-proof gap: incoming markers were absent from the old
Redis/child diagnostic checks and late phases. No application leak was observed.
The single d6c3469 fix wave preserves old assertions, supplies all marker classes,
and checks actual event completion and metadata/diagnostics after append, reopen,
collision and recreation. Independent scoped re-review marked R1 ADDRESSED,
with no new Critical/Important/Minor finding. Retained nonblocking Minors are dense
Task3 JSX and incumbent local browser-launch/color warnings; neither was hidden
or used to justify an unrelated refactor or unchanged-suite rerun.

## Actual synthetic integration and persistence

One new source/contact/case/ticket context is distinct from the old unclassified
fixture. Verified read-only IMAPS capture preserves exact raw bytes/UID namespace,
parser2 runs through the owner, and per-variant attestation publishes scoped text.
Current authenticated staff creates the ticket over HTTPS with protected replay.
Promotion creates no participant and sends nothing. A separate owner requester
attestation is required before the first real TLS SMTP reply.

The actual frozen first reply has the original incoming root in both In-Reply-To
and References, exact decoded public text and no persisted private-note canary.
Receiving/sending sources differ within the same queue. Later independently
attested messages append and explicitly reopen the closed ticket with a real
reviewed reason. The conversation versions are2/4/6/11. A promoted exact alias
preserves its original receipt; a raw collision on that alias yields collision/
version4 and a fixed warning without rewriting received text or history.

Runtime API and worker table AND column privileges, actual SELECT42501 and opted-in
owner-command refusals were checked. Viewer writes/replays403, hidden admin404,
private-note403, protocol428, changed-intent409 and new-key duplicate409 are real
responses. Current scope and authoritative single incoming reads guard receipts.

The corrected proof supplies nine incoming canaries to the actual SMTP child.
Late observations use12 metadata/log markers and scan actual decoded Redis/SQL
before and after the exact relevant nonempty event set is delivered AND processed
by identity_activity_v1. Main API/worker diagnostics are checked too:

| Phase | Delivered and processed events | Redis scans |
| --- | --- | --- |
| After append | 19 | 2 |
| After explicit reopen | 30 | 2 |
| After alias collision | 35 | 2 |
| After API/PostgreSQL recreation | 35 | 2 |

Collision/recreation preserve the same event-set SHA256
2f5fb92007017c8ef2a93bf6afd21eed3ac626a049484253a82feca8b882c1d5.
These are actual phase observations, not continuous recording of every transient
Redis value. Incoming root IDs remain required in their intended SMTP wire;
metadata/log exclusions do not globally forbid legitimate conversation headers.

API AND PostgreSQL containers were recreated with the same persisted volume.
Original receipts, raw/text hashes, received/recorded/accepted times and all old
frozen wire/attempt/status values remained unchanged. The three old SMTP modes
retain one DATA/attempt, accepted or uncertain state and no restart resend. Active
DATA SIGTERM and worker-child restart are real proofs; they do not substitute for
ordinary Compose PID1 shutdown. SMTP250 proves server acceptance, not inbox delivery.

## Local runtime identity and scope

Fresh API/owner/worker image:
aec1f4a213d7a4f7caf418593ed41d134dff38b11ba5c774bce43f187655ca48.
All77 actual image application/migration modules match source; no application
module was host-mounted or overwritten. The privacy fix reused that unchanged
image. PostgreSQL/ingress base images were explicitly reused and Redis used its
pinned upstream fixture image. The local standalone had no web service and used
disabled cgroups/a single bridge because of Windows Podman limitations. Production
Compose resource/network settings were preserved. Final hosted Docker must prove
the complete topology, resource caps, web image and ordinary shutdown.

No mandatory dependency, service or native tuning was added. No new image inherits
an older scan or x86-64-v1 qualification. Final actual target testing follows all
remaining MVP development under the user's updated validation cadence.

## Immutable evidence and failures retained

Private576-entry local/source archive,11489390 bytes:
C:/Users/wagne/.codex/state/evidence/attested-incoming-d6c3469/local-acceptance.zip.
SHA2568b3a4aa3ecb589499cbab0049d3ded8ec054dff686095693bf47f62171e6d843.
Every archived entry was reread/verified. It contains current source, prior
Task1/2/3 archives, both review ranges, reports, RED/GREEN, actual runtime metadata,
original and fixed manifests, failure history and the complete controller ledger.
TLS keys/credential files are excluded; log credential fields are redacted with
original and persisted hashes distinguished. No raw client workbook or production
log was committed. All175 final runtime-source and53 selected fix-evidence hashes
were independently matched; the old report's exact byte prefix is preserved.

Failed early standalone attempts were fixture/setup errors: missing synthetic
roles, Windows Podman tmpfs options, CRLF shell script, Windows command length and
queue-unique sender reuse. Attempts7/8 passed earlier scopes but only attempt9
proved both container recreations. The isolated Task3 reporter encoding failure
and Windows web-check child crash remain recorded with later passing checks.
Task4's earliest two RED commands were observed in the implementer transcript but
their raw files were not saved; that limitation remains explicit. R1's later RED/
GREEN has separately saved stdout/stderr/exit metadata, not reconstructed results.

Earlier publication14f334d passed all five hosted gates:994 API in726.95s,
154 browser in5.4m, packaged Docker, source17LOW/zero blockers/secrets and five
nonempty zero-vulnerability image inventories66/70/49/16/43. That success predates
Task4's new harness. Its11-entry archive SHA256 is
4d21fc4b9280c898e4bf9e3de7f8644245057180842c6d12e3c353adac856bc3.
## Final hosted acceptance

Publication36e46428872efafb0c0b32acb4b9902f1e2067de passed every exact hosted gate:

| Gate | Run | Actual result |
| --- | --- | --- |
| API | [43209674571](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43209674571) | 1040 passed in750.62s |
| Browser | [43209674496](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43209674496) | 154 passed in5.8m |
| Containers | [43209674579](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43209674579) | Actual complete Docker Compose/TLS/resource/network/non-root/secret/PID1/recreation and old/new incoming assertions passed |
| Source security | [43209674644](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43209674644) | 17LOW, zero blockers and secrets |
| Images | [43209674474](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43209674474) | Five nonempty inventories66/70/49/16/43, zero reported vulnerabilities/secrets |

All five full logs were inspected and retained after credential redaction, with
no actual failure/error/5xx/traceback/SIGILL signal. Pinned GitHub-action runtime
deprecations and isolated CI initdb local-trust warnings remain visible; no check
was disabled to remove them. All three downloaded artifact digests match GitHub
metadata. The packaged artifact has17 screenshots and the old delivery JSON.
The new incoming JSON was generated/asserted by the passing script but omitted
by its former artifact path; the workflow now explicitly retains that existing
file in subsequent runs. Full new local JSON/checkpoints are already preserved.

Private13-entry final hosted archive,2029151 bytes:
C:/Users/wagne/.codex/state/evidence/attested-incoming-d6c3469/ci-36e4642.zip,
SHA256cdf13f7606176e14a50186392e3aca0520569522cb88a54ca2a9961ef0e90390.
It includes all five logs, complete security reports/image identities, packaged
artifact, GitHub metadata, summary and the preserved earlier a0 browser failure.
Every archived entry was hash-verified. Image-security and packaged jobs build
separate image identities; no equality or target qualification is inferred.

Incoming conversation development/CI is accepted. Proceed to private files;
operational provider policy, integrated rollback and final target remain separate.

## Remaining gates and continuation

Runbook [attested-incoming.md](runbooks/attested-incoming.md) retains explicit trust,
original-intent recovery, collision preservation and promotion-aware rollback.
The Task1-only reader cannot represent promoted records. Schema1/2-compatible
worker/provisioning and version-aware owner tools remain necessary. Exercise an
actual compatible application rollback pair against promoted history during
integrated hardening; never delete data or blindly revert to an older image.

Q03/Q16 real provider/identity policy, Q09 retention and Q21 production mail sizing
remain external. Missing Message-ID cannot provide a fabricated reference; finite
ASCII routing grammar deliberately retains incompatible raw input in quarantine.
Attachments remain quarantined until the next private object-storage/fail-closed
scanning stage. No continuation prompt, production rollout, real import or target
connection is implied by this incremental completion.
