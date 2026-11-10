# Client registry operations

Scope: ADR-0018 registry and ADR-0022 contact/default configuration. Use synthetic data in homologation.
Real customer mappings and membership approval remain Q-04/Q-05; this runbook
does not authorize production provisioning or deployment.

## Create and operate

From Minha conta, open Clientes. An identity.manage operator supplies a client
name and explicitly selects an existing active initial manager. Creation grants
that manager a customer ceiling and operations_manager role atomically. It ends
all sessions of that manager, including the current session if selecting yourself.
Authenticate again after self-delegation. The creator receives no implicit grant.

The directory lists only clients for which the current account has both records.
Platform administration, team membership and team roles never bypass this scope.
An empty directory can be correct for a platform administrator. Names need not be
unique; confirm the UUID before access changes. Names are plain text, 1..150 code
points after trimming. Do not merge records based on workbook labels.

Open a client to read its state and scoped activity. A client operations_manager
can rename, archive or restore it. A viewer can read it. Archive preserves data
and existing read scope. No contact, project, task or default project is created.

## Change customer access

### External contacts and default project

ADR-0022 adds nested contact GET/POST and GET/PATCH routes under
/api/v1/clients/CLIENT_UUID/contacts. A contact is an external email identity,
never an internal account or a permission. The same normalized address may exist
in different clients; archived contacts retain their unique address within the
client. Only client operations_manager writes; viewer reads. Both still require
the separate client ceiling. Verification is server-owned unverified; this slice
sends no email and establishes no requester identity proof.

Create with {display_name,email} and Idempotency-Key. Retain the original body/key
after uncertain delivery and verify the original request; the minimal receipt
contains client_id/contact_id. Fresh scope is required for replay. GET the scoped
contact to obtain its ETag; PATCH name/email/active with that If-Match. A real
contact change also advances the client's version and records one redacted client
event. Re-read client metadata before a later default/name/state PATCH. Archived
clients block new contacts and real contact edits; reads/no-op/committed-create
replay retain their original authorization rules.

Client PATCH additionally accepts default_project_id or explicit null. Setting
a new non-null value requires an active authorized same-client project and owning
team, plus active client. A composite FK enforces customer consistency. Clearing
is allowed after archival. Existing defaults survive archival; future ticket
automation must recheck eligibility and triage instead of inventing a project.
No ticket/task is created by this setting.

Migration b46087000010 preserves existing data and refuses downgrade with durable
contact/default configuration or events. Keep a compatible expanded application
and worker; earlier workers reject the new contact/default event payloads. Never
delete history/contacts/defaults or reset volumes to force rollback.

Use a trusted interactive host terminal with the existing runtime configuration.
The CLI confirms the target email and client UUID before writing. Replace the
example identifiers; never pass a password as a command argument.

```bash
uv run python -m altvia.cli grant-client-access --email employee@example.invalid --client-id CLIENT_UUID --role viewer
uv run python -m altvia.cli grant-client-access --email employee@example.invalid --client-id CLIENT_UUID --role operations_manager
uv run python -m altvia.cli revoke-client-access --email employee@example.invalid --client-id CLIENT_UUID
```

In an already authorized container environment, the equivalent interactive entry
point is:

```bash
docker compose -f infra/compose.yaml exec api python -m altvia.cli grant-client-access --email employee@example.invalid --client-id CLIENT_UUID --role viewer
docker compose -f infra/compose.yaml exec api python -m altvia.cli revoke-client-access --email employee@example.invalid --client-id CLIENT_UUID
```

A real change updates both records in one transaction, advances account/client
versions, ends target sessions and records audit/outbox. Selecting another client
role replaces the existing one. A coherent same-state call is a no-op, preserving
sessions and history even if the client/account is inactive. New grants or repairs
require an active account and client; revocation remains possible when inactive.
There is no bulk grant, implicit emergency bypass or browser grant screen.

## Recover and roll back

If a creation reply is lost, Verificar resultado verifies the original protected
intent; it does not create a fresh client. Session changes dispose local intent.
After authenticating again, inspect authorized state before submitting another
creation. A stale metadata edit requires deliberate reload/discard, never an
automatic write against a newer version. History can recover independently.

Migration b46087000006 is expand-only and refuses a populated destructive
downgrade. Preserve customer, grant, audit, outbox and activity data. Do not reset
volumes or delete records to force rollback. Keep an application/worker version
that understands client events. An older identity-only worker would dead-letter
them; stop the worker rather than deploying that incompatible consumer, then
resume a compatible worker to recover durable events. Production rollback also
requires the existing backup, immutable-image and post-change verification gates.
