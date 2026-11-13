# Same-client ticket/work links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver persisted, authorized manual N:N links between existing same-client tickets and work items, with reciprocal browser views and independent lifecycle.

**Architecture:** Extend the modular monolith using the existing three composite keys, domain ACL helpers, identity serialization, aggregate versions and protected receipts. Emit two strict reciprocal events and filter counterpart authority in SQL before history pagination. No automation or My Work changes.

**Tech Stack:** Existing Python 3.12/FastAPI/Pydantic/SQLAlchemy/PostgreSQL/Alembic; Next.js/TypeScript/TanStack Query/Playwright; existing worker/outbox. No new dependency.

**Spec:** docs/adr/0039-ticket-work-links.md, master specification and affected
ADR0007/0020/0021/0028. Contracts precede code.

**State:** Task1 schema atb4c31e5 is independently approved after84 remote tests
with0 skips/warnings and native lint/type/Alembic checks. Separate test-only
project-manager correction9a3e225 has source approval and controlled/canonical
browser proof. Exact full current hosted gates remain pending; Tasks2-4 are not
implemented. See docs/ticket-work-link-evidence.md. Incoming-file development is accepted
at62dbeeb/closure6dd5eb2. Use one implementer and independent task reviews, then
one final whole-increment review. User's existing main/noPR/continuous-work
instructions supersede routine approval or execution-choice pauses.

## Global Constraints

- "Same client is mandatory, not a configurable policy or an inferred client mapping."
- "A link grants no read/write scope, account membership, note permission, file access, sender verification or delivery authority."
- "No state, assignee, priority, due date, completion timestamp, SLA field, message or participant is copied or synchronized."
- "API SELECT/INSERT/DELETE only on this table; no UPDATE and no worker grants."
- "All identity columns are NOT NULL."
- "No-op leaves both versions/timestamps/events unchanged."
- "Current permission always precedes saved receipt disclosure."
- "Do not modify legacy POST fingerprints."
- "No generic updated/assigned event is emitted" for relationship effects.
- "No subject, title, descriptions, reasons, names, contact data or body" in link events.
- No totals; page default50/max100 and actor/resource/filter-bound cursor.
- "Final target qualification remains consolidated after development; no VM operation belongs in this increment."
- No Elasticsearch/OpenSearch/Solr/MongoDB/vector/local-model additions or ISA requirement beyond x86-64-v1; never `-march=native`.
- Preserve tracked user changes, ASCII prose, parent stop points and existing publication authorization. No production deployment, import, SSH/security change or Zammad retirement.

## Review Focus

1. RF1: Delayed successful unlink retry after later relink acknowledges the original receipt without deleting the new relationship; changing either reviewed version under the same key conflicts. Task2/Task3.
2. RF2: Hidden counterpart events at the first page boundary reveal no ID, timestamp, count or cursor contribution; readable unlink history survives removal of the live link. Task2.
3. RF3: Forged internal/cross-client joins or parent identity changes fail native FK enforcement, including NULL bypass attempts, without partial aggregate effects. Task1/Task2.
4. RF4: Reassignment, revocation, archive, closure and logout around a two-parent mutation preserve current authority, finite lock completion and no duplicate/version-overflow effects. Task2/Task3.
5. RF5: Committed response followed by failed refresh/session replacement exposes no stale actionable state; retained history remains private after API/PostgreSQL recreation. Task3/Task4 prove this feature boundary. Pre-link API/worker images are prohibited by the recorded compatibility contract; actual compatible-image rollback rehearsal remains a required consolidated integrated-hardening gate.

---

## File map and execution boundaries

Task1 independently delivers an empty-schema expansion under the reviewed contracts with real SQL/privilege tests. Task2 delivers the full API/event/read contract through actual PostgreSQL. Task3 delivers usable browser integration through real HTTPS. Task4 delivers packaged persistence, whole-increment review and exact-source acceptance evidence; it is validation, not a new feature subsystem. No automation scaffolding.

New production files: `apps/api/altvia/ticket_work.py` (pair locking, SQL policy and effects), `ticket_work_schemas.py` (DTOs/query/header documentation), `ticket_work_api.py` (protected HTTP); `apps/web/src/lib/ticket-work.ts` (generated-type transport), `apps/web/src/components/ticket-work/links.tsx` (two scoped panels and local review/recovery). No general relationship framework or unrelated router split.

