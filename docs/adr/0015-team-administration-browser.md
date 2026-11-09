# ADR-0015: Team administration in the browser

Date: 2026-11-09. Status: contracted before implementation; Foundation slice.
Builds on ADR-0008/0009/0010. No backend or schema change.

## Scope and approach

Expose the existing persisted identity-team APIs to identity.manage operators:
team list/create, detail/rename/archive/restore, paginated roster, paginated
existing-account selection and add/remove membership. Account creation/status,
passwords, role grants and scoped delegation remain existing CLI operations.
Organizational membership never grants client/project/content permissions.
The administrative browser route is not the scoped-reader interface.

Use separate /admin/teams and /admin/teams/{UUID} pages in the incumbent visual
world. Standard linked pages preserve URLs, back navigation and mobile flow with
less state than a drawer or multi-pane selection system. An inline-only list
would mix unrelated team forms and complicate pagination; a wizard adds steps
to routine edits. The user delegated routine decisions and asked not to pause.

Lists remain bounded, UUID-ordered and cursor-driven, using the existing typed
OpenAPI DTOs. Do not invent totals, alphabetic sorting or server search. Names
need not be unique; expose the record identifier where it disambiguates teams
or roster entries. Existing-account labels include real name/email/state.
Inactive accounts cannot be selected for new membership. Archived teams retain
their rosters and cannot receive members; restore is explicit.

## Session and data boundary

Reuse the existing identity query, login/logout, exact Origin/CSRF and no-store
transport. Extract shared identity framing rather than implementing another
authentication flow. Private team queries/mutations live in a transient query
client owned by the authenticated user/session subtree. Replace that subtree on
subject/CSRF-session change; cancel and clear its private client on unmount.
Do not place CSRF tokens in query keys, storage, URLs, logs or SSR output.

Private callbacks from a closed subtree cannot invalidate a later session.
Confirmed resource401/403 gates private content and rechecks /auth/me; automatic
rechecks do not remount a repeatedly rejected resource in a loop. A user may
explicitly verify access again. An ordinary successful focus refresh with the
same session preserves forms and keyboard focus. Only theme persists locally.
An ordinary user sees no administrative link, data query or mutation control;
the API remains authoritative for every request even if browser state is altered.

## Writes, concurrency and uncertainty

Generate one idempotency key per create/add intent, freeze its normalized payload
and original If-Match, and keep them in memory until a definitive reply. Disable
duplicate submission. After a transport/5xx failure, do not claim failure or
success: offer an explicit verification using exactly the same POST intent.
Never substitute a new key or version for that verification. A replay is an
historical acknowledgement; refetch current state before further editing.
Full page abandonment loses an unconfirmed in-memory intent; no automatic
resubmission occurs on reload. The operator must inspect current records first.

PATCH/DELETE use the version of the reviewed snapshot. They are not protected
POST replays: transport uncertainty or409 blocks further editing until an explicit
reload/review. Preserve unsaved name input through ordinary background refresh;
discard it only by the operator's explicit reload/cancel. Archive/remove have
inline named confirmation, with predictable focus recovery. Do not overwrite a
newer version automatically or infer success from a later matching name.

Check detail ETag against its typed body version and roster ETag against the
detail snapshot. A mismatch blocks normal writes pending reload. User-facing
messages describe changed data and recovery, never raw headers/keys/versions.
Mutation receipts do not optimistically replace lists or cached versions.

## Acceptance and limits

Real PostgreSQL/browser tests: empty/create/rename/archive/restore, add/remove,
inactive account/team, pagination, reload persistence, lost POST acknowledgement
with one logical effect, version conflicts, safe transport recovery, HTML-like
names, long Unicode names, access denial, session/subject changes, late responses,
keyboard/focus, responsive light/dark, axe and rendered screenshot review.
Preserve all existing identity E2E and backend contracts/tests. Package and scan
the actual updated web image; existing Compose identity/recovery gates remain.

No new native dependency, higher ISA, search engine, production data or deployment.
Actual x86-64-v1 VM homologation and the rest of Foundation remain open.
