"""SQL/Redis/loopback-TLS integration of optional mail delivery workers."""

import secrets
import time
from datetime import UTC, datetime, timedelta
from threading import Thread
from uuid import UUID

import pytest
from altvia import mail_delivery, provision
from altvia.mail_intake import register_source
from altvia.mail_participants import attest_requester, register_sender, revoke_requester
from altvia.models import OutboundMessage
from altvia.smtp_transport import ActiveTransports, deliver_once
from altvia.worker import build_worker, dispatch_mail_once
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from test_mail_delivery import enqueue
from test_smtp_transport import certificate, smtp_server
from test_team_api import admin_client
from test_ticket_messages import append
from test_tickets import setup, ticket
from test_worker import broker_settings

__all__ = ["admin_client", "broker_settings", "certificate"]


def queued(client, engine, user, account):
    refs = setup(client, engine, user)
    path = ticket(client, refs)
    message = append(client, path).json()["message_id"]
    with Session(engine) as db, db.begin():
        source = register_source(db, "synthetic_smtp", UUID(refs["queue_id"]))
        account = account.model_copy(update={"source_id": source.id})
        register_sender(db, account)
        participant = attest_requester(db, UUID(path.rsplit("/", 1)[1]), 2, "synthetic-only")
        participant_id = participant.id
    result = enqueue(client, path, message, account, participant_id)
    assert result.status_code == 201, result.text
    return UUID(result.json()["delivery_id"]), account, participant_id


def state(engine, identifier):
    with Session(engine) as db:
        row = db.get(OutboundMessage, identifier)
        return row.state, row.attempts, row.wire, row.smtp_message_id, row.last_error_code


def test_real_two_workers_duplicate_wakeups_and_lost_broker_are_single_send(
    certificate, admin_client, db_engine, seeded_user, broker_settings
):
    with smtp_server(certificate) as (account, _, messages, _):
        identifier, account, _ = queued(admin_client, db_engine, seeded_user, account)
        worker_url = db_engine.url.set(username="altvia_worker", password=secrets.token_urlsafe(24))
        app_url = db_engine.url.set(username="altvia_app", password=secrets.token_urlsafe(24))
        provision.provision_runtime(
            db_engine,
            app_url.render_as_string(hide_password=False),
            worker_url.render_as_string(hide_password=False),
        )
        engine = create_engine(worker_url, hide_parameters=True)
        active1, active2 = ActiveTransports(), ActiveTransports()
        accounts = {account.source_id: account}
        broker1, worker1, _ = build_worker(
            engine, broker_settings, accounts=accounts, active=active1
        )
        broker2, worker2, _ = build_worker(
            engine, broker_settings, accounts=accounts, active=active2
        )
        try:
            assert dispatch_mail_once(engine, broker1, accounts) == 1
            broker1.client.flushdb()  # Real broker loss before actors start.
            assert state(db_engine, identifier)[:2] == ("queued", 0)
            assert dispatch_mail_once(engine, broker2, accounts) == 1
            actor1, actor2 = broker1.get_actor("mail_delivery"), broker2.get_actor("mail_delivery")
            for _ in range(3):
                actor1.send(str(identifier))
                actor2.send(str(identifier))
            assert str(identifier) in actor1.message(str(identifier)).encode().decode()
            worker1.start()
            worker2.start()
            for _ in range(100):
                if state(db_engine, identifier)[0] == "accepted":
                    break
                time.sleep(0.05)
            else:
                pytest.fail("real worker failed to persist SMTP acceptance")
            broker1.join("mail", timeout=5000)
            assert state(db_engine, identifier)[:2] == ("accepted", 1)
            assert messages == [state(db_engine, identifier)[2]]
            assert not deliver_once(engine, identifier, accounts)
        finally:
            active1.cancel()
            active2.cancel()
            worker1.stop(timeout=5000)
            worker2.stop(timeout=5000)
            broker1.client.close()
            broker2.client.close()
            engine.dispose()


