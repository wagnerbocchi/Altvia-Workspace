# ADR-0004: Transactional outbox and stable business effects

Date: 2026-11-08. Status: selected design. Queue library not yet selected.

Context: ticket assignment and mail jobs must survive restarts/retry/race without
duplicate work. Redis-only publication between commit and enqueue can lose events.

Decision: write aggregate/history/audit/outbox in one Postgres transaction.
Dispatcher leases with SKIP LOCKED, persists attempts/lease expiry, republishes
after failure. Transport is at least once. Consumer transaction claims
`(consumer,event_id)` and business key before domain mutation and commits all
effects together. Redelivery after committed effect observes the existing record.

Task creation unique key `(rule_id, action_id, ticket_id)` intentionally
survives new event IDs, rule revisions, reassignment and reopen. Execution ledger
also records event and rule revision. Link/use an existing logical work item when
appropriate. Multiple independent rule actions can create multiple tasks only
if explicitly configured. No project/owner resolution means durable triage with
reason and no placeholder project. Reassignment never takes over in-progress
ownership implicitly; closed ticket never auto-completes linked work.

Action identity is an immutable server-assigned UUID, not array position.
Reordering retains IDs, removal tombstones them and replacement receives a new
ID with explicit new-work review. IDs cannot be reused. Rule revision snapshots
retain the original action schema so historical effects remain explainable.

Retry transient errors with exponential backoff and jitter, initial proposal
8 attempts, 5 s initial, 15 min cap. Permanent validation/auth errors quarantine
immediately. Exhausted jobs enter logical DLQ with safe error, alert and explicit
replay; no data purge. Rule actions are schema allowlisted, bounded conditions,
no script/expression execution. Worker rechecks current authorization/scope.

Alternatives: synchronous-only side effects block requests and fail remote I/O;
distributed exactly-once claims exceed transport guarantees; event-ID-only
deduplication fails reassignment/reopen. PostgreSQL outbox is existing durable
infrastructure and avoids another mandatory service.

Proof: crash before/after enqueue, after effect commit before acknowledgement,
Redis loss, two concurrent workers, duplicate assignment/reopen and explicit
DLQ replay. Verify no lost event or second logical task. SMTP uncertainty remains
separate and cannot be solved by database uniqueness alone (ADR-0005).
