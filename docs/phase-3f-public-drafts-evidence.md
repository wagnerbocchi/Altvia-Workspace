# Phase 3F public response draft evidence

Updated2026-11-12. Source558f4eec27d6acb1d7978d844023983ae3e42b30 passed all five
hosted gates. Public unsent conversation drafts are development-complete; native
SMTP, inbound promotion, files, remaining MVP and final target qualification
remain open. Only synthetic data and disposable local/hosted test systems were used.

## Delivered behavior and decisions

Contracts9a891f7/85c5e32 and ADR-0034 preceded persisted API16ae9d9 and reviewed
browser/package558f4ee. Public ticket_messages are immutable and structurally
separate from private ticket_notes. Current ticket readers require queue role
and explicit client ceiling. Draft writes require the manager or current assignee,
active parents and an editable ticket. Private note delegation is independent.

The existing identity-before-auth/parent/ticket lock, reviewed If-Match, protected
Idempotency-Key and atomic receipt/version/audit/outbox owners are reused. Current
authority and valid protocol precede saved replay. New keys create distinct drafts;
same-key authorized replay returns the original receipt. Closed/inactive state
blocks fresh effects without destroying committed receipts. Strict events contain
IDs only; body, subject, addresses and private note content never enter activity,
audit, outbox or request logs. Lists and detail bind both actor and ticket.

The browser provides chronological persisted pages, escaped multiline text,
explicit review, independent private-note composition and Rascunho - nao enviado.
It retains original text/key/version through uncertain POST, failed reads and
focus refresh. An acknowledged ID remains locked until authoritative ticket,
message detail and visible message page reads succeed. See the usable procedure
in docs/runbooks/ticket-responses.md. No email, verification, ticket transition,
first response or SLA success is implied by saving a draft.

Migration b46087000021 adds RESTRICT references, length/text/state/version checks,
unique ticket/version and append-only SQL guards. API SELECT/INSERT only; worker
has no message table grant. Downgrade refuses populated messages or drafted
history. Application rollback retains the expansion and compatible event reader;
never erase records/history to force contraction.

Three explicit decisions and costs remain visible:

1. Immutable public drafts stay separate from private notes. Revising saved text
   costs another draft until an explicit later send/cancel contract.
2. delivery_status=draft belongs to the read projection rather than a redundant
   immutable column. The later delivery aggregate must own transport state.
3. Resource403 is distinct from real session/CSRF failure. Original protected
   intent survives action denial in the same readable session; actual logout,
   revocation or CSRF rejection still destroys local private state. Unsaved text
   can be lost on real session termination or navigation away.

## Local checks and source review correction

Actual missing-route404 RED preceded the API implementation. The first13 cases
had11 passing and two fixture mistakes: expected DBAPIError instead of the safe503
boundary, and a missing CSRF override. Corrected/expanded actual PostgreSQL API,
public message/private note/manual ticket/activity/runtime suites passed100 in
356.39s. Ruff/format, mypy40, generated OpenAPI/TypeScript comparison and actual
wheel/sdist build passed. No required check is replaced by a source inspection.

The frontend implementer passed20 message/note browser cases, web check/build and
generated-type comparison. Fresh independent source review found one Important
defect, no Critical/Minor: reassignment after an uncertain save caused403 and the
generic transport destroyed the session-local original intent. The shared write
hook also cleared it, and refreshed authority hid its review.

Both committed/uncommitted real browser scenarios failed before correction.
The responsible transport now distinguishes forbidden from authentication/CSRF;
the write owner retains the original intent; the response review stays disabled
and visible while read scope remains; verification reuses the original request.
Restored assignment returns200 for a committed receipt and409 for the stale
uncommitted request, without a second draft. Discard is explicit and follows a
successful read. Separate401/CSRF403 cases prove local private state still ends.
All24 affected browser cases passed. The final stabilized full suite passed131
in6.9m, with original timeouts, one worker and zero retries. Final web check/build,
Ruff/format121 and mypy40 passed; generated contracts remained exact.

One full local run was invalidated by an executor rebuild while the prior Next
server was still executing tests. It showed loading-state failures and was
stopped; its complete sanitized log remains preserved. It is not passing evidence
or a diagnosed product regression. The final131 run used stable built files.
An initial TypeScript predicate narrowing error was corrected before final checks.
Earlier Store Python launch failures remain distinct from application assertions;
the explicit project interpreter ran the actual passing browser tests.

