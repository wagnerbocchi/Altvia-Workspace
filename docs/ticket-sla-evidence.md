# Ticket SLA development evidence

ADR0042 and docs/plans/2026-11-14-ticket-sla.md define the selected contract.
SLA capability is not complete. Task1 implements only exact bounded calendar
arithmetic; persisted configuration, native cycles/evaluator, UI and acceptance
remain pending. No hours, holidays or targets are configured for Altvia.

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
