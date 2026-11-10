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
Phase 1B adds the real browser flow.
Phase 1C adds persisted team and participant administration for identity.manage
operators. Account creation, activation, password reset, platform administration
and constrained team read grants now also have protected browser administration
under ADR-0016. Restricted CLI operations remain available. Team membership never
grants client or project content access.
Foundation also includes durable worker/Redis processing and restricted identity
activity. Phase 2A adds a persisted client directory, explicit initial-manager
selection, scoped rename/archive/restore and client history. Client content always
requires a separate ceiling and role, including for platform administrators.
Further customer access changes use the restricted host CLI. Phase 2B implements
internal/customer projects, explicit initial managers, scoped metadata lifecycle,
operational classification, real members and project-only history under ADR-0019.
Creation controls follow current API creation authority independently of pagination.
Further project role/membership changes use the restricted host CLI. Phase 2C
adds persisted tasks/subtasks, explicit owners/participants, precise deadlines,
deliberate state transitions, ongoing termination, internal comments and scoped
history under ADR-0020. Assignment never grants content access. Agents edit only
owned/participating work; managers assign/reparent; viewers remain read-only.
Protected writes preserve original intents and expose deliberate recovery.
Task core is qualified in docs/phase-2c-work-evidence.md. Phase 2D implements native
PostgreSQL task search, deliberate filters, independently paged project Kanban and
task-only My Work under ADR-0021. Actual x86-64-v1 qualification passed in
docs/phase-2d-discovery-evidence.md. Contacts, default ticket projects, unified
ticket assignments and Service Desk remain subsequent deliveries.
HTTPS, secure HttpOnly cookies, Origin/CSRF checks and no browser auth-token
storage are required. Keyboard access, visible focus, responsive layout and
dark/light themes are required. All mandatory runtime dependencies must support
x86-64-v1. The current five-image Foundation stack passed on the supplied target
VM, including the Phase 2D discovery increment in docs/phase-2d-discovery-evidence.md;
changed or future mandatory native artifacts require repeated qualification.
Representative capacity and production readiness remain open. No Elasticsearch/OpenSearch.

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
