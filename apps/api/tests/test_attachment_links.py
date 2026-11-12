"""Concrete immutable content links over actual PostgreSQL and private TLS S3."""

from uuid import UUID, uuid4

import pytest
from file_core_support import file_services
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_attachments import controlled_ready, upload
from test_team_api import admin_client, preconditions
from test_tickets import setup, ticket

__all__ = ["admin_client", "file_services"]
pytestmark = pytest.mark.usefixtures("file_services")


def ready(
    client,
    engine,
    path,
    tmp_path,
    *,
    purpose="public",
    filename="proof.txt",
    content=b"file\n",
    version=1,
):
    result = upload(
        client, path, purpose=purpose, filename=filename, content=content, version=version
    )
    assert result.status_code == 201, result.text
    identifier = result.json()["attachment_id"]
    scan_path = tmp_path / uuid4().hex
    scan_path.mkdir()
    controlled_ready(client, engine, UUID(identifier), scan_path)
    return identifier


def post(client, path, ids, *, version=1, key=None, kind="messages"):
    return client.post(
        path + "/" + kind,
        json={"body_text": "Linked text", "attachment_ids": ids},
        headers=preconditions(version, key),
    )


def test_ordered_message_links_and_legacy_omission(admin_client, db_engine, seeded_user, tmp_path):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    ids = [
        ready(admin_client, db_engine, path, tmp_path, filename=n)
        for n in ["first.txt", "second.log"]
    ]
    key = uuid4().hex
    response = post(admin_client, path, ids[::-1], key=key)
    assert response.status_code == 201, response.text
    receipt = response.json()
    assert set(receipt) == {"ticket_id", "message_id"}
    result = admin_client.get(path + "/messages/" + receipt["message_id"]).json()
    assert result["attachment_count"] == 2
    assert [r["id"] for r in result["attachments"]] == ids[::-1]
    assert [r["filename"] for r in result["attachments"]] == ["second.log", "first.txt"]
    assert all(set(r) == {"id", "filename", "media_type", "bytes"} for r in result["attachments"])
    assert post(admin_client, path, ids[::-1], key=key).json() == receipt
    assert post(admin_client, path, ids, key=key).status_code == 409
    legacy_key = uuid4().hex
    legacy_body = {"body_text": "Old client"}
    first = admin_client.post(
        path + "/messages", json=legacy_body, headers=preconditions(2, legacy_key)
    )
    assert first.status_code == 201
    assert (
        admin_client.post(
            path + "/messages", json=legacy_body, headers=preconditions(2, legacy_key)
        ).status_code
        == 200
    )
    assert (
        admin_client.post(
            path + "/messages",
            json={**legacy_body, "attachment_ids": []},
            headers=preconditions(2, legacy_key),
        ).status_code
        == 409
    )
    legacy = admin_client.get(path + "/messages/" + first.json()["message_id"]).json()
    assert legacy["attachment_count"] == 0 and legacy["attachments"] == []
    with db_engine.connect() as db:
        event = db.scalar(
            text(
                "SELECT payload FROM outbox_events WHERE "
                "event_type='ticket.message_drafted' AND "
                "payload->>'message_id'=:id"
            ),
            {"id": receipt["message_id"]},
        )
    assert set(event) == {
        "actor_id",
        "actor_kind",
        "ticket_id",
        "client_id",
        "queue_id",
        "message_id",
    }


def test_link_guards_and_sql_count_immutability(admin_client, db_engine, seeded_user, tmp_path):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    identifier = ready(admin_client, db_engine, path, tmp_path)
    pending = upload(admin_client, path).json()["attachment_id"]
    other = ticket(admin_client, refs)
    assert post(admin_client, other, [identifier]).status_code == 404
    assert post(admin_client, path, [str(uuid4())]).status_code == 404
    assert post(admin_client, path, [pending]).status_code == 409
    for ids in [[identifier, identifier], [str(uuid4()) for _ in range(21)], None]:
        assert post(admin_client, path, ids).status_code == 422
    result = post(admin_client, path, [identifier])
    assert result.status_code == 201, result.text
    message = result.json()["message_id"]
    for statement in [
        "UPDATE ticket_messages SET attachment_count=0 WHERE id=:message",
        "DELETE FROM ticket_message_attachments WHERE message_id=:message",
        "UPDATE ticket_message_attachments SET position=1 WHERE message_id=:message",
        "INSERT INTO "
        "ticket_message_attachments(message_id,ticket_id,attachm"
        "ent_id,purpose,position) SELECT "
        "id,ticket_id,:pending,'public',1 FROM ticket_messages "
        "WHERE id=:message",
        "INSERT INTO "
        "ticket_messages(id,ticket_id,author_id,body_text,ticket"
        "_version,attachment_count) SELECT "
        ":new,ticket_id,author_id,'missing',99,1 FROM "
        "ticket_messages WHERE id=:message",
    ]:
        with pytest.raises(DBAPIError), db_engine.begin() as db:
            db.execute(
                text(statement),
                {"message": UUID(message), "pending": UUID(pending), "new": uuid4()},
            )


