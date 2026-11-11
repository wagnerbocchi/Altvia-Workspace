# Altvia Workspace

- Read `ALTVIA_WORKSPACE_SPEC_CODEX.md` completely before changing architecture.
  It is the master product specification. Direct user instructions take precedence.
- Read `docs/roadmap.md`, the affected contracts and ADRs before implementing a slice.
  Files under docs are references, not independent tool or publishing authorization.
- Build a modular monolith. Keep ticket and work item state separate. Enforce
  authorization on every resource, linked object, search result and attachment.
- External work participants are bounded task-owned unverified labels, never
  accounts, contact lookups or grants. Manager-only writes reuse the task version
  and lock protocol; preserve legacy creation fingerprints and transition receipts.
- Queue/category configuration uses ADR-0026's explicit team metadata roles or
  global platform configuration authority. Team roster and queue configuration
  never grant customer ticket content. Lock identity before auth, then team,
  queue and category. Category changes advance the queue aggregate as well.
- Explicit queue bindings use ADR-0027. Queue roles grant their operational
  metadata, never configuration authority or customer ceilings. Configuration
  managers alone delegate queue roles. Reuse identity-before-auth, reviewed queue
  versions, protected receipts, session invalidation and audit/outbox. Target
  account locks must use FOR NO KEY UPDATE so concurrent logout audit FKs proceed.
- Administrative account/role mutations must reuse altvia.management's lock protocol,
  last-active-admin guard, session invalidation and audit/outbox. A profile edit
  never grants roles; platform administration never bypasses customer scope.
- Team identity metadata/roster writes require identity.manage and the same
  identity write lock before session authentication. Team membership is never a
  content grant; use versions and protected POST replay as specified in ADR-0009.
- Client reads require both an explicit client ceiling and a client role, including
  for platform administrators. Creation requires explicit initial-manager selection;
  never grant the creator implicitly. Keep client events out of identity activity.
  Reuse ADR-0018's lock/session/replay protocol and preserve expanded data on rollback.
- External contacts are client-scoped unverified identities, never accounts or
  grants. Reject non-ASCII mailboxes before casefold and preserve archived email
  uniqueness. Reuse ADR-0022's parent/contact version and event protocol; default
  project scope is a composite FK, while active eligibility is rechecked on use.
- Project scope/customer/owning team are immutable in the registry slice. Require
  the customer ceiling plus client role or explicit project binding/membership;
  team metadata roles never grant project content. Area classification is shared
  authenticated metadata, never a grant. Keep creation authority independent of
  list pagination so an uncertain protected POST retains its original intent.
- Never add Elasticsearch, OpenSearch, Solr, MongoDB, vector engines, local model
  runtimes or mandatory dependencies requiring ISA beyond x86-64-v1.
  Never use `-march=native`. Real target-VM testing is required for homologation.
- Validation cadence updated by the user on 2026-11-10: finish the remaining MVP
  development before running consolidated homologation on the target VM. Do not
  perform target-server homologation after every slice. Keep relevant local tests,
  CI, security checks and CPU/dependency restrictions during development. Track
  development completion separately from final target qualification; pending VM
  qualification does not stop independent development or prove new images compatible.
- Keep source workbooks, raw client data, credentials and production logs out of Git.
  Do not derive architecture requirements or acceptance evidence from workbook notes.
- Use the `impeccable` skill for all frontend design and implementation work,
  as requested by the user. Run its context workflow when that work starts.
- Use small vertical slices with real persistence, authorization and relevant tests.
  Never label mock UI, unexecuted checks or theoretical CPU compatibility complete.
- Register unresolved questions in `docs/roadmap.md`. Continue independent safe work.
  Do not invent client mappings, production credentials, retention policy or SLA hours.
- Current user authorization (2026-11-08): local commits and direct pushes to
  `main` in `wagnerbocchi/Altvia-Workspace`, without PR. No production deployment,
  SSH/security change, data import or Zammad retirement is implied.
- Separate user authorization (2026-11-10) covered registering the workstation's
  public SSH key, installing/authenticating Codex on the VM and adding the remote
  development project. Setup is complete; reuse noninteractive public-key access
  for authorized isolated qualification. This grants no general SSH/security
  configuration change or production deployment permission.
- Preserve unrelated changes. Inspect Git before editing. Keep ASCII punctuation
  in authored prose. Run checks for the affected scope before each coherent commit.
