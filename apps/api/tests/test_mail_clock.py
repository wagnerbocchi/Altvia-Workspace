"""DB-authoritative delivery time despite skewed API/worker process clocks."""

from datetime import datetime, timedelta
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from uuid import UUID

import pytest
from altvia import mail_delivery as delivery
from altvia import ticket_api
from altvia.models import AuditLog, OutboundMessage, OutboxEvent
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_mail_delivery import enqueue, prepared
from test_team_api import admin_client
from test_worker import broker_settings

__all__ = ["admin_client", "broker_settings"]


def skew(monkeypatch, days):
    class ClockType(type):
        def __instancecheck__(cls, value):
            return isinstance(value, datetime)

    class ProcessClock(datetime, metaclass=ClockType):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=days)

    monkeypatch.setattr(delivery, "datetime", ProcessClock)
    monkeypatch.setattr(ticket_api, "datetime", ProcessClock)


def clock(engine):
    with engine.connect() as db:
        return db.scalar(text("SELECT clock_timestamp()"))


def test_advanced_api_freezes_db_time_and_accepts_true_provider_evidence(
    admin_client, db_engine, seeded_user, monkeypatch
):
    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    before = clock(db_engine)
    skew(monkeypatch, 2)
    result = enqueue(admin_client, path, message, account, participant)
    assert result.status_code == 201, result.text
    identifier = UUID(result.json()["delivery_id"])
    after = clock(db_engine)
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, identifier)
        frozen = row.wire, row.smtp_message_id, row.created_at
        assert before <= row.created_at == row.next_attempt_at <= after
        date = parsedate_to_datetime(BytesParser().parsebytes(row.wire)["Date"])
        assert 0 <= (row.created_at - date).total_seconds() < 1
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "ticket.delivery_queued")
        )
        assert before <= event.occurred_at == event.next_attempt_at <= after
    current = delivery.claim(db_engine, {account.source_id: account})
    assert current is not None
    assert delivery.pre_data(db_engine, identifier, current.token)
    accepted_at = clock(db_engine)
    assert delivery.finalize(db_engine, identifier, current.token, "data_unknown")
    before = clock(db_engine)
    with Session(db_engine) as db, db.begin():
        row = db.get(OutboundMessage, identifier)
        delivery.reconcile(
            db,
            identifier,
            row.version,
            "accepted",
            "synthetic-provider-receipt",
            workers_drained=True,
            accepted_at=accepted_at,
        )
    after = clock(db_engine)
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, identifier)
        assert row.state == "accepted" and row.accepted_at == accepted_at
        assert (row.wire, row.smtp_message_id, row.created_at) == frozen
        assert before <= row.next_attempt_at <= after
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "mail.delivery_reconciled"))
        assert before <= audit.occurred_at <= after
        event = db.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.aggregate_id == identifier)
            .order_by(OutboxEvent.aggregate_version.desc())
        )
        assert event.occurred_at == audit.occurred_at == event.next_attempt_at


@pytest.mark.parametrize("days", [-2, 2])
def test_default_claim_live_finalize_and_events_follow_db_clock(
    admin_client, db_engine, seeded_user, monkeypatch, days
):
    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    before = clock(db_engine)
    skew(monkeypatch, days)
    current = delivery.claim(db_engine, {account.source_id: account})
    assert current is not None
    assert (
        before + timedelta(seconds=120)
        <= current.lease_until
        <= clock(db_engine) + timedelta(seconds=120)
    )
    assert delivery.frozen_delivery(db_engine, current.delivery_id, current.token)
    assert delivery.pre_data(db_engine, current.delivery_id, current.token)
    assert delivery.finalize(db_engine, current.delivery_id, current.token, "accepted")
    after = clock(db_engine)
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, current.delivery_id)
        assert before <= row.accepted_at <= after
        for event in db.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == row.id)):
            assert before <= event.occurred_at == event.next_attempt_at <= after


@pytest.mark.parametrize("expired,days", [(False, 2), (True, -2)])
@pytest.mark.parametrize("enabled", [False, True])
def test_skewed_worker_recovery_obeys_db_lease(
    admin_client, db_engine, seeded_user, broker_settings, monkeypatch, expired, days, enabled
):
    from altvia.worker import build_worker, dispatch_mail_once

    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    current = delivery.claim(db_engine, {account.source_id: account})
    assert delivery.pre_data(db_engine, current.delivery_id, current.token)
    if expired:
        with db_engine.begin() as db:
            db.execute(
                text(
                    "UPDATE outbound_messages SET lease_until=clock_timestamp()-interval '1 second'"
                )
            )
    skew(monkeypatch, days)
    accounts = {account.source_id: account} if enabled else {}
    broker, _, _ = build_worker(db_engine, broker_settings, accounts=accounts)
    try:
        assert dispatch_mail_once(db_engine, broker, accounts) == 0
    finally:
        broker.client.close()
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, current.delivery_id)
        assert row.state == ("uncertain" if expired else "transmitting")
        assert row.lease_token == (None if expired else current.token)
    if not expired:
        assert delivery.finalize(db_engine, current.delivery_id, current.token, "accepted")


def test_fast_host_cannot_claim_a_future_db_due_time(
    admin_client, db_engine, seeded_user, monkeypatch
):
    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    assert enqueue(admin_client, path, message, account, participant).status_code == 201
    with db_engine.begin() as db:
        db.execute(
            text("UPDATE outbound_messages SET next_attempt_at=clock_timestamp()+interval '1 hour'")
        )
    skew(monkeypatch, 2)
    assert delivery.claim(db_engine, {account.source_id: account}) is None


def test_historical_skew_evidence_refusal_preserves_uncertainty_and_frozen_bytes(
    admin_client, db_engine, seeded_user, monkeypatch
):
    _, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    # Reproduce an immutable historical snapshot from the old advanced-clock
    # writer without changing a saved row or its SQL guards.
    real_clock = delivery._clock
    with monkeypatch.context() as historical:
        historical.setattr(delivery, "_clock", lambda db: real_clock(db) + timedelta(days=2))
        result = enqueue(admin_client, path, message, account, participant)
    assert result.status_code == 201
    identifier = UUID(result.json()["delivery_id"])
    future = clock(db_engine) + timedelta(days=2, seconds=1)
    current = delivery.claim(db_engine, {account.source_id: account}, future)
    assert delivery.pre_data(db_engine, identifier, current.token, future)
    assert delivery.finalize(db_engine, identifier, current.token, "data_unknown", future)
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, identifier)
        saved = row.wire, row.smtp_message_id, row.created_at, row.version
    with (
        Session(db_engine) as db,
        db.begin(),
        pytest.raises(ValueError, match="invalid_acceptance_evidence_time"),
    ):
        delivery.reconcile(
            db,
            identifier,
            saved[3],
            "accepted",
            "historical-provider-evidence",
            workers_drained=True,
            accepted_at=clock(db_engine),
        )
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, identifier)
        assert row.state == "uncertain" and row.accepted_at is None
        assert (row.wire, row.smtp_message_id, row.created_at, row.version) == saved
