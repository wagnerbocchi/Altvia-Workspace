# Altvia Workspace

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

The mandatory master specification selects Next.js, strict TypeScript,
Tailwind/shadcn, React Hook Form/Zod and TanStack Query. The existing backend
uses FastAPI, PostgreSQL, SQLAlchemy and revocable server sessions.

## Users

Internal support agents, operational staff, managers and administrators.
They coordinate client work and service requests with explicit resource scope.

## Product Purpose

Bring project work and native service desk operations together while preserving
their independent lifecycles. Authorized links connect tickets and work items;
My Work eventually consolidates authorized assignments without double counting.

## Operating Context

Desktop operational use, with responsive browser access. Portuguese is the
initial interface language. The supplied workbook is discovery evidence, not
production seed data. Login uses an administrator-provisioned account; there is
no public registration or self-service password reset yet.

## Capabilities and Constraints

Phase 1A implements login, current identity and logout with persistent sessions.
Phase 1B adds the real browser flow. Domain modules remain future deliveries.
HTTPS, secure HttpOnly cookies, Origin/CSRF checks and no browser auth-token
storage are required. Keyboard access, visible focus, responsive layout and
dark/light themes are required. All mandatory runtime dependencies must support
x86-64-v1; actual target-VM validation is pending. No Elasticsearch/OpenSearch.

## Brand Commitments

The confirmed product name is Altvia Workspace. No approved logo, palette,
typeface or visual reference was supplied. Visual choices are provisional
implementation decisions, recorded for later review per the user's instruction
to continue and register questions instead of pausing development.

## Evidence on Hand

ALTVIA_WORKSPACE_SPEC_CODEX.md is the product authority. docs/prd/PRD.md and
docs/contracts/api.md establish behavior. The identity API has real PostgreSQL
tests; docs/phase-1-evidence.md records their limits. There are no approved
brand assets, customer testimonials or operational dashboard metrics to publish.

## Product Principles

- Persist real behavior before presenting it as available.
- Keep client and resource permissions explicit and enforced by the API.
- Make the next action clear without exposing implementation details.
- Preserve source uncertainty and record unresolved decisions.
