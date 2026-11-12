"""Private durable MIME normalization, actual command and runtime denial."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia import mail_normalize
from altvia.activity import consume_event
from altvia.models import ActivityEvent, InboundMailPreview, MailboxSource, OutboxEvent
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_mail_intake import capture, source

__all__ = ["source"]
RAW = b"Subject: private-subject\r\nContent-Type: text/html\r\n\r\n<p>private-body</p>"


def result(engine, variant):
    return mail_normalize.normalize_variant(engine, variant)


def test_result_persists_without_ticket_shared_activity_or_payload_events(db_engine, source):
    raw = capture(db_engine, RAW)
    first = result(db_engine, raw.variant_id)
    assert first.status == "ready" and not first.replayed and first.source_id == source
    assert result(db_engine, raw.variant_id).replayed
    with Session(db_engine) as db:
        stored = db.get(InboundMailPreview, raw.variant_id)
        assert stored.subject == "private-subject" and stored.body_text == "private-body"
        assert (stored.parser_version, stored.part_count, stored.attachment_count) == (1, 1, 0)
        assert db.get(MailboxSource, source).version == 3
        events = list(db.scalars(select(OutboxEvent)))
        assert len(events) == 3 and "private-" not in json.dumps([e.payload for e in events])
        assert db.scalar(text("SELECT count(*) FROM tickets")) == 0
        ids = [e.event_id for e in events]
    for event_id in ids:
        assert consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(ActivityEvent)) == 0


def test_rejection_and_collision_are_durable_without_reinterpreting_intake(db_engine, source):
    a = capture(db_engine, RAW)
    b = capture(db_engine, b"not valid MIME")
    assert result(db_engine, a.variant_id).status == "ready"
    assert result(db_engine, b.variant_id).status == "rejected"
    assert result(db_engine, b.variant_id).replayed
    assert capture(db_engine, RAW).state == "collision"
    with Session(db_engine) as db:
        row = db.get(InboundMailPreview, b.variant_id)
        assert row.body_text is row.subject is row.part_count is row.attachment_count is None
        assert row.reason == "invalid_headers"


def test_concurrent_normalization_replays_one_result(db_engine, source):
    raw = capture(db_engine, RAW)
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _: result(db_engine, raw.variant_id), range(4)))
    assert sum(not receipt.replayed for receipt in receipts) == 1
    with Session(db_engine) as db:
        assert db.get(MailboxSource, source).version == 3
        assert db.scalar(select(func.count()).select_from(InboundMailPreview)) == 1


def test_failed_event_rolls_back_preview_and_source_version(db_engine, source):
    raw = capture(db_engine, RAW)
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE outbox_events ADD CONSTRAINT test_reject_normalize "
                "CHECK(event_type<>'mailbox.message_normalized')"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            result(db_engine, raw.variant_id)
        with Session(db_engine) as db:
            assert db.get(InboundMailPreview, raw.variant_id) is None
            assert db.get(MailboxSource, source).version == 2
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE outbox_events DROP CONSTRAINT test_reject_normalize")
            )


def test_parse_runs_without_source_write_transaction(db_engine, source, monkeypatch):
    raw = capture(db_engine, RAW)
    original = mail_normalize.normalize

    def observe(value):
        with db_engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout='500ms'"))
            connection.execute(text("SELECT id FROM mailbox_sources FOR UPDATE NOWAIT"))
        return original(value)

    monkeypatch.setattr(mail_normalize, "normalize", observe)
    assert result(db_engine, raw.variant_id).status == "ready"


def test_source_exhaustion_rolls_back_but_existing_replay_remains_valid(db_engine, source):
    first = capture(db_engine, RAW)
    second = capture(db_engine, RAW, uid=2)
    result(db_engine, first.variant_id)
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE mailbox_sources SET version=2147483647"))
    assert result(db_engine, first.variant_id).replayed
    with pytest.raises(mail_normalize.NormalizeError):
        result(db_engine, second.variant_id)


def test_preview_immutability_runtime_denial_and_guarded_downgrade(db_engine, source):
    from altvia.provision import provision_runtime
    from test_runtime_provision import runtime_url

    raw = capture(db_engine, RAW)
    result(db_engine, raw.variant_id)
    for statement in (
        "UPDATE inbound_mail_previews SET body_text='rewrite'",
        "DELETE FROM inbound_mail_previews",
    ):
        with pytest.raises(DBAPIError), db_engine.begin() as connection:
            connection.execute(text(statement))
    with pytest.raises(DBAPIError):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000018")
    runtime = runtime_url(db_engine)
    worker = runtime.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        runtime.render_as_string(hide_password=False),
        worker.render_as_string(hide_password=False),
    )
    for url in (runtime, worker):
        engine = create_engine(url, hide_parameters=True)
        try:
            for sql in ("SELECT * FROM inbound_mail_previews", "DELETE FROM inbound_mail_previews"):
                with pytest.raises(DBAPIError), engine.begin() as connection:
                    connection.execute(text(sql))
        finally:
            engine.dispose()


@pytest.mark.parametrize("change", ["body", "status", "variant", "reason"])
def test_normalized_events_reject_poison_without_shared_activity(db_engine, source, change):
    raw = capture(db_engine, RAW)
    result(db_engine, raw.variant_id)
    with Session(db_engine) as db, db.begin():
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "mailbox.message_normalized")
        )
        payload = dict(event.payload)
        if change == "variant":
            payload.pop("variant_id")
        else:
            payload[{"body": "body_text", "status": "status", "reason": "reason"}[change]] = (
                "poison"
            )
        event.payload = payload
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"


def test_normalize_cli_opt_in_arguments_config_and_actual_replay(
    db_engine, source, monkeypatch, capsys
):
    raw = capture(db_engine, RAW)
    args = ["--variant-id", str(raw.variant_id)]
    monkeypatch.delenv("ALTVIA_ALLOW_MAIL_NORMALIZE", raising=False)
    assert mail_normalize.main(args) == 1
    capsys.readouterr()
    monkeypatch.setenv("ALTVIA_ALLOW_MAIL_NORMALIZE", "1")
    for replay in (False, True):
        assert mail_normalize.main(args) == 0
        receipt = json.loads(capsys.readouterr().out)
        assert receipt["replayed"] is replay and receipt["status"] == "ready"
        assert "private-" not in json.dumps(receipt)
    with pytest.raises(SystemExit):
        mail_normalize.main(["--variant-id", "private-marker"])
    assert "private-marker" not in str(capsys.readouterr())
    assert mail_normalize.main(["--variant-id", str(uuid4())]) == 1
    monkeypatch.setenv("ALTVIA_DATABASE_URL", "private-invalid-credential")
    assert mail_normalize.main(args) == 1
    assert "private-invalid-credential" not in str(capsys.readouterr())


def test_preview_empty_migration_roundtrip_and_event_guard(db_engine, seeded_user):
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000018")
    command.upgrade(config, "head")
    command.check(config)
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO audit_logs(id,action,occurred_at,correlation_id,details) "
                "VALUES(gen_random_uuid(),'mailbox.message_normalized',now(),'test','{}')"
            )
        )
    with pytest.raises(DBAPIError):
        command.downgrade(config, "b46087000018")


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "ready", "subject": None},
        {"status": "ready", "part_count": None},
        {"status": "ready", "attachment_count": None},
        {"status": "ready", "body_text": "x" * 65537},
        {"status": "ready", "part_count": 65},
        {"status": "ready", "attachment_count": 2},
        {"status": "ready", "parser_version": 2},
        {"status": "other"},
        {
            "status": "rejected",
            "subject": None,
            "body_text": None,
            "part_count": None,
            "attachment_count": None,
            "reason": None,
        },
        {"status": "rejected", "reason": "unapproved"},
    ],
)
def test_sql_rejects_null_or_unbounded_interpretation(db_engine, source, fields):
    raw = capture(db_engine, RAW)
    values = {
        "variant_id": raw.variant_id,
        "parser_version": 1,
        "status": "ready",
        "subject": "bounded",
        "body_text": "bounded",
        "part_count": 1,
        "attachment_count": 0,
        "reason": None,
        **fields,
    }
    with pytest.raises(DBAPIError), Session(db_engine) as db, db.begin():
        db.add(InboundMailPreview(**values))


def test_overflow_header_command_persists_rejection_replays_and_never_echoes(
    db_engine, source, monkeypatch, capsys
):
    raw = capture(
        db_engine,
        b"Date: Wed, 1 Jan 999999999999999999999999999999 "
        b"00:00:00 +0000\r\n\r\nprivate-overflow-body",
    )
    monkeypatch.setenv("ALTVIA_ALLOW_MAIL_NORMALIZE", "1")
    for replay in (False, True):
        assert mail_normalize.main(["--variant-id", str(raw.variant_id)]) == 0
        output = capsys.readouterr()
        receipt = json.loads(output.out)
        assert receipt["status"] == "rejected" and receipt["replayed"] is replay
        assert (
            not output.err
            and "private-overflow" not in output.out
            and "Traceback" not in output.out
        )
    with Session(db_engine) as db:
        row = db.get(InboundMailPreview, raw.variant_id)
        assert row.reason == "invalid_headers" and row.body_text is row.subject is None
