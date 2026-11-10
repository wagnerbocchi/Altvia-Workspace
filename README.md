# Altvia Workspace

Internal self-hosted workspace for projects, work items and native service desk.

The [master specification](ALTVIA_WORKSPACE_SPEC_CODEX.md) defines the product.
The initial repository was empty. Phase 0 establishes contracts and decisions.
Phase 1A adds a tested PostgreSQL identity API; Phase 1B adds its real browser
login, account and logout flow with dark/light themes. The full workspace is not yet
implemented or production-validated. The earlier four-image Foundation stack
passed qualification on the supplied x86-64-v1 guest; future native artifacts must
repeat target validation.
Phase 1 is now complete, including persisted account/team administration, a real
durable identity worker and private Redis, administrative history and security CI.
The final five-image stack passed actual x86-64-v1 VM qualification, with zero
reported image vulnerabilities. All five hosted gates passed (290 API and 31
browser tests). See [Foundation closure](docs/phase-1-closure-evidence.md) for exact
source/image identities, migrations, recovery and operational limits.
Phase 2A now adds the real client registry, explicit initial-manager delegation,
scoped archive/restore/history and restricted customer-access CLI. Source dc091de
passed 316 API/37 browser tests, all five hosted gates and repeated actual guest
qualification with zero reported vulnerabilities in the five exact tested images.
See [Client registry evidence](docs/phase-2a-client-evidence.md).
Phase 2B adds persisted internal/customer projects, explicit project management,
shared operational areas, members and scoped history. Source 5faa866 passed 358
API/42 browser tests, all five hosted gates and actual x86-64-v1 qualification;
the same five tested images report zero vulnerabilities. See
[Project registry evidence](docs/phase-2b-project-evidence.md). Phase 2 remains open
for work items/boards/search/My Work and later client contracts. Production
deployment and real-data import remain separate.
Phase 1C-a extends restricted host administration for ordinary accounts and
platform privileges, with session revocation and last-active-admin protection.
Phase 1C-b adds the team identity/roster API, optimistic concurrency and protected
POST replay. Team membership grants no implicit client-content permission.
Phase 1C-c persists explicit team read scopes and restricted grant/revoke CLI.
Phase 1C-d packages the API with separate runtime DB privileges and API-only HTTPS
containers; acceptance evidence and remaining gates are in the Phase 1C report.
Phase 1C-e removes unused vulnerable SQLite from the API runtime and enforces that
capability boundary during image build and real container validation.
Phase 1C-g/h closes the recorded image findings and packages the frontend behind
the shared HTTPS edge. Phase 1C-i exposes real team/roster administration in the
browser, with explicit concurrency/recovery and isolated private session data.

## Project references

- [Discovery and workbook reconciliation](docs/discovery/repository-and-workbook.md)
- [PRD and requirement traceability](docs/prd/PRD.md)
- [Architecture and ownership](docs/architecture/architecture.md)
- [Data model and planned migrations](docs/architecture/data-model.md)
- [API and event contracts](docs/contracts/api.md)
- [Security and RBAC](docs/security/security-requirements.md)
- [x86-64-v1 compatibility gate](docs/architecture/infrastructure-compatibility.md)
- [Actual target VM qualification](docs/target-vm-foundation-evidence.md)
- [ADRs](docs/adr/0001-modular-monolith.md)
- [Roadmap, questions and gates](docs/roadmap.md)
- [Phase 0 evidence](docs/phase-0-report.md)
- [Development setup and checks](docs/runbooks/development.md)
- [Browser setup and HTTPS integration checks](docs/runbooks/browser-development.md)
- [Team identity API and concurrency/retry protocol](docs/runbooks/team-api.md)
- [API containers, file secrets and runtime privilege boundary](docs/runbooks/api-containers.md)
- [Phase 1 implementation evidence](docs/phase-1-evidence.md)
- [Phase 1 closure and final acceptance matrix](docs/phase-1-closure-evidence.md)
- [Phase 2A client registry acceptance](docs/phase-2a-client-evidence.md)
- [Client registry and explicit access operations](docs/runbooks/client-registry.md)
- [Phase 2B project and area acceptance](docs/phase-2b-project-evidence.md)
- [Project registry and explicit access operations](docs/runbooks/project-registry.md)
- [Phase 1C administration evidence](docs/phase-1c-evidence.md)

The original XLSX is retained locally under `data/sources/`, ignored by Git.
Obtain it through an authorized channel before implementing an importer. Do not
reconstruct operational records from documentation or seed production with samples.
