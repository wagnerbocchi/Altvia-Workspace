# Phase 2D task discovery evidence

Date: 2026-11-10. Scope: ADR-0021 task filters, native PostgreSQL search,
independently paged project board and task-only personal queue. Qualification
remains open until the changed artifacts pass hosted and actual target-VM gates.
Phase 2 and production readiness remain open.

## Behavior and boundaries

The existing project task list accepts typed status, priority, work type, owner,
owner-or-participant, unassigned, deadline presence and aware deadline-range
filters. Title and description use Portuguese websearch_to_tsquery with a native
GIN expression index. No service, dependency or ISA requirement was added.
Unknown/repeated query parameters and numeric or timezone-free range timestamps
are refused. Filtered cursors bind the current actor and normalized criteria;
the existing unfiltered project cursor contract remains compatible.

GET /my-work applies the complete visible-project SQL predicate before filtering,
ordering and pagination. Owner OR participant EXISTS selects each task once.
Customer ceilings and both required membership halves remain mandatory. Team
metadata, assignment and platform administration never grant project content.
Project names are returned only within that scope. There are no global counts,
ticket rows or per-result permission queries. Deadline precision is preserved.

The browser deliberately applies native labeled filters, resets paging with each
applied query and supports independent board-column loading, paging and recovery.
Additional filters can be expanded without forcing a full-form scroll to results.
Desktop lanes remain stable for populated and empty states; narrow screens stack.
Existing task detail owns all mutations. Creation stays mounted independently of
filter/page changes, retaining uncertain original intent. Refresh/recovery also
updates creation authority; failed authority reads lock new creation.

Migration b46087000009 changes indexes only. Downgrade preserves task/history data
and restores former owner/participant indexes. The incumbent identity, themes,
tokens and session-owned cache are preserved. Runbook: runbooks/work-items.md.

Contracts preceded implementation in 215eb31. Backend and generated contracts:
4d56e97bfff434b14e121f5508ba1038f1558b7b. Final browser/packaged revision and
qualification evidence will be recorded after their required gates pass.

## Local proof and corrected failures

- Initial missing-behavior API tests failed before implementation. Focused
  discovery/storage proof: 34 passed in 72.26 seconds on real PostgreSQL.
- Complete API: 424 passed in 141.30 seconds. Ruff check/format, strict mypy,
  generated OpenAPI/TypeScript and web checks passed.
- Search proof covers Portuguese words, phrases, exclusions, stopwords, edit
  freshness, range bounds, null deadlines and actual GIN selection over 6000
  synthetic rows. SQL/query-count, scope revocation, platform non-grant,
  owner/participant deduplication, cursor binding and rollback are exercised.
- Fresh source review found one P2 recovery defect: discovery refresh did not
  recover independent creation authority or observe fresh archival there. A
  failing browser regression preceded the fix; the focused four-test suite
  passed afterward in 15.6 seconds. No second source review was substituted.
- The first complete browser run passed 51 of 52 tests. Its existing subtask
  test assumed the principal task was on the first picker page; new synthetic
  discovery tasks made that assumption false. The test now follows actual
  picker pagination. Production paging and timeouts were not weakened.
- The exact-instant directory assertion also assumed a first-page match. It now
  finds its own task across pages, waits for loaded results and checks that row's
  timezone. The corrected instant test passed in the subsequent full attempt.
- Final affected browser suite: all10 work/discovery tests passed in49.8 seconds,
  including real persistence, write recovery, exact instants, personal dedup,
  column paging, authority recovery, accessibility and responsive captures.
  Final web lint/types, production build, Python source/wheel build and packaged
  script syntax/Ruff checks passed.
- Later full Windows attempts encountered an internal axe finishRun JSON.parse
  error on the unchanged account accessibility surface. Worker restarts lost
  in-memory login reuse, causing subsequent 429 source-limit failures. No login
  cap, accessibility rule or production behavior was relaxed. An isolated real
  account diagnostic passed eight scans; a synthetic probe passed60 JSON round
  trips and12 axe scans. These probes do not establish the intermittent cause.
  Full-suite Linux execution remains required; no passing complete local browser
  run is claimed for this increment.
- Impeccable's full finish review requested compact filters and stable desktop
  lanes. All twelve same-size theme/viewport recaptures were inspected; its
  round-1 verdict scored both fixes resolved with disposition ship. This verdict
  covers those scored fixes. The prescribed documenter verified the incumbent
  extension and the updated PRODUCT.md. DESIGN.md and sidecar remain unchanged;
  preexisting empty narrative.rules drift is reported without repair.

## Remaining qualification gates

Hosted complete browser/API, source/image security and packaged Docker gates are
pending; local full-suite axe execution remains unresolved. The expanded packaged
proof includes personal deduplication, scope, five states, persisted search and
transaction-rolled-back native GIN selection, plus actual mobile board/personal
navigation. Adding assertions is not evidence that they have executed.

Actual changed-artifact x86-64-v1 proof requires an authenticated task SSH master
to the supplied VM. Password entry occurs only in the user's interactive terminal;
no credential is requested in chat or stored. The previous task-core environment
and retained volumes must remain intact. New proof uses a unique private directory,
synthetic data, loopback-only ingress and unchanged server security configuration.
No production deployment, real import or Zammad retirement is authorized here.
