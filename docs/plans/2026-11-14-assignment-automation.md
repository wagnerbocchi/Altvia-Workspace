# Durable assignment automation implementation plan

> For agentic workers: use superpowers:executing-plans inline, task by task, with
> one fresh independent whole-increment review at the end. Do not spawn implementers.

Goal: implement ADR0041's real structured assignment-to-work action, durable
triage/recovery and scoped browser configuration, preserving manual contracts.

Architecture: atomic native assignment staging, separate PostgreSQL execution
lease/effect receipt and one registered Dramatiq consumer. Reuse native ticket,
project/work/link authority and locks; retain the existing activity consumer.
Tech stack: installed Python/FastAPI/SQLAlchemy/Alembic/PostgreSQL/Redis/Dramatiq
and Next.js/TypeScript/TanStack Query. No dependency/service addition.
Spec: docs/adr/0041-durable-assignment-automation.md, with master4.2/8.1 and ADR0004.
The independent builder questions are resolved in the ADR before source. The
user's continuous execution/direct-main authorization supersedes routine plan
approval/execution-choice pauses. Real policy questions stay in roadmap.

## Global constraints

- x86-64-v1 mandatory; never -march=native or mandatory AVX/AVX2/SSE4.2.
- No Elasticsearch/OpenSearch/Solr/MongoDB/vector/local-model runtime.
- No arbitrary rule code, production rollout, real import or destructive retention.
- Stable business identity (rule_id,action_id,ticket_id); one immutable action.
- Ticket before project graph/work row; identity723504391 before auth/effect.
- Current source AND target authority before counterparts/history/page metadata.
- Preserve all schema1/manual event shapes, protected fingerprints and receipts.
- Impeccable for frontend; existing Twenty-inspired Operate/light/dark system.
- Isolated actual DB fixtures only. Finish development before final VM qualification.

## Review focus

1. Off/on after claim: an older captured revision remains cancelled by the durable
   disable floor, even with an unexpired old token. Task1/Task2.
2. Intentional unlink or default-project change after success: no recreated edge,
   changed owner or second work across revision/reassign/reopen/replay. Task2.
3. Work-only reader: truthful automated creation without private execution/source
   ID, and no reciprocal hidden ticket history before LIMIT/cursor. Task2/Task3.
4. Last-active/current authorizer/assignee grants revoked while queued: no event
   actor or historical receipt becomes permission for a new effect. Task2.
5. Adopting a hidden/ambiguous pre-existing link: generic triage, no hidden count,
   arbitrary candidate selection or duplicate work. Task2/Task3.

## Task 1: Persisted finite rules and atomic assignment staging

Files: extend apps/api/altvia/models.py and provision.py; add
apps/api/migrations/versions/b46087000029_assignment_automation.py;
add automation_schemas.py, automation_rules.py and automation_api.py under
apps/api/altvia; extend identity.py, ticket_api.py, activity.py, main.py;
add apps/api/tests/test_automation_rules.py and test_automation_migration.py.
Update docs/contracts/api.md and architecture/data-model.md before source.

Interfaces: AutomationRule, AutomationRuleRevision, AutomationExecution and
AutomationEffect model names; RuleCreate/RulePatch/RuleOutput/RuleReceipt;
create_automation_router(engine: Engine, settings: Settings) -> APIRouter;
stage_assignment(db: Session, event: OutboxEvent, ticket: Ticket) -> None.
identity.record_event retains existing arguments and returns the created
OutboxEvent; only _assigned uses that return to stage in the same transaction.

HTTP (all /api/v1):

| Route | Strict behavior |
| --- | --- |
| GET /ticket-queues/{queue_id}/automation-rules | Required unique client_id UUID plus limit/cursor; authorize full config conjunction; page by UUID; no total |
| POST same collection | Body client_id,title,priority,ticket_statuses; fixed enabled=false; queue If-Match and Idempotency-Key;201/minimal queue_id,client_id,rule_id;replay200 |
| GET /ticket-queues/{queue_id}/automation-rules/{rule_id} | Full current conjunction; RuleOutput+ETag(rule); reviewed queue_version included |
| PATCH same detail | Nonempty enabled/title/priority/ticket_statuses, no null; If-Match(rule),If-Match-Queue,Idempotency-Key;200/minimal receipt, including replay; read fresh detail afterward |

RuleOutput: id,queue_id,client_id,action_id,version,queue_version,enabled,title,
priority,ticket_statuses,authorizer_id,cancelled_through_version,created_at,updated_at.
PATCH protected fingerprint includes both original versions, full immutable route
and canonical body; replay never re-enables after a later disable. All current
scope/action checks and valid header syntax precede receipt disclosure; only new
intents compare current versions. Revisions include complete immutable action.
Real create/edit advances queue once; no-op records its intent without changes.
POST duplicate scope409 automation_rule_exists, stale409 version_conflict,
hidden/absent404, readable forbidden403, missing428, invalid422. New action edits
require active parents; disable and committed replay survive archive.
All lists limit1..100/default50, actor/parent/client-bound cursor, unique known
query fields only. Name/ID alone supplies no grant. No DELETE endpoint.

