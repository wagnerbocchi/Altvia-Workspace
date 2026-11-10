from uuid import UUID

from altvia import cli
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_identity_cli import invoke
from test_project_registry import admin_client, project
from test_team_api import created as create_team

__all__ = ["admin_client"]


def test_project_access_cli_changes_both_records_after_two_confirmations(
    admin_client, seeded_user, db_engine, settings, monkeypatch
):
    from altvia.models import ProjectMember, RoleBinding

    team = create_team(admin_client)["id"]
    receipt = project(admin_client, seeded_user, team)
    assert receipt.status_code == 201, receipt.text
    identifier = receipt.json()["project_id"]
    for command, role in [("grant-project-access", "viewer"), ("revoke-project-access", None)]:
        extra = ["--project-id", identifier] + (["--role", role] if role else [])
        invoke(monkeypatch, settings, command, "employee@example.test", *extra)
        answers = iter(["employee@example.test", identifier])
        monkeypatch.setattr("builtins.input", lambda _, answers=answers: next(answers))
        assert cli.main() == 0
        with Session(db_engine) as db:
            binding = db.scalar(
                select(RoleBinding).where(RoleBinding.project_id == UUID(identifier))
            )
            assert (binding.role_name if binding else None) == role
            assert (db.get(ProjectMember, (UUID(identifier), seeded_user)) is not None) == (
                role is not None
            )
