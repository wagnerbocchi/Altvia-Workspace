# ADR-0018: Client registry and explicit customer access

Date: 2026-11-09. Status: implemented and qualified for Phase 2A.
Scope: the first FR-002 vertical slice, before projects and operational areas.
User authorized continued incremental development after Foundation closure.

## Choice and limits

Extend the modular monolith and current PostgreSQL/session/HTTP protocols. Build
a real client directory, detail, create, rename, archive/restore and scoped history.
No new dependency, native binary, external service, default project, contacts,
data import, operational-area placeholder or ticket/work implementation.

Alternatives considered: adding projects and tasks together creates a much larger
authorization/schema change; a global admin client list violates the existing
customer ceiling; a host-only registry leaves the requested user-facing workflow
incomplete. A bounded registry with explicit initial delegation is the first
complete dependency of client projects. The selection is an engineering decision
under the user's instruction to continue and record questions without pausing.

Names are trimmed, 1..150 characters and need not be unique. Never merge names or
infer an operational client's identity from workbook labels. Deletion is archive,
not physical removal. Actual production mappings and grants remain Q-04/Q-05.

## Schema and authorization

clients: UUID id, name, active, positive version, created_at/updated_at UTC.
client_access_grants: composite PK(user_id,client_id), FKs to users/clients,
granted_by nullable FK for trusted management commands and created_at UTC.
Extend role_bindings with nullable client_id and an exclusive client scope for
viewer/operations_manager. Existing global/team constraints remain intact. Client
bindings have UNIQUE(user_id,client_id); a person has one current client role.
The ceiling and binding are separate records as required by the security model.

Both are required for every client read. viewer reads; operations_manager reads
and manages that client's metadata. A team binding, team membership, global
platform_admin or orphaned client binding never supplies a ceiling. SQL filters
before pagination. Hidden and unknown UUIDs both return 404; a readable client
with a forbidden write returns 403. Archived clients remain readable until revoked.

Creation is a configuration action requiring fresh identity.manage. The caller
must explicitly select an active initial manager, creating that person's ceiling
and operations_manager binding in the same transaction. There is no implicit
creator grant. Creation returns only client_id and manager_user_id as its receipt;
it is not a backdoor for reading customer metadata. Its protected replay returns
the same minimal receipt after fresh configuration authorization, never repeats
delegation and never exposes current client state. Self-delegation is permitted
only through that explicit selection and revokes the current session as usual.

Further role/ceiling changes initially use restricted interactive host CLI,
requiring target email and client UUID confirmations. Grant/update/revoke operate
on both records atomically, revoke target sessions, advance auth_version and the
client version and append audit/outbox. A same-state call is a no-op. New grants
require an active account/client. No browser grant administration or all-account
lookup for ordinary client managers is introduced in this slice.

All mutations acquire the existing identity write advisory lock before session
authentication, then client/user row locks. This reuses the current serialized
grant/revocation and protected-POST protocol; future project write concurrency
will be contracted separately. Metadata PATCH uses If-Match and increments only
on a real change. Audits and events commit with state. No runtime DDL privilege.

## HTTP contracts

| Route | Contract |
| --- | --- |
| GET /clients | Authenticated, SQL ceiling + client role filter, UUID ascending cursor, limit 1..100/default50, no total/global count |
| POST /clients | identity.manage, Origin/CSRF and Idempotency-Key; {name,manager_user_id}; 201 {client_id,manager_user_id}, protected replay200 |
| GET /clients/{id} | Scoped read; id/name/active/version/timestamps/can_manage; ETag |
| PATCH /clients/{id} | Scoped operations_manager, Origin/CSRF and If-Match; strict nonempty {name?,active?}; safe409 on stale version |
| GET /clients/{id}/activity | Parent scoped read first; bounded occurred_at/event_id descending feed with client-bound cursor |

Anonymous401, invalid input422, missing precondition428. Deny unsupported query
fields. Pagination never relies on an opaque cursor as authority. Every request
rechecks current grants. Names are plain text; no HTML or raw payload rendering.

## Worker and history isolation

Extend the existing durable activity projection for allowlisted client.created,
client.updated and client.access_changed events. A strict client payload includes
only actor metadata, initial manager or affected user UUID, selected role/null
and changed field names. No names, email, credentials or arbitrary JSON in history.
Schema permits resource_type client; identity history explicitly filters to its
existing identity/team resources. Client events never appear in that global
administration feed. The client feed always applies parent authorization first.

Reuse the registered JSON actor and stable existing consumer deduplication key;
its legacy identity_activity_v1 name remains a durable protocol identifier.
No event is sent to an unsupported consumer or silently discarded. Existing
unknown/malformed event DLQ behavior and lease/retry semantics remain unchanged.

## Persistence, safety and verification

Expand-only migration b46087000006 adds registry/ceilings/client role scope and
activity constraint. Preserve every existing identity/team/history row. Downgrade
refuses populated clients or client history before any destructive DDL. API gets
only required registry/grant DML; worker privileges remain unchanged. No extension,
wheel or ISA change. Reuse unchanged native qualification; changed packaged
application still needs container/CI proof and target execution when access exists.

Prove two-client isolation, admin-without-ceiling denial, ceiling-only/binding-only
denial, fresh revoke/demotion, session invalidation, cross-client cursor rejection,
creation replay after revoke, concurrent duplicate creation and stale PATCH,
transactional audit/outbox and idempotent scoped projection. Real browser proof
covers provisioning to another manager, relogin after self-delegation, empty/error
recovery, plain-text names, archive/restore, version conflicts, scoped history,
keyboard focus, themes/mobile and no overflow. Use Impeccable for all interface work.

Rollback chooses compatible application images with expanded data intact. Do not
delete customer history, reset volumes or run downgrade to make rollback succeed.
FR-002 and Phase 2 remain incomplete until subsequent project/area/work slices.
