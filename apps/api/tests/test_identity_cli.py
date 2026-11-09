import sys

import pytest
from altvia import cli, management
from altvia.config import Settings
from altvia.models import AuditLog, OutboxEvent, RoleBinding, User
from conftest import TEST_PASSWORD
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_sessions import login


def invoke(monkeypatch, settings, command, email="employee@example.test", *extra):
    monkeypatch.setattr(sys, "argv", ["altvia", command, "--email", email, *extra])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli, "Settings", lambda: settings)


def test_cli_provisions_real_nonprivileged_account(
    client, db_engine, settings, monkeypatch, capsys
):
    invoke(monkeypatch, settings, "create-user", "new@example.test", "--name", "New Employee")
    entered = iter([TEST_PASSWORD, TEST_PASSWORD])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(entered))
    assert cli.main() == 0
    assert TEST_PASSWORD not in capsys.readouterr().out
    response = client.post(
        "/api/v1/auth/sessions",
        json={
            "email": "new@example.test",
            "password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["capabilities"] == []
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 2


@pytest.mark.parametrize("command", ["disable-user", "enable-user", "grant-admin", "revoke-admin"])
def test_cli_state_and_privilege_changes_require_confirmation_and_no_password(
    client,
    db_engine,
    settings,
    monkeypatch,
    command,
):
    with Session(db_engine) as db, db.begin():
        management.bootstrap_admin(db, "admin@example.test", "Admin", TEST_PASSWORD)
        if command == "enable-user":
            management.set_account_active(db, "employee@example.test", False)
        if command == "revoke-admin":
            management.set_platform_admin(db, "employee@example.test", True)
    invoke(monkeypatch, settings, command)
    monkeypatch.setattr("builtins.input", lambda _: "employee@example.test")
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("Unexpected password prompt"))
    assert cli.main() == 0
    with Session(db_engine) as db:
        user = db.scalar(select(User).where(User.email_normalized == "employee@example.test"))
        assert user.active == (command != "disable-user")
        is_admin = db.scalar(select(RoleBinding).where(RoleBinding.user_id == user.id)) is not None
        assert is_admin == (command == "grant-admin")


def test_wrong_confirmation_never_mutates_or_prompts_for_password(
    client,
    db_engine,
    settings,
    monkeypatch,
    capsys,
):
    invoke(monkeypatch, settings, "disable-user")
    monkeypatch.setattr("builtins.input", lambda _: "another@example.test")
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("Unexpected password prompt"))
    assert cli.main() == 1
    assert "Confirmation" in capsys.readouterr().err
    with Session(db_engine) as db:
        assert db.scalar(select(User.active))
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize(
    "extra", [[], ["--name", "Ignored"]], ids=["missing-name", "unexpected-name"]
)
def test_invalid_command_fields_are_rejected_before_prompts(settings, monkeypatch, extra, capsys):
    command = "create-user" if not extra else "disable-user"
    invoke(monkeypatch, settings, command, "employee@example.test", *extra)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("Unexpected password prompt"))
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("Unexpected confirmation prompt"))
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    message = capsys.readouterr().err
    assert "--name is required" in message if not extra else "--name is only valid" in message


def test_noninteractive_command_is_rejected_before_secret_input(settings, monkeypatch, capsys):
    invoke(monkeypatch, settings, "create-user", "new@example.test", "--name", "New")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("Unexpected password prompt"))
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert "interactive terminal is required" in capsys.readouterr().err


def test_password_argument_is_rejected_and_never_echoed(settings, monkeypatch, capsys):
    secret = "Never echo this synthetic secret"
    invoke(
        monkeypatch,
        settings,
        "create-user",
        "new@example.test",
        "--name",
        "New",
        "--password",
        secret,
    )
    with pytest.raises(SystemExit):
        cli.main()
    captured = capsys.readouterr()
    assert secret not in captured.err + captured.out


def test_existing_command_also_rejects_secret_arguments_without_echo(settings, monkeypatch, capsys):
    secret = "Never echo this second synthetic secret"
    invoke(monkeypatch, settings, "reset-password", "employee@example.test", "--password", secret)
    with pytest.raises(SystemExit):
        cli.main()
    captured = capsys.readouterr()
    assert secret not in captured.err + captured.out


