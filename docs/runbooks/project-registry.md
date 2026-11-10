# Projects and operational areas

Scope: ADR-0019 registry slice. Use synthetic data in homologation. This runbook
does not authorize production provisioning, import, migration or deployment.

## Classify and create

From Minha conta, open Projetos, then Áreas operacionais. Authenticated employees
can consult the shared catalog; identity.manage operators can create, rename,
archive and restore areas. Names are case-sensitive and unique after trimming.
Archiving preserves existing project classifications; new assignments require an
active area. An area is classification only and never grants customer access.

Project creation appears only for current configuration or scoped creation
authority. Its visibility is independent of the current client/project page.
Configuration operators may create internal or customer projects and explicitly
select an active initial manager. A scoped customer operations_manager can create
for that customer, select only themselves as manager and use a team for which they
have explicit team metadata read scope. Creation requires active references and
an existing customer ceiling for the selected manager of a customer project.

Select the owning team, optional area and initial manager explicitly. Creation
grants that manager project membership plus project_manager and ends their existing
sessions. Selecting yourself requires login again. The creator receives no implicit
membership. No customer ceiling, default project, task or board is created silently.
Customer, owning team and internal/customer scope cannot be changed in this slice.

## Read and manage a project

Customer projects first require an explicit customer ceiling. Within that ceiling,
a client viewer/operations_manager reads the customer's projects, or an explicit
project viewer/agent/project_manager plus membership reads the selected project.
Internal projects require the explicit project role and membership. Team roles,
team roster and platform administration never confer project content access.

Client operations_manager and project_manager can rename, archive, restore and
change/clear the area. Viewers/agents cannot alter project metadata. The detail
separates actual participants from scoped history. Shared area names are readable;
protected team/customer references remain identifiers rather than exposing names
through the project API. Archived resources remain readable until access is revoked.

## Change project access

ADR-0023 adds Administrar membros from a readable project's detail. Only scoped
project managers or customer operations managers can write; global administration
alone does not grant content access. Add an existing account by its known email,
select a project role, then review and confirm the exact email/role. Existing direct
roles are replaced. The screen never lists global accounts or grants a customer
ceiling. An unavailable account and an ineligible account share one safe error.

Alterar papel retains the reviewed Project version. Removing a direct access pair
preserves work assignments/history and does not revoke inherited customer access.
Access changes end affected sessions; changing your own access requires login
again and can remove your management authority. There is no last-manager guard.
Use the trusted CLI below for approved recovery if no browser manager remains.

After a lost add response, use Verificar concessao to retry only its original
email/role/version/key. A replay confirms that submission, not the current role.
Refresh current data before another edit. A version conflict requires explicit
reload and review; never resubmit against a newer version without checking it.
Failed parent/list refresh keeps an uncertain add frozen. Archived projects permit
removal, while new grants/role changes require active references.

Membership/role changes also remain available in a trusted interactive terminal with the existing
runtime configuration. Confirm the target email and project UUID. Examples use
placeholders; enter actual approved identifiers, never a password argument.

```bash
uv run python -m altvia.cli grant-project-access --email employee@example.invalid --project-id PROJECT_UUID --role viewer
uv run python -m altvia.cli grant-project-access --email employee@example.invalid --project-id PROJECT_UUID --role agent
uv run python -m altvia.cli grant-project-access --email employee@example.invalid --project-id PROJECT_UUID --role project_manager
uv run python -m altvia.cli revoke-project-access --email employee@example.invalid --project-id PROJECT_UUID
```

In an already authorized container environment:

```bash
docker compose -f infra/compose.yaml exec api python -m altvia.cli grant-project-access --email employee@example.invalid --project-id PROJECT_UUID --role agent
docker compose -f infra/compose.yaml exec api python -m altvia.cli revoke-project-access --email employee@example.invalid --project-id PROJECT_UUID
```

Grants update membership and binding atomically, revoke sessions and record
audit/outbox. A different role replaces the existing project role. Customer-project
grants require a separately approved customer ceiling; this command never supplies
one. Actual grants/repairs require active account/project/customer. Revocation is
allowed when inactive; coherent repeat calls are no-ops preserving sessions/history.
Removing a project grant does not remove independent inherited customer authority.
To remove all customer-project access, separately revoke the customer ceiling
through the existing approved client process. No last-project-manager guard is
claimed; trusted configuration CLI can repair inactive/orphaned project management.

## Recovery and rollback

Verify an uncertain creation with Verificar cadastro, which reuses the original
protected intent and key. Independent list/history recovery does not resend writes.
Changing session or leaving the page disposes private in-memory intents; authenticate
and inspect current authorized state before issuing another request. A stale or
uncertain metadata PATCH requires deliberate reload/discard, never automatic replay
against a newer version. Area names cannot contain customer-sensitive content:
the catalog is shared with authenticated employees.

Migration b46087000007 preserves existing identity/customer data and refuses a
populated destructive downgrade. Keep expanded schema, project/member/grant,
audit/outbox/activity data and volumes. Keep a worker compatible with project/area
events, or stop the worker until that version resumes. An older worker would
dead-letter unknown event types. Never delete history/reset volumes/force downgrade
to make rollback pass. Existing production backup/image/approval gates still apply.
