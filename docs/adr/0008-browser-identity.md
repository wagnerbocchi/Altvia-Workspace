# ADR-0008: Same-origin browser identity and bounded frontend

Date: 2026-11-09. Status: implemented for Phase 1B; deployment/CPU gates open.

Context: Phase 1A already owns credential validation, secure cookie creation,
expiry/revocation, Origin verification and CSRF. The first browser slice must
exercise those real behaviors without inventing unfinished business modules.

Decision: Next.js/strict TypeScript with Tailwind and shadcn-style primitives,
React Hook Form/Zod and TanStack Query. OpenAPI is exported from FastAPI and
generates TypeScript DTOs; CI rejects contract drift. Browser requests use the
same origin; the production edge routes /api/v1 to FastAPI. No BFF or duplicate
authorization service is added. Identity and CSRF stay in transient query memory;
the opaque session cookie is HttpOnly and no auth state goes to browser storage.
Only theme preference is persisted locally. No identity is serialized in SSR.

The browser verifies identity on load and visibility/focus revalidation. It does
not poll /me and keep an idle session alive. A server-confirmed 401 returns to
login; a transport failure presents retry, without claiming logout succeeded.
Screen transitions establish keyboard focus. Public account creation/password
reset UI is absent because only restricted management commands exist.

Nonce-based document CSP requires dynamic SSR. Scripts use nonces and
strict-dynamic, with unsafe-eval only in development. Inline styles remain
allowed for framework/theme operation. Frame embedding, plugins and cross-origin
connections are denied; private API responses remain no-store.

Native compatibility: exclude Next's optional Sharp package. Linux x64 prebuilt
Sharp requires SSE4.2. Image optimization is disabled and its route tested 404.
Node/SWC/Tailwind native artifacts still require the real baseline VM gate.

Tooling tradeoffs: TypeScript 5.9.3 retains the compiler factory API used by
openapi-typescript; TypeScript 7 failed that generator. ESLint 9.39.4 stays within
all Next plugin peer ranges; ESLint 10 produced unsupported peer ranges. The
deprecated tooling major needs a future coordinated plugin upgrade. A narrowly
scoped minimatch override to 11.0.1 resolves GHSA-g3hv-75wg-m249; lint/generation
and the complete frontend build verify that tool chain after the override.
All versions are exact and pnpm lockfile is committed.

Proof: production build and strict lint/types; real HTTPS browser/FastAPI/Postgres
tests of invalid/valid login, reload, server expiry, failure/retry, pending/rate
state, logout, CSRF/Origin and document headers; axe and screenshot review for
light/dark desktop/mobile. This is not SSO, identity administration, production
ingress, complete security certification or target-VM homologation.
