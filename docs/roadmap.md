# Development roadmap and decision register

Updated 2026-11-09. User authorized incremental development after contracts,
direct pushes to main and no PR. Continue safe independent work while questions
await answers. This does not authorize production deployment or real data import.

## Milestones and gates

| Phase | Ordered vertical deliveries | Dependencies | Exit evidence |
| --- | --- | --- | --- |
| 0 Discovery/design | Source inspection, PRD, ERD/dictionary, RBAC, ADRs, API/events, CPU plan and roadmap | Master spec + XLSX | Reviewable contracts, divergences and unknowns recorded; no product implementation in Phase 0 commit |
| 1 Foundation/identity | 1A backend auth/session/policy kernel and migrations; 1B real login UI with impeccable; 1C account administration, worker/outbox/Compose/CI/runtime validation | Phase 0 contracts; selected supported artifacts | Real login/logout/expiry/revocation; resource ACL negative tests; DB persistence/migrations; build/lint/typecheck/tests; actual VM CPU gate |
| 2 Clients/projects/work | Client/area + project/member slice; task/subtask/owner/participants/history; Kanban/list/search/My Work tasks | Phase 1 gate | Operate one real project end to end, graph/version race tests, no mock counts |
| 3 Native Service Desk | Queue/ticket/history; public/internal conversation + quarantine/private attachments; native IMAP/SMTP/reopen | Phase 2 + mailbox/provider data | Real request received/responded/reopened/closed; spoof/ACL/MIME/delivery tests and restart persistence |
| 4 Unified work/automation | N:N authorization; structured rules and durable consumer/DLQ; unified projection | Phase 3 | Assignment/retry/race/reassign/reopen singular logical effect; pagination and partial-ACL consolidation |
| 5 SLA/analytics/import | Versioned calendar/SLA; real dashboards; import staging/dry-run/reconciliation; P1 notifications after core | Phase 4 + approved calendars/mappings | Source metrics reproduced with explicit reference date; 34/19/8 dispositions; negative permissions; calendar/retry tests |
| 6 Hardening/readiness | Full E2E, targeted security tests, profiling, image/native audit, recovery/runbooks, pilot | Prior gates + production authorization | Guest runtime/load evidence, backup/restore/rollback, retention approval and pilot checklist |

Deliver one useful persisted vertical slice per coherent commit. No phase
advancement from UI appearance alone. Reuse unchanged passing evidence; test
affected behavior after each change. No release date/velocity estimate without
environment/volume data. Do not replace Zammad until formal operational acceptance.

Phase 1 can progress locally while VM access is absent, but cannot claim its
exit gate or proceed to production. If all independent work is exhausted, report
the exact blocker rather than silently weakening acceptance.

## Definition of ready and done per slice

Before implementation: ownership, typed request/response, permission predicates,
schema/constraint delta, failure/race behavior and meaningful tests are defined.
Before commit/push: relevant build/lint/typecheck/tests pass or the bounded
incomplete status is explicit; no secrets/raw client data; intended diff only.
Before phase completion: UI uses real API/persistence, negative ACL and recovery
paths pass; commands and results recorded; required VM gates are satisfied.

Production migrations/deploy: immutable images, backup, compatible schema plan,
documented rollback and post-change verification. External publication permission
currently covers this GitHub repository's main only, not production services.

## Open questions and safe defaults

| ID | Needed answer / owner | Safe action while pending | Gate blocked |
| --- | --- | --- | --- |
| Q-01 | Infrastructure admin: target hostname/SSH user and approved access path; raw guest flags/OS | Local development; no fabricated guest evidence, no SSH setting changes | Phase 1 CPU homologation |
| Q-02 | Infrastructure admin: RAM/disk/IOPS/persistent volumes, load/users/mail per day | Conservative bounded defaults; no performance promise | Capacity/prod readiness |
| Q-03 | Support owner: mailboxes, TLS/auth/forwarding/trusted MTA and SMTP limits | Adapter contracts and controlled test SMTP/IMAP only | Real Phase 3 email acceptance |
| Q-04 | Operations: actual client/team/project/queue membership matrix | Deny by default; test explicit grants with synthetic test data only | Provisioning/pilot |
| Q-05 | Operations: approve 29 source-label mappings and 8 participant aliases | Preserve unresolved source; no automatic client merges/user creation | Real import |
| Q-06 | Row owners: approve ongoing row 32; resolve recurring wording versus done at row 34 | ADR-0006 model; retain source facts, no recurrence generation | Real import |
| Q-07 | Support owner: calendar, holidays, SLA targets, pause and reopen policy | Versioned model and deterministic test calendars, no real SLA promises | Phase 5 actual policy |
| Q-08 | Identity admin: OIDC issuer/claims/MFA availability | Secure local sessions, no simulated SSO/MFA | Corporate SSO when requested |
| Q-09 | Management/privacy owner: retention, deletion holds, access/export approvals | No destructive retention job; protect raw data/logs/backups | Production data policy |
| Q-10 | Support/management: desired Zammad migration/cutover/rollback | Keep current helpdesk; no API/database dependency | Optional future migration |
| Q-11 | Infrastructure/security: storage/scanner/proxy selection and CPU-approved builds | Local private storage adapter, quarantine fail-closed | Production attachment/proxy acceptance |
| Q-12 | Infrastructure admin: hypervisor ownership and CPU-model change possibility | x86-64-v1 remains mandatory | None: CPU upgrade is not assumed |
| Q-13 | Product owner: approved logo/brand and visual preferences | Provisional restrained Portuguese interface, system fonts, no invented assets or claims; review after return | Final visual approval only |
| Q-14 | Engineering/security: ongoing service-image security | Residual-finding candidates have zero reported vulnerabilities in all three actual images; blocking HIGH/CRITICAL CI and retained unfiltered reports; no risk acceptance or guest homologation | Remaining production security/readiness gates |

