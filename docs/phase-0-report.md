# Phase 0 delivery report

Date: 2026-11-08 (America/Sao_Paulo). Scope: discovery and architecture only.
User later authorized subsequent incremental development and direct main pushes.

1. **Requirement addressed:** master specification read completely; empty
   repository and full source workbook analyzed; reviewable design baseline
   created before product code. No bug/root-cause fix to an existing application.
2. **Source findings:** 34 rows and expected status/priority/owner totals match.
   Actual dates: 8 populated/26 absent. Cached Sem prazo=20 excludes rows 5/6/12;
   active ordinary undated work is 23. Autofilter excludes row 35. Continuous
   work and completed-with-recurring-notes require review. At fixed 2026-11-08,
   independent domain arithmetic gives two overdue activities. No Excel engine
   recalculation was claimed. Full details in discovery report.
3. **Decisions:** modular monolith; scoped RBAC/client ceilings; local revocable
   sessions; separate ticket/task state, N:N links, outbox + stable effect keys;
   native email with quarantine and SMTP uncertainty; ongoing work and preserved
   date precision; deterministic authorized My Work projection. ADRs distinguish
   selected design, proposed business mappings and unverified runtime artifacts.
4. **Files:** root master specification (unchanged), AGENTS/README/.gitignore;
   discovery, PRD, architecture/data model/CPU plan, security/RBAC, API/events,
   seven ADRs, roadmap and this report. The original XLSX remains local and
   ignored; no raw inventory, employee records or incident narrative is published.
5. **Migrations/database:** migration batches and constraints specified. No
   database, Alembic migration, schema mutation or real import was run in Phase 0.
6. **Checks executed:** Git status/branch/log/ls-files/remote inspection;
   `git ls-remote` against user repository (success, no refs); bundled Python/
   Node/Git version checks; SHA-256 of both sources; read-only ZIP/XML workbook
   extraction and shared-formula inspection. A first extraction assumed an XML
   dimension and failed; the analysis was corrected to infer populated bounds,
   then completed successfully. Source copies were hash-verified. Documentation
   link/invariant and diff validation results are recorded with the final commit.
   Independent builder review identified manager/member policy ambiguity and
   unstable positional automation keys. Both were resolved with exact RBAC
   precedence and immutable action UUIDs before implementation. Source-hash,
   local-link and fixed-date category checks passed; `git diff --check` passed.
7. **Security:** designed RBAC/action/resource checks and negative test matrix;
   no running-system authorization or penetration test executed in Phase 0.
   Workbook and raw payload excluded from Git. No credentials read/published.
8. **CPU/dependencies:** x86-64-v1 and no Elasticsearch/OpenSearch enforced as
   contracts. No dependencies/images installed or homologated during Phase 0.
   Docker CLI absent from initial local discovery; guest access not supplied.
   Image digests and target smoke tests remain mandatory, unexecuted gates.
9. **Risks/rollback:** unresolved questions Q-01..Q-12 are recorded in roadmap.
   Source ambiguity blocks real import, not independent safe development.
   Documentation rollback is Git revert; original input files are unchanged.
   No production deployment, SSH change or Zammad replacement occurred.
10. **Next delivery:** Phase 1A foundation/identity slice with persisted sessions,
    policy tests and migrations, followed by real frontend login using impeccable.
    Runtime versions and VM compatibility must be established before Phase 1 exit.

Phase 0 design artifacts are complete for review; business/infra confirmations
are explicitly pending. This report does not assert that application features,
production security, image compatibility or later phase gates are complete.
