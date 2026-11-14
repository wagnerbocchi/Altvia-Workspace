"""Real manual tickets, queue/customer authority and durable lifecycle."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia import identity, management
from altvia.models import (
    Client,
    ClientAccessGrant,
    ClientContact,
    OutboxEvent,
    Role,
    RoleBinding,
    TicketCategory,
    TicketQueue,
    User,
)
from conftest import TEST_PASSWORD
from fastapi.testclient import TestClient
from sla_migration_support import pre_sla_ticket
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_client_registry import created as create_client
from test_team_api import admin_client, preconditions, sign_in
from test_ticket_queues import category, queue

__all__ = ["admin_client"]


def setup(client, engine, employee):
    client_id = create_client(client, employee)
    queue_path = queue(client)
    category_path = category(client, queue_path)
    assert (
        client.post(
            queue_path + "/members",
            json={"email": "employee@example.test", "role_name": "operations_manager"},
            headers=preconditions(2),
        ).status_code
        == 201
    )
    queue_id = UUID(queue_path.rsplit("/", 1)[1])
    with Session(engine) as db, db.begin():
        contact = ClientContact(
            client_id=UUID(client_id),
            display_name="Solicitante",
            email_normalized="requester@example.test",
        )
        db.add(contact)
        users = {}
        for email, role in [("agent@example.test", "agent"), ("viewer@example.test", "viewer")]:
            user = management.create_user(db, email, role.title(), TEST_PASSWORD)
            users[role] = user.id
            db.execute(insert(Role).values(name=role).on_conflict_do_nothing())
            db.add(
                RoleBinding(user_id=user.id, role_name=role, scope_kind="queue", queue_id=queue_id)
            )
            db.add(
                ClientAccessGrant(
                    user_id=user.id, client_id=UUID(client_id), created_at=datetime.now(UTC)
                )
            )
        db.flush()
        requester_id = contact.id
    sign_in(client, "employee@example.test")
    return {
        "client_id": client_id,
        "queue_id": str(queue_id),
        "requester_id": str(requester_id),
        "category_id": category_path.rsplit("/", 1)[1],
        "agent_id": str(users["agent"]),
        "viewer_id": str(users["viewer"]),
    }


def body(refs, **changes):
    return {
        "client_id": refs["client_id"],
        "queue_id": refs["queue_id"],
        "requester_id": refs["requester_id"],
        "category_id": refs["category_id"],
        "subject": " Queda do servidor ",
        "description": "Conexao indisponivel",
        "priority": "high",
        **changes,
    }


def create(client, refs, key=None, **changes):
    return client.post(
        "/api/v1/tickets", json=body(refs, **changes), headers=preconditions(key=key)
    )


def ticket(client, refs, **changes):
    response = create(client, refs, **changes)
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"ticket_id"}
    return "/api/v1/tickets/" + response.json()["ticket_id"]


def transition(client, path, version, target, reason=None, key=None):
    return client.post(
        path + "/transitions",
        json={"target_status": target, "reason": reason},
        headers=preconditions(version, key),
    )


def test_ticket_create_persist_edit_and_scoped_reference_labels(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    first = admin_client.get(path)
    assert first.status_code == 200 and first.headers["etag"] == '"1"'
    value = first.json()
    assert value["subject"] == "Queda do servidor" and value["status"] == "new"
    assert isinstance(value["number"], str) and int(value["number"]) > 0
    assert value["requester_name"] == "Solicitante" and value["source"] == "manual"
    assert value["can_update"] and value["can_assign"] and value["can_claim"]
    response = admin_client.patch(
        path, json={"description": "Texto revisado", "category_id": None}, headers=preconditions(1)
    )
    assert response.status_code == 200 and response.headers["etag"] == '"2"'
    assert response.json()["category_id"] is None
    noop = admin_client.patch(
        path, json={"description": "Texto revisado"}, headers=preconditions(2)
    )
    assert noop.json()["version"] == 2
    assert (
        admin_client.patch(path, json={"priority": "low"}, headers=preconditions(1)).status_code
        == 409
    )
    history = admin_client.get(path + "/status-history").json()["items"]
    assert (
        len(history) == 1 and history[0]["from_status"] is None and history[0]["to_status"] == "new"
    )
    from altvia.models import Ticket

    with Session(db_engine) as db:
        persisted = db.get(Ticket, UUID(path.rsplit("/", 1)[1]))
        assert persisted.description == "Texto revisado" and persisted.version == 2


def test_ticket_scope_needs_queue_role_and_ceiling_even_for_platform(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    sign_in(admin_client, "admin@example.test")
    for suffix in ["", "/status-history", "/activity"]:
        assert admin_client.get(path + suffix).status_code == 404
    assert admin_client.get("/api/v1/tickets").json()["items"] == []
    assert create(admin_client, refs).status_code == 404
    sign_in(admin_client, "agent@example.test")
    assert admin_client.get(path).status_code == 200
    assert admin_client.get("/api/v1/clients").json()["items"] == []
    assert admin_client.get("/api/v1/clients/" + refs["client_id"] + "/contacts").status_code == 404
    choices = f"/api/v1/ticket-choices/{refs['queue_id']}/clients/{refs['client_id']}"
    assert (
        admin_client.get(choices + "/requesters").json()["items"][0]["id"] == refs["requester_id"]
    )
    assert admin_client.get(choices + "/assignees").status_code == 403
    with Session(db_engine) as db, db.begin():
        actor = db.scalar(select(User).where(User.email_normalized == "agent@example.test"))
        db.delete(db.get(ClientAccessGrant, (actor.id, UUID(refs["client_id"]))))
    assert admin_client.get(path).status_code == 404
    assert admin_client.get(choices + "/requesters").status_code == 404
    assert admin_client.get("/api/v1/tickets").json()["items"] == []


def test_assigned_agent_claim_and_manager_delegation_revalidate_candidates(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    sign_in(admin_client, "viewer@example.test")
    assert admin_client.get(path).status_code == 200
    assert create(admin_client, refs).status_code == 403
    assert admin_client.post(path + "/claim", json={}, headers=preconditions(1)).status_code == 403
    sign_in(admin_client, "agent@example.test")
    assert (
        admin_client.patch(path, json={"subject": "Denied"}, headers=preconditions()).status_code
        == 403
    )
    assert (
        admin_client.patch(
            path, json={"assignee_id": refs["agent_id"]}, headers=preconditions()
        ).status_code
        == 403
    )
    assert create(admin_client, refs, assignee_id=refs["viewer_id"]).status_code == 403
    key = uuid4().hex
    claim = admin_client.post(path + "/claim", json={}, headers=preconditions(1, key))
    assert claim.status_code == 200 and claim.json() == {"ticket_id": path.rsplit("/", 1)[1]}
    assert (
        admin_client.post(path + "/claim", json={}, headers=preconditions(1, key)).status_code
        == 200
    )
    assert admin_client.get(path).json()["version"] == 2
    assert (
        admin_client.patch(
            path, json={"subject": "Atendimento assumido"}, headers=preconditions(2)
        ).status_code
        == 200
    )
    assert (
        admin_client.patch(
            path, json={"requester_id": refs["requester_id"]}, headers=preconditions(3)
        ).status_code
        == 403
    )
    sign_in(admin_client, "employee@example.test")
    assert (
        admin_client.patch(
            path, json={"assignee_id": refs["viewer_id"]}, headers=preconditions(3)
        ).status_code
        == 422
    )
    assert (
        admin_client.patch(path, json={"assignee_id": None}, headers=preconditions(3)).status_code
        == 200
    )
    assert admin_client.get(path).json()["version"] == 4


def test_ticket_complete_state_graph_and_explicit_queue_close_reopen_policy(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    for version, target, reason in [
        (1, "open", None),
        (2, "pending_customer", "Aguardando retorno"),
        (3, "open", None),
        (4, "pending_third_party", "Fornecedor"),
        (5, "resolved", "Servico recuperado"),
    ]:
        response = transition(admin_client, path, version, target, reason)
        assert response.status_code == 200, response.text
        assert response.json()["history_id"]
    assert transition(admin_client, path, 6, "closed").status_code == 409
    assert transition(admin_client, path, 6, "open", "Nova solicitacao").status_code == 409
    sign_in(admin_client, "admin@example.test")
    queue_path = "/api/v1/ticket-queues/" + refs["queue_id"]
    current = admin_client.get(queue_path).json()
    configured = admin_client.patch(
        queue_path,
        json={"allow_manual_close": True, "allow_reopen": True},
        headers=preconditions(current["version"]),
    )
    assert configured.status_code == 200
    sign_in(admin_client, "employee@example.test")
    assert transition(admin_client, path, 6, "closed").status_code == 200
    closed = admin_client.get(path).json()
    assert closed["resolved_at"] and closed["closed_at"] and not closed["can_update"]
    assert (
        admin_client.patch(path, json={"subject": "Closed"}, headers=preconditions(7)).status_code
        == 409
    )
    assert transition(admin_client, path, 7, "open", "Revisar recuperacao").status_code == 200
    reopened = admin_client.get(path).json()
    assert reopened["resolved_at"] is None and reopened["closed_at"] is None
    history = admin_client.get(path + "/status-history").json()["items"]
    assert len(history) == 8 and history[0]["to_status"] == "open"


def test_ticket_transition_protocol_invalid_graph_reason_noop_and_replay(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    assert transition(admin_client, path, 1, "resolved", "Invalid jump").status_code == 409
    assert transition(admin_client, path, 1, "new").json()["history_id"] is None
    key = uuid4().hex
    first = transition(admin_client, path, 1, "open", key=key)
    assert first.status_code == 200
    assert transition(admin_client, path, 2, "resolved", "  ").status_code == 422
    assert transition(admin_client, path, 2, "pending_customer").status_code == 422
    assert transition(admin_client, path, 2, "resolved", "Restaurado").status_code == 200
    replay = transition(admin_client, path, 1, "open", key=key)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert admin_client.get(path).json()["status"] == "resolved"
    assert transition(admin_client, path, 1, "open", "Different", key=key).status_code == 409


def test_ticket_strict_input_cross_scope_and_active_reference_boundaries(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    for change in [
        {"number": "123"},
        {"status": "open"},
        {"subject": " \t\u00a0"},
        {"subject": "Line\nbreak"},
        {"description": "bad\0text"},
        {"priority": "urgent"},
        {"requester_id": str(uuid4())},
        {"category_id": str(uuid4())},
        {"assignee_id": refs["viewer_id"]},
    ]:
        assert create(admin_client, refs, **change).status_code == 422
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    for patch in [
        {},
        {"client_id": refs["client_id"]},
        {"queue_id": refs["queue_id"]},
        {"status": "open"},
        {"subject": None},
        {"requester_id": None},
    ]:
        assert admin_client.patch(path, json=patch, headers=preconditions()).status_code == 422
    with Session(db_engine) as db, db.begin():
        db.get(ClientContact, UUID(refs["requester_id"])).active = False
        db.get(User, UUID(refs["agent_id"])).active = False
    assert create(admin_client, refs).status_code == 422
    assert (
        admin_client.patch(path, json={"priority": "critical"}, headers=preconditions()).status_code
        == 200
    )
    assert admin_client.get(path).json()["requester_name"] == "Solicitante"
    assert admin_client.get(path).json()["assignee_name"] == "Agent"


def test_ticket_create_receipt_survives_archive_but_requires_present_role(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    key = uuid4().hex
    response = create(admin_client, refs, key=key)
    assert response.status_code == 201
    sign_in(admin_client, "admin@example.test")
    queue_path = "/api/v1/ticket-queues/" + refs["queue_id"]
    assert (
        admin_client.patch(queue_path, json={"active": False}, headers=preconditions(3)).status_code
        == 200
    )
    sign_in(admin_client, "employee@example.test")
    replay = create(admin_client, refs, key=key)
    assert replay.status_code == 200 and replay.json() == response.json()
    assert create(admin_client, refs).status_code == 409
    with Session(db_engine) as db, db.begin():
        binding = db.scalar(
            select(RoleBinding).where(
                RoleBinding.user_id == seeded_user, RoleBinding.scope_kind == "queue"
            )
        )
        binding.role_name = "viewer"
    assert create(admin_client, refs, key=key).status_code == 403


def test_ticket_filters_fts_cursor_scope_and_independent_creation_authority(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    first = ticket(
        admin_client, refs, subject="Conexao indisponivel PostgreSQL", priority="critical"
    )
    second = ticket(admin_client, refs, subject="Outra solicitacao", priority="low")
    page = admin_client.get("/api/v1/tickets?limit=1").json()
    assert (
        page["can_create"]
        and page["next_cursor"]
        and page["items"][0]["id"] == second.rsplit("/", 1)[1]
    )
    cursor = page["next_cursor"]
    assert (
        admin_client.get("/api/v1/tickets", params={"cursor": cursor}).json()["items"][0]["id"]
        == first.rsplit("/", 1)[1]
    )
    found = admin_client.get(
        "/api/v1/tickets", params={"q": '"Conexao indisponivel"', "priority": "critical"}
    ).json()
    assert [row["id"] for row in found["items"]] == [first.rsplit("/", 1)[1]]
    empty = admin_client.get("/api/v1/tickets", params={"queue_id": str(uuid4())}).json()
    assert empty["items"] == [] and empty["can_create"]
    assert (
        admin_client.get("/api/v1/tickets", params={"cursor": cursor, "q": "Other"}).status_code
        == 422
    )
    for query in [
        "?limit=1&limit=2",
        "?unknown=x",
        "?q=" + "x" * 201,
        "?assignee_id=" + refs["agent_id"] + "&unassigned=true",
    ]:
        assert admin_client.get("/api/v1/tickets" + query).status_code == 422


def test_ticket_mutation_failure_is_atomic_and_version_exhaustion_safe(
    admin_client, db_engine, seeded_user, monkeypatch
):
    refs = setup(admin_client, db_engine, seeded_user)
    original = identity.record_event

    def fail(db, actor, resource, event, *args, **kwargs):
        if event == "ticket.created":
            raise RuntimeError("injected ticket event failure")
        return original(db, actor, resource, event, *args, **kwargs)

    monkeypatch.setattr(identity, "record_event", fail)
    with pytest.raises(RuntimeError, match="injected ticket"):
        create(admin_client, refs)
    monkeypatch.setattr(identity, "record_event", original)
    assert admin_client.get("/api/v1/tickets").json()["items"] == []
    path = ticket(admin_client, refs)
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE tickets SET version=2147483647 WHERE id=:id"),
            {"id": UUID(path.rsplit("/", 1)[1])},
        )
    assert (
        admin_client.patch(
            path, json={"subject": "Overflow"}, headers=preconditions(2147483647)
        ).status_code
        == 409
    )
    assert admin_client.get(path).json()["subject"] == "Queda do servidor"


def test_ticket_concurrent_claims_or_transitions_have_single_effect(
    admin_client, db_engine, seeded_user, settings
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    cookies, csrf = dict(admin_client.cookies), admin_client.headers["X-CSRF-Token"]

    def claim(_):
        with TestClient(
            admin_client.app,
            base_url=settings.public_origin,
            headers={"Origin": settings.public_origin, "X-CSRF-Token": csrf},
        ) as writer:
            writer.cookies.update(cookies)
            return writer.post(path + "/claim", json={}, headers=preconditions(1)).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, range(2))) == [200, 409]
    assert admin_client.get(path).json()["version"] == 2
    with Session(db_engine) as db:
        assigned = list(
            db.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == UUID(path.rsplit("/", 1)[1]),
                    OutboxEvent.event_type == "ticket.assigned",
                )
            )
        )
        assert len(assigned) == 1


def test_ticket_bigint_number_exactness_and_guarded_schema_roundtrip(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000014")
    command.upgrade(config, "head")
    with db_engine.begin() as connection:
        connection.execute(text("ALTER SEQUENCE tickets_number_seq RESTART WITH 9007199254740993"))
    path = ticket(admin_client, refs)
    pre_sla_ticket(db_engine, path)
    assert admin_client.get(path).json()["number"] == "9007199254740993"
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable ticket"):
        command.downgrade(config, "b46087000014")
    with pytest.raises(DBAPIError), db_engine.begin() as connection:
        connection.execute(
            text("UPDATE tickets SET subject=E'\\t' WHERE id=:id"),
            {"id": UUID(path.rsplit("/", 1)[1])},
        )
    command.check(config)


def test_ticket_events_are_redacted_strict_and_projected_once(admin_client, db_engine, seeded_user):
    from altvia.activity import consume_event

    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    assert transition(admin_client, path, 1, "open").status_code == 200
    with Session(db_engine) as db:
        events = list(
            db.scalars(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == UUID(path.rsplit("/", 1)[1]))
            )
        )
    assert {event.event_type for event in events} == {
        "ticket.created",
        "ticket.assigned",
        "ticket.status_changed",
    }
    assert all(
        "Queda" not in str(event.payload) and "requester@example.test" not in str(event.payload)
        for event in events
    )
    assigned = next(event for event in events if event.event_type == "ticket.assigned")
    assert assigned.payload["old_assignee_id"] is None
    for event in events:
        assert consume_event(db_engine, event.event_id, datetime.now(UTC))
        assert not consume_event(db_engine, event.event_id, datetime.now(UTC))
    assert len(admin_client.get(path + "/activity").json()["items"]) == 3


@pytest.mark.parametrize("previous,target,version", [(None, "open", 2), ("new", "open", 1)])
def test_ticket_history_sql_rejects_invalid_initial_state(
    admin_client, db_engine, seeded_user, previous, target, version
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    pre_sla_ticket(db_engine, path)
    # Use a separate ticket history version to isolate graph validation from uniqueness.
    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM ticket_status_history"))
    with pytest.raises(DBAPIError, match="ck_ticket_state_graph"), db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ticket_status_history "
                "(id,ticket_id,actor_id,from_status,to_status,version) "
                "VALUES (:id,:ticket,:actor,:previous,:target,:version)"
            ),
            {
                "id": uuid4(),
                "ticket": UUID(path.rsplit("/", 1)[1]),
                "actor": seeded_user,
                "previous": previous,
                "target": target,
                "version": version,
            },
        )


def test_ticket_event_projection_quarantines_malformed_metadata(
    admin_client, db_engine, seeded_user
):
    from altvia.activity import consume_event

    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    with Session(db_engine) as db:
        original = db.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == UUID(path.rsplit("/", 1)[1]),
                OutboxEvent.event_type == "ticket.assigned",
            )
        )
        source = dict(original.payload)
    invalid = [
        {key: value for key, value in source.items() if key != "old_assignee_id"},
        {**source, "ticket_id": str(uuid4())},
        {**source, "new_assignee_id": None},
        {**source, "changed_fields": "subject"},
        {**source, "subject": "private text"},
        {**source, "changed_fields": "assignee_id,assignee_id"},
    ]
    for payload in invalid:
        with Session(db_engine) as db, db.begin():
            event = OutboxEvent(
                aggregate_type="ticket",
                aggregate_id=UUID(path.rsplit("/", 1)[1]),
                aggregate_version=1,
                event_type="ticket.assigned",
                schema_version=1,
                payload=payload,
                occurred_at=datetime.now(UTC),
                correlation_id=uuid4().hex,
                status="pending",
                attempts=0,
                next_attempt_at=datetime.now(UTC),
            )
            db.add(event)
            db.flush()
            event_id = event.event_id
        assert not consume_event(db_engine, event_id, datetime.now(UTC))
        with Session(db_engine) as db:
            saved = db.get(OutboxEvent, event_id)
            assert saved.status == "dead" and saved.last_error_code == "invalid_event"


def test_ticket_choices_expose_assignment_capability_and_bound_paging(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    choices = admin_client.get("/api/v1/ticket-choices/queues").json()
    assert choices["items"][0]["can_assign"]
    sign_in(admin_client, "agent@example.test")
    assert not admin_client.get("/api/v1/ticket-choices/queues").json()["items"][0]["can_assign"]
    with Session(db_engine) as db, db.begin():
        db.add(
            ClientContact(
                client_id=UUID(refs["client_id"]),
                display_name="Second requester",
                email_normalized="second@example.test",
            )
        )
    route = f"/api/v1/ticket-choices/{refs['queue_id']}/clients/{refs['client_id']}/requesters"
    page = admin_client.get(route + "?limit=1").json()
    assert page["next_cursor"] and len(page["items"]) == 1
    other = admin_client.get(route, params={"cursor": page["next_cursor"]}).json()
    assert len(other["items"]) == 1 and page["items"][0]["id"] != other["items"][0]["id"]
    sign_in(admin_client, "employee@example.test")
    assert admin_client.get(route, params={"cursor": page["next_cursor"]}).status_code == 422


def test_ticket_real_cross_customer_requester_and_cross_queue_category_are_denied(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        foreign = Client(
            name="Foreign customer", created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
        )
        db.add(foreign)
        db.flush()
        contact = ClientContact(
            client_id=foreign.id,
            display_name="Private name",
            email_normalized="private@example.test",
        )
        parent = db.get(TicketQueue, UUID(refs["queue_id"]))
        other = TicketQueue(name="Other queue", team_id=parent.team_id)
        db.add_all([contact, other])
        db.flush()
        category = TicketCategory(name="Private category", queue_id=other.id)
        db.add(category)
        db.flush()
        foreign_contact, foreign_category = str(contact.id), str(category.id)
    for change in [{"requester_id": foreign_contact}, {"category_id": foreign_category}]:
        denied = create(admin_client, refs, **change)
        assert denied.status_code == 422 and "Private" not in denied.text
    path = ticket(admin_client, refs)
    for patch in [{"requester_id": foreign_contact}, {"category_id": foreign_category}]:
        assert admin_client.patch(path, json=patch, headers=preconditions()).status_code == 422
    with pytest.raises(DBAPIError, match="fk_ticket_requester_client"), db_engine.begin() as db:
        db.execute(text("UPDATE tickets SET requester_id=:id"), {"id": UUID(foreign_contact)})
    with pytest.raises(DBAPIError, match="fk_ticket_category_queue"), db_engine.begin() as db:
        db.execute(text("UPDATE tickets SET category_id=:id"), {"id": UUID(foreign_category)})


def test_ticket_transition_receipt_requires_current_assignment_role_and_ceiling(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    sign_in(admin_client, "agent@example.test")
    key = uuid4().hex
    assert transition(admin_client, path, 1, "open", key=key).status_code == 200
    with Session(db_engine) as db, db.begin():
        db.execute(text("UPDATE tickets SET assignee_id=NULL"))
    assert transition(admin_client, path, 1, "open", key=key).status_code == 403
    with Session(db_engine) as db, db.begin():
        db.execute(text("UPDATE tickets SET assignee_id=:id"), {"id": UUID(refs["agent_id"])})
        binding = db.scalar(
            select(RoleBinding).where(RoleBinding.user_id == UUID(refs["agent_id"]))
        )
        binding.role_name = "viewer"
    assert transition(admin_client, path, 1, "open", key=key).status_code == 403
    with Session(db_engine) as db, db.begin():
        db.delete(db.get(ClientAccessGrant, (UUID(refs["agent_id"]), UUID(refs["client_id"]))))
    assert transition(admin_client, path, 1, "open", key=key).status_code == 404


def test_ticket_write_routes_enforce_origin_csrf_version_and_replay_headers(
    admin_client, db_engine, seeded_user, settings
):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    operations = [
        ("POST", "/api/v1/tickets", body(refs), False, True),
        ("PATCH", path, {"priority": "low"}, True, False),
        ("POST", path + "/claim", {}, True, True),
        ("POST", path + "/transitions", {"target_status": "open"}, True, True),
    ]
    with TestClient(admin_client.app, base_url=settings.public_origin) as client:
        client.cookies.update(dict(admin_client.cookies))
        for method, route, payload, versioned, protected in operations:
            valid = {
                **preconditions(),
                "Origin": settings.public_origin,
                "X-CSRF-Token": admin_client.headers["X-CSRF-Token"],
            }
            for header in ["Origin", "X-CSRF-Token"]:
                headers = {name: value for name, value in valid.items() if name != header}
                assert (
                    client.request(method, route, json=payload, headers=headers).status_code == 403
                )
            for header, needed in [("If-Match", versioned), ("Idempotency-Key", protected)]:
                if not needed:
                    continue
                headers = {name: value for name, value in valid.items() if name != header}
                assert (
                    client.request(method, route, json=payload, headers=headers).status_code == 428
                )
                headers[header] = "invalid value"
                assert (
                    client.request(method, route, json=payload, headers=headers).status_code == 422
                )


def test_ticket_concurrent_create_replay_and_transitions_preserve_one_effect(
    admin_client, db_engine, seeded_user, settings
):
    refs = setup(admin_client, db_engine, seeded_user)
    key = uuid4().hex
    cookies = dict(admin_client.cookies)
    headers = {
        "Origin": settings.public_origin,
        "X-CSRF-Token": admin_client.headers["X-CSRF-Token"],
    }

    def send(route, payload, extra):
        with TestClient(
            admin_client.app, base_url=settings.public_origin, headers=headers
        ) as writer:
            writer.cookies.update(cookies)
            return writer.post(route, json=payload, headers=extra)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(send, "/api/v1/tickets", body(refs), preconditions(key=key))
            for _ in range(2)
        ]
        responses = [future.result(timeout=15) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json() == responses[1].json()
    path = "/api/v1/tickets/" + responses[0].json()["ticket_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(send, path + "/transitions", {"target_status": "open"}, preconditions(1))
            for _ in range(2)
        ]
        assert sorted(future.result(timeout=15).status_code for future in futures) == [200, 409]
    assert len(admin_client.get(path + "/status-history").json()["items"]) == 2


def test_ticket_actual_runtime_identity_insert_and_append_only_history(
    admin_client, db_engine, seeded_user, settings
):
    from altvia.main import create_app
    from altvia.provision import provision_runtime
    from sqlalchemy import create_engine
    from test_runtime_provision import runtime_url

    refs = setup(admin_client, db_engine, seeded_user)
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
        path = ticket(client, refs)
        assert transition(client, path, 1, "open").status_code == 200
    for credential, statements in [
        (
            runtime,
            [
                "DELETE FROM tickets",
                "UPDATE ticket_status_history SET reason='rewrite'",
                "DELETE FROM ticket_status_history",
            ],
        ),
        (worker, ["SELECT * FROM tickets", "SELECT * FROM ticket_status_history"]),
    ]:
        engine = create_engine(credential, hide_parameters=True)
        try:
            for statement in statements:
                with pytest.raises(DBAPIError), engine.begin() as db:
                    db.execute(text(statement))
        finally:
            engine.dispose()


def test_ticket_assignment_and_target_logout_finish_without_deadlock(
    admin_client, db_engine, seeded_user, settings, monkeypatch
):
    from altvia import tickets

    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    logout_authenticated, target_locked, release_logout = Event(), Event(), Event()
    real_record, real_validate = identity.record_event, tickets.validate_assignee

    def record(db, actor_id, resource_id, event, *args, **kwargs):
        if event == "identity.session_revoked" and str(actor_id) == refs["agent_id"]:
            logout_authenticated.set()
            assert release_logout.wait(10)
        return real_record(db, actor_id, resource_id, event, *args, **kwargs)

    def validate(db, access, identifier):
        real_validate(db, access, identifier)
        target_locked.set()

    with TestClient(
        admin_client.app,
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as target:
        sign_in(target, "agent@example.test")
        monkeypatch.setattr(identity, "record_event", record)
        monkeypatch.setattr(tickets, "validate_assignee", validate)
        with ThreadPoolExecutor(max_workers=2) as pool:
            logout = pool.submit(target.delete, "/api/v1/auth/sessions/current")
            try:
                assert logout_authenticated.wait(5)
                mutation = pool.submit(
                    admin_client.patch,
                    path,
                    json={"assignee_id": refs["agent_id"]},
                    headers=preconditions(),
                )
                assert target_locked.wait(5)
            finally:
                release_logout.set()
            assert logout.result(timeout=15).status_code == 204
            assert mutation.result(timeout=15).status_code == 200
    assert admin_client.get(path).json()["assignee_id"] == refs["agent_id"]


def test_ticket_workflow_configuration_events_are_strict_and_downgrade_guarded(
    admin_client, db_engine, seeded_user
):
    from altvia.activity import consume_event

    refs = setup(admin_client, db_engine, seeded_user)
    sign_in(admin_client, "admin@example.test")
    path = "/api/v1/ticket-queues/" + refs["queue_id"]
    assert not admin_client.get(path).json()["allow_reopen"]
    assert (
        admin_client.patch(path, json={"allow_reopen": None}, headers=preconditions(3)).status_code
        == 422
    )
    assert (
        admin_client.patch(
            path + "/categories/" + refs["category_id"],
            json={"allow_reopen": True},
            headers=preconditions(),
        ).status_code
        == 422
    )
    assert (
        admin_client.patch(
            path, json={"allow_reopen": True, "allow_manual_close": True}, headers=preconditions(3)
        ).status_code
        == 200
    )
    with Session(db_engine) as db:
        original = db.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == UUID(refs["queue_id"]),
                OutboxEvent.event_type == "ticket_queue.updated",
            )
        )
    assert consume_event(db_engine, original.event_id, datetime.now(UTC))
    with Session(db_engine) as db, db.begin():
        bad = OutboxEvent(
            aggregate_type="ticket_queue",
            aggregate_id=original.aggregate_id,
            aggregate_version=4,
            event_type="ticket_queue.category_updated",
            payload={**original.payload, "category_id": refs["category_id"]},
            occurred_at=datetime.now(UTC),
            correlation_id=uuid4().hex,
            next_attempt_at=datetime.now(UTC),
        )
        db.add(bad)
        db.flush()
        event_id = bad.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    # Historical policy remains meaningful even after both flags return to defaults.
    assert (
        admin_client.patch(
            path,
            json={"allow_reopen": False, "allow_manual_close": False},
            headers=preconditions(4),
        ).status_code
        == 200
    )
    with pytest.raises(DBAPIError, match="Cannot downgrade while durable ticket or workflow"):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000014")


def test_ticket_fts_uses_gin_and_list_query_count_is_bounded(admin_client, db_engine, seeded_user):
    from altvia.tickets import SEARCH_DOCUMENT
    from sqlalchemy import event

    refs = setup(admin_client, db_engine, seeded_user)
    for subject in ["Servidor indisponivel", "Servidor recuperado", "Solicitacao nova"]:
        ticket(admin_client, refs, subject=subject)
    with db_engine.begin() as connection:
        connection.execute(text("SET LOCAL enable_seqscan=off"))
        plan = (
            connection.execute(
                text(
                    "EXPLAIN SELECT id FROM tickets WHERE "
                    + SEARCH_DOCUMENT
                    + " @@ websearch_to_tsquery('portuguese', 'servidor')"
                )
            )
            .scalars()
            .all()
        )
        assert "ix_ticket_search" in " ".join(plan)
    statements = []

    def record(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", record)
    try:
        page = admin_client.get("/api/v1/tickets?q=servidor")
    finally:
        event.remove(db_engine, "before_cursor_execute", record)
    assert page.status_code == 200 and len(page.json()["items"]) == 2
    # Session authentication, one joined page and independent creation authority.
    assert len(statements) <= 5


@pytest.mark.parametrize(
    "scope,role",
    [
        ("global", "platform_admin"),
        ("team", "operations_manager"),
        ("client", "operations_manager"),
    ],
)
def test_ticket_policy_rejects_configuration_or_client_only_authority(scope, role):
    from altvia.policy import Binding, Principal, Resource, can

    user, client, team, queue_id = (uuid4() for _ in range(4))
    identifier = {"global": None, "team": team, "client": client}[scope]
    actor = Principal(user, True, (Binding(role, scope, identifier),), frozenset({client}))
    for action in [
        "ticket.read",
        "ticket.create",
        "ticket.update",
        "ticket.transition",
        "ticket.assign",
    ]:
        assert not can(actor, action, Resource(client, team_id=team, queue_id=queue_id))
