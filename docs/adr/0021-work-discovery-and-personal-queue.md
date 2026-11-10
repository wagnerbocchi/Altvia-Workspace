# ADR-0021: Authorized task discovery and personal queue

Date: 2026-11-10. Status: selected for incremental implementation; not qualified.
Scope: Phase 2D, FR-004 tasks only. ADR-0007's future ticket projection remains
unchanged. Direct user authorization covers implementation and main publication.

## Decision and alternatives

Extend the existing project task collection and project authorization predicate.
Use native PostgreSQL full text search with a GIN expression index. A separate
search service would violate the baseline; browser-only filtering would omit
unloaded pages and permit inconsistent scope. No new dependency or native build.

GET /work-items keeps its required project_id and WorkPage response, including
fresh creation authority independent of filters/pagination. Add single-value
status, priority, work_type, owner_id, involved_user_id, unassigned, due_presence,
due_from, due_before and q. involved_user_id means owner OR participant;
unassigned=true means owner IS NULL (participants may still exist). Filters
combine with AND; contradictory filters return no matches. due_presence is
dated/undated. due_from is inclusive and due_before exclusive, both aware UTC
instants compared against the existing due_at boundary. Missing deadlines never
match a range. Reject reversed/equal ranges, unsupported or repeated parameters.
Enums, UUIDs, aware timestamps and limit 1..100 are validated server-side.

q trims to at most 200 characters. Empty input disables search. Search title and
description, using explicit portuguese regconfig and websearch_to_tsquery: words,
quoted phrases, OR and exclusion follow PostgreSQL semantics. No prefix, fuzzy,
substring or accent-insensitive promise. Queries with no searchable terms return
no matches. Do not search comments, history, other domains or hidden resources.
Use a matching immutable to_tsvector expression GIN index; no duplicate text store.
Parameterize all values. UUID ascending order remains stable; no rank/sort mode.

GET /my-work returns a bounded task-only page for the authenticated actor. Query
the full authorized project set using project_registry.visible_projects, then
owner OR EXISTS participant, filters and pagination. Never collect one project
page or deduplicate only the result page. A task where the actor is both owner
and participant appears once. Assignment, team metadata and platform admin are
never content grants. Re-evaluate authority on every page; hidden/nonexistent
project/client/team filters both yield empty pages without metadata.

My Work accepts the same task filters plus optional project_id/client_id/team_id.
Return {items,next_cursor,as_of}; each item is a small task summary with
kind=work_item, id, project_id, project_name, title, status, priority, work_type,
due and due_at. Project name is returned only through the same SQL-authorized
join. No counts, ticket badges, write capabilities or directory lookup. Include
all states unless filtered; the UI makes this explicit. Detail owns fresh write
authority and all existing protected mutations. as_of is the response UTC time,
not a repeatable-read snapshot across requests. Concurrent edits can change
matches; refreshing restarts pagination.

Cursors bind collection, actor, project and canonical normalized filters using
a SHA-256 scope hash, excluding limit/cursor. This is binding, not authorization
or encryption. Validate current authority even for a supplied cursor. Keep old
unfiltered project cursor scope for compatibility; filtered scopes are distinct.
No search query or titles are serialized in cursor or logs.

## Browser and persistence

Extend the incumbent Impeccable Operate surface and session-owned query cache.
List and Kanban use the same filter form and authoritative API. Submit filters
deliberately; changing filters resets every page. Each status column queries and
pages independently, including loading, empty, failure, retry and navigation.
Show loaded rows, never a total inferred from a page. Open a card's task detail
to change state with the existing version/idempotency/reason/ongoing protocol;
no drag-only controls or independent transition logic. Narrow screens stack
columns and wrap controls without whole-page horizontal overflow.

Meu Trabalho has its own authenticated route and scoped project links. It states
that only tasks are supplied, allows filtering/search/paging and links to detail.
Session replacement discards queries and local state. Do not imply ticket
unification, new grants, notifications, dashboards or real import.

Migration b46087000009 adds only query indexes: GIN search plus project/status/id,
owner/id, and participant user/item. No data rewrite, new runtime grants or event.
Rollback may drop these indexes without losing work data; application rollback
can retain them. FTS uses the existing PostgreSQL artifact and still requires
actual target-VM execution before this increment is called qualified.

## Acceptance and boundary

Prove search title/description, phrases/negation/stop words/edit freshness, typed
filters/null and deadline boundary, pagination/filter binding, full-set personal
deduplication and project/client/team ceilings. Cover assignment after revocation,
both membership halves, platform/team non-grants, archived reads, no query per
personal result, migration rollback/data preservation and actual GIN use on
representative synthetic data. Browser covers real persistence, board column
paging, filter reset, empty/error recovery, personal links, keyboard, mobile,
themes, axe and session disposal. Required source review, five hosted gates and
actual x86-64-v1 packaged proof remain gates, never inferred completion.

Stop this increment at qualified task discovery. Contacts/default ticket project
contracts, member administration, milestones and Service Desk remain later work.
