# ADR-0003: Local identity with revocable server sessions

Date: 2026-11-08. Status: selected design; timeout/hash cost defaults proposed
until measured. Corporate IdP information is pending, not a development blocker.

Context: internal employees need enforceable revocation and resource-level
permissions. MVP has no external portal or known OIDC provider.

Decision: Argon2id local password hashing, opaque cryptographically random
256-bit session tokens, only token hashes persisted. Same-origin secure cookie,
CSRF token plus Origin verification, server expiry/revocation. No localStorage
auth token. Separate scoped grants from profile/account fields. No public signup
or production default credential. Restricted one-time bootstrap/reset management
commands, bounded rate control and audited identity changes.

Initial proposal: idle 30 min, absolute 12 h; Argon2id 64 MiB/3 iterations/1 lane.
Benchmark target latency/memory and cap concurrent hashing. Password/role changes
rotate or revoke sessions. Every request checks active account/session and
current scope, so revocation does not wait for JWT expiry.

OIDC identity adapter may be added when issuer/client/claims and MFA requirements
are supplied. Link by verified issuer+subject with explicit account mapping.
Do not create a speculative abstraction or implement fake MFA now.

Alternatives: browser JWTs complicate revocation; unconfirmed SSO blocks the
first useful slice; basic auth lacks required session ergonomics and controls.
Proof: expiry, replay/revocation, CSRF, enumeration/rate control, scoped RBAC,
password reset and concurrent login tests; Argon2 binary on actual guest.

Phase 1C-a extends the restricted CLI for ordinary account provisioning and
account/admin state changes. Typed email confirmation protects state/role
operations; no password argument or insecure terminal fallback is accepted.
The existing advisory lock serializes management writes and protects the last
active platform admin. User mutations use NO KEY UPDATE so audit FK key-share
locks remain compatible with session revocation. Changes invalidate sessions,
advance auth_version and append audit/outbox in one caller-owned transaction.
The operator is trusted at the host/DB boundary; this is not employee-facing
HTTP administration or a claim of per-employee operator attribution.
