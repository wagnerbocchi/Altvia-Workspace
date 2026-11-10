# Phase 2E contact/default-project evidence

Date: 2026-11-10. Scope ADR-0022. Phase 2E is implemented and qualified.
Application source 334d477 passed actual changed-artifact VM qualification;
test-only c722de2 passed all five final hosted gates. Their two-file diff changes
only contact browser fixtures/tests; runtime source and pinned inputs are unchanged.
No production deployment, email transport or real-data import.

Contracts preceded code in 3f0d1f1. Migration b46087000010 expands contacts and
nullable same-client defaults; a composite FK owns customer integrity. External
contact identities remain unverified and independent of internal accounts. All
nested resources require the parent customer ceiling plus client role. Real
writes reuse the identity lock before authentication, optimistic versions,
protected POST receipts and redacted transactional client audit/outbox.

The browser supplies a paged contact directory, protected create, scoped detail,
edit/archive/restore and explicit nullable default-project selection/clear. Each
client/contact read requires the customer ceiling plus client role, including
platform administrators. Contact writes require operations_manager; viewers read.
Each real contact write advances its own and parent versions; stale edits fail
instead of overwriting concurrent work. Saved POST receipts contain IDs only and
are returned after fresh parent authorization. Archived contacts retain unique
email identity per client; an address in another client or internal account
establishes no identity equality, portal access or permission.

Email is bounded ASCII dot-atom, strip/casefold normalized, server-only unverified.
Raw Unicode is rejected before casefold can substitute another address. Default
assignment requires current same-client active project/team/client; a composite
FK protects scope in SQL. Retained defaults survive archival and future ticket
consumers must revalidate and triage. No email, ticket or task side effect exists.

Files: client_contacts.py/contact_api.py own contact policy/HTTP, client_api.py
extends default configuration, models/migration10 own integrity, activity.py and
provision.py own strict events and least privilege. client-workspace components,
scoped routes and generated transports/types own browser workflows. PostgreSQL/API,
browser and packaged tests prove persistence, ACL, races, replay and recovery.

## Executed local proof

- Missing-route API RED: 404 instead of201. After implementation, 29 tests passed
  before the missing worker allowlist caused the expected projection failure.
  After strict event handling, focused contacts/storage: 35 passed in 78.82 seconds.
- `uv run python .superpowers/phase1-tests/run.py --api apps/api/tests -q --tb=short`:
  459 passed in 654.13 seconds. Covers inherited tests, real PostgreSQL, preserved migration
  rollback refusal/drift, scope, concurrent uniqueness, versions/replay and events.
- Later runtime DELETE denial test failed before restricting the new table to
  SELECT/INSERT/UPDATE. `test_api_contact_runtime_privilege_and_worker_denial`
  plus complete test_runtime_provision.py passed21 tests in 45.39 seconds afterward.
  Worker has no contact-table read privilege. The final hosted 463-test execution
  below includes this refinement and the later email corrections.
- Ruff check/format, strict mypy, source/wheel build, regenerated OpenAPI/TypeScript,
  web lint/types and production build passed. No runtime dependency was added.
- Browser initially failed on the absent contact link. The initial integrated
  run revealed delayed frame-scheduled field focus moving email input into name;
  mount-time layout focus fixed that behavior. All four contact browser tests
  then passed in 13.9 seconds, including persisted create/edit/archive/restore/default/
  clear, committed-create lost response with identical replay body/key,
  stale contact/default conflict recovery, viewer and hidden-account boundaries.
  Sixteen actual synthetic desktop/mobile/light/dark captures include axe and
  overflow checks. The subsequent complete review result is recorded below.

Subsequent review/validation supersedes that pending visual status:

- Impeccable's owning-client context and default-selector/cancel focus findings
  were reproduced RED and fixed. Complete Windows browser suite: 58 passed in 3.2 minutes.
  The same reviewer inspected all sixteen recaptures plus four focused-editor
  captures, scored both fixes resolved and returned ship at that fix scope.
  Documenter updated PRODUCT.md; DESIGN.md/sidecar remain unchanged, including
  preexisting narrative.rules drift. Actual source hooks reported no deterministic
  issues; this is not a whole-design approval.