- [x] Write real native tests first for missing tables/routes; prove actual RED.
  Include rule scope/action uniqueness, revision snapshot/invalid enums/array
  duplicates, composite effect/source FK mismatches, paired lease/state/attempt
  checks, SQL runtime immutable-column denial and empty/populated downgrade guards.
  Preserve schema1 rows and older migration behavior. No test database shared.
- [x] Implement migration/model/explicit grants with no enabled records. Include
  ActivityEvent actor CHECK expansion, constrained to the three schema2 types;
  all old actor shapes preserved. API receives only intended rule/revision/job
  writes; no worker domain writer grant until Task2's actual caller is implemented.
- [x] Add API tests for every conjunct/non-grant, scoped list and hidden parent,
  strict bodies/query/header grammar, archived disable/no-op, parent/child versions,
  protected uncertain POST/PATCH and rollback of queue/revision/audit/receipt.
- [x] Implement native configuration owner and private metadata event validation.
  Global identity lock precedes auth; native client then team/queue then rule.
  Every real disable advances monotone cancelled_through_version to new revision;
  reenable preserves it. Ordinary edit retains earlier staged snapshots.
- [x] Prove enabled assignment stages exactly one job/source/revision atomically
  through create/patch/claim/native-mail create; disabled/no rule stages none.
  Force enqueue/audit failure and assert ticket/version/history/event rollback.
  Protected replay emits no second job. Old manual event JSON remains exact.
- [x] Implement stage_assignment at the actual _assigned owner, controlled flush
  for the real event UUID and strict schema/context validation, never a time scan.
- [x] Run native new modules plus queue/ticket/mail/link nearest regressions;
  uv run ruff check apps/api; uv run ruff format --check apps/api; uv run mypy;
  migration head/metadata gates. Expected: real pass, explicit limits retained.
  Export OpenAPI/types with installed commands and web check; preserve legacy
  operations/components. Commit coherent schema/config/staging batches.

## Task 2: Native atomic effect, lease recovery and truthful activity

Files: add apps/api/altvia/automation_execution.py, automation_events.py,
automation_execution_api.py and work_creation.py; migration30 adds the restricted
source view needed by actual API recovery without base-outbox reads; extend
work_api.py, work_items.py, tickets.py, ticket_work.py, identity.py, activity.py,
activity_api.py, provision.py, worker.py and automation_schemas.py/automation_api.py;
add tests/test_automation_execution.py and test_automation_activity.py.

Interfaces: immutable identity.AutomationOrigin(execution_id: UUID);
identity.record_event(..., origin: AutomationOrigin | None = None) -> OutboxEvent;
work_creation.create_record(db, actor_id, permission, body: WorkCreate, *, now,
correlation_id, origin=None) -> WorkItem shared by real manual and worker callers;
ticket_work.change_link retains existing parameters and adds origin=None.
Manual origin=None preserves exact incumbent envelopes, timestamps and receipts.
Metadata-only loading at native scoped owners excludes eager private text/contact/
account hash and external-label relationships without changing permission/locks.
The automation caller requires native project manage, guaranteed only after live
client-management/ceiling checks; assignee still separately passes contributors.

automation_execution.claim_due(engine, now, limit=20) -> list[tuple[UUID, UUID]];
publication_failed(engine, execution_id, token, now) -> bool;
consume(engine, execution_id, token, now) -> bool.
One registered assignment_work actor receives UUID strings only; database row,
current unexpired token and validated source own truth. No broker-side retries.
Use native30s/8attempt/5..900s+jitter policy; SIGTERM stops dispatch and drains.

GET /tickets/{ticket_id}/automation-executions: limit/cursor page before which
current source and any mapped target visibility is enforced. ExecutionOutput:
id,rule_id,action_id,rule_version,source_event_id,state,attempts,error_code,
created_at,updated_at,version,can_retry,effect nullable {work_item_id,project_id,mode}.
Hide the whole mapped row when the target is unreadable. No total/token/payload.
POST /tickets/{ticket_id}/automation-executions/{execution_id}/retry: no body;
execution If-Match and Idempotency-Key;202 rescheduled minimal execution_id,200
committed replay. New intent only triage/dead, full current config conjunction,
active/current-source eligibility, disabled/fenced/superseded refusal409. No
revision/source/effect replacement; replay cannot revive a later cancelled run.

- [x] First prove actual RED for pending job having no task effect. Exercise
  exactly-one creation/adoption, independent lifecycle/priority/due, no private
  ticket text copied and no implicit project/account/grant.
- [x] Extract the real manual work creation/history/event owner and reuse it;
  run existing manual creation/fingerprint/event/agent restrictions unchanged.
  Extend reciprocal event owner with typed origin, strict schema2 projection,
  ActivityEvent actor CHECK, source/effect validation and DTO provenance redaction.
- [x] Prove full stable-key matrix across new event IDs/revisions/reassign/reopen,
  two workers, crash before/after commit, after publish before ack, Redis outage,
  expired/mismatched tokens, manual unlink/relink, changed default and version
  overflow. Off/on with a delayed unexpired token must cancel old work; new
  post-enable assignment may use the later revision. No forced new-work path.
