# Ticket/work link development evidence

Updated2026-11-13. ADR0039 and the four-task plan are selected. Task1 schema at
b4c31e5 has independent source approval and real remote PostgreSQL proof. The
separate existing browser-oracle correction9a3e225 also has source approval.
Exact current full hosted acceptance is pending. Manual link API/events/UI,
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

## Remaining gates

Publish the reviewed source and observe all five exact-source hosted workflows,
including both container jobs. Record full failures/skips/warnings/artifacts;
the historical184/1 run is not relabeled green. Then continue Task2 API, current
both-endpoint authorization, two reviewed versions/protected link+unlink,
strict reciprocal events/privacy before pagination, followed by the real Operate
panels and packaged relationship proof. Link lifecycle stays independent.

Minimum compatible API/worker readers, guarded contraction and retained-history
privacy remain required. Actual encrypted backup/compatible-image rollback and
final integrated x86-64-v1 qualification remain separately assigned; native
development checks do not close those gates. No production rollout, real import,
provider/retention/customer mapping/SLA policy or Zammad retirement is implied.
