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
the final browser decimal assertion. browser-green04 passed all five final cases
in16.2s with exact native decimal comparison, geometry, keyboard, four native
theme/width captures, axe, overflow and frozen input maps. All four fresh renders
were inspected directly. Independent whole-increment review remains required.

packaged01 and number-red02 stopped before exercising their product checks:
Docker reported all predefined address pools fully subnetted. All14 retired
networks selected for cleanup were verified as this task's internal networks with
zero endpoints. Only those networks were removed; containers, volumes and logs
were preserved. No host/Docker/SSH security configuration changed. The exact
cleanup record is network-cleanup01.json. Fresh packaged02 uses the corrected
decimal source. No failed run is counted as acceptance.

packaged02 completed the entire unmodified uv run python scripts/container_smoke.py
command in591.728s with exit0, empty stderr and37,617 unchanged mapped inputs.
The dedicated pair produced exactly one work row and one ticket badge before
and after actual API/PostgreSQL recreation. Existing unlink/no-op/replay/relink
and independent lifecycle checks remain intact. Native queue revocation produced
old-session401; the same actor's fresh login retained its in-progress task with
no ticket row, badge, more flag or hidden ticket ID. No extra write was added to
fit a count. The new record remains keys/states only, without titles or credentials.

Runtime/configuration/dependency/proof bytes in that551-file source map match
the completed source. Later changes are design/evidence documentation and the
independently proved contact clock test, not the packaged runtime. Raw stdout
SHA256 is94b50cba6a1c393df4f4964c6fa4fdf82b09e6bc77320fd7111a37719d5a74330;
the common archive SHA256 for packaged02/browser-green04 is
494e90910d8d1131c028d8c7ab8389d5666092d7c15e708bac06b0575ef603d5.
Final exact-source hosted/security gates and independent review remain pending.

## Contact regression fixture correction

The full hosted Browser run43547104201 at91ffdbf passed208 cases and failed only
the pre-existing contact focus regression: clock.pauseAt(now) became a past
instant after clock.install advanced virtual time. Complete run logs are retained
under ci-91ffdbf. This is a test setup failure, not a new contact product fix.

The test now pauses one minute ahead before opening the form; its30s test timeout
keeps that boundary in the future. The form's delayed autofocus remains held.
Native contact-clock-green01 passed all9 contact cases in36.1s, static/build and
unchanged frozen maps. Controlled contact-clock-red01 restored only the pre97b
focus owner in its private snapshot: the same corrected test failed on the
inactive name input, with8 other cases passing. That negative control proves the
fixture correction retains the actual keyboard/focus regression check. Canonical
contact production source was never reverted or changed. Final hosted gates on
the completed increment remain pending.

## Hosted runtime acceptance candidate85dd260

All five workflows passed for85dd2604fc6b53704a77dcfbac70fca54580ffcd:

| Gate | Actual result | Run |
| --- | --- | --- |
| API | 1602 passed,3 explicit native-console skips,0 failures/errors;1236.46s | [43549600451](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43549600451) |
| Browser | 214 passed in8.7m | [43549600381](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43549600381) |
| Containers | api-runtime and private-file-runtime both passed, including both packaged relationship proofs | [43549600541](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43549600541) |
| Source security | Passed | [43549600490](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43549600490) |
| Image security | Seven nonempty inventories;0 vulnerabilities | [43549600506](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43549600506) |

The3 API skips name freshclam, freshclam-daemon and clamd foreground checks,
which require an explicitly supplied prebuilt pinned native image. They are
retained, not counted as passes. The separate actual private-file runtime job
passed its native infrastructure/console and packaged checks. Complete logs,
job metadata, API JUnit and actual image reports are in ci-85dd260. Package counts:
API72, ClamAV38, ingress70, PostgreSQL49, Redis16, storage107 and web43; every
report has zero vulnerabilities, including lower severities. No ignore added.

The private native evidence archive collect01-proof.tar.gz has SHA256
3fe1fcbb72692e5ba3f7d67f6c4373b96cfb493eca28c5f5e1a2ed309d60b10f.
All471 manifest entries were verified after transfer;401 credential canaries
matched no collected file. Audit/manifest metadata add two archive entries.

## Manual visual harness compatibility

The opt-in workspace capture suite is intentionally excluded from ordinary CI.
Inspection found two old task-only state assertions that still opened the new
default unified view. capture-red01 first stopped earlier at a fixture KeyError:
the plain-text inbound sample unnecessarily required ALTVIA_STORAGE_FILE.
Its owner already supports zero-file text without storage, so the guarded test
fixture now passes an optional path. Binary staging still fails closed without
real storage. No production mail owner behavior or grant changed.

With that fixture correction, capture-red02 reached and reproduced the actual
missing old task-empty message. Both old empty/error captures now explicitly
select Somente tarefas and retain their original assertions. capture-green01
passed the complete opt-in test in58.3s, producing120 real captures in30 groups
and passing every320px overflow check. Ruff/scripts, web check/build/native guard
and39,651 frozen input checks passed. Selected default/empty/error renders were
inspected; the original unified native390/1440 light/dark captures remain.

These follow-up edits affect only the guarded test fixture and opt-in capture
test, with their own executed proof. Application runtime, dependencies and the
runtime proof source remain byte-identical to85dd260. Reuse its passing runtime
gates; do not claim they ran on a later test/documentation commit. Final fresh
whole-increment review is still required before accepting this feature.
