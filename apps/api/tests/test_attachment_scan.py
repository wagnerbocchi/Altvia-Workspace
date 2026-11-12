"""Real DB-clock scan fencing; controlled socket results are not signed AV proof."""

import importlib.util
from datetime import timedelta
from threading import Event
from uuid import UUID

import pytest
from file_core_support import file_path, file_services
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_attachments import upload
from test_file_scan_transport import daemon
from test_team_api import admin_client
from test_tickets import setup, ticket

__all__ = ["admin_client", "file_services"]

pytestmark = pytest.mark.usefixtures("file_services")


def uploaded(client, engine, employee):
    parent = ticket(client, setup(client, engine, employee))
    response = upload(client, parent)
    assert response.status_code == 201
    return parent, UUID(response.json()["attachment_id"])


def scanner_owner():
    assert importlib.util.find_spec("altvia.attachment_scan") is not None, (
        "durable scanner owner missing"
    )
    from altvia import attachment_scan

    return attachment_scan


def test_scan_claim_fences_duplicate_and_only_current_clean_releases(
    admin_client, db_engine, seeded_user, tmp_path
):
    scan = scanner_owner()
    from altvia.file_storage import S3Store
    from altvia.file_storage_owner import load_storage
    from altvia.models import Attachment, AttachmentScanAttempt

    parent, identifier = uploaded(admin_client, db_engine, seeded_user)
    claim = scan.claim(db_engine, identifier)
    assert claim is not None and claim.generation == 1 and claim.attempt == 1
    assert (claim.lease_until - claim.db_now).total_seconds() == 60
    assert scan.claim(db_engine, identifier) is None
    storage = S3Store(load_storage(file_path("scanner")))
    version = f"ClamAV 1.4.6/28181/{claim.db_now.strftime('%a %b %d %H:%M:%S %Y')}\0".encode()
    with daemon(tmp_path, [version, b"stream: OK\0", version]) as (client, received):
        assert scan.run_claim(db_engine, claim, storage, client, Event())
    assert received == [b"private text\n"]
    storage.close()
    with Session(db_engine) as db:
        row = db.get(Attachment, identifier)
        assert row.state == "ready" and row.version == 3
        attempt = db.get(AttachmentScanAttempt, (identifier, 1, 1))
        assert attempt.engine == "1.4.6" and attempt.database_version == 28181
    content = admin_client.get("/api/v1/attachments/" + str(identifier) + "/content")
    assert content.status_code == 200 and content.content == b"private text\n"
    assert "attachment;" in content.headers["content-disposition"]
    assert admin_client.get(parent).json()["version"] == 1
    assert not scan.finalize(
        db_engine, claim, scan.ScanResult("clean", "clean", "1.4.6", 28181, claim.db_now)
    )


@pytest.mark.parametrize("reason", ["infected", "encrypted", "limit"])
def test_immutable_policy_refusal_is_terminal_not_manually_retried(
    admin_client, db_engine, seeded_user, reason
):
    scan = scanner_owner()
    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    claim = scan.claim(db_engine, identifier)
    result = scan.ScanResult(
        "infected" if reason == "infected" else "failed", reason, "1.4.6", 28181, claim.db_now
    )
    assert scan.finalize(db_engine, claim, result)
    detail = admin_client.get("/api/v1/attachments/" + str(identifier)).json()
    assert detail["state"] == "rejected" and not detail["can_retry_scan"]


def test_finalization_rechecks_definition_age_against_current_database_clock(
    admin_client, db_engine, seeded_user
):
    scan = scanner_owner()
    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    claim = scan.claim(db_engine, identifier)
    date = claim.db_now - timedelta(hours=48) + timedelta(milliseconds=10)
    with db_engine.connect() as db:
        db.execute(text("SELECT pg_sleep(0.03)"))
    assert scan.finalize(db_engine, claim, scan.ScanResult("clean", "clean", "1.4.6", 28181, date))
    assert (
        admin_client.get("/api/v1/attachments/" + str(identifier)).json()["state"] == "quarantine"
    )


