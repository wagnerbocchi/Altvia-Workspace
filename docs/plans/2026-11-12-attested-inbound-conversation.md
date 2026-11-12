# Attested incoming conversation implementation plan

> Execute task by task with superpowers:subagent-driven-development. Continue
> under the user's existing MVP/direct-main authorization; record real policy
> questions without stopping independent safe development.

**Goal:** Publish explicitly classified/attested incoming mail, promote it through
current staff authority and preserve safe incoming/outgoing conversation threads.

**Architecture:** Extend the existing monolith with one scoped immutable case
projection and private origins, then immutable incoming conversation records.
Existing owner quarantine, ticket authorization/replay and SMTP remain the owners.

**Tech Stack:** Existing Python3.12/FastAPI/SQLAlchemy/PostgreSQL/Redis/Next.js,
standard-library bounded email parsing. No dependency/service addition.

**Spec:** docs/adr/0036-attested-inbound-conversation.md, master specification.

## Global constraints

- No live provider, real identity attestation/import, production rollout or SSH.
- Preserve x86-64-v1 and all prohibited-dependency/native-tuning restrictions.
- Runtime never reads source/raw/poll/private preview/origin/evidence tables.
- Case read needs current queue role plus explicit client ceiling; administration
  or team membership grants neither. Fresh promotion uses current action authority.
- Identity write lock before session authentication; ordered parents, relevant
  cases, ticket, contact. Owner publication uses source before case, never reverse.
- Old draft/note/manual/delivery fingerprints and event envelopes stay exact.
- Case is per-message attestation, never a global contact/account verification.
- Never send/convert private notes; no automatic mail from incoming promotion.
- Network work stays outside DB transactions; all case/ticket/receipt/events atomic.
- Real Q03/Q16 trust/provider policy remains external; no fictional mapping/grant.

## Review focus

- Foreign claimed IDs must not poison an existing customer anchor or reveal it.
- Same-context conflicting anchors must not disappear through writer filtering.
- A late collision on any duplicate alias must invalidate the shared case, even
  when an old capture binary makes the change; retain promoted history.
- First SMTP reply must include original eligible incoming ID; ordinary clients
  need not echo X headers and missing Message-ID must not become a fabricated ID.
- A saved receipt must survive case completion/invalidation while current case
  AND resulting-ticket authority still guard it; retain exact original HTTP intent.

### Task 1: Classified case publication and scoped read API

**Files:** Create apps/api/migrations/versions/b46087000023_attested_mail_cases.py,
altvia/mail_routing.py, mail_cases.py,
mail_cases_owner.py, mail_case_schemas.py, mail_case_api.py,
tests/test_mail_routing.py and tests/test_mail_cases.py. Extend models/provision/
main/mail_intake/activity and the bounded root-header entry point in mail_mime.
Export OpenAPI and TypeScript through existing exporters.

**Interfaces produced:**

- Frozen RoutingHeaders: message_id:str|None, in_reply_to:str|None,
  references:tuple[str,...], thread_token:str|None, from_email:str.
  parse_routing(raw:bytes)->RoutingHeaders raises fixed RoutingError only.
- attest_case(engine,variant_id,contact_id,contact_version,evidence)->CaseReceipt,
  owner-only explicit ALTVIA_ALLOW_MAIL_CASES=1 command. Receipt gives case_id,
  current state, disposition primary/alias/collision and replayed; no content.
  revoke_case(engine,case_id,expected_version) preserves history. Metadata inspect
  may return version/state/parser status/IDs, never body/header/evidence.
- mail_triage_cases owns body/context/routing/state/version. Migration00024 adds
  actual promotion receipt fields/FKs and the promoted state;00023 has no dangling
  incoming UUID or placeholder receipt/capability. mail_case_origins owns immutable
  variant/hash/evidence/intent provenance.
  A malformed/outbound-ID-conflicting publication is refused without publishing
  or acknowledging a classification; raw stays quarantined. Same-key conflicting
  verified origins are durable and invalidate the existing case.
- GET /api/v1/mail-cases, limit1..100/default25, cursor bound to actor+filters,
  optional queue_id/client_id/state; list omits body and routing internals.
  GET /mail-cases/{id} gives scoped subject/body/contact snapshot/current state
  and version. Hidden404. Task1's real independently testable outcome is owner
  publication/scoped reads; Task2 adds actual promotion eligibility/candidates,
  not placeholder capability fields or fake mutation endpoints.

