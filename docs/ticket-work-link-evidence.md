# Ticket/work link development evidence

Updated2026-11-13. ADR0039 Tasks1/2 schema and protected API are implemented and
independently reviewed atb4c31e5 and9a45874/657167d. The earlier exact5c0d423
hosted gates all passed. Current API source has208 relevant native passes plus
two covering passes for its generated-response correction; current full hosted
acceptance remains pending. Operate panels, packaged relationship proof,
whole-feature/MVP acceptance and final target qualification are not claimed.

## Native schema slice

TicketWorkItem uses its natural ticket/work pair, required client/queue/project
identities and the three existing composite parent keys. PostgreSQL enforces
same non-null client, restrictive parents, fixed related type, actor and aware
creation timestamp. No work customer copy, ownership trigger or parent-key
replacement is introduced. API receives SELECT/INSERT/DELETE only; UPDATE and
all worker join access remain denied. This is a technical DB grant, not a user
content permission or a new HTTP endpoint.

Contraction locks the join/outbox/audit/activity/receipt stores and refuses live
links, each of four future link-event families, or either protected namespace,
even after every live link is removed. Expired receipts are not silently purged.
Empty roundtrip retains prior keys, rows/counts and unrelated grants.

The user selected altvia-vm for development/tests. The source was transferred by
verified Git bundle and guarded owned-file overlay; unrelated remote work stayed
untouched. A clean530-file snapshot avoided ignored environment/private state.
Pinned Python/uv/lock dependencies and current API-CI PostgreSQL17 ran nonroot
in a private capped Docker fixture, with no host ports or host package changes.

| Scope | Actual result |
| --- | --- |
| Native storage |24 passed,0 skips/warnings |
| Runtime provision/work storage/tickets |60 passed,0 skips/warnings |
| Static/schema |Ruff,format167 files,mypy62 files,Alembic upgrade and drift check passed |
| Independent review |Spec and task quality pass,0 actionable Critical/Important/Minor |

All13 native records/raw hashes and535 before/after inputs were independently
checked;530 source entries match the canonical base/overlay. Three new files
match committed blobs exactly. Models/provision were tested with CRLF and differ
from committed blobs only by LF normalization. This supports same-code schema
approval, not exact-byte full hosted qualification. Evidence archive SHA256:
9859278840204795b8be6026ce7705ef1164f36588dc4b33ebeaffeec68897d6.

Retained failures include23 expected missing-table failures/1 parent-schema pass;
first GREEN22 passes/2 auxiliary Client timestamp-fixture failures; local Podman
connection125 before tests; and earlier lint failures. Final proof used the
user-selected remote stack. No earlier failed attempt is counted green.

## Existing project-manager browser publication gate

Docs-only6dd5eb2 CI passed API1469/3 explicit native-console skips, source/image
security and both container jobs, including303 successful combined commands and
the incoming6-object matching restore. Browser run43489974428 failed1/passed184.
The failure was projects.spec.ts:172, before any project POST: it expected the
first raw users-page account to be a selectable manager. The UI correctly exposes
self plus active other accounts; the directory legitimately includes inactive
accounts. The original failed row's active flag was not exported and remains
unknown. No recurrence rate or exact historical row state is inferred.

Controlled native RED03 used eleven NEW synthetic ungranted low-UUID accounts,
with the eleventh inactive, forcing an inactive first row on page two. The real
API200 response and rendered options proved that the old expectation fails for
valid data. No existing actor/session/role was changed by this fixture. All39620
inputs stayed unchanged. That controlled condition is distinct from unavailable
metadata in the historical run.

Correction9a3e225 changes only four added/one removed test lines: await the exact
rendered sequence of empty choice, current actor and active other response rows.
No UI, timeout, retry, skip, response predicate or selection policy changed. The
full original explicit-manager/lost-reply/201-200 replay/original key+body/locked-
form/independent pagination/read recovery/reader-session assertions remain intact.

| Scope | Actual result and limit |
| --- | --- |
| Controlled RED03 |1 expected old-oracle failure,39620 unchanged inputs |
| Controlled GREEN01 |1 passed,0 skips,same forced inactive-first condition,39620 unchanged inputs |
| Canonical projects Module01 |5 passed,0 skips,no private seed/diagnostic hooks,39620 unchanged inputs |
| Static02 |Next typegen,ESLint max-warnings0,tsc noEmit passed;39616 unchanged inputs |
| Baseline build |Native guard/web check/build passed on unchanged application source; reused for the test-only correction |
| Independent review |Spec and quality pass,0 actionable Critical/Important/Minor |

All299 exported hashes, actual input maps, source/probe bytes and raw channels
were independently checked. Module01/Static02 source530 exactly matches9a3e225.
Archive SHA256:
bbcab9f0ea92c1e9fcf562a821b71c83b6b687fa66a9df693ff8fe890d0858ec.
The failed6dd archive remains separate,254 entries/CRC verified, SHA256:
059f939d432100e48f5a91c2ee03d1c3cc34d99b9a7b2efb68bfb2738285a84e.

Accepted runs retain the inherited Next standalone-launcher notice. Bootstrap
used private Ubuntu24.04/Node24.21/Python3.12 tooling, current locks and actual
Chromium, with capped nonroot containers and private PG/Redis. No S3 was needed
for this scope. Tool-cache and image-reference bootstrap failures, RED02's uv
editable-metadata guard125 and Static01's pnpm-bookkeeping guard125 remain
retained. Only generated task-run bookkeeping was classified as output; source,
dependencies and compiled build stayed covered. Optional xz manpage notices and
disposable PG local-trust initialization are not production configuration proof.

