# Phase 3D private ticket note development evidence

Updated 2026-11-11. Final acceptance candidate is
fb83c0364606d8e90a8f488f67bcd848e6cbacda. Phase 3D development acceptance is complete:
all five exact-source hosted gates passed, with local full suites also passing.
Phase 3, the full MVP and consolidated target qualification remain open under the
user's development-first cadence. No production deployment or real import occurred.

## Delivered behavior and architectural decisions

Contracts 4a5267a preceded backend 089bf39 and browser/packaged 1864f61.
Runtime correction 359b80e, owner-side evidence probe df7b15f and distinct test
identity selector fb83c03 complete the source checkpoints. ADR-0029 delivers the
private-note portion of FR-006 and scoped FR-012 activity. Public replies, files,
native email and requester verification retain subsequent contracts.

Queue bindings carry independent note_access none/read/write, default none.
Write includes read. Only queue agent/operations_manager bindings may hold
read/write; configuration managers alone delegate them. Customer ceiling and
queue authority remain mandatory on every read/write, independently of assignment.
Platform, team, client, project and configuration roles confer no implicit note
content. Actual business delegations remain Q-20; only synthetic fixtures receive
test grants.

Four architectural decisions were made before implementation:

1. Deliver private notes before public conversation. A dedicated immutable table
   has no recipient, delivery or transport fields. The cost if the sequence is
   unsuitable is later union/read integration while retaining the private ACL.
2. Keep the three note tiers on the existing queue binding instead of introducing
   an overlapping grant ledger. Future per-note compartments need another policy.
3. Require reopening a closed ticket before a fresh note, preserving existing
   lifecycle eligibility. A different policy needs a later audited change.
4. Permit permission-only reductions on inactive accounts/parents when the role
   stays fixed. Increased authority or role changes retain active-reference
   requirements. A stricter revocation policy would retain avoidable access until
   references were restored.

## Persistence, security and compatibility

Migration b46087000016 adds bounded plain-text notes, RESTRICT parent/author
references, unique ticket/version ordering and SQL UPDATE/DELETE rejection.
API runtime has note SELECT/INSERT; the worker has no note-table privilege.
Guarded downgrade refuses durable notes, permissions or note/access history.
Application rollback preserves expansion and compatible event consumption.

Identity locking precedes authentication, followed by incumbent parent/ticket
locking, FOR NO KEY UPDATE target-account locks, reviewed versions, session
invalidation and atomic audit/outbox. Protected POST fingerprints preserve
omitted legacy note_access. Role-only changes preserve compatible permissions;
viewer/removal clears them. Current authority precedes replay, which returns saved
IDs without restoring permission. Strict note events contain identifiers only.
Private activity is filtered in SQL before pagination. Note text is absent from
inbox FTS, ordinary outputs, audit and outbox. Denied callers receive no note
ID/body/count or private activity event. Notes produce no outbound delivery.

The browser mounts notes only with current read capability and the composer only
with write capability. It retains reviewed draft version across refetch, exact
body/key/version through uncertain POST and acknowledged note ID until
authoritative ticket/note/page reads succeed. All ticket mutations share the
existing write owner and stay blocked through failed post-receipt refresh.

No dependency, search engine, asset, font or design token was added. The existing
gosu builder was updated to patched Go 1.27.4 with unchanged GOAMD64=v1 and
CGO_ENABLED=0. No -march=native or AVX/AVX2/SSE4.2 requirement was introduced.
These source restrictions do not qualify new images on the actual x86-64-v1
target. Integrated target qualification follows remaining MVP development.

## Executed local validation and reviews

- Focused real PostgreSQL/API: 70 passed; final foreign-customer/closed-ticket
  cases: 2 passed. Default-denial and inactive-parent reduction tests failed
  before implementation/correction. The focused concurrent queue test emitted
  one Pydantic UnsupportedFieldAttributeWarning for alias limit; retained as an
  advisory, not counted as a behavioral failure.
- Full resumed API: 612 passed in 1201.32 seconds, exit 0. Complete sanitized log:
  altvia-browser-8eefa69682-api.log. No warning summary was emitted in this run.
- Ruff/format, mypy across 36 files, OpenAPI/TypeScript generation, wheel/sdist and
  web check/build passed. Local SAST reported four LOW findings and zero blockers.
- Focused real HTTPS/PostgreSQL browser: 9 passed in 24.5 seconds after the
  missing-note RED. Covers literal persistence, reader/denied boundaries,
  committed/uncommitted uncertainty, failed reads, stale draft, acknowledged
  failed refresh, explicit grant/downgrade and ordered paging.
- Full resumed local browser: 116 passed in 5.9 minutes, exit 0. Complete
  646645-byte sanitized log: altvia-browser-c5359ed782-browser.log. No failed
  test, traceback or error-level event; existing standalone/color advisories
  remain visible.
- Keyboard, axe and overflow checks passed at 1440/390 pixels, light/dark.
  All 16 composition/note/grant/refresh-error captures were inspected.

The initial full local API/browser runs were interrupted by a host/runtime
restart. Their empty logs are preserved and never count as passes. Local Podman
was recovered by a scoped machine stop/start after its Windows forwarding port
became unavailable; the port was reassigned and volumes preserved. No target VM
or SSH configuration change occurred.

Executed full-suite commands were the local isolated runner
python .superpowers/phase1-tests/run.py --api -q and
python .superpowers/phase1-tests/run.py. Hosted equivalents were
uv run pytest -q, uv run node apps/web/scripts/browser-test.mjs and
uv run python scripts/container_smoke.py. These use disposable synthetic data;
they are not production or target-VM acceptance commands.

