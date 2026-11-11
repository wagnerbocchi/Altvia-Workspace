# Read-only IMAPS quarantine poll implementation plan

> Execute inline with superpowers:executing-plans. Standing authorization covers
> direct main commits/pushes; no live mailbox, real import or per-slice target SSH.

**Goal:** Receive controlled IMAPS mail into durable quarantine and safely resume.
**Architecture:** Standard-library bounded TLS wire adapter, owner-only finite poll,
fenced PostgreSQL cursor/lease and existing atomic capture/private event owner.
**Tech stack:** Python imaplib/ssl, existing Pydantic/SQLAlchemy/PostgreSQL/Alembic.
**Spec:** docs/adr/0031-readonly-imap-quarantine-poll.md and master specification.

## Constraints and review focus

- No server writes, inferred identity, MIME rendering, ticket promotion or SMTP.
- No new dependency/ISA, raw-table runtime grant, API or frontend surface.
- INBOX only, TLS validation, 2 MiB literal, 16384-byte lines, window1000/batch25.
- Lease120s, wire budget90s/socket10s, namespace bound only after verified login/select.
- Checkpoint/reset/capture requires current lease token; no network I/O in a DB transaction.
- A malicious literal size must be rejected before reading/allocating its body.
- A partial poll cannot skip its failed UID or roll back earlier committed messages.
- Late/expired poll tokens cannot rewind another epoch/cursor or clear another lease.
- Empty UID gaps advance only within a successful SEARCH and observed UIDNEXT bound.
- Namespace/UID reset and password rotation must preserve original private receipts.

### Task 1 Checkpoint/lease persistence and private events

**Files:** models.py, mail_intake.py, imap_poll.py,
migrations/versions/b46087000018_imap_poll_states.py, tests/test_imap_poll.py.
**Interfaces:** acquire/release fenced lease; initialize selected epoch; atomic
capture_checkpoint and scan_checkpoint; record_intake_event extends current owner.

- [ ] Write/run failing real PostgreSQL tests for leases/fencing, namespace/reset,
  atomic capture/checkpoint/event failure, cursor bounds and legacy event compatibility.
- [ ] Implement constrained private state, guarded migration and existing private
  audit/outbox integration with strict new payloads and unchanged old envelopes.
- [ ] Run focused persistence/runtime/migration and static checks; commit checked source.

### Task 2 Bounded read-only TLS collector and restricted CLI

**Files:** imap_poll.py, tests/imap_fixture.py, tests/test_imap_poll.py,
scripts/imap_test_certificate.mjs, runbooks/imap-poll.md.
**Interfaces:** IMAPPollSettings, poll_once(engine,settings,key)->PollReceipt;
python -m altvia.imap_poll --source-key KEY with explicit opt-in/external secrets.

- [ ] Write/run actual controlled TLS protocol RED for capture/resume and dangerous
  responses: oversized/truncated literal, wrong UID/epoch, bad certificates/auth,
  malformed SEARCH/lines, partial/batch/gap behavior and source locks during I/O.
- [ ] Implement certificate-verified IMAPS/EXAMINE/PEEK with bounded wire parsing,
  monotonic read/write budget and network outside transactions. Keep data opaque.
- [ ] Prove command guard/redaction and real persisted operator flow. Run local
  affected suites, Ruff/format/mypy, generated-contract comparison and package build.

### Task 3 Independent review, packaged proof and publication

**Files:** container_smoke.py, roadmap/PRD/security/contracts/evidence and private ledger.
**Interfaces:** exact reviewed source, synthetic TLS packaged receipt/checkpoint
persistence after recreation, runtime denial and complete hosted scan inventories.

- [ ] Add actual synthetic owner-side TLS poll proof and restarted PostgreSQL cursor
  check. Complete one fresh whole-increment source review and fix Important findings.
- [ ] Publish coherent checked commits; inspect all five exact-source hosted gates,
  complete logs/artifacts, severity metadata and nonempty image inventories.
- [ ] Preserve hashed evidence, publish bounded Markdown closure, verify actual
  remote main/clean tree and unchanged tested product source. Keep Phase3/MVP open.
