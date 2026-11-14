"""Native delivery evidence captured independently of shared activity status."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from altvia import mail_delivery as delivery
from altvia import provision
from altvia.activity import consume_event
from altvia.mail_intake import register_source
from altvia.mail_participants import attest_requester, register_sender
from altvia.mail_settings import SMTPAccount
from altvia.models import OutboundMessage, OutboxEvent
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_automation_rules import rule_context
from test_mail_delivery import enqueue
from test_runtime_provision import runtime_url
from test_sla_cycles import change
from test_sla_execution import owner, tracked
from test_team_api import admin_client
from test_ticket_messages import append

__all__ = ["admin_client", "rule_context"]


def capture(engine, limit=20):
    function = getattr(owner(), "capture_acceptances", None)
    assert callable(function), "Missing independent accepted-response SLA capture"
    return function(engine, limit=limit)


def queued(client, engine, path, refs):
    message = append(client, path).json()["message_id"]
    version = client.get(path).json()["version"]
    with Session(engine) as db, db.begin():
        source = register_source(db, "sla_synthetic_sender", UUID(refs["queue_id"]))
        account = SMTPAccount(
            source_id=source.id,
            host="smtp.example.test",
            port=465,
            tls_mode="implicit",
            username="synthetic",
            password="synthetic",
            from_email="support@example.test",
        )
        register_sender(db, account)
        participant = attest_requester(
            db, UUID(path.rsplit("/", 1)[1]), version, "synthetic-sla-evidence"
        )
        participant_id = participant.id
    result = enqueue(client, path, message, account, participant_id, version=version)
    assert result.status_code == 201, result.text
    claim = delivery.claim(engine, {account.source_id: account})
    assert claim and delivery.pre_data(engine, claim.delivery_id, claim.token)
    return claim


def test_only_durable_accepted_public_response_fulfills_and_capture_ignores_activity_status(
    admin_client, db_engine, rule_context
):
    path, _, _, _ = tracked(admin_client, db_engine, rule_context, first=60)
    claim = queued(admin_client, db_engine, path, rule_context)
    assert capture(db_engine) == 0
    assert delivery.finalize(db_engine, claim.delivery_id, claim.token, "accepted")
    with Session(db_engine) as db:
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.payload["state"].astext == "accepted")
        )
        event_id = event.event_id
    assert consume_event(db_engine, event_id, datetime.now(UTC))
    assert capture(db_engine) == 1
    assert capture(db_engine) == 0
    assert owner().evaluate_due(db_engine) == 1
    with db_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT outcome FROM ticket_sla_goals WHERE goal='first_response'")
            )
            == "fulfilled"
        )
        assert connection.scalar(
            text("SELECT first_response_at FROM ticket_sla_states")
        ) == connection.scalar(text("SELECT accepted_at FROM outbound_messages"))
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_acceptances")) == 1
        assert (
            connection.scalar(
                text("SELECT count(*) FROM processed_events WHERE consumer='sla_acceptance_v1'")
            )
            == 1
        )


def test_previous_cycle_draft_and_finalization_after_resolution_never_fulfill_reopen(
    admin_client, db_engine, rule_context
):
    path, _, _, _ = tracked(admin_client, db_engine, rule_context, first=60)
    claim = queued(admin_client, db_engine, path, rule_context)
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE ticket_queues SET allow_reopen=true"))
    change(admin_client, path, "open")
    change(admin_client, path, "resolved")
    change(admin_client, path, "open")
    assert delivery.finalize(db_engine, claim.delivery_id, claim.token, "accepted")
    assert capture(db_engine) == 1
    assert owner().evaluate_due(db_engine) == 2
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_acceptances")) == 0
        assert (
            connection.scalar(
                text("SELECT first_response_at FROM ticket_sla_states WHERE cycle_number=2")
            )
            is None
        )
        assert (
            connection.scalar(
                text(
                    "SELECT outcome FROM ticket_sla_goals "
                    "WHERE cycle_number=1 AND goal='first_response'"
                )
            )
            == "unfulfilled"
        )


@pytest.mark.parametrize("first,expected,breaches", [(1, "breached", 1), (60, "fulfilled", 0)])
def test_late_owner_evidence_corrects_derived_response_but_retains_breach_once(
    admin_client, db_engine, rule_context, first, expected, breaches
):
    path, _, _, _ = tracked(admin_client, db_engine, rule_context, first=first)
    claim = queued(admin_client, db_engine, path, rule_context)
    assert delivery.finalize(db_engine, claim.delivery_id, claim.token, "data_unknown")
    evidence_at = datetime.now(UTC)
    change(admin_client, path, "open")
    change(admin_client, path, "resolved")
    assert owner().evaluate_due(db_engine) == 1
    with Session(db_engine) as db, db.begin():
        row = db.get(OutboundMessage, claim.delivery_id)
        delivery.reconcile(
            db,
            row.id,
            row.version,
            "accepted",
            "synthetic-receipt-sla",
            workers_drained=True,
            accepted_at=evidence_at,
        )
    assert capture(db_engine) == 1
    assert owner().evaluate_due(db_engine) == 1
    assert capture(db_engine) == 0 and owner().evaluate_due(db_engine) == 0
    with db_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT outcome FROM ticket_sla_goals WHERE goal='first_response'")
            )
            == expected
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM ticket_sla_events "
                    "WHERE goal='first_response' AND kind='breached'"
                )
            )
            == breaches
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM ticket_sla_events "
                    "WHERE goal='first_response' AND kind='corrected'"
                )
            )
            == 1
        )
        assert (
            connection.scalar(
                text("SELECT occurred_at=observed_at FROM ticket_sla_events WHERE kind='corrected'")
            )
            is True
        )
        identifier = connection.scalar(
            text("SELECT event_id FROM ticket_sla_events WHERE kind='corrected'")
        )
    assert consume_event(db_engine, identifier, datetime.now(UTC))
    assert all(
        "source_delivery_id" not in row["details"]
        for row in admin_client.get(path + "/activity").json()["items"]
    )


def test_capture_rejects_forged_source_without_fact_and_acknowledges_safe_metadata_once(
    admin_client, db_engine, rule_context
):
    path, _, _, _ = tracked(admin_client, db_engine, rule_context)
    claim = queued(admin_client, db_engine, path, rule_context)
    assert delivery.finalize(db_engine, claim.delivery_id, claim.token, "accepted")
    with Session(db_engine) as db, db.begin():
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.payload["state"].astext == "accepted")
        )
        event.payload = {**event.payload, "delivery_id": str(uuid4())}
    assert capture(db_engine) == 1 and capture(db_engine) == 0
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_acceptances")) == 0
        assert (
            connection.scalar(
                text("SELECT count(*) FROM audit_logs WHERE action='sla.acceptance_rejected'")
            )
            == 1
        )


def test_competing_capture_workers_commit_one_fact_and_wake_without_duplicate_receipt(
    admin_client, db_engine, rule_context
):
    path, _, _, _ = tracked(admin_client, db_engine, rule_context, first=60)
    claim = queued(admin_client, db_engine, path, rule_context)
    assert delivery.finalize(db_engine, claim.delivery_id, claim.token, "accepted")
    barrier = Barrier(2)

    def run():
        barrier.wait()
        return capture(db_engine)

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _: run(), range(2)))
    assert sorted(counts) == [0, 1]
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_acceptances")) == 1


def test_runtime_worker_can_capture_without_message_body_or_api_evidence_write(
    admin_client, db_engine, rule_context
):
    path, _, _, _ = tracked(admin_client, db_engine, rule_context, first=60)
    claim = queued(admin_client, db_engine, path, rule_context)
    assert delivery.finalize(db_engine, claim.delivery_id, claim.token, "accepted")
    app_url = runtime_url(db_engine)
    worker_url = app_url.set(username="altvia_worker")
    provision.provision_runtime(
        db_engine,
        app_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    engine = create_engine(worker_url, hide_parameters=True)
    app = create_engine(app_url, hide_parameters=True)
    try:
        assert capture(engine) == 1
        assert owner().evaluate_due(engine) == 1
        for target, statement in (
            (engine, "SELECT body_text FROM ticket_messages"),
            (engine, "UPDATE ticket_sla_acceptances SET accepted_at=now()"),
            (app, "SELECT * FROM sla_public_acceptance_sources"),
            (app, "SELECT * FROM ticket_sla_acceptances"),
        ):
            with target.begin() as connection, pytest.raises(DBAPIError) as error:
                connection.execute(text(statement))
            assert error.value.orig.sqlstate == "42501"
    finally:
        engine.dispose()
        app.dispose()


def test_main_loop_sla_stage_owns_actual_capture_evaluation_and_cancellation(
    admin_client, db_engine, rule_context
):
    from threading import Event

    from altvia import worker

    path, _, _, _ = tracked(admin_client, db_engine, rule_context, first=60)
    claim = queued(admin_client, db_engine, path, rule_context)
    assert delivery.finalize(db_engine, claim.delivery_id, claim.token, "accepted")
    stage = getattr(worker, "dispatch_sla_once", None)
    assert callable(stage), "Missing SLA stage in native worker loop"
    stop = Event()
    stop.set()
    assert stage(db_engine, stop) == 0
    assert stage(db_engine) == 2
    assert stage(db_engine) == 0
    with db_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT outcome FROM ticket_sla_goals WHERE goal='first_response'")
            )
            == "fulfilled"
        )


def test_capture_sql_failure_rolls_back_fact_wakeup_and_receipt_before_retry(
    admin_client, db_engine, rule_context
):
    path, _, _, _ = tracked(admin_client, db_engine, rule_context, first=60)
    claim = queued(admin_client, db_engine, path, rule_context)
    assert delivery.finalize(db_engine, claim.delivery_id, claim.token, "accepted")
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE ticket_sla_acceptances ADD CONSTRAINT "
                "synthetic_reject_acceptance CHECK(false) NOT VALID"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            capture(db_engine)
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ticket_sla_acceptances DROP CONSTRAINT synthetic_reject_acceptance"
                )
            )
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ticket_sla_acceptances")) == 0
        assert (
            connection.scalar(
                text("SELECT count(*) FROM processed_events WHERE consumer='sla_acceptance_v1'")
            )
            == 0
        )
        assert connection.scalar(text("SELECT version FROM ticket_sla_states")) == 1
    assert capture(db_engine) == 1
