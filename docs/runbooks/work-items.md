# Project tasks and subtasks

Scope: ADR-0020 task core and ADR-0021 discovery. Homologation uses synthetic data. Production deployment,
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

## Identify outside involvement

ADR-0025 adds Envolvidos externos, um por linha to the manager's existing create
and edit form. Enter up to 50 names, at most 150 Unicode code points per name.
Blank lines are ignored; repeated exact names are refused after whitespace trim.
Names are supplied attribution, not verified identities. They do not create an
account, grant project/client access, send a message or add work to an employee's
My Work. No contact directory or matching by name/email is consulted.

Detail displays these names separately from internal participants. Managers can
replace the list or clear the field to remove all external involvement. Agents
and readers consult the names; an assigned agent editing other content preserves
them. The list shares the task's reviewed version, current-reference checks,
original creation intent and explicit conflict reload. Do not rebase an old edit
on a fresh task version without reviewing the current list.

The browser follows the API's whitespace rules and preserves non-whitespace
Unicode content, including U+FEFF, during unrelated edits. External-only changes
record the field name in internal task history without copying names into events.

Migration b46087000012 adds a task-owned link table. Preserve the expanded table,
all existing labels and durable audit/outbox/activity on application rollback.
Downgrade refuses data or new-field events, even after every label was cleared;
its table lock prevents a concurrent link write from bypassing the data check.
Keep a compatible worker for the new changed field, or stop it until compatible
code resumes. No forced downgrade, volume reset or real-data import is authorized.

## Find tasks and operate the board

Project task discovery defaults to a paged list. Search applies to the title and
description through native PostgreSQL Portuguese full-text search. Use quoted
phrases, OR and minus-prefixed exclusions as supported by websearch syntax.
Stopwords alone may produce no matches. Search is word-based, not a substring or
identifier lookup. Apply filters deliberately; Limpar filtros restores defaults.

Filtros adicionais expands status, priority, work type, personal involvement and
deadline presence. Each filter change starts a fresh page. Quadro groups matches
by task state with independent paging, loading, retry and empty feedback. Each
column is a partial page, not a total count. Open the task detail to change state;
the board does not implement a separate transition protocol or drag operation.
Refreshing task results also refreshes creation authority. An authority read error
locks new creation until recovery without discarding retained intent.

Meu trabalho includes authorized tasks where the current account is owner or
participant, once per task. It includes all states unless filtered. Each result
links to its project and existing task detail. Assignment never grants project
access. Tickets are not included in this increment.

API-only discovery filters also support an explicit owner or involved account,
unassigned tasks, and inclusive due_from/exclusive due_before aware timestamps.
Personal queries support project scope. Unknown or repeated query keys are refused.
Filtered cursors bind actor and normalized criteria; do not reuse them after a
filter change. Date precision and timezone semantics remain those above.

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

Migration b46087000009 changes indexes only, including a Portuguese GIN expression
index over title and description. Its downgrade preserves task/history data and
restores the former owner/participant indexes. Rolling back this increment still
requires retaining migration8's expanded data and compatible write consumers.

Task-core qualification: ../phase-2c-work-evidence.md. Discovery qualification and
remaining gates: ../phase-2d-discovery-evidence.md. External participants, tickets
and imports remain later slices.
