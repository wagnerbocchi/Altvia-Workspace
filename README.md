# Altvia Workspace

Internal self-hosted workspace for projects, work items and native service desk.

The [master specification](ALTVIA_WORKSPACE_SPEC_CODEX.md) defines the product.
The initial repository was empty. Phase 0 establishes contracts and decisions.
Phase 1A adds a tested PostgreSQL identity API; Phase 1B adds its real browser
login, account and logout flow with dark/light themes. The full workspace is not yet
implemented or production-validated. No target CPU homologation is claimed.
Phase 1C-a extends restricted host administration for ordinary accounts and
platform privileges, with session revocation and last-active-admin protection.
Phase 1C-b adds the team identity/roster API, optimistic concurrency and protected
POST replay. Team membership grants no implicit client-content permission.
Phase 1C-c persists explicit team read scopes and restricted grant/revoke CLI.
Phase 1C-d packages the API with separate runtime DB privileges and API-only HTTPS
containers; acceptance evidence and remaining gates are in the Phase 1C report.
Phase 1C-e removes unused vulnerable SQLite from the API runtime and enforces that
capability boundary during image build and real container validation.

## Project references

- [Discovery and workbook reconciliation](docs/discovery/repository-and-workbook.md)
- [PRD and requirement traceability](docs/prd/PRD.md)
- [Architecture and ownership](docs/architecture/architecture.md)
- [Data model and planned migrations](docs/architecture/data-model.md)
- [API and event contracts](docs/contracts/api.md)
- [Security and RBAC](docs/security/security-requirements.md)
- [x86-64-v1 compatibility gate](docs/architecture/infrastructure-compatibility.md)
- [ADRs](docs/adr/0001-modular-monolith.md)
- [Roadmap, questions and gates](docs/roadmap.md)
- [Phase 0 evidence](docs/phase-0-report.md)
- [Development setup and checks](docs/runbooks/development.md)
- [Browser setup and HTTPS integration checks](docs/runbooks/browser-development.md)
- [Team identity API and concurrency/retry protocol](docs/runbooks/team-api.md)
- [API containers, file secrets and runtime privilege boundary](docs/runbooks/api-containers.md)
- [Phase 1 implementation evidence](docs/phase-1-evidence.md)
- [Phase 1C administration evidence](docs/phase-1c-evidence.md)

The original XLSX is retained locally under `data/sources/`, ignored by Git.
Obtain it through an authorized channel before implementing an importer. Do not
reconstruct operational records from documentation or seed production with samples.
