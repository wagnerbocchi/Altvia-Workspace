# Phase 2H external work participant evidence

Status: development acceptance complete on f5b4e2a, 2026-11-10. All five hosted
gates passed. Target homologation remains deferred until remaining MVP
development is complete, per the user's 2026-11-10 instruction. No target SSH,
production deployment, real import or identity/contact mapping occurred.

## Scope and source

Contracts/ADR-0025/plan preceded implementation in 6a03689. Backend a4c456d adds
work_item_external_participants through expand-only migration b46087000012,
existing WorkCreate/Patch/Output fields and redacted work activity. External
involvement is bounded task-owned plain-text attribution: at most 50 distinct
trimmed exact case-sensitive labels of 1..150 Unicode code points, without NUL/CR/LF.
It creates no account, contact link, session, grant, email or My Work involvement.

Manager-only metadata uses existing identity-before-authentication, project graph
and scoped work-row locking. Real set changes advance the task once with atomic
audit/outbox; reordering is a no-op. The current project/customer ceiling remains
mandatory. Assigned agents can edit independent content without changing these
labels; readers only consult. Current writable references and stale/exhausted
version checks remain. The API has SELECT/INSERT/DELETE only on the new table;
the worker cannot read it. External-only changes are updated, never assigned.

Empty creation lists are omitted from the canonical fingerprint to preserve old
keys. Existing transition receipts default the new output field to [], preserving
their historical snapshot without rewriting stored receipts. The browser retains
original uncertain lists/keys and reviewed task versions through read recovery.
No dependency, service, native library or ISA requirement was introduced.

## Executed local evidence

- Initial real API RED: 13 failed/10 invalid-input passes in 51.47s for unsupported
  fields, absent table/output and strict event validation. Focused GREEN:23 passed
  in 68.00s. Added legacy-task migration preservation before the complete run.
- Complete local API: 522 passed/1 failed in 957.00s. The pre-existing discovery
  rollback probe ran current expanded code after dropping later metadata tables,
  causing 503 on history lookup. The corrected probe checks v8 history directly,
  restores head, then asserts current HTTP history. Final affected suite:
  `python .superpowers/phase1-tests/run.py --api apps/api/tests/test_external_work_participants.py apps/api/tests/test_work_discovery.py::test_discovery_index_rollback_preserves_tasks_and_history -q`:
  24 passed in 70.03s. The final full hosted run passed all 523 tests; this report
  does not turn the earlier failed local run into a complete passing local run.
- Initial five-browser-test RED included three mistaken /work-items UI routes; corrected
  /projects/{id}/work rerun explicitly failed on the missing external field.
  After implementation, five real workflows passed in 21.8s, then 23.9s after
  waiting for the actual section before checking that loading had settled.
- One fresh source review reported a Unicode Minor. Root regraded it Important:
  JavaScript trim() drops U+FEFF although Python strip() retains it, so a legal
  API-created list could be altered or block an unrelated browser title edit.
  A real API-to-browser regression failed before correction. The local parser now
  matches Unicode White_Space plus Python's ASCII separators, retaining U+FEFF.
  All six feature browser tests passed in 18.5s after the one fix pass, including
  exact Unicode preservation, real persistence, clear/reload, keyboard, manager/
  agent/reader limits, literal text, uncertain POST recovery and stale review.
- Complete local browser suite: 78 passed in 5.1m after the Unicode correction.
  Frontend/fixture/packaged assertions were published in f5b4e2a, following the
  contract and backend commits. No application source follows that revision.
- Ruff/format/mypy, generated OpenAPI/TypeScript and web check/build passed.
  The new packaged smoke supplies external labels and asserts them again after
  API/PostgreSQL recreation. That hosted gate passed; no local Docker or target-VM
  proof is claimed.

The guarded local runner uses disposable PostgreSQL/Redis with a localhost Podman
tunnel. No target-server connection is made. Complete failed/passing logs are
retained; existing Next standalone/NO_COLOR harness warnings are not product failures.

## Reviews and visual evidence

One fresh immutable source review covered c7d1f37 plus contracts and implementation,
SHA256 ff3b5419ce93d6ea4e1be6763982eb48d736383735e489c5910e286e50b0844a.
It found no Critical/Important and the Unicode Minor above. Root's regraded fix
has real RED/GREEN evidence; no second source review is claimed. No source Minor
is left deferred. The reviewer correctly did not certify hosted/publication,
settled captures, future contact association or deferred target CPU execution.

Sixteen real create/detail/edit/recovery captures cover desktop 1440/mobile 390,
light/dark, axe and overflow checks. The helper operates the actual theme control
and asserts browser color-scheme. A first detail-light frame caught comments
loading after reload; those original frames were retained and the settled rerun
replaced them. All 16 final frames were opened and validated before handoff.
Impeccable's fresh full-surface finish review returned ship with no material
fixes. Its documenter verified this as an ordinary code-led Operate extension;
DESIGN.md and .impeccable/design.json remain unchanged. The pre-existing empty
sidecar narrative.rules drift was recorded without unrelated system repair.

