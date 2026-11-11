# Phase 3E-a native mail quarantine development evidence

Updated 2026-11-11. Candidate source 72116da02151851d67727d952fd167e09506d9c6.
Bounded development acceptance is complete with all five exact-source gates.
Phase 3, native end-to-end email, the full
MVP and consolidated actual-target qualification remain open.

## Delivered boundary

Contracts 489b3fc preceded implementation 118d99f under ADR-0030. The native
intake ledger preserves bounded opaque RFC822 bytes under an explicit mailbox
source and UIDVALIDITY/UID identity. Its owner-only operator commands register a
source and capture binary stdin. Every accepted input remains quarantined. No
sender, customer, contact, ticket or participant identity is inferred from it.

Equal identity/bytes replay stable receipt IDs without a second version or event.
Different bytes retain immutable variants and permanently mark collision, also
when replaying the original. Equal bytes under another source/UID/UIDVALIDITY
remain separate receipts. Source-row serialization prevents concurrent retries
from duplicating variants. Source identity and queue binding cannot be remapped.

Migration b46087000017 creates mailbox_sources, inbound_mail_envelopes and
inbound_mail_variants with RESTRICT references, unique identities, uint32 UID
checks, raw size/hash checks and mutation guards. Raw SHA256 is checked by native
PostgreSQL against the stored bytes. Opaque bytes1..2097152 and 16 distinct
variants bound each capture/identity. Overflow refuses acknowledgement; no
checkpoint is advanced. Receipts, source version, audit and outbox commit together.
Variant/history preservation is enforced on rollback/downgrade.

API/worker raw-table privileges remain empty. The existing consumer validates
strict identifier/state events and acknowledges/deduplicates them without shared
activity. The CLI requires explicit opt-in and existing owner credentials, reads
bounded binary stdin and prints minimal receipts only after commit. Argument,
configuration and database errors never echo inputs or connection details.
There is no HTTP route, raw browser surface or implicit platform content grant.

## Decisions and costs

1. Start native email with durable opaque quarantine while provider/sender policy
   remains unknown. Later verified promotion must integrate these receipts.
2. Use existing PostgreSQL BYTEA for bounded raw input and one atomic write.
   Larger volumes require a compatible private-storage migration and manifest.
3. Use owner-only binary stdin instead of assigning unclassified customer mail to
   application roles. Delegated triage requires a subsequent explicit policy/UI.
4. Use provisional 2 MiB/16-variant bounds. Production provider sizing must be
   approved under Q-21; rejected input never receives a successful receipt.

The independent reviewer judged live IMAP/checkpoints, provider authentication,
sender verification, header/Message-ID parsing, ticket promotion/correlation,
MIME display, attachment extraction/scanning, SMTP/public replies, real imports,
production throughput/storage/retention and target compatibility outside this
bounded increment. These remain required later capabilities or policy gates,
not delivered behavior. This preserves the explicit ADR-0030 scope; its cost is
that full native email/production/target acceptance remains pending. No in-scope
runtime or security expectation was discarded for lack of specification wording.

## Executed local checks and independent review

- The first local setup attempt failed before product tests because the active
  Podman machine had no images. Rebuilt the current pinned PostgreSQL image
  locally, retaining patched Go 1.27.4/GOAMD64=v1 and its actual build/probe log.
  Image ID 10f50bf333f3a90fca724c3ac931324f1237058b20eb87f9932aac8a16ae0019.
  A task-owned runner selects that image. No target VM/security change occurred.
- Missing-module collection RED preceded implementation. An actual PostgreSQL
  private-consumer RED preceded its acknowledgement branch. Six missing-command
  CLI tests failed before main and passed after implementation. An initial event
  constructor omitted its pre-flush schema version; its error was corrected with
  explicit version 1 before the behavioral consumer test.
- Expanded real PostgreSQL/CLI/activity/runtime suite: 62 passed in 83.48 seconds.
  Tests cover opaque malformed bytes, replay/collision, UID reset/source isolation,
  exact size/uint32 limits, immutable SQL/hash constraints, variant/version overflow,
  event rollback, concurrent retry, runtime denial, poisoned metadata, empty
  migration round trip/consistency and durable-history contraction refusal.
- Command exercised through the task runner:
  python .superpowers/sdd/2026-11-11-mail-quarantine-intake/run-local.py --api -q
  apps/api/tests/test_mail_intake.py apps/api/tests/test_mail_intake_cli.py
  apps/api/tests/test_activity.py apps/api/tests/test_runtime_provision.py.
