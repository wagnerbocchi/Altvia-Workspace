# ADR-0001: Modular monolith and domain ownership

Date: 2026-11-08. Status: selected design baseline from master specification;
runtime choices remain conditional on ADR-0002. User authorized incremental work.

Context: independent internal operation needs transactions across work, support,
audit and events. There is no existing code or service topology to preserve.

Decision: Next.js UI and Python FastAPI API/worker with one PostgreSQL database,
module-owned writes and explicit policy checks. Worker reuses domain services.
Redis is transport/cache, not business truth. Postgres FTS + GIN owns search.
Compose plus HTTPS proxy, no Kubernetes/microservices. TypeScript contracts
are generated from API schema. Private storage behind an adapter, no mandatory
storage product until CPU/security validation. Create folders only when needed.

Alternatives: microservices add distributed transactions/operations with no
proven scaling need; Django would be viable greenfield but departs from the
specified FastAPI direction without a benefit established here; help-desk APIs
would violate product independence. Existing implementation reuse is unavailable.

Consequences: one deployment lifecycle and straightforward transactions, with
module-boundary discipline and shared database capacity as explicit constraints.
Read aggregates may join authorized domains; mutations go through their owners.
Split services only after measured need and a superseding ADR.

Proof required: real login/data slice, DB constraints, restart persistence,
integration tests and target runtime evidence. This ADR is not that proof.
