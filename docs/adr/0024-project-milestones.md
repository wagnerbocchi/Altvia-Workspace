# ADR-0024: Basic project milestones

Date: 2026-11-10. Status: selected before implementation, Phase 2G.
Master sections 6/7/8.3 require persisted project milestones. User delegated
routine decisions and deferred target-VM homologation until MVP development ends.

## Decision

Add a small project-owned milestone registry using existing scoped project reads,
identity-first write serialization, optimistic versions, protected POST receipts
and project activity. A milestone has title, optional deadline, and state
planned|done|cancelled. It does not create tasks, synchronize work states or grant
access. Advanced scheduling, dependency/Gantt planning and automatic completion
percentages remain outside this slice. Manual milestones avoid inventing progress
or coupling independent work lifecycles. A task-link subsystem would add scope
without a master requirement; a visual-only milestone list would not be complete.

## Data and time

Expand-only migration b46087000011 adds project_milestones: UUID PK, project_id FK
RESTRICT, title VARCHAR(300) trimmed/nonempty, state VARCHAR(20), positive version,
UTC created_at/updated_at and the same four deadline fields as work items. Index
(project_id,id) supports UUID paging. Reuse the exact date/instant deadline DTO,
PostgreSQL local-day boundary conversion and timezone/DST validation. Date means
the whole selected local day; instant means an aware exact timestamp. No deadline
is invented. Consolidate these existing helpers in altvia.deadlines, retaining
compatible re-exports for work callers and existing generated DTO shapes.

States start planned. planned can become done or cancelled; either terminal state
can reopen to planned. Switching directly between terminal states returns409.
Same-state/no-field-change is a no-op, preserving versions/events, even after
reference archival. No physical delete: cancellation retains history.

## Authorization and atomicity

All reads authorize the parent project, including customer ceiling. A nested ID
must belong to that parent. Hidden/absent parent or cross-project milestone is404;
readable non-manager write is403. Platform/team metadata never bypass content ACL.
All writes acquire the identity advisory lock before authentication, then lock
Project, then the milestone. Actual writes require active project/owning team/
customer; archived references remain readable and permit committed POST replay.

Real changes advance the milestone and Project versions atomically with redacted
audit/outbox. New milestones start version1. No session revocation or membership
effect is introduced. Project activity receives project.milestone_created/updated,
aggregate_type project, aggregate_id Project.id, aggregate_version Project.version,
actor/correlation and milestone_id; updates add only changed field names from
title,due,state. Payloads contain no titles, deadline input or arbitrary text.
The worker validates those exact fields and deduplicates using its existing ledger.
Identity/client activity must not expose milestone events. Worker gains no table
access; runtime API gets SELECT/INSERT/UPDATE, never DELETE on this new table.

## HTTP contract

All paths start /api/v1/projects/{project_id}/milestones.

| Route | Contract |
| --- | --- |
| GET collection | Scoped stable UUID page, limit1..100/default50, actor+parent cursor, no counts |
| POST collection | Strict {title,due?}; Origin/CSRF/Idempotency-Key; receipt201 {project_id,milestone_id}, replay200 after fresh management |
| GET /{id} | Current milestone, due/due_at, version/ETag/UTC timestamps and can_manage |
| PATCH /{id} | Strict nonempty {title?,due?,state?}; milestone If-Match; nullable due clears; title/state cannot be null; current record/ETag200 |

POST replay returns only original IDs and never resets current data or state.
Fresh authority is checked before receipt lookup; archived references do not
invalidate a committed receipt. Missing precondition428, malformed422, stale409,
exhausted version409. Unsupported/repeated collection query fields return422.
All transport stays no-store and plain text. Resource scope is immutable.
Records and pages expose project_writable as scoped active-reference eligibility,
independent of can_manage authority, so the browser can disable unavailable writes
even when a project's own active flag is unchanged or its list is empty.

## Browser and acceptance

Project detail links to a dedicated milestones directory; each milestone has a
detail route. Preserve the incumbent Impeccable Operate system. Managers create,
edit title/deadline, conclude/cancel/reopen; readers only consult. Cancel/reopen
are deliberate confirmed actions. Independent parent/list recovery must retain an
uncertain POST's original body/key and session owner. Capture the reviewed
milestone version when opening edit/confirmation; never rebase it silently.
Retain an exact instant unchanged when editing unrelated fields, including
sub-millisecond precision; UTC entry is explicit and date-only timezone is shown.

Prove migration preservation/refused destructive downgrade, least privileges,
deadline boundaries, cross-project/client ACL, replay/no-op, version races,
state transitions, strict redacted event projection and actual persisted browser
operations with keyboard/axe/light/dark/mobile recovery. Existing work deadline
tests must continue passing after consolidation. Use local/hosted CI proof now;
final integrated x86-64-v1 homologation remains pending under the new user cadence.

## Rollback

Downgrade refuses any milestone or related durable audit/outbox/activity data
before DDL. Preserve expanded table/data and a compatible worker on application
rollback; old workers cannot project the new event names. Do not reset volumes.
No real data import, new dependency, external engine or production deployment.
External work participants remain the next bounded Phase 2 slice.
