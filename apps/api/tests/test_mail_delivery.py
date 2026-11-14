"""Protected public delivery on real PostgreSQL, with synthetic attestations only."""

from test_team_api import admin_client
from test_tickets import setup, ticket

__all__ = ["admin_client"]


import json
import secrets
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
from uuid import UUID, uuid4

import pytest
from altvia import mail_delivery as delivery
from altvia import provision
from altvia.mail_intake import register_source
from altvia.mail_participants import attest_requester, register_sender, revoke_requester
from altvia.mail_settings import SMTPAccount, load_accounts
from altvia.models import OutboundMessage, OutboxEvent
from sla_migration_support import pre_sla_ticket
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_team_api import preconditions, sign_in
from test_ticket_messages import append


def test_delivery_choices_require_explicit_attestation(admin_client, db_engine, seeded_user):
    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    response = admin_client.get(path + "/delivery-choices")
    assert response.status_code == 200, response.text
    assert response.json() == {"sender": None, "participant": None, "can_send": False}


def prepared(client, engine, user, from_email="support@example.test"):
    refs = setup(client, engine, user)
    path = ticket(client, refs)
    message = append(client, path).json()["message_id"]
    with Session(engine) as db, db.begin():
        source = register_source(db, "synthetic_sender", UUID(refs["queue_id"]))
        account = SMTPAccount(
            source_id=source.id,
            host="smtp.example.test",
            port=465,
            tls_mode="implicit",
            username="synthetic",
            password="synthetic",
            from_email=from_email,
        )
        register_sender(db, account)
        participant = attest_requester(
            db, UUID(path.rsplit("/", 1)[1]), 2, "synthetic-test-evidence-only"
        )
        participant_id = participant.id
    return refs, path, message, account, participant_id


def enqueue(client, path, message, account, participant, key=None, version=2):
    return client.post(
        path + "/messages/" + message + "/delivery",
        json={"source_id": str(account.source_id), "participant_id": str(participant)},
        headers=preconditions(version, key),
    )


def test_queue_snapshot_replay_unique_and_scoped_status(admin_client, db_engine, seeded_user):
    refs, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    choices = admin_client.get(path + "/delivery-choices").json()
    assert choices["can_send"] and choices["participant"]["email"] == "requester@example.test"
    assert "evidence" not in json.dumps(choices)
    key = uuid4().hex
    result = enqueue(admin_client, path, message, account, participant, key)
    assert result.status_code == 201, result.text
    assert set(result.json()) == {"ticket_id", "message_id", "delivery_id"}
    replay = enqueue(admin_client, path, message, account, participant, key)
    assert replay.status_code == 200 and replay.json() == result.json()
    assert enqueue(admin_client, path, message, account, participant, version=3).status_code == 409
    status = admin_client.get(path + "/messages/" + message + "/delivery").json()
    assert status["state"] == "queued" and status["attempts"] == 0 and status["accepted_at"] is None
    assert admin_client.get(path + "/messages/" + message).json()["delivery_status"] == "queued"
    assert admin_client.get(path).json()["version"] == 3
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, UUID(result.json()["delivery_id"]))
        wire = BytesParser(policy=policy.default).parsebytes(row.wire)
        assert wire["From"] == "support@example.test" and wire["To"] == "requester@example.test"
        assert wire.get_content_type() == "text/plain"
        assert wire["Message-ID"] == row.smtp_message_id
        assert "Resposta publica" in wire.get_content()
        events = list(
            db.scalars(
                select(OutboxEvent).where(OutboxEvent.event_type == "ticket.delivery_queued")
            )
        )
        assert len(events) == 1 and set(events[0].payload) == {
            "actor_id",
            "actor_kind",
            "ticket_id",
            "client_id",
            "queue_id",
            "message_id",
            "delivery_id",
        }
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path + "/messages/" + message + "/delivery").status_code == 404
    assert enqueue(admin_client, path, message, account, participant, key).status_code == 404


