# Phase 2F project member administration evidence

Status: implementation and local verification; hosted/target qualification pending.
This report does not close Phase 2 or authorize production deployment.

## Scope and implementation

ADR-0023 and plan docs/plans/2026-11-10-project-members.md preceded product code
in 32e5a78. Persisted HTTP membership writes and generated contracts are619f94c;
deterministic revocation/roster race evidence isce15847. Managers add an existing
account by known email, change its direct role and remove direct access. No global
directory or customer ceiling grant is introduced. The browser confirms every
known-email grant before submission and retains the original uncertain intent.

Shared domain ownership keeps membership/binding changes, session invalidation,
Project version and redacted audit/outbox in one transaction. Identity write lock
precedes authentication. Reads/writes/replays retain current customer/project ACL.
Member pages verify their Project version unchanged around the roster query. The
browser never combines an old roster with a fresh parent's write version.

No migration, data import, new package/native artifact or ISA requirement is added.
Rollback preserves all existing data/events and the compatible CLI; no downgrade
or volume deletion is needed. No production deployment or security/SSH change.

## Local evidence

- `python .superpowers/phase1-tests/run.py --api -q`: 476 passed in691.38s before
  the roster-version read extension; affected project/CLI/member suite then40
  passed in97.17s, including the new version field. Final enlarged suite pending.
- Missing membership routes:13 new tests failed405 before implementation.
- Version-field regression failed KeyError before implementation.
- Distinct-session account/customer revocation tests observed actual advisory-lock
  waiters before authentication, then401/no access/version/event effect. Both
  failed when serialization was temporarily removed. Roster interleaving failed
  200-versus409 with its guard removed. Restored production sources:3 passed in10.14s.
- Browser initial six workflows passed; full66 passed in3.5m. Mobile readable-width
  regression failed before reusing the existing responsive member-row pattern.
- Source review identified the add-form self-demotion confirmation gap and the
  inadequate concurrent-request proof. Explicit confirmation test failed before
  correction; all7 member browser tests passed in17.3s afterward. Complete final
  browser run pending. No critical/minor findings or declined behaviors.
- Ruff/format/mypy, generated OpenAPI/TypeScript, web check/build, native dependency
  guard and dependency audit passed. No new dependency or Sharp is present.
- Sixteen real desktop/mobile/light/dark captures cover directory, reviewed grant,
  role editing and removal. They have zero axe violations and no horizontal
  overflow; mobile member identity width is tested. Impeccable finish pending.

## Decisions and practical limits

- Known-email transactional addition avoids a new global account lookup surface;
  a mistaken approved address needs an explicit audited correction.
- Stable version around the roster read avoids project/session lock inversion;
  concurrent changes may require manual refresh.
- Every known-email grant receives explicit review, including Unicode self-targets;
  ordinary additions incur one extra confirmation.

Basic project milestones and external work participants remain subsequent Phase 2
slices. Advanced dependency planning remains FR-016/P2 backlog. Real account/client
provisioning, retention/capacity and production acceptance remain separate gates.