- One fresh source review found two P2 email-contract defects: Zod's generic email
  predicate rejected API-supported dot-atom addresses and blocked name-only edits;
  API casefold converted some unsupported Unicode mailboxes into different ASCII
  addresses. Both were reproduced before correction. Browser now validates the
  bounded ASCII dot-atom policy inline; API rejects raw non-ASCII before casefold.
  Rejected Unicode create/PATCH leaves contact/client versions and events intact.
- After those source fixes, contacts/storage39 passed in 84.28 seconds and affected browser 8
  passed in 19.5 seconds, covering slash/exclamation mailboxes in both create and name-only
  edits. Ruff/format/mypy and web check/build passed. No second source review.
  Final complete hosted suites and actual-target qualification passed below.

## Infrastructure and remaining gates

An initial Windows test harness failed while decoding child CP1252 output as
UTF-8. The ignored local runner now sets child Python UTF-8 output; the repeated
test then demonstrated the actual missing behavior. A PowerShell unquoted
@contacts filter also selected no tests; only the repeated explicit-file failure
counts as RED. No production policy or test assertion was weakened.

The first hosted revision 334d477 passed API 463/202.90s, containers, source and image
security; browser 54 passed/6 failed on HTTP429. Complete run analysis found the
40-attempt source cap in fixed 600-second windows. The earlier Windows58 run
crossed a bucket boundary; Linux exhausted the same bucket during ordinary setup.
Test-only c722de2 reuses three real password-verified sessions from the guarded
disposable fixture. Subsequent requests still authenticate against actual sessions,
roles and ceilings with Secure/HttpOnly host-only cookies and real CSRF. Fixture
secrets remain ignored and mode 0600; login HTTP/rate-limit tests are unchanged.
No cap, source header, retry, timeout or assertion was weakened. Full Windows60
passed in 3.2 minutes within one window: 39 HTTP201, one invalid401 and one pre-auth403,
no 429. The existing intermittent Windows axe cause is not claimed resolved merely
because this complete run passed.

## Final hosted acceptance

Exact test revision: c722de2b7c1f394ef4391eebcf9bc32d625bcaf9.

| Gate | Executed result |
| --- | --- |
| [API 42856007216](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42856007216) | 463 passed in 205.24 seconds; migrations/drift, lint/format/types/build passed |
| [Browser 42856007332](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42856007332) | 60 passed in 1.7 minutes; locked build/contracts/types/native guard/audit passed |
| [Containers 42856007133](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42856007133) | Actual Docker/HTTPS contact/default/replay/scope/recreation/browser plus existing restore/worker/native-search proof passed |
| [Images 42856006965](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42856006965) | Eight scanner tests passed; five nonempty inventories, matching report hashes and zero reported vulnerabilities |
| [Source 42856007168](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42856007168) | Zero secrets or blocking SAST; four existing LOW CLI/assert metadata findings retained |

The final packaged contact and directory captures were inspected, including
owning-client identity and persisted revised contact name. Complete initial/final
logs and image/source reports are retained. Action-level Node20/24,
url.parse/punycode deprecation notices and disposable PostgreSQL local-init trust
warnings are test infrastructure observations; no product security policy was
changed in response. Final browser acceptance includes the six initially failed
tests; no filtered rerun or silent skip substitutes for the complete suite.

## Actual x86-64-v1 target qualification

Exact immutable application: 334d477c0c8dc785d4c7add463a33a8b8ebf6287.
Archive SHA256 cb933efade324c821e3ced93f8fb29c2f09be28ed4f0e188225f6a20f1ef36a4.
Private source: /root/altvia-contacts-334d477-162148/source; unique Compose project
altvia-test-355453e0d1. Smoke ran 2026-11-10T16:22:00Z..16:25:51Z, exit 0.
Separate native/resource/event verification and actual-image scanning exited 0.

The guest still advertises SSE2/pni/cx16 but no SSSE3/SSE4.1/SSE4.2/AVX/AVX2/FMA/
BMI2. Python 3.12.16/Argon2/imports, Node 24.22.1/ICU/TLS, PostgreSQL 17.11,
Redis 7.4.12 and nginx 1.30.6 executed successfully. Runtime guards confirm no API
SQLite, web Sharp or API/web package installers. No service, native dependency,
compiler baseline or mandatory ISA changed. No -march=native.

