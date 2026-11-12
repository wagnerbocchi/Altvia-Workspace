# Development roadmap and decision register

Updated 2026-11-12. User authorized incremental development after contracts,
direct pushes to main and no PR. Continue safe independent work while questions
await answers. This does not authorize production deployment or real data import.

## Current authorized design scope

User instruction2026-11-12: continue backend development and validation, but stop
before beginning any design, UI or UX. Private-files Task3 backend is now closed
on accepteddf3c8bb (immutable content links and explicitly reviewed MIME delivery),
with relevant checks, independent review and authorized publication complete.
The user subsequently invoked Impeccable and clarified a whole-system visual
redesign, selecting Twenty CRM as the reference. The active scope is the26
existing routes under docs/plans/2026-11-12-workspace-redesign.md. Private-files
Task4 was stopped before any implementation when that clarification arrived.
It remains pending separately. The new design preserves existing functionality,
resource authority and light/dark support. No production deployment or target
qualification is implied. The MVP remains incomplete.

## Current validation cadence

User instruction on 2026-11-10 supersedes the earlier per-slice VM cadence:
complete the remaining MVP development first, then run consolidated homologation
on the actual target server. Do not rebuild and homologate the target stack after
each increment. Continue small persisted slices, contracts before code, relevant
local tests, CI and security/native-dependency checks throughout development.

Record development completion, local/CI verification and target qualification as
separate states. Passing development gates permits the next independent slice;
the deferred VM gate does not block that development. Keep x86-64-v1 mandatory
and never extend an older image's qualification to a changed untested artifact.
After development is complete, qualify the final integrated application on the
actual baseline VM, fixing and revalidating any findings. Production acceptance,
real imports and Zammad retirement still require their separate authorization.
Earlier qualification entries below remain historical evidence, not instructions
to repeat server homologation during each new delivery.

## Delivery status

Task3 closure: all five exact-df3c8bb hosted gates passed,1198 API cases/three
explicit opt-in native-image skips and154 browser cases. All25 new file-link/MIME
cases actually executed; separate mandatory signed/current scanner/update/reload
and packaged regressions passed. Source22LOW/0blockers/secrets0 and seven nonempty
zero-vulnerability inventories pass. Independent source/spec review has zero
findings; prior M1 request-purpose enums are resolved. The original local257/8
stale-schema run remains failed; full265-case rerun on fresh correct PG passed.
Full source/hash/raw-evidence/restore-scope record: docs/phase-3i-private-file-evidence.md.
No UI/design work, incoming-MIME file ownership or target qualification is complete.

Phase 1 is closed on 2026-11-09. Final source 2f6ba60 passed all five hosted gates,
290 API and 31 browser tests, and the full five-image/six-service stack passed on
the actual x86-64-v1 VM. Exact tested images have zero reported vulnerabilities.
Worker shutdown during broker loss and all 27 recovered events are proven.
See docs/phase-1-closure-evidence.md. The user subsequently authorized continued
development. Phase 2A now delivers the scoped client registry in ADR-0018.
Source dc091de passed 316 API/37 browser tests, all five hosted gates and actual
baseline-VM packaged/native/cgroup proof. Exact tested five images report zero
vulnerabilities. See docs/phase-2a-client-evidence.md and its implementation plan.
Phase 2B now delivers internal/customer projects, shared operational areas,
explicit project management/membership and scoped history under ADR-0019.
Source 5faa866 passed 358 API/42 browser tests, all five hosted gates and actual
baseline-VM packaged/native/cgroup proof; the same five tested images report zero
vulnerabilities. See docs/phase-2b-project-evidence.md. Phase 2C now delivers real
tasks/subtasks, owners/participants, deadlines, transitions, internal comments and
attributable scoped history under ADR-0020. Source d5ae972 passed 403 API/48 browser
tests, all five hosted gates and actual x86-64-v1 packaged/native/cgroup proof.
The same five tested images report zero vulnerabilities. See
docs/phase-2c-work-evidence.md. Member, milestone and external-participant
workflow traceability is now closed by docs/phase-2-development-closure.md.
Phase 2D task discovery implements ADR-0021 and
docs/plans/2026-11-10-work-discovery.md after contracts in 215eb31. Backend 4d56e97
passed 424 API tests; browser search/filters, independent board paging and task-only
My Work are implemented. Source review's authority-recovery defect is fixed;
Impeccable scored both visual fixes resolved and preserved the incumbent system.
Final acceptance source 1c20f48 passed all five hosted gates: 424 API and 52 browser
tests, packaged Docker/HTTPS/native GIN/recovery, source security and five images
with zero reported vulnerabilities. Exact source 1c20f48 also passed actual
x86-64-v1 packaged/native/cgroup/GIN/recovery qualification; the same five
target-tested images report zero vulnerabilities. See
docs/phase-2d-discovery-evidence.md. Public-key SSH access and remote development
project registration are complete under separate user authorization. No password
entry is required while that key is loaded and remains authorized.

## Milestones and gates

Continuous MVP completion now includes ADR-0034 public response drafts. Persisted
API16ae9d9 and browser/recovery558f4ee passed100 affected API checks and131 full
local browser checks; one Important ownership-loss recovery finding has actual
RED/GREEN proof. All five exact558f4ee hosted gates passed with796 API/131 browser,
actual packaged restart/privacy and five zero-finding image inventories. See
docs/phase-3f-public-drafts-evidence.md. This is not yet full native email or final
target qualification. The next selected
engineering contract is ADR-0035 and its verified-mail-delivery plan. Sender and
requester attestation remain explicit owner operations with real policy Q03/Q16;
no production verification or sending is authorized or inferred.

ADR-0035 development is complete on accepted source c47fd8a. Persisted5c6da0d,
SMTP/worker6ae7e4f, browser e58c786, clock correction51ad72a and packaged c47fd8a
passed all five final hosted gates:894 API/142 browser and actual TLS SMTP,
uncertainty/restart/privacy/API-PG recreation/active SIGTERM. Active DATA shutdown
exited0 in1.116s; each scenario had one attempt/DATA and no restart resend.
All three fresh review findings have RED/GREEN and independent ADDRESSED/PASS;
final local201 passed706.44s. Five image inventories have zero vulnerabilities;
source has nine LOW and zero blockers/secrets. Sanitized252-entry evidence is
hash-bound in docs/phase-3g-verified-delivery-evidence.md. Full incoming mail,
private files, remaining MVP and final integrated target qualification stay open.

