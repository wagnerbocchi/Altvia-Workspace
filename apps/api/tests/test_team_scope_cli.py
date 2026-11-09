from uuid import UUID

import pytest
from altvia import cli
from altvia.models import RoleBinding, Team
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_identity_cli import invoke

TEAM_ID = "00000000-0000-0000-0000-000000000123"


@pytest.mark.parametrize("role", ["viewer", "operations_manager"])
def test_cli_team_grant_and_revoke_require_email_and_team_confirmation(
    client, db_engine, settings, seeded_user, monkeypatch, role
):
    with Session(db_engine) as db, db.begin():
        db.add(Team(id=UUID(TEAM_ID), name="CLI scope"))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("Unexpected password"))
    for command, exists in [("grant-team-role", True), ("revoke-team-role", False)]:
        invoke(
            monkeypatch,
            settings,
            command,
            "employee@example.test",
            "--team-id",
            TEAM_ID,
            "--role",
            role,
        )
        answers = iter([" Employee@Example.Test ", TEAM_ID])
        prompts = []

        def confirm(prompt, prompts=prompts, answers=answers):
            prompts.append(prompt)
            return next(answers)

        monkeypatch.setattr("builtins.input", confirm)
        assert cli.main() == 0
        assert len(prompts) == 2
        with Session(db_engine) as db:
            binding = db.scalar(select(RoleBinding).where(RoleBinding.user_id == seeded_user))
            assert (binding is not None) == exists
            if exists:
                assert binding.role_name == role and binding.team_id == UUID(TEAM_ID)


@pytest.mark.parametrize(
    "command,extra",
    [
        ("grant-team-role", []),
        ("revoke-team-role", ["--team-id", TEAM_ID]),
        ("grant-team-role", ["--role", "viewer"]),
        ("grant-team-role", ["--team-id", "synthetic-secret", "--role", "viewer"]),
        ("grant-team-role", ["--team-id", TEAM_ID, "--role", "synthetic-secret"]),
        ("grant-admin", ["--team-id", TEAM_ID]),
        ("reset-password", ["--role", "viewer"]),
    ],
)
def test_team_flags_are_restricted_and_invalid_values_redacted(
    settings, monkeypatch, capsys, command, extra
):
    invoke(monkeypatch, settings, command, "employee@example.test", *extra)
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("Unexpected prompt"))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("Unexpected password"))
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "synthetic-secret" not in captured.err + captured.out


@pytest.mark.parametrize(
    "answer", ["wrong", "00000000-0000-0000-0000-000000000999", EOFError, KeyboardInterrupt]
)
def test_team_confirmation_failure_never_opens_database(settings, monkeypatch, answer):
    invoke(
        monkeypatch,
        settings,
        "grant-team-role",
        "employee@example.test",
        "--team-id",
        TEAM_ID,
        "--role",
        "viewer",
    )
    answers = iter(["employee@example.test", answer])

    def confirm(_):
        value = next(answers)
        if isinstance(value, type):
            raise value()
        return value

    monkeypatch.setattr("builtins.input", confirm)
    monkeypatch.setattr(cli, "make_engine", lambda _: pytest.fail("Unexpected database connection"))
    assert cli.main() == (130 if answer is KeyboardInterrupt else 1)
