# Versioned ticket SLA implementation plan

> For agentic workers: use superpowers:executing-plans inline, task by task.
> Do not spawn implementers. Obtain one fresh whole-increment review at the end.

Goal: real scoped SLA configuration, preserved first-response/resolution cycles,
business-time evaluation and visible truthful outcomes under ADR0042.

Architecture: freeze native eligibility in ticket transactions; evaluate immutable
history and authoritative durable acceptance facts in the existing DB worker.
Use native metadata predicates, protected receipts, generated DTOs and Operate UI.
Stack: installed Python datetime/zoneinfo, FastAPI/Pydantic, SQLAlchemy/Alembic,
PostgreSQL and Next.js/TypeScript/TanStack Query. No new dependency/service.
Spec: docs/adr/0042-versioned-ticket-sla.md; master FR-011/012 and8.3.
The user's delegated continuous development supersedes routine approval pauses.
Q07 actual calendars/targets remain unconfigured; no production activation.

## Global constraints

- x86-64-v1 required, no -march=native, AVX/AVX2/SSE4.2 mandatory dependency.
- No Elasticsearch/OpenSearch/Solr/MongoDB/vector/local-model runtime.
- Existing manual/schema1 events, protected receipts and actual transport stay exact.
- Authoritative ordinary acceptance is durable accepted_at, not network-observation
  time. UI must disclose delayed-finalization limits; no inferred backdating.
- Policy/calendar snapshots survive edits, disable, archive and authorizer exit.
- Current ticket scope gates every outcome, event, page and cursor.
- Integer microseconds and aware UTC; frozen installed TZif, no arbitrary upload.
- No source workbook/credentials/private logs in Git. Preserve unrelated work.
- Impeccable for frontend; reuse Twenty-inspired Operate/light/dark design.
- Final consolidated target qualification follows MVP development.

## Review focus

1. A final SMTP250 before resolution but durable accepted_at after it must not
   invent earlier fulfillment. Task3 pins this selected clock and Task4 explains it.
2. A previous-cycle draft sent after reopen must not fulfill the new cycle even
   at an equal wall timestamp; use native message.ticket_version. Task3.
3. Late owner acceptance evidence can correct a derived outcome but cannot delete
   a breach/history row or duplicate a correction under retries. Task3/Task5.
4. A selected archived category/calendar must fail new freeze without fallback,
   while existing captured cycles continue without content grants. Task2/Task3.
5. A long/poison cycle or an extreme calendar must not monopolize the worker,
   disclose stale results as current or exhaust its memory. Task1/Task3/Task5.

## Task 1: Exact, bounded frozen-calendar arithmetic

Files: add apps/api/altvia/business_time.py and tests/test_business_time.py.
No route, DB migration or user-facing policy is introduced by this foundation.

Interfaces: frozen Window(weekday,start_minute,end_minute), FrozenZone(name,tzif,
sha256), CalendarSnapshot(zone,windows,holidays), DeadlineProgress(through,
remaining_us,due_at). freeze_timezone(name: str) -> FrozenZone;
build_calendar(zone, windows: Sequence[Window], holidays: Sequence[date]) ->
CalendarSnapshot; intervals(calendar, utc_day: date) -> tuple[(datetime,datetime)];
elapsed_us(calendar,start,end) -> int; advance(calendar,start,budget_us,end) ->
DeadlineProgress. Constructors/build validate exact finite input; no bool as int.

Rulings: requests cover at most32 UTC civil dates, wholly in2000..2099;
oversized/naive/reversed spans are rejected, never truncated. Zero span is valid.
advance reports bounded progress/remaining budget when the deadline lies beyond
the requested end, rather than searching without bound. A zero budget completes
at start; a positive budget ends exactly at the closing boundary when equal.
The caller persists continuation; no hidden moving clock or fixed company hours.

Compute actual UTC-minute segments across each UTC day. Compare local eligibility
and offset at the segment ends; when a boundary/transition splits it, inspect the
60 integer-second subsegments, then coalesce contiguous working intervals.
Installed TZif transitions have integer-second resolution; partial query seconds
are exact interval intersections. Repeated local minutes count both occurrences;
skipped local minutes/dates contribute none. This handles historical non-minute
offsets without guessing an ambiguous local boundary. Cache at most16 parsed TZif
objects and256 immutable UTC-day interval results, never mutable DB/session data.