Modified native owners: models.py:473/654, provision.py:40, admin_http.py:105, activity.py:307, ticket_api.py:684, work_api.py:468, main.py:202; browser tickets/detail.tsx:27, work-items/detail.tsx:20, generated contracts. Leave activity_api.py:36 generic pagination unchanged. Existing work_items.py:86/113/127, tickets.py:148/172/213, project_registry.py:29 and work_queries.py:24/35 supply authority, involved predicate and FTS.

Reserved migration: `apps/api/migrations/versions/b46087000028_ticket_work_links.py`, down_revision=`b46087000027`; ADR: `docs/adr/0039-ticket-work-links.md`. If another change occupies either number, resolve it in the contract before source.

## Runner and fixture contract (NOT executed here)

Commands run at repository root. `apps/api/tests/conftest.py:25` requires an already configured isolated database named altvia_test and ALTVIA_ALLOW_TEST_DB=1; fixtures truncate it. Never guess credentials, print secrets, use production or parallelize destructive fixtures against one DB. Reuse the parent's established launcher/environment. This preparation established no local launcher.

Actual commands from api-ci.yml/web-ci.yml:

```text
uv run ruff check apps/api
uv run ruff format --check apps/api
uv run mypy
uv run alembic -c apps/api/alembic.ini upgrade head
uv run alembic -c apps/api/alembic.ini check
uv run python scripts/export_openapi.py
pnpm --filter @altvia/web generate:api
pnpm web:check
pnpm web:build
```

Actual browser launcher: `uv run node apps/web/scripts/browser-test.mjs`. Accepts trailing Playwright args, owns migration/fixture/API/web/HTTPS/worker lifecycle, requires ALTVIA_PUBLIC_ORIGIN=https://127.0.0.1:3443, checks ports3000/8000/3443 and internally loads generated .env.browser-session. Do not separately run browser_fixture.py while another test owns the DB. Fixture generates credentials/sessions; never invent static launch credentials or print its file.

Full hosted workflows also use `sh scripts/ci_redis.sh` and `uv run python scripts/ci_file_storage.py start`, `verify`, `stop`, with workflow-owned variables. These are Linux job commands, not a Windows launcher proposal. Full local gates reuse the parent harness or report its absence. `uv run pytest -q --junitxml=.superpowers/api-tests.xml` requires incumbent native-file setup and explicit skip accounting; focused pass is not full acceptance.

### Task 1: Native schema and privileges under the accepted contract

**Files:** Create migrationb46087000028, `apps/api/tests/ticket_work_support.py`, `apps/api/tests/test_ticket_work_storage.py`; modify models.py, provision.py. Contract/status documents are controller-owned; preserve them during checks.

**Interfaces:** Produces models.TicketWorkItem with PK(ticket_id,work_item_id), required client_id/queue_id/project_id, relation_type Literal related, created_by and UTC created_at. Produces fixture LinkContext(ticket_id:UUID,work_item_id:UUID,project_id:UUID,client_id:UUID,queue_id:UUID), and make_link_context(client:TestClient,db_engine:Engine,seeded_user:UUID)->LinkContext. Compose test_tickets.setup/ticket, test_project_registry.project(...,customer=...), test_work_items.create_work and test_team_api.preconditions/sign_in. Existing setup_project helper creates INTERNAL work, so cannot establish a valid pair. Test implementation may follow incumbent untyped fixture conventions.

- [x] Step1: Confirm accepted ADR0039/plan, completed independent builder check and recorded controller preflight BEFORE source. Recheck full migration parentb46087000027 and reserved numberb46087000028. Contract promotion is controller-owned and must already be committed; do not repeat its commit or alter legacy contracts during a test.
- [x] Step2: Write test_native_ticket_work_same_client_and_null_guard (RF3): actual owner INSERT succeeds only for same client; work/project, ticket/client/queue, internal project and each nullable identity mismatch raises DBAPIError with no row. Add test_ticket_work_pair_unique_and_parent_key_restricted, test_ticket_work_runtime_privileges and test_empty_roundtrip_preserves_existing_parent_keys. Use real SQL, not mocked FKs.
- [x] Step3: Run `uv run pytest -q apps/api/tests/test_ticket_work_storage.py`. Expected red is missing model/table/privilege behavior; record actual diagnostic. Unavailable disposable DB is a blocker, not useful red.
- [x] Step4: Implement model/migration: reuse existing unique keys from migrations00010:13,00008:35,00024:15; three non-null RESTRICT composite FKs, pair PK, reverse(work_item_id,ticket_id) index, relation_type='related' CHECK and created_by actor FK. Add API SELECT/INSERT/DELETE only. No new customer column, cross-table CHECK or ownership trigger.
- [x] Step5: Implement downgrade lock-and-refuse for rows OR new event/audit/activity history OR link/unlink receipt namespaces, including after all links deleted. Add test_downgrade_refuses_unlinked_history_or_receipt with exact Task2 names and valid raw fixtures. Never drop earlier parent unique keys or restore stale privilege maps.
- [x] Step6: Run storage suite plus `uv run pytest -q apps/api/tests/test_runtime_provision.py apps/api/tests/test_work_storage.py apps/api/tests/test_tickets.py`, native lint/type/schema commands above. Expected exit0/no Alembic drift; retain warnings/skips. Fresh SQL/privilege review; stage only owned files and commit `feat: persist same-client ticket work links`.

