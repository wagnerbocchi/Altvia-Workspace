# Restricted identity administration implementation plan

> For agentic workers: use superpowers:executing-plans task by task with TDD and
> a fresh final reviewer. User authorized native execution and direct main pushes;
> do not insert another plan/PR approval pause.

Goal: provision ordinary internal accounts and safely activate, deactivate,
grant and revoke platform administration through the existing restricted CLI.

Architecture: extend altvia.management, whose transaction is owned by the CLI.
Reuse local Argon2, session invalidation, audit and outbox. Serialize privileged
management writes with the existing transaction advisory lock so concurrent
deactivation/demotion cannot remove the last active administrator. No migration,
HTTP endpoint, frontend screen or production account operation in this slice.

Tech stack: existing Python 3.12, SQLAlchemy 2, PostgreSQL and pytest.

Spec: ALTVIA_WORKSPACE_SPEC_CODEX.md; docs/contracts/api.md identity section;
docs/security/security-requirements.md; ADR-0003. This is Phase 1C-a, not the
Phase 1 exit gate. Worker/Compose/HTTP administration/scoped teams remain later.

## Global constraints

- Mandatory x86-64-v1; no new native or higher-ISA dependency.
- No default password, credential argument, public signup or implicit content ACL.
- Passwords 14+ characters, at most 1024 UTF-8 bytes, Argon2id.
- Transactional account/role/session/audit/outbox changes; no internal commit.
- All privilege/account-state changes revoke existing sessions and increment
  auth_version; an unchanged state creates no second effect.
- Tests run only on explicitly enabled disposable altvia_test. No real users.
- Preserve unrelated files and user containers; no production deployment.

## Review focus

1. Concurrent demotion/deactivation must leave at least one active platform admin.
2. A deactivated account cannot sign in; reactivation never resurrects old tokens.
3. Privilege changes revoke sessions even when the account remains active.
4. Audit/outbox failure rolls back account/role and session changes together.
5. CLI rejects invalid invocation/confirmation before password prompts or writes;
   DB/config errors never print secrets.

## Task 1: Transactional account and privilege operations

Files: modify apps/api/altvia/management.py; create
apps/api/tests/test_identity_administration.py. Existing models are sufficient.

Interfaces:
- create_user(db: Session, email: str, display_name: str, password: str) -> None
- set_account_active(db: Session, email: str, active: bool) -> bool
- set_platform_admin(db: Session, email: str, enabled: bool) -> bool
- Existing bootstrap_admin/reset_password retain their public signatures.

- [x] Add failing real-Postgres tests for ordinary provisioning/no role escalation,
  case-normalized duplicate, invalid fields, transactional rollback, disable/
  reenable, role grant/revoke, idempotent no-op, missing user, inactive grant and
  two concurrent attempts to remove active administrators.
- [x] Run the new tests and observe the missing-operation failures.
- [x] Extend management.py. Reuse one advisory lock (723504391), common account
  validation and session invalidation. Use FOR NO KEY UPDATE for user mutations
  so audit FK inserts are compatible with session revocation; never change PKs.
  Reject the last active admin removal with last_active_admin (409), duplicates
  with account_already_exists (409), absent user with account_not_found (404).
- [x] Run the complete API suite, Ruff/format and mypy. Commit the coherent service
  increment after passing checks; ledger the commit and results.

## Task 2: Restricted interactive command integration

Files: modify apps/api/altvia/cli.py; create apps/api/tests/test_identity_cli.py;
update docs/runbooks/development.md and docs/phase-1-evidence.md.

Consumes: Task 1 signatures. Produces CLI commands create-user, disable-user,
enable-user, grant-admin, revoke-admin, retaining bootstrap-admin/reset-password.

- [ ] Write failing CLI tests using real DB/services: create-user then HTTP login,
  state/role command effects, exact email confirmation, terminal/password-argument
  rejection, invalid arguments before prompts, safe errors and no secret output.
- [ ] Run the new tests and observe unsupported-command/behavior failures.
- [ ] Extend the parser. Password commands require hidden double entry; account/
  privilege commands require typed target-email confirmation. All commands require
  an interactive terminal. No password parameter or generic arbitrary role setter.
- [ ] Run all API tests, lint/format/mypy/build; obtain fresh read-only review,
  resolve material findings with regression proof, document commands/limits and
  publish completed changes directly to main. Observe API and browser CI.

## Decisions and execution ledger

- Ruling: native execution on main follows standing user authorization. Skill
  interview/worktree/publishing menus do not reopen settled decisions.
- Ruling: provision ordinary users through the restricted CLI first. The API has
  no public provisioning workflow; avoid a temporary password or unimplemented
  invite/reset delivery flow. Cost: operations still need trusted host access.
- Pre-flight: Task 2 consumes exactly Task 1's three signatures; no conflict.
- Phase 1 remains open for HTTP/scoped identity, worker/Compose/security and VM.
