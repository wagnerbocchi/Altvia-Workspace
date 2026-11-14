# Unified personal work evidence

ADR0040 read projection is in development. This document records backend proof;
it does not accept the browser increment, whole MVP or target qualification.
Accepted manual links remain separately documented in ticket-work-link-evidence.md.

## Backend behavior and compatibility

GET /api/v1/my-work/unified combines current authorized personally involved work
and assigned tickets. Native PostgreSQL full-set suppression precedes keyset
pagination. Each task remains independent; visible linked ticket badges are
bounded to three plus visible-only more. No schema, privilege, worker, dependency
or domain lifecycle change is introduced. The legacy task-only endpoint remains.

The initial concurrent-unlink implementation used separate selection and badge
queries. Native unlink-red02 reproduced a lost assigned ticket after a second
authenticated session committed DELETE between those queries. unlink-red01 was
an invalid fixture attempt: the independent client lacked the required Origin
header and received403 before the concurrency exercise. Both outcomes are retained.

Selection and bounded enrichment now execute in one PostgreSQL statement
snapshot. The existing authentication/session lock and transaction isolation
remain unchanged. This provides response coherence, not a cross-request snapshot.

## Executed native checks

Private evidence root:
`.superpowers/sdd/2026-11-13-unified-personal-work/` locally, and
`/root/altvia-workspace-dev/.superpowers/unified-personal-work-20261113` on altvia-vm.
Fresh private altvia_test databases, internal container networks and explicit test
opt-in were used. No public port, Docker socket mount or host configuration change.
Runtime source was mounted read-only and mapped inputs remained unchanged.

- green05: pytest apps/api/tests/test_unified_work.py -q,
  34 passed in110.53s. Includes actual native concurrent unlink, current ACL,
  full-set paging, same UUID across domains, filters, deadlines, cursor binding,
  required generated discriminators and positive constant-query instrumentation.
- green05: ruff check apps/api, ruff format --check apps/api and mypy passed;
  mypy checked68 source files.
- green05: the complete nearest discovery/manual-link/link-activity/project-
  milestone modules passed114 cases in419.13s. Together with the34 new cases,
  this run passed148 API cases. Frozen source maps remained unchanged.
- Native EXPLAIN ANALYZE/BUFFERS on6,001 eligible tasks returned100 work rows,
  plus one cursor probe. Root Sort had101 rows, execution39.666ms,
  planning8.064ms. This is measured synthetic evidence, not a production SLO.
- generation01: locked offline uv preparation, OpenAPI export and TypeScript
  generation ran twice; repeated output bytes were stable. pnpm web:check passed.
  The subsequent concurrency change affects the query/test only, not schemas.
  Comparison against the preceding committed OpenAPI preserved every incumbent
  component schema and the complete /api/v1/my-work operation.

API proof tools image:
`sha256:7b3a8bfb5a2536e7bb81405179d1be4021ddf255c1758458153ca7353afcf651`.
Generation tools image:
`sha256:a30ee9ab5640f44f3cf4d3feb24a9edbaf3905bc8f62c20b4413e3876e1ae574`.
These development tools do not replace qualification of the shipped images.

## Remaining acceptance

Real browser completion and rendered review,
packaged recreation/current scope, independent whole-increment review and all
five exact-source hosted/security workflows remain required. Compatible-image
rollback, encrypted backup/restore and final integrated x86-64-v1 qualification
remain separate gates. No production rollout, real import or retirement occurred.

## Decimal compatibility correction

Backend91ffdbf was published after the initial148-case proof. Rendered inspection
then identified that the new summaries used numeric ticket numbers, unlike the
incumbent exact decimal-string TicketOutput. The new interface is not accepted
on that source. number-red01 was an invalid fixture attempt to UPDATE a GENERATED
ALWAYS column. The corrected fixture drives the native identity sequence in its
dedicated test database and restores it afterward. number-red03 reproduced both
2^53+1 and BIGINT maximum as integer-versus-string assertion failures.

TicketNumber now owns the existing TicketOutput pattern and is reused by the
new summaries. Standalone formatting and the bounded SQL JSON aggregate both
preserve decimal strings. No incumbent response schema changes. green06 passed
all36 unified cases in121.21s, the legacy BIGINT/schema-roundtrip case in6.41s,
Ruff/check/format and mypy68. Its6,001-row plan returned100+1 rows, Sort root101,
execution42.524ms and planning10.536ms. generation02 repeated both exports with
stable bytes and passed web check; all pre-increment OpenAPI component schemas
and the complete legacy /my-work operation compare equal. Both new number
properties exactly match TicketOutput's property.

## Browser and isolated-stack progress

browser-red01 failed four cases at the missing default control/search before UI
implementation. browser-green01 passed4 cases in13.2s. browser-green02 passed26
cases in2.1m: five new cases plus the complete incumbent discovery/link modules.
This includes actual delayed old-response disposal after identity replacement,
visible badge cap3/more, independent done/new states and real detail navigation.
The existing task assertions remain and explicitly select Somente tarefas.

Actual390/1440 light/dark captures, axe and overflow passed in the same batch.
PhotoCraft was unavailable; the images were inspected directly. Rendered review
found the closed filter disclosure vertically above its neighboring select; a
local alignment rule and numeric render assertion corrected it. browser-green03
passed all five cases in17.0s, including that geometry check. These runs precede
the final browser decimal assertion; browser-green04 remains pending.

packaged01 and number-red02 stopped before exercising their product checks:
Docker reported all predefined address pools fully subnetted. All14 retired
networks selected for cleanup were verified as this task's internal networks with
zero endpoints. Only those networks were removed; containers, volumes and logs
were preserved. No host/Docker/SSH security configuration changed. The exact
cleanup record is network-cleanup01.json. Fresh packaged02 uses the corrected
decimal source and remains pending. No failed run is counted as acceptance.