### Task 2: Protected API, SQL lists and reciprocal activity

**Files:** Create ticket_work.py, ticket_work_schemas.py, ticket_work_api.py, `apps/api/tests/test_ticket_work.py`, `apps/api/tests/test_ticket_work_activity.py`; modify admin_http.py:105, activity.py:307, ticket_api.py:684, work_api.py:468, main.py:202, generated docs/contracts/openapi.json and apps/web/src/lib/api.generated.ts. Do not broaden ActivityOutput/ActivityEvent.

**Interfaces produced:**

- ReviewedLinkVersions(ticket:int,work_item:int), frozen dataclass; TicketWorkPair(ticket:Ticket,ticket_access:tickets.Access,work_item:WorkItem,work_access:work_items.Access), frozen dataclass; both in ticket_work.py.
- scoped_pair(db:Session,actor_id:UUID,ticket_id:UUID,work_item_id:UUID,*,write:bool=False)->TicketWorkPair: both readable scopes first and common client check; only writes require canonical ticket-before-work graph/row locks and refreshed current update authority on both ends.
  Existing work_items.scoped_work does not use populate_existing. The pair owner
  must deliberately expire/refresh or populate_existing under acquired locks;
  an initial read's identity-map instance is not proof of current locked values.
- change_link(db:Session,actor_id:UUID,pair:TicketWorkPair,*,linked:bool,now:datetime,correlation_id:str)->bool: caller authenticated/locked/compared versions; false for coherent no-op, otherwise active/closed validation, pair insert/delete, both advances and record_event calls; no independent commit.
- linked_work_query(actor_id:UUID,ticket_id:UUID)->Select[Any], linked_ticket_query(actor_id:UUID,work_item_id:UUID)->Select[Any], work_choices_query(actor_id:UUID,ticket:Ticket,filters:TicketWorkChoicesQuery)->Select[Any] in ticket_work.py: select authorized summary columns before paging with native predicates.
- link_activity_clause(actor_id:UUID,resource_type:Literal['ticket','work_item'])->ColumnElement[bool]: ordinary events pass; new events require current counterpart/context through EXISTS independently of live link existence.
- create_ticket_work_router(engine:Engine,settings:Settings)->APIRouter, _reviewed_versions(request:Request)->ReviewedLinkVersions, _scope(actor_id:UUID,parent_id:UUID,direction:Literal['work','tickets','choices'],filters:dict[str,object])->str in ticket_work_api.py. Reuse _cursor/_next_cursor and limit+1; SHA256 compact actor/parent/direction/normalized-filter canonical JSON; cursor max250, no title/q text in emitted token.
- Extend native _expected_version(request:Request,*,header:str='if-match',required_code:str='version_required',invalid_code:str='invalid_version')->int in admin_http.py, preserving all default behavior. New helper passes header='if-match-work-item', required_code='work_item_version_required', invalid_code='invalid_work_item_version'. Only new _reviewed_versions rejects duplicate header values before parsing with each header's invalid code.

**Exact DTOs:** Inputs extra=forbid/hide_input_in_errors. Reuse native UUID/status/Priority types; no copied enums. Names below generate TypeScript schemas.