Routing_v1 exact bounds: reuse16384-byte root headers/2048 physical line/100 fields.
ASCII ID<=320: angle brackets around dot-atom local part and DNS domain (labels
1..63 ASCII alphanumeric with internal hyphens, total domain<=253); local atoms
use RFC atext letters/digits and !#$%&'*+-/=?^_`{|}~, joined by single dots.
Preserve ID case. Missing ID allowed; malformed/duplicate present ID rejected.
In-Reply-To at most1 ID; References at most64 IDs separated by folding whitespace;
no comments/obsolete quoted/domain-literal forms. Thread token optional64 lowercase
hex. From exactly1 mailbox, optional Sender/Reply-To exactly1 each and all matching
the attested current ASCII mailbox. Reject non-no Auto-Submitted, null Return-Path
and report/DSN forms. No broad header codec trust or external fetch.

- [ ] RED actual PG/source/variant/parser2 publication/read API. Pin immutable
  body/context, contact version/email/activity checks, owner-role/opt-in denial,
  runtime raw/origin/evidence denial, missing/malformed/hostile routing limits.
- [ ] Implement contextual unique key source/client/contact/email/Message-ID,
  nullable-ID primary-only cases, exact alias versus changed-wire contradiction,
  immutable provenance and source/version/private event transaction. No expected
  source version: unrelated capture traffic must not invalidate immutable review.
- [ ] Add source->case SQL collision trigger covering ANY alias origin and old
  capture writes, stable case order, permanent invalidation/version overflow,
  no reverse customer/ticket lock or old payload change. Test races/atomic rollback.
- [ ] Cover foreign-context same-ID independence, own reserved outbound-ID refusal
  without poisoning outbound, per-variant reclassification refusal, revocation,
  archived parents/contact, pagination/filter/hidden resource and guarded rollback.
  Reserve existing server-generated outbound IDs regardless of queued/preparing/
  transmitting/accepted/failed/uncertain state; only accepted rows route replies.
  Refused publication creates no acknowledged origin/case and leaves raw quarantine.
- [ ] Run affected real PG tests plus routing/MIME/intake/runtime/activity, lint,
  FORMAT/mypy/security/build/migration drift and generated contracts. Commit checked
  owner/read boundary after independent task spec+quality review.

### Task 2: Protected create/append/reopen and thread-preserving conversation

**Files:** Create apps/api/migrations/versions/b46087000024_incoming_conversation.py,
mail_promotion.py, tests/test_mail_promotion.py;
extend case schemas/API/service, tickets/ticket_api/models/provision/activity,
mail_delivery and tests. Regenerate OpenAPI/TypeScript.

**Interfaces produced:**

- POST /mail-cases/{id}/promotion, If-Match and Idempotency-Key. Strict create body
  action=create, subject1..300, priority, optional category_id/assignee_id. Context
  comes from case; description empty. Strict append body action=append,ticket_id,
  ticket_version>0,reopen:boolean,reopen_reason<=2000|null. No arbitrary body,
  sender/client/queue/contact/evidence/actor fields. Minimal receipt case_id,
  ticket_id,incoming_message_id;201 fresh,200 protected replay.
- immutable ticket_incoming_messages references its case and same ticket/client/
  queue, has unique case and ticket version, received/recorded times and staff
  recording actor. Body/original subject live once in case; historical sender
  snapshots never FK-bind to a mutable current requester.
- GET /tickets/{id}/conversation: discriminated incoming/outbound records ascending
  ticket version, limit1..100/default50, actor/ticket-bound cursor. Incoming gives
  scoped snapshot sender/text/subject/times/fixed invalidation warning. Outbound
  wraps existing TicketMessageOutput/delivery status. No notes/raw/evidence/token.
  Keep old /messages strictly outbound-only.
- GET /tickets/{id}/incoming-messages/{incoming_id} checks current ticket and
  matching parent before returning the incoming record,404 hidden/mismatched.
  The browser uses this authoritative receipt read independently of pagination.
  Case detail now adds actual can_create/can_append/safely correlated candidate
  fields, never a hidden target identity or a placeholder capability.
  Summary/detail add current client_name/queue_name through the same scoped
  parent joins, without requiring client-registry roles or creation choices.
- resolve_candidate(db,case,actor_id) resolves all same-context known incoming or
  accepted outbound anchors before action filtering. Include all relevant case
  locks in stable order and re-resolve invalidation after lock. Foreign/unknown
  strings confer no authority or special error; all-known-own conflict fails.

- [ ] RED actual API creation/append/reopen, known anchor+unknown/foreign ancestors,
  two-own-ticket ambiguity, invalid own anchor, token mismatch/absence and same-queue
  different source. Check contact/email changes, participant requirement, current
  staff role/assignment/ceiling/session, hidden parent and linked row negatives.