ADR-0036 Task1 now implements the owner-classified immutable case/origin boundary,
strict routing_v1, alias-aware SQL late-collision invalidation, private events and
current queue-role/client-ceiling filtered list/detail reads. Task1 source711d4b0
passed420 affected tests in1083.10s, static/package/web/generated gates and an
independent spec/quality review with zero findings. Bandit15LOW/zero blockers.
All282 raw source hashes matched;22-entry local evidence archive SHA256
d07400f82078e385d9ea63151ff950580a58fa0ab688638678deb47768fc9355 is retained at
the private workstation evidence path attested-inbound-task1-711d4b0/acceptance.zip.
Published Task1 sourceff71101 passed all five hosted gates: API959 in563.96s,
browser142 in4.9m, source security, images and packaged containers. Runs:
Source43176945766, Images43176945880, Containers43176945836,
Browser43176945842, API43176945922. No full incoming-mail completion is claimed
at that owner/read boundary.
No new unresolved engineering policy was needed: Q03/Q16 still own real receiving
and per-variant identity evidence; conservative routing compatibility is documented
in docs/contracts/api.md. Task2 adds protected persisted create/append/explicit reopen, scoped incoming/
outbound conversation and authoritative incoming receipt reads. It reuses current
creation/action authority, preserves legacy envelopes, locks contextual anchors
before the ticket and keeps invalidated history immutable. Final local frozen acceptance passed484 affected tests in1397.78s, including actual
runtime-role promotion/read/freeze and worker schema2/private denials. All13
static/security/package/native/generated/web-check/production-build gates passed;
OpenAPI/TypeScript reproduce exactly, Bandit17LOW/zero blockers, all288 raw sources
unchanged (aggregate3b92c48ea3e0430a741d34edd0ef462edf86e6017a874d4f78b9dd80c18d4e18).
Task2 source 7c198c8 passed independent specification and quality review with zero
findings. The private 48-entry acceptance archive has SHA256
a1e302cf9980d77a1f0eb214d43d485236843976f80660aae3fac3e87a585e76 and retains
separate stdout/stderr, exit metadata, earlier failures, manifests and review.
Hosted acceptance follows publication. UI and actual packaged incoming workflow
remain Tasks3/4; no complete incoming-mail or final target claim is made here.
Its clarified ADR0036 contract retains the first eligible incoming root when
more than16 precede the first reply, excludes previous-requester references from
new wires, and preserves receipts/history for promoted aliases and invalidation.

Task3 adds actual scoped triage and the combined incoming/outgoing conversation
at931c28c, with the detail-only historical receipt contract f7f71e6. Independent
specification/quality review approved it without Critical/Important findings;
Impeccable's two material findings were corrected and independently accepted,
and its documentation handoff found no material gap. Local frozen acceptance:
191 API in918.09s and154 full browser in10.2m; the final four-file visual/FORM
correction passed12 incoming scenarios/all36 corrected axe/theme captures,
web checks and build. Backend bytes remained unchanged. Both original36 and
corrected36 captures, full logs/failures and298 raw source hashes are preserved
in the private528-entry archive attested-inbound-task3-931c28c/acceptance.zip,
SHA256924cff84fdf654cd6a05c7718c037de9a23c07671da60d1f3292f86e78dadb68.
Minor readability cleanup and existing local runner warnings remain explicit;
neither is a functional blocker. Hosted a0da5a5's browser focus failure remains
historical; its deterministic correction now passed on14f334d with ALL FIVE gates:
994 API in726.95s,154 browser in5.4m, packaged containers, source security and five
nonempty zero-vulnerability image inventories66/70/49/16/43. Source has17LOW,
zero blockers/secrets. Exact hosted11-entry archive SHA256
4d21fc4b9280c898e4bf9e3de7f8644245057180842c6d12e3c353adac856bc3 is retained
at the same private Task3 evidence directory/ci-14f334d.zip.

Task4 harness source e91bcc5 locally passed19 focused tests in17.79s and actual
IMAPS/parser2/owner attestation/scoped HTTPS creation, separate requester proof,
TLS first reply references, append/explicit reopen, alias collision, table AND
column denials and API/PG container recreation. Original unclassified v1/v2 and
all three outgoing uncertainty/shutdown scenarios remain intact. Root verified
all175 raw source and26 evidence hashes. Fresh API image modules77 match source;
other local base images were reused, no web service/full Compose/cgroup claim is
made for that standalone run. Whole-increment independent review, final exact
hosted Docker/image acceptance and final target qualification remain pending.
See docs/runbooks/attested-incoming.md for explicit trust/recovery boundaries and
promotion-aware rollback. No provider, production or target claim is made.

The whole-increment review found one Important harness privacy-proof gap, no
observed application leak. The single d6c3469 fix wave has saved12-failure RED,
56 passing focused tests in18.74s and one actual packaged152.0s flow. Redis/SQL and
child/main diagnostics now check complete channel-specific canaries through four
actual delivered/processed checkpoints19/30/35/35. Scoped independent re-review
approved R1 with no new issue. Local/source576-entry archive SHA256
8b3a4aa3ecb589499cbab0049d3ded8ec054dff686095693bf47f62171e6d843 preserves
earlier source/UI archives and failure history. See
docs/phase-3h-attested-incoming-evidence.md.
Final publication36e4642 passed all five hosted gates:1040 API in750.62s,
154 browser in5.8m, actual full packaged Docker and source/image security.
Source17LOW/zero blockers/secrets; five nonempty inventories66/70/49/16/43 have
zero reported vulnerabilities. Root inspected all five full sanitized logs and
verified all three artifact digests. Final13-entry hosted archive SHA256
cdf13f7606176e14a50186392e3aca0520569522cb88a54ca2a9961ef0e90390 also preserves
the old a0 browser failure. The workflow now retains its existing incoming JSON
in subsequent artifacts; its actual local checkpoint JSON is already archived.
Incoming development/CI is accepted. Private files follows directly; provider,
operational rollback and final integrated target gates remain separate.

ADR0037 and docs/plans/2026-11-12-private-file-core.md select the next development
contract: VersityGW1.11.0 S3/POSIX with native narrow policies/conditional immutable
PUT/fsync/TLS, botocore1.44.1 and signed vendor ClamAV1.4.6-r0. That selection alone
did not install, build or ISA/security-qualify any component. Existing
resource/session/note authority, bounded streaming and real persisted scan jobs
precede UI; no placeholder files or raw-mail grants. Staff/outbound file core and
later owner-bounded incoming-MIME files are distinct required increments.
The builder check exposed one ambiguity, now explicit: policy1 scans on upload;
ready is a historical fresh-definition decision, while every access still checks
current resource scope and actual byte integrity. Q-22 retains the production
choice of future expiry/on-access rescans. Local Podman has2048 MiB; full signed
standard-definition acceptance uses adequate hosted/final-target resources without
restarting/resizing that local VM. Continue independent development.

Task1 infrastructure source046eacf and scoped corrections1c4e134 now have actual
local storage/TLS/policy/integrity/restart and transport evidence. The first review
found three Important byte-evidence/timeout/safe-error issues;39 focused correction
tests passed after eight failing RED cases. Scoped independent re-review marked
all three ADDRESSED with no new breakage. At that pre-hosted boundary, full
signed-definition/update/resource/all-seven/regression acceptance was pending.
Initial323 evidence/29 source hashes and supplemental38 artifacts/five sources were
independently verified. Old26/42 Windows command hash mismatches are preserved as
a historical evidence defect, with zero differences after newline normalization.
No file HTTP route/table/UI or full attachment functionality is claimed here.
See docs/phase-3i-private-file-evidence.md.

