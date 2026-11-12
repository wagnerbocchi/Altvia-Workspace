# Phase 3E-c private MIME development evidence

Updated 2026-11-11. Source ae4d25a31e9d7d30a77cf0b4ff056635a67f6427 passed all
five hosted gates and actual packaged proof, with the two explicit minor contract
gaps below. Phase 3, native end-to-end email, MVP and final actual-target
qualification remain open. No real provider, mailbox or client data was used.

## Implemented boundary

ADR-0032/plan 17fe438 preceded parser 147cc18 and persistence 8afbd83. An owner
explicitly normalizes a quarantined variant through the finite opt-in command.
The result is immutable parser-v1 private subject/plain text or a fixed rejection
with no partial content. HTML is never persisted/rendered, URLs are never fetched,
attachments/forwarded messages stay opaque. No identity/contact/customer lookup,
ticket promotion, public API/browser surface, SMTP or IMAP checkpoint change.

Each source-serialized result/source version/audit/outbox commits atomically.
Raw parsing is outside write transactions; immutable variant/source identity is
rechecked on persistence. Concurrent retries converge on one result/event; later
collision state is preserved and never becomes verification. Existing results
replay even after source-version exhaustion. Strict new events include IDs and
status only; legacy shapes remain exact and shared activity remains empty.

Migration b46087000019 adds inbound_mail_previews with RESTRICT variant FK,
parser_version=1, explicit ready/rejected null-state and byte/count checks,
append-only update/delete trigger and downgrade refusal for rows or history.
Neither runtime role gains preview/raw access. App rollback retains expansion
and compatible private consumption. No dependency/image pin/ISA change.

Raw/headers/structure/decoded bytes and final text are independently bounded:
2 MiB raw; 16384-byte header blocks, 2048-byte physical lines and 100 fields;
64 entities/depth 8; 262144 decoded inline bytes; 65536 UTF-8 final body bytes.
Subject max 998 characters/3992 UTF-8 bytes. HTML nesting max 64 and start/self-
closing tokens max 4096. MIME body charsets support UTF-8/ASCII/ISO-8859-1/
Windows-1252, strict transfer decoding and no silent truncation. Subject/closing-
token policy gaps below are explicitly not claimed complete.

Three architectural rulings and costs:

1. Text-only private extraction without a rendering dependency. Formatting and
   link targets are lost; a future UI must escape all remaining untrusted text.
2. Strict finite MIME/body-charset subset with rejection instead of replacement.
   Some legitimate provider mail will reject; unchanged raw bytes permit later
   reviewed processing rather than guessing production compatibility.
3. Explicit variant selection and immutable parser-v1 interpretation. Scheduling
   and any changed interpretation need later integration/versioning contracts.

## Executed local checks and independent review

Missing-parser/service collection RED preceded implementation. First pure suite
had 29 passing and two fixture mistakes: reused nested boundary and undeclared
8bit transfer. Corrected fixtures passed 31 in 0.16s. Initial real PostgreSQL
service/CLI suite passed 13 in 22.15s. An unknown-disposition regression observed
RED before treating non-inline dispositions as opaque attachments. SQL tests
also reject null/unbounded states directly. The expanded affected suite passed
153 in 241.22s before final review corrections.

The fresh independent whole-increment static review found no Critical, two
Important and two Minor issues. It did not execute tests or establish packaged,
hosted or target acceptance. One correction pass addresses the Important issues:

- R1: lazy Date parsing could throw OverflowError on a giant numeric year, escaping
  normalization/CLI. Pure and actual PostgreSQL CLI tests observed RED, including
  the real email.utils/datetime stack. Header-boundary containment now persists
  fixed invalid_headers rejection; CLI also has fixed diagnostic defense.
- R2: an outer closing tag could pop a suppressed template/object/svg root and
  include hidden text. XML-style self-closing script/template could also release
  suppression. Five actual regressions observed RED; crossing closures and
  self-closing active roots now reject the complete result without partial text.

Targeted six regressions passed in 0.06s. After this correction pass, the complete
affected suite passed 160 in 245.57s, including actual PostgreSQL CLI rejection/
replay without an input-bearing diagnostic. No second review substitutes for
executed proof. Source correction/packaged proof ae4d25a was committed and pushed
after these checks. Its actual hosted/packaged gates subsequently all passed.
Ruff/format across 112 files, mypy across 40 files, final wheel/sdist and unchanged
OpenAPI/TypeScript export passed. Initial source SAST had four existing LOW and
zero blockers. Full exact-source security acceptance remains a hosted gate.

Deferred minors, both reproduced independently of the review's static claims:

