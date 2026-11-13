"""Reviewed MIME2 freezes verified actual S3 bytes before real TLS SMTP."""

from contextlib import contextmanager
from email import policy
from email.parser import BytesParser
from uuid import UUID, uuid4

import pytest
from altvia.file_storage import S3Store
from file_core_support import file_services
from sqlalchemy import text
from test_attachment_links import post, ready
from test_mail_cases import context
from test_mail_delivery import prepared
from test_smtp_transport import certificate, smtp_server
from test_team_api import admin_client, preconditions, sign_in

__all__ = ["admin_client", "file_services", "certificate", "context"]
pytestmark = pytest.mark.usefixtures("file_services")


def prepared_files(client, engine, user, tmp_path, contents=None):
    refs, path, _, account, participant = prepared(client, engine, user)
    contents = contents or [
        ("primeiro.txt", b"first\n"),
        ("relatorio \u00e7.log", b"line\x20two\n"),
    ]
    ids = [
        ready(client, engine, path, tmp_path, filename=name, content=data, version=2)
        for name, data in contents
    ]
    message = post(client, path, ids, version=2)
    assert message.status_code == 201, message.text
    return refs, path, message.json()["message_id"], account, participant, ids, contents


def send(client, path, message, account, participant, ids, *, key=None, version=3, omitted=False):
    body = {"source_id": str(account.source_id), "participant_id": str(participant)}
    if not omitted:
        body["attachment_ids"] = ids
    return client.post(
        path + "/messages/" + message + "/delivery", json=body, headers=preconditions(version, key)
    )


def test_visible_incoming_file_never_forwards_or_changes_frozen_wire(
    admin_client, db_engine, context, tmp_path, monkeypatch
):
    from altvia.mail_participants import attest_requester
    from sqlalchemy.orm import Session
    from test_attachments import controlled_ready
    from test_mail_case_file_api import published
    from test_mail_promotion import promote, sender

    case, asset = published(db_engine, context)
    controlled_ready(admin_client, db_engine, asset.id, tmp_path)
    assert admin_client.get(f"/api/v1/attachments/{asset.id}").json()["can_download"]
    receipt = promote(admin_client, case.case_id).json()
    path = "/api/v1/tickets/" + receipt["ticket_id"]
    with Session(db_engine) as db, db.begin():
        participant = attest_requester(db, UUID(receipt["ticket_id"]), 2, "synthetic:proof").id
    account = sender(db_engine, context)
    message_id = post(admin_client, path, [], version=2).json()["message_id"]
    monkeypatch.setattr(
        S3Store, "verified_spool", lambda *a, **k: pytest.fail("incoming forwarded")
    )
    refused = send(admin_client, path, message_id, account, participant, [str(asset.id)])
    assert refused.status_code == 409, refused.text
    key = uuid4().hex
    sent = send(admin_client, path, message_id, account, participant, [], key=key, omitted=True)
    assert sent.status_code == 201, sent.text
    with db_engine.connect() as db:
        frozen = db.execute(text("SELECT wire,wire_format FROM outbound_messages")).one()
    assert frozen.wire_format == 1 and b"private file" not in frozen.wire
    assert asset.filename.encode() not in frozen.wire
    replay = send(admin_client, path, message_id, account, participant, [], key=key, omitted=True)
    assert replay.status_code == 200 and replay.json() == sent.json()
    with db_engine.connect() as db:
        assert db.execute(text("SELECT wire,wire_format FROM outbound_messages")).one() == frozen


