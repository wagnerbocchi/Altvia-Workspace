# Data model and planned migrations

Design contract for the complete product. Applied development schema is limited
to identity, team/idempotency and ADR-0017 activity migrations; other tables below
remain planned. Execution evidence is in the Phase 1/1C reports, not this ERD.
UUID primary keys unless stated. Timestamps
are TIMESTAMPTZ in UTC; business calendars name an IANA timezone. Mutable
aggregates have positive integer version and created_at/updated_at. State
values use CHECK constraints for incremental migration, not silent free text.

```mermaid
erDiagram
    users ||--o{ sessions : owns
    users ||--o{ role_bindings : granted
    roles ||--o{ role_bindings : scopes
    roles ||--o{ role_permissions : allows
    permissions ||--o{ role_permissions : defines
    teams ||--o{ team_members : contains
    users ||--o{ team_members : joins
    clients ||--o{ client_contacts : has
    clients o|--o{ projects : scopes
    teams ||--o{ projects : owns
    projects ||--o{ project_members : includes
    projects ||--o{ work_items : contains
    users o|--o{ work_items : owns
    work_items o|--o{ work_items : parent
    work_items ||--o{ work_item_assignees : involves
    clients ||--o{ tickets : owns
    client_contacts ||--o{ tickets : requests
    ticket_queues ||--o{ tickets : routes
    tickets ||--o{ ticket_messages : contains
    tickets ||--o{ ticket_work_items : links
    work_items ||--o{ ticket_work_items : links
    tickets ||--o{ ticket_sla_states : times
    sla_policies ||--o{ ticket_sla_states : snapshots
    business_calendars ||--o{ sla_policies : governs
    mailboxes ||--o{ inbound_messages : receives
    ticket_messages ||--o| outbound_messages : delivers
    attachments ||--o{ attachment_links : protects
    outbox_events ||--o{ processed_events : deduplicates
    automation_rules ||--o{ automation_executions : executes
    import_batches ||--o{ import_rows : stages
```

Diagram shows core cardinalities. Table definitions below also cover supporting
entities. Dotted operational domains are not implied shared authorization.

## Applied Foundation activity projection

Migration b46087000005 adds activity_events and processed_events, plus the safe
outbox last_error_code. This is the first real consumer of existing identity/team
events; ticket automation remains Phase 4. processed_events has composite primary
key (consumer,event_id) and an outbox foreign key. activity_events uses event_id
as its primary/foreign key, bounded typed resource/actor metadata, aggregate
version, UTC occurrence, correlation ID and allowlisted JSON details. Its
(occurred_at,event_id) index owns descending cursor ordering. Projection,
deduplication and delivered status commit together under the locked outbox row.

Neither table is an editable audit replacement. API can read activity only;
separate worker credentials own the insert/deduplication and processing columns.
No data purge is introduced. Downgrade refuses populated new tables instead of
erasing durable history. ADR-0017 and docs/phase-1-closure-evidence.md contain
implementation decisions, preservation proof and exact acceptance evidence.

## Identity and scope

| Table | Essential columns and database guarantees |
| --- | --- |
| users | id, email_normalized UNIQUE, display_name, password_hash nullable for future OIDC, active, auth_version; no source-name provisioning |
| sessions | id, user_id FK, token_hash UNIQUE, csrf_hash, created/expires/last_seen/revoked_at; opaque token never stored plaintext |
| teams/team_members | team UUID/name/active/version/created_at/updated_at; PK(team_id,user_id), active membership with timestamps; identity roster never grants content access |
| roles/permissions/role_permissions | Stable unique names; PK(role_id,permission_id); role changes audited |
| role_bindings | user_id, role_id, scope_type, nullable client/project/team/queue FKs; CHECK matches exactly one scope or permitted global platform role; unique binding indexes for nullable scopes |
| client_access_grants | PK(user_id,client_id), granted_by, created_at; explicit ceiling on access to that client's content |
| idempotency_records | actor_id, route, key, request_hash, resource/status/result, expires_at; UNIQUE(actor_id,route,key); no sensitive response body unless encrypted/restricted |

Applied Phase 1C-c role_bindings is deliberately narrower than the complete-product
table above: UUID id, user_id/role_name FKs, scope_kind, nullable team_id FK.
CHECK permits only global/platform_admin without team or team/viewer and
team/operations_manager with team. Partial UNIQUE(user_id,role_name) for global
and UNIQUE(user_id,role_name,team_id) for team plus a user lookup index preserve
global semantics and allow repeated role names on distinct teams. ADR-0010 owns
that initial slice. Project/queue scopes remain unimplemented.

