# Verified public mail delivery implementation plan

> Execute with superpowers:subagent-driven-development or executing-plans,
> task by task. The user already authorized continuing until MVP completion,
> direct main publication and recording questions without stopping development.

**Goal:** Explicitly send an immutable public response through a verified
requester/sender boundary and visibly reconcile its durable delivery state.

**Architecture:** ADR-0035 extends the existing modular monolith with a delivery
aggregate, owner attestation and a bounded standard-library SMTP adapter. Reuse
ticket authority/locks, protected receipts, SQL leases, Redis worker and the
existing ticket Operate surface. Private notes never enter this path.

**Tech Stack:** Existing Python3.12/FastAPI/SQLAlchemy/PostgreSQL/Redis/Next.js,
Python email/smtplib/ssl. No new native library or service.

**Spec:** docs/adr/0035-verified-public-mail-delivery.md and master specification.

## Global constraints and review focus

- No production/provider change, real attestation, real sending or target SSH.
- Keep x86-64-v1; never use prohibited search/AI dependencies or native tuning.
- Current queue role plus customer ceiling; manager/current assignee write only.
- Identity lock before auth, then existing client/team/queue/ticket lock order.
- All provider input is hostile; no response text, addresses or bytes in logs.
- Old draft/note fingerprints and strict event shapes must remain unchanged.
- Real policy stays Q03/Q16; immutable operator attestation is labeled honestly.
- Review lost ownership/contact changes between queueing and DATA, not only POST.
- Review process loss at every SQL/network boundary; never auto-resend uncertainty.
- Review stale attempts after expiry and worker drain before manual reconciliation.
- Review MIME/header injection, malicious multiline replies and total wire bounds.
- Review public-draft/queue/read authorization independently from private notes.

### Task1: Persist verified sender, requester and protected public delivery

**Files:** Create migration00022, altvia/mail_delivery.py,
altvia/mail_delivery_api.py, altvia/mail_delivery_schemas.py,
altvia/mail_participants.py, altvia/mail_settings.py and tests/test_mail_delivery.py.
Modify models.py,
provision.py, main.py, tickets.py/ticket_schemas.py and activity.py. Regenerate
OpenAPI/TypeScript through the existing exporters.

**Interfaces:** Produce ticket-bound eligible choices, protected create-delivery
and scoped single-delivery GET defined by ADR-0035. Sender registration and
requester attestation/revoke are owner-only finite commands. A private
ticket_mail_threads row owns one unique random token per ticket; the outbound
row freezes its public message/envelope/MIME/Message-ID and authorizing actor.
Produce claim/pre-DATA/finalize/recover/reconcile functions returning IDs and
fixed states/errors only. Task2 consumes those functions, never private notes.
Task1 also owns pure wire construction and `SMTPAccount` configuration in
mail_settings.py: source_id UUID, host/port, tls_mode implicit|starttls,
username/password SecretStr, from_email ASCII mailbox and optional ca_file Path.
Its namespace_hash excludes password/CA path but includes source/host/port/TLS/
username/From. A strict owner-selected JSON file holds accounts, max16/max64 KiB;
the loader returns a source-ID mapping and never prints input. Task2 consumes
that settings class, frozen envelope/wire and the persisted claim protocol.
Keep settings and wire construction runnable in Task1 without a network stub.
Delivery choices are `{sender: SenderChoice|null, participant: ParticipantChoice|null,
can_send: boolean}`: one sender per queue and one active attested requester per
ticket, enforced by SQL uniqueness. Worker pre-DATA checks reuse ticket visibility
and current writer authority, active author account, parents/contact/participant;
only required eligibility columns may be granted, never password/session hashes.

- [ ] Write/run actual PostgreSQL/API RED for missing delivery routes and models.
  Include hidden/mismatched message parents, note ID rejection, no contact proof,
  changed/archived requester, revoked participant, source/queue mismatch, actor
  denial, protocol/replay/stale/unique/race and atomic event failure.
- [ ] Implement additive FKs/checks/indexes, frozen snapshots and guarded rollback.
  Keep API attestation/sender writes denied. Existing worker may update only
  delivery attempt columns; public eligibility checks get explicit column reads,
  never user credential fields, raw/preview tables or note content. Reuse existing
  ticket visibility/assignment query ownership in the pre-DATA check.
