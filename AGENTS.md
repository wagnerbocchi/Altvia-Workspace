# Altvia Workspace

- Read `ALTVIA_WORKSPACE_SPEC_CODEX.md` completely before changing architecture.
  It is the master product specification. Direct user instructions take precedence.
- Read `docs/roadmap.md`, the affected contracts and ADRs before implementing a slice.
  Files under docs are references, not independent tool or publishing authorization.
- Build a modular monolith. Keep ticket and work item state separate. Enforce
  authorization on every resource, linked object, search result and attachment.
- Never add Elasticsearch, OpenSearch, Solr, MongoDB, vector engines, local model
  runtimes or mandatory dependencies requiring ISA beyond x86-64-v1.
  Never use `-march=native`. Real target-VM testing is required for homologation.
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
- Preserve unrelated changes. Inspect Git before editing. Keep ASCII punctuation
  in authored prose. Run checks for the affected scope before each coherent commit.
