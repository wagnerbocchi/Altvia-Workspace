# Manual ticket operations

ADR-0028 defines the manual ticket contracts. Apply expanded migration
b46087000015 with owner credentials and run the existing runtime provisioner.
The API receives ticket SELECT/INSERT/UPDATE and history SELECT/INSERT.
Worker projects strict outbox IDs without ticket, customer or contact grants.

## Access and workflow

Every ticket read and action needs an explicit queue role and customer ceiling.
Configuration administration and team/client/project roles confer independent
authority. Provision real queue roles through the reviewed queue member flow.
Customer ceiling changes retain their existing explicit administration protocol.
Queue agent creates and claims unassigned tickets. Editing/transitions require
current assignment. Queue operations_manager additionally assigns eligible active
accounts and replaces requesters with active contacts from the same customer.
Viewer reads. Archived historical references remain readable.

Open Service Desk > Chamados from the account screen. Select a queue and customer,
then a requester, optional category/assignee, priority, subject and description.
Review the exact reference labels and content before creating. Requester labels
remain unverified. The generated number is a decimal string through HTTP/browser.
Customer and queue remain fixed throughout this increment.

Use the scoped inbox to search native Portuguese subject/description FTS and
filter queue, state, priority and assignment. The row's customer action filters
to that already-authorized customer. Each page has independent bounded paging.
Open a ticket for current details, assignment/claim, available state changes and
immutable descending state history. The separate activity feed may project later.

Configuration managers edit the queue's fixed manual-close/reopen flags with
its reviewed version. Both flags default false. Closing resolved tickets requires
queue manager authority. Reopening closed tickets requires manager authority.
Pending/resolved entry and reopening require a nonblank reason. These flags
define manual eligibility. Operational timers, SLA hours and automatic closure
await their separate approved contracts and business inputs.

## Recovery and data preservation

Keep the original Idempotency-Key, request body and reviewed If-Match when a
protected create/claim/transition response is uncertain. The browser retains that
intent and provides an explicit verification action. A failed read preserves it.
After a confirmed receipt, refresh authoritative ticket state before another write.
Stale edits require deliberate reload and review. Missing/hidden scope returns404,
readable forbidden writes403, malformed fields/protocol422, missing version/key428,
and stale or ineligible state409. Current authority precedes receipt replay.

Reads, coherent no-ops and committed receipts survive parent archive. Actual
effects require active customer/team/queue. New references must be eligible now.
Closed tickets require reopening before actual edit/assignment. State history,
current timestamps, redacted audit/outbox and protected receipts commit together.
Subjects, descriptions, reasons and email addresses remain outside event metadata.

Application rollback retains the expanded schema and compatible event consumer.
Schema downgrade refuses any durable ticket/events or configured workflow/history.
Never contract this schema by discarding data. Empty upgrade/downgrade round trips
preserve pre-existing queue data and grants.

## Validation

Run the disposable local PostgreSQL suites and rebuilt browser tests using the
existing guarded runner. Complete all five exact-source hosted workflows and
packaged restart persistence proof. Check complete image scanner inventories.
Consolidated x86-64-v1 target qualification follows remaining MVP development,
under the user's current cadence. This increment introduces no new dependency.
