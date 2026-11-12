"""Real public unsent drafts, independent note authority and protected persistence."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia.activity import consume_event
from altvia.models import OutboxEvent
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in
from test_tickets import setup, ticket

__all__ = ["admin_client"]


def append(client, path, version=1, body="Resposta publica em revisao", key=None):
    return client.post(
        path + "/messages", json={"body_text": body}, headers=preconditions(version, key)
    )


def test_public_draft_persists_plain_text_without_note_grant_or_delivery(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    result = append(admin_client, path, body="  Linha um\n<script>texto literal</script>  ")
    assert result.status_code == 201, result.text
    assert set(result.json()) == {"ticket_id", "message_id"}
    row = admin_client.get(path).json()
    assert row["version"] == 2 and row["can_add_message"] and not row["can_read_notes"]
    assert row["status"] == "new" and row["assignee_id"] is None and row["resolved_at"] is None
    message = admin_client.get(path + "/messages/" + result.json()["message_id"]).json()
    assert message["body_text"] == "Linha um\n<script>texto literal</script>"
    assert message["visibility"] == "public" and message["delivery_status"] == "draft"
    assert message["direction"] == "outbound" and message["ticket_version"] == 2
    assert admin_client.get(path + "/notes").status_code == 403
    with Session(db_engine) as db:
        events = list(
            db.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == UUID(row["id"])))
        )
        assert [e.event_type for e in events].count("ticket.message_drafted") == 1
        assert "texto literal" not in json.dumps([e.payload for e in events])
        event_id = next(e.event_id for e in events if e.event_type == "ticket.message_drafted")
    assert consume_event(db_engine, event_id, datetime.now(UTC))
    activity = admin_client.get(path + "/activity").json()["items"]
    assert any(e["event_type"] == "ticket.message_drafted" for e in activity)


def test_read_and_write_authority_do_not_come_from_platform_or_note_access(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    assert append(admin_client, path).status_code == 201
    for account in ("agent@example.test", "viewer@example.test"):
        sign_in(admin_client, account)
        assert admin_client.get(path + "/messages").status_code == 200
        assert not admin_client.get(path).json()["can_add_message"]
        assert append(admin_client, path, version=2).status_code == 403
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path + "/messages").status_code == 404
    assert append(admin_client, path, version=2).status_code == 404
    sign_in(admin_client, "employee@example.test")
    assigned = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    sign_in(admin_client, "agent@example.test")
    assert append(admin_client, assigned).status_code == 201
    assert admin_client.get(assigned + "/notes").status_code == 403


def test_replay_preserves_receipt_after_archive_and_refuses_current_scope_loss(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    key = uuid4().hex
    first = append(admin_client, path, key=key)
    assert first.status_code == 201
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE clients SET active=false WHERE id=:id"), {"id": UUID(refs["client_id"])}
        )
    replay = append(admin_client, path, key=key)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert append(admin_client, path, version=2).status_code == 409
    with db_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM client_access_grants WHERE user_id=:actor AND client_id=:client"),
            {"actor": seeded_user, "client": UUID(refs["client_id"])},
        )
    assert append(admin_client, path, key=key).status_code == 404
    assert admin_client.get(path + "/messages").status_code == 404


def test_pagination_scopes_and_exact_parent_lookup(admin_client, db_engine, seeded_user):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    ids = []
    for version in (1, 2, 3):
        response = append(admin_client, path, version=version, body=f"Publica {version}")
        assert response.status_code == 201
        ids.append(response.json()["message_id"])
    page = admin_client.get(path + "/messages?limit=2").json()
    assert [row["id"] for row in page["items"]] == ids[:2] and page["next_cursor"]
    tail = admin_client.get(
        path + "/messages", params={"limit": 2, "cursor": page["next_cursor"]}
    ).json()
    assert [row["id"] for row in tail["items"]] == ids[2:] and tail["next_cursor"] is None
    other = ticket(admin_client, refs)
    assert admin_client.get(other + "/messages/" + ids[0]).status_code == 404
    assert (
        admin_client.get(other + "/messages", params={"cursor": page["next_cursor"]}).status_code
        == 422
    )
    assert admin_client.get(path + "/messages?limit=2&limit=3").status_code == 422
    assert admin_client.get(path + "/messages?unexpected=1").status_code == 422


@pytest.mark.parametrize("body", ["", " \n\t", "x" * 10001, "bad\x00text"])
def test_invalid_draft_does_not_advance_ticket(admin_client, db_engine, seeded_user, body):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    assert append(admin_client, path, body=body).status_code == 422
    assert admin_client.get(path).json()["version"] == 1


def test_protocol_and_private_shape_are_enforced(admin_client, db_engine, seeded_user):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    assert admin_client.post(path + "/messages", json={"body_text": "review"}).status_code == 428
    assert (
        admin_client.post(
            path + "/messages",
            json={"body_text": "review", "visibility": "internal"},
            headers=preconditions(),
        ).status_code
        == 422
    )
    assert append(admin_client, path, version=2).status_code == 409


def test_atomic_event_failure_and_exhaustion_leave_no_draft(admin_client, db_engine, seeded_user):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE outbox_events ADD CONSTRAINT test_reject_message "
                "CHECK(event_type<>'ticket.message_drafted')"
            )
        )
    try:
        assert append(admin_client, path).status_code == 503
        assert admin_client.get(path).json()["version"] == 1
        assert admin_client.get(path + "/messages").json()["items"] == []
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE outbox_events DROP CONSTRAINT test_reject_message")
            )
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE tickets SET version=2147483647"))
    assert append(admin_client, path, version=2147483647).status_code == 409


def test_concurrent_retries_create_one_draft(admin_client, db_engine, seeded_user):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    cookies = dict(admin_client.cookies)
    key = uuid4().hex
    headers = preconditions(1, key)
    headers["X-CSRF-Token"] = admin_client.headers["X-CSRF-Token"]

    def write(_):
        with TestClient(
            admin_client.app,
            base_url=str(admin_client.base_url),
            cookies=cookies,
            headers=dict(admin_client.headers),
        ) as isolated:
            return isolated.post(
                path + "/messages", json={"body_text": "One draft"}, headers=headers
            )

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(write, range(3)))
    assert sorted(r.status_code for r in results) == [200, 200, 201]
    assert len({r.json()["message_id"] for r in results}) == 1


def test_sql_immutability_and_guarded_downgrade(admin_client, db_engine, seeded_user):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    assert append(admin_client, path).status_code == 201
    for sql in ("UPDATE ticket_messages SET body_text='rewrite'", "DELETE FROM ticket_messages"):
        with pytest.raises(DBAPIError), db_engine.begin() as connection:
            connection.execute(text(sql))
    with pytest.raises(DBAPIError):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000020")


def test_message_empty_migration_roundtrip_and_history_guard(db_engine, seeded_user):
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000020")
    command.upgrade(config, "head")
    command.check(config)
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO audit_logs(id,action,occurred_at,correlation_id,details) "
                "VALUES(gen_random_uuid(),'ticket.message_drafted',now(),'test','{}')"
            )
        )
    with pytest.raises(DBAPIError):
        command.downgrade(config, "b46087000020")


@pytest.mark.parametrize("change", ["body", "note", "missing"])
def test_message_metadata_rejects_body_private_identifier_or_missing_id(
    admin_client, db_engine, seeded_user, change
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    assert append(admin_client, path).status_code == 201
    with Session(db_engine) as db, db.begin():
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "ticket.message_drafted")
        )
        payload = dict(event.payload)
        if change == "missing":
            payload.pop("message_id")
        else:
            payload["body_text" if change == "body" else "note_id"] = (
                "private" if change == "body" else str(uuid4())
            )
        event.payload = payload
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"


def test_api_has_only_append_read_and_worker_has_no_message_privilege(
    admin_client, db_engine, seeded_user
):
    from altvia.provision import provision_runtime
    from test_runtime_provision import runtime_url

    refs = setup(admin_client, db_engine, seeded_user)
    assert append(admin_client, ticket(admin_client, refs)).status_code == 201
    runtime = runtime_url(db_engine)
    worker = runtime.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        runtime.render_as_string(hide_password=False),
        worker.render_as_string(hide_password=False),
    )
    with db_engine.connect() as connection:
        for role, allowed in (("altvia_app", {"SELECT", "INSERT"}), ("altvia_worker", set())):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                actual = connection.scalar(
                    text("SELECT has_table_privilege(:role,'ticket_messages',:privilege)"),
                    {"role": role, "privilege": privilege},
                )
                assert actual == (privilege in allowed)