def test_password_mismatch_does_not_create_identity(
    client, db_engine, settings, monkeypatch, capsys
):
    invoke(monkeypatch, settings, "create-user", "new@example.test", "--name", "New")
    entered = iter([TEST_PASSWORD, "different password"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(entered))
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert "Passwords do not match" in captured.err
    assert TEST_PASSWORD not in captured.err + captured.out
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_cli_reports_last_admin_guard_without_changing_account(
    client,
    db_engine,
    settings,
    monkeypatch,
    capsys,
):
    with Session(db_engine) as db, db.begin():
        management.bootstrap_admin(db, "admin@example.test", "Admin", TEST_PASSWORD)
    invoke(monkeypatch, settings, "disable-user", "admin@example.test")
    monkeypatch.setattr("builtins.input", lambda _: "admin@example.test")
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("Unexpected password prompt"))
    assert cli.main() == 1
    assert "last_active_admin" in capsys.readouterr().err
    with Session(db_engine) as db:
        assert db.scalar(select(User.active).where(User.email_normalized == "admin@example.test"))


def test_cli_existing_reset_command_still_revokes_session(
    client,
    db_engine,
    settings,
    monkeypatch,
):
    assert login(client).status_code == 201
    invoke(monkeypatch, settings, "reset-password")
    entered = iter(["A newly reset test password!", "A newly reset test password!"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(entered))
    assert cli.main() == 0
    assert client.get("/api/v1/auth/me").status_code == 401


def test_database_error_during_cli_operation_is_redacted(
    client,
    db_engine,
    settings,
    monkeypatch,
    capsys,
):
    invoke(monkeypatch, settings, "disable-user")
    monkeypatch.setattr("builtins.input", lambda _: "employee@example.test")
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("Unexpected password prompt"))
    raw = "postgresql://u:private-password@localhost/db"

    def reject(*_):
        raise SQLAlchemyError(raw)

    monkeypatch.setattr(cli, "set_account_active", reject, raising=False)
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert raw not in captured.out + captured.err
    with Session(db_engine) as db:
        assert db.scalar(select(User.active))
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 0


def test_invalid_configuration_during_cli_operation_never_exposes_url(
    settings, monkeypatch, capsys
):
    invoke(monkeypatch, settings, "disable-user")
    monkeypatch.setattr("builtins.input", lambda _: "employee@example.test")
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("Unexpected password prompt"))
    raw = "mysql://u:private-password@x/db"

    def invalid():
        return Settings(_env_file=None, database_url=raw, public_origin="https://example.test")

    monkeypatch.setattr(cli, "Settings", invalid)
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert raw not in captured.out + captured.err
    assert "Invalid configuration" in captured.err


def test_engine_configuration_errors_are_redacted(client, settings, monkeypatch, capsys):
    invoke(monkeypatch, settings, "reset-password")
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: TEST_PASSWORD)
    raw = "postgresql+psycopg://u:private-password@invalid/db"

    def reject(_):
        raise ValueError(raw)

    monkeypatch.setattr(cli, "make_engine", reject)
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert raw not in captured.out + captured.err


@pytest.mark.parametrize("failure,code", [(EOFError, 1), (KeyboardInterrupt, 130)])
def test_cancelled_password_entry_never_mutates(
    client, settings, db_engine, monkeypatch, failure, code
):
    invoke(monkeypatch, settings, "reset-password")

    def cancel(_):
        raise failure()

    monkeypatch.setattr(cli.getpass, "getpass", cancel)
    assert cli.main() == code
    with Session(db_engine) as db:
        assert db.scalar(select(User.auth_version)) == 1


def test_insecure_getpass_fallback_is_rejected(client, settings, monkeypatch, capsys):
    invoke(monkeypatch, settings, "reset-password")

    def unsafe(_):
        raise cli.getpass.GetPassWarning("Synthetic unsafe terminal detail")

    monkeypatch.setattr(cli.getpass, "getpass", unsafe)
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert "Synthetic unsafe terminal detail" not in captured.out + captured.err