Impeccable's independent finish review opened16 desktop/mobile/light/dark captures
and returned ship after fixing one paragraph inset. Documentation preserved the
incumbent system; no token/dependency/redesign was introduced. Root inspected four
additional final denial-state captures after the recovery correction, using the
existing action-row spacing. All20 final captures assert zero axe WCAG2A/AA/2.1AA
violations and no horizontal overflow. Existing identity-era catalog/brief metadata
drift remains recorded without unrelated repair. No deferred source-review Minor.

## Exact-source hosted and packaged proof

All complete run logs and original log ZIPs were collected and checked. No workflow
error or Python traceback appears in the final five runs. PostgreSQL rejection
logs cover deliberate constraints, FK/role denial, append-only history, injected
event rollback and downgrade refusal; the existing work-parent race deliberately
provokes a deadlock and checks one winning mutation. The retained Pydantic warning
is alias limit in test_queue_access_concurrent_reviewed_writes_one_wins. Setup
action url.parse/Node20 deprecations and local standalone/color advisories are
separate tooling observations, not suppressed production vulnerabilities.

| Gate | Result | Run |
| --- | --- | --- |
| API | 796 passed, one warning in517.06s; migrations/static/build passed | [43145422652](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43145422652) |
| Browser | 131 passed in3.7m | [43145422752](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43145422752) |
| Containers | Actual HTTPS/public draft/replay/restart/privacy and full prior packaged proof passed | [43145422723](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43145422723) |
| Source security | Four existing LOW metadata findings; zero blockers/secrets | [43145422754](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43145422754) |
| Image security | Eight report tests; five nonempty inventories, zero vulnerabilities at every severity | [43145422670](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43145422670) |

Packaged proof uses a separate public-draft ticket, so existing note/version/event
fixtures remain unchanged. It actually appends/replays a public draft, restarts
PostgreSQL/API, verifies the same body/ID/version/draft state and proves ordinary
ticket readers can read without a note grant but cannot write. Existing private
quarantine/MIME/TLS IMAP, FTS/GIN, restore, worker/Redis and role proofs also passed.
The image-security job builds independently; image identity with the container
job or actual target is not inferred.

| Image | Packages | Scanned image ID |
| --- | ---: | --- |
| API | 66 | sha256:32873b109cca9db4e266df2d40f391cb362e2dda31aaa55a64477a02b467a281 |
| PostgreSQL | 49 | sha256:caf13e4b20bd97a6b05740ed22f786ef50c73fcc85f877d46e37dd1b778587cf |
| Ingress | 70 | sha256:b7e868c1e864a5582a60b98038634be05a55660b5b675ad1f9aa95ca2d5bbd16 |
| Web | 43 | sha256:c12269661e612bef96fd1c5e003f4d168aceb52d198b5833d2d1428a99dfd23a |
| Redis | 16 | sha256:6f8ae2d8666e98c7e6a1de9784569a85b57c8e41335a220406bb2a1e8c31b052 |

Report SHA-256 and exact image IDs were checked against the manifest; scanner DB
SHA-256719de0cb21fdbc1bf3cb433f7ea57f68910c9d1771f8334026035f5fb11ff325.
No new dependency or CPU requirement was introduced. New images still need final
integrated actual x86-64-v1 qualification under the user's cadence.

## Evidence and continuation

Immutable sanitized workstation archive:
C:/Users/wagne/.codex/state/evidence/public-ticket-drafts-558f4ee/acceptance.zip.
All98 entries passed ZIP integrity and97 per-entry hashes;6063481 bytes;
SHA-256 febef582ae4767188d766efe9fef85f12bcfab14eb654120821a2301e9607995.
Receipt remains outside the archive. It retains exact tested source, full local
RED/GREEN/final/invalidated logs, source/design reviews,20 captures, hosted metadata,
logs/log ZIPs and source/image reports. Credentials, TLS keys, source workbook,
optional browser cache and future uncommitted source are excluded.

The next contract is ADR-0035/plan c67a43b, with addressable headings181469d.
Verified public delivery persistence is now in development. No whole-MVP, live
provider, production deployment, real import or Zammad-retirement claim is made.
