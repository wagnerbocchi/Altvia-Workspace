# Queue and category configuration

ADR-0026 defines the team-owned Service Desk registry. Open Filas de atendimento
from Minha conta, select an explicitly managed active team and enter a queue name.
The selected team is immutable. Open a queue to rename, archive or restore it,
maintain its categories and consult scoped history. Categories keep their own
active flags when a queue is archived.

Global platform configuration administrators can configure queues. Explicit team
operations_manager bindings manage their team's configuration. Team viewer
bindings consult it. Roster membership supplies no configuration authority.
Customer ticket content will use its separately contracted queue permissions
and explicit customer ceiling in the next slices.

## Write recovery

Creation uses a persisted immutable ID receipt. If its response is lost, use
Verificar cadastro with the original retained team, name and idempotency key.
The server rechecks authority before replay. Read failures and independently
paged queue/team lists preserve that intent. A different request using the same
key returns idempotency_conflict.

Rename and archive confirmation retain the reviewed record version. A competing
edit returns version_conflict. Recarregar e descartar edicao fetches current data
before releasing that draft. A failed read keeps the draft blocked and readable.
Dependent controls stay blocked while local writes and their version refreshes
are pending. Retry an unavailable read to reconcile the record before acting.
Queue history advances on category changes as well as queue edits.

Names contain 1..150 Unicode code points after Python strip normalization. NUL,
CR and LF are rejected. Exact names are unique within their parent, including
archived records. Restore that record or choose another name after name_exists.
Actual new records and edits require active ancestors. Reads, coherent no-ops
and committed receipt replay remain available after ancestor archive.

## Verification

Run the guarded local helper against disposable local PostgreSQL and Redis.

```powershell
python .superpowers/phase1-tests/run.py --api apps/api/tests/test_ticket_queues.py -q
python .superpowers/phase1-tests/run.py ticket-queues.spec.ts
uv run ruff check apps/api scripts
uv run ruff format --check apps/api scripts
uv run mypy
pnpm web:check
pnpm web:build
```

Hosted gates run complete API/browser checks and actual packaged persistence,
scope, worker and recovery proof. Queue/category fixtures are created after the
existing broker-outage batch and checked after API/PostgreSQL recreation.
Final target qualification follows remaining MVP development under the current
user-directed cadence. Record the exact tested source and image reports.

## Preservation and remaining checks

Migration b46087000013 expands schema and the activity resource constraint. The
API has SELECT/INSERT/UPDATE on queue metadata. The worker consumes redacted
outbox events without queue-table access. Downgrade takes exclusive table locks
and refuses surviving rows or durable queue audit/outbox/activity. Preserve the
schema, metadata, history and volumes. An application rollback requires a worker
that understands the queue event family.

The source review records a deferred defense gap in direct SQL nonblank checks.
PostgreSQL btrim with its default argument recognizes ordinary spaces. HTTP
validation applies the full Python whitespace rule, while a direct SQL write
could still insert a tab/NBSP-only name. The current application rejects that
input. The direct SQL constraint needs a future matching-whitespace refinement.