Applied Phase 2A migration b46087000006 adds clients with UUID/name/active/positive
version/UTC timestamps and client_access_grants with composite user/client PK,
restrictive FKs, nullable granted_by and UTC created_at. role_bindings adds client_id;
its CHECK permits exactly one global/team/client scope. A client scope accepts only
viewer or operations_manager, with UNIQUE(user_id,client_id). Both a ceiling and
a binding are required; neither record alone authorizes a read. Existing team/global
semantics and every earlier row are preserved. No default_project_id, contacts,
areas or projects are created speculatively.

The activity constraint now accepts resource_type=client. The existing projection,
deduplication key and worker privileges are reused; identity reads explicitly filter
identity/team resources. Client reads authorize the parent before applying a
client-bound cursor. Populated client/history tables refuse downgrade before DDL.
Rollback preserves the expanded schema/data and a compatible worker (ADR-0018).

Contact and internal-user identities are distinct. OIDC subject/issuer mapping
is deferred until IdP is known; never join accounts by unverified email alone.
`client_access_grants` is an intentional addition to make the client's ceiling
explicit and prevent team/project grants from revealing another client.

## Projects and work

Phase 2C migration b46087000008 adds work_items, work_item_assignees,
work_item_comments and work_item_status_history under ADR-0020. Parent scope uses
a composite FK and self CHECK; a DB trigger serializes hierarchy changes through
the project advisory lock and rejects cycles/immutable project changes. API takes
identity then project then task locks. Enum/title/version/state/date constraints
and native timezone boundary validation guard persisted task shape. Comments and
status history are append-only; worker has no task-table access. Comment paging
uses (work_item_id,created_at,id); state paging uses unique (work_item_id,version).
Populated work/history refuses destructive downgrade. Current task response names
join only actual assignment records and use select-in batching for participants.
Date boundaries use the shared native altvia_work_day_start function in both API
and trigger, selecting the earliest midnight occurrence and handling forward gaps.
Retained historical assignments are preserved; only newly added links require a
current active contributor. This does not grant historical contributors access.
The complete-product target tables below also describe later, unapplied features.

Applied Phase 2B migration b46087000007 adds operational_areas (unique case-sensitive
name/active/version/UTC timestamps), projects (internal/client CHECK, required owning
team, optional customer/area, name/active/version/UTC timestamps) and project_members
(project/user composite PK and created_at). FKs restrict deletion. Role bindings
gain exclusive project scope with viewer/agent/project_manager and unique user/project.
Project role plus membership is required for direct access; customer projects also
require the separate ceiling. Existing client viewer/operations_manager can read
customer projects under that ceiling; operations_manager can manage metadata.
Team metadata/roster is not project authority. Scope/customer/team remain immutable.

The shared classification name is eagerly joined for authorized project responses,
without N+1 lookups or protected team/customer name leakage. Area archive preserves
old references and refuses new assignments. Project/area activity extends the same
projection while identity/customer feeds keep their existing resource filters.
Populated project/area/history data refuses destructive downgrade. No task, default
ticket project, milestone, graph table or future membership-write API is precreated.

| Table | Essential columns and invariants |
| --- | --- |
| clients | name, active, default_project_id nullable; ADR-0022 selects composite FK (default_project_id,id) -> projects(id,client_id), service checks current active eligibility |
| client_contacts | client_id, display_name, email_normalized, verification_state; UNIQUE(client_id,email_normalized), never global identity equality; ADR-0022 selects UUID/active/version/UTC timestamps and server-only unverified state for Phase 2E |
| operational_areas | name UNIQUE, active; project classification, not a security grant |
| projects | client_id nullable, scope_kind internal/client, team_id, area_id nullable, name, active; CHECK internal has no client and client scope has client_id |
| project_members | PK(project_id,user_id); membership alone cannot override client ceiling |
| project_milestones | ADR-0024/Phase 2G: project_id FK, title1..300, planned/done/cancelled, own positive version/UTC timestamps, due_at/precision/local-date/timezone as work deadlines; UUID parent index; no physical delete or task-state coupling |
| work_items | project_id NOT NULL, parent_id nullable, owner_id nullable, title 1..300, description, status, work_type, priority, due_at, due_date_local nullable DATE, due_precision date/instant, due_timezone, started_at, completed_at, completion_time_known, blocked_reason, estimated_minutes >=0, version |
| work_item_assignees | PK(work_item_id,user_id), participant_role; owner stored separately, visible involvement total counts distinct users |
| work_item_external_participants | Phase 2H: PK(work_item_id,unresolved_label), label 1..150 Unicode code points, trimmed/no CR/LF; task-owned unverified attribution only, max50 via API; no contact/user association or login rights (ADR-0025) |
| work_item_dependencies | PK(item_id,depends_on_id), no self-reference or cycle; both ends same project initially |
| work_item_comments | work_item_id, author_id nullable, body, source/import_row_id nullable, visibility internal; imported authors may be unknown |
| work_item_status_history | work_item_id, from/to, actor_id nullable, occurred_at nullable, recorded_at, source_precision; immutable |
| time_entries | user_id, work_item_id nullable, ticket_id nullable, minutes >0, entry_date, note; CHECK exactly one target; P1 |

