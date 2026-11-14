# Ticket SLA development evidence

ADR0042 and docs/plans/2026-11-14-ticket-sla.md define the selected contract.
SLA capability is not complete. Task1 calendar arithmetic and Task2's persisted
configuration APIs have development evidence below. Native cycles/evaluator, UI
and capability acceptance remain pending. No hours, holidays or targets are
configured for Altvia.

## Scoped configuration APIs

Eight actual nested calendar/policy list/detail/create/PATCH operations now use
the existing identity-before-authentication and client/team/queue/own lock order.
The shared current authority owner was extracted from the actual automation
caller, preserving its aliases and behavior. Shared strict HTTP query/version
validation lives in admin_http. No alternate permission model is introduced.

Calendars capture trusted installed timezone bytes only after protected replay;
omitted timezone preserves them and explicit same-name selection can refresh
them. Policies start disabled, retain immutable null-aware selectors and explicitly
review an immutable calendar revision. Selection ranks exact/category/priority/
default before current reference eligibility. Historical authorizer departure
does not disable business policy. No-op/archived disable/committed replay retain
later state; foreign scope, stale versions, overflow and uncertain repeated intent
have real native checks. Private configuration events are strictly validated and
acknowledged without a shared activity projection, even with the worker credential.

config-red01 failed actual POST404 versus201 before the HTTP source. Native
config-green01 passed61 cases in57.83s (15 configuration,46 calendar), with
Ruff/check/format and mypy80. Local53 schema cases plus46 calendar cases passed99
in0.29s. Native selector-red01 failed the missing selection owner before source.
config-green02 ran no tests because the selected legacy filename was wrong;
the corrected collection was checked before running config-green03. That native
batch passed161 cases in325.23s, including configuration/storage, automation,
queue access and client registry. One incumbent Pydantic identifier alias warning
in the concurrent queue-access case is retained. Native static gates passed.

boundaries01 passed three cases and failed one synthetic fixture at the wrong
module for set_client_access; the fixture now calls its real client_registry
owner. integrity-red01 reproduced two product errors before correction: checking
a historical active flag instead of current calendar eligibility, and silently
falling back when a selected current policy revision is missing. The latter now
fails503; no broader policy is substituted. Current calendar eligibility gates an
explicit historical math revision after reactivation. Native
config-integrity-green01 passed all55 cases in227.02s: current configuration,
cursor/concurrency/artifact/privacy/integrity boundaries and the full automation
execution suite. Current API product hashes match that passing frozen snapshot.
Its subsequent Ruff check failed one formatting-only long test line; local
formatting/static checks pass after correction, with a final native batch pending.

OpenAPI/TypeScript generation ran twice with identical bytes. All81 prior paths
and155 prior components remain exactly unchanged. Local web typegen/ESLint/types
passed. Local source SAST retains35 low findings,0 blocking, without an ignore.
No UI, timer, native cycle, worker evaluator, production policy or final target
qualification is implied by this configuration increment.

## Configuration storage foundation

Migration31 adds only four live configuration tables: immutable-scope calendar
and policy identities plus append-only complete revisions. Canonical bounded
window/holiday JSONB is checked by invoker-only immutable SQL validators with
fixed pg_catalog search path. Composite foreign keys preserve same-customer/
queue/calendar/category scope; NULLS NOT DISTINCT enforces selector uniqueness
including disabled defaults. TZif size/magic/digest and finite targets/explicit
pause choices are checked natively. No policy or cycle is seeded.

The API role has SELECT/INSERT and only identity version/timestamp UPDATE; it
cannot mutate snapshots, scope or delete history. The worker receives no SLA
table or validator EXECUTE grant in this foundation. Actual runtime-role inserts,
denied writes/reads/helper calls, malformed nested data, null pause elements,
empty holidays/pauses, independent maximum targets and all four history/receipt
contraction guards are exercised. An empty roundtrip preserves real legacy
identity/event rows and passes Alembic metadata comparison.

schema-red01 failed the actual four-table existence assertion before source.
schema-green01 stopped at a synthetic fixture's missing required legacy Client
timestamps; those fixture values were supplied without relaxing product schema.
schema-green02 passed35 storage cases. Final schema-nearest01 passed90 cases in
187.45s:39 storage plus incumbent automation migration, runtime provisioning and
queue regressions. Ruff/check/format and strict mypy passed against the frozen
native source. PostgreSQL stopped, volumes retained, and only the verified empty
task-owned internal network was removed. This is isolated development evidence,
not API/cycle capability or final target qualification.

## Frozen business-calendar foundation

The installed standard library now captures trusted IANA TZif bytes/hash and
builds immutable canonical weekly-window/holiday snapshots. Touching windows
coalesce; overlap, duplicate, invalid/mutable/timezone/path input is rejected.
Arithmetic intersects actual UTC availability, including repeated/missing local
times, holidays across midnight and second-based offsets. Integer microseconds
preserve partial instants. Deadline steps return explicit remaining budget and
progress, never an unbounded scan or fabricated timestamp.

Each call covers at most32 UTC dates in2000..2099, with an exclusive endpoint
allowed at2100-01-01. Frozen rules are independent of a later installed tzdata
revision, including different bytes under the same timezone name. This adds no
route, DTO, DB table, policy seed, worker action or task deadline synchronization.
The actual existing API image inventory already includes tzdata2026f-r0;
Windows uses its existing installed tzdata resource. No dependency was added.

Actual local calendar-red01 failed the missing business-time owner assertion in
0.17s before implementation. Local calendar-green01 then passed44 cases in0.28s.
The first mypy run found an IO[bytes]/BinaryIO annotation mismatch at the standard
resource reader; using the standard IO[bytes] type fixed it without runtime
behavior changes. Ruff/check/format and strict mypy76 passed afterward.

Native calendar-native01 stopped before tests because the root-owned private
runner/map mounts lacked read permission for the nonroot test UID. Only those
task-owned nonsecret mounts were made read-only0444 inside their protected
parent. No server/security setting or application privilege was changed.
calendar-native02 passed44 cases in1.53s, static gates and actual cold/warm/
distinct-snapshot/memory bounds. It is retained as an intermediate result.

Final calendar-native03 passed all46 cases in1.19s, including the additional
same-name/different-frozen-rules and partial-microsecond deadline cases. Native
Ruff/check/format and mypy76 passed. Tests cover NY gap/fold partial windows and
23/25-hour local days, Lord_Howe half-hour shifts, Apia's skipped date/local holiday,
and a trusted synthetic TZif with a30-second offset. The latter exercises old
second-based offsets outside the supported real historical date range; it is not
an HTTP-upload feature. Current math/test hashes match the final frozen source.

The isolated native image runs with no network, nonroot UID10001, a read-only
root/source, tmpfs, no capabilities, no-new-privileges,1 CPU and512MiB memory.
Native benchmark: cold32-day evaluation0.390245s; warm0.000169s;32 distinct
snapshots0.400241s. Peak pure-engine RSS25100KiB. Stressing300 dates retained
256 cached day results; parsed zones are independently bounded to16. All passed
the predefined2s cold/distinct and96MiB pure-engine limits. These are development
engine measurements, not a whole-worker load test or a production SLA promise.

Exact commands, image ID, inputs, pytest JUnit, successful/failed channels and
benchmark metadata remain private under .superpowers/sdd/2026-11-14-ticket-sla
and the selected isolated development host's ticket-sla-20261114 directory.
All transferred final evidence hashes were verified. This does not qualify a
changed production image or close final integrated x86-64-v1 qualification.