def expire(db_engine, identifier):
    # Explicit owner-only fault fixture. Never exposed as a runtime clean/state flag.
    with db_engine.begin() as db:
        db.execute(text("ALTER TABLE attachments DISABLE TRIGGER attachment_guard"))
        db.execute(
            text(
                "UPDATE attachments SET lease_until=clock_timestamp()-interval '1 second' "
                "WHERE id=:id"
            ),
            {"id": identifier},
        )
        db.execute(text("ALTER TABLE attachments ENABLE TRIGGER attachment_guard"))


def test_lost_expired_stopped_generation_and_retry_history(admin_client, db_engine, seeded_user):
    scan = scanner_owner()
    from altvia.models import AttachmentScanAttempt
    from test_team_api import preconditions

    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    late = scan.claim(db_engine, identifier)
    expire(db_engine, identifier)
    assert not scan.finalize(
        db_engine, late, scan.ScanResult("clean", "clean", "1.4.6", 28181, late.db_now)
    )
    assert scan.recover(db_engine) == [identifier]
    with Session(db_engine) as db:
        attempt = db.get(AttachmentScanAttempt, (identifier, 1, 1))
        assert attempt.reason == "lease_expired"
    with db_engine.begin() as db:
        db.execute(text("ALTER TABLE attachments DISABLE TRIGGER attachment_guard"))
        db.execute(
            text("UPDATE attachments SET next_attempt_at=clock_timestamp() WHERE id=:id"),
            {"id": identifier},
        )
        db.execute(text("ALTER TABLE attachments ENABLE TRIGGER attachment_guard"))
    # Eight bounded transient failures; advancing next-attempt is an owner fixture.
    for number in range(2, 9):
        claim = scan.claim(db_engine, identifier)
        assert claim.attempt == number
        assert scan.finalize(db_engine, claim, scan.ScanResult("failed", "unavailable"))
        if number < 8:
            with db_engine.begin() as db:
                db.execute(text("ALTER TABLE attachments DISABLE TRIGGER attachment_guard"))
                db.execute(
                    text("UPDATE attachments SET next_attempt_at=clock_timestamp() WHERE id=:id"),
                    {"id": identifier},
                )
                db.execute(text("ALTER TABLE attachments ENABLE TRIGGER attachment_guard"))
    route = "/api/v1/attachments/" + str(identifier)
    detail = admin_client.get(route).json()
    assert detail["state"] == "failed" and detail["can_retry_scan"]
    headers = preconditions(detail["version"])
    retry = admin_client.post(route + "/scan-retries", json={}, headers=headers)
    assert retry.status_code == 201
    newer = scan.claim(db_engine, identifier)
    assert newer.generation == 2 and newer.attempt == 1
    replay = admin_client.post(route + "/scan-retries", json={}, headers=headers)
    assert replay.status_code == 200 and replay.json() == retry.json()
    assert not scan.finalize(
        db_engine, late, scan.ScanResult("clean", "clean", "1.4.6", 28181, late.db_now)
    )
    with Session(db_engine) as db:
        assert len(list(db.scalars(select(AttachmentScanAttempt)))) == 8


def test_private_file_events_acknowledge_without_shared_activity(
    admin_client, db_engine, seeded_user
):
    from datetime import UTC, datetime

    from altvia.activity import consume_event
    from altvia.models import ActivityEvent, OutboxEvent

    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db:
        event_id = db.scalar(
            select(OutboxEvent.event_id).where(OutboxEvent.aggregate_id == identifier)
        )
    assert consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert (
            db.scalar(select(ActivityEvent).where(ActivityEvent.resource_id == identifier)) is None
        )
        assert db.get(OutboxEvent, event_id).status == "delivered"


