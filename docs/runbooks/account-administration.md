# Account administration

Requires an authenticated identity.manage account. From Minha conta, select
Administrar contas. An ordinary account has no administration links; entering
/admin/users directly still checks server authorization.

## Create and review

Use Nova conta with name, email and an initial password of at least 14 characters,
at most 1024 UTF-8 bytes. New accounts are active and receive no administrative
permission or team access. Communicate credentials through an approved private
channel. There is no password email, self-service reset or invented invitation.

Open a named account from the bounded list. Review its email, identifier, active
state and platform-admin status before changing access. Pagination follows stable
UUID order, not alphabetical order; there is no search or total-count estimate.

## Security changes

Each status/password/role action shows a named inline confirmation. A change ends
all existing sessions of that account. Changing your own account returns you to
login. Keep another active platform administrator before disabling yourself or
revoking your own administration; the server refuses removal of the last one.
No-op status/role requests preserve sessions and create no repeated audit event.

The account detail separates platform administration from team read grants.
Choose an existing active team and either Leitura (viewer) or Gestor operacional
(leitura) (operations_manager). These are the constrained read roles implemented
in Foundation. Team participation alone never grants this access, and platform
administration never bypasses client/project authorization. Archived teams and
inactive accounts cannot receive grants; existing grants can still be revoked.

## Recover without duplicate effects

If the reply is lost, Verificar resultado resends the original protected request.
Do not create another request to guess whether the first one succeeded. Password
inputs are cleared after dispatch; only the private in-memory intent is retained
for explicit verification. Nothing is stored in browser storage, URLs or SSR.

Recarregar dados resolves a stale reviewed snapshot. It never repeats the write
with a newer version automatically. Independent read recovery preserves an
uncertain request. Session replacement or leaving the page disposes local intents;
after returning, inspect current account state before submitting another change.
A lost reply to your own security change can also end the session: authenticate
with the resulting credentials and inspect state before another operation.

Audit/outbox, session revocation and public idempotency receipt share one database
transaction. Credentials/password hashes never appear in their payloads. HTTP
attribution uses the authenticated actor and correlation ID; restricted CLI
management commands remain available with their existing confirmation workflow.
