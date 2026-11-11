# Explicit queue access administration

ADR-0027 defines this increment. Use /service-desk/queues, open a permitted queue
and select Administrar membros. An explicit owning-team operations_manager or
platform configuration administrator can add an existing account by known email,
review the submitted identity and queue role, then confirm. Queue readers inspect
the bounded roster. Account discovery and customer delegation remain separate.

## Roles and recovery

Consulta maps to viewer, Agente to agent and Gestor de atendimento to
operations_manager within that queue. Queue roles allow operational metadata
reads. Future ticket content additionally requires its explicit customer ceiling.
The queue manager role supplies no configuration or delegation authority.
Team membership and client/project roles alone supply no queue grant.

Actual access changes end the target account's sessions. A self-target change
requires login again. History is retained on removal. Existing independent team,
platform and customer permissions survive removal of a queue binding.

Writes capture the reviewed queue version. A stale edit requires Recarregar para
revisar and a new deliberate review. A lost POST response requires Verificar
concessao, preserving the original email, role, version and key. A saved ID receipt
confirms the submitted operation. Refresh queue/roster to inspect current access.
Failed refresh keeps further edits blocked until authoritative reads succeed.
An archived queue or team permits reading and removal. Restore both before new
grants or real role changes. No-op writes preserve versions, events and sessions.

## Persistence and rollback

Migration b46087000014 adds nullable role_bindings.queue_id with a RESTRICT FK,
scope CHECK and unique partial account/queue index. Existing binding shapes remain
valid. The API uses existing role_bindings privileges. Worker receives no table
access and validates only the exact redacted access event through the outbox.

Apply migrations with the established migration owner before starting the new
API/worker. Preserve the expanded schema and new-event consumer on application
rollback. Downgrade refuses any queue binding or durable access audit/outbox/
activity event. Removing grants does not make audit history disposable. Never
delete data to force downgrade. Use a reviewed backup/restore procedure for a
separately authorized rollback requiring older schema.

## Validation

Run the focused backend with
`python .superpowers/phase1-tests/run.py --api apps/api/tests/test_queue_access.py apps/api/tests/test_ticket_queues.py -q`.
Build the web application before using the existing-output browser runner with
`pnpm web:build`, then run
`python .superpowers/phase1-tests/run.py queue-access.spec.ts`.
The guarded local runner uses isolated test PostgreSQL/Redis, synthetic accounts
and localhost-only transport. Keep its unique API/browser logs for failures.
Hosted container checks prove persisted grants/replay after API/database
recreation and reject queue-only escalation or customer discovery.

Local/hosted proof establishes development behavior. Final consolidated target
qualification after remaining MVP development must exercise the integrated
images on the actual x86-64-v1 VM. No new native dependency or ISA requirement
is introduced by this schema/API/UI increment.