| DTO | Fields |
| --- | --- |
| TicketWorkCreate | work_item_id:UUID |
| TicketWorkReceipt | ticket_id:UUID, work_item_id:UUID |
| TicketWorkListQuery | limit:int=50 (1..100), cursor:str/null max250 |
| TicketWorkChoicesQuery | List query fields plus project_id:UUID/null, q:trimmed str/null max200 |
| WorkLinkChoice | work_item_id,project_id UUID; project_name,title str; status work Status; priority Priority; version positive int |
| LinkedWork | WorkLinkChoice fields plus can_unlink:bool |
| LinkedTicket | ticket_id UUID; number decimal string; subject str; status ticket Status; priority Priority; version positive int; can_unlink bool |
| TicketWorkPage | items:list[LinkedWork],next_cursor:str/null,can_link:bool |
| WorkTicketPage | items:list[LinkedTicket],next_cursor:str/null |
| TicketWorkChoices | items:list[WorkLinkChoice],next_cursor:str/null,can_link:bool |

can_link means fresh ticket update+active/not-closed authority independent of results; candidate rows independently require work-update and active parents. Work-side exposes per-link can_unlink; add-link navigation stays on ticket detail. Lists show readable counterparts only; can_unlink requires both update permissions and active/new-effect eligibility. No hidden count/placeholder. Ticket number stays string.

Header OpenAPI constant IF_MATCH_WORK_ITEM in ticket_work_schemas.py is the native IF_MATCH structure with name=If-Match-Work-Item; routes explicitly advertise it alongside native IF_MATCH and IDEMPOTENCY_KEY.

**Routes:** GET /tickets/{id}/work-items; GET /work-items/{id}/tickets; GET /tickets/{id}/work-item-choices; POST /tickets/{id}/work-items body TicketWorkCreate; DELETE /tickets/{id}/work-items/{work_id} with no body. All under /api/v1. Mutations require Origin/CSRF, If-Match ticket, If-Match-Work-Item task and Idempotency-Key. Both versions quoted integer1..2147483647.

| Condition | Status/code |
| --- | --- |
| Missing ticket header | 428/version_required |
| Invalid/repeated ticket header | 422/invalid_version |
| Missing work header | 428/work_item_version_required |
| Invalid/repeated work header | 422/invalid_work_item_version |
| Missing/invalid idempotency header | 428/idempotency_key_required or422/invalid_idempotency_key |
| Key reused with changed canonical intent | 409/idempotency_conflict |
| Either fresh reviewed version stale | 409/version_conflict |
| Both readable but customer differs | 409/ticket_work_client_mismatch |
| Absent/hidden endpoint; forbidden readable action | 404/not_found;403/forbidden |

Existing active/closed/overflow errors remain domain-owned. Parse If-Match first, then companion header, preserving deterministic precedence. Unknown/repeated query values422; invalid cursor422/invalid_cursor through native owner. Inputs never echo foreign IDs/names.

Namespaces: ticket-work-link:{ticket_id} and ticket-work-unlink:{ticket_id}:{work_item_id}. _operation receives {ticket_id:str,work_item_id:str,ticket_version:int,work_item_version:int}; original versions ARE fingerprinted. _remember stores pair receipt, status201/200 for link and204 for unlink. POST replay200; DELETE replay204/no body/ETag. Fresh no-op link200/unlink204 saves receipt without advance/event; real insert201/delete204 advances both.

**Write order:** Origin -> identity advisory -> session/CSRF -> BOTH readable endpoints -> both update permissions -> ticket customer/team/queue/ticket locks -> work graph/work row -> refreshed permission/common-client -> parse both headers -> protected fingerprint/receipt -> saved result OR compare both current versions -> presence/no-op -> active/closed checks for actual effect -> change_link -> remember -> outer commit. All failure paths save neither partial effect nor receipt. Matching saved receipt does not reapply current presence, active eligibility or version equality. Current scope/common-client remains mandatory. No-op and replay may survive archived parents/closed ticket; a real effect cannot. Terminal task state does not add a new restriction.

**Events:** ticket.work_linked, ticket.work_unlinked, work_item.ticket_linked, work_item.ticket_unlinked. Dedicated TicketWorkEventPayload in activity.py: actor_id UUID, actor_kind Literal user, ticket_id/work_item_id/client_id/queue_id/project_id UUID, relation_type Literal related; no optional extras. Exact own aggregate/type, positive version and schema1. Two record_event calls share time/correlation, own advanced version, distinct UUIDs. Native consumer/ProcessedEvent projects once each. Preserve old expected-field sets/envelopes.

link_activity_clause joins current endpoint rows using safe UUID string comparisons on JSON fields, no unsafe casts; verify current same-client and recorded project/queue context. Add to BOTH feeds BEFORE activity_page and preserve note filtering. Never authorize history via live relationship existence. If hidden, suppress entire event, including time/actor/correlation and cursor contribution.