- [x] Implement current-authorizer/domain/active/assignee resolution under native
  ticket-before-graph locks, immutable effect receipt and atomic new work/link.
  Existing usable link adopts without a version change; ambiguous/hidden target,
  missing/inactive default or denied authorizer goes to bounded private triage.
- [x] Prove current source/project/queue/ceiling/authorizer/assignee revocation,
  platform/team non-grants, unsupported/corrupt event/schema, actual worker-role
  denied password/hash/note/message/raw/owner/role writes. Add only exact metadata
  reads/row-lock/version columns and INSERT grants needed by executed native calls.
- [x] Implement dispatch/claim/fence/backoff/DLQ and scoped protected retry. Prove
  disabled/revision-floor authority precedes effects, and hidden rows contribute
  no data/count/cursor. Prove work-only creation is truthful without execution/
  source IDs; reciprocal history after unlink still requires both scopes.
- [x] Run all new/affected API/worker/activity/privacy/migration tests and static
  gates. Expected: pass with unchanged frozen source. Export contracts/types and
  verify manual schema1/legacy operations. Commit coherent worker/privacy batches.

## Task 3: Actual rule configuration and scoped recovery interface

Files: add apps/web/src/lib/automation.ts and components/automation/{rules,runs}.tsx;
extend native queue detail/router/screens for a scoped client-selected rule form;
extend ticket detail with a native paged automation outcome panel; extend work/
ticket activity labels for actor_kind automation without displaying private IDs.
Add apps/web/tests/automation.spec.ts and guarded scripts/browser_fixture.py cases.

Interfaces: generated RuleOutput/ExecutionOutput/Page/Receipt only;
createAutomationApi(csrf,onAuthError) with scoped list/detail/create/patch/runs/retry
using existing abortable authenticated transport and protected intent owner.
No hand-maintained duplicate DTO, client-side authorization or worker trigger.

- [x] Run Impeccable context workflow before UI; preserve DESIGN.md/Operate tokens.
  Write real API/browser RED first. Native client choices must expose only current
  authorized client-manager scopes; selected client does not establish permission.
- [x] Build actual disabled create, review/enable/edit/disable with both versions,
  protected retry of uncertain intents and fresh GET after acknowledgement. Show
  action meaning and that disabling fences older queued revisions. Keep create
  mounted independently of list pagination/errors. Never populate real policy.
- [x] Build scoped actual execution/triage/retry, target links and truthful native
  automation labels. Preserve manual activity strings and task/ticket independence.
  Test creation, assignment, delayed worker effect, adoption and recovery through
  actual API/PG/Redis launcher; no mocked successful business action.
- [x] Prove keyboard/focus, pending/empty/error/retry/conflict, uncertain protected
  intents, both revisions, identity replacement and delayed old response disposal.
  Capture390/1440 both themes, overflow/axe and inspect actual renders together.
  Test work-only hidden ticket/execution IDs in network responses and displayed UI.
- [x] Run new and affected browser modules, web check/build/native guard, resolve
  source/visual defects. Expected: pass with real screenshots, no synthetic totals.
  Commit coherent interface/test/documentation batch.

## Task 4: Packaged recovery and development acceptance

Files: extend the existing packaged relationship proof at its responsible native
actor boundaries or add scripts/packaged_automation_proof.py to keep ownership
clear; connect it to scripts/container_smoke.py without weakening old assertions.
Add docs/assignment-automation-evidence.md; update ADR/roadmap/continuous ledger.

- [ ] Prove actual configured disabled/no-rule behavior then explicit synthetic
  enable/assignment creates exactly one native task/link/effect. Recreate API/PG/
  worker and Redis; replay/new assignment preserves receipt and manually removed
  edge. Current revocation retains no hidden ticket/execution metadata. Native
  schema2 activity is projected exactly once. Preserve incumbent singleton canaries.
- [ ] Run appropriate full packaged/static/native guards. Preserve exact source/
  config/dependency input hashes, commands, logs, failures and narrow proof limits.
  Expected: actual pass, not a theoretical compatibility claim.
- [ ] Publish authorized main commits and observe all five exact-source hosted
  workflows, both container jobs and seven actual image inventories. Run complete
  relevant failing logs through diagnosis if any check fails; no skip called pass.
- [ ] Obtain one independent whole-increment source/visual review; resolve every
  Important/Critical once with actual RED/GREEN and passing affected/full gates.
  Record all rulings and evidence, then accept only this development increment.
- [ ] Continue SLA as the next separate contract. Keep real Q-23 policies,
  compatible-image rollback/encrypted restore and final integrated x86-64-v1
  qualification open; no production rollout/import/retirement is implied.

## Self-review

Master4.2/8.1 staging/resolvers map toTask1/Task2; singular logical effects and
independent lifecycle toTask2; visible scoped triage/recovery toTask2/Task3;
actual restart/redelivery/least privilege toTask2/Task4. Every review focus names
its native/browser owner. Interfaces and version headers agree across tasks.
One action/lifetime rule avoids speculative general automation machinery while
preserving ADR0004's stable business identity and future explicit new-work boundary.
