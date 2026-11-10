# ADR-0022: Client contacts and default ticket project

Date: 2026-11-10. Status: selected before implementation; Phase 2E implementation
in progress, final review/qualification pending.
User authorized continuing development, routine decisions and direct main pushes;
questions are recorded rather than blocking independent safe work.

## Decision and alternatives

Extend the existing client registry with external email contacts and an explicit
nullable default project. Reuse PostgreSQL, existing scoped reads, the identity
write lock, protected POST replay, versioned PATCH and client audit/outbox/feed.
No new dependency, service, native artifact or ISA requirement.

A global contact directory or reuse of internal User identities would conflate
customer identities and grants. Reject both. Deferring everything to email would
leave no explicit authorized configuration for requesters and project selection.
The selected bounded registry precedes tickets; it sends no email and creates no
ticket/task/account, portal access, membership or permission.

## Data and identity

Migration b46087000010 adds client_contacts with UUID id, immutable client_id FK,
trimmed display_name 1..150, email_normalized up to 254, active, positive version,
UTC created_at/updated_at and server-owned verification_state. Unique
(client_id,email_normalized) includes archived rows. The same address may occur
in distinct clients or an internal account without establishing any identity link.
Archive/restore preserves identity; no physical-delete API.

Email uses the existing strip/casefold normalization plus a bounded ASCII mailbox
syntax (dot-atom local part, dotted DNS domain, no control characters/display
names/address lists). No network/DNS check. International mailbox/IDNA support
requires a separately scoped transport policy. Names remain Unicode plain text.
verification_state is always unverified in this slice, enforced in the database;
it is never writable. Editing email cannot assert delivery or identity proof.
Q-16 records future trusted verification/correlation policy; no matching by
address alone may authorize a message, account or client. Raw email/name stay out
of audit/outbox, logs and idempotency receipts.

clients gains default_project_id nullable. A composite FK
(default_project_id,id) -> projects(id,client_id), backed by UNIQUE(id,client_id),
enforces same-client scope even for direct SQL and concurrent writes. Null means
no default; no fake project is created. Project scope/customer are already
immutable at the API boundary. Setting a different non-null default requires an
active client/project/owning team and current authorization on that project.
Clearing is allowed for archived clients. A retained default survives project,
team or client archival; future ticket automation must revalidate eligibility
and emit triage instead of assuming this configuration guarantees usability.
No ticket resolver or automation scaffold is implemented here.

## Authorization and concurrency

Every contact route authorizes its parent through ADR-0018's separate customer
ceiling AND client role, including platform administrators. Project-only members
do not gain contact/client access. viewer reads; operations_manager writes.
Unknown/hidden parents and contacts both404; a readable parent with forbidden
write403. Nested paths additionally match contact.client_id; UUIDs are no grant.
All mutations lock identity writes before session authentication, then parent
Client and contact rows. No session or grant change is involved in contact writes.

New contact creation/real edits require an active client. A same-state PATCH with
the correct version remains a no-op, even after archival. Each real contact
change increments its own version and the parent client version, atomically
recording one client event. Contact creation starts contact version1 and advances
the parent. Client default changes use the existing Client If-Match/version,
no-op and client.updated protocol. Concurrent duplicate emails return409; no
partial event, parent increment or receipt may survive a rejected transaction.
The shared lock serializes registry writes and revocations, including project
archival; database uniqueness/FKs remain the integrity boundary.

## HTTP and event contracts

All paths use /api/v1, current no-store/session/Origin/CSRF protocols and strict
extra-forbid bodies. Anonymous401; malformed422; missing precondition428;
stale version409. UUID pages have limit1..100/default50, actor+parent-bound
cursors, no counts and no unsupported/repeated query fields.

| Route | Contract |
| --- | --- |
| GET /clients/{client_id}/contacts | Parent-scoped UUID page of ContactOutput, includes archived contacts |
| POST /clients/{client_id}/contacts | Scoped manager; Idempotency-Key; {display_name,email}; 201 minimal {client_id,contact_id}, replay200 |
| GET /clients/{client_id}/contacts/{contact_id} | Parent+child scope; ContactOutput with ETag |
| PATCH /clients/{client_id}/contacts/{contact_id} | Scoped manager; If-Match contact version; nonempty {display_name?,email?,active?}, null forbidden |
| PATCH /clients/{client_id} | Existing versioned endpoint additionally accepts default_project_id UUID or explicit null |
| GET /clients and /clients/{client_id} | Existing ClientOutput additionally returns nullable default_project_id; no extra linked name |

ContactOutput: id,client_id,display_name,email_normalized,active,
verification_state,version,created_at,updated_at. POST receipts contain no names,
emails or mutable versions. Recheck fresh parent write authority before looking
up a saved receipt; replay never recreates, restores or reveals current contact
metadata. Archived-parent replay of an already committed create is allowed after
the same fresh authorization; a new create remains blocked.

Allowlist client.contact_created and client.contact_updated with client aggregate
ID/version, actor metadata and contact_id. Updated payload adds changed_fields
from display_name,email,active; created payload has no changed_fields. Expand
client.updated's allowed fields with default_project_id, preserving strict unique
field names. No arbitrary payload or raw name/email. The existing client feed
authorizes its parent; identity and project feeds never include contact events.
Keep the existing durable consumer identifier/deduplication and worker privileges.

## Browser and acceptance

Use Impeccable's incumbent context workflow. Client detail links to a dedicated
contacts directory with paged list/create and a scoped contact detail route for
edit/archive/restore. This keeps contact creation mounted independently of client
metadata recovery and avoids growing the existing detail into a long form.
Explain external identity and unverified status in plain
language. Default-project selection lists only authorized projects of this
client, with explicit clear, pagination, reviewed version and conflict recovery.
Preserve session-owned caches and original protected POST intent through network
uncertainty. Refresh client metadata/history after contact writes; invalidate
the directory without assuming a write grants access. No arbitrary client data.

Prove real persistence, same-email cross-client independence, duplicate races,
cross-client/ceiling-only/role-only/admin denial, viewer writes, fresh revocation
before replay, strict schema/email validation, contact/client stale writes and
no-ops, event atomicity/redaction/dedup/feed isolation, same-client composite FK,
archived eligibility, migration preservation/refusal and runtime least privilege.
Real browser tests cover create/list/detail/edit/archive/restore/default paging,
uncertain create, stale conflict, failure recovery, plain-text names, keyboard,
axe, dark/light/mobile. Run all five hosted gates and actual changed-artifact
VM/native/cgroup/image qualification before calling this slice qualified.

Rollback preserves expanded data and uses compatible application/worker images.
Downgrade refuses before destructive DDL if contacts, non-null defaults or new
durable contact/default events exist. Never remove data or reset volumes to pass
downgrade. Grant API only required contact DML; worker gains no contact reads.
Production deployment/import and Service Desk remain separate authorization/gates.
