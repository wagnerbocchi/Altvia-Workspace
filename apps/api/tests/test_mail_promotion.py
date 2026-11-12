"""Synthetic incoming promotion through real protected HTTP and PostgreSQL."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_mail_cases import RAW, context, publish
from test_team_api import admin_client, preconditions, sign_in

__all__ = ["admin_client", "context"]


def promote(client, case_id, body=None, version=1, key=None):
    return client.post(
        f"/api/v1/mail-cases/{case_id}/promotion",
        json=body or {"action": "create", "subject": "Reviewed subject", "priority": "high"},
        headers=preconditions(version, key),
    )


def test_create_snapshot_receipt_replay_and_conversation(db_engine, context, admin_client):
    first = publish(db_engine, context)
    key = uuid4().hex
    response = promote(admin_client, first.case_id, key=key)
    assert response.status_code == 201, response.text
    receipt = response.json()
    assert set(receipt) == {"case_id", "ticket_id", "incoming_message_id"}
    path = "/api/v1/tickets/" + receipt["ticket_id"]
    item = admin_client.get(path).json()
    assert item["source"] == "email" and item["version"] == 2 and item["description"] == ""
    case_detail = admin_client.get(f"/api/v1/mail-cases/{first.case_id}").json()
    assert case_detail["client_name"] == item["client_name"]
    assert case_detail["queue_name"] == item["queue_name"]
    assert promote(admin_client, first.case_id, key=key).json() == receipt
    assert promote(admin_client, first.case_id, key=key).status_code == 200
    assert promote(admin_client, first.case_id).status_code == 409
    conversation = admin_client.get(path + "/conversation").json()
    incoming = conversation["items"][0]
    assert incoming["kind"] == "incoming" and incoming["body_text"] == "private-body"
    assert incoming["subject"] == "private-subject" and incoming["ticket_version"] == 2
    assert incoming["invalidation_warning"] is None
    assert (
        admin_client.get(path + "/incoming-messages/" + receipt["incoming_message_id"]).json()
        == incoming
    )
    assert admin_client.get(path + "/messages").json()["items"] == []
    assert admin_client.get(path + "/delivery-choices").json()["participant"] is None


def test_detail_receipt_survives_reload_for_readers_but_not_hidden_ticket(
    db_engine, context, admin_client
):
    from altvia.mail_cases_owner import revoke_case

    first = publish(db_engine, context)
    path = f"/api/v1/mail-cases/{first.case_id}"
    assert admin_client.get(path).json()["promotion_receipt"] is None
    receipt = promote(admin_client, first.case_id).json()
    assert admin_client.get(path).json()["promotion_receipt"] == receipt
    assert "promotion_receipt" not in admin_client.get("/api/v1/mail-cases").json()["items"][0]
    revoke_case(db_engine, first.case_id, 2)
    sign_in(admin_client, "viewer@example.test")
    detail = admin_client.get(path).json()
    assert detail["promotion_receipt"] == receipt and not detail["can_create"]
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path).status_code == 404


def test_known_incoming_anchor_append_requires_participant_and_current_write(
    db_engine, context, admin_client
):
    from altvia.mail_participants import attest_requester

    first = publish(db_engine, context)
    receipt = promote(admin_client, first.case_id).json()
    raw = RAW.replace(b"<incoming@", b"<reply@").replace(
        b"Subject:",
        b"In-Reply-To: <incoming@example.test>\r\nReferences: <unknown@example.test>\r\nSubject:",
    )
    reply = publish(db_engine, context, raw, uid=2)
    body = {
        "action": "append",
        "ticket_id": receipt["ticket_id"],
        "ticket_version": 2,
        "reopen": False,
    }
    assert promote(admin_client, reply.case_id, body).status_code == 409
    assert promote(admin_client, reply.case_id).status_code == 409
    with Session(db_engine) as db, db.begin():
        attest_requester(db, UUID(receipt["ticket_id"]), 2, "synthetic:proof")
    detail = admin_client.get(f"/api/v1/mail-cases/{reply.case_id}").json()
    assert detail["can_append"] and not detail["can_create"]
    assert detail["candidate_ticket_id"] == receipt["ticket_id"]
    response = promote(admin_client, reply.case_id, body)
    assert response.status_code == 201, response.text
    sign_in(admin_client, "agent@example.test")
    assert promote(admin_client, reply.case_id, body).status_code == 403


def test_incoming_event_is_metadata_only(db_engine, context, admin_client):
    from datetime import UTC, datetime

    from altvia.activity import consume_event
    from altvia.models import OutboxEvent

    first = publish(db_engine, context)
    assert promote(admin_client, first.case_id).status_code == 201
    with Session(db_engine) as db:
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "ticket.message_received")
        )
        assert set(event.payload) == {
            "actor_id",
            "actor_kind",
            "ticket_id",
            "client_id",
            "queue_id",
            "incoming_message_id",
        }
        assert "private-" not in str(event.payload)
        event_id = event.event_id
    assert consume_event(db_engine, event_id, datetime.now(UTC))


def promoted(client, engine, refs, *, key=None):
    from altvia.mail_participants import attest_requester

    first = publish(engine, refs)
    response = promote(client, first.case_id, key=key)
    assert response.status_code == 201, response.text
    receipt = response.json()
    with Session(engine) as db, db.begin():
        attest_requester(db, UUID(receipt["ticket_id"]), 2, "synthetic:proof")
    return first, receipt, "/api/v1/tickets/" + receipt["ticket_id"]


def reply(engine, refs, uid=2, ancestors="<incoming@example.test>", token=None):
    headers = f"References: {ancestors}\r\n" if ancestors else ""
    if token:
        headers += f"X-Altvia-Thread: {token}\r\n"
    raw = RAW.replace(b"<incoming@", f"<reply{uid}@".encode()).replace(
        b"Subject:", headers.encode() + b"Subject:"
    )
    return publish(engine, refs, raw, uid=uid)


def append_intent(receipt, version=2, **changes):
    return {
        "action": "append",
        "ticket_id": receipt["ticket_id"],
        "ticket_version": version,
        "reopen": False,
        **changes,
    }


@pytest.mark.parametrize("invalidation", ["collision", "revoked"])
def test_promotion_replay_and_history_survive_invalidation(
    db_engine, context, admin_client, invalidation
):
    from altvia.mail_cases_owner import revoke_case
    from test_mail_intake import capture

    key = uuid4().hex
    first, receipt, path = promoted(admin_client, db_engine, context, key=key)
    alias = publish(db_engine, context, uid=2)
    assert alias.case_id == first.case_id and alias.state == "promoted"
    with Session(db_engine) as db:
        from altvia.models import OutboxEvent

        event = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "mail.case_aliased"))
        assert event.schema_version == 2 and event.payload["state"] == "promoted"
        from altvia.mail_cases import validate_case_event

        validate_case_event(event)
    if invalidation == "collision":
        capture(db_engine, RAW + b"contradiction", uid=2)
    else:
        revoke_case(db_engine, first.case_id, 3)
    assert promote(admin_client, first.case_id, key=key).status_code == 200
    assert promote(admin_client, first.case_id, key=key).json() == receipt
    incoming = admin_client.get(path + "/incoming-messages/" + receipt["incoming_message_id"])
    assert incoming.json()["invalidation_warning"] == "incoming_attestation_invalidated"
    next_case = reply(db_engine, context, uid=3)
    assert promote(admin_client, next_case.case_id, append_intent(receipt)).status_code == 409
    assert promote(admin_client, next_case.case_id).status_code == 409


@pytest.mark.parametrize("closed", [False, True])
def test_explicit_reopen_has_two_versions_real_reason_and_existing_policy(
    db_engine, context, admin_client, closed
):
    from test_tickets import transition

    _, receipt, path = promoted(admin_client, db_engine, context)
    with db_engine.begin() as con:
        con.execute(text("UPDATE ticket_queues SET allow_reopen=true,allow_manual_close=true"))
    assert transition(admin_client, path, 2, "open").status_code == 200
    assert transition(admin_client, path, 3, "resolved", "done").status_code == 200
    version = 4
    if closed:
        assert transition(admin_client, path, version, "closed").status_code == 200
        version += 1
    next_case = reply(db_engine, context)
    body = append_intent(receipt, version, reopen=True)
    assert promote(admin_client, next_case.case_id, body).status_code == 422
    assert (
        promote(admin_client, next_case.case_id, {**body, "reopen_reason": "  "}).status_code == 422
    )
    with db_engine.begin() as con:
        con.execute(text("UPDATE ticket_queues SET allow_reopen=false"))
    assert (
        promote(admin_client, next_case.case_id, {**body, "reopen_reason": "reply"}).status_code
        == 409
    )
    with db_engine.begin() as con:
        con.execute(text("UPDATE ticket_queues SET allow_reopen=true"))
    key = uuid4().hex
    result = promote(admin_client, next_case.case_id, {**body, "reopen_reason": "reply"}, key=key)
    assert result.status_code == 201, result.text
    assert admin_client.get(path).json()["version"] == version + 2
    assert admin_client.get(path).json()["status"] == "open"
    assert (
        promote(
            admin_client, next_case.case_id, {**body, "reopen_reason": "reply"}, key=key
        ).status_code
        == 200
    )
    assert (
        promote(
            admin_client, next_case.case_id, {**body, "reopen_reason": "changed"}, key=key
        ).status_code
        == 409
    )
    assert (
        promote(
            admin_client,
            next_case.case_id,
            {**body, "ticket_version": version + 1, "reopen_reason": "reply"},
            key=key,
        ).status_code
        == 409
    )
    history = admin_client.get(path + "/status-history").json()["items"]
    assert history[0]["version"] == version + 1 and history[0]["reason"] == "reply"


def test_resolved_append_without_reopen_retains_status(db_engine, context, admin_client):
    from test_tickets import transition

    _, receipt, path = promoted(admin_client, db_engine, context)
    transition(admin_client, path, 2, "open")
    transition(admin_client, path, 3, "resolved", "done")
    case = reply(db_engine, context)
    assert promote(admin_client, case.case_id, append_intent(receipt, 4)).status_code == 201
    assert admin_client.get(path).json()["status"] == "resolved"


def test_all_known_own_anchors_resolved_before_action_filter(db_engine, context, admin_client):
    from altvia.mail_cases_owner import revoke_case

    first, receipt, path = promoted(admin_client, db_engine, context)
    other = publish(db_engine, context, RAW.replace(b"incoming@", b"other@"), uid=2)
    other_response = promote(admin_client, other.case_id)
    assert other_response.status_code == 201
    third = reply(db_engine, context, 3, "<incoming@example.test> <other@example.test>")
    assert promote(admin_client, third.case_id, append_intent(receipt)).status_code == 409
    assert promote(admin_client, third.case_id).status_code == 409
    revoke_case(db_engine, other.case_id, 2)
    assert promote(admin_client, third.case_id, append_intent(receipt)).status_code == 409
    assert (
        admin_client.get(f"/api/v1/mail-cases/{third.case_id}").json()["candidate_ticket_id"]
        is None
    )
    assert admin_client.get(path).json()["version"] == 2
    assert first.case_id != other.case_id


@pytest.mark.parametrize("change", ["email", "inactive", "participant", "requester"])
def test_current_requester_contact_and_participant_required(
    db_engine, context, admin_client, change
):
    from altvia.models import ClientContact

    _, receipt, _ = promoted(admin_client, db_engine, context)
    case = reply(db_engine, context)
    with Session(db_engine) as db, db.begin():
        if change == "email":
            db.execute(text("UPDATE client_contacts SET email_normalized='changed@example.test'"))
        elif change == "inactive":
            db.execute(text("UPDATE client_contacts SET active=false"))
        elif change == "participant":
            from altvia.mail_participants import revoke_requester
            from altvia.models import TicketParticipant

            revoke_requester(db, db.scalar(select(TicketParticipant.id)), 1)
        else:
            contact = ClientContact(
                client_id=UUID(context["client_id"]),
                display_name="Other",
                email_normalized="other@example.test",
            )
            db.add(contact)
            db.flush()
            db.execute(text("UPDATE tickets SET requester_id=:id"), {"id": contact.id})
    assert promote(admin_client, case.case_id, append_intent(receipt)).status_code == 409
    detail = admin_client.get(f"/api/v1/mail-cases/{case.case_id}").json()
    assert not detail["can_create"] and not detail["can_append"]


@pytest.mark.parametrize("token", [None, "a" * 64, "b" * 64])
def test_thread_token_only_corroborates_known_anchor(db_engine, context, admin_client, token):
    from altvia.models import TicketMailThread

    _, receipt, _ = promoted(admin_client, db_engine, context)
    with Session(db_engine) as db, db.begin():
        db.add(TicketMailThread(ticket_id=UUID(receipt["ticket_id"]), token="a" * 64))
    case = reply(db_engine, context, token=token)
    result = promote(admin_client, case.case_id, append_intent(receipt))
    assert result.status_code == (409 if token == "b" * 64 else 201), result.text
    token_only = reply(db_engine, context, uid=3, ancestors="", token="a" * 64)
    assert promote(admin_client, token_only.case_id, append_intent(receipt, 3)).status_code == 409


def test_protocol_complete_fingerprint_and_strict_body(db_engine, context, admin_client):
    first = publish(db_engine, context)
    path = f"/api/v1/mail-cases/{first.case_id}/promotion"
    body = {"action": "create", "subject": "Reviewed subject", "priority": "high"}
    assert admin_client.post(path, json=body).status_code == 428
    for extra in ("body_text", "client_id", "queue_id", "actor_id", "evidence", "source"):
        assert promote(admin_client, first.case_id, {**body, extra: "forged"}).status_code == 422
    key = uuid4().hex
    assert promote(admin_client, first.case_id, key=key).status_code == 201
    assert promote(admin_client, first.case_id, version=2, key=key).status_code == 409
    assert (
        promote(admin_client, first.case_id, {**body, "subject": "changed"}, key=key).status_code
        == 409
    )


def test_create_agent_unassigned_receipt_recovery_current_authority(
    db_engine, context, admin_client
):
    sign_in(admin_client, "agent@example.test")
    first = publish(db_engine, context)
    key = uuid4().hex
    result = promote(admin_client, first.case_id, key=key)
    assert result.status_code == 201, result.text
    path = "/api/v1/tickets/" + result.json()["ticket_id"]
    assert not admin_client.get(path).json()["can_update"]
    assert promote(admin_client, first.case_id, key=key).status_code == 200
    with db_engine.begin() as con:
        con.execute(
            text(
                "UPDATE role_bindings SET role_name='viewer' "
                "WHERE user_id=:id AND scope_kind='queue'"
            ),
            {"id": UUID(context["agent_id"])},
        )
    assert promote(admin_client, first.case_id, key=key).status_code == 403


def test_conversation_pagination_scope_and_authoritative_receipt(db_engine, context, admin_client):
    from test_ticket_messages import append
    from test_tickets import ticket

    _, receipt, path = promoted(admin_client, db_engine, context)
    draft = append(admin_client, path, version=2)
    assert draft.status_code == 201
    second = reply(db_engine, context)
    incoming = promote(admin_client, second.case_id, append_intent(receipt, 3))
    assert incoming.status_code == 201
    page = admin_client.get(path + "/conversation?limit=1").json()
    tail = admin_client.get(path + "/conversation", params={"cursor": page["next_cursor"]}).json()
    assert [row["kind"] for row in tail["items"]] == ["outbound", "incoming"]
    assert [row["ticket_version"] for row in tail["items"]] == [3, 4]
    confirmed = admin_client.get(
        path + "/incoming-messages/" + incoming.json()["incoming_message_id"]
    )
    assert confirmed.json() == tail["items"][1]
    other_path = ticket(admin_client, context)
    assert (
        admin_client.get(
            other_path + "/incoming-messages/" + receipt["incoming_message_id"]
        ).status_code
        == 404
    )
    assert (
        admin_client.get(
            other_path + "/conversation", params={"cursor": page["next_cursor"]}
        ).status_code
        == 422
    )
    sign_in(admin_client, "viewer@example.test")
    assert (
        admin_client.get(path + "/conversation", params={"cursor": page["next_cursor"]}).status_code
        == 422
    )
    assert admin_client.get(path + "/conversation").status_code == 200
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get(path + "/conversation").status_code == 404
    assert (
        admin_client.get(path + "/incoming-messages/" + receipt["incoming_message_id"]).status_code
        == 404
    )


def sender(engine, refs):
    from altvia.mail_intake import register_source
    from altvia.mail_participants import register_sender
    from altvia.mail_settings import SMTPAccount

    with Session(engine) as db, db.begin():
        source = register_source(db, "different-outgoing-source", UUID(refs["queue_id"]))
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
    return account


def freeze_reply(client, engine, refs, path):
    from test_mail_delivery import enqueue
    from test_ticket_messages import append

    account = sender(engine, refs)
    version = client.get(path).json()["version"]
    message = append(client, path, version=version).json()["message_id"]
    choices = client.get(path + "/delivery-choices").json()
    return enqueue(
        client,
        path,
        message,
        account,
        choices["participant"]["participant_id"],
        version=version + 1,
    )


@pytest.mark.parametrize("missing", [False, True])
def test_first_reply_actual_wire_references_original_or_explicit_missing_id(
    db_engine, context, admin_client, missing
):
    from email import policy
    from email.parser import BytesParser

    from altvia.mail_participants import attest_requester
    from altvia.models import OutboundMessage

    raw = RAW.replace(b"Message-ID: <incoming@example.test>\r\n", b"") if missing else RAW
    first = publish(db_engine, context, raw)
    receipt = promote(admin_client, first.case_id).json()
    path = "/api/v1/tickets/" + receipt["ticket_id"]
    with Session(db_engine) as db, db.begin():
        attest_requester(db, UUID(receipt["ticket_id"]), 2, "synthetic:proof")
    result = freeze_reply(admin_client, db_engine, context, path)
    assert result.status_code == 201, result.text
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, UUID(result.json()["delivery_id"]))
        parsed = BytesParser(policy=policy.default).parsebytes(row.wire)
        assert parsed["In-Reply-To"] == (None if missing else "<incoming@example.test>")
        assert parsed["References"] == (None if missing else "<incoming@example.test>")
        assert "private-body" not in parsed.get_content()


def test_first_reply_retains_root_after_many_incoming_and_later_uses_latest16(
    db_engine, context, admin_client
):
    from datetime import UTC, datetime
    from email import policy
    from email.parser import BytesParser

    from altvia.mail_delivery import reference_ids
    from altvia.models import OutboundMessage, Ticket, TicketParticipant

    _, receipt, path = promoted(admin_client, db_engine, context)
    for uid in range(2, 19):
        case = reply(db_engine, context, uid)
        assert promote(admin_client, case.case_id, append_intent(receipt, uid)).status_code == 201
    result = freeze_reply(admin_client, db_engine, context, path)
    assert result.status_code == 201, result.text
    with Session(db_engine) as db, db.begin():
        outgoing = db.get(OutboundMessage, UUID(result.json()["delivery_id"]))
        parsed = BytesParser(policy=policy.default).parsebytes(outgoing.wire)
        refs = str(parsed["References"]).split()
        assert refs == [
            "<incoming@example.test>",
            *[f"<reply{uid}@example.test>" for uid in range(4, 19)],
        ]
        assert parsed["In-Reply-To"] == "<reply18@example.test>"
        outgoing.state = "accepted"
        outgoing.accepted_at = datetime.now(UTC)
        db.flush()
        item = db.get(Ticket, UUID(receipt["ticket_id"]))
        participant = db.scalar(select(TicketParticipant))
        later = reference_ids(db, item, participant)
        assert len(later) == 16 and later[-1] == outgoing.smtp_message_id
        assert "<incoming@example.test>" not in later


def test_changed_requester_and_invalidated_anchors_excluded_from_new_freeze(
    db_engine, context, admin_client
):
    from datetime import UTC, datetime
    from email import policy
    from email.parser import BytesParser

    from altvia.mail_cases_owner import revoke_case
    from altvia.mail_participants import attest_requester, revoke_requester
    from altvia.models import ClientContact, OutboundMessage, TicketParticipant

    first, receipt, path = promoted(admin_client, db_engine, context)
    revoke_case(db_engine, first.case_id, 2)
    result = freeze_reply(admin_client, db_engine, context, path)
    assert result.status_code == 201
    with Session(db_engine) as db, db.begin():
        row = db.get(OutboundMessage, UUID(result.json()["delivery_id"]))
        assert BytesParser(policy=policy.default).parsebytes(row.wire)["References"] is None
        row.state = "accepted"
        row.accepted_at = datetime.now(UTC)
        revoke_requester(db, db.scalar(select(TicketParticipant.id)), 1)
        other = ClientContact(
            client_id=UUID(context["client_id"]),
            display_name="New requester",
            email_normalized="new@example.test",
        )
        db.add(other)
        db.flush()
        db.execute(text("UPDATE tickets SET requester_id=:id"), {"id": other.id})
        attest_requester(db, UUID(receipt["ticket_id"]), 4, "synthetic:new-proof")
    result = freeze_reply(admin_client, db_engine, context, path)
    assert result.status_code == 201, result.text
    with Session(db_engine) as db:
        row = db.get(OutboundMessage, UUID(result.json()["delivery_id"]))
        parsed = BytesParser(policy=policy.default).parsebytes(row.wire)
        assert parsed["References"] is None and parsed["To"] == "new@example.test"


def test_accepted_outbound_anchor_different_source_unknown_and_foreign_ancestors(
    db_engine, admin_client, seeded_user
):
    from datetime import UTC, datetime

    from altvia.mail_intake import register_source
    from altvia.models import OutboundMessage
    from test_mail_delivery import enqueue, prepared

    refs, path, message, account, participant = prepared(admin_client, db_engine, seeded_user)
    result = enqueue(admin_client, path, message, account, participant)
    assert result.status_code == 201
    with Session(db_engine) as db, db.begin():
        outgoing = db.get(OutboundMessage, UUID(result.json()["delivery_id"]))
        outgoing.state = "accepted"
        outgoing.accepted_at = datetime.now(UTC)
        anchor = outgoing.smtp_message_id
        register_source(db, "synthetic-source", UUID(refs["queue_id"]))
    case = reply(
        db_engine, refs, ancestors=f"<foreign@example.test> {anchor} <unknown@example.test>"
    )
    receipt = {"ticket_id": path.rsplit("/", 1)[1]}
    result = promote(admin_client, case.case_id, append_intent(receipt, 3))
    assert result.status_code == 201, result.text


def test_atomic_event_failure_and_concurrent_receipt_replay(db_engine, context, admin_client):
    from concurrent.futures import ThreadPoolExecutor

    from altvia.models import IdempotencyRecord, MailTriageCase, Ticket, TicketIncomingMessage

    first = publish(db_engine, context)
    key = uuid4().hex
    with db_engine.begin() as con:
        con.execute(
            text(
                "ALTER TABLE outbox_events ADD CONSTRAINT refuse_incoming "
                "CHECK(event_type<>'ticket.message_received')"
            )
        )
    try:
        assert promote(admin_client, first.case_id, key=key).status_code == 503
        with Session(db_engine) as db:
            assert db.scalar(select(Ticket.id)) is None
            assert db.scalar(select(TicketIncomingMessage.id)) is None
            assert db.get(MailTriageCase, first.case_id).state == "ready"
            assert (
                db.scalar(select(IdempotencyRecord.key).where(IdempotencyRecord.key == key)) is None
            )
    finally:
        with db_engine.begin() as con:
            con.execute(text("ALTER TABLE outbox_events DROP CONSTRAINT refuse_incoming"))
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: promote(admin_client, first.case_id, key=key), range(3)))
    assert sorted(row.status_code for row in results) == [200, 200, 201]
    assert results[0].json() == results[1].json() == results[2].json()


def test_anchor_collision_wins_before_waiting_promotion(db_engine, context, admin_client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from altvia.mail_intake import capture_message
    from altvia.models import MailTriageCase

    first, receipt, path = promoted(admin_client, db_engine, context)
    case = reply(db_engine, context)
    started = Event()

    def waiting():
        started.set()
        return promote(admin_client, case.case_id, append_intent(receipt))

    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(db_engine) as db, db.begin():
            db.execute(
                select(MailTriageCase.id)
                .where(MailTriageCase.id == first.case_id)
                .with_for_update()
            ).one()
            future = pool.submit(waiting)
            assert started.wait(5)
            capture_message(db, "synthetic-source", 1, 1, RAW + b"late-conflict")
        assert future.result(timeout=10).status_code == 409
    assert admin_client.get(path).json()["version"] == 2


def test_runtime_promotion_reads_worker_schema2_and_private_denials(db_engine, context, settings):
    from datetime import UTC, datetime

    from altvia.activity import consume_event
    from altvia.mail_participants import attest_requester
    from altvia.main import create_app
    from altvia.models import OutboxEvent
    from altvia.provision import provision_runtime
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError
    from test_runtime_provision import runtime_url

    first = publish(db_engine, context)
    url = runtime_url(db_engine)
    worker_url = url.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    runtime_settings = settings.model_copy(
        update={"database_url": SecretStr(url.render_as_string(hide_password=False))}
    )
    with TestClient(
        create_app(runtime_settings),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        sign_in(client, "employee@example.test")
        result = promote(client, first.case_id)
        assert result.status_code == 201, result.text
        receipt = result.json()
        path = "/api/v1/tickets/" + receipt["ticket_id"]
        with Session(db_engine) as db, db.begin():
            attest_requester(db, UUID(receipt["ticket_id"]), 2, "synthetic:runtime-proof")
        case = reply(db_engine, context)
        detail = client.get(f"/api/v1/mail-cases/{case.case_id}")
        assert detail.status_code == 200 and detail.json()["can_append"]
        assert promote(client, case.case_id, append_intent(receipt)).status_code == 201
        assert len(client.get(path + "/conversation").json()["items"]) == 2
        assert (
            client.get(path + "/incoming-messages/" + receipt["incoming_message_id"]).status_code
            == 200
        )
        assert freeze_reply(client, db_engine, context, path).status_code == 201
        publish(db_engine, context, uid=3)
    for role_url in (url, worker_url):
        engine = create_engine(role_url, hide_parameters=True)
        try:
            for statement in (
                "SELECT source_id FROM mail_triage_cases",
                "SELECT * FROM mail_case_origins",
                "SELECT * FROM inbound_mail_variants",
                "SELECT * FROM inbound_mail_previews",
                "SELECT * FROM mailbox_sources",
                "SELECT * FROM mailbox_poll_states",
                "SELECT evidence FROM ticket_participants",
                "UPDATE mail_triage_cases SET body_text='forged'",
                "DELETE FROM ticket_incoming_messages",
                "UPDATE ticket_incoming_messages SET ticket_version=3",
            ):
                with pytest.raises(DBAPIError), engine.begin() as con:
                    con.execute(text(statement))
            if role_url.username == "altvia_worker":
                with Session(db_engine) as db:
                    events = list(
                        db.scalars(
                            select(OutboxEvent.event_id).where(
                                OutboxEvent.event_type.in_(
                                    {"mail.case_aliased", "ticket.message_received"}
                                )
                            )
                        )
                    )
                for identifier in events:
                    assert consume_event(engine, identifier, datetime.now(UTC))
        finally:
            engine.dispose()


def test_real_foreign_context_ancestor_neither_routes_nor_blocks_own_anchor(
    db_engine, context, admin_client
):
    from altvia.mail_cases_owner import attest_case
    from altvia.mail_normalize import normalize_variant
    from altvia.models import ClientContact
    from test_mail_intake import capture

    _, receipt, _ = promoted(admin_client, db_engine, context)
    with Session(db_engine) as db, db.begin():
        contact = ClientContact(
            client_id=UUID(context["client_id"]),
            display_name="Foreign context",
            email_normalized="foreign@example.test",
        )
        db.add(contact)
        db.flush()
        contact_id = contact.id
    raw = RAW.replace(b"requester@example.test", b"foreign@example.test").replace(
        b"incoming@", b"foreign@"
    )
    captured = capture(db_engine, raw, uid=2)
    normalize_variant(db_engine, captured.variant_id)
    foreign = attest_case(db_engine, captured.variant_id, contact_id, 1, "synthetic:foreign-proof")
    assert promote(admin_client, foreign.case_id).status_code == 201
    case = reply(
        db_engine,
        context,
        3,
        "<incoming@example.test> <foreign@example.test> <unknown@example.test>",
    )
    assert promote(admin_client, case.case_id, append_intent(receipt)).status_code == 201
    only = reply(db_engine, context, 4, "<foreign@example.test>")
    assert promote(admin_client, only.case_id, append_intent(receipt, 3)).status_code == 409
    assert (
        admin_client.get(f"/api/v1/mail-cases/{only.case_id}").json()["candidate_ticket_id"] is None
    )


@pytest.mark.parametrize("target", ["case", "ticket"])
def test_version_exhaustion_does_not_partially_reopen_or_record(
    db_engine, context, admin_client, target
):
    from altvia.models import TicketIncomingMessage
    from test_tickets import transition

    _, receipt, path = promoted(admin_client, db_engine, context)
    case = reply(db_engine, context)
    body = append_intent(receipt)
    with db_engine.begin() as con:
        if target == "case":
            con.execute(text("ALTER TABLE mail_triage_cases DISABLE TRIGGER mail_case_guard"))
            con.execute(
                text("UPDATE mail_triage_cases SET version=2147483647 WHERE id=:id"),
                {"id": case.case_id},
            )
            con.execute(text("ALTER TABLE mail_triage_cases ENABLE TRIGGER mail_case_guard"))
        else:
            con.execute(text("UPDATE ticket_queues SET allow_reopen=true"))
    if target == "ticket":
        transition(admin_client, path, 2, "open")
        transition(admin_client, path, 3, "resolved", "done")
        with db_engine.begin() as con:
            con.execute(text("UPDATE tickets SET version=2147483646"))
        body = append_intent(receipt, 2147483646, reopen=True, reopen_reason="reply")
    response = promote(
        admin_client, case.case_id, body, version=2147483647 if target == "case" else 1
    )
    assert response.status_code == 409, response.text
    with Session(db_engine) as db:
        assert len(list(db.scalars(select(TicketIncomingMessage)))) == 1
    state = admin_client.get(path).json()
    assert state["version"] == (2 if target == "case" else 2147483646)
    assert state["status"] == ("new" if target == "case" else "resolved")


def test_sql_immutable_receipt_and_composite_parent_ownership(db_engine, context, admin_client):
    from sqlalchemy.exc import DBAPIError
    from test_tickets import ticket

    first, receipt, _ = promoted(admin_client, db_engine, context)
    other_path = ticket(admin_client, context)
    for statement in (
        "UPDATE ticket_incoming_messages SET received_at=now()",
        "DELETE FROM ticket_incoming_messages",
        "UPDATE mail_triage_cases SET ticket_id=:other,version=version+1 WHERE id=:case",
    ):
        with pytest.raises(DBAPIError), db_engine.begin() as con:
            con.execute(
                text(statement),
                {"other": UUID(other_path.rsplit("/", 1)[1]), "case": first.case_id},
            )
    with pytest.raises(DBAPIError), db_engine.begin() as con:
        con.execute(
            text(
                "INSERT INTO ticket_incoming_messages SELECT gen_random_uuid(),case_id,"
                "ticket_id,client_id,queue_id,ticket_version+1,actor_id,received_at,recorded_at "
                "FROM ticket_incoming_messages WHERE id=:id"
            ),
            {"id": UUID(receipt["incoming_message_id"])},
        )


@pytest.mark.parametrize("revocation", ["ceiling", "session", "assignment"])
def test_append_receipt_rechecks_current_staff_authority(
    db_engine, context, admin_client, revocation
):
    from altvia.models import User

    _, receipt, _ = promoted(admin_client, db_engine, context)
    case = reply(db_engine, context)
    key = uuid4().hex
    body = append_intent(receipt)
    assert promote(admin_client, case.case_id, body, key=key).status_code == 201
    with db_engine.begin() as con:
        if revocation == "ceiling":
            con.execute(text("DELETE FROM client_access_grants"))
        elif revocation == "session":
            con.execute(text("UPDATE users SET auth_version=auth_version+1"))
        else:
            with Session(db_engine) as db:
                actor_id = db.scalar(
                    select(User.id).where(User.email_normalized == "employee@example.test")
                )
            con.execute(
                text(
                    "UPDATE role_bindings SET role_name='agent' "
                    "WHERE user_id=:id AND scope_kind='queue'"
                ),
                {"id": actor_id},
            )
    expected = {"ceiling": 404, "session": 401, "assignment": 403}[revocation]
    assert promote(admin_client, case.case_id, body, key=key).status_code == expected
