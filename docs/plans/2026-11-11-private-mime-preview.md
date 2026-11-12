# Private MIME preview implementation plan

> Execute inline with superpowers:executing-plans. User authorization covers
> direct main commits/pushes, without new approval or target SSH per increment.

**Goal:** Turn controlled quarantined mail into durable private text or rejection.
**Architecture:** Bounded MIME entity traversal and stdlib HTML-to-text, immutable
owner-only result, existing source serialization and strict private event owner.
**Tech stack:** Python email/codecs/HTMLParser, SQLAlchemy/PostgreSQL/Alembic.
**Spec:** docs/adr/0032-private-bounded-mime-preview.md and master specification.

## Constraints and review focus

- No sender/thread proof, ticket mutation, API/browser grant, SMTP or URL fetch.
- Raw/capture/cursor identity and legacy event payloads remain unchanged.
- Enforce structure/resource limits before recursively parsing hostile entities.
- Multipart alternatives must not treat text attachments as customer body text.
- No partial text after a rejection; no payload or header in CLI/event diagnostics.
- No decoder replacement or silent truncation; fixed charset support is explicit.
- Append-only parser results and source lock ordering preserve replay/concurrency.
- Preserve raw data and guarded expansion on rollback; no new dependency/ISA.

### Task 1 Bounded normalization

Files: apps/api/altvia/mail_mime.py, apps/api/tests/test_mail_mime.py.
Interface: normalize(raw: bytes) -> NormalizedMail with status/subject/body_text/
part_count/attachment_count/reason; no persistence or external I/O.

- [x] Add failing plain/encoded/HTML/mixed/alternative/related/attachment tests and
  hostile malformed/size/depth/parts/header/encoding/control cases. Run pytest:
  expected missing module first, then concrete failed behavior before fixes.
- [x] Implement bounded per-entity header traversal, strict transfer/charset codecs,
  text selection and non-rendering HTML extraction at ADR-0032 limits.
- [x] Run focused pytest, Ruff/format/mypy. Expected all pass. Commit checked slice.

### Task 2 Durable private results and owner command

Files: models.py, mail_normalize.py, mail_intake.py,
migrations/versions/b46087000019_mail_previews.py, tests/test_mail_normalize.py.
Interface: normalize_variant(engine, variant_id) -> NormalizeReceipt; restricted
python -m altvia.mail_normalize --variant-id UUID with explicit opt-in.

- [x] Observe real PostgreSQL RED for missing result table/service; add replay,
  collision/concurrency/version/rollback, private event, runtime and migration tests.
- [x] Implement append-only checks/trigger, source-serialized atomic write/event
  and idempotent CLI with fixed diagnostics. Preserve old event envelopes.
- [x] Run complete affected MIME/intake/IMAP/activity/runtime suites and actual
  command proof; static/contracts/package/security checks. Expected all pass.

### Task 3 Independent review, packaged acceptance and publication

Files: scripts/packaged_imap_proof.py, runbooks, evidence, roadmap/PRD, ledger.
Interface: actual owner command on synthetic data, restarted DB result/runtime
denial, exact reviewed source and complete hosted artifacts.

- [x] Add packaged normalization/replay/restart proof; dispatch one fresh source
  review. Address Important findings once with observed RED/GREEN and full suite.
- [x] Publish checked source to main; inspect all five hosted gates, complete logs,
  warnings/security findings and nonempty exact-image inventories.
- [x] Preserve sanitized hashed evidence and publish Markdown closure. Verify
  remote main, clean tree and unchanged tested code. Keep Phase 3/MVP/VM open.

Evidence: docs/phase-3e-c-mime-evidence.md records exact source ae4d25a, local160,
hosted744 API/116 browser, actual packaged proof and immutable archive. R1/R2 are
fixed with RED/GREEN proof. R3/R4 remain explicitly deferred minor contract gaps,
to close before user-facing preview/production mail acceptance. This is a private
development increment, not full native email/MVP or final target acceptance.