First hosted sourcef171dfa passed1098 API/154 browser, source security and all-seven
nonempty zero-vulnerability inventories. Existing packaged regressions also passed.
The required new private-file job failed native freshclam log initialization at
/dev/stderr; it did not load definitions or prove a scan. Its56 focused Linux tests,
52 real storage checks/restart and Docker storage cgroups passed, with18 exact
source and50 exact stream hashes verified. H1 is corrected in5c722da using native
foreground console logging; final15 focused/native checks passed and independent
re-review marked H1 ADDRESSED/no new breakage. That first attempt did not qualify
signed-definition/reload; all failed artifacts/full logs are preserved in the public
Phase3I evidence record. No target qualification or full attachment claim.

Task1 infrastructure is now accepted on a7628bf: ALL FIVE exact-source hosted gates
SUCCESS,1098 API/three explicit opt-in native skips,154 browser, source18LOW/zero
blockers/secrets and seven nonempty zero-vulnerability inventories. Actual full
signed/current ClamAV1.4.6/daily28181 passed clean/EICAR/encryption/expanded-limit/
oversize/stale/stopped controls, three signature verifications and real daily
replacement/reload3628258 signatures. Real Docker storage/scanner/updater cgroups
and isolation passed;18 source/132 raw-stream hashes matched. Final13-entry hosted
archive SHA2560d0433e9a6254d4a5d5b59fd9e61c3fbca691c1486fcb8777ab165efdc4cca5e
and all failures/reviews are retained in docs/phase-3i-private-file-evidence.md.
Proceed directly to persisted assets/scan jobs, content links/MIME2, browser and
integrated files, then incoming-MIME files. Final target qualification remains
deferred; no uploaded-file functionality or production acceptance is claimed yet.

Task 2 now has a reviewed local candidate through e7fcefc: real persisted binary
uploads/private downloads/metadata/retries and fenced durable scans under 00025.
1132 distinct local passes are independently reconciled across the complete
invocation, exact 76 missing-tool recoveries and two clock controls; three native
image checks remain explicit skips with separate producer proof. Eight focused
checks resolve the review's Important BOM type-filter issue; scoped re-review is
clean. The route-purpose generated-enum Minor is deferred to the next affected
contract. Local source SAST22 LOW/zero blockers, secrets zero and API image SCA
zero findings pass. The new single full-suite CI owner supplies real private S3
and verifies required cases actually execute. Its actual hosted startup/full
current-source gates remain pending. This is not full file/MIME/UI completion.
Task 1 console evidence now has explicit safe v2 review archives after correcting
an empty-username URL scrubber; original console copies remain private historical
evidence. Exact outcomes and corrections: docs/phase-3i-private-file-evidence.md.

Actual515d379 API CI failed before pytest: Docker static IP requires an explicit
user subnet (H2). The other four workflows passed, including154 browser cases,
signed/current ClamAV/reload and all seven zero-vulnerability inventories. No API
pass is inferred. Reviewed fix cb49780 reserves and verifies a nonoverlapping
internal /24 through native IPAM with at most three overlap-only retries. Ten
focused checks and actual Podman verified-TLS/bootstrap/PUT/GET pass; scoped
specification/quality review is clean. Failed hosted artifacts are immutable.
Actual cb49780 API CI then found H3: Docker's valid built-in host/none networks
have null IPAM.Config. It failed before network creation/pytest; the other four
workflows again passed, including154 browser cases and actual signed scanner/
reload. Correction160c886 accepts only those exact native name/driver/null forms,
retaining strict malformed rejection and all configured allocated subnets.
Retained-native-shape RED2 and focused GREEN21/Ruff/format pass; scoped independent
specification/quality review is clean. Actual Docker/full-suite acceptance remains
pending before Task3. Actual033c8ac then created the explicit private Docker
network successfully but failed H4: valid immediate inspection omits optional
Gateway. No API tests ran; other four workflows passed, including154 browser
cases and actual signed scanner/reload. Reviewed65e3712 supports that absent
field while retaining all private-boundary checks and rejecting invalid present
gateways; RED3/GREEN38/static checks and scoped independent specification/quality
review pass. Required actual Docker/full API acceptance was pending at that review.
No target operation, global network change, full-file completion or CPU claim
is implied. All failed artifacts and reviewed fixes remain immutable in Phase3I.

Task2 is now ACCEPTED on65e3712: ALL FIVE exact-source hosted workflows SUCCESS.
Actual native Docker/TLS/private S3 startup and cleanup passed; single complete
API invocation1173 passed/0errors/0failures/3explicit native-image skips in835.07s.
All37 required real-S3 file cases actually executed. Separate mandatory signed/
current scanner producer/update/reload passed; browser154/5.7m, source22LOW/
0blockers/secrets0 and all seven nonempty zero-vulnerability inventories passed.
Root verified197 API source+32 stream hashes and18 producer source+130 streams.
Six complete sanitized logs/five digest-verified artifacts remain in accepted
ci-65e3712.zip13 entries/1917672 bytes/SHA256
d20e32d879b4ae431aaf42d331eb85d523d41ebcae5b22fba39156d8ea1c0932.
Two nonblocking redundant Pydantic alias warnings in existing concurrent queue
tests remain explicit final-review observations. Continue immediately to Task3
content links/reviewed MIME2 and its deferred purpose-enum correction, then real
browser flows/packaged restore. Full file/MVP and final target qualification stay
open. Exact outcomes and preserved failures: docs/phase-3i-private-file-evidence.md.

The accepted incoming increment used ADR-0036 and
docs/plans/2026-11-12-attested-inbound-conversation.md: owner-attested classified
cases, existing queue/customer scope, protected staff promotion, contextual
identity/correlation and incoming/outgoing conversation. Unknown raw mail stays
private; per-message proof never verifies a global contact or grants an account.
Foreign claimed IDs cannot poison another customer's anchors. First SMTP reply
references and late alias collisions are explicit acceptance cases. Q03/Q16 real
trust/provider policy remains open; no live operation is inferred.

The Phase 3E-c policy follow-up delivers ADR-0033: strict Subject/body charset
ownership, complete HTML token accounting and separate immutable parser2 results.
Contracts31bbd6f preceded implementation. Final e0e6b06 passed all five hosted
gates with779 API/116 browser, local affected195 and actual v1/v2/replay/restart/
runtime-denial proof. Five nonempty image inventories report zero vulnerabilities;
source retains four existing LOW, zero blockers/secrets. R3/R4 and follow-up
review findings are fixed with RED/GREEN proof; no deferred Minor remains here.
See docs/phase-3e-c-policy-v2-evidence.md. Preserve parser1 rows/event schema1;
new writes/replay use version2/schema2. Drain old owner tools for key migration;
rollback retains compatible tools and expansion. A reproduced removed Alpine
Node pin was updated exactly to24.22.3-r0, with actual image capability/security
proof. No new artifact inherits old CPU qualification. No user-facing preview,
provider/production authorization or target connection is implied. Full native
email/Phase 3/MVP and final integrated actual-target qualification remain open.