def test_note_writer_and_work_contributor_keep_distinct_authority(
    admin_client, db_engine, seeded_user, tmp_path
):
    from test_team_api import sign_in
    from test_ticket_notes import configure
    from test_work_items import create_work, setup_project

    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    configure(admin_client, refs, seeded_user, "write", role="agent")
    identifier = ready(admin_client, db_engine, path, tmp_path, purpose="note")
    assert post(admin_client, path, [identifier]).status_code == 403
    added = post(admin_client, path, [identifier], kind="notes")
    assert added.status_code == 201, added.text
    note = admin_client.get(path + "/notes/" + added.json()["note_id"]).json()
    assert note["attachment_count"] == 1 and note["attachments"][0]["id"] == identifier
    configure(admin_client, refs, seeded_user, "none", role="agent")
    assert admin_client.get(path + "/notes").status_code == 403
    assert admin_client.get("/api/v1/attachments/" + identifier).status_code == 404
    sign_in(admin_client, "admin@example.test")
    project = setup_project(admin_client, seeded_user)
    work = "/api/v1/work-items/" + create_work(admin_client, project).json()["work_item_id"]
    from altvia.project_registry import set_project_access
    from sqlalchemy.orm import Session

    with Session(db_engine) as db, db.begin():
        set_project_access(db, "employee@example.test", UUID(project), "agent")
    sign_in(admin_client, "employee@example.test")
    assert (
        admin_client.patch(
            work, json={"title": "No owner right"}, headers=preconditions()
        ).status_code
        == 403
    )
    work_id = ready(admin_client, db_engine, work, tmp_path, purpose="work")
    result = admin_client.post(
        work + "/comments",
        json={"body": "Work file", "attachment_ids": [work_id]},
        headers=preconditions(),
    )
    assert result.status_code == 201, result.text
    assert result.json()["attachment_count"] == 1
    assert (
        admin_client.get(work + "/comments").json()["items"][0]["attachments"][0]["id"] == work_id
    )


def test_link_event_failure_rolls_back_every_effect(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch
):
    from altvia import ticket_api

    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    identifier = ready(admin_client, db_engine, path, tmp_path)

    def failed(*args, **kwargs):
        raise RuntimeError("controlled_atomic_failure")

    monkeypatch.setattr(ticket_api, "_event", failed)
    with pytest.raises(RuntimeError, match="controlled_atomic_failure"):
        post(admin_client, path, [identifier])
    assert admin_client.get(path).json()["version"] == 1
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM ticket_messages")) == 0
        assert db.scalar(text("SELECT count(*) FROM ticket_message_attachments")) == 0
        assert (
            db.scalar(
                text("SELECT count(*) FROM idempotency_records WHERE route LIKE 'ticket-message:%'")
            )
            == 0
        )


def test_request_purpose_schemas_are_owner_specific(admin_client):
    document = admin_client.get("/openapi.json").json()
    for path, allowed in [
        ("/api/v1/tickets/{identifier}/attachments", ["public", "note"]),
        ("/api/v1/work-items/{identifier}/attachments", ["work"]),
    ]:
        for method in ["post", "get"]:
            schema = next(
                p["schema"]
                for p in document["paths"][path][method]["parameters"]
                if p["name"] == "purpose"
            )
            assert schema.get("enum", [schema.get("const")]) == allowed


def test_restricted_runtime_can_create_links_and_worker_cannot_read_them(
    admin_client, db_engine, seeded_user, settings, tmp_path
):
    import secrets

    from altvia import provision
    from altvia.main import create_app
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from test_team_api import sign_in

    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    identifier = ready(admin_client, db_engine, path, tmp_path)
    app_url = db_engine.url.set(username="altvia_app", password=secrets.token_urlsafe(24))
    worker_url = db_engine.url.set(username="altvia_worker", password=secrets.token_urlsafe(24))
    provision.provision_runtime(
        db_engine,
        app_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    runtime_settings = settings.model_copy(
        update={
            "database_url": settings.database_url.__class__(
                app_url.render_as_string(hide_password=False)
            )
        }
    )
    with TestClient(
        create_app(runtime_settings),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        sign_in(client, "employee@example.test")
        result = post(client, path, [identifier])
        assert result.status_code == 201, result.text
        assert (
            client.get(path + "/messages/" + result.json()["message_id"]).json()["attachment_count"]
            == 1
        )
    worker = create_engine(worker_url, hide_parameters=True)
    try:
        for table in [
            "ticket_message_attachments",
            "ticket_note_attachments",
            "work_comment_attachments",
        ]:
            with pytest.raises(DBAPIError), worker.begin() as db:
                db.execute(text("SELECT * FROM " + table))
    finally:
        worker.dispose()


def test_migration_roundtrip_with_empty_new_state(db_engine, seeded_user):
    from alembic import command
    from alembic.config import Config

    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000025")
    command.upgrade(config, "head")
    command.check(config)


def test_contraction_refuses_immutable_link_history(admin_client, db_engine, seeded_user, tmp_path):
    from alembic import command
    from alembic.config import Config

    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    identifier = ready(admin_client, db_engine, path, tmp_path)
    assert post(admin_client, path, [identifier]).status_code == 201
    with pytest.raises(DBAPIError, match="Cannot contract immutable file content/history"):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000025")
    assert (
        admin_client.get(path + "/messages").json()["items"][0]["attachments"][0]["id"]
        == identifier
    )


def test_reverse_selection_concurrency_commits_one_immutable_order(
    admin_client, db_engine, seeded_user, tmp_path
):
    from concurrent.futures import ThreadPoolExecutor

    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    ids = [
        ready(admin_client, db_engine, path, tmp_path, filename=f"file-{i}.txt") for i in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(post, admin_client, path, selection) for selection in [ids, ids[::-1]]]
        results = [call.result(timeout=10) for call in calls]
    assert sorted(result.status_code for result in results) == [201, 409]
    winner = next(result for result in results if result.status_code == 201)
    row = admin_client.get(path + "/messages/" + winner.json()["message_id"]).json()
    assert [file["id"] for file in row["attachments"]] in [ids, ids[::-1]]
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM ticket_messages")) == 1
        assert db.scalar(text("SELECT count(*) FROM ticket_message_attachments")) == 2
