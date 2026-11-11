"""Real PostgreSQL proof of owner-only opaque native-mail quarantine."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia import mail_intake
from altvia.activity import consume_event
from altvia.models import (
    ActivityEvent,
    InboundMailEnvelope,
    InboundMailVariant,
    MailboxSource,
    OutboxEvent,
    Team,
    TicketQueue,
)
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


@pytest.fixture
def source(db_engine, seeded_user):
    with Session(db_engine) as db, db.begin():
        team = Team(name="Synthetic intake team")
        db.add(team)
        db.flush()
        queue = TicketQueue(team_id=team.id, name="Synthetic intake queue")
        db.add(queue)
        db.flush()
        row = mail_intake.register_source(db, "synthetic-source", queue.id)
        return row.id


def capture(engine, raw=b"From: unverified@example.test\r\n\r\nOpaque private input", **kwargs):
    with Session(engine) as db, db.begin():
        return mail_intake.capture_message(
            db,
            kwargs.pop("key", "synthetic-source"),
            kwargs.pop("validity", 1),
            kwargs.pop("uid", 1),
            raw,
            **kwargs,
        )


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_intake_preserves_opaque_raw_without_ticket_or_shared_activity(db_engine, source):
    raw = b"malformed\x00\xff<script>private marker</script>"
    receipt = capture(db_engine, raw)
    assert receipt.source_id == source and receipt.state == "quarantine" and not receipt.replayed
    with Session(db_engine) as db:
        variant = db.get(InboundMailVariant, receipt.variant_id)
        assert variant.raw_message == raw
        assert count(db, InboundMailEnvelope) == count(db, InboundMailVariant) == 1
        events = list(db.scalars(select(OutboxEvent)))
        assert len(events) == 2
        assert "private marker" not in json.dumps([e.payload for e in events])
        assert all(e.aggregate_type == "mailbox_source" for e in events)
        assert db.scalar(text("SELECT count(*) FROM tickets")) == 0
        ids = [e.event_id for e in events]
    for event_id in ids:
        assert consume_event(db_engine, event_id, datetime.now(UTC))
        assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert count(db, ActivityEvent) == 0


def test_intake_replay_preserves_ids_and_reports_later_collision(db_engine, source):
    first = capture(db_engine, b"first private raw")
    replay = capture(db_engine, b"first private raw")
    assert replay.replayed and replay.variant_id == first.variant_id
    second = capture(db_engine, b"different hostile raw")
    assert second.envelope_id == first.envelope_id and second.variant_id != first.variant_id
    assert second.state == "collision" and not second.replayed
    replay = capture(db_engine, b"first private raw")
    assert replay.state == "collision" and replay.variant_id == first.variant_id and replay.replayed
    with Session(db_engine) as db:
        assert db.get(MailboxSource, source).version == 3
        assert count(db, OutboxEvent) == 3
        assert count(db, InboundMailVariant) == 2


def test_intake_same_content_new_uid_validity_or_source_is_not_dropped(db_engine, source):
    with Session(db_engine) as db, db.begin():
        queue_id = db.get(MailboxSource, source).queue_id
        mail_intake.register_source(db, "other-source", queue_id)
    receipts = [
        capture(db_engine),
        capture(db_engine, uid=2),
        capture(db_engine, validity=2),
        capture(db_engine, key="other-source"),
    ]
    assert len({r.envelope_id for r in receipts}) == 4
    assert all(not r.replayed and r.state == "quarantine" for r in receipts)


@pytest.mark.parametrize(
    "validity,uid,raw",
    [
        (0, 1, b"x"),
        (1, 0, b"x"),
        (-1, 1, b"x"),
        (1, 2**32, b"x"),
        (2**32, 1, b"x"),
        (True, 1, b"x"),
        (1, True, b"x"),
        (1, 1, b""),
        (1, 1, b"x" * (2097152 + 1)),
    ],
)
def test_intake_rejects_invalid_identity_and_raw_before_acknowledgement(
    db_engine, source, validity, uid, raw
):
    with pytest.raises(mail_intake.IntakeError):
        capture(db_engine, raw, validity=validity, uid=uid)
    with Session(db_engine) as db:
        assert count(db, InboundMailEnvelope) == count(db, InboundMailVariant) == 0
        assert db.get(MailboxSource, source).version == 1


def test_intake_exact_size_uint32_and_archive_preserve_capture(db_engine, source):
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE ticket_queues SET active=false"))
    receipt = capture(db_engine, b"x" * 2097152, validity=2**32 - 1, uid=2**32 - 1)
    assert receipt.state == "quarantine"
    with Session(db_engine) as db:
        assert len(db.get(InboundMailVariant, receipt.variant_id).raw_message) == 2097152


def test_intake_source_identity_does_not_silently_remap_and_requires_active_parent(
    db_engine, source
):
    with Session(db_engine) as db, db.begin():
        queue_id = db.get(MailboxSource, source).queue_id
        assert mail_intake.register_source(db, "synthetic-source", queue_id).id == source
    for key, queue in [("../secret", queue_id), ("a" * 65, queue_id), ("valid", uuid4())]:
        with pytest.raises(mail_intake.IntakeError), Session(db_engine) as db, db.begin():
            mail_intake.register_source(db, key, queue)
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE ticket_queues SET active=false"))
    with pytest.raises(mail_intake.IntakeError), Session(db_engine) as db, db.begin():
        mail_intake.register_source(db, "inactive-parent", queue_id)


def test_intake_concurrent_retries_and_different_bytes_are_serialized(db_engine, source):
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _: capture(db_engine), range(4)))
    assert len({r.variant_id for r in receipts}) == 1
    assert sum(not r.replayed for r in receipts) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        changed = list(pool.map(lambda raw: capture(db_engine, raw), [b"other1", b"other2"]))
    assert all(r.state == "collision" for r in changed)
    with Session(db_engine) as db:
        assert db.get(MailboxSource, source).version == 4
        assert count(db, InboundMailVariant) == 3


def test_intake_variant_and_version_overflow_leave_no_partial_receipt(db_engine, source):
    for n in range(16):
        capture(db_engine, str(n).encode())
    with pytest.raises(mail_intake.IntakeError):
        capture(db_engine, b"seventeenth")
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE mailbox_sources SET version=2147483647"))
    assert capture(db_engine, b"0").replayed
    with pytest.raises(mail_intake.IntakeError):
        capture(db_engine, b"another UID", uid=2)
    with Session(db_engine) as db:
        assert count(db, InboundMailVariant) == 16 and count(db, InboundMailEnvelope) == 1


def test_intake_outbox_failure_rolls_back_every_effect(db_engine, source):
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE outbox_events ADD CONSTRAINT test_reject_mail "
                "CHECK(event_type <> 'mailbox.message_quarantined')"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            capture(db_engine)
        with Session(db_engine) as db:
            assert count(db, InboundMailEnvelope) == count(db, InboundMailVariant) == 0
            assert db.get(MailboxSource, source).version == 1
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE outbox_events DROP CONSTRAINT test_reject_mail"))


def test_intake_sql_raw_hash_immutability_and_guarded_downgrade(db_engine, source):
    receipt = capture(db_engine)
    for statement in [
        "UPDATE inbound_mail_variants SET raw_message='rewrite'::bytea",
        "DELETE FROM inbound_mail_variants",
        "INSERT INTO inbound_mail_variants(id,envelope_id,raw_message,raw_sha256) "
        "SELECT gen_random_uuid(),envelope_id,'bad'::bytea,repeat('0',64) "
        "FROM inbound_mail_variants LIMIT 1",
    ]:
        with pytest.raises(DBAPIError), db_engine.begin() as connection:
            connection.execute(text(statement))
    with pytest.raises(DBAPIError):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000016")
    with Session(db_engine) as db:
        assert db.get(InboundMailVariant, receipt.variant_id) is not None


def test_intake_api_and_worker_cannot_read_or_write_raw_tables(db_engine, source):
    from altvia.provision import provision_runtime
    from test_runtime_provision import runtime_url

    capture(db_engine)
    runtime = runtime_url(db_engine)
    worker = runtime.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        runtime.render_as_string(hide_password=False),
        worker.render_as_string(hide_password=False),
    )
    for credential in [runtime, worker]:
        engine = create_engine(credential, hide_parameters=True)
        try:
            for table in ["mailbox_sources", "inbound_mail_envelopes", "inbound_mail_variants"]:
                for action in ["SELECT * FROM", "DELETE FROM"]:
                    with pytest.raises(DBAPIError), engine.begin() as connection:
                        connection.execute(text(f"{action} {table}"))
        finally:
            engine.dispose()


@pytest.mark.parametrize("change", ["body", "source", "version", "actor", "envelope"])
def test_intake_private_consumer_rejects_poisoned_metadata(db_engine, source, change):
    capture(db_engine)
    with Session(db_engine) as db, db.begin():
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "mailbox.message_quarantined")
        )
        if change == "body":
            event.payload = {**event.payload, "raw_message": "private poison"}
        elif change == "source":
            event.aggregate_id = uuid4()
        elif change == "version":
            event.schema_version = 2
        elif change == "actor":
            event.payload = {**event.payload, "actor_kind": "user"}
        else:
            event.payload = {k: v for k, v in event.payload.items() if k != "envelope_id"}
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"
        assert count(db, ActivityEvent) == 0


def test_intake_source_and_collision_identity_are_immutable_in_sql(db_engine, source):
    first = capture(db_engine, b"first")
    capture(db_engine, b"collision")
    for statement in [
        "UPDATE mailbox_sources SET source_key='remapped'",
        "UPDATE inbound_mail_envelopes SET uid=2",
        "UPDATE inbound_mail_envelopes SET state='quarantine'",
        "DELETE FROM mailbox_sources",
    ]:
        with pytest.raises(DBAPIError), db_engine.begin() as connection:
            connection.execute(text(statement))
    assert capture(db_engine, b"first").variant_id == first.variant_id
    assert capture(db_engine, b"first").state == "collision"


def test_intake_empty_roundtrip_and_history_guard(db_engine, seeded_user):
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000016")
    command.upgrade(config, "head")
    command.check(config)
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO audit_logs(id,actor_id,action,resource_id,"
                "occurred_at,correlation_id,details) VALUES(gen_random_uuid(),NULL,"
                "'mailbox_source.created',NULL,now(),'synthetic','{}'::jsonb)"
            )
        )
    with pytest.raises(DBAPIError):
        command.downgrade(config, "b46087000016")