- [ ] Step1: Write test_link_two_versions_atomic_and_independent_states using make_link_context: insert201/minimal pair; both versions+1; state/priority/assignment/dates unchanged; exactly two audit/outbox events; same-key retry200/no effects; N:N uniqueness. Add complete matrix comparing native require_update behavior: both project membership halves, ceiling, internal project, team/admin/config-only, assigned-agent and manager combinations.
- [ ] Step2: Write test_link_unlink_relink_original_receipts (RF1): A link -> B unlink -> C relink -> retry B preserves C; retry A never recreates a later removed link; changing either version under same key409. Assert no-op receipt, fresh stale409, active vs replay ordering, unchanged old transition fingerprints. Include every header code/duplicate/missing combination from table.
- [ ] Step3: Run `uv run pytest -q apps/api/tests/test_ticket_work.py`; record missing-route/contract red. Implement DTOs/parser extension/pair/change helpers/routes and register router. No list or event placeholder is an accepted backend deliverable.
- [ ] Step4: Implement queries: reuse visible_projects projected manage boolean, tickets.visible, work_queries.involved and filtered(WorkFilters(q=...)). Candidate update predicate is manage OR (current direct agent role+membership AND involved), under full visible project/customer query; test parity with work_items.can_update across matrix. Apply both scopes, active eligibility, same client, project/q, already-linked exclusion BEFORE order/limit. Never enumerate one project page or filter rows in Python. Use EXISTS/batching to avoid N+1. Cursor binds normalized filters excluding limit/cursor; hidden project filter returns empty/no metadata; can_link remains independent of page.
- [ ] Step5: Write test_link_event_privacy_precedes_cursor_and_survives_unlink (RF2): hidden newest event plus visible event at limit1 yields visible row/no hidden next_cursor; revoke hides link/unlink metadata; absence of live link retains readable history; note/ordinary/foreign feeds unchanged. Add strict payload/aggregate/schema/version rejection and duplicate consume_event tests. Implement new family and BOTH feed predicates together.
- [ ] Step6: Write test_link_current_authority_and_concurrent_lifecycle (RF4), separate DB sessions/HTTP clients, finite waits and observed lock acquisition: link vs revoke/archive/reassign/work transition/logout has one coherent authorized ordering or denial, no deadlock/partial versions/duplicate. Write test_either_version_overflow_and_second_event_failure_rollback plus constraint injection (RF3). Owner raw writers are not declared serialized by HTTP lock; investigate an actual conflicting path before contract acceptance.
- [ ] Step7: Run `uv run pytest -q apps/api/tests/test_ticket_work.py apps/api/tests/test_ticket_work_activity.py apps/api/tests/test_ticket_work_storage.py apps/api/tests/test_tickets.py apps/api/tests/test_ticket_notes.py apps/api/tests/test_work_review.py apps/api/tests/test_work_discovery.py apps/api/tests/test_worker.py apps/api/tests/test_activity.py apps/api/tests/test_runtime_provision.py`. Require relevant pass/no unexplained skip, native lint/type/schema checks. Export/generate API; rerun generation with no second diff. Existing operations unchanged except documented extension.
- [ ] Step8: Fresh backend source review against RF1-RF4, downgrade, predicate parity and activity privacy. Stage owned files and commit `feat: expose protected ticket work relationships`. Record exact tested source/commands/results; no browser or whole-feature acceptance yet.

### Task 3: Operate panels and retained two-parent intent

**Files:** Create apps/web/src/lib/ticket-work.ts, apps/web/src/components/ticket-work/links.tsx, apps/web/tests/ticket-work.spec.ts; modify both detail.tsx and scripts/browser_fixture.py. Update accurate Impeccable surface briefs only as execution workflow requires. No new global route/My Work change.

**Interfaces:** createTicketWorkApi(csrf:string,onAuthError:(error:unknown)=>void) returns work(ticketId,cursor,signal?), tickets(workItemId,cursor,signal?), choices(ticketId,cursor,filters,signal?), link(intent:LinkIntent):Promise<TicketWorkReceipt>, unlink(intent:LinkIntent):Promise<void>. IDs string, cursor string/null, signal AbortSignal. work returns Promise<TicketWorkPage>, tickets Promise<WorkTicketPage>, choices Promise<TicketWorkChoices>, using Task2 generated DTOs. LinkIntent={operation:'link'|'unlink',ticketId:string,workItemId:string,ticketVersion:number,workItemVersion:number,key:string}, readonly. LinkFilters={project_id?:string,q?:string}. Use native createAdminTransport/versionHeader and merge ONLY companion header.

