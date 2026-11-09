# Altvia Workspace

Internal self-hosted workspace for projects, work items and native service desk.

The [master specification](ALTVIA_WORKSPACE_SPEC_CODEX.md) defines the product.
The initial repository was empty. Phase 0 establishes contracts and decisions.
Phase 1A adds a tested PostgreSQL identity API. The full workspace is not yet
implemented or production-validated. No target CPU homologation is claimed.

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
- [Phase 1 implementation evidence](docs/phase-1-evidence.md)

The original XLSX is retained locally under `data/sources/`, ignored by Git.
Obtain it through an authorized channel before implementing an importer. Do not
reconstruct operational records from documentation or seed production with samples.
