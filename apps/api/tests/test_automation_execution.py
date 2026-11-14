"""Real durable assignment effects; source and target remain separate domains."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib import import_module
from importlib.util import find_spec
from uuid import UUID, uuid4

import pytest
from altvia import project_registry
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_automation_rules import create_rule, patch_rule, rule_context
from test_project_registry import project
from test_runtime_provision import runtime_url
from test_team_api import admin_client, preconditions, sign_in
from test_tickets import ticket

__all__ = ["admin_client", "rule_context"]


@pytest.fixture
def effect_context(admin_client, db_engine, rule_context, seeded_user):
    refs = dict(rule_context)
    with db_engine.connect() as connection:
        team = connection.scalar(
            text("SELECT team_id FROM ticket_queues WHERE id=:id"),
            {"id": UUID(refs["queue_id"])},
        )
    created = project(admin_client, seeded_user, str(team), customer=refs["client_id"])
    assert created.status_code == 201, created.text
    refs["project_id"] = created.json()["project_id"]
    sign_in(admin_client, "employee@example.test")
    client_path = "/api/v1/clients/" + refs["client_id"]
    current = admin_client.get(client_path)
    assert current.status_code == 200, current.text
    changed = admin_client.patch(
        client_path,
        json={"default_project_id": refs["project_id"]},
        headers=preconditions(current.json()["version"]),
    )
    assert changed.status_code == 200, changed.text
    with Session(db_engine) as db, db.begin():
        project_registry.set_project_access(
            db, "agent@example.test", UUID(refs["project_id"]), "agent"
        )
    refs["rule_path"] = create_rule(admin_client, refs)
    assert patch_rule(admin_client, refs["rule_path"], enabled=True).status_code == 200
    return refs


def consume_available(engine):
    # The initial baseline has a real durable job but no effect consumer. Keeping
    # that baseline in this test produces a business assertion RED (zero work),
    # rather than a missing-import/fixture error. GREEN must use the real owner.
    if find_spec("altvia.automation_execution") is None:
        return
    execution = import_module("altvia.automation_execution")
    for identifier, token in execution.claim_due(engine, datetime.now(UTC)):
        execution.consume(engine, identifier, token, datetime.now(UTC))


def test_assignment_creates_one_native_work_without_copying_private_ticket_text(
    admin_client, db_engine, effect_context
):
    refs = effect_context
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM automation_executions")) == 1
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 0
    consume_available(db_engine)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 1
        item = connection.execute(
            text(
                "SELECT title,description,priority,status,owner_id,project_id,due_at,"
                "due_precision,version FROM work_items"
            )
        ).one()
        assert tuple(item) == (
            "Configured assignment work",
            "",
            "medium",
            "todo",
            UUID(refs["agent_id"]),
            UUID(refs["project_id"]),
            None,
            None,
            2,
        )
        assert connection.scalar(text("SELECT count(*) FROM automation_effects")) == 1

        assert connection.scalar(text("SELECT count(*) FROM ticket_work_items")) == 1
        assert connection.scalar(text("SELECT state FROM automation_executions")) == "succeeded"
        assert connection.scalar(text("SELECT status FROM tickets")) == "new"
    current = admin_client.get(path)
    assert current.status_code == 200 and current.json()["priority"] == "high"
    consume_available(db_engine)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 1
        assert connection.scalar(text("SELECT count(*) FROM automation_effects")) == 1


def execution_owner():
    return import_module("altvia.automation_execution")


def test_off_on_cancels_an_old_unexpired_claim(admin_client, db_engine, effect_context):
    refs = effect_context
    ticket(admin_client, refs, assignee_id=refs["agent_id"])
    owner = execution_owner()
    identifier, token = owner.claim_due(db_engine, datetime.now(UTC))[0]
    assert patch_rule(admin_client, refs["rule_path"], enabled=False).status_code == 200
    assert patch_rule(admin_client, refs["rule_path"], enabled=True).status_code == 200
    assert owner.consume(db_engine, identifier, token, datetime.now(UTC)) is False
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT state FROM automation_executions")) == "cancelled"
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 0


def test_wrong_expired_token_and_forged_caller_clock_cannot_create_work(
    admin_client, db_engine, effect_context
):
    ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    owner = execution_owner()
    identifier, token = owner.claim_due(db_engine, datetime.now(UTC))[0]
    assert owner.consume(db_engine, identifier, uuid4(), datetime.now(UTC)) is False
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE automation_executions SET lease_until=clock_timestamp()-interval '1 second'"
            )
        )
    assert owner.consume(db_engine, identifier, token, datetime(2000, 1, 1, tzinfo=UTC)) is False
    new_identifier, new_token = owner.claim_due(db_engine, datetime.now(UTC))[0]
    assert new_identifier == identifier and new_token != token
    assert owner.consume(db_engine, identifier, token, datetime.now(UTC)) is False
    assert owner.consume(db_engine, identifier, new_token, datetime.now(UTC)) is True
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 1


def test_two_real_consumers_have_one_logical_effect(admin_client, db_engine, effect_context):
    ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    owner = execution_owner()
    identifier, token = owner.claim_due(db_engine, datetime.now(UTC))[0]
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(
            pool.map(
                lambda _: owner.consume(db_engine, identifier, token, datetime.now(UTC)), range(2)
            )
        )
    assert sorted(outcomes) == [False, True]
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 1
        assert connection.scalar(text("SELECT count(*) FROM automation_effects")) == 1
        assert connection.scalar(text("SELECT count(*) FROM ticket_work_items")) == 1


def test_final_lease_loss_rolls_back_work_history_links_and_effect(
    admin_client, db_engine, effect_context, monkeypatch
):
    from altvia import work_creation

    ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    owner = execution_owner()
    identifier, token = owner.claim_due(db_engine, datetime.now(UTC))[0]
    original = work_creation.create_record
    reached = []

    def expire_after_insert(db, *args, **kwargs):
        result = original(db, *args, **kwargs)
        reached.append(result.id)
        db.execute(
            text(
                "UPDATE automation_executions SET "
                "lease_until=clock_timestamp()-interval '1 second' "
                "WHERE id=:id"
            ),
            {"id": identifier},
        )
        return result

    with monkeypatch.context() as patch:
        patch.setattr(work_creation, "create_record", expire_after_insert)
        assert owner.consume(db_engine, identifier, token, datetime.now(UTC)) is False
    assert len(reached) == 1
    with db_engine.connect() as connection:
        for table in (
            "work_items",
            "work_item_status_history",
            "ticket_work_items",
            "automation_effects",
        ):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        assert (
            connection.scalar(text("SELECT count(*) FROM outbox_events WHERE schema_version=2"))
            == 0
        )
    # The injected expiry was in that same rolled-back transaction. Retrying the
    # still-current original token now exercises real recovery, without a new task.
    assert owner.consume(db_engine, identifier, token, datetime.now(UTC)) is True


@pytest.mark.parametrize(
    "missing",
    [
        "default",
        "project_active",
        "assignee_project",
        "assignee_active",
        "authorizer",
        "ceiling",
        "queue_access",
        "configuration_access",
        "client_role",
        "assignee_queue",
        "client_active",
        "team_active",
    ],
)
def test_live_resolution_and_authority_never_invent_a_grant(
    admin_client, db_engine, effect_context, seeded_user, missing
):
    refs = effect_context
    ticket(admin_client, refs, assignee_id=refs["agent_id"])
    with db_engine.begin() as connection:
        if missing == "default":
            connection.execute(text("UPDATE clients SET default_project_id=NULL"))
        elif missing == "project_active":
            connection.execute(text("UPDATE projects SET active=false"))
        elif missing == "assignee_project":
            connection.execute(
                text("DELETE FROM role_bindings WHERE scope_kind='project' AND user_id=:id"),
                {"id": UUID(refs["agent_id"])},
            )
        elif missing in {"authorizer", "assignee_active"}:
            target = seeded_user if missing == "authorizer" else UUID(refs["agent_id"])
            connection.execute(text("UPDATE users SET active=false WHERE id=:id"), {"id": target})
        elif missing == "ceiling":
            connection.execute(
                text("DELETE FROM client_access_grants WHERE user_id=:id"), {"id": seeded_user}
            )
        elif missing in {"queue_access", "configuration_access", "client_role", "assignee_queue"}:
            scope = {
                "queue_access": "queue",
                "configuration_access": "team",
                "client_role": "client",
                "assignee_queue": "queue",
            }[missing]
            connection.execute(
                text("DELETE FROM role_bindings WHERE user_id=:id AND scope_kind=:scope"),
                {
                    "id": UUID(refs["agent_id"]) if missing == "assignee_queue" else seeded_user,
                    "scope": scope,
                },
            )
        elif missing == "client_active":
            connection.execute(text("UPDATE clients SET active=false"))
        else:
            connection.execute(text("UPDATE teams SET active=false"))
        bindings = connection.scalar(text("SELECT count(*) FROM role_bindings"))
        projects = connection.scalar(text("SELECT count(*) FROM projects"))
    consume_available(db_engine)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 0
        assert connection.scalar(text("SELECT count(*) FROM role_bindings")) == bindings
        assert connection.scalar(text("SELECT count(*) FROM projects")) == projects
        assert connection.scalar(text("SELECT state FROM automation_executions")) == "triage"


def test_receipt_survives_unlink_reassignment_rule_edit_and_missing_new_default(
    admin_client, db_engine, effect_context, seeded_user
):
    refs = effect_context
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    consume_available(db_engine)
    with db_engine.connect() as connection:
        work_id = connection.scalar(text("SELECT id FROM work_items"))
    source, target = (
        admin_client.get(path).json(),
        admin_client.get(f"/api/v1/work-items/{work_id}").json(),
    )
    removed = admin_client.delete(
        f"{path}/work-items/{work_id}",
        headers={
            **preconditions(source["version"]),
            "If-Match-Work-Item": f'"{target["version"]}"',
        },
    )
    assert removed.status_code == 204, removed.text
    assert (
        patch_rule(
            admin_client, refs["rule_path"], title="Later title", priority="critical"
        ).status_code
        == 200
    )
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE clients SET default_project_id=NULL"))
    source = admin_client.get(path).json()
    assert (
        admin_client.patch(
            path, json={"assignee_id": str(seeded_user)}, headers=preconditions(source["version"])
        ).status_code
        == 200
    )
    consume_available(db_engine)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 1
        assert connection.scalar(text("SELECT count(*) FROM ticket_work_items")) == 0
        assert connection.scalar(text("SELECT count(*) FROM automation_effects")) == 1
        assert connection.scalar(text("SELECT owner_id FROM work_items")) == UUID(refs["agent_id"])
        assert (
            connection.scalar(text("SELECT title FROM work_items")) == "Configured assignment work"
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM automation_executions WHERE state='succeeded'")
            )
            == 2
        )


def test_actual_worker_role_can_execute_without_private_content_or_authority_writes(
    admin_client, db_engine, effect_context
):
    from altvia.provision import provision_runtime

    ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    api_url = runtime_url(db_engine)
    worker_url = api_url.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        api_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    worker_engine = create_engine(worker_url, hide_parameters=True)
    try:
        try:
            consume_available(worker_engine)
        except DBAPIError as error:
            assert error.orig.sqlstate == "42501"
            pytest.fail("The real worker role cannot yet execute the native assignment effect")
        with db_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM work_items")) == 1
        for statement in (
            "SELECT password_hash FROM users",
            "SELECT email_normalized FROM users",
            "SELECT subject FROM tickets",
            "SELECT description FROM tickets",
            "SELECT title FROM work_items",
            "SELECT description FROM work_items",
            "SELECT body_text FROM ticket_notes",
            "SELECT body_text FROM ticket_messages",
            "SELECT * FROM inbound_mail_variants",
            "UPDATE users SET active=active",
            "UPDATE role_bindings SET role_name=role_name",
            "UPDATE clients SET default_project_id=default_project_id",
            "UPDATE tickets SET assignee_id=assignee_id",
            "UPDATE tickets SET status=status",
            "UPDATE work_items SET owner_id=owner_id",
            "UPDATE work_items SET status=status",
            "UPDATE automation_rules SET version=version",
            "UPDATE automation_rule_revisions SET enabled=enabled",
            "UPDATE automation_executions SET source_event_id=source_event_id",
            "DELETE FROM ticket_work_items",
            "DELETE FROM automation_effects",
        ):
            with pytest.raises(DBAPIError) as caught, worker_engine.begin() as connection:
                connection.execute(text(statement))
            assert caught.value.orig.sqlstate == "42501", statement
    finally:
        worker_engine.dispose()


@pytest.mark.parametrize("count", [1, 2])
def test_existing_native_links_adopt_only_one_without_mutating_work(
    admin_client, db_engine, effect_context, seeded_user, count
):
    from test_work_items import create_work

    refs = effect_context
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    versions = {}
    for _ in range(count):
        response = create_work(admin_client, refs["project_id"], owner_id=str(seeded_user))
        assert response.status_code == 201, response.text
        work_id = response.json()["work_item_id"]
        source = admin_client.get(path).json()
        linked = admin_client.post(
            path + "/work-items",
            json={"work_item_id": work_id},
            headers={**preconditions(source["version"]), "If-Match-Work-Item": '"1"'},
        )
        assert linked.status_code == 201, linked.text
        versions[work_id] = admin_client.get("/api/v1/work-items/" + work_id).json()
    source = admin_client.get(path).json()
    consume_available(db_engine)
    assert admin_client.get(path).json() == source
    for work_id, before in versions.items():
        assert admin_client.get("/api/v1/work-items/" + work_id).json() == before
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == count
        state, code = connection.execute(
            text("SELECT state,error_code FROM automation_executions")
        ).one()
        assert (state, code) == (
            ("succeeded", None) if count == 1 else ("triage", "existing_work_needs_review")
        )
        assert connection.scalar(text("SELECT count(*) FROM automation_effects")) == (count == 1)
        if count == 1:
            assert connection.scalar(text("SELECT mode FROM automation_effects")) == "adopted"
        assert (
            connection.scalar(text("SELECT count(*) FROM outbox_events WHERE schema_version=2"))
            == 0
        )


@pytest.mark.parametrize("corruption", ["schema", "type", "payload", "version"])
def test_corrupted_durable_assignment_never_creates_work(
    admin_client, db_engine, effect_context, corruption
):
    ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    statement = {
        "schema": "schema_version=99",
        "type": "event_type='ticket.updated'",
        "payload": "payload=payload || jsonb_build_object('unexpected',true)",
        "version": "aggregate_version=2147483647",
    }[corruption]
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE outbox_events SET "
                + statement
                + " WHERE event_id=(SELECT source_event_id FROM automation_executions)"
            )
        )
    consume_available(db_engine)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 0
        assert connection.execute(
            text("SELECT state,error_code FROM automation_executions")
        ).one() == ("dead", "invalid_event")


def test_unpublished_claim_exhaustion_is_bounded_and_stale_token_cannot_reset_it(
    admin_client, db_engine, effect_context
):
    ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    owner = execution_owner()
    tokens = []
    for attempt in range(1, 9):
        identifier, token = owner.claim_due(db_engine, datetime.now(UTC))[0]
        tokens.append(token)
        assert owner.publication_failed(db_engine, identifier, token, datetime.now(UTC)) is True
        assert owner.publication_failed(db_engine, identifier, token, datetime.now(UTC)) is False
        with db_engine.begin() as connection:
            state, attempts, delay = connection.execute(
                text(
                    "SELECT state,attempts,extract(epoch FROM (next_attempt_at-updated_at)) "
                    "FROM automation_executions"
                )
            ).one()
            assert attempts == attempt and 0 < delay <= 1080
            assert state == ("dead" if attempt == 8 else "pending")
            connection.execute(
                text(
                    "UPDATE automation_executions SET "
                    "next_attempt_at=clock_timestamp()-interval '1 second'"
                )
            )
    assert len(set(tokens)) == 8
    assert owner.claim_due(db_engine, datetime.now(UTC)) == []
    assert owner.consume(db_engine, identifier, tokens[0], datetime.now(UTC)) is False
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 0


def test_ticket_version_exhaustion_rolls_back_every_new_domain_effect(
    admin_client, db_engine, effect_context
):
    ticket(admin_client, effect_context, assignee_id=effect_context["agent_id"])
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE tickets SET version=2147483647"))
    consume_available(db_engine)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT version FROM tickets")) == 2147483647
        assert connection.scalar(text("SELECT state FROM automation_executions")) == "triage"
        for table in (
            "work_items",
            "work_item_status_history",
            "ticket_work_items",
            "automation_effects",
        ):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0


def test_post_enable_assignment_uses_new_revision_while_old_claim_stays_cancelled(
    admin_client, db_engine, effect_context
):
    refs = effect_context
    ticket(admin_client, refs, assignee_id=refs["agent_id"])
    owner = execution_owner()
    identifier, token = owner.claim_due(db_engine, datetime.now(UTC))[0]
    assert patch_rule(admin_client, refs["rule_path"], enabled=False).status_code == 200
    assert (
        patch_rule(admin_client, refs["rule_path"], enabled=True, title="New revision").status_code
        == 200
    )
    ticket(admin_client, refs, assignee_id=refs["agent_id"])
    assert owner.consume(db_engine, identifier, token, datetime.now(UTC)) is False
    consume_available(db_engine)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 1
        assert connection.scalar(text("SELECT title FROM work_items")) == "New revision"
        assert set(connection.scalars(text("SELECT state FROM automation_executions"))) == {
            "cancelled",
            "succeeded",
        }


def test_queued_old_assignee_is_superseded_before_any_work_is_created(
    admin_client, db_engine, effect_context, seeded_user
):
    refs = effect_context
    path = ticket(admin_client, refs, assignee_id=refs["agent_id"])
    owner = execution_owner()
    identifier, token = owner.claim_due(db_engine, datetime.now(UTC))[0]
    response = admin_client.patch(
        path, json={"assignee_id": str(seeded_user)}, headers=preconditions()
    )
    assert response.status_code == 200, response.text
    assert owner.consume(db_engine, identifier, token, datetime.now(UTC)) is False
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 0
        assert (
            connection.scalar(
                text("SELECT state FROM automation_executions WHERE id=:id"), {"id": identifier}
            )
            == "superseded"
        )
    consume_available(db_engine)
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM work_items")) == 1
        assert connection.scalar(text("SELECT owner_id FROM work_items")) == seeded_user