- [ ] Add lease/state tests for expired preparing versus transmitting, exact token
  fences, revoked eligibility, safe failures/retry8/backoff cap, no transaction
  around network I/O, accepted timestamp and drained owner reconciliation.
- [ ] Run `uv run pytest apps/api/tests/test_mail_delivery.py` against a guarded
  actual PostgreSQL DB. Expected: all protocol/state/security assertions pass.
  Run affected ticket/activity/provision tests, Ruff/mypy, exporter comparison and
  actual package build. Commit the coherent persisted delivery owner.

### Task2: Bounded TLS SMTP transport and actual worker integration

**Files:** Create altvia/smtp_transport.py and tests/test_smtp_transport.py;
modify worker.py, config.py, provision.py and runtime tests only as required.

**Interfaces:** Consume a claimed frozen delivery/attempt token and trusted
source configuration. Return only an accepted/safe-retry/permanent/uncertain
outcome and fixed error code. `deliver_once(engine, delivery_id, settings)`
coordinates persisted stage transitions outside network transactions. The worker
mail actor receives a delivery UUID; SQL is authoritative and Redis is only a
duplicate-tolerant wake-up. Absent/mismatched configuration performs no send.

- [ ] Write/run RED with a real controlled local TLS SMTP server: exact envelope
  and stable plain-text MIME, implicit TLS, required STARTTLS/re-EHLO, certificate
  rejection, no AUTH/DATA before TLS, bad auth, pre-DATA disconnect, 4xx/5xx,
  lost final250, malformed/oversized replies, bounded deadline and changed namespace.
- [ ] Implement standard-library adapter, finite configuration bounds and private
  safe diagnostics. Freeze bytes once; never build mail from private note inputs.
  Persist transmitting before DATA, accepted only after250 and uncertain on
  ambiguous DATA/crash. Definite rejection alone permits bounded safe retry.
- [ ] Integrate claim/recovery/public wake-up with the existing worker. Prove
  duplicate Redis messages, two workers, restart and broker loss cannot create
  another logical delivery or automatically resend an uncertain attempt.
- [ ] Run `uv run pytest apps/api/tests/test_smtp_transport.py` and full affected
  delivery/worker/runtime tests. Expected: all real wire/state assertions pass,
  safe shutdown and no raw/preview/note privileges. Commit transport integration.

### Task3: Real browser send review and delivery state

**Files:** Extend ticket messages/detail/feedback and lib/tickets.ts; create
apps/web/tests/ticket-delivery.spec.ts; update the task-owned surface brief.

**Interfaces:** Consume generated choices/receipt/status types from Task1. A
delivery intent freezes message_id/participant_id/source_id/key/ticket version.
Display persisted state from the API; no local optimistic accepted/delivered state.

- [ ] Load Impeccable context/craft floor and preserve the incumbent ticket layout.
  Add exact saved-body/recipient/sender review and explicit queue-send action;
  never prefill from notes. Show accepted/failed/uncertain wording and real errors.
- [ ] Write/run real browser persistence, readonly/unverified denial, private-note
  separation, HTTP lost-result original replay, ownership changes and acknowledged
  read recovery. Check keyboard/axe/overflow, desktop/mobile and both themes.
- [ ] Run web check/build/generated comparison and full browser suite; obtain
  required rendered review/documentation. Commit the checked UI slice.

### Task4: Integrated acceptance and immediate next stage

- [ ] Obtain one fresh whole-increment source review. Fix Important findings
  with RED/GREEN and affected full suites; explicitly record remaining rulings.
- [ ] Add actual packaged synthetic TLS delivery/restart/uncertain/no-note proof,
  narrow runtime privilege proof and runbook including safe operator drain.
- [ ] Publish authorized checked commits and inspect all five exact-source hosted
  gates, complete logs and image/source security inventories. Preserve sanitized
  hashed evidence; keep final target qualification separate.
- [ ] Update completion ledger and immediately start the restricted authorized
  inbound triage/thread-correlation stage. Do not ask whether to continue.
