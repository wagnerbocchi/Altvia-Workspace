# Phase 3E-c private MIME parser2 policy evidence

Updated 2026-11-11. Source e0e6b0659e3a6e72eb0c76aa92704e7357825c3b passed all
five hosted gates and actual packaged acceptance. Full native email/Phase 3/MVP
and consolidated target-VM qualification remain open. Only synthetic data was used.

## Delivered behavior and historical preservation

ADR-0033/plan 31bbd6f preceded parser d1132a8, versioned persistence bc73771 and
final correction 6bf7317. The previous R3/R4 Subject-charset/end-token gaps are
corrected for parser2, without modifying or relabeling a parser1 interpretation.
The new finite owner command explicitly creates/replays (variant_id,2), returns
parser_version and preserves every raw receipt, collision and old result.

Subject/body codecs share the finite canonical UTF-8/ASCII/ISO-8859-1/Windows-1252
allowlist. Raw Subject is ASCII before any decoder; RFC2047 words validate
transfer syntax and strict bytes individually before public adjacent-word
assembly. Unsupported codecs, malformed transfer, split-invalid multibyte words
or raw international header bytes reject without partial subject/body. No private
stdlib parse-tree API or broad Subject headerregistry decoding is needed.

All actual HTML start/end/self-closing tokens count once toward4096; synthetic
stack closure does not count twice. Nesting64, active-subtree protection and all
raw/header/part/decoded/text bounds remain. No HTML rendering, URL fetch, identity
or client/contact lookup, ticket promotion, SMTP, API/frontend or runtime grant.

Migration b46087000020 expands the existing preview PK to variant_id/parser_version,
allows only1/2 and preserves default1, FK, result constraints, append-only trigger
and grants. New code writes2 explicitly. Downgrade locks preview/audit/outbox and
refuses v2 rows or v2 durable history; a v1-only roundtrip preserves full values.
Schema2 normalized events add exact parser_version="2"; old schema1 normalized
envelopes remain exact. Both are privately consumed without shared activity.
Source lock, atomic result/version/event and protected replay semantics remain.

Three architectural rulings and costs:

1. Composite versioned identity instead of overwriting v1 or duplicating tables.
   Stop/drain old owner commands before the key transition; retain version-aware
   CLI/consumer and expansion on app rollback. Old owner binaries against the new
   key are unsupported. No production migration/rollout occurred here.
2. Raw Subject ASCII and explicit finite encoded/body charsets. Some legitimate
   international raw headers reject until a separately reviewed RFC6532/provider
   boundary; raw bytes remain available for later authorized interpretation.
3. Retain exact signed vendor Node patch pinning after the old package disappeared.
   New runtime artifacts require complete image/capability proof and final actual
   target qualification; older successful CPU evidence does not transfer.

## Actual local checks and source review corrections

Initial R3/R4 regression run observed9 failed/5 passing. Corrected parser passed
52 pure tests in0.26s, including supported aliases/folding, unsupported known/
unknown codecs, strict UTF8 bytes, exact4096/4097 start/end/mixed/self-closing
boundaries. Missing v2 receipt failed before storage implementation. First actual
PostgreSQL persistence/version/event suite passed34 in43.35s. Expanded affected
suite passed185 in259.00s before final review corrections.

Fresh independent whole-increment static review found no Critical, three
Important Subject defects and one adjacent Minor header regression. It did not
execute tests or establish packaged/hosted/target acceptance. One correction pass:

- R1: malformed Base64 raised HeaderParseError outside ValueError handling. Pure
  and actual CLI tests observed RED through the installed email.header stack.
  Strict transfer prevalidation plus the normalization exception boundary now
  yields a durable fixed rejected parser2 result with safe replay/output.
- R2: mixed raw high bytes were converted by decode_header into ASCII backslash
  escapes. Before/after/folded regressions observed RED; original raw Subject
  ASCII validation now precedes any conversion.
- R3: permissive transfer decoding discarded invalid characters and adjacent
  individually invalid UTF8 words could merge into valid bytes. Malformed Base64,
  bad quoted-printable and split-byte words observed RED before independent word
  syntax/codec/byte validation, while valid folded controls remain supported.
- R4: name-based retrieval repeatedly checked only the first duplicate header.
  Its concrete second-Date overflow regression observed RED. The corrected header
  owner uses public policy.header_fetch_parse per actual non-Subject occurrence,
  resolving this adjacent regression while keeping Subject out of headerregistry.

All nine pure regressions observed RED; complete pure suite then passed61 in0.25s.
The final affected MIME/version/intake/IMAP/activity/runtime suite passed195 in
260.14s, including actual CLI rejected/replay, populated v1 upgrade, coexisting
immutability, concurrent v2 replay, event1/2 strictness, separate audit/outbox-only
downgrade guards, event rollback, current role denial and migration comparison.
No Critical/Important/Minor remains deferred in this follow-up. No second review
substitutes for executed regression/full-suite proof. Historical parser1 rows
remain historical, not evidence of corrected policy.

Ruff/format114 files, mypy40, final wheel/sdist and unchanged OpenAPI/TypeScript
export passed. Local SAST retained four existing LOW findings and zero blockers.
Full exact-source security, package execution and API/browser suites remain gates.

## Original hosted failure and reproduced build correction