Phase 3E-c delivers ADR-0032's private MIME-to-text boundary: immutable owner-only
ready/rejected results, source-serialized replay and strict private events. Contract
17fe438 preceded implementation. Final ae4d25a passed all five hosted gates with
744 API/116 browser tests, local affected160, actual packaged command/replay/
restarted text/cursor and runtime-denial proof. Image inventories66/49/70/43/16
report zero vulnerabilities; source has four existing LOW, zero blockers/secrets.
See docs/phase-3e-c-mime-evidence.md. No sender proof, public route, promotion,
attachment extraction or outbound mail is implied. Q-03/Q-09/Q-11/Q-16/Q-21,
Phase 3/MVP and final actual-target qualification remain open.
The independent review's two Important findings have executed RED/GREEN fixes.
That original parser1 source retained two reproduced minor gaps: broader Subject
codecs and uncounted closing tags. The ADR-0033 follow-up above corrects them for
parser2 while preserving historical v1 interpretations. Those old rows never
prove corrected policy or grant user-facing/production acceptance.

Phase 3E-b development is complete under ADR-0031: bounded read-only IMAPS into
existing quarantine, authenticated namespace binding, fenced leases and atomic
durable checkpoints. Contracts add42e6 preceded implementation. Final 426d4b8
passed all five hosted gates: 682 API/116 browser tests, actual packaged TLS poll,
restart/cursor persistence and runtime denial. Both Important review findings
have executed RED/GREEN regressions; no deferred Minor remains. Source security
has four existing LOW findings, zero blockers/secrets; five nonempty image
inventories have zero vulnerabilities. See docs/phase-3e-b-imap-evidence.md.
Only controlled synthetic TLS was used. Q-03/Q-09/Q-16/Q-21, live mailbox acceptance,
MIME verification/promotion, public replies/SMTP and private files remain open.
Phase 3/MVP and consolidated actual-target qualification remain open.

Phase 3E-a development is complete under ADR-0030: owner-only durable native mail
quarantine intake, explicit source/UID identity, immutable raw variants, permanent
collision replay and strictly private event receipts. Contracts 489b3fc preceded
implementation 118d99f. Final 72116da passed all five hosted gates with 646 API/
116 browser tests, actual packaged command/restart/replay and both runtime roles'
raw-table denial. Five nonempty image inventories report zero vulnerabilities;
source security has zero blockers/secrets and four existing LOW findings. A test
probe's API-versus-worker settings error has a reproduced correction and actual
packaged GREEN. Independent source review found no Critical/Important/Minor issue.
See docs/phase-3e-a-mail-intake-evidence.md. No sender verification, ticket
promotion, MIME rendering, live mailbox connection or outbound delivery is
inferred. Q-03/Q-09/Q-16/Q-21 remain open. Native IMAP, MIME triage and verified
public conversation retain subsequent increments. Phase 3/MVP and consolidated
actual-target qualification stay open; only synthetic mail was used.

Phase 3D development is complete under ADR-0029: immutable private ticket notes,
independently delegated note_access none/read/write, scoped private activity and
browser draft/uncertainty recovery. Contracts 4a5267a preceded backend 089bf39
and browser/packaged 1864f61. Final fb83c03 passed all five hosted gates with
612 API/116 browser tests, packaged populated-reader denial/redaction/no-outbound
and restart persistence, zero blocking source findings and zero vulnerabilities
across five nonempty image inventories. The Important acceptance gap is closed;
the independent source review found no application defect or deferred Minor.
Go runtime finding CVE-2026-97054 was removed by a patched builder and same-DB
rescan; failed historical reports remain retained. See
docs/phase-3d-note-evidence.md. Actual note delegates remain Q-20, default none.
Public replies, files, native email and subsequent transfer contracts retain their
own increments. Phase 3, the full MVP and integrated actual-target qualification
remain open under the development-first cadence.

Phase 3C manual ticket development is complete under ADR-0028 and
docs/plans/2026-11-10-manual-tickets.md. Contracts 22befa4 preceded backend 1751269
and browser/packaged da7999c. Exact da7999c passed all five hosted gates with
584 API/107 browser tests, packaged manual lifecycle/replay/customer-queue scope
and restart persistence, zero blocking source findings and five complete image
inventories with zero reported vulnerabilities. Two Important source-review
browser defects have RED/GREEN corrections. Impeccable scored both listed fixes
resolved and the documenter preserved the incumbent system. A legacy test's
fixed-page assumption was corrected using observed real paging without changing
timeouts/retries or production behavior. See docs/phase-3c-ticket-evidence.md.
Customer/queue are immutable in this increment, requester labels remain
unverified and queue close/reopen flags default false under Q-19. Remaining
Phase 3 work includes messages/private files, native email, SLA and subsequent
transfer contracts. Phase 3, later phases and integrated target qualification
remain open under the current development-first cadence.

Phase 3B development is complete under ADR-0027 and
docs/plans/2026-11-10-queue-access.md. Contracts 748c7ec preceded persisted access
8cde51d, reviewed logout-lock correction 08e8294, browser/packaged f366f40 and
project-test isolation 9e183ef. Final 9e183ef passed all five hosted gates with
557 API/96 browser tests, real queue grant persistence/replay/restart/scope proof,
zero blocking source findings and zero reported vulnerabilities in five complete
image inventories. Source review found one Important deadlock, reproduced and
fixed with real RED/GREEN. Impeccable scored its sole copy fix resolved and
preserved the incumbent system. A separate full-run test interference was proven
by a shared-reader selection capture and corrected with a dedicated account.
See docs/phase-3b-queue-access-evidence.md. Queue roles, configuration authority and
customer ceilings remain independent. Phase 3C supplies actual ticket lifecycle
and content enforcement. Phase 3 and integrated target qualification remain open.

Phase 3A implements ADR-0026's scoped persisted team-owned queue/category
configuration. Contracts 0f9059d preceded backend 7ef3a7a and browser 30e337e.
Test-only e3a79c2 strengthens packaged reader CSRF and authorization proof.
Local full API 540 and browser 87 passed. A source review's dependent
version-refresh race has a real RED/GREEN fix. Impeccable returned full-surface
ship and rechecked all final frames after the correction. All five hosted gates
passed on e3a79c2 with 540 API/87 browser, actual packaged queue/category restart
and scope proof, zero blocking source findings and zero reported vulnerabilities
in five complete scanned image inventories. Phase 3A development is complete.
See docs/phase-3a-queue-evidence.md. Final integrated target qualification stays
pending under the user's cadence. Phase 3 remains open.
Phase 3B supplies explicit queue grant administration and Phase 3C supplies manual
ticket content/lifecycle. Messages/files and transport follow as bounded slices.
Mailbox/provider questions remain Q-03/Q-16.

