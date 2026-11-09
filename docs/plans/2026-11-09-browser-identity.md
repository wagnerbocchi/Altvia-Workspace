# Phase 1B: browser identity

Status: implementation and review complete; publication evidence follows in
docs/phase-1-evidence.md. Scope follows the existing Phase 0 contracts and Phase 1A
API. User authorized continued development and direct pushes to main.

## Behavior and ownership before implementation

- The browser loads GET /api/v1/auth/me with no shared or persistent identity
  cache. A 401 displays login; a network/server failure offers a real retry.
- Validated email/password go to POST /api/v1/auth/sessions over the same HTTPS
  origin. The API alone owns credentials, rate limits, cookie and authorization.
- A successful login displays the real account profile. No fake domain pages,
  counts, sample clients or implied resource access are introduced.
- Logout sends the in-memory CSRF value to DELETE /auth/sessions/current.
  Failure must not claim logout succeeded. Expired/revoked sessions return to
  login, and browser focus revalidates the current session.
- Next.js renders the shell, while TanStack Query owns transient identity data.
  No auth/CSRF token goes to localStorage, URLs, logs or generated HTML. Theme
  preference alone may be stored locally. No cross-origin API configuration.
- The edge proxy will route /api/v1 directly to FastAPI. Development uses a
  bounded local HTTPS test gateway; never weaken secure cookies for tests.
- TypeScript DTOs are generated from FastAPI OpenAPI. Form schemas validate
  browser input; backend remains authoritative. UI failures use safe local copy.

## Ordered work and proof

1. Capture product truth and provisional Operate direction with impeccable.
2. Add the smallest Next.js application, generated API types, accessible login,
   account view, real logout and dark/light preference.
3. Run lint/types/production build and browser E2E against real API/PostgreSQL:
   invalid login, valid login, reload, expiry, logout, failure/retry and security
   boundaries. Inspect desktop/mobile renders and keyboard/focus behavior.
4. Run impeccable detector, independent finish review and documentation handoff.
5. Record exact evidence/limits, commit intended files, push main and observe CI.

## Open gates

Q-01 target VM, Phase 1C ingress/Compose/processes and full security/image gates
remain open. This slice does not complete Phase 1 or authorize production deploy.
Brand decisions are provisional (Q-13); use system fonts and no external assets.