## Backlog after core

Current Foundation priority after the verified image/recovery slice: web ingress,
remaining identity administration UX, and a worker/Redis slice only when it has a
real durable consumer. Preserve Q-01 as the Phase1 exit gate; do not substitute
modern CI execution for the unavailable VM or begin Phase2 prematurely.

FR-013 preferences/mentions/notifications, FR-014 time tracking, FR-015 authorized
CSV/XLSX export, FR-016 advanced calendar/Gantt/dependencies, FR-017 external
portal/knowledge base. Billing/subscriptions, marketplace, advanced ITIL/CMDB,
native mobile and local AI remain outside MVP. No speculative code for backlog.

## Evidence ledger

- Phase1C-f: 27b0bcb fixes installed API/PostgreSQL/ingress high/critical image
  findings with vendor-patched Alpine artifacts and baseline gosu rebuild.
  Adds blocking all-service SCA/image CI and cross-libc logical restore proof.
  Independent review's PGDATA reuse finding was confirmed and fixed with an
  entrypoint refusal/fresh-init marker. 244 API tests passed locally on Alpine
  and in hosted CI;7 E2E, actual Docker Compose/recovery and image security gates
  passed. Zero HIGH/CRITICAL across all three actual images; lower severities
  remain visible. See the exact evidence/rollback in docs/phase-1c-evidence.md
  and ADR-0013. Actual VM/worker/Redis/web ingress and remaining Phase1 gates stay open.

- Phase 0: `docs/phase-0-report.md` and workbook reconciliation.
- Phase 1A: identity API implementation, 44 real automated checks, migrations,
  build/lint/types and evidence in `docs/phase-1-evidence.md`. Phase 1 remains
  open for administration/process/runtime/security/target-VM gates.
- Phase 1B: real browser login/account/logout, generated API types, 7 real
  HTTPS/PostgreSQL browser tests, theme/responsive/axe checks and reviewed focus
  recovery, published in `88d945c` with both Linux workflows green. Sharp
  excluded to avoid its Linux x64 SSE4.2 requirement. Phase 1C
  administration/processes/ingress/security and target-VM gates remain open.
- Phase 1C-a: restricted CLI ordinary-user provisioning, active-state changes and
  platform-role administration with atomic session revocation, audit/outbox and
  concurrent last-active-admin protection, published in c8e3920/2f3298a. Full
  83-test API suite passed; both Linux workflows green, independent review clear.
  See `docs/phase-1c-evidence.md` for publication/gates.
- Phase 1C-b: persisted team/roster API and safe account lookup with identity-only
  authorization, versioning, atomic audit/outbox and protected POST replay.
  Published in 030a3f2/a5ce79a; 160 API tests and both Linux workflows passed.
  Review finding on PATCH schema resolved. Remaining gates are in the Phase 1C report.
- Phase 1C-c: persisted constrained team read scopes, transactional restricted
  grant/revoke CLI and SQL-filtered team/roster reads. Storage/service fd92682;
  CLI/API ea7f081; reviewed publication d59709f. Local full API suite 213 passed,
  guarded migration preservation/refusal/roundtrip, API/web build/types/lint and
  unchanged generated contracts passed. Fresh independent review had no findings;
  both hosted Linux workflows passed (213 API tests, 7 browser E2E). Exact links
  and publication evidence are recorded in docs/phase-1c-evidence.md.
  Client grants, admin UI and remaining Phase 1/runtime gates are still open.
- Phase 1C-d: runtime DB privileges/file secrets63d1fa9, image/Compose ee70bea,
  review fixes7b0a933 and build-context correction7df1ebc. Final234 API tests passed
  locally and in hosted Linux; all7 browser E2E and actual Docker Compose/TLS/
  recreation/ACL/readiness/SIGTERM proof passed. Local Podman lacks cgroup memory
  controls; resource limits were preserved and validated through hosted Docker.
  See ADR-0011, docs/runbooks/api-containers.md and exact CI evidence in the Phase1C
  report. Q-14/image security and Q-01/actual CPU, recovery/load, worker/Redis/web
  ingress and remaining Phase1 gates stay open. No production/phase exit claim.
- Phase 1C-e: unused SQLite package/module removal 1d8ed76 with automatic native
  capability guard, preserving Python/bookworm and lockfiles. Same-DB scans removed
  19 SQLite findings (1 critical/5 high/9 medium/4 low), added none; 35 high
  occurrences remain open. Fresh review had no findings. All three hosted gates
  passed on 3b96e2f: 236 API tests, 7 browser E2E and actual pruned-image Compose
  behavior including builder rejection/runtime guard. See ADR-0012 and the exact
  evidence/scan reports. No production/phase exit or target-CPU claim.
- Future implementation entries must include commit, exact commands/results,
  target artifact/host when relevant and outstanding gates. Do not mark a phase
  done merely because the documentation or a subset of tests is complete.