def test_protocol_parent_and_unverified_negatives(admin_client, db_engine, seeded_user):
    refs, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    endpoint = path + "/messages/" + message + "/delivery"
    body = {"source_id": str(account.source_id), "participant_id": str(participant)}
    assert admin_client.post(endpoint, json=body).status_code == 428
    assert admin_client.post(endpoint, json=body, headers=preconditions(99)).status_code == 409
    assert (
        admin_client.post(
            endpoint, json={**body, "wire": "arbitrary"}, headers=preconditions(2)
        ).status_code
        == 422
    )
    other = ticket(admin_client, refs)
    assert enqueue(admin_client, other, message, account, participant, version=1).status_code == 404
    assert enqueue(admin_client, path, str(uuid4()), account, participant).status_code == 404
    assert enqueue(admin_client, path, message, account, uuid4()).status_code == 409
    sign_in(admin_client, "viewer@example.test")
    assert enqueue(admin_client, path, message, account, participant).status_code == 403
    assert admin_client.get(path + "/delivery-choices").json()["can_send"] is False
    sign_in(admin_client, "agent@example.test")
    assert enqueue(admin_client, path, message, account, participant).status_code == 403


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE client_contacts SET active=false",
        "UPDATE client_contacts SET email_normalized='changed@example.test'",
        "UPDATE tickets SET requester_id=:other",
        "revoke",
    ],
)
def test_changed_requester_or_revocation_blocks_queue(admin_client, db_engine, seeded_user, change):
    refs, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        if change == "revoke":
            revoke_requester(db, participant, 1)
        elif ":other" in change:
            # An unrelated current contact is not attested by an old participant.
            from altvia.models import ClientContact

            contact = ClientContact(
                client_id=UUID(refs["client_id"]),
                display_name="Other",
                email_normalized="other@example.test",
            )
            db.add(contact)
            db.flush()
            db.execute(text(change), {"other": contact.id})
        else:
            db.execute(text(change))
    assert enqueue(admin_client, path, message, account, participant).status_code == 409
    assert admin_client.get(path + "/delivery-choices").json()["participant"] is None