def test_worker_file_actor_dispatches_real_redis_and_finite_backlog(
    admin_client, db_engine, seeded_user, tmp_path
):
    import os

    from altvia import worker as worker_owner
    from altvia.config import WorkerSettings
    from altvia.file_storage import S3Store
    from altvia.file_storage_owner import load_storage
    from altvia.worker import build_worker

    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    now = db_engine.connect()
    with now:
        instant = now.scalar(text("SELECT clock_timestamp()"))
    version = f"ClamAV 1.4.6/28181/{instant.strftime('%a %b %d %H:%M:%S %Y')}\0".encode()
    storage = S3Store(load_storage(file_path("scanner")))
    settings = WorkerSettings(
        database_url=db_engine.url.render_as_string(hide_password=False),
        redis_url=os.environ["ALTVIA_REDIS_URL"],
    )
    stop = Event()
    with daemon(tmp_path, [version, b"stream: OK\0", version]) as (scanner, received):
        broker, consumer, _ = build_worker(
            db_engine, settings, file_storage=storage, file_scanner=scanner, stop=stop
        )
        try:
            broker.flush_all()
            broker.client.delete("altvia:file:publisher")
            assert worker_owner.dispatch_file_once(db_engine, broker, stop) == 1
            assert worker_owner.dispatch_file_once(db_engine, broker, stop) == 0
            broker.get_actor("file_scan").send(str(identifier))
            consumer.start()
            broker.join("files", timeout=15000)
            assert received == [b"private text\n"]
        finally:
            stop.set()
            consumer.stop(timeout=5000)
            broker.flush_all()
            broker.client.close()
            storage.close()
    assert admin_client.get("/api/v1/attachments/" + str(identifier)).json()["state"] == "ready"


def test_runtime_scanner_columns_and_api_cannot_release_clean(
    admin_client, db_engine, seeded_user, tmp_path
):
    from altvia.file_storage import S3Store
    from altvia.file_storage_owner import load_storage
    from altvia.provision import provision_runtime
    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError
    from test_runtime_provision import runtime_url

    scan = scanner_owner()
    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    api_url = runtime_url(db_engine)
    worker_url = api_url.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        api_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    worker = create_engine(worker_url, hide_parameters=True)
    api = create_engine(api_url, hide_parameters=True)
    try:
        with worker.connect() as db:
            db.execute(text("SELECT id,object_key,sha256,bytes,state FROM attachments"))
        for statement in [
            "SELECT filename FROM attachments",
            "SELECT purpose FROM attachments",
            "SELECT creator_id FROM attachments",
            "SELECT body_text FROM ticket_notes",
            "SELECT * FROM inbound_mail_variants",
            "SELECT * FROM inbound_mail_previews",
            "SELECT * FROM mail_case_origins",
            "UPDATE attachments SET filename=filename",
            "DELETE FROM attachments",
        ]:
            with worker.begin() as db, pytest.raises(DBAPIError) as denied:
                db.execute(text(statement))
            assert denied.value.orig.sqlstate == "42501"
        for statement in [
            "UPDATE attachments SET state='ready',version=version+1",
            "SELECT * FROM attachment_scan_attempts",
            "INSERT INTO attachment_scan_attempts(attachment_id) VALUES (NULL)",
        ]:
            with api.begin() as db, pytest.raises(DBAPIError):
                db.execute(text(statement))
        owned = scan.claim(worker, identifier)
        assert owned is not None
        version = f"ClamAV 1.4.6/28181/{owned.db_now.strftime('%a %b %d %H:%M:%S %Y')}\0".encode()
        storage = S3Store(load_storage(file_path("scanner")))
        try:
            with daemon(tmp_path, [version, b"stream: OK\0", version]) as (scanner, _):
                assert scan.run_claim(worker, owned, storage, scanner, Event())
        finally:
            storage.close()
    finally:
        worker.dispose()
        api.dispose()


def test_stop_while_final_lock_waits_cannot_publish_clean(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from time import monotonic, sleep

    from altvia import attachment_scan as scan
    from altvia.file_storage import S3Store
    from altvia.file_storage_owner import load_storage

    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    owned = scan.claim(db_engine, identifier)
    version = f"ClamAV 1.4.6/28181/{owned.db_now.strftime('%a %b %d %H:%M:%S %Y')}\0".encode()
    stop = Event()
    storage = S3Store(load_storage(file_path("scanner")))
    with daemon(tmp_path, [version, b"stream: OK\0", version]) as (scanner, received):
        with ThreadPoolExecutor(max_workers=1) as pool:
            with db_engine.begin() as locked:
                locked.execute(
                    text("SELECT id FROM attachments WHERE id=:id FOR UPDATE"), {"id": identifier}
                )
                pid = locked.scalar(text("SELECT pg_backend_pid()"))
                future = pool.submit(scan.run_claim, db_engine, owned, storage, scanner, stop)
                deadline = monotonic() + 8
                blocked = False
                while monotonic() < deadline:
                    with db_engine.connect() as monitor:
                        blocked = monitor.scalar(
                            text(
                                "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                                "WHERE :pid=ANY(pg_blocking_pids(pid)))"
                            ),
                            {"pid": pid},
                        )
                    if blocked:
                        break
                    sleep(0.02)
                assert blocked and received == [b"private text\n"]
                stop.set()
            assert not future.result(timeout=5)
    storage.close()
    assert admin_client.get("/api/v1/attachments/" + str(identifier)).json()["state"] == "scanning"


