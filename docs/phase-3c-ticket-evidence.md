# Phase 3C manual ticket development evidence

Updated 2026-11-10. Development acceptance is complete for application/test source
da7999c5fcef19bbf6a7c86ab07922457fcaea2f. Phase 3 remains open. Consolidated
target qualification follows remaining MVP development under the user's cadence.

## Delivered behavior and decisions

ADR-0028 contracts in 22befa4 preceded backend 1751269 and browser/packaged
da7999c. This bounded increment implements FR-005 and scoped FR-012 with persisted
manual ticket creation, decimal-string human numbers, scoped inbox/search/filters,
detail editing, eligible assignment/self-claim, six states and immutable history.
Every ticket, history, activity and linked choice applies explicit queue authority
and customer ceilings. Configuration, team, client and project roles retain their
independent boundaries. Platform administration confers no ticket content.

The coordinator chose immutable customer/queue for this increment. Managers may
replace the same-customer requester and assign currently eligible active accounts.
Ticket-only reference choices expose minimum customer/contact/account labels
without directory grants. Inbox customer filtering starts from authorized rows.
Requester identity stays unverified through form, final review and detail.

Queue manual-close/reopen flags default false and use existing reviewed
configuration authority. Queue managers close resolved tickets and reopen closed
tickets when the respective flag permits it. Assigned agents may reopen resolved
tickets when permitted. Pending/resolved entry and reopening require a reason.
Real business policy remains Q-07/Q-19, including any later automatic grace period.
Customer/queue transfers need a subsequent both-boundaries contract.

Current authority precedes protected receipt replay. Original POST body/key and
reviewed version survive uncertain responses and failed reads. Committed replay
does not repeat assignment, history or timestamps. Archived historical references
remain readable and unrelated edits retain inactive requester/assignee labels.
Actual effects require active parents and eligible new references. Closed tickets
require reopening before actual edits/assignment. After a minimal receipt, the
browser requires authoritative state before another write.

## Persistence, security and compatibility

Migration b46087000015 adds default-false queue flags, native positive BIGINT
identity numbers, composite requester/customer and category/queue foreign keys,
ticket/history constraints, native Portuguese FTS/GIN and ticket activity scope.
The history graph explicitly separates initial null-to-new/version 1 from non-null
transitions at later versions. Empty migration round trips preserve prior queues.
Downgrade refuses durable tickets/events and configured or historical policies.
Application rollback retains the expanded schema and compatible event consumer.

Identity locking precedes authentication. Parent/ticket/reference locks and the
incumbent FOR NO KEY UPDATE target-account protocol preserve session/logout
concurrency. Ticket changes, immutable state history, protected receipts and
redacted audit/outbox commit together. Strict event families validate exact field
presence, aggregate ID, state graph and explicit nullable old assignee. Ticket
events remain outside other resource feeds. Subjects, descriptions, reasons and
emails remain outside event metadata.

The actual API runtime role inserts identity numbers and appends history while
history UPDATE/DELETE and ticket DELETE are denied. Worker has no ticket/history
table grants. Existing dependencies and CPU restrictions remain in force. This
increment introduces no search engine, dependency or ISA requirement. New images
await consolidated actual x86-64-v1 target qualification.

## Executed validation and reviewed corrections

Full local real PostgreSQL/API passed 584 in1125.01 seconds. Focused post-commit
historical-reference proof passed 1. Ruff, format, mypy across 36 source files, wheel/sdist,
OpenAPI/TypeScript generation and web check/build passed. Native GIN selection,
bounded joined reads, BIGINT beyond JavaScript's safe integer range, composite
FKs, least privileges, downgrade guards, rollback/overflow and concurrent
create/claim/transition/target logout have actual regression evidence.

One fresh whole-increment source review found two Important browser defects.
Prepared transitions could silently adopt a newer refetched version. Confirmed
creation could become repeatable while detail navigation was slow. Real browser
tests observed the newer If-Match and reenabled Create button before correction.
The owning components now retain the reviewed transition snapshot and acknowledged
ticket ID. Both regressions pass. No minor finding or declined judgment remains.

A full browser run passed 106/107 with all 11 ticket tests passing. The remaining
team test stopped after four next-page attempts while its observed snapshot
showed page 5 and another available page. New fixture accounts exposed this old
test assumption. The three copies now share real page advancement checks and
wait for the received page before selecting. The 30-second timeout, zero retries, page size and
production behavior remain intact. The corrected full local suite passed 107/107
in 6.6 minutes. The transient Playwright snapshot was inspected before replacement;
the complete failing run and its observation record are retained.

Impeccable inspected 28 valid desktop/mobile light/dark captures, then requested
the unverified-requester notice in visible final review and the explicit inherited
FORM seed. The notice was missing while the form was hidden. After this narrow
text/document correction, rebuilt lifecycle, visible-review assertion, keyboard,
axe and overflow proof passed 1 and the four review frames were recaptured.
The reviewer scored both fixes resolved with ship for those fixes. The documenter
preserved the incumbent system and recorded pre-existing narrative.rules drift.
Final exact-source hosted browser checks cover all107 tests after this correction.

PostgreSQL's logged raw work-graph deadlock is the existing intentional 40P01
refusal test, which prelocks inverse rows and proves only one edge commits.
Negative constraints, immutable-history and downgrade refusals are asserted test
conditions. No required validation gate failed on the acceptance source.

## Exact-source hosted acceptance

All five workflows completed successfully on da7999c. Full run/job/artifact
metadata, logs and downloaded artifacts are preserved privately.

| Workflow | Executed result | Run |
| --- | --- | --- |
| API checks | 584 passed in 306.95 seconds, schema/static/build gates passed | [42945346939](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42945346939) |
| Browser checks | 107 passed in 2.6 minutes, generated contracts/check/build passed | [42945346914](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42945346914) |
| Container checks | Manual lifecycle, denied inherited content, replay and restart ticket/history persistence passed with existing packaged TLS/ACL/recovery proofs | [42945346775](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42945346775) |
| Service image security | Five complete inventories, 0 reported vulnerabilities | [42945346936](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42945346936) |
| Source security | 0 blockers, 0 detected secrets, 4 pre-existing LOW Bandit findings | [42945347105](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42945347105) |

API/PostgreSQL/ingress/web/Redis inventories contain 66/49/70/43/16 package records.
Every report hash matches its scanner manifest. Scanner/database metadata and
image IDs are preserved. These inventories qualify the scanned builds on the
acceptance source. Actual final target image qualification remains separate.

## Evidence preservation and remaining scope

The private immutable archive is
`C:/Users/wagne/.codex/state/altvia-workspace/evidence/phase-3c-manual-tickets-da7999c/acceptance.zip`.
It has 128 files and 4702249 bytes. SHA256 is
`f9ffe25e928c7ba4caa6121c590cb6f82643afdd54ed2c88c8de50a1734e83ec`.
Every entry was checked against its manifest and the ZIP integrity test passed.
The sibling publication receipt records final documentation and remote equality.

Remaining development includes ticket messages/private files, native email, SLA,
subsequent transfers and Phase 4 consolidation/automation, then later phases in
the roadmap. Real mailbox inputs and workflow policy questions remain registered.
Final integrated target qualification, production deployment, real import and
Zammad retirement retain their existing gates and authorizations.