Source6bf7317 passed API [43132748435](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43132748435)
with779 tests in499.43s, browser [43132748432](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43132748432)
with116 in3.1m and source security [43132748653](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43132748653).
Image [43132748362](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43132748362)
and container [43132748387](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43132748387)
failed at web-image construction, before new packaged runtime assertions. Image
reports covered only API/PostgreSQL/ingress, all zero-finding; this is explicitly
an incomplete failed security gate, never five-image acceptance. Complete failed
jobs/logs/partial reports are preserved. Original private build stderr was not
uploaded by those jobs, so it was not available from their run records.

A fresh local --no-cache build reproduced the exact signed Alpine package
selection failure: pinned nodejs24.22.1-r1 was no longer available; the repository
offered24.22.3-r0. Update e0e6b06 changes only that exact runtime pin in the same
base-image family/digest. The real corrected local web image built successfully,
with Node24.22.3/module137, pt-BR/standalone, absent Sharp and package installers
and UID10001 capability checks. Application/frontend source and other package
pins remain unchanged. All five hosted gates now follow the changed artifact;
neither the earlier failed run nor generic x86_64 labels prove final ISA readiness.

## Hosted and packaged acceptance

Final-source source and image security succeeded. Source reports retain the four
existing LOW findings, zero blockers and zero detected secrets. Eight image-report
builder tests passed0.02s; all five nonempty inventories have zero vulnerabilities
at every severity. Report hashes and retained log ZIP integrity were verified.
Scanned builds are independent of the container job's builds; identical IDs or
baseline-ISA qualification are never inferred between separate artifacts.

| Scanned image | Packages | Image ID |
| --- | ---: | --- |
| API | 66 | sha256:dc58d7283093ed478972396c51f00b2e99755ff187013a32d1d7c93c98782e23 |
| PostgreSQL | 49 | sha256:d5ed215e707c8a9736d2a29e1399e83e7df6b56b9776be9552bd6580b91312f8 |
| Ingress | 70 | sha256:344409ba108de1048b2cdc7c0150ebe1d263afdcb7c9f02e6fbfe28c4b67bc19 |
| Web | 43 | sha256:9bea230ce59855ba8ee565a48bbb5323f2a9529bbf9a6335b4791b05beee367a |
| Redis | 16 | sha256:847d30cc8813f98d8f3330507cdcf8507394ae301f312a8a06c96a08900d541e |

Trivy database SHA-256:
400e7b60cf78b5ceba57f9ed02cd98603dd89b57516f648f829a6f6a42843be4.

Complete exact-source jobs/logs/log ZIPs/artifacts were collected and inspected;
there is no failed step, Python traceback or workflow error in the final five runs.

| Gate | Actual result | Run |
| --- | --- | --- |
| API checks | 779 passed, 2 warnings in484.03s; static/migration/build checks passed | [43133816267](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43133816267) |
| Browser checks | 116 passed in3.8m | [43133816312](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43133816312) |
| Container checks | Actual MIME v1/v2 coexistence, explicit replay and recreated DB results/cursor; current role denial and full prior proof passed | [43133816261](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43133816261) |
| Source security | Four existing LOW findings; zero blockers/secrets | [43133816349](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43133816349) |
| Service image security | Eight report tests; five nonempty inventories, zero vulnerabilities all severities | [43133816228](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43133816228) |

The retained Pydantic advisories concern alias body in
test_queue_access_concurrent_reviewed_writes_one_wins and queue_id in
test_queue_atomic_failure_overflow_and_competing_versions. Setup-action Node
url.parse deprecation notices are retained separately from application tests;
none is silently suppressed or called a product vulnerability. Complete API SQL
negatives include four append-only failures, four v2 downgrade refusals, separate
audit/outbox-only history guards, injected event rollback, state/parser constraints
and private-role denial. The old work-parent concurrency test deliberately creates
a database deadlock and asserts only one mutation commits. Other expected FK/
constraint/migration negatives match existing tests; no fixture error is counted
as a production failure or as production acceptance.

The packaged proof actually invoked IMAPS/current normalization commands against
controlled loopback TLS, seeded a distinct synthetic historical result, proved
explicit version2/replay and recreated API/PostgreSQL before verifying both
interpretations and cursor. Both runtime roles retain no raw/poll/preview grants.
The separately executed populated-v1 migration test proves real schema upgrade;
the packaged synthetic seed is not misrepresented as running a legacy parser.

Sanitized immutable workstation archive:
phase-3e-c-policy-v2-e0e6b06/acceptance.zip under Codex state evidence. It retains
reviewed source, original/final hosted metadata/logs/artifacts, source review,
RED/GREEN/full local outputs and exact old-pin failure/new-pin build proof. All
124 entries passed ZIP and per-entry hash verification; archive3943678 bytes;
SHA-256 e462bdcb95a5857d0f7811342c555def8c7aef153a755ffd2e9b8a56098f0f26.
The receipt remains outside the archive to avoid self-reference. Scratch stays
preserved; no destructive cleanup, credential/TLS-key archival, live mailbox or
target-server operation occurred in this follow-up.

Provider/RFC6532 interoperability, actual contact/sender/thread verification,
authorized triage/promotion, public replies/SMTP and scanned private attachments
are not delivered by this policy follow-up. Q-03/Q-09/Q-11/Q-16/Q-21 remain open.
No production deployment, real import, live mailbox use or Zammad retirement is
implied. Final actual x86-64-v1 qualification follows remaining MVP development.