def test_lease_token_predata_acceptance_and_worker_privacy(admin_client, db_engine, seeded_user):
    refs, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    result = enqueue(admin_client, path, message, account, participant)
    assert result.status_code == 201, result.text
    password = secrets.token_urlsafe(24)
    app_url = db_engine.url.set(username="altvia_app", password=password)
    worker_url = db_engine.url.set(username="altvia_worker", password=password)
    provision.provision_runtime(
        db_engine,
        app_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    provision.provision_runtime(
        db_engine,
        app_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    engine = create_engine(worker_url, hide_parameters=True)
    try:
        now = datetime.now(UTC)
        assert delivery.claim(engine, {}) is None
        mismatch = account.model_copy(update={"host": "other.example.test"})
        assert delivery.claim(engine, {account.source_id: mismatch}) is None
        claim = delivery.claim(engine, {account.source_id: account}, now)
        assert claim and delivery.claim(engine, {account.source_id: account}, now) is None
        frozen = delivery.frozen_delivery(engine, claim.delivery_id, claim.token, now)
        assert frozen and frozen.wire
        assert not delivery.pre_data(engine, claim.delivery_id, uuid4(), now)
        assert delivery.pre_data(engine, claim.delivery_id, claim.token, now)
        assert not delivery.finalize(engine, claim.delivery_id, uuid4(), "accepted", now)
        assert delivery.finalize(engine, claim.delivery_id, claim.token, "accepted", now)
        assert not delivery.finalize(engine, claim.delivery_id, claim.token, "accepted", now)
        status = admin_client.get(path + "/messages/" + message + "/delivery").json()
        assert status["state"] == "accepted" and status["accepted_at"] and status["attempts"] == 1
        for statement in (
            "SELECT password_hash FROM users",
            "SELECT * FROM users",
            "SELECT * FROM sessions",
            "SELECT body_text FROM ticket_notes",
            "SELECT raw_message FROM inbound_mail_variants",
            "SELECT evidence FROM ticket_participants",
            "UPDATE outbound_messages SET envelope_to='forged@example.test'",
            "INSERT INTO ticket_participants(id) VALUES(gen_random_uuid())",
            "UPDATE mail_senders SET from_email='forged@example.test'",
        ):
            with engine.begin() as conn, pytest.raises(DBAPIError):
                conn.execute(text(statement))
    finally:
        engine.dispose()


def test_expiry_uncertainty_safe_retry_and_owner_reconcile(admin_client, db_engine, seeded_user):
    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    now = datetime.now(UTC)
    claim = delivery.claim(db_engine, {account.source_id: account}, now)
    later = now + timedelta(seconds=121)
    assert not delivery.pre_data(db_engine, claim.delivery_id, claim.token, later)
    assert delivery.recover(db_engine, later) == [claim.delivery_id]
    retry = delivery.claim(db_engine, {account.source_id: account}, later)
    assert retry.token != claim.token
    assert delivery.pre_data(db_engine, retry.delivery_id, retry.token, later)
    lost = later + timedelta(seconds=121)
    assert delivery.recover(db_engine, lost) == [claim.delivery_id]
    assert delivery.claim(db_engine, {account.source_id: account}, lost) is None
    with Session(db_engine) as db, db.begin():
        row = db.get(OutboundMessage, claim.delivery_id)
        assert row.state == "uncertain"
        with pytest.raises(ValueError):
            delivery.reconcile(
                db,
                row.id,
                row.version,
                "not_accepted",
                "synthetic-provider-evidence",
                workers_drained=False,
            )
        delivery.reconcile(
            db,
            row.id,
            row.version,
            "not_accepted",
            "synthetic-provider-evidence",
            workers_drained=True,
        )
    now = lost + timedelta(seconds=1)
    for attempt in range(3, 9):
        current = delivery.claim(db_engine, {account.source_id: account}, now)
        assert current
        assert delivery.finalize(db_engine, current.delivery_id, current.token, "temporary", now)
        with Session(db_engine) as db:
            row = db.get(OutboundMessage, current.delivery_id)
            assert row.attempts == attempt
            if attempt < 8:
                assert 0 < (row.next_attempt_at - now).total_seconds() <= 3600
                now = row.next_attempt_at
            else:
                assert row.state == "failed" and row.last_error_code == "retry_exhausted"


def test_predata_rechecks_revoked_actor_and_attestation(admin_client, db_engine, seeded_user):
    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    current = delivery.claim(db_engine, {account.source_id: account})
    with Session(db_engine) as db, db.begin():
        revoke_requester(db, participant, 1)
    assert not delivery.pre_data(db_engine, current.delivery_id, current.token)
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, current.delivery_id)
        assert row.state == "failed" and row.last_error_code == "eligibility_revoked"


def test_atomic_rollback_and_frozen_sql_guards(admin_client, db_engine, seeded_user):
    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION reject_delivery_event() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN IF NEW.event_type='ticket.delivery_queued' THEN RAISE EXCEPTION "
                "'synthetic'; END IF; RETURN NEW; END $$"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER reject_delivery BEFORE INSERT ON outbox_events "
                "FOR EACH ROW EXECUTE FUNCTION reject_delivery_event()"
            )
        )
    try:
        assert enqueue(admin_client, path, message, account, participant).status_code == 503
        with Session(db_engine) as db:
            assert db.scalar(select(OutboundMessage.id)) is None
        assert admin_client.get(path).json()["version"] == 2
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DROP TRIGGER reject_delivery ON outbox_events"))
            conn.execute(text("DROP FUNCTION reject_delivery_event()"))
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    for statement in (
        "UPDATE outbound_messages SET wire='forged'::bytea",
        "DELETE FROM outbound_messages",
        "UPDATE ticket_participants SET email='forged@example.test'",
        "DELETE FROM ticket_participants",
        "UPDATE mail_senders SET from_email='forged@example.test'",
    ):
        with db_engine.begin() as conn, pytest.raises(DBAPIError):
            conn.execute(text(statement))


