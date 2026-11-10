# Phase 2 development traceability audit

Date: 2026-11-10. Phase 2 development is complete. Final Phase 2H source f5b4e2a
passed all five hosted gates, with 523 API and 78 browser tests, packaged
persistence/recovery, zero blocking source findings and zero reported image
vulnerabilities. Final integrated target qualification is a separate deferred gate.

## Scope covered

The master Phase 2 gate is operation of an authorized project and its tasks using
real persistence rather than simulated UI. FR-002/003, the task portion of FR-004
and their scoped FR-012 history are traced below. Contracts preceded each slice.

| Capability | Contract and actual delivery | Evidence |
| --- | --- | --- |
| Clients and explicit customer access | ADR-0018: persisted registry, selected manager, separate customer ceiling and role; no implicit platform bypass | phase-2a-client-evidence.md |
| Internal/customer projects and areas | ADR-0019: multiple projects per customer, immutable scope/team/customer, explicit management, shared area classification without content grants | phase-2b-project-evidence.md |
| Core work | ADR-0020: real tasks/subtasks, graph integrity, owner/internal contributors, dates/instants, blocking/completion/reopen, comments and attributable history | phase-2c-work-evidence.md; later shared deadline regressions in Phase 2G |
| Discovery | ADR-0021: typed list filters, PostgreSQL Portuguese FTS/GIN, independently paged Kanban and deduplicated task-only My Work after authorization | phase-2d-discovery-evidence.md |
| Contacts/default project | ADR-0022: client-scoped unverified external contacts and explicit same-client default, without account, verification, email or ticket side effects | phase-2e-contact-evidence.md |
| Project membership | ADR-0023: known-email reviewed browser grants/roles/removal, immutable protected intent, fresh authority, session invalidation and scoped events | phase-2f-member-evidence.md |
| Basic milestones | ADR-0024: persisted planned/done/cancelled deliveries, optional exact deadlines, explicit reopening and independent task lifecycle | phase-2g-milestone-evidence.md |
| External involvement | ADR-0025: bounded task-owned external labels, manager writes, inert scoped reads, no inferred identity/grant and preserved old receipts | phase-2h-external-participant-evidence.md |

Task and ticket state stay separate. Owner/internal involvement remains different
from supplied outside attribution. Neither team roster, classification, assignment,
external names nor platform administration supplies missing customer content rights.
No production account matrix or workbook mapping was invented.

## Acceptance boundary

Prior slice reports contain their exact source/test/runtime evidence. Phase 2G
and Phase 2H follow the user's updated local/CI cadence, so older native image
qualification cannot be extended to changed application images or vendor packages.
Phase 2H passed final full hosted API/browser, actual packaged persistence/recovery,
source security and five-image scanning. The packaged check explicitly verifies
external labels after API/PostgreSQL recreation. Source review's Unicode issue
was regraded Important and fixed with real RED/GREEN plus complete passing suites;
Impeccable returned ship and documented the unchanged incumbent design system.
Failed and passing capture/Unicode/rollback-test evidence is retained; no passing
result is inferred from a review. See the exact five runs in the Phase 2H report.

Final integrated qualification on the actual x86-64-v1 VM remains mandatory after
remaining MVP development. No target SSH, production deployment, real import,
mailbox use or Zammad retirement follows from Phase 2 development acceptance.

## Later delivery and unresolved inputs

Native queues, categories, tickets, public/internal messages, private attachments
and IMAP/SMTP belong to Phase 3. Controlled test mailboxes/transports can support
independent development; actual provider/MTA/verification policy stays Q-03/Q-16.
The next bounded implementation should establish those contracts before code.

Ticket/work N:N, structured automation and consolidated ticket/task My Work remain
Phase 4. Real progress/workload dashboards and operational analytics, SLA calendar
semantics and reconciled workbook import remain Phase 5. No placeholder counts or
imported assignments substitute for these features. Retention, capacity, storage/
scanner approval, real membership and import mappings remain the recorded owner
decisions, not defaults invented to close a gate.

Q-18 concerns possible future contact association for task labels; it does not
block the delivered unverified-label workflow. P1 notifications/time tracking/
exports and P2 advanced dependencies/Gantt/portal remain their explicit backlog.
The current product does not yet meet the full MVP or replace the live help desk.