TicketWorkLinks({ticket:TicketRecord,session:WorkspaceSession,parentLocked:boolean,onBusyChange:(busy:boolean)=>void}) and WorkTicketLinks({work:WorkRecord,session:WorkspaceSession,parentLocked:boolean,onBusyChange:(busy:boolean)=>void}) in links.tsx. Existing parent detail blocks ordinary edits while child is reviewing/writing/refreshing acknowledged state; child blocks editing while parent owns mutation. Do not feed the child's own busy flag back into parentLocked and disable its recovery.

Query keys: ['ticket-work',ticketId,cursor], ['work-tickets',workItemId,cursor], ['ticket-work-choices',ticketId,normalizedFilters,cursor]. Fresh review fetches existing ['ticket',ticketId] and ['work-item',workItemId] detail versions with throwOnError. Use the existing useTeamWrite.perform promise as owner, typed perform(intent:LinkIntent):Promise<void>: validate POST receipt IDs match the intended pair (DELETE success is204), then await BOTH fresh detail reads (inactive counterpart through fetchQuery) and current link lists before resolving perform; invalidate both activity/choice collections. Native onSuccess then clears intent and runs confirmed only after those reads succeed. invalidateQueries alone does not establish fresh versions. Retain only the smallest session-bound acknowledged:LinkIntent|null after a known committed response, so a refresh failure can retry READS without sending the mutation again. If perform is retried with the same acknowledged key/pair/versions, skip the write and repeat paired reads; use the existing reconcile/read-retry path when native onError clears an intent for a definite read error. Keep controls blocked by this known-commit state until authoritative refresh succeeds or the session is disposed. Do not create a generic mutation framework, speculative pre-commit latch or new recovery protocol. A lost write response without acknowledgment still uses the original protected request/key. Session replacement unmounts state; late callbacks check isCurrent(). No localStorage/sessionStorage for customer intent.

- [ ] Step1: Before frontend execution, run Impeccable context once from project root: `& 'C:/Users/wagne/.agents/skills/impeccable/scripts/impeccable.cmd' context --target apps/web/src/components/tickets/detail.tsx` on Windows, or native launcher in supported shell. Read directives, PRODUCT.md, DESIGN.md and incumbent ticket/work briefs; inspect accepted screens. Read craft-floor immediately before UI edits. Context was NOT run by planning task; explicit no-services/dependency/write boundary remains. Preserve current Operate visual world.
- [ ] Step2: Extend browser_fixture.py with DEDICATED same-client link project/queue/client/requester and MANAGER, AGENT, VIEWER, TICKET_ONLY, WORK_ONLY actors. Use existing management/access/session functions with random identities and private generated file conventions. Export generated ALTVIA_E2E_LINK_{kind}_SESSION/account IDs and LINK_CLIENT_ID/PROJECT_ID/QUEUE_ID/REQUESTER_ID. Do not broaden existing fixture actors: ordinary work project is internal and shared actors have independent revocation tests.
- [ ] Step3: Write @ticket-work persisted reciprocal links preserve both lifecycles; @ticket-work delayed unlink recovery preserves relink (RF1); @ticket-work acknowledged write blocks until both refreshes succeed (RF5); @ticket-work session replacement disposes pending pair (RF4/RF5). Use real generated sessions/API, inject only controlled browser response loss/read failure, inspect state through actual API. Run `uv run node apps/web/scripts/browser-test.mjs tests/ticket-work.spec.ts` after required build/environment. Expected red is missing panel/behavior, not launcher failure.
- [ ] Step4: Implement generated transport and panels with native pagers/Button/plain text, useTeamWrite and WriteRecovery. Ticket panel: paged search/selection/review/link/unlink; work panel: reciprocal list/unlink/navigation to ticket detail for adding. Fresh details govern review; preserve BOTH original versions/key through uncertain/conflicting/forbidden replies. Page/filter/read failure never silently erases an uncertain write. 409 requires explicit successful reload/review before replacement. No optimistic state/count or automatic relink/reopen/claim/create.
- [ ] Step5: Integrate parent busy/refresh ownership narrowly in tickets/detail.tsx:27/:78 and work-items/detail.tsx:20/:32. Preserve note/message/file/delivery acknowledgment flows. Test lost POST/DELETE response, historical receipt with now-changed relation, stale either version, archive/closure/read-only, counterpart revocation/hidden page, keyboard focus and separate native status labels.
- [ ] Step6: Run `pnpm web:check`, `pnpm web:build`, focused browser suite, then `uv run node apps/web/scripts/browser-test.mjs tests/tickets.spec.ts tests/work-items.spec.ts tests/ticket-notes.spec.ts tests/ticket-messages.spec.ts tests/attachments.spec.ts`. Capture link/review/empty/error/recovery views at1440/390 widths, light/dark; require no horizontal overflow, axe WCAG2A/AA/2.1AA and keyboard submit/cancel/recovery. Inspect visuals, record actual paths/fixes, finish Impeccable documentation and fresh source review. Stage owned browser/fixture files and commit `feat: operate ticket work links in browser` after passes.