def test_review_freezes_exact_ordered_mime_and_replay_never_refetches(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch
):
    _, path, message, account, participant, ids, contents = prepared_files(
        admin_client, db_engine, seeded_user, tmp_path
    )
    actual = S3Store.verified_spool
    gets = []

    @contextmanager
    def observed(self, *args, **kwargs):
        gets.append(args[0])
        with actual(self, *args, **kwargs) as source:
            yield source

    monkeypatch.setattr(S3Store, "verified_spool", observed)
    assert (
        send(admin_client, path, message, account, participant, ids, omitted=True).status_code
        == 409
    )
    assert send(admin_client, path, message, account, participant, ids[::-1]).status_code == 409
    assert gets == []
    key = uuid4().hex
    result = send(admin_client, path, message, account, participant, ids, key=key)
    assert result.status_code == 201, result.text
    assert len(gets) == 2
    assert (
        send(admin_client, path, message, account, participant, ids, key=key).json()
        == result.json()
    )
    assert len(gets) == 2
    assert post(admin_client, path, [], version=4).status_code == 201
    replay = send(admin_client, path, message, account, participant, ids, key=key)
    assert replay.status_code == 200 and replay.json() == result.json()
    assert len(gets) == 2
    with db_engine.connect() as db:
        row = db.execute(
            text("SELECT wire,wire_format FROM outbound_messages WHERE id=:id"),
            {"id": UUID(result.json()["delivery_id"])},
        ).one()
    parsed = BytesParser(policy=policy.default).parsebytes(row.wire)
    assert row.wire_format == 2 and parsed.get_content_type() == "multipart/mixed"
    parts = list(parsed.iter_attachments())
    assert [(p.get_filename(), p.get_payload(decode=True)) for p in parts] == contents
    assert parsed.get_body(("plain",)).get_content().strip() == "Linked text"


def test_unauthorized_and_revoked_during_actual_prefetch_never_freeze(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch
):
    _, path, message, account, participant, ids, _ = prepared_files(
        admin_client, db_engine, seeded_user, tmp_path
    )
    actual = S3Store.verified_spool
    gets = []

    @contextmanager
    def revoked(self, *args, **kwargs):
        gets.append(args[0])
        with actual(self, *args, **kwargs) as source:
            with db_engine.begin() as db:
                db.execute(text("SET LOCAL lock_timeout='1s'"))
                db.execute(
                    text("DELETE FROM client_access_grants WHERE user_id=:user"),
                    {"user": seeded_user},
                )
            yield source

    monkeypatch.setattr(S3Store, "verified_spool", revoked)
    sign_in(admin_client, "viewer@example.test")
    assert send(admin_client, path, message, account, participant, ids).status_code == 403
    assert not gets
    sign_in(admin_client, "employee@example.test")
    assert send(admin_client, path, message, account, participant, ids).status_code == 404
    assert gets
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM outbound_messages")) == 0
        assert (
            db.scalar(
                text("SELECT version FROM tickets WHERE id=:id"),
                {"id": UUID(path.rsplit("/", 1)[1])},
            )
            == 3
        )


def test_storage_failure_and_corruption_publish_nothing(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch
):
    from altvia.file_storage import StorageError

    _, path, message, account, participant, ids, _ = prepared_files(
        admin_client, db_engine, seeded_user, tmp_path
    )

    @contextmanager
    def failed(*args, **kwargs):
        raise StorageError("controlled_failure")
        yield

    with monkeypatch.context() as patch:
        patch.setattr(S3Store, "verified_spool", failed)
        result = send(admin_client, path, message, account, participant, ids)
        assert result.status_code == 503 and result.headers["retry-after"] == "5"
    # Preserve the actual object and metadata, but address a deliberately absent immutable key.
    with db_engine.begin() as db:
        db.execute(text("ALTER TABLE attachments DISABLE TRIGGER attachment_guard"))
        db.execute(
            text("UPDATE attachments SET sha256=repeat('0',64) WHERE id=:id"), {"id": UUID(ids[0])}
        )
        db.execute(text("ALTER TABLE attachments ENABLE TRIGGER attachment_guard"))
    assert send(admin_client, path, message, account, participant, ids).status_code == 503
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM outbound_messages")) == 0
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM idempotency_records WHERE route LIKE 'ticket-delivery:%'"
                )
            )
            == 0
        )
    assert admin_client.get(path).json()["version"] == 3