@pytest.mark.parametrize(
    "fault,want",
    [("disconnect", "queued"), ("lost", "uncertain"), ("final4", "queued"), ("final5", "failed")],
)
def test_real_wire_result_persisted_and_uncertain_never_reclaimed(
    certificate, admin_client, db_engine, seeded_user, fault, want
):
    with smtp_server(certificate, fault=fault) as (account, _, messages, _):
        identifier, account, _ = queued(admin_client, db_engine, seeded_user, account)
        accounts = {account.source_id: account}
        assert deliver_once(db_engine, identifier, accounts)
        snapshot = state(db_engine, identifier)
        assert snapshot[:2] == (want, 1)
        if want in {"uncertain", "failed"}:
            assert (
                mail_delivery.claim(db_engine, accounts, datetime.now(UTC) + timedelta(days=1))
                is None
            )
            assert not deliver_once(db_engine, identifier, accounts)
            assert len(messages) == 1


def test_namespace_change_no_connection_password_rotation_keeps_frozen_snapshot(
    certificate, admin_client, db_engine, seeded_user
):
    with smtp_server(certificate) as (account, commands, messages, _):
        identifier, account, _ = queued(admin_client, db_engine, seeded_user, account)
        original = state(db_engine, identifier)
        changed = account.model_copy(update={"username": account.username.__class__("changed")})
        assert not deliver_once(db_engine, identifier, {account.source_id: changed})
        assert not deliver_once(db_engine, identifier, {})
        assert commands == [] and state(db_engine, identifier) == original
        rotated = account.model_copy(update={"password": account.password.__class__("rotated")})
        assert deliver_once(db_engine, identifier, {account.source_id: rotated})
        assert state(db_engine, identifier)[0] == "accepted"
        assert messages == [original[2]] and state(db_engine, identifier)[3] == original[3]


def test_revoked_after_rcpt_is_rechecked_before_data(
    certificate, admin_client, db_engine, seeded_user
):
    participant = None

    def revoke():
        with Session(db_engine) as db, db.begin():
            revoke_requester(db, participant, 1)

    with smtp_server(certificate, before_data=revoke) as (account, commands, messages, _):
        identifier, account, participant = queued(admin_client, db_engine, seeded_user, account)
        assert not deliver_once(db_engine, identifier, {account.source_id: account})
        assert state(db_engine, identifier)[0] == "failed"
        assert state(db_engine, identifier)[4] == "eligibility_revoked"
        assert messages == [] and not any(line.upper().startswith(b"DATA") for _, line in commands)


@pytest.mark.parametrize("fault,want", [("greeting_stall", "queued"), ("data_stall", "uncertain")])
def test_shutdown_cancels_socket_and_persists_safe_or_uncertain_stage(
    certificate, admin_client, db_engine, seeded_user, fault, want
):
    with smtp_server(certificate, fault=fault) as (account, _, _, waiting):
        identifier, account, _ = queued(admin_client, db_engine, seeded_user, account)
        active = ActiveTransports()
        thread = Thread(
            target=deliver_once,
            args=(db_engine, identifier, {account.source_id: account}),
            kwargs={"active": active},
        )
        thread.start()
        assert waiting.wait(3)
        started = time.monotonic()
        active.cancel()
        thread.join(2)
        assert not thread.is_alive() and time.monotonic() - started < 2
        assert state(db_engine, identifier)[:2] == (want, 1)


def test_expired_transmitting_restart_recovers_uncertain_without_wire(
    certificate, admin_client, db_engine, seeded_user
):
    with smtp_server(certificate) as (account, commands, messages, _):
        identifier, account, _ = queued(admin_client, db_engine, seeded_user, account)
        accounts = {account.source_id: account}
        claimed = mail_delivery.claim(db_engine, accounts, identifier=identifier)
        assert mail_delivery.pre_data(db_engine, identifier, claimed.token)
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE outbound_messages SET lease_until=clock_timestamp()-interval '1 second'"
                )
            )
        assert mail_delivery.recover(db_engine) == [identifier]
        assert state(db_engine, identifier)[0] == "uncertain"
        assert not deliver_once(db_engine, identifier, accounts)
        assert commands == [] and messages == []


def test_worker_sql_bounds_are_session_local_and_rollback_on_timeout(db_engine):
    from altvia.config import WorkerSettings
    from altvia.database import make_engine
    from sqlalchemy.exc import DBAPIError

    settings = WorkerSettings(
        database_url=db_engine.url.render_as_string(hide_password=False),
        redis_url="redis://:synthetic@localhost/0",
    )
    engine = make_engine(settings, worker_timeouts=True)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SHOW statement_timeout")) == "5s"
            assert connection.scalar(text("SHOW lock_timeout")) == "3s"
        with engine.begin() as connection, pytest.raises(DBAPIError):
            connection.execute(text("SELECT pg_sleep(6)"))
        with engine.begin() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
        with db_engine.connect() as connection:
            assert connection.scalar(text("SHOW statement_timeout")) == "0"
    finally:
        engine.dispose()