### Task 4: Packaged persistence, source freeze and whole review

**Files:** Create scripts/packaged_ticket_work_proof.py and docs/ticket-work-link-evidence.md; modify scripts/container_smoke.py at existing fixture/recreation points, roadmap and continuous ledger. Private evidence JSON contains no credentials/content. Existing five workflows normally need no edit.

**Interfaces:** prepare_ticket_work(client:httpx.Client,ticket_body:dict[str,Any],work_body:dict[str,Any])->dict[str,Any] creates dedicated synthetic records via API, links them, captures IDs/versions/status and original minimal replay intent in memory. assert_ticket_work(client:httpx.Client,proof:dict[str,Any])->dict[str,Any] checks recreated persistence, reciprocal reads, original receipt, unlink/no-op/relink, independent lifecycle and activity privacy. Proof never contains credentials. Reuse fresh legitimate authentication after revocation; do not assume old session remains valid.

Preparation insertion point: existing customer contributor work creation around container_smoke.py:1250 where same-client ticket_body/work_body exist. Do not mutate incumbent manual ticket/work records: post-recreation proof around:1577 asserts exact ticket version7/activity count8. Call assert_ticket_work from the legitimate actor's post-recreation fresh session. Preserve existing SMTP/IMAP/file evidence and failure history; add no runner flag/service.

- [ ] Step1: Add small packaged helper and wire before existing API/PostgreSQL recreation/after fresh authentication. Add orchestration unit test only if it proves a failure boundary rather than restating calls. Run `uv run ruff check scripts` and `uv run ruff format --check scripts`; actual packaged execution is behavior evidence.
- [ ] Step2: Prove feature-level RF5 retained-history privacy after the existing API/PostgreSQL recreation, including counterpart revocation and readable unlink history; retain Task1 guarded downgrade evidence. Record the minimum compatible API+worker SOURCE contract: API retains both-feed counterpart filtering, worker accepts and deduplicates new event families. Prohibit pre-link API/worker images; no purge or destructive contraction. Defer ACTUAL compatible-image pair rollback rehearsal, together with the already planned consolidated encrypted-backup/restore work, to integrated hardening in docs/plans/2026-11-11-mvp-completion.md. Register it explicitly as a required final gate, pending rather than waived. Current feature recreation proves retained state/current ACL, not image rollback. No disable switch or third restore protocol.
- [ ] Step3: After relevant packaged/affected checks pass, commit only proof helper/integration files as `test: prove ticket work packaged persistence`; freeze source with Git SHA, clean owned diff and exact commands/results/skips/warnings/artifacts. Obtain independent Task4 source review before publication. The final whole-increment review follows all exact hosted gates and covers spec, native FK authority, SQL privacy, lock/replay/overflow, browser acknowledgment and API+worker compatibility. Fixes require affected revalidation and scoped re-review. Review silence alone is not validation evidence.
- [ ] Step4: Publication follows parent authorization only. Observe all five hosted workflows at EXACT runtime SHA: API checks, Browser checks, Container checks (api-runtime AND private-file-runtime), Source security, Service image security. Actual incumbent commands: `uv run python scripts/container_smoke.py`, `uv run python scripts/container_smoke.py --files`, `uv run python scripts/private_file_infra_proof.py`, `node --test scripts/packaged_file_browser.test.mjs`; scanner commands are owned by source-security.yml/image-security.yml. Let workflows supply credentials/runtime. Preserve full relevant failure logs, not only first symptom; distinguish explicit native skips from failures.
- [ ] Step5: Record exact source/run/artifact IDs, real relationship recreation/browser/visual/SQL/privacy evidence, minimum compatible API+worker source contract, security findings and limitations. Explicitly record actual compatible-image rollback rehearsal as pending consolidated integrated hardening; do not claim rollback success from recreation. Only mark manual-link development complete after required feature gates; integrated-hardening rollback and final target gates remain pending. Evidence-only commit identifies unchanged tested runtime SHA. Stage evidence/ledger and commit `docs: record ticket work link validation`. The controller obtains final whole-increment review after these gates, records all dispositions and decides acceptance/next contract; automation/My Work requires its next contract.

