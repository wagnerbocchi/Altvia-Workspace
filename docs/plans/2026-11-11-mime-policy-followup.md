# MIME policy follow-up implementation plan

> Execute inline with superpowers:executing-plans. User authorization covers
> direct main commits/pushes; questions stay registered; no per-slice target SSH.

**Goal:** Close R3/R4 without rewriting previous private MIME interpretations.
**Architecture:** Shared finite charset owner, complete HTML token accounting,
versioned immutable preview key and compatible private event schemas.
**Tech stack:** Existing Python stdlib/email/HTMLParser and PostgreSQL/Alembic.
**Spec:** docs/adr/0033-versioned-private-mime-corrections.md, ADR-0032/master.

## Constraints and review focus

- No HTML rendering, identity proof, ticket/SMTP effect, API/frontend/runtime grant.
- Preserve every parser-v1 row/event; reprocess only into a separate parser-v2 row.
- Reject unsupported Subject codecs before any broad header-registry decoding.
- Count only real wire HTML tokens, including unmatched closers, once each.
- Existing source lock/atomic/replay/private event protocol remains authoritative.
- Old owner commands must drain for schema transition; retain compatible tooling
  on rollback. Never contract away v2 data/history. No new dependency/ISA.

### Task 1 Correct bounded parsing

Files: apps/api/altvia/mail_mime.py, apps/api/tests/test_mail_mime.py.
Interface: PARSER_VERSION=2; normalize(raw) remains a fixed ready/rejected result.

- [x] Write/run R3/R4 failing tests, supported aliases/folded words, invalid bytes
  and exact mixed/start/end/self-closing token boundaries. Expected concrete RED.
- [x] Share strict canonical charset validation with body decoding, interpret raw
  Subject before headerregistry and count real HTML tokens without synthetic doubles.
- [x] Run focused pytest/static checks. Expected all pass. Commit coherent fix.

### Task 2 Persist separate versioned interpretation and packaged proof

Files: models.py, mail_normalize.py, mail_intake.py, migration00020,
tests/test_mail_normalize.py, packaged_imap_proof.py, container_smoke.py.
Interface: normalize_variant creates/replays (variant_id,2); CLI receipt includes
parser_version; event normalized/schema2 has exact parser_version="2" metadata.

- [x] Observe missing v2 persistence RED. Add populated-v1 upgrade/rollback,
  same-variant coexisting results, concurrent replay, event1/2 strictness and
  poison rejection, event failure rollback, immutability/runtime denial proofs.
- [x] Implement guarded key expansion and explicit v2 write/event/receipt. Update
  current readers/tests to select version explicitly; keep all raw data intact.
- [x] Run affected MIME/intake/IMAP/activity/runtime suites, actual command,
  lint/types/contracts/build/security. Expected all pass. Add actual packaged
  v1/v2 coexistence/replay/restart proof; no target connection.

### Task 3 Review, acceptance and publication

Files: runbooks, ADR/roadmap/PRD/evidence and private execution ledger.
Interface: exact reviewed source and complete real local/hosted/package evidence.

- [x] Dispatch one fresh whole-increment source review; fix Important findings
  once using observed RED/GREEN plus complete affected suite.
- [x] Publish checked source, inspect all five hosted gates/full logs/artifacts,
  warnings, severity metadata and nonempty image inventories.
- [x] Preserve sanitized hashed evidence, publish bounded closure, verify remote
  main/clean tree/unchanged tested code. Keep full email/MVP/target gates open.

Acceptance: docs/phase-3e-c-policy-v2-evidence.md records exact final e0e6b06,
195 local/779 hosted API/116 browser, actual v1/v2/replay/restart/runtime-denial,
five-image zero-finding proof and immutable archive. The initial two build failures
and actual removed-pin RED/corrected Node24.22.3-r0 GREEN remain preserved.
No review finding is deferred. Full native email/MVP and final target stay open.
