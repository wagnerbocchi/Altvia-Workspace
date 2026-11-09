from uuid import UUID, uuid4

import pytest
from altvia import cli
from sqlalchemy.orm import Session
from test_client_registry import admin_client, created
from test_identity_cli import invoke

__all__ = ["admin_client"]


def test_client_access_cli_requires_both_confirmations(
    admin_client, seeded_user, db_engine, settings, monkeypatch
):
    from altvia.models import ClientAccessGrant, RoleBinding
    from sqlalchemy import select

    identifier = created(admin_client, seeded_user)
    for command, role in [("grant-client-access", "viewer"), ("revoke-client-access", None)]:
        extra = ["--client-id", identifier] + (["--role", role] if role else [])
        invoke(monkeypatch, settings, command, "employee@example.test", *extra)
        answers = iter(["employee@example.test", identifier])
        monkeypatch.setattr("builtins.input", lambda _, answers=answers: next(answers))
        assert cli.main() == 0
        with Session(db_engine) as db:
            binding = db.scalar(
                select(RoleBinding).where(RoleBinding.client_id == UUID(identifier))
            )
            assert (binding.role_name if binding else None) == role
            assert (db.get(ClientAccessGrant, (seeded_user, UUID(identifier))) is not None) == (
                role is not None
            )


def test_bad_client_confirmation_never_opens_database(settings, monkeypatch):
    invoke(
        monkeypatch,
        settings,
        "grant-client-access",
        "employee@example.test",
        "--client-id",
        str(uuid4()),
        "--role",
        "viewer",
    )
    answers = iter(["employee@example.test", "wrong"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli, "make_engine", lambda _: pytest.fail("Unexpected database access"))
    assert cli.main() == 1