Known Phase 3A follow-up from source review concerns raw SQL whitespace-only
names. Default PostgreSQL btrim checks ordinary spaces, while HTTP validation
uses the full Python strip rule. The direct SQL defense refinement is deferred
to hardening and remains documented in docs/runbooks/ticket-queues.md.

Phase 2H development is complete under ADR-0025 and
docs/plans/2026-11-10-external-work-participants.md. Contracts 6a03689 preceded
backend a4c456d and browser f5b4e2a: bounded task-owned external labels,
manager-only writes, no identity/contact/grant inference and legacy replay
compatibility. Exact f5b4e2a passed all five hosted gates with 523 API/78 browser
tests, actual packaged label persistence/recovery, zero blocking source findings
and zero reported vulnerabilities in all five scanned images. A fresh source
review's Unicode finding was fixed with RED/GREEN; Impeccable returned ship and
preserved the incumbent system. See docs/phase-2h-external-participant-evidence.md.
The Phase 2 development audit is closed in docs/phase-2-development-closure.md.
Final integrated VM qualification remains deferred. Next: Phase 3 native Service
Desk contracts, then bounded persisted queue/ticket slices. Phases 3-6 and full
MVP/production acceptance remain open; no production deployment or real import.

Phase 2G implements basic persisted project milestones under ADR-0024 and
docs/plans/2026-11-10-project-milestones.md, contracted before code in 83c0858.
Backend 14bee57 and browser 128a718 reuse project ACL, versions/protected replay,
redacted activity and shared date/instant deadlines. Local 500 API/72 browser
checks and Impeccable corrections/documentation passed. The initial hosted image
gate found 50 installed library occurrences; vendor correction 011e0a5 passed
same-DB local five-image scanning with zero findings. Exact corrected source
011e0a5 passed all five hosted gates with 500 API/72 browser tests and zero reported
vulnerabilities across all five scanned images. Phase 2G development is complete;
see docs/phase-2g-milestone-evidence.md. Final target qualification
is deferred under the current cadence. No task synchronization, fabricated progress
or advanced scheduling is introduced. Phase 2H now supplies external involvement.

Phase 2E selected before code: ADR-0022 and
docs/plans/2026-11-10-client-contacts.md define scoped external contacts and an
explicit same-client default project. Contact identity never grants account,
portal or content access. Use a composite PostgreSQL FK for default scope;
no email/ticket side effect. Backend c67c195 and Unicode guard a3028b5 are tested;
browser contact/default configuration is implemented with both Impeccable fixes
scored resolved and documentation completed. Source review's two email-contract
defects have RED/GREEN fixes. Final application 334d477 passed actual guest
packaged/native/cgroup/contact/default event/image qualification. Test-only
c722de2 passed all five hosted gates with 463 API/60 browser tests. Current local
full browser 60 and final affected API 39/browser 8 passed; all five exact
native-tested images report zero vulnerabilities. Phase 2E is complete. See
docs/phase-2e-contact-evidence.md. Audit remaining Phase 2 traceability before
Service Desk; do not declare the whole phase complete from this increment alone.

Phase 2F now delivers scoped browser membership administration under ADR-0023:
known-email grants with explicit immutable review, versioned role changes/removal,
session invalidation, protected replay and scoped redacted events. Source b179695
passed all five hosted gates (480 API/67 browser) and actual x86-64-v1 packaged
member/ACL/session/replay/persistence/native/resource/recovery proof. Exact native
image IDs have zero reported vulnerabilities. Impeccable's single spacing fix
scored resolved; its documenter preserved the incumbent system. See
docs/phase-2f-member-evidence.md. Phase 2G implements milestones; external work
participants remain a subsequent Phase 2 slice; advanced dependencies stay P2.

| Phase | Ordered vertical deliveries | Dependencies | Exit evidence |
| --- | --- | --- | --- |
| 0 Discovery/design | Source inspection, PRD, ERD/dictionary, RBAC, ADRs, API/events, CPU plan and roadmap | Master spec + XLSX | Reviewable contracts, divergences and unknowns recorded; no product implementation in Phase 0 commit |
| 1 Foundation/identity | 1A backend auth/session/policy kernel and migrations; 1B real login UI with impeccable; 1C account administration, worker/outbox/Compose/CI/runtime validation | Phase 0 contracts; selected supported artifacts | Real login/logout/expiry/revocation; resource ACL negative tests; DB persistence/migrations; build/lint/typecheck/tests; actual VM CPU gate |
| 2 Clients/projects/work | Client/area + project/member slice; task/subtask/owner/participants/history; Kanban/list/search/My Work tasks | Phase 1 gate | Operate one real project end to end, graph/version race tests, no mock counts |
| 3 Native Service Desk | Queue/ticket/history; public/internal conversation + quarantine/private attachments; native IMAP/SMTP/reopen | Phase 2 + mailbox/provider data | Real request received/responded/reopened/closed; spoof/ACL/MIME/delivery tests and restart persistence |
| 4 Unified work/automation | N:N authorization; structured rules and durable consumer/DLQ; unified projection | Phase 3 | Assignment/retry/race/reassign/reopen singular logical effect; pagination and partial-ACL consolidation |
| 5 SLA/analytics/import | Versioned calendar/SLA; real dashboards; import staging/dry-run/reconciliation; P1 notifications after core | Phase 4 + approved calendars/mappings | Source metrics reproduced with explicit reference date; 34/19/8 dispositions; negative permissions; calendar/retry tests |
| 6 Hardening/readiness | Full E2E, targeted security tests, profiling, image/native audit, recovery/runbooks, pilot | Prior gates + production authorization | Guest runtime/load evidence, backup/restore/rollback, retention approval and pilot checklist |

Deliver one useful persisted vertical slice per coherent commit. No phase
advancement from UI appearance alone. Reuse unchanged passing evidence; test
affected behavior after each change. No release date/velocity estimate without
environment/volume data. Do not replace Zammad until formal operational acceptance.

The supplied VM qualifies the recorded five-image member-administration stack.
Changed mandatory artifacts will be qualified together after development under
the current user-directed cadence above. Production readiness remains
open. If all independent work is exhausted, report
the exact blocker rather than silently weakening acceptance.

## Definition of ready and done per slice

Phase 2F qualified on 2026-11-10: scoped browser member administration under
ADR-0023 and docs/plans/2026-11-10-project-members.md. Reuse the existing access
service; add accounts by known email without a global discovery endpoint. The
Phase 2G/2H now close milestone and external-involvement development traceability;
see docs/phase-2-development-closure.md. Advanced dependency planning stays
FR-016/P2 backlog. Historical Phase 2F target evidence remains in
docs/phase-2f-member-evidence.md; final changed-stack qualification stays pending.

Before implementation: ownership, typed request/response, permission predicates,
schema/constraint delta, failure/race behavior and meaningful tests are defined.
Before commit/push: relevant build/lint/typecheck/tests pass or the bounded
incomplete status is explicit; no secrets/raw client data; intended diff only.
Before development completion of a phase: UI uses real API/persistence, negative
ACL and recovery paths pass, and relevant local/CI commands and results are recorded.
Record final target qualification as pending until consolidated homologation runs
after remaining MVP development. Do not claim target compatibility from local/CI proof.