def test_expired_attempt_recovery_preserves_bounded_backoff(admin_client, db_engine, seeded_user):
    scan = scanner_owner()
    from altvia.models import Attachment

    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    assert scan.claim(db_engine, identifier) is not None
    expire(db_engine, identifier)
    assert scan.recover(db_engine) == [identifier]
    with Session(db_engine) as db:
        row = db.get(Attachment, identifier)
        now = db.scalar(text("SELECT clock_timestamp()"))
        assert 28 <= (row.next_attempt_at - now).total_seconds() <= 30
    assert scan.claim(db_engine, identifier) is None


def test_blackholed_socket_stop_is_bounded_and_cannot_release(
    admin_client, db_engine, seeded_user, tmp_path
):
    import socket
    from concurrent.futures import ThreadPoolExecutor
    from threading import Thread

    from altvia.file_scan_transport import ClamClient
    from altvia.file_settings import ScannerSettings
    from altvia.file_storage import S3Store
    from altvia.file_storage_owner import load_storage

    scan = scanner_owner()
    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    owned = scan.claim(db_engine, identifier)
    socket_path = tmp_path / "blackhole.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(1)
    entered, release, stop = Event(), Event(), Event()

    def blackhole():
        with listener.accept()[0] as connection:
            connection.recv(1024)
            entered.set()
            release.wait(8)

    server = Thread(target=blackhole)
    server.start()
    storage = S3Store(load_storage(file_path("scanner")))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            work = pool.submit(
                scan.run_claim,
                db_engine,
                owned,
                storage,
                ClamClient(ScannerSettings(socket_path=socket_path)),
                stop,
            )
            assert entered.wait(5)
            stop.set()
            assert not work.result(timeout=6)
        assert (
            admin_client.get("/api/v1/attachments/" + str(identifier)).json()["state"] == "scanning"
        )
    finally:
        release.set()
        server.join(timeout=2)
        listener.close()
        storage.close()
    assert not server.is_alive()


def test_definition_age_crossing_while_waiting_for_file_lock_is_not_ready(
    admin_client, db_engine, seeded_user
):
    from concurrent.futures import ThreadPoolExecutor
    from time import sleep

    scan = scanner_owner()
    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    owned = scan.claim(db_engine, identifier)
    fresh = scan.ScanResult(
        "clean",
        "clean",
        "1.4.6",
        28181,
        owned.db_now - timedelta(hours=48) + timedelta(milliseconds=200),
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        with db_engine.begin() as locked:
            locked.execute(
                text("SELECT id FROM attachments WHERE id=:id FOR UPDATE"), {"id": identifier}
            )
            waiting = pool.submit(scan.finalize, db_engine, owned, fresh)
            sleep(0.3)
        assert waiting.result(timeout=5)
    assert (
        admin_client.get("/api/v1/attachments/" + str(identifier)).json()["state"] == "quarantine"
    )


def test_scan_history_rejects_forged_lease_and_unbounded_reason(
    admin_client, db_engine, seeded_user
):
    from sqlalchemy.exc import DBAPIError

    scan = scanner_owner()
    _, identifier = uploaded(admin_client, db_engine, seeded_user)
    owned = scan.claim(db_engine, identifier)
    statement = text(
        "INSERT INTO attachment_scan_attempts(attachment_id,generation,attempt,token,"
        "claimed_at,lease_until,finished_at,disposition,reason) VALUES "
        "(:id,:generation,:attempt,:token,:claimed,:until,clock_timestamp(),'failed',:reason)"
    )
    values = {
        "id": identifier,
        "generation": owned.generation,
        "attempt": owned.attempt,
        "token": owned.token,
        "claimed": owned.db_now,
        "until": owned.lease_until,
        "reason": "unbounded diagnostic",
    }
    with db_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(statement, values)
    with db_engine.begin() as db, pytest.raises(DBAPIError):
        from uuid import uuid4

        db.execute(statement, {**values, "token": uuid4(), "reason": "unavailable"})