- [ ] Extract only the shared creation/history responsibility from manual create;
  reuse creation_access, self/unassigned restrictions and validation AFTER replay.
  Source is an internal manual/email argument, not a new manual body field.
  Reuse _event/_assigned, advance/transition with narrow optional DB timestamps for
  new incoming actions; preserve all old defaults/fingerprints/field sets.
- [ ] Implement atomic versions: new ticket/history1 then incoming2; append next;
  explicit permitted reopen next then incoming following. Require real reason,
  existing queue flag/targets and current action authority. No automatic state
  sync, arbitrary new-ticket bypass of a recognized thread or implicit participant.
- [ ] Protect replay with current case and resulting ticket/action authorization
  before minimal receipt, fresh version/eligibility only on new effects. SQL unique
  case prevents another key/message. Test committed/uncommitted replay, race,
  collision-before/after, event rollback/version exhaustion and mixed locks.
  Fingerprint the original case If-Match version AND complete body. Create replay
  reuses current creation/self-assignee checks plus resulting ticket read scope;
  append replay requires current target write authority. In particular, creation
  of an unassigned ticket must not make its own successful receipt unrecoverable.
- [ ] Extend freeze reference query to eligible promoted incoming and accepted
  outbound IDs in the current contact/frozen-recipient context, latest16
  chronological except first-reply earliest incoming root plus latest other15,
  preserving exact eligible outbound-only ordering
  and existing wire. Prove actual first reply In-Reply-To/References, missing-ID
  limitation, >16 incoming before first reply, changed-requester exclusion,
  invalidated anchor exclusion and no foreign IDs/private text. Identical aliases
  after promotion keep the same Case/receipt/incoming row; version their promoted
  private alias event explicitly as schema2 while preserving ready schema1.
- [ ] Run full affected PG/mail/ticket/activity/runtime/migration/static/build/
  contract gates. Independent task spec+quality review, then coherent checked commit.

### Task 3: Real attested triage and incoming/outgoing browser conversation

**Files:** Create web mail-case route/components/lib/tests; extend service-desk
navigation and ticket conversation using generated API types, existing send/status
and protected intent owner. Add only guarded disposable owner fixtures as needed.

**Interfaces consumed:** Task1 scoped cases; Task2 strict promotion receipt and
conversation union; existing ticket creation category/assignee choices and sender/
requester/send/status APIs. No HTTP owner attestation backdoor.

- [ ] Run user-required Impeccable context/craft floor, preserve incumbent Operate
  world, define surface brief. Only published owner-attested cases appear; empty
  and readonly states explain real next actions without raw counts or inert controls.
- [ ] Exact immutable text/contact/client/queue review; new subject/priority and
  bounded choices, safe correlated target/reopen reason. Preserve original
  case/key/version/body and target ticket version through HTTP/ownership failures.
  Receipt acknowledgement reads actual case+ticket/incoming record before new
  writes; real session/CSRF loss clears private state. No optimistic promotion.
- [ ] One conversation display with incoming and public outbound, current delivery
  states/review/composer reused; notes retain their own permission/layout/body.
  Per-message attestation wording never claims a verified global contact/account.
- [ ] Real PG/API/Redis/TLS browser new-request/reply/reopen/restart, missing ID,
  long escaped text, foreign/readonly/hidden cases, note separation, uncertain HTTP
  and receipt recovery. No fabricated status/promotion endpoints. Keyboard/axe/
  desktop/mobile/light/dark capture and independent Impeccable review/documentation.
- [ ] Check/build/generated comparison, affected then frozen full browser; do not
  edit source/fixtures or rebuild .next during tests. Independent source gate and
  checked UI commit. No provider/target operation.

### Task 4: Complete synthetic integration and immediate private-files stage

- [ ] Fresh whole-increment source review, consolidated fixes with RED/GREEN and
  scoped re-review; preserve earlier outgoing clock/privacy/restart evidence.
- [ ] Packaged IMAPS capture/parser2/owner attestation/scoped HTTPS creation,
  separate requester attestation, real TLS first reply references, verified
  correlated incoming append/explicit reopen, duplicate/collision/role/private
  denial and API/PG restart. Use separate fixtures, preserve old exact assertions.
- [ ] Publish checked source, inspect all five exact CI gates/full logs/nonempty
  security reports and sanitized hashed artifact archive. No per-slice target SSH.
- [ ] Update roadmap/evidence/completion ledger, immediately select the private
  object-storage/fail-closed scanning contract and continue. No continuation prompt.
