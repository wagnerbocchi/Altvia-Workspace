# Mail quarantine intake implementation plan

> Execute inline with superpowers:executing-plans under standing direct-main
> authorization. Reuse completed unchanged-source gates; no per-slice target SSH.

**Goal:** Preserve native mail input durably without granting unverified identity.
**Architecture:** Owner-only operator boundary, PostgreSQL receipt/variant ledger,
strict redacted outbox consumption; no HTTP/frontend or live provider effects.
**Tech stack:** Existing Python standard library, SQLAlchemy, Alembic/PostgreSQL.
**Spec:** docs/adr/0030-mail-quarantine-intake.md; fully read master specification.

## Global constraints

- Contracts before implementation. No actual mail import or provider connection.
- Opaque raw bytes only, no MIME rendering, customer mapping or outbound effect.
- UIDVALIDITY/UID uint32; raw1..2097152 bytes; 16 variants; source key ASCII1..64.
- Atomic receipts/audit/outbox, serialized source, immutable variants, owner-only.
- No new dependency/ISA requirement, no inferred compatibility or full MVP claim.

## Review focus

- A replay after a collision must still report collision, never normal quarantine.
- Identical raw content under a new UID/UIDVALIDITY/source must not be dropped.
- Raw input and credentials must not appear in CLI errors or shared activity.
- Malformed bytes must remain bounded opaque data, never parsed or rendered.
- Event failure/overflow/concurrent capture cannot produce an acknowledged partial write.

### Task 1 Durable quarantine and private event consumption

**Files:** models.py, mail_intake.py, activity.py,
migrations/versions/b46087000017_mail_quarantine.py, tests/test_mail_intake.py.
**Interfaces:** register_source(db,key,queue_id)->MailboxSource;
capture_message(db,key,uid_validity,uid,raw)->CaptureReceipt with source_id,
envelope_id,variant_id,state,replayed; validate_intake_event(event)->bool.

- [x] Write/run failing real PostgreSQL tests for all review-focus inputs,
  source/UID scope, collision/replay, raw limits, atomicity and concurrency.
- [x] Implement the three constrained tables, append-only variants and owner-side
  functions, strict redacted events and intentional private consumer acknowledgement.
- [x] Prove SQL hash/length/FKs/immutability, runtime denial and guarded migration;
  run focused API, Ruff/format/mypy, migration consistency and full API. Commit.

### Task 2 Restricted binary-stdin operator command

**Files:** mail_intake.py, tests/test_mail_intake_cli.py, runbooks/mail-intake.md.
**Interfaces:** register-source/capture commands from ADR-0030; opt-in env guard,
DatabaseSettings, generic safe error, minimal JSON metadata receipt.

- [x] Write/run failing CLI guard/input/error tests and actual isolated capture.
- [x] Implement bounded binary stdin, sanitized argument failures, owner transaction
  and minimal output with no raw bytes/hash/header/addresses or credentials.
- [x] Run relevant checks and actual persisted command proof; document rollback
  and limitations; commit the checked batch.

### Task 3 Packaged proof, independent review and publication

**Files:** container_smoke.py, roadmap/PRD/contracts/evidence and private ledger.
**Interfaces:** exact reviewed source, synthetic packaged intake/restart/denial,
five hosted gates and nonempty image inventories.

- [x] Add real owner-side packaged synthetic capture/replay/restart proof with
  runtime denial; complete one fresh whole-increment source review and fix Important.
- [x] Publish checked commits, inspect complete hosted results/artifacts and scan
  severities. Freeze sanitized evidence before any permitted scratch cleanup.
- [x] Record bounded completion and remaining native email work; publish Markdown
  closure and verify clean actual remote main with unchanged tested product source.
