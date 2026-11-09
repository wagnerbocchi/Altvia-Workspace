import pytest
from alembic import command
from alembic.config import Config
from altvia import management
from conftest import TEST_PASSWORD
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def test_activity_migration_preserves_old_events_and_refuses_projected_data_loss(
    db_engine, seeded_user
):
    from datetime import UTC, datetime

    from altvia.activity import consume_event

    config = Config("apps/api/alembic.ini")
    with Session(db_engine) as db, db.begin():
        management.create_user(db, "migration-worker@example.test", "Worker", TEST_PASSWORD)
    with db_engine.connect() as connection:
        before = connection.execute(text("SELECT event_id,payload FROM outbox_events")).all()
    command.downgrade(config, "b46087000004")
    command.upgrade(config, "head")
    with db_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT event_id,payload FROM outbox_events")).all() == before
        )
    assert consume_event(db_engine, before[0].event_id, datetime.now(UTC))
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable activity exists"):
        command.downgrade(config, "b46087000004")
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM activity_events")) == 1
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "b46087000005"
    command.check(config)