Production migrations/deploy: immutable images, backup, compatible schema plan,
documented rollback and post-change verification. External publication permission
currently covers this GitHub repository's main only, not production services.

## Open questions and safe defaults

| ID | Needed answer / owner | Safe action while pending | Gate blocked |
| --- | --- | --- | --- |
| Q-01 | Five-image member application b179695 qualified on the supplied VM, 2026-11-10; user subsequently deferred further target homologation until remaining MVP development is complete | Preserve exact tested evidence; continue local/CI checks and qualify the final changed stack together afterward | Satisfied for recorded images; final integrated target qualification remains required |
| Q-02 | Infrastructure admin: IOPS, workload/users/mail per day and production volume/backup policy; observed 8 vCPUs, 31.3 GiB RAM and 500 GiB disk | Conservative bounded defaults; inventory alone establishes no capacity or performance promise | Capacity/prod readiness |
| Q-03 | Support owner: mailboxes, TLS/auth/forwarding/trusted MTA and SMTP limits | Adapter contracts and controlled test SMTP/IMAP only | Real Phase 3 email acceptance |
| Q-04 | Operations: actual client/team/project/queue membership matrix | Deny by default; test explicit grants with synthetic test data only | Provisioning/pilot |
| Q-05 | Operations: approve 29 source-label mappings and 8 participant aliases | Preserve unresolved source; no automatic client merges/user creation | Real import |
| Q-06 | Row owners: approve ongoing row 32; resolve recurring wording versus done at row 34 | ADR-0006 model; retain source facts, no recurrence generation | Real import |
| Q-07 | Support owner: calendar, holidays, SLA targets, pause and reopen policy | Versioned model and deterministic test calendars, no real SLA promises | Phase 5 actual policy |
| Q-08 | Identity admin: OIDC issuer/claims/MFA availability | Secure local sessions, no simulated SSO/MFA | Corporate SSO when requested |
| Q-09 | Management/privacy owner: retention, deletion holds, access/export approvals | No destructive retention job; protect raw data/logs/backups | Production data policy |
| Q-10 | Support/management: desired Zammad migration/cutover/rollback | Keep current helpdesk; no API/database dependency | Optional future migration |
| Q-11 | Infrastructure/security: production storage/scanner/proxy acceptance and CPU-approved artifacts | ADR0037 selects VersityGW1.11.0/botocore1.44.1/ClamAV1.4.6-r0 for isolated development, not production or CPU acceptance; bounded private objects and no destructive retention | Production attachment/proxy acceptance |
| Q-12 | Infrastructure admin: hypervisor ownership and CPU-model change possibility | x86-64-v1 remains mandatory | None: CPU upgrade is not assumed |
| Q-13 | Product owner: approved logo/brand and visual preferences | Provisional restrained Portuguese interface, system fonts, no invented assets or claims; review after return | Final visual approval only |
| Q-14 | Engineering/security: ongoing service-image security | All five actual target-tested images have zero reported vulnerabilities; blocking HIGH/CRITICAL CI, SAST medium+ and every detected secret; retained complete severity metadata, no risk acceptance | Remaining production security/readiness gates |
| Q-15 | Resolved: owner authorized workstation public-key registration, remote Codex login and project registration; fresh noninteractive Windows SSH and actual Phase 2D qualification passed | Reuse agent-backed key with strict known-host checks; one connection per stage because native Windows multiplexing failed its probe; preserve previous environments and server security | None for current qualification; key removal, agent restart or changed host identity may require user action |
| Q-16 | Support/security owner: trusted contact verification, international mailbox/IDNA and authenticated sender correlation policy | Contacts remain server-only unverified, bounded ASCII mailboxes; no send, account linking, portal grant or client selection by email alone | Future actual email/verification acceptance; registry work can proceed |
| Q-17 | Engineering should diagnose remaining browser intermittency. Earlier Windows task/axe observations and the initial Phase 3A contact timeout remain unexplained | Phase 3B fixed separate shared-reader interference. Phase 3C observed an independent team test stopping at page 5 despite available next records and replaced fixed-page lookup with real advancement checks. Final da7999c passed local/hosted 107 with original timeout/retries. Preserve failed logs and distinguish these proven causes from the unexplained earlier contact/task/axe cases | Remaining runner reliability branches and final integrated acceptance |
| Q-18 | Product/security: whether task-owned external labels should later associate with client contacts, and how to preserve their distinct read scopes | Bounded supplied labels only, including internal projects; no contact lookup, matching, account creation or content grant | Future association policy only; Phase 2H can proceed |

| Q-19 | Support owner should select actual manual-close/reopen policy and any future automatic grace period | Phase 3C fixed queue flags default false. Synthetic tests explicitly enable manual behavior. Keep real calendars, SLA hours and automatic closure outside this manual setting | Production workflow policy and later SLA/automation acceptance |
| Q-20 | Support/security owners should identify real internal-note readers and writers per queue | ADR-0029 defaults every old binding to none. Configuration managers can explicitly delegate read/write with current customer ceilings. Synthetic fixtures alone receive test grants | Real organizational note delegation and production privacy policy |
| Q-21 | Support/infrastructure owners should approve actual inbound mail sizes, traffic and quarantine storage budget | Phase 3E-a bounds opaque raw intake to 2 MiB and 16 distinct variants per UID identity; refuse acknowledgement on overflow and never advance a mailbox checkpoint | Production connector/storage sizing; controlled synthetic intake can proceed |
| Q-22 | Security/operations: should already scanned files expire or require a new scan/current scanner health at access time? | ADR0037 policy1 scans on upload; ready records its actual engine/definition decision, while current scope/hash/length remain mandatory at each access. No timeless-safe claim, expiry or company policy is invented | Production scan-validity policy; isolated core development continues |

## Backlog after core

Account/status/password/role browser administration is implemented in30c577d,
with protected persisted API 207c203 and ADR-0016; reviewed fix 7e0e66b. Local and
hosted API 270/browser 30 passed, along with all four hosted gates. Independent
source review had no findings; Impeccable's spacing fix was scored resolved and
the incumbent system preserved. Updated actual target images passed packaged
account/TLS/ACL/recovery/cgroup proof and have zero reported image findings.
Exact evidence: docs/account-administration-evidence.md.
The final Foundation increment delivers the actual durable identity activity
consumer, restricted browser history, private Redis, safe logs and source-security
gates under ADR-0017. All Foundation gates passed on 2f6ba60. Phase 2A/2B registries
and Phase 2C task core are qualified under the user's subsequent instructions.
Phase 2D contracts preceded Kanban/filter/search/My Work implementation; exact
source 1c20f48 passed hosted and actual target qualification. This bounded
increment is complete. Phase 2E contracts preceded persisted contact/default
configuration and its qualified browser/worker/native delivery. Phase 2F completes
browser member writes and the exit traceability audit. Phase 2G implements basic
project milestones. The next slice covers external work participants, with
contracts before code and ticket state kept separate. Advanced dependency planning
remains FR-016/P2 backlog.
Production capacity/retention/provider decisions remain
the later gates listed above, not unimplemented Foundation requirements.

