"""Versioned private interpretations preserve old data and exact event envelopes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from altvia.activity import consume_event
from altvia.mail_intake import record_intake_event
from altvia.mail_normalize import normalize_variant
from altvia.models import (
    ActivityEvent,
    InboundMailPreview,
    InboundMailVariant,
    MailboxSource,
    OutboxEvent,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_mail_intake import capture, source

__all__ = ["source"]
RAW = b"Subject: =?utf-7?q?+AOk-?=\r\n\r\nVisible"


def legacy_result(engine, source_id, variant_id):
    with Session(engine) as db, db.begin():
        source_row = db.get(MailboxSource, source_id)
        variant = db.get(InboundMailVariant, variant_id)
        db.add(
            InboundMailPreview(
                variant_id=variant_id,
                parser_version=1,
                status="ready",
                subject="é",
                body_text="Visible",
                part_count=1,
                attachment_count=0,
            )
        )
        source_row.version += 1
        record_intake_event(
            db,
            source_row,
            "mailbox.message_normalized",
            {
                "envelope_id": str(variant.envelope_id),
                "variant_id": str(variant_id),
                "status": "ready",
            },
        )


def snapshot(engine, variant_id):
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text(
                    "SELECT * FROM inbound_mail_previews WHERE variant_id=:id AND parser_version=1"
                ),
                {"id": variant_id},
            )
            .mappings()
            .one()
        )


def test_populated_upgrade_preserves_v1_and_adds_distinct_v2(db_engine, source):
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000019")
    raw = capture(db_engine, RAW)
    legacy_result(db_engine, source, raw.variant_id)
    before = snapshot(db_engine, raw.variant_id)
    command.upgrade(config, "head")
    command.check(config)
    receipt = normalize_variant(db_engine, raw.variant_id)
    assert receipt.parser_version == 2 and receipt.status == "rejected" and not receipt.replayed
    assert normalize_variant(db_engine, raw.variant_id).replayed
    assert snapshot(db_engine, raw.variant_id) == before
    with Session(db_engine) as db:
        assert db.get(InboundMailPreview, (raw.variant_id, 2)).reason == "unsupported_charset"
        assert db.get(InboundMailVariant, raw.variant_id).raw_message == RAW
    for version in (1, 2):
        with pytest.raises(DBAPIError), db_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE inbound_mail_previews SET body_text='rewrite' "
                    "WHERE parser_version=:version"
                ),
                {"version": version},
            )
    with pytest.raises(DBAPIError):
        command.downgrade(config, "b46087000019")
    assert snapshot(db_engine, raw.variant_id) == before


def test_v1_only_downgrade_roundtrip_preserves_interpretation(db_engine, source):
    raw = capture(db_engine, RAW)
    legacy_result(db_engine, source, raw.variant_id)
    before = snapshot(db_engine, raw.variant_id)
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000019")
    assert snapshot(db_engine, raw.variant_id) == before
    command.upgrade(config, "head")
    assert snapshot(db_engine, raw.variant_id) == before


def test_concurrent_v2_reprocessing_preserves_v1_and_private_schema1_schema2_events(
    db_engine, source
):
    raw = capture(db_engine, RAW)
    legacy_result(db_engine, source, raw.variant_id)
    before = snapshot(db_engine, raw.variant_id)
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _: normalize_variant(db_engine, raw.variant_id), range(4)))
    assert all(r.parser_version == 2 and r.status == "rejected" for r in receipts)
    assert sum(not r.replayed for r in receipts) == 1
    assert snapshot(db_engine, raw.variant_id) == before
    with Session(db_engine) as db:
        assert db.get(MailboxSource, source).version == 4
        assert db.scalar(select(func.count()).select_from(InboundMailPreview)) == 2
        events = list(
            db.scalars(
                select(OutboxEvent).where(OutboxEvent.event_type == "mailbox.message_normalized")
            )
        )
        assert {e.schema_version for e in events} == {1, 2}
        for event in events:
            assert ("parser_version" in event.payload) == (event.schema_version == 2)
            assert set(event.payload) <= {
                "actor_id",
                "actor_kind",
                "source_id",
                "envelope_id",
                "variant_id",
                "status",
                "parser_version",
            }
        ids = [e.event_id for e in events]
    for identifier in ids:
        assert consume_event(db_engine, identifier, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(ActivityEvent)) == 0


@pytest.mark.parametrize("change", ["schema1", "schema3", "missing", "legacy", "noncanonical"])
def test_schema2_poison_cannot_be_projected_or_silently_treated_as_legacy(
    db_engine, source, change
):
    raw = capture(db_engine, RAW)
    normalize_variant(db_engine, raw.variant_id)
    with Session(db_engine) as db, db.begin():
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "mailbox.message_normalized")
        )
        payload = dict(event.payload)
        if change in {"schema1", "schema3"}:
            event.schema_version = 1 if change == "schema1" else 3
        elif change == "missing":
            payload.pop("parser_version")
        else:
            payload["parser_version"] = "1" if change == "legacy" else "02"
        event.payload = payload
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"


def test_v2_audit_history_alone_blocks_key_contraction(db_engine, source):
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO audit_logs(id,action,occurred_at,correlation_id,details) "
                "VALUES(gen_random_uuid(),'mailbox.message_normalized',now(),'test',"
                '\'{"parser_version":"2"}\'::jsonb)'
            )
        )
    with pytest.raises(DBAPIError):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000019")


def test_v2_outbox_history_alone_blocks_key_contraction(db_engine, source):
    with Session(db_engine) as db, db.begin():
        now = datetime.now(UTC)
        db.add(
            OutboxEvent(
                aggregate_type="mailbox_source",
                aggregate_id=source,
                aggregate_version=1,
                event_type="mailbox.message_normalized",
                schema_version=2,
                payload={
                    "actor_id": None,
                    "actor_kind": "management_command",
                    "source_id": str(source),
                    "envelope_id": str(uuid4()),
                    "variant_id": str(uuid4()),
                    "status": "ready",
                    "parser_version": "2",
                },
                occurred_at=now,
                correlation_id="test",
                next_attempt_at=now,
            )
        )
    with pytest.raises(DBAPIError):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000019")


def test_event_failure_rolls_back_only_new_interpretation(db_engine, source):
    raw = capture(db_engine, RAW)
    legacy_result(db_engine, source, raw.variant_id)
    before = snapshot(db_engine, raw.variant_id)
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE outbox_events ADD CONSTRAINT test_reject_v2 "
                "CHECK(event_type<>'mailbox.message_normalized' OR schema_version<>2)"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            normalize_variant(db_engine, raw.variant_id)
        assert snapshot(db_engine, raw.variant_id) == before
        with Session(db_engine) as db:
            assert db.get(InboundMailPreview, (raw.variant_id, 2)) is None
            assert db.get(MailboxSource, source).version == 3
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE outbox_events DROP CONSTRAINT test_reject_v2"))
