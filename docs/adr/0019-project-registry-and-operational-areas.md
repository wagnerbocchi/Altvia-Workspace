# ADR-0019: Project registry and operational areas

Date: 2026-11-09. Status: selected for Phase 2B implementation.
Scope: next FR-002 slice after the qualified client registry; no work items yet.
User authorized continued development, direct main publication and routine choices.

## Decision and alternatives

Extend the existing monolith, scoped SQL reads, protected POST, versioned PATCH
and activity projection. Areas are a shared authenticated classification catalog,
not a customer container or permission grant. Projects have immutable internal/client
scope and owning team, optional area, explicit initial manager and real membership.
No new dependency, engine, native binary, production import or deployment.

A team-role inheritance design would broaden the existing metadata-only grants;
reject it. Shipping tasks/boards with registry multiplies unrelated state and graph
rules; defer those. Extending the existing client registry patterns gives the
smallest complete persisted project/area path without speculative infrastructure.

## Schema and authorization

operational_areas: UUID, unique case-sensitive trimmed name 1..150, active,
positive version, UTC timestamps. Authenticated users read the bounded catalog;
identity.manage creates/renames/archives/restores it. Existing projects retain an
archived classification; new assignments require an active area. No physical delete.

projects: UUID/name/active/version/UTC timestamps, scope_kind internal|client,
client_id nullable FK, team_id required FK, operational_area_id nullable FK.
CHECK internal iff client_id IS NULL. All FKs restrict deletion. Scope, customer
and owning team cannot be PATCHed in this slice. Same names may occur in projects.
project_members: PK(project_id,user_id), timestamps. role_bindings adds exclusive
project_id scope with viewer|agent|project_manager and UNIQUE(user_id,project_id).
Membership alone or binding alone never grants a project read.

For a client project, every read/write first requires the separate customer ceiling.
Then either the existing client viewer/operations_manager role reads all projects
within that customer, or a project role plus membership reads that project.
Client operations_manager and explicit project_manager manage project metadata;
viewer/agent cannot. Client viewers cannot create or write projects. Internal
projects require an explicit project role plus membership. Existing team metadata
roles, team roster and global platform administration never authorize project reads.
Account deactivation and customer-ceiling revocation apply on the next request.
Archived clients/projects remain readable; archiving is not permission revocation.

Creation requires either fresh identity.manage configuration authority or, for a
client project, that client's operations_manager plus team.read for the selected
owning team. The scoped creator may select only themselves as initial manager;
global configuration may explicitly select another active account. Selected team,
customer and optional area must exist and be active. A selected manager for a
customer project must already have a customer ceiling; creation never adds one.
Creation atomically inserts project, manager membership and project_manager role,
invalidates the manager's sessions and records audit/outbox. No implicit creator
membership. A minimal {project_id,manager_user_id} receipt/replay exposes no current
project metadata and never repeats delegation. Every replay rechecks current
configuration or scoped creation authority, even for an old idempotency record.

Further project role/membership grant/update/revoke uses the restricted interactive
CLI with typed email and project UUID. It updates both records together, requires
an existing customer ceiling for new client-project access, invalidates target
sessions and advances the project version with audit/outbox. Coherent same-state
calls are no-ops even after inactivity. Actual grants/repairs require active account,
project and customer. No arbitrary role/global identity capability is granted.
No browser member writes or global account lookup for project managers yet.
Member reads return only id/display_name/active/role, never email or credentials.

All writes reuse the identity advisory lock before authentication and parent/target
row locks, serializing account/client/project grants and revocations. No automatic
ceiling, last-manager protection or implicit access from owning-team membership is
invented; trusted CLI configuration can repair a project with inactive managers.

## HTTP and event contracts

All routes use /api/v1. Collections use stable UUID cursors, limit 1..100/default50,
filter authorization in SQL before pagination and expose no global counts.

| Route | Contract |
| --- | --- |
| GET /operational-areas | Authenticated classification catalog |
| POST /operational-areas | identity.manage, Origin/CSRF/Idempotency-Key; {name}, 201/current protected replay200 |
| PATCH /operational-areas/{id} | identity.manage, Origin/CSRF/If-Match; nonempty strict {name?,active?}, stale409/duplicate-name409 |
| GET /projects | Scoped project list; optional client_id filter never grants visibility; fresh can_create independent of list/client pagination |
| POST /projects | Creation authority above; strict {name,scope_kind,client_id?,team_id,operational_area_id?,manager_user_id}; receipt201/replay200 |
| GET /projects/{id} | Scoped fields/IDs/ETag/can_manage and globally readable operational_area_name; no unauthorized linked names |
| PATCH /projects/{id} | Scoped manager, Origin/CSRF/If-Match; {name?,active?,operational_area_id?}; explicit null clears area; stale409 |
| GET /projects/{id}/members | Authorize parent, bounded current members with safe fields |
| GET /projects/{id}/activity | Authorize parent before project-bound descending activity cursor |

Hidden/absent project both404; readable forbidden write403; anonymous401; malformed
or unsupported body/query422; missing version428. Retain existing no-store transport,
plain-text names, scoped errors and session-owned browser intents. Area creation's
protected replay rechecks identity.manage; it cannot grant or expose customer data.

Allowlist operational_area.created/updated and project.created/updated/access_changed
in the existing worker. Payloads contain actor IDs, manager/member/role IDs or
changed field names, never names/emails/raw bodies. Identity history remains limited
to identity/team; customer history stays client-only. Project activity requires
project scope. Reuse existing consumer/deduplication and least-privilege roles.

## Acceptance and rollback

Migration b46087000007 is expand-only; preserve existing clients/grants/history.
Refuse downgrade when any area/project/history data exists before destructive DDL.
API receives required table DML; worker gains no operational table privileges.
Keep expanded data and a compatible worker on rollback; older workers cannot
consume new event types. Do not force downgrade/reset volumes/delete history.

Prove internal/client isolation, ceiling/binding/membership halves, no team/admin
bypass, session invalidation/no-op/replay, client filter/cursor denial, immutable
scope, archived reference assignment, version/concurrent-create races, migration
preservation, strict event projection and identity/client feed isolation. Real
browser covers area lifecycle, project creation/relogin/directory/detail/rename/
archive/restore/classification/members/history, uncertain writes, conflicts,
independent recovery, keyboard/axe/themes/mobile. Apply Impeccable to all UI.
Run the five hosted gates and changed packaged application on the actual baseline VM.

Contacts, default project for tickets, tasks/subtasks, graph rules, comments, boards,
milestones, search and My Work remain subsequent slices. FR-002/Phase 2 remain open
until their full acceptance, not merely this registry, has been delivered.