def test_safe_retry_preserves_frozen_bytes_across_password_rotation(
    certificate, admin_client, db_engine, seeded_user
):
    with smtp_server(certificate, fault="once_temporary") as (account, _, messages, _):
        identifier, account, _ = queued(admin_client, db_engine, seeded_user, account)
        assert deliver_once(db_engine, identifier, {account.source_id: account})
        original = state(db_engine, identifier)
        assert original[:2] == ("queued", 1)
        assert not deliver_once(db_engine, identifier, {account.source_id: account})  # Backoff.
        with db_engine.begin() as connection:
            connection.execute(
                text("UPDATE outbound_messages SET next_attempt_at=clock_timestamp()")
            )
        account = account.model_copy(update={"password": account.password.__class__("rotated")})
        assert deliver_once(db_engine, identifier, {account.source_id: account})
        assert state(db_engine, identifier)[:2] == ("accepted", 2)
        assert messages == [original[2], original[2]]
        assert state(db_engine, identifier)[3] == original[3]


def test_dispatch_backpressure_limits_duplicate_wakeups(
    certificate, admin_client, db_engine, seeded_user, broker_settings
):
    with smtp_server(certificate) as (account, commands, _, _):
        _, account, _ = queued(admin_client, db_engine, seeded_user, account)
        accounts = {account.source_id: account}
        broker, _, _ = build_worker(db_engine, broker_settings, accounts=accounts)
        try:
            for _ in range(8):
                broker.client.delete("altvia:mail:publisher")
                assert dispatch_mail_once(db_engine, broker, accounts) == 1
            broker.client.delete("altvia:mail:publisher")
            assert dispatch_mail_once(db_engine, broker, accounts) == 0
            assert broker.do_qsize("mail") == 8
            assert commands == []
        finally:
            broker.client.close()


def test_predata_lock_timeout_retains_safe_lease_for_restart(
    certificate, admin_client, db_engine, seeded_user
):
    from altvia import management
    from altvia.config import WorkerSettings
    from altvia.database import make_engine
    from sqlalchemy.exc import DBAPIError

    with smtp_server(certificate) as (account, commands, messages, _):
        identifier, account, _ = queued(admin_client, db_engine, seeded_user, account)
        accounts = {account.source_id: account}
        claimed = mail_delivery.claim(db_engine, accounts, identifier=identifier)
        config = WorkerSettings(
            database_url=db_engine.url.render_as_string(hide_password=False),
            redis_url="redis://:synthetic@localhost/0",
        )
        engine = make_engine(config, worker_timeouts=True)
        try:
            with Session(db_engine) as holder, holder.begin():
                management.lock_identity_writes(holder)
                began = time.monotonic()
                with pytest.raises(DBAPIError):
                    mail_delivery.pre_data(engine, identifier, claimed.token)
                assert 2 <= time.monotonic() - began < 5
            assert state(db_engine, identifier)[:2] == ("preparing", 1)
            with db_engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE outbound_messages SET "
                        "lease_until=clock_timestamp()-interval '1 second'"
                    )
                )
            assert mail_delivery.recover(engine) == [identifier]
            assert state(db_engine, identifier)[:2] == ("queued", 1)
            assert commands == [] and messages == []
        finally:
            engine.dispose()


@pytest.mark.parametrize("transmitting,want", [(False, "queued"), (True, "uncertain")])
def test_restart_without_smtp_config_still_recovers_expired_sql_stage(
    certificate, admin_client, db_engine, seeded_user, broker_settings, transmitting, want
):
    with smtp_server(certificate) as (account, commands, messages, _):
        identifier, account, _ = queued(admin_client, db_engine, seeded_user, account)
        claimed = mail_delivery.claim(
            db_engine, {account.source_id: account}, identifier=identifier
        )
        if transmitting:
            assert mail_delivery.pre_data(db_engine, identifier, claimed.token)
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE outbound_messages SET lease_until=clock_timestamp()-interval '1 second'"
                )
            )
        broker, _, _ = build_worker(db_engine, broker_settings, accounts={})
        try:
            assert dispatch_mail_once(db_engine, broker, {}) == 0
            assert state(db_engine, identifier)[:2] == (want, 1)
            assert commands == [] and messages == []
        finally:
            broker.client.close()