def test_config_bounds_namespace_and_plain_mime(tmp_path):
    account = SMTPAccount(
        source_id=uuid4(),
        host="smtp.example.test",
        port=465,
        tls_mode="implicit",
        username="operator",
        password="secret",
        from_email="sender@example.test",
    )
    assert (
        account.namespace_hash
        == account.model_copy(
            update={"password": "rotated", "ca_file": tmp_path / "ca"}
        ).namespace_hash
    )
    assert (
        account.namespace_hash != account.model_copy(update={"host": "other.test"}).namespace_hash
    )
    path = tmp_path / "smtp.json"
    entry = account.model_dump(mode="json")
    entry["username"] = "operator"
    entry["password"] = "secret"
    path.write_text(json.dumps([entry]))
    assert load_accounts(path)[account.source_id] == account
    for content in (
        json.dumps([entry] * 17),
        json.dumps([entry, entry]),
        "x" * 65537,
        json.dumps([{**entry, "from_email": "nonascii\u00e9@example.test"}]),
        json.dumps([{**entry, "host": "smtp://user:password@host"}]),
    ):
        path.write_text(content)
        with pytest.raises(ValueError, match="^invalid_smtp_configuration$"):
            load_accounts(path)


def test_full_existing_public_draft_unicode_budget():
    body = "\U0001f600" * 10000
    wire = delivery.build_wire(
        "sender@example.test",
        "requester@example.test",
        "\U0001f600" * 300,
        body,
        "<fixed@example.test>",
        "f" * 64,
        datetime.now(UTC),
        [],
    )
    parsed = BytesParser(policy=policy.default).parsebytes(wire)
    assert parsed.get_content().rstrip("\r\n") == body
    assert len(wire) <= 262144


@pytest.mark.parametrize("stage", ["preparing", "transmitting"])
def test_expiry_is_checked_after_blocked_lock_using_database_clock(
    admin_client, db_engine, seeded_user, stage
):
    from concurrent.futures import ThreadPoolExecutor

    from altvia.management import lock_identity_writes

    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    current = delivery.claim(db_engine, {account.source_id: account})
    if stage == "transmitting":
        assert delivery.pre_data(db_engine, current.delivery_id, current.token)
    stale_now = datetime.now(UTC)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE outbound_messages SET lease_until=clock_timestamp()+interval '0.3 seconds' "
                "WHERE id=:id"
            ),
            {"id": current.delivery_id},
        )
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(db_engine) as blocker, blocker.begin():
            if stage == "preparing":
                lock_identity_writes(blocker)
                future = pool.submit(
                    delivery.pre_data, db_engine, current.delivery_id, current.token, stale_now
                )
            else:
                blocker.execute(
                    select(OutboundMessage)
                    .where(OutboundMessage.id == current.delivery_id)
                    .with_for_update()
                ).one()
                future = pool.submit(
                    delivery.finalize,
                    db_engine,
                    current.delivery_id,
                    current.token,
                    "accepted",
                    stale_now,
                )
            blocker.execute(text("SELECT pg_sleep(0.5)"))
        assert future.result(timeout=10) is False
    with Session(db_engine) as db:
        assert db.get(OutboundMessage, current.delivery_id).state == stage