- [x] Write a missing-behavior RED for a real work window's exact elapsed time.
  Then cover ordered/touching/overlapping windows, holiday/local midnight,
  weekends, partial microseconds and exact/zero budgets, bounds and invalid TZif.
- [x] Implement trusted installed timezone capture: IANA membership, bounded
  read from native TZPATH or installed tzdata resource fallback, path traversal
  denial and SHA256 verification before ZoneInfo.from_file. No new package.
- [x] Prove US gap/fold partial windows, Australia/Lord_Howe half-hour shifts,
  Pacific/Apia skipped date and Africa/Monrovia historical-second offset behavior
  where within the supported range (otherwise use a trusted synthetic TZif fixture
  purely to exercise arithmetic, never exposed through HTTP).
- [x] Implement canonical frozen windows/holidays and exact interval engine;
  reject duplicates/overlap and coalesce touching windows. No fabricated defaults.
- [x] Run all pure cases with installed Python, Ruff/check/format/mypy. Native
  repeat on the selected isolated host must include cold32-day evaluation and
  repeated shared/distinct snapshot benchmarks, recorded bounds/cache sizes and
  unchanged inputs. Commit this foundation without claiming complete SLA.

## Task 2: Real scoped calendar and policy configuration

Files: add sla_schemas.py, sla_configuration.py, sla_api.py and
migrations/versions/b46087000031_sla_configuration.py; extend models.py,
provision.py, main.py and activity.py. Add configuration/migration/API tests.
Extract queue_client_configuration.py from actual automation_rules.access only
for the two real callers, preserving RuleAccess alias/semantics as necessary.
Update docs/contracts/api.md, architecture/data-model.md and security requirements
with exact tables/fields/ACL before migration/runtime source.

Interfaces: CalendarCreate(client_id,name,timezone,windows,holidays,active),
CalendarPatch(nonempty subset without null); PolicyCreate(client_id,category_id?,
priority?,name,calendar_id,calendar_version,first_response_minutes,
resolution_minutes,approach_minutes,pause_states), fixed disabled creation;
PolicyPatch(nonempty enabled/name/calendar pair/targets/approach/pause subset).
Selectors and scope are immutable. Pydantic forbids extra fields, duplicate
window/holiday/pause values, NUL, repeated/unknown query and caller TZif bytes.

CalendarOutput: id,client_id,queue_id,version,queue_version,name,active,timezone,
windows,holidays,tzif_sha256,can_edit,created_at,updated_at. No raw TZif in HTTP.
CalendarSummary omits windows/holidays/hash; collection pages use summaries to
avoid multiplying1000-holiday payloads by the page limit.
PolicyOutput: id,client_id,queue_id,category_id,priority,version,queue_version,
enabled,name,calendar_id,calendar_version,targets,approach,pause_states,
authorizer_id,can_edit,created_at,updated_at. Native choices expose only this scope.
Receipt: calendar_id or policy_id with queue/client IDs, never full private data.
Lists/Page follow ADR0042 limit/cursor, required unique client_id and no total.

Use ADR0042 nested collection/detail routes. POST queue If-Match; PATCH own
If-Match plus If-Match-Queue; all protected by Idempotency-Key. Preserve original
canonical body/versions/key across retry. Current scope precedes saved receipts;
new actual changes advance queue and own version once; no-op/replay does not.
Policy calendar_id/version are an explicit reviewed pair; check both current
calendar eligibility and existence/scope of that immutable revision.

- [x] Native actual RED before tables/routes. Prove composite customer/queue/
  calendar/category integrity, null-aware selector uniqueness, immutable revisions,
  insert-only exact runtime grants, populated downgrade refusal and empty roundtrip.
- [x] Implement only the four live configuration tables in31. No empty cycle
  scaffold, seeded calendar, enabled policy or fictitious hours. Later32 adds the
  cycle/evaluator tables when their actual owner is implemented.
- [x] Prove full current role conjunction/non-grants, strict bounds, initial
  disabled state, version overflow rollback, no-op/archive-disable/replay and
  protected uncertain create/patch. Delayed replay must preserve newer revisions.
- [x] Implement native owner, minimal protected receipts, metadata-only private
  configuration events and explicit scope choices. Current selector helper ranks
  exact > category > priority > default, then validates current selected references.
