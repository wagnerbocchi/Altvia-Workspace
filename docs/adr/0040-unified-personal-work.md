# ADR-0040: Authorized unified personal work

Date2026-11-13. Read-only increment development accepted2026-11-14 at1f7d5ab,
after native/browser/packaged proof, independent whole review, its one corrected
P2 and all five final hosted gates. See docs/unified-work-evidence.md for exact
results, skips, warning and limits. Automation and integrated qualification remain
separate. The master specification was read
completely. ADR0007 supplies the projection invariant; ADR0021 task discovery
and ADR0039 manual-link authority/compatibility remain unchanged. The user's
continuous-development/direct-main authorization covers implementation after
contracts; no production rollout, import or new resource grant is implied.

## Decision and alternatives

Implement real personal ticket/work consolidation independently of the later
automation writer. Existing manual N:N links supply the required data. Native
PostgreSQL queries can provide the feature without a materialized counter,
projection worker, new schema, runtime grant or dependency. A client-side merge
would miss unloaded pages; connected-component grouping would collapse distinct
tasks. Neither satisfies ADR0007.

Keep GET /api/v1/my-work and its existing task DTOs, filters, ordering and cursor
unchanged. Add GET /api/v1/my-work/unified with its own discriminated response,
filters and cursor. The existing browser /my-work route offers the unified queue
and the incumbent advanced task view. This preserves existing consumers while
the default browser view becomes the actual consolidated personal queue.

## Eligibility and full-set deduplication

For the authenticated actor, compute W from project_registry.visible_projects,
work_queries.involved and the validated work filters. Compute T from
tickets.visible, current assignee_id and the validated ticket filters. Read
archived resources under their existing read policy; do not add active-only
restrictions or infer grants from an assignment, relationship, external label,
team metadata role or platform administrator.

Return each W once. Return t in T as a standalone row only when NOT EXISTS a
ticket_work_items row connecting it to ANY eligible W. Apply this anti-join over
the entire filtered, authorized set before sorting or pagination. Never use
only the loaded work page, a transitive group or a visible ticket count. A
hidden or filtered-out linked work item cannot suppress an eligible ticket.
Different assignees, a shared task and an empty relationship set retain their
independent meanings. A link never changes either domain's state or authority.

## HTTP contract

UnifiedWorkFilters forbids unsupported/repeated keys. Fields are limit1..100
(default50), cursor(max512), kind=all|work_item|ticket(defaultall), optional
priority, client_id, team_id, work_status, ticket_status and q(max200). UUIDs,
domain enums and aware cursor instants are validated server-side. Trim q and
canonicalize empty input to absent. Apply the existing native Portuguese FTS
semantics independently to task title/description and ticket subject/description.
Do not search notes, comments, attachments or other hidden content.

Each status filter constrains only its named domain. Common priority/client/team
and q criteria apply independently to W and T. kind selects candidate domains
before suppression: ticket makes W empty, so all filtered eligible T remain
standalone; work_item omits T but retains visible provenance badges. New unified
queries have no project, work-type or due filter. Those remain available through
the unchanged advanced task endpoint/view; no ticket deadline or SLA is invented
to make their schemas match.

Response UnifiedWorkPage contains items, next_cursor and as_of (UTC response
instant). items is a strict union discriminated by kind:

- UnifiedWorkItem retains MyWorkItem's task fields and adds created_at,
  linked_tickets (maximum3) and has_more_linked_tickets (strict boolean).
- UnifiedTicket has kind=ticket, id, positive decimal-string number (the existing
  TicketOutput contract, never a JavaScript numeric value), subject (existing Subject,
  maximum300), ticket status, priority, client_id, queue_id, queue_name and
  created_at. It has no task due field, private text/count, requester or mutation
  capability.
- LinkedTicketBadge has id, the same exact decimal-string number, subject, ticket
  status and priority. Preserve BIGINT values beyond JavaScript's safe range. Return
  the first3 visible linked tickets by UUID ascending, plus a boolean when more
  VISIBLE links exist. The existing paged relationship panel owns full discovery.
  Badges represent current visible origins independently of the actor's ticket
  assignment and query status filters. They are not additional personal rows.

No total, inferred effort, notification, automation state or write capability is
returned. A page is bounded even when a task has many links. Badge enrichment
must reuse both current parent visibility predicates, with a bounded window over
only the returned work IDs. Use a fixed query count, never one ORM lookup per
result. Selection, full-set suppression and badge enrichment use one PostgreSQL
statement snapshot. A concurrent link/unlink must not produce a response that
suppresses a ticket under one link state and loses its badge under another.
This is response coherence, not a snapshot retained across page requests.
Preserve the native authenticated session lock/last_seen update; do not
introduce a read-only transaction incompatible with authentication.

## Ordering, cursor and current authority

Sort priority critical0/high1/medium2/low3, created_at ascending, UUID ascending,
then kind ascending (ticket before work_item only at an exact key tie). A real
same-UUID pair across the two independent tables must paginate without loss.

The new cursor is URL-safe base64, without padding, of ASCII
`v1|<scope>|<rank>|<UTC ISO>|<UUID>|<kind>`. Scope is unified-work:SHA256 of actor
UUID plus canonical normalized filters, excluding limit/cursor and empty q.
Require exactly six parts, versionv1, matching scope, rank0..3, an aware ISO
instant, a UUID and a valid domain. Malformed or mismatched input returns422
invalid_cursor. This is scope binding, not encryption, signing or authorization.
No title, subject or search text appears in cursor/log output.

Recheck current authority on every page and every enrichment query. Session
revocation still yields401, and hidden/nonexistent client/team filters both yield
an empty page without metadata. as_of is not a cross-request snapshot; concurrent
changes can change membership or ordering and refresh restarts pagination. A
scope filter/cursor never becomes a content grant.

## Browser, evidence and rollback

Use Impeccable on the incumbent Twenty-inspired Operate surface. Keep the route,
heading, tokens and native controls. A labeled button group selects Fila unificada
(default) or Somente tarefas (existing advanced TaskFilters/results). Own their
filters and paging in separate keyed subtrees; preserve the existing task view's
functional assertions by selecting it explicitly in its tests. New tests prove
the default unified behavior. Session replacement disposes all private queries
and local filters. Current denied states hide previously cached rows/badges.

Show independent domain labels/status and task deadlines only on task rows.
Explain bounded represented ticket origins without presenting page length as a
total. Preserve keyboard focus, actual detail links, deliberate filter submission,
loading/empty/error/retry and390/1440 light/dark/axe behavior. No mock metric or
decorative action substitutes for API results.

Acceptance covers zero/one/many relationships on both sides, different assignees,
owner plus participant, shared tasks, full-set suppression across page boundaries,
same UUID across domains, filter-driven ticket reappearance, hidden badges and
ceiling revocation, cursor binding, bounded query count and representative SQL
plans. Keep all legacy endpoint/cursor tests. Source/visual reviews, actual
packaged persistence/current scope and exact-source hosted/security gates remain
required. Add an index only if measured evidence requires a separately contracted
reversible migration; this decision reserves none.

Removing this read surface can retain every existing row and return users to the
legacy task endpoint. It does not relax ADR0039's minimum compatible API/worker
floor for retained link history. Actual compatible-image rollback, encrypted
backup/restore, final integrated x86-64-v1 qualification and production acceptance
remain separate gates. Automation, SLA, analytics and import are not implemented
by this contract. Real provider/mapping/retention/calendar questions remain in
the existing roadmap register.