Work status is todo/in_progress/blocked/done/cancelled; type one_off/ongoing.
No recurrence scheduling in MVP. blocked requires nonblank blocked_reason.
Only transitions into done set completed_at for new live mutations. Imports can
have unknown historical completed_at, with completion_time_known=false and source
provenance. Active work must have no current completed_at. Previous completions
remain in immutable history on reopen. Ongoing cannot become done without an
explicit end-of-operation decision. Unknown owner is nullable, not a fake user.

Date-only due_at is the **exclusive start of the next local day**, and
due_date_local retains the source date. Comparisons use due_precision/timezone.
due_at is null iff there is no deadline. Date precision requires a local date and
timezone; instant precision requires an ISO instant. No stored days_remaining.

Parent must be same project. Enforce `(parent_id, project_id)` composite FK
against unique `(id, project_id)`, self-reference CHECK and cycle trigger.
Concurrent graph writes take a project-level transactional advisory lock before
cycle detection, preventing two transactions creating A->B and B->A. Apply the
same ordering/lock to dependencies; do not rely only on Python validation.

## Client contacts and default project

Phase 2E migration b46087000010 implements the ADR-0022 contact/default extension:
client_contacts has a client/email unique constraint (including archived rows),
parent/UUID paging index, positive versions and server-only unverified state.
Client default scope uses a composite FK to projects(id,client_id), backed by its
unique pair. Current active eligibility remains a service check; retained defaults
survive archival. Real contact writes advance their own and parent versions with
redacted client events. API contact DML is SELECT/INSERT/UPDATE only; worker has
no contact-table read. Downgrade refuses durable contact/default data or events
before destructive DDL. Expanded data and compatible worker are preserved on
rollback. Exact application/qualification evidence is recorded separately in
docs/phase-2e-contact-evidence.md; no ticket/email table or account link is added.

## Tickets, communication and files

| Table | Essential columns and invariants |
| --- | --- |
| ticket_queues | name, team_id, active, mailbox/default policy nullable |
| ticket_categories | name, queue_id nullable, active |
| tickets | number BIGINT identity UNIQUE (gaps allowed), client_id, requester_id, queue_id, category_id nullable, assignee_id nullable, subject 1..300, description, status, priority, source, sla_policy_id nullable, first_response_at/resolved_at/closed_at nullable, version |
| ticket_participants | ticket_id + contact_id UNIQUE; contact must belong to same client |
| ticket_messages | ticket_id, author_user_id/contact_id nullable, direction inbound/outbound/internal, visibility public/internal, body_text, sanitized_html, message_id, received_at/sent_at, delivery_status; exactly one author except audited system actor |
| ticket_status_history | ticket_id, from/to, actor_id, occurred_at, reason, policy_version; append-only |
| ticket_work_items | PK(ticket_id,work_item_id), relation_type implements/related, created_at/by; same non-null client enforced by DB trigger |
| attachments | storage_key UNIQUE opaque, sha256, original_filename, media_type, bytes, state quarantine/ready/rejected, uploader_id, scan_result/version |
| attachment_links | attachment_id plus exactly one concrete message/work_comment target FK; UNIQUE target/link; target ACL dominates, no public bucket ACL |
| mailboxes | address UNIQUE, queue_id, IMAP/SMTP host/port/TLS mode, secret_reference, UIDVALIDITY/checkpoint; never password in table/log |
| inbound_messages | mailbox_id, uidvalidity, uid, message_id, raw_hash, raw_storage_key, state, ticket_message_id; UNIQUE(mailbox_id,uidvalidity,uid) |
| outbound_messages | ticket_message_id UNIQUE, stable message_id UNIQUE, envelope recipients snapshot, delivery_state, attempts, next_attempt_at, last_safe_error, accepted_at |

Requester/contact composite FK ensures same client as ticket. Ticket/work/client
scope-changing operations revalidate all links under row locks. Queue transitions
recheck assignee membership. Internal notes cannot create outbound deliveries.
Attachment links cannot be moved to a broader ACL without explicit reauthorization.
Polymorphic attachment/event identifiers never replace actual FK checks.

