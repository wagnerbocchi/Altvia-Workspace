# ADR-0007: Unified work without double representation

Date: 2026-11-08. Status: selected initial projection contract.

Context: N:N ticket/work relationships and different assignees make naive UNION
or connected-component grouping misleading. A ticket can represent multiple
independent tasks; a task can serve several requests.

Decision: for authenticated user and validated filters, first compute all
authorized eligible work items W (owner or assignee) and eligible tickets T
(assigned user). Apply ACL and filters before projection. Return each W once,
with visible linked tickets as badges. Return a ticket t in T as a standalone
row only if no item in W links t. Deduplicate BEFORE sorting/pagination.
Never deduplicate just the current page or drop a task because another task
shares a ticket. Hidden links never suppress visible work or leak metadata.

Filter semantics: each candidate independently satisfies common priority/client/
date criteria. Status filters are domain-specific, not an arbitrary shared
status enum. A ticket can reappear if its linked task does not qualify under
the current filter/user. Explain represented origins in UI. Task deadline and
ticket SLA use separate typed fields and consistent sort rules for missing dates.

Examples: one ticket linked to two eligible tasks yields two rows; two tickets
linked to one eligible task yields one row with two badges. Ticket assigned A
linked to task owned B yields a standalone ticket for A and task for B. No
visible eligible linked task means ticket is retained. Changing filters does
not silently lose the ticket. Shared task is counted once in employee effort.

Analytics exposes distinct ticket_count/work_item_count and unified_count with
documented predicates. Time entries attach to exactly one target, never counted
again through a relationship. No transitive graph grouping; it would merge
independent work and complicate ACL/pagination. No count hardcoded in production.

Proof: zero/one/many links on both sides, cross-client denial, partial ACL,
different assignees, filtering, reopen, independent states and page boundaries.
