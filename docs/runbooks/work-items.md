# Project tasks and subtasks

Scope: ADR-0020 task core. Homologation uses synthetic data. Production deployment,
real imports, ticket integration and membership provisioning require separate scope.

## Operate tasks

Open an authorized project, then Tarefas do projeto. Managers can create tasks,
select an optional owner, add up to 50 distinct participants, and select a principal
task in the same project. Agents create self-owned tasks without delegated links.
Assignment does not confer project access. Viewers can read only.

Task detail persists title, description, priority, estimate and optional deadline.
Managers control hierarchy and assignments. Agents update or transition tasks
only while assigned as owner or participant; scoped agents may comment. Former
contributors remain identified on historical links, but cannot obtain access from
those links. Removing access takes effect on subsequent reads and writes.

Date deadlines retain their original date and IANA zone. They include the full
local day; the stored boundary is the first instant of the following local date.
A missing deadline stays missing. Instant deadlines display their actual device
zone. Unrelated edits preserve the original exact instant. To change a repeated
local clock time, select UTC and enter the intended instant explicitly. Deliberate
browser instant changes support milliseconds; the API supports microseconds.

Start a one-off task before completion. Blocking requires a reason. Ongoing work
starts in progress and requires explicit Encerrar trabalho contínuo. Terminal
reopens require a reason; only managers restore cancelled work. Parent and child
states remain independent. No recurrence or completion cascade is generated.

Comments are internal plain text. The comment, state-history and activity sections
show author identifiers and bounded navigation. Activity may appear after worker
projection; use Atualizar atividade. Safe field names explain edits without
placing comment, title, description or reason prose in queue payloads.

## Recover uncertain writes

After an interrupted protected creation, transition or comment, use the displayed
verification action to replay the original intent and key. Do not create a new
request to guess whether the first one committed. Current authority is checked
before a saved receipt is exposed. A stale edit retains its inputs; explicitly
reload the latest version before choosing the final change. Session changes
dispose private cached data and pending intent.

Archived project/customer/team references remain readable within current scope.
They prevent new task writes; an already committed protected receipt remains
replayable if current resource/action authority still allows it. A retained stale
owner or participant does not prevent an unrelated manager edit, removal or new
active participant. Reassigning a removed stale contributor is refused.

## Verify and roll back

```bash
uv run python .superpowers/phase1-tests/run.py --api apps/api/tests -q
uv run python .superpowers/phase1-tests/run.py
uv run ruff check apps/api scripts
uv run ruff format --check apps/api scripts
uv run mypy
uv build
pnpm web:check
pnpm web:build
node --check scripts/container_browser.mjs
```

The local helper is Windows/Podman-specific and creates disposable test DB/Redis
containers. Hosted workflows use their declared services. Actual guest proof runs
scripts/container_smoke.py with ALTVIA_ALLOW_CONTAINER_TEST=1 in a new private
directory, then verifies native runtimes, cgroups and exact scanned image IDs.
The script retains private test configuration and volumes after stopping containers.
Never commit its secrets or raw logs.

Migration b46087000008 expands the existing schema. Comments and state history
are append-only. The API has only SELECT/INSERT there; the worker has no task-table
access. Populated downgrade is refused before destructive DDL. Preserve expanded
tables, data and volumes on rollback; use compatible API and worker images.
Stop an incompatible worker instead of consuming new event families with old
validation. Do not force downgrade, truncate history or reset volumes.

Task-core qualification and limits: ../phase-2c-work-evidence.md. Kanban, filtering,
search, My Work, external participants, tickets and imports remain later slices.