- [x] Run affected automation/queue/client/config/schema regressions and static
  gates. Generate OpenAPI/TS twice and compare all old operations/components.
  Commit complete persisted configuration without claiming cycle support.

## Task 3: Native cycles, evaluator and first accepted response

Files: add sla_cycles.py,sla_execution.py,sla_events.py,sla_read_api.py and
migrations/versions/b46087000032_ticket_sla.py; extend models.py,provision.py,
ticket_api.create_record,tickets.transition,worker.py,activity.py and main.py.
Add native cycle/worker/acceptance/privacy/migration tests. No SMTP function or
old delivery envelope changes are needed: reuse actual durable accepted_at.

Interfaces: freeze_cycle(db,ticket,history) -> None at actual
new-ticket and resolved/closed -> open owners only. Same-state/committed replay
does not call it. Capture accepted events with separate processed_events consumer
sla_acceptance_v1, independently of activity status; no delivery-time watermark.
capture_acceptances(engine,limit=20) -> int; evaluate_due(engine,limit=20) -> int.
Both are bounded DB-only operations called in the existing main worker loop.

The internal sla_clock owner supplies immutable HistoryPoint/ClockProgress and
bounded step results for the two actual response/resolution goals. It consumes
integer microseconds and native ordered history; it has no account, transport or
HTTP authority. Each goal gets at most16 UTC dates (actual plus future search)
and499 history rows per pure step. The DB owner uses498-row pages and reserves
up to four native start/resolution/last-progress facts, remaining within32 dates/
1000 ordered history rows per cycle. Future search retains
its own anchor, through instant and remaining budget; a new actual observation
does not restart a long search. A relevant pause/resume invalidates only a future
projection, retaining an actual deadline already reached. Equality is on time;
only business elapsed greater than the target breaches. An early terminal goal
needs no invented future deadline. Unknown, reversed or discontinuous native
history fails timing_inconsistent. No-op same-instant progress still advances
native history version. Partial history never grants a projection past unseen rows.

Persist the two actual goal progress records in a constrained ticket_sla_goals
child keyed by(ticket_id,cycle_number,goal), rather than duplicate response_*/
resolution_* columns or opaque mutable JSON in ticket_sla_states. Goal is the
fixed first_response|resolution set, not an extensible workflow vocabulary. This
adds one private relational table with no new user resource, seed or endpoint.
Define its exact columns/ACL/atomic counters in the data model before migration32.

Use the cycle/event tables in ADR0042. Persist fixed response/resolution progress
fields separately: evaluated_through_at,last_history_version,current_status,
elapsed_us,deadline search through/remaining,fulfilled_at and outcome. A real
first-response candidate change resets only that goal's derived progress to cycle
start, retaining observed history. Bounds per evaluation:32 UTC dates and1000
ordered status rows; continuation updates atomically. Same-time history advances
by native version. Nonmonotone native source times yield timing_inconsistent,
never invented elapsed. No-loop/poison failure advances next_check with a safe
state so other cycle IDs remain eligible.

Native message.ticket_version in [cycle_start_version,cycle_end_version) owns
draft membership; accepted_at must also lie in the cycle's UTC range. Capture
current min accepted fact, exact existing event shape and matching delivery row.
Use a restricted source view for delivery/message version/timing metadata, never
grant body access. Processed receipt, invalidation and private rejection/error
metadata commit together. Ended cycles can be awakened by late accepted evidence
without polling every historical cycle forever. Unique logical breach and
correction keys retain every observed event. No source actor becomes permission.

GET /tickets/{id}/sla returns current nullable cycle plus paged prior cycles,
next_cursor and server observed_at. Cycle: number,start_at,end_at,policy/calendar
labels/revisions/timezone/initial selector or unconfigured,state,computed_through_at,
evaluated_at,safe_error,first_response and resolution nullable goal summaries.
Goal: status,target_minutes,elapsed_business_seconds,remaining_business_seconds,
due_at,fulfilled_at,breached_at,corrected. Integers round elapsed down/remaining up;
internal microseconds are exact. Stale/evaluating/unavailable must remain explicit;
reads do not recompute/write. Legacy tickets without a tracked cycle return
current:null; their first later tracked reopen is SLA cycle1, not invented history.

- [x] RED native create/reopen atomic snapshot and missing real evaluator effect.
  Cover policy selection/fallback refusal, current category/priority snapshot,
  no-policy/legacy, reference archival and authorizer exit with current read denial.
