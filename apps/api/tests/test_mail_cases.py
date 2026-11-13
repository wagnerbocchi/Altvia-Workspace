"""Actual owner publication and scoped API persistence."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from altvia.mail_cases_owner import CaseError, attest_case, revoke_case
from altvia.mail_intake import register_source
from altvia.mail_normalize import normalize_variant
from altvia.models import MailCaseOrigin, MailTriageCase, OutboxEvent
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_mail_intake import capture
from test_team_api import admin_client, sign_in
from test_tickets import setup

__all__ = ["admin_client"]
RAW = (
    b"From: Requester <requester@example.test>\r\nMessage-ID: "
    b"<incoming@example.test>\r\nSubject: "
    b"private-subject\r\n\r\nprivate-body"
)


@pytest.fixture
def context(admin_client, db_engine, seeded_user):
    refs = setup(admin_client, db_engine, seeded_user)
    with Session(db_engine) as db, db.begin():
        register_source(db, "synthetic-source", UUID(refs["queue_id"]))
    return refs


def publish(engine, refs, raw=RAW, uid=1, evidence="synthetic:proof", version=1):
    receipt = capture(engine, raw, uid=uid)
    normalize_variant(engine, receipt.variant_id)
    return attest_case(engine, receipt.variant_id, UUID(refs["requester_id"]), version, evidence)


def test_publication_exact_snapshot_replay_alias_contradiction(db_engine, context, admin_client):
    first = publish(db_engine, context)
    assert first.state == "ready" and first.disposition == "primary" and not first.replayed
    assert publish(db_engine, context).replayed
    alias = publish(db_engine, context, uid=2, evidence="different:proof")
    assert alias.case_id == first.case_id and alias.disposition == "alias"
    detail = admin_client.get("/api/v1/mail-cases/" + str(first.case_id))
    assert detail.status_code == 200, detail.text
    assert detail.json()["body_text"] == "private-body"
    assert "references" not in detail.json() and "evidence" not in detail.json()
    conflict = publish(db_engine, context, RAW.replace(b"private-body", b"changed-body"), uid=3)
    assert conflict.case_id == first.case_id and conflict.disposition == "collision"
    assert conflict.state == "collision"
    with Session(db_engine) as db:
        assert db.get(MailTriageCase, first.case_id).body_text == "private-body"
        assert len(list(db.scalars(select(MailCaseOrigin)))) == 3


def test_alias_receipt_late_collision_invalidates_and_events_remain_private(db_engine, context):
    from altvia.activity import consume_event
    from altvia.models import ActivityEvent

    first = publish(db_engine, context)
    publish(db_engine, context, uid=2)
    capture(db_engine, RAW + b"contradiction", uid=2)
    with Session(db_engine) as db:
        case = db.get(MailTriageCase, first.case_id)
        assert case.state == "collision" and case.version == 3
        events = list(db.scalars(select(OutboxEvent)))
        assert all("private-" not in str(e.payload) for e in events)
        ids = [e.event_id for e in events]
    for identifier in ids:
        assert consume_event(db_engine, identifier, datetime.now(UTC))
    with Session(db_engine) as db:
        assert not list(
            db.scalars(select(ActivityEvent).where(ActivityEvent.event_type.like("mail.%")))
        )


def test_missing_id_never_cross_uid_deduplicates_and_stale_review_refuses(db_engine, context):
    raw = RAW.replace(b"Message-ID: <incoming@example.test>\r\n", b"")
    assert (
        publish(db_engine, context, raw).case_id != publish(db_engine, context, raw, uid=2).case_id
    )
    with pytest.raises(CaseError):
        publish(db_engine, context, uid=3, version=2)
    with pytest.raises(CaseError):
        publish(db_engine, context, raw, evidence="other:intent")


def test_scope_requires_current_queue_binding_and_customer_even_admin(
    db_engine, context, admin_client
):
    first = publish(db_engine, context)
    path = "/api/v1/mail-cases/" + str(first.case_id)
    assert admin_client.get(path).status_code == 200
    page = admin_client.get("/api/v1/mail-cases").json()
    assert len(page["items"]) == 1 and "body_text" not in page["items"][0]
    sign_in(admin_client, "viewer@example.test")
    assert admin_client.get(path).status_code == 200
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path).status_code == 404
    assert admin_client.get("/api/v1/mail-cases").json()["items"] == []
    sign_in(admin_client, "employee@example.test")
    with db_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM client_access_grants WHERE client_id=:id"),
            {"id": UUID(context["client_id"])},
        )
    assert admin_client.get(path).status_code == 404


def test_revocation_retains_body_and_blocks_republication(db_engine, context):
    first = publish(db_engine, context)
    revoke_case(db_engine, first.case_id, 1)
    assert publish(db_engine, context).state == "revoked"
    with pytest.raises(CaseError):
        revoke_case(db_engine, first.case_id, 1)
    with Session(db_engine) as db:
        assert db.get(MailTriageCase, first.case_id).body_text == "private-body"


@pytest.mark.parametrize("target", ["client", "queue", "team", "contact"])
def test_current_active_parents_required(db_engine, context, target):
    table = {
        "client": "clients",
        "queue": "ticket_queues",
        "team": "teams",
        "contact": "client_contacts",
    }[target]
    with db_engine.begin() as connection:
        connection.execute(text(f"UPDATE {table} SET active=false"))
    with pytest.raises(CaseError):
        publish(db_engine, context)
    with Session(db_engine) as db:
        assert not list(db.scalars(select(MailTriageCase)))
        assert not list(db.scalars(select(MailCaseOrigin)))


def test_parser2_required_empty_subject_and_full_bounded_body(db_engine, context, admin_client):
    raw = b"From: requester@example.test\r\nMessage-ID: <full@example.test>\r\n\r\n" + b"x" * 65536
    receipt = capture(db_engine, raw)
    with pytest.raises(CaseError):
        attest_case(
            db_engine, receipt.variant_id, UUID(context["requester_id"]), 1, "synthetic:proof"
        )
    normalize_variant(db_engine, receipt.variant_id)
    case = attest_case(
        db_engine, receipt.variant_id, UUID(context["requester_id"]), 1, "synthetic:proof"
    )
    row = admin_client.get("/api/v1/mail-cases/" + str(case.case_id)).json()
    assert row["subject"] == "" and row["body_text"] == "x" * 65536
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE client_contacts SET display_name='Changed',version=version+1")
        )
    row = admin_client.get("/api/v1/mail-cases/" + str(case.case_id)).json()
    assert row["contact_name"] == "Solicitante" and row["version"] == 1


def test_foreign_contact_and_source_context_independent_same_id(db_engine, context):
    from altvia.models import ClientContact, MailboxSource

    first = publish(db_engine, context)
    with Session(db_engine) as db, db.begin():
        other = ClientContact(
            client_id=UUID(context["client_id"]),
            display_name="Other",
            email_normalized="other@example.test",
        )
        db.add(other)
        source = db.scalar(select(MailboxSource))
        register_source(db, "other-source", source.queue_id)
        db.flush()
        other_id = other.id
    variant = capture(
        db_engine, RAW.replace(b"requester@example.test", b"other@example.test"), uid=2
    )
    normalize_variant(db_engine, variant.variant_id)
    second = attest_case(db_engine, variant.variant_id, other_id, 1, "synthetic:proof")
    variant = capture(db_engine, RAW, key="other-source")
    normalize_variant(db_engine, variant.variant_id)
    third = attest_case(
        db_engine, variant.variant_id, UUID(context["requester_id"]), 1, "synthetic:proof"
    )
    assert len({first.case_id, second.case_id, third.case_id}) == 3
    with Session(db_engine) as db:
        assert all(c.state == "ready" for c in db.scalars(select(MailTriageCase)))
    with pytest.raises(CaseError):
        attest_case(db_engine, variant.variant_id, other_id, 1, "synthetic:proof")


def test_paged_filter_cursors_hidden_ids_and_query_validation(db_engine, context, admin_client):
    ids = [
        publish(db_engine, context, RAW.replace(b"incoming@", f"m{i}@".encode()), uid=i + 1).case_id
        for i in range(3)
    ]
    path = "/api/v1/mail-cases"
    first = admin_client.get(path, params={"limit": 2}).json()
    assert [i["id"] for i in first["items"]] == [str(i) for i in reversed(ids[1:])]
    cursor = first["next_cursor"]
    tail = admin_client.get(path, params={"limit": 2, "cursor": cursor}).json()
    assert [i["id"] for i in tail["items"]] == [str(ids[0])] and tail["next_cursor"] is None
    assert admin_client.get(path, params={"state": "revoked"}).json()["items"] == []
    assert (
        len(
            admin_client.get(
                path, params={"queue_id": context["queue_id"], "client_id": context["client_id"]}
            ).json()["items"]
        )
        == 3
    )
    assert admin_client.get(path, params={"state": "ready", "cursor": cursor}).status_code == 422
    sign_in(admin_client, "viewer@example.test")
    assert admin_client.get(path, params={"cursor": cursor}).status_code == 422
    for query in (
        "limit=0",
        "limit=101",
        "state=invalid",
        "unknown=1",
        "limit=2&limit=3",
        "cursor=hostile",
    ):
        assert admin_client.get(path + "?" + query).status_code == 422
    from uuid import uuid4

    assert admin_client.get(path + "/" + str(uuid4())).status_code == 404


def test_owner_cli_opt_in_safe_arguments_and_actual_receipts(
    db_engine, context, monkeypatch, capsys
):
    from altvia import mail_cases_owner

    receipt = capture(db_engine, RAW)
    normalize_variant(db_engine, receipt.variant_id)
    args = [
        "attest",
        "--variant-id",
        str(receipt.variant_id),
        "--contact-id",
        context["requester_id"],
        "--contact-version",
        "1",
        "--evidence",
        "synthetic:proof",
    ]
    monkeypatch.delenv("ALTVIA_ALLOW_MAIL_CASES", raising=False)
    assert mail_cases_owner.main(args) == 1
    capsys.readouterr()
    monkeypatch.setenv("ALTVIA_ALLOW_MAIL_CASES", "1")
    assert mail_cases_owner.main(args) == 0
    import json

    output = json.loads(capsys.readouterr().out)
    assert not output["replayed"] and "private-" not in str(output)
    assert mail_cases_owner.main(["inspect", "--case-id", output["case_id"]]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {"case_id", "version", "state"}
    with pytest.raises(SystemExit):
        mail_cases_owner.main(["attest", "--evidence", "private-marker"])
    assert "private-marker" not in str(capsys.readouterr())


def test_runtime_api_reads_narrow_projection_no_private_or_owner_access(
    db_engine, context, settings
):
    from altvia.main import create_app
    from altvia.provision import provision_runtime
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError
    from test_runtime_provision import runtime_url

    first = publish(db_engine, context)
    app_url = runtime_url(db_engine)
    worker_url = app_url.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        app_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    for url in (app_url, worker_url):
        engine = create_engine(url, hide_parameters=True)
        try:
            for statement in (
                "SELECT * FROM mail_case_origins",
                "SELECT source_id FROM mail_triage_cases",
                "SELECT * FROM inbound_mail_previews",
                "SELECT * FROM inbound_mail_variants",
                "SELECT * FROM mailbox_sources",
                "SELECT * FROM mailbox_poll_states",
                "UPDATE mail_triage_cases SET state='revoked'",
                "DELETE FROM mail_triage_cases",
            ):
                with pytest.raises(DBAPIError), engine.begin() as connection:
                    connection.execute(text(statement))
            with pytest.raises(CaseError, match="owner_required"):
                revoke_case(engine, first.case_id, 1)
            with pytest.raises(CaseError, match="owner_required"):
                attest_case(
                    engine, first.case_id, UUID(context["requester_id"]), 1, "synthetic:proof"
                )
            if url.username == "altvia_worker":
                with pytest.raises(DBAPIError), engine.begin() as connection:
                    connection.execute(text("SELECT message_id FROM mail_triage_cases"))
                from altvia.activity import consume_event

                with Session(db_engine) as db:
                    event_id = db.scalar(
                        select(OutboxEvent.event_id).where(
                            OutboxEvent.aggregate_id == first.case_id
                        )
                    )
                assert consume_event(engine, event_id, datetime.now(UTC))
                with pytest.raises(DBAPIError), engine.begin() as connection:
                    connection.execute(text("SELECT body_text FROM mail_triage_cases"))
        finally:
            engine.dispose()
    runtime_settings = settings.model_copy(
        update={"database_url": SecretStr(app_url.render_as_string(hide_password=False))}
    )
    with TestClient(
        create_app(runtime_settings),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        sign_in(client, "employee@example.test")
        assert client.get("/api/v1/mail-cases").status_code == 200
        detail = client.get("/api/v1/mail-cases/" + str(first.case_id))
        assert detail.status_code == 200, detail.text
        assert detail.json()["body_text"] == "private-body"


def test_immutable_guards_atomic_event_failure_and_guarded_contraction(db_engine, context):
    from alembic import command
    from alembic.config import Config
    from altvia.models import MailboxSource
    from sqlalchemy.exc import DBAPIError

    first = publish(db_engine, context)
    for statement in (
        "UPDATE mail_triage_cases SET body_text='rewrite'",
        "UPDATE mail_case_origins SET evidence='rewrite'",
        "DELETE FROM mail_triage_cases",
        "DELETE FROM mail_case_origins",
    ):
        with pytest.raises(DBAPIError), db_engine.begin() as connection:
            connection.execute(text(statement))
    with pytest.raises(DBAPIError):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000022")
    receipt = capture(db_engine, RAW, uid=2)
    normalize_variant(db_engine, receipt.variant_id)
    with Session(db_engine) as db:
        before = db.scalar(select(MailboxSource.version))
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE outbox_events ADD CONSTRAINT test_refuse_case "
                "CHECK(event_type<>'mail.case_aliased')"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            attest_case(
                db_engine, receipt.variant_id, UUID(context["requester_id"]), 1, "synthetic:proof"
            )
        with Session(db_engine) as db:
            assert db.get(MailTriageCase, first.case_id).version == 1
            assert db.get(MailCaseOrigin, receipt.variant_id) is None
            assert db.scalar(select(MailboxSource.version)) == before
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE outbox_events DROP CONSTRAINT test_refuse_case"))


def test_concurrent_attestation_and_capture_publication_race(db_engine, context):
    from concurrent.futures import ThreadPoolExecutor

    receipt = capture(db_engine, RAW)
    normalize_variant(db_engine, receipt.variant_id)

    def attest():
        return attest_case(
            db_engine, receipt.variant_id, UUID(context["requester_id"]), 1, "synthetic:proof"
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda _: attest(), range(4)))
    assert sum(not r.replayed for r in rows) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        publication = pool.submit(lambda: publish(db_engine, context, uid=2))
        collision = pool.submit(lambda: capture(db_engine, RAW + b"collision"))
        collision.result(timeout=10)
        try:
            publication.result(timeout=10)
        except CaseError:
            pass
    with Session(db_engine) as db:
        assert db.get(MailTriageCase, rows[0].case_id).state == "collision"


def test_empty_case_migration_roundtrip_and_drift(db_engine, seeded_user):
    from alembic import command
    from alembic.config import Config

    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000022")
    command.upgrade(config, "head")
    command.check(config)


@pytest.mark.parametrize(
    "state", ["queued", "preparing", "transmitting", "accepted", "failed", "uncertain"]
)
def test_every_generated_outbound_id_reserved_only_in_own_context(
    db_engine, admin_client, seeded_user, state
):
    from uuid import uuid4

    from altvia.models import ClientContact, OutboundMessage
    from test_mail_delivery import enqueue, prepared

    refs, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    queued = enqueue(admin_client, path, message, account, participant)
    assert queued.status_code == 201
    delivery_id = UUID(queued.json()["delivery_id"])
    with Session(db_engine) as db, db.begin():
        register_source(db, "synthetic-source", UUID(refs["queue_id"]))
        delivery = db.get(OutboundMessage, delivery_id)
        delivery.state = state
        delivery.accepted_at = datetime.now(UTC) if state == "accepted" else None
        delivery.lease_token = uuid4() if state in {"preparing", "transmitting"} else None
        delivery.lease_until = datetime.now(UTC) if delivery.lease_token else None
        claimed = RAW.replace(b"<incoming@example.test>", delivery.smtp_message_id.encode())
    with pytest.raises(CaseError, match="reserved_message_id"):
        publish(db_engine, refs, claimed)
    with Session(db_engine) as db, db.begin():
        assert not list(db.scalars(select(MailCaseOrigin)))
        assert not list(db.scalars(select(MailTriageCase)))
        assert db.get(OutboundMessage, delivery_id).state == state
        other = ClientContact(
            client_id=UUID(refs["client_id"]),
            display_name="Other",
            email_normalized="other@example.test",
        )
        db.add(other)
        db.flush()
        other_id = other.id
    receipt = capture(
        db_engine, claimed.replace(b"requester@example.test", b"other@example.test"), uid=2
    )
    normalize_variant(db_engine, receipt.variant_id)
    foreign = attest_case(db_engine, receipt.variant_id, other_id, 1, "synthetic:proof")
    assert foreign.state == "ready"
    with Session(db_engine) as db:
        assert db.get(OutboundMessage, delivery_id).state == state


def test_old_capture_collision_before_waiting_publication_refuses_atomically(db_engine, context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from altvia.mail_intake import capture_message
    from altvia.models import MailboxSource

    receipt = capture(db_engine, RAW)
    normalize_variant(db_engine, receipt.variant_id)
    started = Event()

    def attest():
        started.set()
        return attest_case(
            db_engine, receipt.variant_id, UUID(context["requester_id"]), 1, "synthetic:proof"
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(db_engine) as db, db.begin():
            db.execute(select(MailboxSource).with_for_update()).all()
            waiting = pool.submit(attest)
            assert started.wait(5)
            capture_message(db, "synthetic-source", 1, 1, RAW + b"old-capture")
        with pytest.raises(CaseError, match="receipt_collision"):
            waiting.result(timeout=10)
    with Session(db_engine) as db:
        assert not list(db.scalars(select(MailTriageCase)))
        assert not list(db.scalars(select(MailCaseOrigin)))


def test_case_version_exhaustion_rolls_back_late_capture_and_origin(db_engine, context):
    from altvia.models import InboundMailEnvelope, InboundMailVariant, MailboxSource
    from sqlalchemy.exc import DBAPIError

    first = publish(db_engine, context)
    with db_engine.begin() as connection:
        connection.execute(text("ALTER TABLE mail_triage_cases DISABLE TRIGGER mail_case_guard"))
        connection.execute(text("UPDATE mail_triage_cases SET version=2147483647"))
        connection.execute(text("ALTER TABLE mail_triage_cases ENABLE TRIGGER mail_case_guard"))
    with Session(db_engine) as db:
        before = db.scalar(select(MailboxSource.version))
    with pytest.raises(DBAPIError):
        capture(db_engine, RAW + b"collision")
    with Session(db_engine) as db:
        assert db.scalar(select(InboundMailEnvelope.state)) == "quarantine"
        assert len(list(db.scalars(select(InboundMailVariant)))) == 1
        assert db.scalar(select(MailboxSource.version)) == before
        assert db.get(MailTriageCase, first.case_id).state == "ready"
    with pytest.raises(CaseError, match="case_version_exhausted"):
        publish(db_engine, context, uid=2)


def test_refused_malformed_or_mismatching_mail_never_publishes(db_engine, context):
    for uid, raw in enumerate(
        (
            RAW.replace(b"<incoming@example.test>", b"broken"),
            RAW.replace(b"requester@example.test", b"stranger@example.test"),
        ),
        1,
    ):
        with pytest.raises(CaseError):
            publish(db_engine, context, raw, uid=uid)
    with Session(db_engine) as db:
        assert not list(db.scalars(select(MailCaseOrigin)))
        assert not list(db.scalars(select(MailTriageCase)))


@pytest.mark.parametrize("poison", ["body_text", "source_id", "state", "actor_kind"])
def test_case_event_consumer_rejects_extra_or_invalid_metadata(db_engine, context, poison):
    from altvia.activity import consume_event

    first = publish(db_engine, context)
    with Session(db_engine) as db, db.begin():
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == first.case_id))
        event.payload = {**event.payload, poison: "private-poison"}
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"


def test_revocation_remains_available_after_parent_and_contact_archive(db_engine, context):
    first = publish(db_engine, context)
    with db_engine.begin() as connection:
        for table in ("clients", "teams", "ticket_queues", "client_contacts"):
            connection.execute(text(f"UPDATE {table} SET active=false"))
    revoke_case(db_engine, first.case_id, 1)
    with Session(db_engine) as db:
        assert db.get(MailTriageCase, first.case_id).state == "revoked"


def test_same_id_same_mailbox_other_client_remains_independent_and_hidden(
    db_engine, context, admin_client
):
    from altvia.models import Client, ClientContact

    first = publish(db_engine, context)
    with Session(db_engine) as db, db.begin():
        client = Client(
            name="Foreign customer", created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
        )
        db.add(client)
        db.flush()
        contact = ClientContact(
            client_id=client.id,
            display_name="Foreign requester",
            email_normalized="requester@example.test",
        )
        db.add(contact)
        db.flush()
        contact_id, client_id = contact.id, client.id
    receipt = capture(db_engine, RAW.replace(b"private-body", b"foreign-body"), uid=2)
    normalize_variant(db_engine, receipt.variant_id)
    foreign = attest_case(db_engine, receipt.variant_id, contact_id, 1, "synthetic:foreign-proof")
    assert foreign.case_id != first.case_id
    with Session(db_engine) as db:
        assert db.get(MailTriageCase, first.case_id).state == "ready"
    assert admin_client.get("/api/v1/mail-cases/" + str(foreign.case_id)).status_code == 404
    assert (
        admin_client.get("/api/v1/mail-cases", params={"client_id": str(client_id)}).json()["items"]
        == []
    )


def test_owner_cli_lazy_storage_fixed_refusal_and_no_stdin(db_engine, context, monkeypatch, capsys):
    import sys

    from altvia import mail_cases_owner
    from test_mail_case_files import message, variant

    class NoStdin:
        def read(self, *args):
            pytest.fail("Owner classification must not consume stdin")

        @property
        def buffer(self):
            pytest.fail("Owner classification must not consume binary stdin")

    monkeypatch.setattr(sys, "stdin", NoStdin())
    monkeypatch.setenv("ALTVIA_ALLOW_MAIL_CASES", "1")
    monkeypatch.setenv("ALTVIA_STORAGE_FILE", "/private-unavailable-storage-marker")
    # The owner subtype needs only DB and optional storage, never API/worker config.
    monkeypatch.delenv("ALTVIA_PUBLIC_ORIGIN", raising=False)
    args = [
        "attest",
        "--variant-id",
        str(variant(db_engine, RAW)),
        "--contact-id",
        context["requester_id"],
        "--contact-version",
        "1",
        "--evidence",
        "synthetic:proof",
    ]
    assert mail_cases_owner.main(args) == 0
    output = capsys.readouterr()
    assert "private-" not in output.out and output.err == ""
    args[2] = str(variant(db_engine, message().replace(b"<incoming@", b"<files@"), uid=2))
    assert mail_cases_owner.main(args) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Mail case command refused; no classification acknowledged.\n"
