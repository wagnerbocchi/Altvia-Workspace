# ADR-0016: Account and permission administration

Date: 2026-11-09. Status: implemented in 207c203/30c577d, reviewed fix 7e0e66b.
Evidence: docs/account-administration-evidence.md. Foundation increment.
Extends ADR-0003/0009/0010/0015; no new database schema or dependency.

## Behavior and ownership

Expose existing altvia.management operations to identity.manage operators through
linked /admin/users and /admin/users/{UUID} browser pages. Create ordinary active
accounts, activate/deactivate, reset passwords, grant/revoke global platform_admin,
and grant/revoke only viewer or operations_manager on an existing team. No profile
editor, arbitrary role, customer grant, self-service reset or corporate SSO.
Membership remains organizational metadata, never an access grant. Platform admin
never bypasses customer content authorization. Existing CLI behavior is preserved.

The service owns the identity transaction lock, last-active-admin guard, session
invalidation, audit/outbox and grant constraints. HTTP acquires the same lock before
authentication and adds exact Origin, CSRF, fresh identity.manage authorization,
strict bounded JSON, optimistic concurrency and protected POST replay. All effects,
audit/outbox and receipt commit together. HTTP supplies the authenticated actor and
correlation ID; CLI retains its management-command attribution.

## HTTP contract

All paths below have prefix /api/v1. Existing GET /users summary stays unchanged.

| Method/path | Body/result |
| --- | --- |
| POST /users | email, display_name, password; 201 UserAdminOutput |
| GET /users/{id} | 200 UserAdminOutput and ETag |
| POST /users/{id}/activation | active boolean; 200 UserAdminOutput |
| POST /users/{id}/password | password; 200 UserAdminOutput |
| POST /users/{id}/platform-admin | enabled boolean; 200 UserAdminOutput |
| GET /users/{id}/team-roles | UUID-ordered bounded binding page and user ETag |
| POST /users/{id}/team-roles | team_id, role_name, enabled; 200 UserAdminOutput |

UserAdminOutput contains id, display_name, email, active, platform_admin,
version and created_at. Version is the existing User.auth_version. Security
changes advance it and revoke all sessions; no-op grants/status changes do neither.
Overflow is rejected with 409 version_exhausted. Existing-user POST requires the
reviewed If-Match. Every POST requires Idempotency-Key. Missing precondition 428,
invalid syntax 422, stale version 409, changed-payload replay 409. All models forbid
extra fields. Names trim to 1..150 characters, normalized email follows the existing
identity policy, password requires 14 characters and at most 1024 UTF-8 bytes.

Role-page rows contain binding id, team_id, team_name, team_active and role_name.
Limit 1..100, default 50; opaque cursor bound to the account, no invented totals or
search. Grants require active account and team; revocation remains possible when
either is inactive. User ETag binds role review to account security state. A team
may change independently; the service checks its current state under the lock.

## Secret-safe replay and session boundary

Receipt scope is actor + route + key, retained at least 7 days. Ordinary payloads
use the existing SHA256 fingerprint. Credential-bearing payloads instead use
Argon2id (memory 65536 KiB, time 3, parallelism 1,32-byte output) over canonical JSON,
with a deterministic 16-byte salt from SHA256(actor, route, key). This fits the
existing 64-character request_hash and avoids storing a fast password verifier.
Comparison is constant-time. Receipt results contain public DTOs only. No plaintext
password or password hash enters audit/outbox, response, receipt, URL or log.
Fresh authorization precedes replay. Replay returns the historical public receipt;
the browser must refetch current account and roles before another write.

A fresh successful mutation of the current account that revoked its session clears
the session cookie and returns X-Session-Revoked: true. That header is never stored
in a receipt or returned for replay under a subsequent valid session. Last-active-
admin protection remains authoritative, including concurrent attempts.

Browser credentials live only in an uncontrolled password input and a private
intent ref until a definitive result or session-subtree disposal. Clear the input
on dispatch. Never put passwords in React snapshots, TanStack variables/query keys,
storage, SSR or console. Uncertain transport/5xx freezes the original key, payload
and reviewed version; explicit verification replays exactly that request. No
automatic retries. Independent read recovery must preserve uncertain intent.
Dispose secret refs on definitive result, unmount or session change. Fence all
callbacks with session.isCurrent(); one outstanding account write at a time.

Use incumbent native forms, bounded paging, inline named confirmations for security
changes and clear warnings for self-session revocation. Refresh/read conflicts
block writes until explicit recovery; never silently substitute a new version.

## Acceptance and limits

Real PostgreSQL and browser proofs cover lifecycle, duplicate/stale/replayed writes,
secret exclusion, attribution, permission revocation, self-session behavior, last
admin, inactive grants, bounded role pages and unchanged team/identity behavior.
Review rendered desktop/mobile light/dark UI, keyboard/focus and axe. Build/scan
actual changed images and repeat isolated target-VM qualification before claiming
the updated runtime homologated. No production deployment, real accounts/import,
new mandatory native artifacts, search engines or higher CPU ISA.