def test_private_purpose_and_invalid_review_do_not_fetch(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch
):
    from test_ticket_notes import configure

    _, path, message, account, participant, ids, _ = prepared_files(
        admin_client, db_engine, seeded_user, tmp_path
    )
    configure(
        admin_client, {"queue_id": admin_client.get(path).json()["queue_id"]}, seeded_user, "write"
    )
    note = ready(admin_client, db_engine, path, tmp_path, purpose="note", version=3)

    def forbidden(*args, **kwargs):
        pytest.fail("Storage accessed before review authorization")

    monkeypatch.setattr(S3Store, "verified_spool", forbidden)
    assert post(admin_client, path, [note], version=3).status_code == 404
    assert send(admin_client, path, message, account, participant, [note]).status_code == 409
    for selection in [None, ids * 2, [str(uuid4()) for _ in range(21)]]:
        assert send(admin_client, path, message, account, participant, selection).status_code == 422
    assert send(admin_client, path, message, account, participant, []).status_code == 409


def test_busy_and_parent_change_during_prefetch_hold_no_database_lock(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    _, path, message, account, participant, ids, _ = prepared_files(
        admin_client, db_engine, seeded_user, tmp_path
    )
    entered, release = Event(), Event()
    actual = S3Store.verified_spool

    @contextmanager
    def blocked(self, *args, **kwargs):
        with actual(self, *args, **kwargs) as source:
            entered.set()
            assert release.wait(8)
            yield source

    monkeypatch.setattr(S3Store, "verified_spool", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(send, admin_client, path, message, account, participant, ids)
        try:
            assert entered.wait(5)
            assert send(admin_client, path, message, account, participant, ids).status_code == 503
            # Real content write needs identity and parent locks and must finish while S3 waits.
            assert post(admin_client, path, [], version=3).status_code == 201
        finally:
            release.set()
        assert first.result(timeout=8).status_code == 409
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM outbound_messages")) == 0


@pytest.mark.parametrize(
    "fault,want,attempts",
    [(None, "accepted", 1), ("lost", "uncertain", 1), ("once_temporary", "accepted", 2)],
)
def test_actual_tls_worker_sends_only_frozen_mime(
    certificate, admin_client, db_engine, seeded_user, tmp_path, monkeypatch, fault, want, attempts
):
    import secrets

    from altvia import provision
    from altvia.mail_intake import register_source
    from altvia.mail_participants import attest_requester, register_sender
    from altvia.smtp_transport import deliver_once
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from test_tickets import setup, ticket

    contents = [("second.log", b".dot\n"), ("arquivo \u00e7.txt", b"exact bytes\n")]
    with smtp_server(certificate, fault=fault) as (account, commands, messages, _):
        refs = setup(admin_client, db_engine, seeded_user)
        path = ticket(admin_client, refs)
        ids = [
            ready(admin_client, db_engine, path, tmp_path, filename=name, content=data)
            for name, data in contents
        ]
        message = post(admin_client, path, ids).json()["message_id"]
        with Session(db_engine) as db, db.begin():
            source = register_source(db, "synthetic_files", UUID(refs["queue_id"]))
            account = account.model_copy(update={"source_id": source.id})
            register_sender(db, account)
            participant = attest_requester(db, UUID(path.rsplit("/", 1)[1]), 2, "synthetic-only").id
        result = send(admin_client, path, message, account, participant, ids, version=2)
        assert result.status_code == 201, result.text
        identifier = UUID(result.json()["delivery_id"])
        with db_engine.connect() as db:
            wire = db.scalar(
                text("SELECT wire FROM outbound_messages WHERE id=:id"), {"id": identifier}
            )

        def forbidden(*args, **kwargs):
            pytest.fail("Worker fetched S3 after freeze")

        monkeypatch.setattr(S3Store, "verified_spool", forbidden)
        worker_url = db_engine.url.set(username="altvia_worker", password=secrets.token_urlsafe(24))
        app_url = db_engine.url.set(username="altvia_app", password=secrets.token_urlsafe(24))
        provision.provision_runtime(
            db_engine,
            app_url.render_as_string(hide_password=False),
            worker_url.render_as_string(hide_password=False),
        )
        worker_engine = create_engine(worker_url, hide_parameters=True)
        try:
            assert deliver_once(worker_engine, identifier, {account.source_id: account})
        finally:
            worker_engine.dispose()
        if attempts == 2:
            with db_engine.begin() as db:
                db.execute(
                    text(
                        "UPDATE outbound_messages SET "
                        "next_attempt_at=clock_timestamp() WHERE id=:id"
                    ),
                    {"id": identifier},
                )
            assert deliver_once(db_engine, identifier, {account.source_id: account})
        assert not deliver_once(db_engine, identifier, {account.source_id: account})
        with db_engine.connect() as db:
            row = db.execute(
                text("SELECT state,wire,attempts FROM outbound_messages WHERE id=:id"),
                {"id": identifier},
            ).one()
        assert row.state == want and row.attempts == attempts and row.wire == wire
        assert messages == [wire] * attempts
        assert len([line for _, line in commands if line.strip().upper() == b"DATA"]) == attempts
        parsed = BytesParser(policy=policy.default).parsebytes(messages[0])
        assert [
            (part.get_filename(), part.get_payload(decode=True))
            for part in parsed.iter_attachments()
        ] == contents


def test_format2_encoded_limit_and_legacy_builder_bound():
    from datetime import UTC, datetime

    from altvia.mail_delivery import MAX_MIME_BYTES, PublicFile, build_mime_wire, build_wire

    wire = build_wire(
        "from@example.test",
        "to@example.test",
        "subject",
        "body",
        "<id@example.test>",
        "token",
        datetime(2026, 11, 12, tzinfo=UTC),
        [],
    )
    expected = (
        b"From: from@example.test\r\nTo: to@example.test\r\nSubject: subject\r\n"
        b"Message-ID: <id@example.test>\r\nDate: Thu, 12 Nov 2026 00:00:00 +0000\r\n"
        b'X-Altvia-Thread: token\r\nContent-Type: text/plain; charset="utf-8"\r\n'
        b"Content-Transfer-Encoding: quoted-printable\r\nMIME-Version: 1.0\r\n\r\nbody\r\n"
    )
    assert wire == expected
    small = build_mime_wire(
        wire, [PublicFile(uuid4(), "small.txt", "text/plain", b"x" * (18 * 1024 * 1024))]
    )
    assert len(small) < MAX_MIME_BYTES
    with pytest.raises(ValueError, match="message_too_large"):
        build_mime_wire(
            wire, [PublicFile(uuid4(), "large.txt", "text/plain", b"x" * (19 * 1024 * 1024))]
        )
    with pytest.raises(ValueError, match="message_too_large"):
        build_mime_wire(
            wire, [PublicFile(uuid4(), "huge.txt", "text/plain", b"x" * (MAX_MIME_BYTES + 1))]
        )


@pytest.mark.parametrize(
    "mutation,status",
    [
        ("UPDATE client_contacts SET active=false", 409),
        ("DELETE FROM sessions WHERE user_id=:user", 401),
    ],
)
def test_current_requester_and_session_rechecked_after_actual_s3(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch, mutation, status
):
    _, path, message, account, participant, ids, _ = prepared_files(
        admin_client, db_engine, seeded_user, tmp_path
    )
    actual = S3Store.verified_spool

    @contextmanager
    def changed(self, *args, **kwargs):
        with actual(self, *args, **kwargs) as source:
            with db_engine.begin() as db:
                db.execute(text("SET LOCAL lock_timeout='1s'"))
                db.execute(text(mutation), {"user": seeded_user})
            yield source

    monkeypatch.setattr(S3Store, "verified_spool", changed)
    assert send(admin_client, path, message, account, participant, ids).status_code == status
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM outbound_messages")) == 0


@pytest.mark.parametrize("megabytes,expected_gets", [(9, 0), (7, 3)])
def test_raw_and_encoded_api_bounds_are_atomic(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch, megabytes, expected_gets
):
    contents = [(f"file-{i}.txt", b"x" * (megabytes * 1024 * 1024)) for i in range(3)]
    _, path, message, account, participant, ids, _ = prepared_files(
        admin_client, db_engine, seeded_user, tmp_path, contents
    )
    actual = S3Store.verified_spool
    gets = []

    @contextmanager
    def observed(self, *args, **kwargs):
        gets.append(args[0])
        with actual(self, *args, **kwargs) as source:
            yield source

    monkeypatch.setattr(S3Store, "verified_spool", observed)
    result = send(admin_client, path, message, account, participant, ids)
    assert result.status_code == 409, result.text
    assert len(gets) == expected_gets
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM outbound_messages")) == 0
        assert db.scalar(text("SELECT count(*) FROM ticket_mail_threads")) == 0
        assert (
            db.scalar(
                text("SELECT count(*) FROM outbox_events WHERE event_type='ticket.delivery_queued'")
            )
            == 0
        )
    assert admin_client.get(path).json()["version"] == 3


def test_legacy_migration_retains_wire_receipt_timestamps_and_fingerprints(
    admin_client, db_engine, seeded_user
):
    import hashlib
    import json

    from alembic import command
    from alembic.config import Config
    from test_mail_delivery import enqueue

    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    key = uuid4().hex
    receipt = enqueue(admin_client, path, message, account, participant, key)
    assert receipt.status_code == 201
    with db_engine.connect() as db:
        before = db.execute(
            text("SELECT wire,smtp_message_id,created_at,next_attempt_at FROM outbound_messages")
        ).one()
        rows = db.execute(
            text(
                "SELECT route,request_hash,result FROM idempotency_records "
                "WHERE route LIKE 'ticket-message:%' OR route LIKE 'ticket-delivery:%'"
            )
        ).all()
    body = {"participant_id": str(participant), "source_id": str(account.source_id)}
    hashes = {
        hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for value in [body, {"body_text": "Resposta publica em revisao"}]
    }
    assert {row.request_hash for row in rows} == hashes
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000025")
    command.upgrade(config, "head")
    with db_engine.connect() as db:
        assert (
            db.execute(
                text(
                    "SELECT wire,smtp_message_id,created_at,next_attempt_at FROM outbound_messages"
                )
            ).one()
            == before
        )
        assert db.scalar(text("SELECT wire_format FROM outbound_messages")) == 1
        assert (
            db.execute(
                text(
                    "SELECT route,request_hash,result FROM idempotency_records "
                    "WHERE route LIKE 'ticket-message:%' OR route LIKE 'ticket-delivery:%'"
                )
            ).all()
            == rows
        )
    result = enqueue(admin_client, path, message, account, participant, key)
    assert result.status_code == 200 and result.json() == receipt.json()
    detail = admin_client.get(path + "/messages/" + message).json()
    assert detail["attachment_count"] == 0 and detail["attachments"] == []


def test_delivery_event_failure_rolls_back_freeze_thread_version_and_receipt(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch
):
    from altvia import mail_delivery_api

    _, path, message, account, participant, ids, _ = prepared_files(
        admin_client, db_engine, seeded_user, tmp_path
    )

    def failed(*args, **kwargs):
        raise RuntimeError("controlled_delivery_event_failure")

    monkeypatch.setattr(mail_delivery_api, "_event", failed)
    with pytest.raises(RuntimeError, match="controlled_delivery_event_failure"):
        send(admin_client, path, message, account, participant, ids)
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM outbound_messages")) == 0
        assert db.scalar(text("SELECT count(*) FROM ticket_mail_threads")) == 0
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM idempotency_records WHERE route LIKE 'ticket-delivery:%'"
                )
            )
            == 0
        )
    assert admin_client.get(path).json()["version"] == 3


def test_mime2_preserves_original_incoming_root_context(admin_client, db_engine, context, tmp_path):
    from test_mail_promotion import promoted, sender

    _, _, path = promoted(admin_client, db_engine, context)
    account = sender(db_engine, context)
    identifier = ready(admin_client, db_engine, path, tmp_path, version=2)
    message = post(admin_client, path, [identifier], version=2).json()["message_id"]
    participant = admin_client.get(path + "/delivery-choices").json()["participant"][
        "participant_id"
    ]
    result = send(admin_client, path, message, account, participant, [identifier])
    assert result.status_code == 201, result.text
    with db_engine.connect() as db:
        wire = db.scalar(text("SELECT wire FROM outbound_messages"))
    parsed = BytesParser(policy=policy.default).parsebytes(wire)
    assert parsed["References"] == "<incoming@example.test>"
    assert parsed["In-Reply-To"] == "<incoming@example.test>"
    assert parsed["To"] == "requester@example.test"
    assert b"private-body" not in wire