- R3: encoded Subject words use the stdlib codec registry; a UTF-7 Subject is
  accepted even though UTF-7 body bytes reject. Result remains untrusted/private.
- R4: 5000 extra closing tags do not consume the separate 4096 start/self-closing
  counter. Raw/decoded-byte limits still bound processing; no unbounded-memory
  claim or XSS was established for this text-only result.

Both are visible contract gaps to close before user-facing previews or production
mail acceptance, not silently accepted satisfaction of the stricter ADR text.
Provider compatibility, retention/storage and later parser versioning remain
Q-03/Q-09/Q-11/Q-16/Q-21. No product owner decision or production sizing is invented.

## Hosted/packaged acceptance

Final-source source security and service-image security passed. Source summaries
retain four existing LOW Bandit findings, zero blockers and zero detected secrets.
Eight image-report builder tests passed in 0.03s. All five reports have nonempty
package inventories and zero vulnerabilities at every severity; report hashes
and retained log ZIP integrity were verified. Trivy database SHA-256:
400e7b60cf78b5ceba57f9ed02cd98603dd89b57516f648f829a6f6a42843be4.

| Scanned image | Packages | Image ID |
| --- | ---: | --- |
| API | 66 | sha256:b0e250a8dd40c44c3d640bb065dc3428e56c8e8719cb67654e5b09ff4222d369 |
| PostgreSQL | 49 | sha256:92f7b122421b2410b5b6bd4968c043bfbc3d40d97f0517d2ad60acd14a381de8 |
| Ingress | 70 | sha256:ff955fee804f95ecf21211f44185c6812f81d961de7328adb5bd36d528d831f6 |
| Web | 43 | sha256:c6e93e03cc3893f7661b24061f26b656f9cff98b3a996a57555717063429c25d |
| Redis | 16 | sha256:ad81d57143d0b9c2bedd12400c7a8c2bb44e78de2a739de941b67e4933f0fb73 |

Scanned builds are separate from the container job's builds. No equality of
independently built IDs or actual baseline-CPU qualification is inferred.

All five complete exact-source runs were collected, including jobs, logs, log ZIPs
and artifacts. No failed step, Python traceback or workflow error remains.

| Gate | Actual result | Run |
| --- | --- | --- |
| API checks | 744 passed, 1 warning, 404.24s; lint/types/migration/build passed | [43126047128](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43126047128) |
| Browser checks | 116 passed in 3.7m | [43126047367](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43126047367) |
| Container checks | Actual IMAPS/normalization command, ready/replay, recreated database text/cursor and runtime denial passed; prior full packaged proof passed | [43126047135](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43126047135) |
| Source security | Four existing LOW findings, zero blockers/secrets | [43126047339](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43126047339) |
| Service image security | Eight report tests; five nonempty inventories, zero vulnerabilities at every severity | [43126047167](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43126047167) |

The retained Pydantic UnsupportedFieldAttributeWarning concerns alias body in
test_queue_atomic_failure_overflow_and_competing_versions. It is not suppressed
or represented as a failing test. Complete API logs contain deliberate negative
SQL tests: nine preview state/size/null failures, one parser-version failure,
append-only denial, four runtime preview denials, guarded downgrade and injected
normalized-event rollback. Existing work-parent concurrency deliberately induces
a database deadlock; the test verifies exactly one mutation commits. The remaining
constraints/FKs/private-role negatives match their existing tests. No negative
fixture error is counted as production failure or production acceptance.

The actual packaged proof ran IMAPS and normalization commands against synthetic
loopback TLS, verified byte capture and ready/replay, recreated API/PostgreSQL,
then checked durable text/cursor and both runtime roles' denial of all raw/poll/
preview privileges. Public output contained IDs/status only. This establishes the
controlled development boundary; provider/verification/production and final guest
ISA qualification are separate evidence gates.

Sanitized immutable workstation archive: phase-3e-c-mime-ae4d25a/acceptance.zip
under Codex state evidence. It retains reviewed source, independent review,
RED/GREEN/local full outputs and complete hosted metadata/logs/artifacts. All
86 entries passed ZIP and per-entry hash verification; 3227675 bytes; SHA-256
fd535ab3c96abbebf3a32d79176d028cf380b471f1e49374a55417b38581a617.
The external receipt avoids archive self-reference. Task scratch is retained;
no destructive cleanup, credential/certificate archival or evidence publication
outside the authorized repository is part of this closure.

MIME is still private normalization, not safe customer display, sender/thread
verification, authorized triage/promotion, SMTP/public conversation or scanned
private files. Full native email/Phase 3/MVP and final baseline-VM qualification
remain open under the user's development-first cadence. No production deployment,
real import, live mailbox use or Zammad retirement is implied.
