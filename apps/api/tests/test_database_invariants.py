import pytest
from altvia.models import AuditLog, SessionRecord
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_sessions import login


def test_audit_records_cannot_be_rewritten(client, db_engine):
    assert login(client).status_code == 201
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.execute(text("UPDATE audit_logs SET action = 'forged'"))


def test_session_and_audit_rollback_when_outbox_insert_fails(client, db_engine):
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE outbox_events ADD CONSTRAINT test_reject_event "
                "CHECK (event_type <> 'identity.session_created')"
            )
        )
    try:
        response = login(client)
        assert response.status_code == 503
        assert "set-cookie" not in response.headers
        assert "SQL" not in response.text
        with Session(db_engine) as db:
            assert db.scalar(select(func.count()).select_from(SessionRecord)) == 0
            assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE outbox_events DROP CONSTRAINT test_reject_event"))