def test_owner_reconciliation_preserves_actual_acceptance_time(
    admin_client, db_engine, seeded_user
):
    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    current = delivery.claim(db_engine, {account.source_id: account})
    assert delivery.pre_data(db_engine, current.delivery_id, current.token)
    assert delivery.finalize(db_engine, current.delivery_id, current.token, "data_unknown")
    accepted_at = datetime.now(UTC)
    with Session(db_engine) as db, db.begin():
        row = db.get(OutboundMessage, current.delivery_id)
        version = row.version
        for invalid in (
            None,
            datetime.now(),
            row.created_at - timedelta(seconds=1),
            accepted_at + timedelta(days=1),
        ):
            with pytest.raises(ValueError, match="invalid_acceptance_evidence_time"):
                delivery.reconcile(
                    db,
                    row.id,
                    version,
                    "accepted",
                    "synthetic-receipt-id",
                    workers_drained=True,
                    accepted_at=invalid,
                )
        with pytest.raises(ValueError):
            delivery.reconcile(
                db,
                row.id,
                version,
                "accepted",
                "address@example.test",
                workers_drained=True,
                accepted_at=accepted_at,
            )
        delivery.reconcile(
            db,
            row.id,
            version,
            "accepted",
            "synthetic-receipt-id",
            workers_drained=True,
            accepted_at=accepted_at,
        )
    with Session(db_engine) as db:
        assert db.get(OutboundMessage, current.delivery_id).accepted_at == accepted_at


def test_delivery_race_has_one_frozen_effect_and_current_authority_replay(
    admin_client, db_engine, seeded_user
):
    from concurrent.futures import ThreadPoolExecutor

    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    key = uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: enqueue(admin_client, path, message, account, participant, key), range(2)
            )
        )
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert responses[0].json() == responses[1].json()
    with Session(db_engine) as db, db.begin():
        db.execute(text("UPDATE clients SET active=false"))
    assert enqueue(admin_client, path, message, account, participant, key).status_code == 200
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM client_access_grants WHERE user_id=:id"), {"id": seeded_user}
        )
    assert enqueue(admin_client, path, message, account, participant, key).status_code == 404


def test_note_id_and_wrong_sender_cannot_deliver(admin_client, db_engine, seeded_user):
    from altvia.models import TicketNote

    refs, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        note = TicketNote(
            ticket_id=UUID(path.rsplit("/", 1)[1]),
            author_id=seeded_user,
            body_text="Private content",
            ticket_version=3,
            created_at=datetime.now(UTC),
        )
        db.add(note)
        db.flush()
        note_id = note.id
    assert enqueue(admin_client, path, str(note_id), account, participant).status_code == 404
    wrong = account.model_copy(update={"source_id": uuid4()})
    assert enqueue(admin_client, path, message, wrong, participant).status_code == 409


def test_migration_refuses_durable_mail_history(admin_client, db_engine, seeded_user):
    from alembic import command
    from alembic.config import Config

    _, path, _, _, _ = prepared(admin_client, db_engine, seeded_user)
    pre_sla_ticket(db_engine, path)
    with pytest.raises(DBAPIError, match="Cannot contract durable"):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000021")


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE users SET active=false WHERE id=:actor",
        "DELETE FROM role_bindings WHERE user_id=:actor",
        "UPDATE client_contacts SET email_normalized='changed@example.test'",
        "UPDATE ticket_queues SET active=false",
    ],
)
def test_worker_predata_eligibility_covers_current_actor_and_parents(
    admin_client, db_engine, seeded_user, change
):
    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    current = delivery.claim(db_engine, {account.source_id: account})
    with db_engine.begin() as conn:
        conn.execute(text(change), {"actor": seeded_user})
    assert not delivery.pre_data(db_engine, current.delivery_id, current.token)


