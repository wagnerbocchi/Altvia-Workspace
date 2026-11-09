"""Migration proof runs only against conftest's guarded disposable database."""

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from altvia import management
from altvia.models import Team
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def test_scope_migration_preserves_global_grants_and_refuses_loss(db_engine, seeded_user):
    config = Config("apps/api/alembic.ini")
    head = ScriptDirectory.from_config(config).get_current_head()
    with Session(db_engine) as db, db.begin():
        management.set_platform_admin(db, "employee@example.test", True)
        team = Team(name="Migration proof")
        db.add(team)
        db.flush()
        team_id = team.id

    def version():
        with db_engine.connect() as connection:
            return connection.scalar(text("SELECT version_num FROM alembic_version"))

    def global_grants():
        with db_engine.connect() as connection:
            return connection.execute(
                text("SELECT user_id,role_name,scope_kind FROM role_bindings ORDER BY user_id")
            ).all()

    before = global_grants()
    command.downgrade(config, "b46087000003")
    assert global_grants() == before
    with db_engine.begin() as connection:
        connection.execute(text("INSERT INTO roles(name) VALUES ('viewer') ON CONFLICT DO NOTHING"))
        connection.execute(
            text(
                "INSERT INTO role_bindings(user_id,role_name,scope_kind) "
                "VALUES (:u,'viewer','global')"
            ),
            {"u": seeded_user},
        )
    with pytest.raises(DBAPIError, match="Unsupported legacy global grants"):
        command.upgrade(config, "head")
    assert version() == "b46087000003"
    assert len(global_grants()) == 2
    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM role_bindings WHERE role_name='viewer'"))
    command.upgrade(config, "head")
    assert global_grants() == before

    with Session(db_engine) as db, db.begin():
        management.set_team_role(db, "employee@example.test", team_id, "viewer", True)
    with pytest.raises(DBAPIError, match="Cannot downgrade while scoped grants exist"):
        command.downgrade(config, "b46087000003")
    assert version() == head
    assert len(global_grants()) == 2
    with Session(db_engine) as db, db.begin():
        management.set_team_role(db, "employee@example.test", team_id, "viewer", False)
    command.downgrade(config, "b46087000003")
    assert global_grants() == before
    command.upgrade(config, "head")
    assert global_grants() == before
    command.check(config)
