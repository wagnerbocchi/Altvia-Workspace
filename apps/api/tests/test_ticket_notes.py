"""Real private-note authority, persistence, protected replay and privacy boundaries."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia import identity
from altvia.models import (
    ActivityEvent,
    ClientAccessGrant,
    IdempotencyRecord,
    OutboxEvent,
    RoleBinding,
    User,
)
from fastapi.testclient import TestClient
from sla_migration_support import pre_sla_ticket
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in
from test_tickets import setup, ticket, transition

__all__ = ["admin_client"]


def configure(client, refs, user, level, role="operations_manager"):
    sign_in(client, "admin@example.test")
    route = "/api/v1/ticket-queues/" + refs["queue_id"]
    version = client.get(route).json()["version"]
    response = client.patch(
        route + "/members/" + str(user),
        json={"role_name": role, "note_access": level},
        headers=preconditions(version),
    )
    assert response.status_code == 204, response.text
    sign_in(client, "employee@example.test")
    return response


def prepared(client, engine, employee):
    refs = setup(client, engine, employee)
    configure(client, refs, employee, "write")
    return refs, ticket(client, refs)


def append(client, path, version=1, body="Nota privada de validacao", key=None):
    return client.post(
        path + "/notes", json={"body_text": body}, headers=preconditions(version, key)
    )


def test_note_default_denial_includes_queue_manager_agent_viewer_and_platform(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    for email in ["employee@example.test", "agent@example.test", "viewer@example.test"]:
        sign_in(admin_client, email)
        row = admin_client.get(path).json()
        assert row.get("can_read_notes") is False and row.get("can_add_note") is False
        assert admin_client.get(path + "/notes").status_code == 403
        assert append(admin_client, path).status_code == 403
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path + "/notes").status_code == 404
    assert append(admin_client, path).status_code == 404


def test_notes_explicit_permission_persist_literal_text_and_immutable_receipt(
    admin_client, db_engine, seeded_user
):
    refs, path = prepared(admin_client, db_engine, seeded_user)
    key = uuid4().hex
    response = append(admin_client, path, body="  Linha um\n<script>texto</script>  ", key=key)
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"ticket_id", "note_id"}
    note_path = path + "/notes/" + response.json()["note_id"]
    note = admin_client.get(note_path).json()
    assert note["body_text"] == "Linha um\n<script>texto</script>"
    assert note["author_id"] == str(seeded_user) and note["visibility"] == "internal"
    assert note["ticket_version"] == 2
    replay = append(admin_client, path, body="  Linha um\n<script>texto</script>  ", key=key)
    assert replay.status_code == 200 and replay.json() == response.json()
    row = admin_client.get(path).json()
    assert row["version"] == 2 and row["status"] == "new"
    assert row["resolved_at"] is None and row["closed_at"] is None
    assert row["can_read_notes"] and row["can_add_note"]
    assert append(admin_client, path, 1).status_code == 409
    assert append(admin_client, path, 2, body=note["body_text"]).status_code == 201
    assert len(admin_client.get(path + "/notes").json()["items"]) == 2
    with Session(db_engine) as db:
        from altvia.models import TicketNote

        persisted = db.get(TicketNote, UUID(response.json()["note_id"]))
        assert persisted.ticket_id == UUID(response.json()["ticket_id"])
        assert persisted.body_text == note["body_text"]


def test_note_read_tier_and_unassigned_writer_require_independent_current_grants(
    admin_client, db_engine, seeded_user
):
    refs, path = prepared(admin_client, db_engine, seeded_user)
    receipt = append(admin_client, path).json()
    configure(admin_client, refs, refs["agent_id"], "read", "agent")
    sign_in(admin_client, "agent@example.test")
    row = admin_client.get(path).json()
    assert row["assignee_id"] is None and row["can_read_notes"] and not row["can_add_note"]
    assert admin_client.get(path + "/notes/" + receipt["note_id"]).status_code == 200
    assert append(admin_client, path, 2).status_code == 403
    configure(admin_client, refs, refs["agent_id"], "write", "agent")
    sign_in(admin_client, "agent@example.test")
    assert append(admin_client, path, 2).status_code == 201
    with Session(db_engine) as db, db.begin():
        db.delete(db.get(ClientAccessGrant, (UUID(refs["agent_id"]), UUID(refs["client_id"]))))
    assert admin_client.get(path + "/notes").status_code == 404
    assert append(admin_client, path, 3).status_code == 404


def test_note_ids_cannot_resolve_under_other_ticket_or_hidden_queue(
    admin_client, db_engine, seeded_user
):
    refs, path = prepared(admin_client, db_engine, seeded_user)
    receipt = append(admin_client, path).json()
    other = ticket(admin_client, refs, subject="Outro chamado")
    assert admin_client.get(other + "/notes/" + receipt["note_id"]).status_code == 404
    assert admin_client.get(path + "/notes/" + str(uuid4())).status_code == 404
    with Session(db_engine) as db, db.begin():
        binding = db.scalar(
            select(RoleBinding).where(
                RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "queue"
            )
        )
        db.delete(binding)
    assert admin_client.get(path + "/notes/" + receipt["note_id"]).status_code == 404
    assert append(admin_client, path, 2).status_code == 404


def test_note_private_activity_is_filtered_before_paging_and_text_stays_out_of_fts(
    admin_client, db_engine, seeded_user
):
    from altvia.activity import consume_event

    refs, path = prepared(admin_client, db_engine, seeded_user)
    receipt = append(admin_client, path, body="Segredointernoquarentena").json()
    assert transition(admin_client, path, 2, "open").status_code == 200
    assert append(admin_client, path, 3, body="Outra nota privada").status_code == 201
    with Session(db_engine) as db:
        events = list(
            db.scalars(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == UUID(receipt["ticket_id"]))
            )
        )
        assert not any("Segredointernoquarentena" in str(event.payload) for event in events)
        assert not any(
            "mail" in event.event_type or "outbound" in event.event_type for event in events
        )
    for event in events:
        assert consume_event(db_engine, event.event_id, datetime.now(UTC))
    writer_events = admin_client.get(path + "/activity").json()["items"]
    assert sum(row["event_type"] == "ticket.note_added" for row in writer_events) == 2
    assert admin_client.get("/api/v1/tickets?q=Segredointernoquarentena").json()["items"] == []
    sign_in(admin_client, "viewer@example.test")
    first = admin_client.get(path + "/activity?limit=1").json()
    assert len(first["items"]) == 1 and first["items"][0]["event_type"] == "ticket.status_changed"
    second = admin_client.get(
        path + "/activity", params={"cursor": first["next_cursor"], "limit": 1}
    ).json()
    assert second["items"][0]["event_type"] == "ticket.created" and second["next_cursor"] is None
    assert receipt["note_id"] not in json.dumps([first, second, admin_client.get(path).json()])


def test_note_paging_uses_ordered_ticket_versions_and_actor_parent_cursor_binding(
    admin_client, db_engine, seeded_user
):
    refs, path = prepared(admin_client, db_engine, seeded_user)
    assert append(admin_client, path).status_code == 201
    assert transition(admin_client, path, 2, "open").status_code == 200
    assert append(admin_client, path, 3).status_code == 201
    page = admin_client.get(path + "/notes?limit=1").json()
    assert page["items"][0]["ticket_version"] == 2 and page["next_cursor"]
    second = admin_client.get(path + "/notes", params={"cursor": page["next_cursor"]}).json()
    assert [row["ticket_version"] for row in second["items"]] == [4]
    other = ticket(admin_client, refs)
    assert (
        admin_client.get(other + "/notes", params={"cursor": page["next_cursor"]}).status_code
        == 422
    )
    for query in ["?limit=1&limit=2", "?unexpected=x", "?cursor=bad", "?limit=0"]:
        assert admin_client.get(path + "/notes" + query).status_code == 422
    configure(admin_client, refs, refs["agent_id"], "read", "agent")
    sign_in(admin_client, "agent@example.test")
    assert (
        admin_client.get(path + "/notes", params={"cursor": page["next_cursor"]}).status_code == 422
    )


def test_note_strict_write_protocol_and_body_boundaries(
    admin_client, db_engine, seeded_user, settings
):
    _, path = prepared(admin_client, db_engine, seeded_user)
    for body in [None, "", "\t\u00a0", "bad\0text", "x" * 10001]:
        assert (
            admin_client.post(
                path + "/notes", json={"body_text": body}, headers=preconditions()
            ).status_code
            == 422
        )
    for extra in [
        {"visibility": "public"},
        {"author_id": str(seeded_user)},
        {"recipient": "other@example.test"},
    ]:
        assert (
            admin_client.post(
                path + "/notes", json={"body_text": "Texto", **extra}, headers=preconditions()
            ).status_code
            == 422
        )
    with TestClient(admin_client.app, base_url=settings.public_origin) as client:
        client.cookies.update(dict(admin_client.cookies))
        valid = {
            **preconditions(),
            "Origin": settings.public_origin,
            "X-CSRF-Token": admin_client.headers["X-CSRF-Token"],
        }
        for header, status in [
            ("Origin", 403),
            ("X-CSRF-Token", 403),
            ("If-Match", 428),
            ("Idempotency-Key", 428),
        ]:
            headers = {key: value for key, value in valid.items() if key != header}
            assert (
                client.post(
                    path + "/notes", json={"body_text": "Texto"}, headers=headers
                ).status_code
                == status
            )
        for header in ["If-Match", "Idempotency-Key"]:
            assert (
                client.post(
                    path + "/notes",
                    json={"body_text": "Texto"},
                    headers={**valid, header: "invalid value"},
                ).status_code
                == 422
            )
    assert append(admin_client, path, body="𠮷" * 10000).status_code == 201


def test_note_receipt_rechecks_revocation_and_survives_archive(
    admin_client, db_engine, seeded_user
):
    refs, path = prepared(admin_client, db_engine, seeded_user)
    key = uuid4().hex
    first = append(admin_client, path, key=key)
    sign_in(admin_client, "admin@example.test")
    queue = "/api/v1/ticket-queues/" + refs["queue_id"]
    version = admin_client.get(queue).json()["version"]
    assert (
        admin_client.patch(
            queue, json={"active": False}, headers=preconditions(version)
        ).status_code
        == 200
    )
    sign_in(admin_client, "employee@example.test")
    assert append(admin_client, path, key=key).json() == first.json()
    assert append(admin_client, path, 2).status_code == 409
    assert admin_client.get(path + "/notes").status_code == 200
    with Session(db_engine) as db, db.begin():
        binding = db.scalar(
            select(RoleBinding).where(
                RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "queue"
            )
        )
        binding.note_access = "read"
    assert append(admin_client, path, key=key).status_code == 403
    with Session(db_engine) as db, db.begin():
        binding = db.scalar(
            select(RoleBinding).where(
                RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "queue"
            )
        )
        binding.note_access = "none"
    assert admin_client.get(path + "/notes").status_code == 403


def test_note_failures_roll_back_and_version_exhaustion_is_safe(
    admin_client, db_engine, seeded_user, monkeypatch
):
    _, path = prepared(admin_client, db_engine, seeded_user)
    original = identity.record_event

    def fail(db, actor, resource, event, *args, **kwargs):
        if event == "ticket.note_added":
            raise RuntimeError("injected note event failure")
        return original(db, actor, resource, event, *args, **kwargs)

    monkeypatch.setattr(identity, "record_event", fail)
    with pytest.raises(RuntimeError, match="injected note"):
        append(admin_client, path)
    monkeypatch.setattr(identity, "record_event", original)
    assert admin_client.get(path + "/notes").json()["items"] == []
    assert admin_client.get(path).json()["version"] == 1
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE tickets SET version=2147483647"))
    assert append(admin_client, path, 2147483647).status_code == 409
    assert admin_client.get(path + "/notes").json()["items"] == []


@pytest.mark.parametrize("shared_key", [True, False])
def test_note_concurrent_writes_have_one_effect(
    admin_client, db_engine, seeded_user, settings, shared_key
):
    _, path = prepared(admin_client, db_engine, seeded_user)
    cookies = dict(admin_client.cookies)
    headers = {
        "Origin": settings.public_origin,
        "X-CSRF-Token": admin_client.headers["X-CSRF-Token"],
    }
    key = uuid4().hex if shared_key else None

    def send(_):
        with TestClient(
            admin_client.app, base_url=settings.public_origin, headers=headers
        ) as writer:
            writer.cookies.update(cookies)
            return append(writer, path, key=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, range(2)))
    assert sorted(response.status_code for response in responses) == (
        [200, 201] if shared_key else [201, 409]
    )
    if shared_key:
        assert responses[0].json() == responses[1].json()
    assert admin_client.get(path).json()["version"] == 2
    assert len(admin_client.get(path + "/notes").json()["items"]) == 1


def test_note_permission_legacy_receipt_does_not_restore_grant(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    sign_in(admin_client, "admin@example.test")
    route = "/api/v1/ticket-queues/" + refs["queue_id"] + "/members"
    key = uuid4().hex
    body = {"email": "agent@example.test", "role_name": "agent"}
    now = datetime.now(UTC)
    with Session(db_engine) as db, db.begin():
        admin = db.scalar(select(User).where(User.email_normalized == "admin@example.test"))
        db.add(
            IdempotencyRecord(
                actor_id=admin.id,
                route=route,
                key=key,
                request_hash=hashlib.sha256(
                    json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                status_code=201,
                result={"queue_id": refs["queue_id"], "user_id": refs["agent_id"]},
                created_at=now,
                expires_at=now + timedelta(days=7),
            )
        )
    replay = admin_client.post(route, json=body, headers=preconditions(1, key))
    assert replay.status_code == 200 and replay.json()["user_id"] == refs["agent_id"]
    configure(admin_client, refs, refs["agent_id"], "write", "agent")
    configure(admin_client, refs, refs["agent_id"], "none", "agent")
    sign_in(admin_client, "admin@example.test")
    assert admin_client.post(route, json=body, headers=preconditions(1, key)).status_code == 200
    with Session(db_engine) as db:
        binding = db.scalar(
            select(RoleBinding).where(RoleBinding.user_id == UUID(refs["agent_id"]))
        )
        assert binding.note_access == "none"


def test_note_permission_downgrade_revokes_sessions_and_old_role_only_writes_preserve_grant(
    admin_client, db_engine, seeded_user
):
    refs, path = prepared(admin_client, db_engine, seeded_user)
    configure(admin_client, refs, refs["agent_id"], "write", "agent")
    with TestClient(
        admin_client.app,
        base_url=str(admin_client.base_url),
        headers={"Origin": str(admin_client.base_url).rstrip("/")},
    ) as agent:
        sign_in(agent, "agent@example.test")
        sign_in(admin_client, "admin@example.test")
        parent = "/api/v1/ticket-queues/" + refs["queue_id"]
        route = parent + "/members/" + refs["agent_id"]
        version = admin_client.get(parent).json()["version"]
        assert (
            admin_client.patch(
                route, json={"role_name": "agent"}, headers=preconditions(version)
            ).status_code
            == 204
        )
        assert agent.get(path + "/notes").status_code == 200
        assert (
            admin_client.patch(
                route, json={"role_name": "viewer"}, headers=preconditions(version)
            ).status_code
            == 204
        )
        assert agent.get(path).status_code == 401
        sign_in(agent, "agent@example.test")
        assert agent.get(path).status_code == 200 and agent.get(path + "/notes").status_code == 403
    with Session(db_engine) as db:
        binding = db.scalar(
            select(RoleBinding).where(RoleBinding.user_id == UUID(refs["agent_id"]))
        )
        assert binding.role_name == "viewer" and binding.note_access == "none"


def test_note_sql_immutability_constraints_and_guarded_downgrade(
    admin_client, db_engine, seeded_user
):
    _, path = prepared(admin_client, db_engine, seeded_user)
    assert append(admin_client, path).status_code == 201
    pre_sla_ticket(db_engine, path)
    for statement in ["UPDATE ticket_notes SET body_text='rewrite'", "DELETE FROM ticket_notes"]:
        with pytest.raises(DBAPIError, match="append-only"), db_engine.begin() as connection:
            connection.execute(text(statement))
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable note"):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000015")
    command.check(Config("apps/api/alembic.ini"))


def test_note_actual_api_runtime_and_worker_privilege_boundary(
    admin_client, db_engine, seeded_user, settings
):
    from altvia.main import create_app
    from altvia.provision import provision_runtime
    from sqlalchemy import create_engine
    from test_runtime_provision import runtime_url

    _, path = prepared(admin_client, db_engine, seeded_user)
    runtime = runtime_url(db_engine)
    worker = runtime.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        runtime.render_as_string(hide_password=False),
        worker.render_as_string(hide_password=False),
    )
    config = settings.model_copy(
        update={
            "database_url": settings.database_url.__class__(
                runtime.render_as_string(hide_password=False)
            )
        }
    )
    with TestClient(
        create_app(config),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        sign_in(client, "employee@example.test")
        assert append(client, path).status_code == 201
        assert len(client.get(path + "/notes").json()["items"]) == 1
    for credential, statements in [
        (runtime, ["UPDATE ticket_notes SET body_text='rewrite'", "DELETE FROM ticket_notes"]),
        (worker, ["SELECT * FROM ticket_notes"]),
    ]:
        engine = create_engine(credential, hide_parameters=True)
        try:
            for statement in statements:
                with pytest.raises(DBAPIError), engine.begin() as connection:
                    connection.execute(text(statement))
        finally:
            engine.dispose()


def test_note_permission_reduction_remains_available_on_archived_queue_and_disabled_target(
    admin_client, db_engine, seeded_user
):
    refs, _ = prepared(admin_client, db_engine, seeded_user)
    configure(admin_client, refs, refs["agent_id"], "write", "agent")
    sign_in(admin_client, "admin@example.test")
    parent = "/api/v1/ticket-queues/" + refs["queue_id"]
    version = admin_client.get(parent).json()["version"]
    assert (
        admin_client.patch(
            parent, json={"active": False}, headers=preconditions(version)
        ).status_code
        == 200
    )
    with Session(db_engine) as db, db.begin():
        db.get(User, UUID(refs["agent_id"])).active = False
    for offset, level in [(1, "read"), (2, "none")]:
        response = admin_client.patch(
            parent + "/members/" + refs["agent_id"],
            json={"role_name": "agent", "note_access": level},
            headers=preconditions(version + offset),
        )
        assert response.status_code == 204, response.text


@pytest.mark.parametrize(
    "role,level",
    [("viewer", "read"), ("viewer", "write"), ("agent", None), ("agent", True), ("agent", "all")],
)
def test_note_permission_strict_fields_reject_invalid_or_viewer_grants(
    admin_client, db_engine, seeded_user, role, level
):
    refs = setup(admin_client, db_engine, seeded_user)
    sign_in(admin_client, "admin@example.test")
    parent = "/api/v1/ticket-queues/" + refs["queue_id"]
    assert (
        admin_client.patch(
            parent + "/members/" + refs["agent_id"],
            json={"role_name": role, "note_access": level},
            headers=preconditions(3),
        ).status_code
        == 422
    )
    assert admin_client.get(parent).json()["version"] == 3


def test_note_migration_empty_roundtrip_and_permission_history_refuses_contraction(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000015")
    command.upgrade(config, "head")
    sign_in(admin_client, "admin@example.test")
    roster = admin_client.get("/api/v1/ticket-queues/" + refs["queue_id"] + "/members").json()
    assert len(roster["items"]) == 3 and all(
        row["note_access"] == "none" for row in roster["items"]
    )
    configure(admin_client, refs, seeded_user, "write")
    configure(admin_client, refs, seeded_user, "none")
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable note"):
        command.downgrade(config, "b46087000015")
    command.check(config)


def test_note_event_projection_strictly_quarantines_body_and_mismatched_fields(
    admin_client, db_engine, seeded_user
):
    from altvia.activity import consume_event

    _, path = prepared(admin_client, db_engine, seeded_user)
    assert append(admin_client, path).status_code == 201
    with Session(db_engine) as db:
        original = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "ticket.note_added")
        )
        payload = dict(original.payload)
    assert consume_event(db_engine, original.event_id, datetime.now(UTC))
    assert not consume_event(db_engine, original.event_id, datetime.now(UTC))
    for change in [
        {"body_text": "private"},
        {"note_id": None},
        {"ticket_id": str(uuid4())},
        {"changed_fields": "subject"},
    ]:
        with Session(db_engine) as db, db.begin():
            event = OutboxEvent(
                aggregate_type="ticket",
                aggregate_id=original.aggregate_id,
                aggregate_version=2,
                event_type="ticket.note_added",
                payload={**payload, **change},
                occurred_at=datetime.now(UTC),
                correlation_id=uuid4().hex,
                next_attempt_at=datetime.now(UTC),
            )
            db.add(event)
            db.flush()
            identifier = event.event_id
        assert not consume_event(db_engine, identifier, datetime.now(UTC))
        with Session(db_engine) as db:
            assert db.get(OutboxEvent, identifier).last_error_code == "invalid_event"
            assert db.get(ActivityEvent, identifier) is None


def test_note_sql_rejects_bad_body_and_capability_scope(admin_client, db_engine, seeded_user):
    refs, path = prepared(admin_client, db_engine, seeded_user)
    for body in ["\t\u00a0", "x" * 10001]:
        with pytest.raises(DBAPIError), db_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ticket_notes(id,ticket_id,author_id,body_text,ticket_version) "
                    "VALUES(:id,:ticket,:author,:body,2)"
                ),
                {
                    "id": uuid4(),
                    "ticket": UUID(path.rsplit("/", 1)[1]),
                    "author": seeded_user,
                    "body": body,
                },
            )
    for statement in [
        "UPDATE role_bindings SET note_access='write' WHERE scope_kind='global'",
        "UPDATE role_bindings SET note_access='read' WHERE role_name='viewer'",
        "UPDATE role_bindings SET note_access='all' WHERE scope_kind='queue'",
    ]:
        with (
            pytest.raises(DBAPIError, match="ck_role_binding_note_access"),
            db_engine.begin() as connection,
        ):
            connection.execute(text(statement))
    configure(admin_client, refs, seeded_user, "read")
    assert admin_client.get(path + "/notes").status_code == 200


def test_note_permission_and_target_logout_finish_without_deadlock(
    admin_client, db_engine, seeded_user, settings, monkeypatch
):
    from altvia import queue_registry

    refs, _ = prepared(admin_client, db_engine, seeded_user)
    sign_in(admin_client, "admin@example.test")
    parent = "/api/v1/ticket-queues/" + refs["queue_id"]
    version = admin_client.get(parent).json()["version"]
    entered, locked, release = Event(), Event(), Event()
    record, invalidate = identity.record_event, queue_registry._invalidate_sessions

    def observe_record(db, actor, resource, event, *args, **kwargs):
        if event == "identity.session_revoked" and str(actor) == refs["agent_id"]:
            entered.set()
            assert release.wait(10)
        return record(db, actor, resource, event, *args, **kwargs)

    def observe_invalidate(db, user, now):
        if str(user.id) == refs["agent_id"]:
            locked.set()
        return invalidate(db, user, now)

    with TestClient(
        admin_client.app,
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as agent:
        sign_in(agent, "agent@example.test")
        monkeypatch.setattr(identity, "record_event", observe_record)
        monkeypatch.setattr(queue_registry, "_invalidate_sessions", observe_invalidate)
        with ThreadPoolExecutor(max_workers=2) as pool:
            logout = pool.submit(agent.delete, "/api/v1/auth/sessions/current")
            try:
                assert entered.wait(5)
                mutation = pool.submit(
                    admin_client.patch,
                    parent + "/members/" + refs["agent_id"],
                    json={"role_name": "agent", "note_access": "write"},
                    headers=preconditions(version),
                )
                assert locked.wait(5)
            finally:
                release.set()
            assert logout.result(timeout=15).status_code == 204
            assert mutation.result(timeout=15).status_code == 204


def test_note_write_identity_lock_precedes_authentication(
    admin_client, db_engine, seeded_user, monkeypatch
):
    from altvia import management
    from conftest import TEST_PASSWORD

    _, path = prepared(admin_client, db_engine, seeded_user)
    entered = Event()
    authenticate = identity.authenticate

    def observe(db, token):
        entered.set()
        return authenticate(db, token)

    monkeypatch.setattr(identity, "authenticate", observe)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(db_engine) as revoker, revoker.begin():
            management.reset_password(revoker, "employee@example.test", TEST_PASSWORD)
            pid = revoker.scalar(text("SELECT pg_backend_pid()"))
            write = pool.submit(append, admin_client, path)
            blocked = False
            deadline = monotonic() + 5
            while monotonic() < deadline and not entered.is_set():
                with db_engine.connect() as monitor:
                    blocked = bool(
                        monitor.scalar(
                            text(
                                "SELECT EXISTS(SELECT 1 FROM pg_locks l "
                                "WHERE l.locktype='advisory' AND NOT l.granted "
                                "AND :pid=ANY(pg_blocking_pids(l.pid)))"
                            ),
                            {"pid": pid},
                        )
                    )
                if blocked:
                    break
                sleep(0.02)
            assert blocked and not entered.is_set()
        assert write.result(timeout=10).status_code == 401


def test_note_foreign_customer_is_hidden_even_with_same_queue_write_permission(
    admin_client, db_engine, seeded_user
):
    from altvia.models import ClientContact
    from test_client_registry import created as create_client

    refs, local = prepared(admin_client, db_engine, seeded_user)
    sign_in(admin_client, "admin@example.test")
    customer = create_client(admin_client, seeded_user, name="Other private customer")
    with Session(db_engine) as db, db.begin():
        contact = ClientContact(
            client_id=UUID(customer),
            display_name="Foreign requester",
            email_normalized="foreign-note@example.test",
        )
        db.add(contact)
        db.flush()
        requester = str(contact.id)
    sign_in(admin_client, "employee@example.test")
    foreign = ticket(admin_client, {**refs, "client_id": customer, "requester_id": requester})
    receipt = append(admin_client, foreign, body="Customer private note").json()
    configure(admin_client, refs, refs["agent_id"], "write", "agent")
    sign_in(admin_client, "agent@example.test")
    for route in [
        foreign + "/notes",
        foreign + "/notes/" + receipt["note_id"],
        local + "/notes/" + receipt["note_id"],
    ]:
        response = admin_client.get(route)
        assert response.status_code == 404 and "Customer private note" not in response.text


def test_note_closed_ticket_keeps_reads_receipt_and_lifecycle_timestamps(
    admin_client, db_engine, seeded_user
):
    refs, path = prepared(admin_client, db_engine, seeded_user)
    key = uuid4().hex
    first = append(admin_client, path, key=key)
    assert first.status_code == 201
    assert transition(admin_client, path, 2, "open").status_code == 200
    assert transition(admin_client, path, 3, "resolved", "Resolucao verificada").status_code == 200
    sign_in(admin_client, "admin@example.test")
    queue = "/api/v1/ticket-queues/" + refs["queue_id"]
    version = admin_client.get(queue).json()["version"]
    assert (
        admin_client.patch(
            queue, json={"allow_manual_close": True}, headers=preconditions(version)
        ).status_code
        == 200
    )
    sign_in(admin_client, "employee@example.test")
    assert transition(admin_client, path, 4, "closed").status_code == 200
    before = admin_client.get(path).json()
    assert before["can_read_notes"] and not before["can_add_note"]
    assert append(admin_client, path, key=key).json() == first.json()
    assert append(admin_client, path, 5).status_code == 409
    assert admin_client.get(path + "/notes").status_code == 200
    after = admin_client.get(path).json()
    assert (after["version"], after["resolved_at"], after["closed_at"]) == (
        before["version"],
        before["resolved_at"],
        before["closed_at"],
    )
