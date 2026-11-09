# Browser development and real identity checks

Scope: identity and team/roster browser development. Read ADR-0008/0015 and
the Phase 1/1C evidence for acceptance limits.
Prerequisites: Node 24, pnpm 11.25.0, the existing uv/Python 3.12 environment and
PostgreSQL 17. Exact frontend versions/integrities are in pnpm-lock.yaml.

```powershell
pnpm install --frozen-lockfile
node scripts/check_web_native.mjs
uv run python scripts/export_openapi.py
pnpm --filter @altvia/web generate:api
pnpm web:check
pnpm web:build
pnpm audit --audit-level=moderate
```

Use the same HTTPS origin for web and API. Route /api/v1 directly to FastAPI and
all page traffic to Next.js. `pnpm web:dev` binds web to 127.0.0.1:3000. The API
runbook binds 127.0.0.1:8000. The packaged shared HTTPS edge is documented in
[the container runbook](api-containers.md). Do not expose plain HTTP or disable
cookie security to log in.

There is no default account. Create a real development account with the existing
interactive bootstrap command against a separate development database. Account
creation, password/status and role administration remain restricted CLI operations.
Domain pages remain future deliveries.

## Team administration

After signing in with identity.manage, choose "Administrar equipes" from "Minha
conta", or open `/admin/teams`. Create or open a team, then rename, archive/restore
or manage participants from existing accounts. Pages contain at most ten records;
use the named previous/next controls. Names can repeat, so check the identifier.
Inactive accounts cannot be added; archived teams keep their roster. Membership
does not grant access to customer or project content.

If a create/add result cannot be confirmed, keep that page open and use "Verificar
resultado". The browser retains the same request in memory. Reloading or leaving
the page loses that unconfirmed intent; inspect current records before creating
another. A conflict or uncertain rename/removal requires explicit reload/review.
Unsaved names remain visible until explicit cancel/discard; routine background
refresh does not replace them. A temporary identity connection error hides private
content while preserving local state for retry. Confirmed access/session changes
close that state. Ordinary accounts have no administrative controls or data reads.

## Disposable browser integration

These tests create synthetic users/teams, expire sessions and disable one
synthetic roster account. Use only the
explicitly enabled disposable database named `altvia_test`. Configure an ignored
`.env.e2e` with the dedicated database URL, exact
`ALTVIA_PUBLIC_ORIGIN=https://127.0.0.1:3443` and `ALTVIA_ALLOW_TEST_DB=1`.
Do not reuse an operational credential/database. No production TLS trust or
certificate-store settings are changed.

```powershell
uv sync --locked
pnpm --filter @altvia/web exec playwright install chromium
pnpm web:build
uv run --env-file .env.e2e node apps/web/scripts/browser-test.mjs
```

The guarded fixture migrates that DB and creates random synthetic ordinary/admin
accounts plus bounded roster-selection fixtures. Use a fresh disposable test DB
for each run; reserved fixture addresses must not be reused in operational data.
Credentials go to ignored `.env.browser-session`, never stdout. The harness
starts API/web and an ephemeral self-signed HTTPS loopback gateway. Browser
certificate bypass applies only to this isolated Playwright context. Port probes
reject pre-existing listeners on 3000/8000/3443; cleanup closes task-owned process
trees, including Windows venv child interpreters. Tests never weaken production
Origin/CSRF rules, rate limits or Secure/HttpOnly cookie settings.

Tests cover real persistence, server expiry and failure recovery. Intercepted
network/rate responses test specific error states; they are not claimed as proof
of backend rate-limit correctness (the API suite owns that). axe checks target
the rendered browser views, not a complete accessibility certification. Screenshots
are local `.impeccable/review` evidence, ignored along with Playwright output.
Traces/video are disabled because identity credentials must not be recorded.

### Windows Podman connectivity used here

Windows forwarding from the task PostgreSQL container was unavailable. An SSH
local-forward channel through the existing Podman machine reached its loopback
DB port. This changed no host network/sshd configuration or trust setting.
The Windows SSH client does not provide Unix control-socket multiplexing; the
single persistent forwarding session was reused for all sequential tests and
closed afterward. No pre-existing user container was changed.

## Native CPU constraint and rollback

Optional Sharp installation is explicitly excluded, and image optimization is
disabled. `check_web_native.mjs` detects accidental presence on clean installs;
updating an older node_modules may retain an orphan link, so regenerate only
task-owned dependency directories if the check fails. Never waive that check.
Linux Node/SWC/oxide artifacts still require actual target-VM validation.

Rollback is a Git revert of this browser slice; no database migration is added.
The test-only TLS gateway is not a production service or deployment artifact.