Task1 files/data stayed unchanged. New browser fixture services were stopped;
volumes/images/evidence remain retained. Client SSH masters were verified and
closed with client-only keepalives; no server SSH/security change occurred.
Credentials/env contents were excluded from exported evidence and Git.

## Exact prior hosted acceptance

All five workflows at exact5c0d423b6212aa73fda322f6e7a8c855d6504d5e passed:
API43506966976, browser43506966432, containers43506966468, source43506966806
and images43506966655. API1493 passed with3 explicit native-console opt-in skips
and no warnings; browser185 passed. Both container jobs passed, including real
signed incoming-file scanning and6-object matching restore/current ACL proof.
Seven nonempty hash-verified image reports contained no reported vulnerabilities.

Complete logs/artifacts,216 API/18 infrastructure/264 combined source hashes,
all290 combined successful commands and66 infrastructure commands were verified;
only intentional negative infrastructure commands9/63 returned nonzero. There
were no error annotations. The279-entry CRC-verified archive has SHA256
02d397ca51d97a3c4f5f9535ea42421ffac898298b3f7b37a7569be43d9312cc.
The old184/1 run and its unavailable row metadata remain retained. These gates
cover the earlier schema/browser correction, not the subsequently added API.

## Protected API and reciprocal history

Source9a4587464ce18b50ed8891b22365e2ca36363c96 implements both-endpoint read/
update authorization, canonical ticket-before-work locks and explicit refreshed
work columns/assignments. Protected POST/DELETE intents include both original
versions and IDs. Delayed unlink replay cannot delete a later relink; historical
link replay cannot recreate a removed link. Current authority precedes receipts.
No-op changes neither aggregate nor events; effects atomically advance both and
record two strict events. Either overflow, native constraint, second-event or
receipt failure rolls back all effects. State, ownership and deadlines stay
independent.

Both direction lists and choices apply current SQL scope before pagination.
Both activity feeds require current readable counterpart and recorded customer/
queue/project context before LIMIT; unlink history needs no surviving join.
The worker validates and projects each of four strict event families once.
No note/file grant, hidden count, broad worker privilege or dependency is added.

| Scope | Actual result and limit |
| --- | --- |
| Required10-module native PostgreSQL suite |208 passed in692.81s,0 skips/warnings;73 new cases included |
| Privacy/freshness mutation check |Three expected failures; exact restoration followed by8 focused passes |
| Concurrency |Separate HTTP/DB clients observed real lock waits for revoke/archive/reassign/transition/logout; refreshed assignment denial covered |
| Native static/schema |Ruff,format172,mypy65,Alembic upgrade/drift passed |
| Generation |OpenAPI/TypeScript generated twice, repeat byte-identical; web check passed |
| Independent backend review |Quality approved0 Critical/Important; one Minor HTTP200 declaration omission corrected below |

Correction657167ddc31ca6e8dd0c364b2b64b0dfd8e4d6cc adds only POST HTTP200
response metadata and its generated OpenAPI/TypeScript entries, preserving201.
Actual native contract assertions failed with KeyError200 before the correction,
then confirmed both statuses use TicketWorkReceipt. Removing just the new200
entry makes the entire OpenAPI equal to9a. Repeat generation/web check and native
Ruff/format/mypy passed; the two existing creation/replay/delayed-intent tests
passed in11.21s without skips/warnings. The unchanged208-case behavior evidence
was reused. Scoped re-review approved M1, with no new or remaining finding.

FastAPI query models remain native typed inline operation parameters, matching
existing filters. Eight JSON DTOs are generated named components; no unused query
components were added. This is a recorded generation clarification, not a missing
typed query contract.

The user-selected altvia-vm ran new private capped PG/Redis/API and offline
generation fixtures, nonroot, with pinned existing tool images and no public
ports or host/security changes. Windows remained canonical; remote published main
and old fixtures/data/evidence were preserved. Real persistent native Windows
OpenSSH sessions were verified and closed; Git-SSH master checks alone were not
treated as proof of actual multiplex reuse.

Root verified all536 Git source bytes, all82 original plus6 correction native
raw/map records, both sets of6 generation records, and29/39 final checker file hashes.
All303 original and81 correction archive members matched extracted proof.
Every final native source/checker/config map stayed unchanged during its check.
Archive SHA256 values:

- Original:593f15c15476284894a8cf0d2f6e63bf2e956dfe830f41f43fba6d45174d40c7.
- Correction:5a68c275d893055e967ec084c5d9d9b43a4573395018470d01d50bef43202782.

Retained failed attempts include the initial nonroot UV cache error before tests,
actual missing-route/unsupported-family RED, two early pytest cache warnings,
format preparation failures, a mypy internal error of unconfirmed cause, and a
constraint-test oracle expecting an exception where native HTTP returns503.
Writable private caches, corrected formatting and the accurate503/no-effects
assertion preceded final passing checks. Controlled mutation failures and archive/
transport preparation errors also remain preserved; none is counted green.

## Remaining gates

Observe current exact-source hosted workflows and continue the real Operate
panels, browser recovery/accessibility/visual checks and packaged relationship
recreation/current-ACL proof. Obtain independent task and whole-increment reviews.
Link lifecycle remains independent; task creation/automation/unified My Work
require the next contract. Passing native backend checks alone does not close
manual-link feature acceptance.

Minimum compatible API/worker readers, guarded contraction and retained-history
privacy remain required. Actual encrypted backup/compatible-image rollback and
final integrated x86-64-v1 qualification remain separately assigned; native
development checks do not close those gates. No production rollout, real import,
provider/retention/customer mapping/SLA policy or Zammad retirement is implied.
