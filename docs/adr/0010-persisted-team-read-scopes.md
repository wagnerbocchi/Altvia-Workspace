# ADR-0010: Persisted team read scopes

Date: 2026-11-09. Status: selected for Phase 1C-c; proof pending.

Context: team metadata currently requires global identity.manage, and role
bindings permit only global scope. Foundation needs persisted explicit scope
without turning organizational membership into authorization or inventing clients.

Decision: support the existing viewer and operations_manager role names at team
scope. Both can read metadata/rosters only for their bound teams through the
current team API. Team writes, global account lookup and global administration
still require identity.manage. No scoped role mutation HTTP endpoint or implicit
membership grant. Client content still requires its explicit client ceiling and
resource permissions; those resource modules/grants remain later work.

Persist each binding with its own UUID. Preserve existing global platform_admin
bindings unchanged in meaning. CHECK constraints admit only global platform_admin
with no team, or viewer/operations_manager with an existing team. Partial unique
indexes prevent duplicate global or same-team grants while permitting the same
role on multiple teams. No permissive generic scope or arbitrary role setter.

Restricted CLI grant-team-role/revoke-team-role take account email, team UUID and
one of the two fixed roles. Confirm both target email and team UUID interactively.
Use the existing identity write lock, NO KEY UPDATE user/team locks, session
invalidation/auth_version, audit and outbox in one transaction. Grant requires
an active account/team; revoke also works after deactivation/archive. Repeating
an unchanged grant has no second effect. Existing grants retain historical team
read access after archive, until explicitly revoked. A role never activates users.

Read authorization is applied in SQL before ordering/limit/cursor selection.
Global identity administrators retain all metadata access; scoped readers receive
only their bound teams. No recognized read grant returns403; an otherwise scoped
reader guessing an unbound team's ID receives404 without its metadata. Rosters
are authorized through the visible parent team before member lookup/pagination.
Global /users and every write remain403 for scoped-only readers. Authentication
rechecks revocation/account status; role changes revoke existing sessions.

Membership alone remains insufficient. Auth capabilities continue to describe
global capabilities; scoped grants are not flattened into identity.manage or a
global team-read flag. The server's filtered resource queries are authoritative.
Pagination remains live: current access is re-evaluated on every request.

Migration fails before changing an unsupported legacy global grant. Downgrade
refuses while team-scoped rows exist, rather than deleting/flattening grants.
No deployed migration is rewritten. Only the dedicated disposable test DB is
used for migration/recovery proof. No new dependency or CPU compatibility claim.