def test_specific_id_claim_and_real_runtime_api_privileges(
    admin_client, db_engine, seeded_user, settings
):
    from altvia.main import create_app
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    first = enqueue(admin_client, path, message, account, participant)
    identifier = UUID(first.json()["delivery_id"])
    assert delivery.claim(db_engine, {account.source_id: account}, identifier=uuid4()) is None
    password = secrets.token_urlsafe(24)
    app_url = db_engine.url.set(username="altvia_app", password=password)
    worker_url = db_engine.url.set(username="altvia_worker", password=password)
    provision.provision_runtime(
        db_engine,
        app_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    with TestClient(
        create_app(
            settings.model_copy(
                update={"database_url": SecretStr(app_url.render_as_string(hide_password=False))}
            )
        ),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as runtime:
        sign_in(runtime, "employee@example.test")
        assert runtime.get(path + "/delivery-choices").status_code == 200
        draft = append(runtime, path, version=3)
        assert draft.status_code == 201, draft.text
        assert (
            enqueue(
                runtime, path, draft.json()["message_id"], account, participant, version=4
            ).status_code
            == 201
        )
    worker = create_engine(worker_url, hide_parameters=True)
    app = create_engine(app_url, hide_parameters=True)
    try:
        current = delivery.claim(worker, {account.source_id: account}, identifier=identifier)
        assert current.delivery_id == identifier
        with Session(worker) as db, pytest.raises(ValueError, match="owner_required"):
            delivery.reconcile(db, identifier, 1, "not_accepted", "synthetic", workers_drained=True)
        for engine in (worker, app):
            with engine.begin() as conn, pytest.raises(DBAPIError):
                conn.execute(text("SELECT evidence FROM ticket_participants"))
    finally:
        worker.dispose()
        app.dispose()


def test_delivery_events_are_strict_and_never_copy_private_content(
    admin_client, db_engine, seeded_user
):
    from altvia.activity import consume_event

    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    assert delivery.claim(db_engine, {account.source_id: account})
    with Session(db_engine) as db:
        queued = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "ticket.delivery_queued")
        )
        state = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "mail.delivery_changed")
        )
        delivery.validate_delivery_event(state)
        assert state.payload["actor_kind"] == "mail_worker"
        assert set(state.payload) == {
            "actor_id",
            "actor_kind",
            "delivery_id",
            "state",
            "error_code",
            "accepted_at",
        }
        queued_id, state_id = queued.event_id, state.event_id
    assert consume_event(db_engine, queued_id, datetime.now(UTC))
    assert consume_event(db_engine, state_id, datetime.now(UTC))
    assert not consume_event(db_engine, state_id, datetime.now(UTC))
    activity = admin_client.get(path + "/activity").json()["items"]
    assert any(e["event_type"] == "ticket.delivery_queued" for e in activity)
    with Session(db_engine) as db:
        state = db.get(OutboxEvent, state_id)
        state.payload = {**state.payload, "body_text": "private"}
        with pytest.raises(ValueError):
            delivery.validate_delivery_event(state)
        assert state.payload["actor_kind"] == "mail_worker"


def test_empty_mail_migration_roundtrip_keeps_prior_public_drafts(
    admin_client, db_engine, seeded_user
):
    from alembic import command
    from alembic.config import Config

    refs = setup(admin_client, db_engine, seeded_user)
    path = ticket(admin_client, refs)
    message = append(admin_client, path).json()["message_id"]
    pre_sla_ticket(db_engine, path)
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000021")
    command.upgrade(config, "head")
    assert admin_client.get(path + "/messages/" + message).json()["delivery_status"] == "draft"
    assert admin_client.get(path + "/delivery-choices").json()["can_send"] is False


@pytest.mark.parametrize("field", ["delivery_id", "message_id"])
def test_delivery_queued_rejects_null_identity_event(admin_client, db_engine, seeded_user, field):
    from altvia.activity import consume_event

    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    with Session(db_engine) as db, db.begin():
        original = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "ticket.delivery_queued")
        )
        event = OutboxEvent(
            schema_version=1,
            aggregate_type="ticket",
            aggregate_id=original.aggregate_id,
            aggregate_version=original.aggregate_version,
            event_type=original.event_type,
            payload={**original.payload, field: None},
            occurred_at=datetime.now(UTC),
            correlation_id=uuid4().hex,
            next_attempt_at=datetime.now(UTC),
        )
        db.add(event)
        db.flush()
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"