| Native target proof | Executed result |
| --- | --- |
| Contact/default API | Client-local email identity, minimal replay, archive/restore, cross-client denial, explicit same-client default and persistence after API/PostgreSQL recreation passed |
| Real packaged browser | Mobile contact create/edit/reload, directory and owning-client context passed; sixteen synthetic captures retained and contact views inspected |
| Client worker projection | Three contact.created/five contact.updated events projected once as client activity; two default-project events delivered |
| Broker loss/recovery | Worker exited 0 in 7.754 seconds with Redis blackholed and recovered all 27 events |
| Native DB/recovery | Logical cross-libc restore/Unicode/constraints, restart, migrations and GIN selection over 6000 rolled-back rows passed; 0.741 ms search execution is diagnostic only |
| Resources/isolation | Live cgroup memory/CPU/PID match Compose; read-only roots, dropped capabilities, no-new-privileges, private DB/queue networks and loopback-only ingress verified; migration-job configuration inspected |
| Cleanup | No task containers running; volumes and prior discovery/task-core environments preserved; each Windows SSH stage connection closed, permanent agent key remains loaded |

Memory/CPU/PID limits: API/PostgreSQL/web 512 MiB/1 CPU/128; worker/migration
256 MiB/1 CPU/64; Redis 128 MiB/0.5 CPU/64; ingress 64 MiB/0.5 CPU/64. PostgreSQL retains
its tested privilege-dropping entrypoint; other long-running services use their
declared non-root accounts. No SSH daemon/firewall policy changed.

| Actual native-tested image | Docker image ID | Packages | Reported vulnerabilities |
| --- | --- | --- | --- |
| API, worker and migration | sha256:618d4ab96b53d58c352f1c2849ab943dd8a5cfa0b5b63a1f278fecab2b2dccb3 | 66 | 0 |
| PostgreSQL | sha256:197ded380a8b1fa48d76743e280a4059b7b02f9dd46e69256123afc34dc60a91 | 49 | 0 |
| Web | sha256:4dd0f18f26eb6e2c863a93b5244abdfa650081a3cb7f5ea6a4b56a280dc6c7aa | 43 | 0 |
| Ingress | sha256:8099179f51b103da4ee07517378ea46d2a81e337c714e885ac7d7adf5730c5f5 | 70 | 0 |
| Redis | sha256:721f763070475edd6510d3943ed8796c0e514f3ec13b181e2a0bf18602a77400 | 16 | 0 |

Trivy pinned image sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa
used the available database updated 2026-11-09T19:03:15Z, next update
2026-11-10T19:03:15Z, SHA256
8c808b8e2b45da2b9849fab569412fd5b0a59455d3335ea0321f0179bcd86130.
All severities/packages are retained, with no ignore file or unfixed filter.
Verification matches native/resource Docker IDs to the scanner manifest and each
unique archive tag, ordered DiffIDs, configured user and report SHA256. Archive
Trivy Metadata.ImageID is not assumed equal to Docker's runtime ID. Hosted IDs
are not substituted for native IDs. Git verifies 334d477..c722de2 changes exactly
apps/web/tests/contacts.spec.ts and scripts/browser_fixture.py; application/native/
dependency inputs remain unchanged, so the exact already-tested images are reused.

Reproduction: frozen dependencies; on the pinned private archive run
`ALTVIA_ALLOW_CONTAINER_TEST=1 python3 scripts/container_smoke.py`; restart its
unique project with --no-build for native/cgroup/event checks; stop preserving
volumes; scan all five docker-save archives; transfer and verify complete evidence.
Exact helper sources, command exit codes and native stdout/stderr are retained.

## Preserved evidence, rollback and limits

Codex Security persistent target artifact:
artifacts/phase2-contact-proof/acceptance.zip, SHA256
3377551e004b4ea0835974fea66d5a433d336f2e7722a775628267ebca18a285.
Includes exact source/state/resource/scan manifests and full reports, native GIN/
outage/event proof, 16 guest captures, 20 local captures, both hosted revisions'
complete logs/artifacts, failed-run history, source/visual/documentation reviews,
decisions and successful qualification verification. Workbook, fixture secrets,
private keys, authentication files and production logs are excluded.

Migration10 is expand-only; preserve expanded contacts/defaults/audit/outbox/
activity and use a compatible application/worker on rollback. Downgrade refuses
durable contact/default data or corresponding events before destructive DDL.
No production migration/deployment, real import, email send or Zammad retirement.
Q-16 still gates actual verification/international email. Retention, representative
capacity and production readiness remain open; a synthetic query timing promises
no production latency. Phase 2 exit still requires traceability of planned member,
milestone and external-participant workflows before starting Service Desk.
