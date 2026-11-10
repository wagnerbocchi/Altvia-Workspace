# ADR-0025: Task-owned external participants

Date: 2026-11-10. Status: accepted and implemented, Phase 2H development complete.
Contracts 6a03689 preceded backend a4c456d and browser f5b4e2a. All five hosted
gates passed with 523 API/78 browser tests; see the Phase 2H evidence report.
Final integrated target qualification remains deferred under the user's cadence.
Master sections 2.1, 4/FR-003 and 8.4 require involved people without silently
turning an unresolved third party into an employee. User delegated routine choices,
direct main publication and local/CI development before final VM homologation.

## Decision and alternatives

Extend the existing work aggregate with task-owned external labels. An external
participant is supplied attribution, not a verified identity, user, assignee,
requester or access grant. It never sends email or enters an employee's My Work.
Use existing PostgreSQL, work authorization, write locks, version/ETag and events.
No new service, dependency, ISA, route or independent lifecycle is needed.

Linking client_contacts now would require both contact and project ACL and a policy
for readers who can see a task but cannot see client contacts. It would also leave
internal-project third parties unresolved. A global external directory or fake
User account would introduce unintended identity and content discovery. Free task
description text already works but cannot distinguish participants structurally.
The chosen bounded labels meet the requirement without those extra trust paths.
Contact association is explicitly deferred (Q-18), not implied by a matching name.

## Data and HTTP

Expand-only migration b46087000012 adds work_item_external_participants, composite
PK(work_item_id,unresolved_label), FK to work_items with RESTRICT, Unicode label
VARCHAR(150), nonempty/trimmed and no CR/LF. PostgreSQL rejects NUL. API trims
labels, rejects embedded NUL/CR/LF, duplicates after trimming, null and more than
50 labels. Equality is exact and case-sensitive; spelling is not identity proof.
Reads sort labels by Unicode code point, independent of database collation.
Existing tasks return an empty list; no source data, account or contact is inferred.

POST /work-items accepts optional external_participants: string[], default [].
PATCH /work-items/{id} accepts the same field, where [] explicitly clears it,
omission preserves it and null is invalid. WorkOutput always includes the list.
Its default [] also reads pre-expansion persisted transition receipts safely.
The create fingerprint omits an empty external_participants field, preserving the
pre-expansion canonical body and existing idempotency keys. Nonempty original
lists remain part of the protected intent. Creation receipts remain IDs only.

Only current managers set external participants, including submitting an unchanged
PATCH field. Agents can create self-owned tasks with no externals and edit other
authorized content without resubmitting this field. Readers see labels solely
through scoped work responses, not a contact/account directory. Assignments,
sessions, customer ceilings, search and My Work predicates remain unchanged.

## Atomicity and events

Reuse identity write serialization before authentication, project graph lock,
scoped task row lock, current writable references and task If-Match. Real changes
replace the bounded label set and advance the task once with audit/outbox; a
reordered identical set is a no-op. Stale writes, exhausted versions and errors
roll back the whole mutation. Project/member versions are not assignment versions.

External-only changes emit work_item.updated with changed_fields containing only
the field name external_participants, never labels, emails or free text. They do
not emit work_item.assigned. Extend the existing strict WorkEventPayload allowlist
and reuse its worker/deduplication and scoped work-only activity feed. The API gets
SELECT/INSERT/DELETE on the new link table, no UPDATE; worker gets no access.
Link removal follows the existing assignment lifecycle; audit/activity is retained.

## Browser and acceptance

Extend the incumbent WorkForm and task detail using Impeccable. Managers enter one
external label per line, maximum 50, 1..150 Unicode code points each. Empty lines
are ignored in this form. Explain that names do not create accounts or grant
access. Display inert plain text separately from internal contributors, including
an explicit empty state. Preserve reviewed versions, original uncertain create
intent, independent list/read recovery and session ownership. No contact lookup,
email field, public notification, picker service or new navigation is introduced.

Prove SQL persistence/constraints, existing-data migration, runtime least privilege,
manager/agent/viewer/cross-client boundaries, no grants/My Work side effect, strict
events/redaction, replay including legacy fingerprints/receipts, no-op/stale/races,
version exhaustion rollback and archived references. Real browser tests cover
create/edit/clear/reload, original-intent recovery, stale review, plaintext,
manager-only controls and mobile/light/dark/axe/keyboard. Existing work tests must
remain green. Run local and five hosted gates; final integrated VM proof is deferred.

## Rollback

Downgrade refuses any external link or durable work event/audit/activity that names
external_participants, even after links were cleared. Preserve expanded data and a
worker that validates the new changed field, or stop that worker until compatible
code resumes. Old code does not write or clear this table; no forced downgrade,
volume reset, real import, client identity mapping or production deployment.