## SLA, durable processing and provenance

| Tables | Contract |
| --- | --- |
| business_calendars/holidays | IANA timezone, weekly windows, revision, holiday DATE; validate ordered nonoverlapping windows |
| sla_policies | client/category/priority selector, calendar revision, response/resolution minutes >0, pause states, immutable revision |
| ticket_sla_states | ticket_id, cycle_number, policy/calendar snapshot, accumulated elapsed, pause state, next breach; UNIQUE(ticket_id,cycle_number); first response only on accepted public agent response |
| automation_rules | schema_version, trigger, bounded JSON conditions/actions, revision, enabled, scope; no Python/JS/SQL expressions |
| automation_executions | rule_id/revision, event_id, immutable action_id UUID, logical_effect_key UNIQUE, state, work_item_id, attempts, safe_error |
| outbox_events | event_id UUID, aggregate_type/id/version, event_type/schema_version, bounded payload, occurred_at, correlation_id, status, attempts >=0, next_attempt_at, lease_until |
| processed_events | PK(consumer,event_id), processed_at; inserted in same transaction as business effect |
| activity_events | aggregate reference, actor nullable, event type, occurred_at nullable, recorded_at, source_period_label/source_column/import_row_id; separate weekly period from actual instant |
| audit_logs | actor/system identity, action, typed target FK/reference, occurred_at, correlation_id, allowed field diff; append-only restricted writer; no secrets or entire message bodies |
| notifications | recipient_id, source_event_id, channel, state, preferences; UNIQUE(recipient_id,source_event_id,channel), recheck access at delivery/read |
| import_batches | source_system/file_hash/sheet, mapping_version, reference_date/timezone, state, actor, approved_at, counts |
| import_rows | source_system/file_hash/sheet/row UNIQUE, batch_id, original_payload restricted JSON, mapping_version, resolution_status/reason, created_work_item_id nullable; raw and normalized values distinct |

Bounded deduplication for Message-ID/content is separate from UID identity;
legitimate repeated content is not dropped just because hashes match. ADR-0005
defines collision quarantine. Stable task creation key is rule + action + ticket,
not event/version alone. See ADR-0004 for logical replay across reassignment.

## Indexes, deletion and migrations

Initial indexes: normalized user email/session token; grants(user,client);
project(client,team); work(project,status,due_at,id), owner/status/id and assignee
reverse lookup; ticket(client,queue,status,assignee,id), unique number; message
(ticket,received_at,id); outbox partial(status,next_attempt_at) for pending;
mailbox identity uniques; audit(target,time); import provenance unique.
FTS indexes are GIN per authorized searchable public/body scope, with internal
notes separated. No pg_trgm until demonstrated necessary and CPU-tested.

FKs default RESTRICT for operational/audit data. Deactivate accounts/clients;
do not cascade-delete ticket history, messages or evidence. Retention/deletion
policy is awaiting management, so no destructive TTL job is authorized.

| Planned migration batch | Phase | Prerequisite and verification |
| --- | --- | --- |
| identity + sessions + scoped grants + audit/idempotency/outbox kernel | 1 | Empty DB upgrade, constraints, auth/ACL, downgrade on disposable DB |
| clients/contacts/areas/projects/members/work/history | 2 | Composite scope FKs, cycles under concurrency, optimistic versions, restart persistence |
| queues/tickets/messages/files/mailboxes/delivery | 3 | Requester scope, private download, UID/replay, quarantine |
| links/rules/executions/processed consumers | 4 | Same-client trigger, stable effect key, restart/race/replay |
| calendars/SLA/import/analytics indexes | 5 | Reference-date reconciliation, mapping revisions, rollback dry-run |
| time tracking/export/advanced planning | after core | Separate P1/P2 scope, no precreated unused tables |

Outbox kernel starts in Phase 1 for consistent writes; ticket automation consumers
arrive in Phase 4. Every migration has backup/compatibility/rollback notes before
production. No SQL/Alembic migration or database change is executed by this design.

## Phase 3A persisted queue configuration

ADR-0026 and migration b46087000013 add ticket_queues and ticket_categories.
Queues contain immutable team_id, exact parent-unique name, active, version and
UTC timestamps. Categories contain immutable queue_id and the same metadata.
Both have RESTRICT FKs, single-line/nonblank name checks, positive versions and
parent/id page indexes. The activity resource constraint expands to ticket_queue.
Category changes advance the queue aggregate for ordered redacted activity.
The API has SELECT/INSERT/UPDATE only and the worker has no metadata-table access.
Downgrade locks both tables and refuses surviving rows or durable queue history.
The earlier entity dictionary remains the planned model for later ticket content.