Residual findings were fixed on683e34d; packaged same-origin web ingress passed
acceptance on465a85b. Both revisions passed all four hosted gates. The four actual
service images now report zero findings, without suppression or risk acceptance.

FR-013 preferences/mentions/notifications, FR-014 time tracking, FR-015 authorized
CSV/XLSX export, FR-016 advanced calendar/Gantt/dependencies, FR-017 external
portal/knowledge base. Billing/subscriptions, marketplace, advanced ITIL/CMDB,
native mobile and local AI remain outside MVP. No speculative code for backlog.

## Evidence ledger

- Phase 2G: contracts 83c0858, backend 14bee57, reviewed browser 128a718 and
  signed vendor-library correction 011e0a5. Local full API 500/browser 72 passed;
  all five exact corrected-source hosted gates passed with 500 API/72 browser.
  Initial image scan detected 50 installed occurrences; exact-pinned Kerberos/
  libxslt vendor updates removed them, proven with the same scanner DB locally
  and in hosted scans. Five full inventories report zero vulnerabilities. One
  source review found no Critical/Important; its paging Minor was also a material
  visual finding and is fixed. Impeccable scored both fixes resolved, preserving
  the incumbent system. The calendar issue was a test-only native theme mismatch,
  corrected by driving the real theme control. Development complete; no target
  SSH/homologation under the updated cadence. Final integrated x86-64-v1 proof and
  external work participants remain open. See docs/phase-2g-milestone-evidence.md.

- Phase 2F: contracts 32e5a78, persisted writes 619f94c, deterministic revocation/
  roster race proofs ce15847, reviewed browser/packaged d55a4b2 and test-only account
  expectation correction b179695. Final local API 480 and affected browser 11 passed;
  all five exact-source hosted gates passed with 480 API/67 browser. Actual baseline
  guest ran the complete immutable b179695 stack: member/session/replay/ACL/browser/
  persistence/resource/native/FTS/logical restore passed. Same five tested image IDs
  have zero reported vulnerabilities; six access events projected once. Worker
  exited 0 in 7.608 seconds during Redis blackhole, recovering 27 events. Important
  source findings have RED/GREEN proof; Impeccable spacing fix resolved, system
  preserved. Initial smoke expectation failure and Windows connection timeout are
  retained, with exact corrections/limits in docs/phase-2f-member-evidence.md.
  Containers stopped, volumes preserved, SSH stages closed, remote dev synchronized.
  This increment is complete; milestones/external participants and production remain open.

- Phase 2E: contracts 3f0d1f1, backend c67c195, Unicode correction a3028b5, reviewed
  browser/packaged application 334d477 and test-fixture correctionc722de2. All five
  final hosted gates passed with 463 API/60 browser tests. Actual baseline guest
  executed the immutable334d477 archive; exact-ID reports show zero vulnerabilities,
  with native/cgroup/private-network/loopback/recreation/contact/default event proof.
  Worker exited 0 in 7.754 seconds under broker blackhole and recovered 27 events.
  Three contact-created/five contact-updated/two default events projected/delivered.
  Both source findings have RED/GREEN fixes; both Impeccable fixes scored resolved,
  documenter preserved the system. Test-only c722de2 fixes login fixture budget
  without changing caps or runtime inputs. Complete source/image/failure/review/
  capture evidence preserved; task containers stopped and volumes retained.
  See docs/phase-2e-contact-evidence.md. Phase 2 exit and production gates remain open.

- Phase 2D: contracts 215eb31, backend 4d56e97, reviewed browser 8c1be1d and
  final packaged proof 1c20f48. All five hosted gates passed with 424 API/52 browser
  tests. Actual baseline guest built/executed the final five images; exact-ID
  reports contain zero vulnerabilities and nonempty package inventories. Native
  cgroups/private networks/loopback, persisted scoped search/personal/columns,
  logical restore and GIN selection over 6000 rolled-back rows passed. Worker
  exited 0 in 6.408 seconds under broker blackhole and recovered 27 events.
  Final mobile captures inspected; task containers stopped and volumes retained.
  Public-key SSH eliminates repeated password entry; remote development project
  registered separately. See docs/phase-2d-discovery-evidence.md. Windows full-suite
  axe cause, production capacity and future domain gates remain open.

- Phase 2B: contracts fa14b3f, backend caa9deb, creation authority 7172128,
  reviewed browser c40198e and packaged proof 5faa866. Full 358 API/42 browser
  tests, fresh source-review corrections, Impeccable ship/documentation and all
  five hosted gates passed. Actual baseline guest built/executed the final five
  images, with exact-ID zero-finding scans and native/cgroup/project-isolation/
  persistence proof. Worker exited 0 in 8.784 seconds under broker blackhole;
  27 events recovered. Full-page skip-link artifact reproduced in a controlled
  same-image diagnostic; viewport/keyboard behavior passed without a product edit.
  Task containers stopped, volumes retained, SSH closed. See
  docs/phase-2b-project-evidence.md. Registry/areas complete; Phase 2 remains open.
  Stop before tasks/boards; no production deployment or real import.

- Phase 2A: contracts 06537b2, backend 4a9a954, reviewed no-op correction 24d534b,
  browser 7092456, packaged proof 11b5043 and test corrections dc091de. Full 316 API/
  37 browser tests, fresh source review fixes, Impeccable ship/documentation and all five
  hosted gates passed. Actual baseline guest built/executed the final five images,
  with exact-ID zero-finding scans and native/cgroup/customer-isolation/recovery
  proof. Worker exited 0 in 8.681 seconds under broker blackhole; 27 events recovered.
  Task stopped, volumes retained, SSH closed. See docs/phase-2a-client-evidence.md.
  Registry slice complete; FR-002/Phase 2 projects/areas/work remain open. No
  production deployment or real import. That increment stopped before projects/areas;
  the subsequently authorized Phase 2B result is recorded above.

- Phase 1 closure: contracts 3fba9a0, worker c9dfb26, history 410abe2, runtime 6e655f5,
  source-review fixes c4252eb, runtime-test corrections 2a80c60/7851794/29f1e4e and
  vendor zlib correction 2f6ba60. 290 API/31 browser tests and all five hosted gates
  passed. Actual target five-image stack passed full packaged/native/cgroup proof;
  exact image IDs have zero reported vulnerabilities. Blackholed Redis shutdown
  exit 0 in 7.742 seconds, all 27 events recovered. Independent source findings addressed;
  Impeccable full extension review ship, incumbent system preserved. Evidence in
  docs/phase-1-closure-evidence.md. Task stopped, volumes retained, SSH closed.
  Phase 2 not started; no production deployment or real-data import.