def test_second_delivery_keeps_private_ticket_thread_and_accepted_reference(
    admin_client, db_engine, seeded_user
):
    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    first = enqueue(admin_client, path, message, account, participant)
    current = delivery.claim(
        db_engine, {account.source_id: account}, identifier=UUID(first.json()["delivery_id"])
    )
    frozen = delivery.frozen_delivery(db_engine, current.delivery_id, current.token)
    assert db_engine.pool.checkedout() == 0
    assert delivery.pre_data(db_engine, current.delivery_id, current.token)
    assert db_engine.pool.checkedout() == 0
    assert delivery.finalize(db_engine, current.delivery_id, current.token, "accepted")
    next_message = append(admin_client, path, version=3, body="Second public response").json()[
        "message_id"
    ]
    second = enqueue(admin_client, path, next_message, account, participant, version=4)
    assert second.status_code == 201, second.text
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, UUID(second.json()["delivery_id"]))
        original = BytesParser(policy=policy.default).parsebytes(frozen.wire)
        later = BytesParser(policy=policy.default).parsebytes(row.wire)
        assert later["X-Altvia-Thread"] == original["X-Altvia-Thread"]
        assert later["Message-ID"] != original["Message-ID"]
        assert later["In-Reply-To"] == original["Message-ID"]
        assert later["References"] == original["Message-ID"]


def test_sql_cannot_attest_another_contact_or_duplicate_active_requester(
    admin_client, db_engine, seeded_user
):
    from altvia.models import ClientContact, TicketParticipant

    refs, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        other = ClientContact(
            client_id=UUID(refs["client_id"]),
            display_name="Other",
            email_normalized="other@example.test",
        )
        db.add(other)
        db.flush()
        other_id = other.id
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.add(
            TicketParticipant(
                ticket_id=UUID(path.rsplit("/", 1)[1]),
                contact_id=other_id,
                email="other@example.test",
                evidence="synthetic",
                attested_at=datetime.now(UTC),
                active=True,
                version=1,
            )
        )
        db.flush()
    with Session(db_engine) as db, db.begin(), pytest.raises(DBAPIError):
        db.add(
            TicketParticipant(
                ticket_id=UUID(path.rsplit("/", 1)[1]),
                contact_id=UUID(refs["requester_id"]),
                email="requester@example.test",
                evidence="synthetic",
                attested_at=datetime.now(UTC),
                active=True,
                version=1,
            )
        )
        db.flush()


@pytest.mark.parametrize("last_label_length", [31, 60])
def test_every_valid_sender_domain_queues_and_keeps_accepted_references(
    admin_client, db_engine, seeded_user, last_label_length
):
    domain = ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * last_label_length])
    from_email = "x@" + domain
    assert len(domain) in {223, 252} and len(from_email) <= 254
    _, path, message, account, participant = prepared(
        admin_client, db_engine, seeded_user, from_email=from_email
    )
    first = enqueue(admin_client, path, message, account, participant)
    assert first.status_code == 201, first.text
    identifier = UUID(first.json()["delivery_id"])
    current = delivery.claim(db_engine, {account.source_id: account}, identifier=identifier)
    first_wire = delivery.frozen_delivery(db_engine, identifier, current.token)
    assert delivery.pre_data(db_engine, identifier, current.token)
    assert delivery.finalize(db_engine, identifier, current.token, "accepted")
    next_message = append(
        admin_client, path, version=3, body="Followup to accepted long-domain sender"
    ).json()["message_id"]
    second = enqueue(admin_client, path, next_message, account, participant, version=4)
    assert second.status_code == 201, second.text
    with Session(db_engine) as db:
        original = db.get(OutboundMessage, identifier)
        later = db.get(OutboundMessage, UUID(second.json()["delivery_id"]))
        parsed = BytesParser(policy=policy.default).parsebytes(later.wire)
        assert len(original.smtp_message_id) == len(domain) + 35
        assert parsed["References"] == original.smtp_message_id
        assert parsed["In-Reply-To"] == original.smtp_message_id
        assert BytesParser(policy=policy.default).parsebytes(first_wire.wire)["From"] == from_email
