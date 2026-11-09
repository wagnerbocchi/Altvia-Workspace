# Altvia Workspace

Internal self-hosted workspace for projects, work items and native service desk.

The [master specification](ALTVIA_WORKSPACE_SPEC_CODEX.md) defines the product.
The initial repository was empty. Phase 0 establishes contracts and decisions;
it does not constitute an implemented or production-validated system.

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

The original XLSX is retained locally under `data/sources/`, ignored by Git.
Obtain it through an authorized channel before implementing an importer. Do not
reconstruct operational records from documentation or seed production with samples.