- Ruff check/format passed across 107 files; mypy passed 37 source files;
  uv build produced wheel/sdist. OpenAPI/TypeScript export produced no contract
  change. Local SAST reported four existing LOW findings and zero blockers.
- One fresh independent whole-increment review inspected tracked and untracked
  source against the ADR, plan and ledger. No Critical, Important or Minor
  findings; all five review-focus paths satisfied. Review did not claim runtime,
  packaged or target acceptance. No frontend/design/system/token/asset/dependency
  changed, so no new frontend design pass was needed.

The full unchanged browser and full API suites are validated by exact-source
hosted gates instead of duplicate local runs. This follows the repository's
instruction to run relevant local checks and reuse passing unchanged evidence.

## Hosted acceptance and security

All five final workflows passed on exact source 72116da. Their complete logs and
artifacts were collected and inspected. The packaged smoke invokes the real operator
command with fixed synthetic bytes, tests collision, recreates API/PostgreSQL,
replays the original and checks both runtime roles' raw-table privilege denial.
These assertions passed in actual execution, not solely source inspection.

| Workflow | Exact-source run | Result |
| --- | --- | --- |
| API checks | [43111768394](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43111768394) | 646 passed in 367.42 seconds; static/migration/build gates passed |
| Browser checks | [43111768409](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43111768409) | 116 passed in 4.0 minutes; generated/web checks passed |
| Container checks | [43111768230](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43111768230) | Rebuilt owner-only quarantine/restart/replay/role denial and complete packaged HTTPS/browser/native/shutdown passed |
| Source security | [43111768313](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43111768313) | Zero blockers/secrets; four existing LOW findings |
| Service image security | [43111768397](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/43111768397) | Five nonempty inventories; zero vulnerabilities at all severities |

Final API emitted no warning summary. Complete logs contain no unexpected
traceback, workflow error or failed step. Constraint/privilege/immutability/
guarded-downgrade errors, the injected mail-event failure and intentional work-
graph deadlock belong to successful negative tests. Existing framework/color and
upstream action/Node deprecation advisories remain visible in the retained logs.
API/PostgreSQL/ingress/web/Redis inventories contain 66/49/70/43/16 package records.
All five report hashes match their manifest. Scanner database SHA256:
400e7b60cf78b5ceba57f9ed02cd98603dd89b57516f648f829a6f6a42843be4.

The first candidate 118d99f passed 646 API tests in 341.31 seconds with no warning
summary, 116 browser tests in 3.7 minutes and both source/image security gates.
Its packaged test passed actual CLI capture,
collision, original-byte replay after recreation and API raw-privilege checks,
then failed at the worker probe. That new probe used API Settings, incorrectly
requiring public_origin absent from the worker contract. A local isolated
configuration RED reproduced the missing field; DatabaseSettings GREEN provided
the existing database-only settings. Test-only 72116da corrects the probe without
changing application behavior, runtime privileges, environment or schema. The
failed complete run is preserved alongside the corrected execution evidence.
Corrected run 43111768230 passed actual packaged intake/collision/restart/replay,
both runtime-role privilege checks and the complete HTTPS/browser/native/shutdown
proof. The subsequent full API result above closes bounded development acceptance.

No dependency, binary pin, image base, compiler flags or ISA requirement changed.
No Elasticsearch/OpenSearch or other prohibited dependency was introduced.
Local/hosted proof cannot qualify changed images on the actual x86-64-v1 target.
Consolidated target qualification remains deferred until remaining MVP development.

## Preserved acceptance evidence

The private immutable bundle is acceptance.zip under
C:/Users/wagne/.codex/state/altvia-workspace/evidence/phase-3e-a-mail-intake-72116da/.
It contains 121 files including its manifest, 3852467 bytes. Archive SHA256:
4e500e0717b5b32794a2514313dc5bea454c8a7637fcc20f6d553d234d38e838.
ZIP integrity and every entry's length/hash were verified. The bundle retains
reviewed source, complete final and failed historical hosted logs/artifacts,
sanitized local RED/GREEN/results, source review, build/probe logs and ledger.
Session/environment/secret files are excluded. archive-receipt.json records the
source/count/size/hash separately. Subsequent publication changes Markdown only
and reuses unchanged tested application source.

## Remaining work

Native IMAP polling/checkpoints, bounded MIME processing, verified sender/thread
correlation, authorized triage/promotion, public replies/SMTP and scanned private
attachments retain subsequent contracts. Actual mailbox/identity/retention/size
policy remains Q-03/Q-09/Q-16/Q-21. Automation/consolidation, SLA/analytics/import
and final hardening remain in later roadmap phases. No production deployment,
real import, live mailbox use or Zammad retirement was performed or authorized.