## Exact assertion anchors for the named test steps

These are assertion excerpts, not new helpers or executed tests. Each named test
arranges its native fixtures in its owning task; the variables below are its
actual SQL/API/browser observations. Keep the full tests in those tasks, not here.

Task1 test_native_ticket_work_same_client_and_null_guard (RF3) and privilege test:

```python
assert valid_insert_count == 1
assert invalid_insert_count == 0
assert rejected_sqlstate in {"23502", "23503"}
assert app_privileges == {"SELECT", "INSERT", "DELETE"}
assert worker_relationship_privileges == set()
```

Task2 test_link_unlink_relink_original_receipts (RF1), privacy test (RF2), and
current-authority/concurrency/atomicity tests (RF3/RF4):

```python
assert first_link.status_code == 201
assert retry_unlink.status_code == 204 and retry_unlink.content == b""
assert current_links.json()["items"][0]["work_item_id"] == str(context.work_item_id)
assert changed_work_header_same_key.json()["code"] == "idempotency_conflict"
assert changed_ticket_header_same_key.json()["code"] == "idempotency_conflict"
assert page.json()["items"] == [visible_event]
assert page.json()["next_cursor"] is None
assert hidden_event_id not in page.text
assert after_failed_write_versions == before_failed_write_versions
assert after_failed_write_event_count == before_failed_write_event_count
assert saved_receipt_after_revocation.status_code in {401, 403, 404}
assert every_concurrent_future_finished_within_timeout
```

Task3 acknowledged-refresh/session tests (RF5), after real POST acknowledgment
and controlled counterpart read failure:

```typescript
await expect(linkReviewSubmit).toBeDisabled();
await expect(retryAuthoritativeRead).toBeEnabled();
expect(writeRequestsAfterReadRetry).toBe(writeRequestsAfterAcknowledgment);
expect(originalWriteHeaders["If-Match-Work-Item"]).toBe(reviewedWorkEtag);
await expect(oldSessionCounterpartTitle).toHaveCount(0);
```

The separate lost-write-response case has no known committed receipt: assert its protected retry preserves originalWriteHeaders and original key. That is distinct from the acknowledged read-only retry above.

Task4 retained-state/current-ACL recreation assertions (RF5), not image-rollback evidence:

```python
assert before_recreation_link_pairs == after_recreation_link_pairs
assert hidden_counterpart_event_ids.isdisjoint(returned_activity_event_ids)
assert projected_count_by_event == {identifier: 1 for identifier in link_event_ids}

```

## Self-review and hard stops

Spec coverage: SQL/grants/downgrade Task1; locks/two-version intent/independent state/API/privacy/worker Task2; actual browser/recovery/session/Operate Task3; packaged recreation/current ACL/minimum compatible API+worker source contract/exact-source whole review Task4. Actual compatible-image rollback rehearsal remains assigned to consolidated integrated hardening and is a required pending final gate, not feature-level success. RF1..RF5 each maps to explicit tests/evidence. Names/signatures consumed later are declared; fixture and packaged helpers are PROPOSED, not asserted existing.

Native simplifications: method-agnostic _operation/_remember handles DELETE without new receipt table; existing advance/require_update/require_active, cursor, FTS and involved predicate; two events fit one-row projection. No broad role/worker grant, relationship aggregate/UUID, browser route, dependency or automation scaffold.

Review decisions: exact second-header error names; summary DTO/capability names; narrowly parameterized native parser; SQL parity with native work eligibility; real owner writers sharing identity/graph order. These are finite engineering choices under ADR0039, subject to the builder gate. Activity counterpart privacy, compatible API+worker source retention and the deferred consolidated rollback rehearsal are requirements. No requirement is waived by deferring image rehearsal.

Stop source work until selected contract/builder-check/preflight are recorded. Stop on incompatible current source, actual lock-order counterexample, absent authorized disposable runner, failing native invariant/privacy/replay or required check. Report concrete blocker; never fabricate results, alter old expectations to hide regression, grant extra scope or install a new engine. No production rollout, real import, target qualification or subagent dispatch by this preparatory worker.