The replacement fresh whole-increment source reviewer reported no application
correctness/privacy defect, no Critical/Minor finding and no declined judgment.
One Important acceptance gap required packaged denial after a note actually
existed. The expanded smoke provisions a separate ordinary ticket reader with
note_access none. After restart, its ticket read succeeds while both populated
note routes deny, paged activity omits private type/ID/body, and owner-side audit/
outbox inspection proves redaction and absence of outbound events. This completes
acceptance coverage; it is not a claimed application-vulnerability RED/GREEN fix.

On 1864f61, the expanded smoke passed reader assertions but its metadata probe
failed because the API correctly has no audit/outbox SELECT. df7b15f uses the
existing owner-side PostgreSQL psql connection with a bound ticket variable; no
runtime privilege was expanded. That run passed the private-note proof and then
failed in the older team browser check. Adding note-reader@example.test made its
substring radio selector match two accounts. A local real-browser reproduction
observed strict-mode RED and identity-qualified GREEN; fb83c03 applies that
selector without changing application behavior, retries or timeouts. Final
packaged run 43088060972 passed the complete browser/container proof, closing the
Important acceptance gap. No re-review or broader runtime privilege was needed.

Impeccable's fresh finish reviewer inspected all 16 captures, verified inherited
seed f6e79c570b8eee00 and returned ship without material fixes. This was an
incumbent code-led extension with no separate quality card/approved comp. Its
documenter preserved DESIGN.md/design.json and recorded pre-existing omissions.
Original review dispatches lost to the host restart produced no report; the
replacement reports are the completed reviews. No Minor finding is deferred.

## Hosted acceptance

Final candidate fb83c03 passed all five workflows. Complete logs and downloaded
artifacts were inspected and retained, including image inventories and hashes.

| Workflow | Exact-source run | Result |
| --- | --- | --- |
| API checks | [43088061261](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43088061261) | 612 passed in 395.86 seconds; Ruff/format/mypy, migrations and build passed |
| Browser checks | [43088060957](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43088060957) | 116 passed in 3.9 minutes; web/generated checks passed |
| Container checks | [43088060972](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43088060972) | Rebuilt packaged HTTPS/ACL/notes/restart/native GIN/recovery/shutdown proof passed |
| Source security | [43088060943](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43088060943) | Zero blockers/secrets; four existing LOW findings |
| Service image security | [43088061059](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43088061059) | All five nonempty inventories; zero vulnerabilities at every severity |

The final API run emitted one Pydantic UnsupportedFieldAttributeWarning for
alias project_id in a concurrent test. Its complete warning is retained; no
test failed. Browser/container logs contain existing standalone/color and
upstream action/Node deprecation advisories. Full logs contain no unexpected
traceback, workflow error or failed step. SQL constraint/privilege/guarded-
downgrade errors and the intentional work-graph deadlock are asserted negative
tests, matching the preceding run's complete error classes.

Historical df7b15f passed 612 API tests in 447.99 seconds with one Pydantic alias
identifier advisory in the concurrent queue test, and 116 browser tests in 3.1
minutes. That warning does not invalidate the concurrent-write assertions and
is retained in the complete log. Its container failure is documented above.
Source security passed with zero blockers, zero detected secrets and four
pre-existing LOW findings. Expected PostgreSQL constraint/privilege/downgrade
errors and the intentional work-graph deadlock belong to negative tests; they
must not be reported as failed application runs.

## Image finding and verified correction

The first candidate 1864f61 passed the HIGH/CRITICAL image threshold but reported
one UNKNOWN CVE-2026-97054 in gosu's Go 1.27.3 standard library. It is not a
zero-finding result. Upstream release metadata at https://go.dev/dl/?mode=json
and the official registry confirmed Go 1.27.4/bookworm, pinned by digest
4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea.
The PostgreSQL image rebuilds the same gosu source/modules with the corrected
compiler. Local actual build passed module tests and user/group privilege-drop
probes. Expected unknown-user refusal is an asserted negative check.

The df7b15f full rescan reported zero vulnerabilities across every severity,
with API/PostgreSQL/ingress/web/Redis inventories of 66/49/70/43/16 package
records. Every report hash matched its manifest. It used the same vulnerability
database SHA256 as the UNKNOWN-positive scan:
4c2300c4576c99501ddad6911f1ced5bcd8ddaf65d925f82205a436154b20e61.
Thus the runtime rebuild removed the finding without suppression. Final-candidate
run 43088061059 independently reports the same nonempty inventory counts and zero
vulnerabilities across all severities, with all report hashes verified against
its manifest and the same scanner database. Old positive reports and failed
smoke logs are retained.

## Preserved acceptance bundle

The private immutable archive is acceptance.zip under
C:/Users/wagne/.codex/state/altvia-workspace/evidence/phase-3d-private-notes-fb83c03/.
It contains 189 files including its manifest, 6380701 bytes. Archive SHA256:
10440d35ed718214788cd4113f29d82f92e33804793eda2342958c778e6591d4.
ZIP integrity, every entry's length/hash and the downloaded hosted log archives
were verified. It preserves the exact reviewed source ZIP, complete final and
historical hosted logs/artifacts, local sanitized logs, RED/GREEN reproduction,
review reports, captures and ledger. Session/environment/secret files were not
included. The separate archive-receipt.json records the source, count, size and
hash without changing the frozen archive. Later closure publication changes
Markdown only, reusing the unchanged tested application source.

## Remaining scope

Public replies/private files, native email, SLA and subsequent transfer contracts
remain in Phase 3. Consolidation/automation and later roadmap phases remain open.
Real mailbox, sender-verification, retention and source-mapping questions retain
registered owners. Production deployment, real import and Zammad retirement
require separate gates and authorization. Actual-target qualification is deferred
until remaining MVP development is complete.