- Phase1C-k: account/security API 207c203, browser 30c577d, packaged proof515f9f1
  and reviewed spacing fix 7e0e66b. Full 270 API/30 browser and all four hosted gates
  passed. Exact final source/images qualified on supplied baseline CPU through
  actual HTTPS/account/replay/ACL/recovery/browser/resource checks, with zero
  reported image vulnerabilities. SSH master closed; isolated task stopped and
  volumes retained. See docs/account-administration-evidence.md. Remaining
  Foundation/production gates remain open; no real account provisioning/deployment.

- Phase 1C-j: authorized Docker/Compose installation and actual target qualification.
  Four images built and passed the packaged identity/team/roster/TLS/ACL/recovery
  workflow on the supplied baseline CPU. Actual cgroup memory/CPU/PID and isolation
  checks passed; exact same image IDs have zero reported vulnerabilities. Test TLS
  umask correction 358e027 passed review and all four hosted gates (244 API tests,
  21 browser tests). See docs/target-vm-foundation-evidence.md for exact versions,
  image identities, commands, setup failures/corrections and retained raw evidence.
  Task containers stopped, volumes preserved, SSH master closed. No public deployment,
  representative capacity claim or completion of remaining Foundation work.

- Phase 1C-i: contracted team/roster browser UX e9cfe74, implementation 960cd7d.
  Real persisted list/create/rename/archive/restore and bounded account/roster
  selection; session-owned private caches, original-intent protected POST recovery
  and reviewed-version writes. Local full browser suite passed 21 tests;
  build/types/lint/contracts/audit and four-image
  unfiltered scan passed. Fresh source review fixes are regression-tested;
  Impeccable finish disposition ship and incumbent-system documentation completed.
  Test-only CI correction ba8c937 passed all four hosted gates: 244 API tests,
  21 browser tests, actual packaged Compose/TLS/recovery and zero reported image
  findings. See docs/phase-1c-evidence.md for exact results. Account/role mutations remain
  CLI-only, and Q-01 still blocks Phase 1 exit. No production deployment.

- Phase1C-g/h: 683e34d closes the10 residual findings via vendor zlib, complete
  runtime pip/ensurepip exclusion and pinned corrected gosu modules. 465a85b
  packages the existing frontend under ADR-0014 with real same-origin HTTPS,
  credential/network isolation, pt-BR native locale support and no Sharp/build
  tools in runtime. Windows/Linux builds,244 API tests,7 existing E2E, actual
  packaged browser/Compose/recovery, theme/axe/visual review and all-service image
  scanning passed. All four actual images report zero findings. The review's
  browser DNS/TLS transport finding was reproduced and corrected before publish.
  Exact workflow links/artifacts and remaining guest/production gates are in
  docs/phase-1c-evidence.md. Identity admin UX/real worker consumer remain pending.

- Phase1C-f: 27b0bcb fixes installed API/PostgreSQL/ingress high/critical image
  findings with vendor-patched Alpine artifacts and baseline gosu rebuild.
  Adds blocking all-service SCA/image CI and cross-libc logical restore proof.
  Independent review's PGDATA reuse finding was confirmed and fixed with an
  entrypoint refusal/fresh-init marker. 244 API tests passed locally on Alpine
  and in hosted CI;7 E2E, actual Docker Compose/recovery and image security gates
  passed. Zero HIGH/CRITICAL across all three actual images; lower severities
  remain visible. See the exact evidence/rollback in docs/phase-1c-evidence.md
  and ADR-0013. Actual VM/worker/Redis/web ingress and remaining Phase1 gates stay open.

- Phase 0: `docs/phase-0-report.md` and workbook reconciliation.
- Phase 1A: identity API implementation, 44 real automated checks, migrations,
  build/lint/types and evidence in `docs/phase-1-evidence.md`. Phase 1 remains
  open for administration/process/runtime/security/target-VM gates.
- Phase 1B: real browser login/account/logout, generated API types, 7 real
  HTTPS/PostgreSQL browser tests, theme/responsive/axe checks and reviewed focus
  recovery, published in `88d945c` with both Linux workflows green. Sharp
  excluded to avoid its Linux x64 SSE4.2 requirement. Phase 1C
  administration/processes/ingress/security and target-VM gates remain open.
- Phase 1C-a: restricted CLI ordinary-user provisioning, active-state changes and
  platform-role administration with atomic session revocation, audit/outbox and
  concurrent last-active-admin protection, published in c8e3920/2f3298a. Full
  83-test API suite passed; both Linux workflows green, independent review clear.
  See `docs/phase-1c-evidence.md` for publication/gates.
- Phase 1C-b: persisted team/roster API and safe account lookup with identity-only
  authorization, versioning, atomic audit/outbox and protected POST replay.
  Published in 030a3f2/a5ce79a; 160 API tests and both Linux workflows passed.
  Review finding on PATCH schema resolved. Remaining gates are in the Phase 1C report.
- Phase 1C-c: persisted constrained team read scopes, transactional restricted
  grant/revoke CLI and SQL-filtered team/roster reads. Storage/service fd92682;
  CLI/API ea7f081; reviewed publication d59709f. Local full API suite 213 passed,
  guarded migration preservation/refusal/roundtrip, API/web build/types/lint and
  unchanged generated contracts passed. Fresh independent review had no findings;
  both hosted Linux workflows passed (213 API tests, 7 browser E2E). Exact links
  and publication evidence are recorded in docs/phase-1c-evidence.md.
  Client grants, admin UI and remaining Phase 1/runtime gates are still open.
- Phase 1C-d: runtime DB privileges/file secrets63d1fa9, image/Compose ee70bea,
  review fixes7b0a933 and build-context correction7df1ebc. Final234 API tests passed
  locally and in hosted Linux; all7 browser E2E and actual Docker Compose/TLS/
  recreation/ACL/readiness/SIGTERM proof passed. Local Podman lacks cgroup memory
  controls; resource limits were preserved and validated through hosted Docker.
  See ADR-0011, docs/runbooks/api-containers.md and exact CI evidence in the Phase1C
  report. Q-14/image security and Q-01/actual CPU, recovery/load, worker/Redis/web
  ingress and remaining Phase1 gates stay open. No production/phase exit claim.
- Phase 1C-e: unused SQLite package/module removal 1d8ed76 with automatic native
  capability guard, preserving Python/bookworm and lockfiles. Same-DB scans removed
  19 SQLite findings (1 critical/5 high/9 medium/4 low), added none; 35 high
  occurrences remain open. Fresh review had no findings. All three hosted gates
  passed on 3b96e2f: 236 API tests, 7 browser E2E and actual pruned-image Compose
  behavior including builder rejection/runtime guard. See ADR-0012 and the exact
  evidence/scan reports. No production/phase exit or target-CPU claim.
- Future implementation entries must include commit, exact commands/results,
  target artifact/host when relevant and outstanding gates. Do not mark a phase
  done merely because the documentation or a subset of tests is complete.