## Hosted acceptance and preserved evidence

All five gates passed on exact f5b4e2a0e7e1cbe9893ac0d02bec4ba248aed7c0.
Complete run logs, job metadata, artifact metadata and downloadable artifacts
were retained. No image scan or CPU success is inferred from a prior delivery.

| Gate | Exact run | Result |
| --- | --- | --- |
| API | [42905035228](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42905035228) | 523 passed in 231.65s; format/lint/mypy/migrations/build |
| Browser | [42905035277](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42905035277) | 78 passed in 2.7m; types/lint/build/contracts/audit/native guard |
| Containers | [42905035341](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42905035341) | Actual packaged HTTPS/browser/ACL/persistence/worker/recovery and logical restore, including external labels after API/PostgreSQL recreation |
| Service images | [42905035179](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42905035179) | Five complete inventories, zero reported vulnerabilities |
| Source | [42905035414](https://github.com/wagnerbocchi/Altvia-Workspace/actions/runs/42905035414) | Zero detected secrets/blocking findings; four existing LOW SAST metadata findings retained |

Full-log inspection distinguishes intentional SQL negative-test refusals from
failures: constraints, restricted grants, append-only history, safe downgrade
refusal and the raw concurrent-parent test's accepted 40P01. The last test forces
opposing row locks before advisory graph locking and confirms one refusal, one
commit and no cycle. Browser/container logs contain no unhandled product failure.
Existing action deprecation, initdb-local trust and harness warnings remain
visible; no cap, timeout, gate or suppression policy was relaxed.

The source-security run 42905035414 on f5b4e2a reports zero detected secrets and
zero blocking SAST findings. Four existing LOW Bandit metadata findings remain
visible: cli.py B105/B101, management.py B101 and provision.py B101. They are not
new external-participant source-review minors and have not been suppressed.

The image-security run 42905035179 on that exact source passed. Each complete
JSON report was read, its SHA256 compared with the manifest, and its installed
package inventory confirmed nonempty. All severities contain zero reported
vulnerabilities. Scanner database SHA256:
cf7fa3086682e8f77298ca8178419a530f97d7c4bd3ac203a64f2977f82e94a6,
UpdatedAt 2026-11-10T19:01:23.081219346Z. These hosted scanned artifacts are not
target-VM-qualified images; container functional proof is a separate build.

| Service | Scanned image ID | Packages |
| --- | --- | --- |
| API | sha256:5c7fb3d649b8f80c94ff994e28c8d246ede7e62355442019c5396e6d56af017d | 66 |
| PostgreSQL | sha256:2ce71db3061e7f55638e391e9c308b491dd7a676975e3d725cd138e2cd32fb07 | 49 |
| Ingress | sha256:0534fed19f3f1ad2efc16efae445c0bb4af171b920f78a0aeeff47d46d2af390 | 70 |
| Web | sha256:da7888698a3e5a6608aa1b74cc7f40d2a95257be3450491923d7c6cfe4c01f20 | 43 |
| Redis | sha256:2f31f822751d7bdafc83bb1f1b394407fcee666e057146c69695942c25e9686a | 16 |

## Preserved evidence

Private durable artifact: phase-2h-external-participants-f5b4e2a/acceptance.zip,
115 files, 5538375 bytes. SHA256
8ffcd9daa607d45229742bd4ac56e1c73bd0d7a5c4051b7be0bd2dca64d2ea72.
ZIP integrity and every file's size/SHA256 were checked. It preserves original
RED/failed runs, final local/hosted logs, complete scans/inventories and artifact
metadata, immutable source review, Unicode correction, rollback-test correction,
Impeccable finish/documentation, initial captures and all 16 final reviewed frames.
The final documentation/publication proof and final ledger are retained separately
without overwriting the acceptance archive. Only Markdown documentation follows
the verified application source. Credentials, raw source workbooks, production
data and production logs remain outside Git.

## Rollback and remaining scope

Keep expanded schema, task labels and all durable history. The downgrade locks
the link table and refuses populated data or external_participants events even
after labels were cleared. A compatible worker must keep validating that changed
field; preserve data rather than forcing downgrade or resetting volumes.

Contact association remains Q-18: task and contact read scopes are deliberately
separate; labels are maintained manually until a separately scoped policy exists.
Final integrated x86-64-v1 qualification stays pending. The completed Phase 2
development traceability audit is docs/phase-2-development-closure.md. Native
Service Desk contracts and bounded queue/ticket development follow in Phase 3.