- [x] Implement current same-scope freeze after native history flush. Roll back
  ticket/history/events/receipts on snapshot/config failure. No old envelope change.
- [x] RED/GREEN business-clock pause/resume/exact deadline, independent goals,
  accepted versus draft/queued/uncertain/private/incoming, old-cycle delayed draft,
  resolution without response, late owner evidence and preserved corrections.
- [x] Implement native serialized evaluator/event projection and exact credential
  grants. Identity precedes client/team/queue/ticket then cycle; no cycle-first
  inversion or mail transport row lock change. Worker cannot mutate ticket state.
- [x] Prove competing workers, rollback/crash/redelivery, historical wake-up,
  invalid source/long/poison isolation, bounded caches and metadata privacy before
  page/cursor. New validated sla_worker activity is truthful and exposes no private
  delivery/source IDs. Preserve manual/schema1 metadata and historical rows.
- [x] Run full affected native/manual-mail/worker/privacy/storage tests, static
  gates, repeated contract export and package build. Commit coherent owners.

## Task 4: Actual Operate configuration and outcome interface

Files: lib/sla.ts, components/sla/{calendars,policies,cycles}.tsx; queue detail
and ticket detail integrations; tests/sla.spec.ts and guarded browser fixture.
Consume generated DTOs and existing authenticated transport/write recovery.

- [x] Impeccable context/local-extension workflow; actual missing-control RED.
  Reuse existing system. Explicit client selection supplies no backend grant.
- [x] Build real timezone/week windows/holiday revision forms and disabled policy
  create/review/enable/edit/disable. Show reviewed selector order, both versions,
  future-cycle boundary and frozen calendar. Never prefill company policy.
- [x] Build real current/history goal outcomes, paused/approaching/breached/
  fulfilled/unfulfilled/corrected/unconfigured/legacy/stale/unavailable states.
  Explain durable acceptance timing; no browser clock invents a deadline.
- [x] Retain original protected intent through uncertain writes; acknowledged
  writes retry reads only. Parent failure owns parent recovery; unavailable child
  panels must not duplicate parent alerts or offer ineffective private retries.
- [x] Prove real API/PG/worker behavior, identity replacement, error/conflict/
  keyboard/focus, both themes and390/1440 axe/overflow/captures. Inspect actual
  renders, apply only real fixes, run affected browser/check/build/native guard.
  Complete Impeccable review/documentation and commit scoped UI/proof.

## Task 5: Packaged acceptance and next independent stage

Files: dedicated packaged SLA proof through existing container_smoke boundaries,
docs/ticket-sla-evidence.md, roadmap and continuous completion ledger.

- [x] Prove synthetic explicit configuration, actual accepted public response,
  pause/resolve/reopen, late evidence correction and once-only breach/event under
  API/PG/worker/Redis recreation with actual installed images and restricted role.
  Preserve all incumbent canaries and the automation proof. No production policy.
- [ ] Run full packaged/static/native gates; freeze exact source/dependency/
  configuration/image identities and retain complete private success/failure logs.
  Reconcile prior intermittent SMTP child exit rather than silently calling it fixed.
- [x] Obtain one fresh independent whole-increment source/visual review. Resolve
  Important/Critical in one RED/GREEN fix pass and run required regression gates.
- [ ] Publish authorized main commits and observe all five exact-source workflows,
  both Container jobs and seven nonempty image inventories. No timeout/skip is pass.
- [ ] Accept only the development capability, retaining Q07/real policy, integrated
  rollback/encrypted restore and final target qualification. Continue analytics/
  guarded importer under a separate contract; no real import or rollout.

Task5 progress: native packaged05 passed the complete771.557s command,37682 frozen
inputs,29 verified evidence files, native SMTP/pause/reopen/late correction and
once-only projection after recreation. The later host-proof health wait is newer
than that native snapshot; all shipped image inputs are unchanged. Native148
harness cases with real TLS S3, local Node-child proof,19 SLA/automation browser
cases and static gates pass. Fresh whole-increment review's sole Important
category-continuity issue has actual RED/GREEN proof; no minors were deferred.
Prior full Impeccable visual acceptance and four new inspected paging captures
remain separately attributed. Exact final hosted workflows, both strengthened
Container commands and all seven inventories remain pending before acceptance.
