"""Isolated HTTPS/owner/restricted-worker orchestration; no provider or production writes."""

import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from email import policy
from email.parser import BytesParser
from pathlib import Path
from uuid import UUID, uuid4


def assert_incoming_wire(wire, root, body, private_marker):
    """Inspect real decoded MIME, including the first attested incoming root."""
    message = BytesParser(policy=policy.default).parsebytes(wire)
    assert str(message["In-Reply-To"]) == root
    assert str(message["References"]).split() == [root]
    assert message.get_content_type() == "text/plain" and not message.is_multipart()
    assert message.get_content().replace("\r\n", "\n") == body + "\n"
    assert private_marker not in message.get_content()
    assert private_marker.encode() not in wire


def worker_privacy_markers(payload, initial):
    """Metadata/log rules, deliberately separate from allowed SMTP references."""
    return tuple(
        dict.fromkeys(
            value.encode()
            for value in (
                payload["private_marker"],
                payload["public_marker"],
                payload["account"]["username"],
                payload["account"]["password"],
                initial[4],
                initial[5],
                *payload.get("privacy_canaries", ()),
            )
        )
    )


def assert_worker_diagnostics(diagnostics, forbidden):
    if isinstance(diagnostics, str):
        diagnostics = diagnostics.encode()
    for secret in forbidden:
        assert secret not in diagnostics


def inspect_worker_metadata(redis, engine, forbidden):
    """One checker for live SMTP children and all later incoming checkpoints."""
    from sqlalchemy import text

    assert forbidden and all(forbidden)
    for key in redis.scan_iter(count=100):
        assert all(value not in key for value in forbidden)
        kind = redis.type(key)
        # Inspect actual decoded values, never potentially compressed Redis DUMP.
        if kind == b"string":
            values = [redis.get(key)]
        elif kind == b"hash":
            values = [part for pair in redis.hscan_iter(key) for part in pair]
        elif kind == b"list":
            values = redis.lrange(key, 0, -1)
        elif kind == b"set":
            values = redis.smembers(key)
        elif kind == b"zset":
            values = redis.zrange(key, 0, -1)
        else:
            assert kind == b"none", "Unexpected Redis value type in proof"
            values = []
        assert all(needle not in (value or b"") for value in values for needle in forbidden)
    with engine.connect() as db:
        for table, column in (("outbox_events", "payload"), ("activity_events", "details")):
            for value in db.scalars(text("SELECT " + column + " FROM " + table)):
                assert_worker_diagnostics(json.dumps(value), forbidden)


def processed_events_complete(rows, expected):
    assert expected, "An empty event set cannot prove worker completion"
    return {row[0] for row in rows} == set(expected) and all(
        row[1] == "delivered" and row[2] is not None for row in rows
    )


def packaged_worker_privacy_checkpoint():
    """Observe existing main-worker completion and Redis through its real role."""
    from altvia.config import WorkerSettings
    from altvia.database import make_engine
    from altvia.models import OutboxEvent, ProcessedEvent
    from redis import Redis
    from sqlalchemy import and_, select, text

    assert os.environ.get("ALTVIA_ALLOW_CONTAINER_TEST") == "1"
    payload = json.load(sys.stdin)
    expected = [UUID(value) for value in payload["event_ids"]]
    forbidden = tuple(value.encode() for value in payload["metadata_markers"])
    settings = WorkerSettings()
    engine = make_engine(settings, worker_timeouts=True)
    redis = Redis.from_url(settings.redis_url.get_secret_value(), socket_timeout=2)
    try:
        with engine.connect() as db:
            assert db.scalar(text("SELECT current_user")) == "altvia_worker"
        deadline, scans = time.monotonic() + 45, 0
        while True:
            inspect_worker_metadata(redis, engine, forbidden)
            scans += 1
            with engine.connect() as db:
                rows = db.execute(
                    select(
                        OutboxEvent.event_id,
                        OutboxEvent.status,
                        ProcessedEvent.processed_at,
                    )
                    .outerjoin(
                        ProcessedEvent,
                        and_(
                            ProcessedEvent.event_id == OutboxEvent.event_id,
                            ProcessedEvent.consumer == "identity_activity_v1",
                        ),
                    )
                    .where(OutboxEvent.event_id.in_(expected))
                ).all()
            if processed_events_complete(rows, expected):
                break
            assert time.monotonic() < deadline, "Relevant main-worker events did not complete"
            time.sleep(0.1)
        inspect_worker_metadata(redis, engine, forbidden)
        print(
            json.dumps(
                {
                    "phase": payload["phase"],
                    "completed_events": len(expected),
                    "event_ids_sha256": hashlib.sha256(
                        "\n".join(sorted(payload["event_ids"])).encode()
                    ).hexdigest(),
                    "redis_scans": scans + 1,
                    "metadata_marker_count": len(forbidden),
                    "actual_worker_role": True,
                    "delivered_and_processed": True,
                    "decoded_redis_and_sql_checked": True,
                }
            )
        )
    finally:
        redis.close()
        engine.dispose()


OWNER_INCOMING_EVENTS = """
import json,sys
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.models import OutboxEvent
p=json.load(sys.stdin)
with Session(make_engine(DatabaseSettings())) as db:
    rows=db.execute(select(OutboxEvent.event_id,OutboxEvent.event_type,OutboxEvent.schema_version)
      .where(OutboxEvent.aggregate_id.in_([UUID(v) for v in p['aggregate_ids']]))
      .order_by(OutboxEvent.event_id)).all()
    assert rows
    print(json.dumps([{'event_id':str(r[0]),'type':r[1],'schema':r[2]} for r in rows]))
"""


def incoming_privacy_checkpoint(run, compose, root, context, phase):
    events = json.loads(
        run(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "migrate",
                "python",
                "-c",
                OWNER_INCOMING_EVENTS,
            ],
            data=json.dumps(context),
        )
    )
    assert (
        sum(row["type"] == "ticket.message_received" for row in events) == context["incoming_count"]
    )
    if phase in {"after-collision", "after-recreation"}:
        assert any(row["type"] == "mail.case_aliased" and row["schema"] == 2 for row in events)
    code = (root / "scripts/packaged_smtp_proof.py").read_text(encoding="utf-8")
    code += (
        "\nos.environ['ALTVIA_ALLOW_CONTAINER_TEST']='1'\npackaged_worker_privacy_checkpoint()\n"
    )
    result = json.loads(
        run(
            [*compose, "exec", "-T", "worker", "python", "-c", code],
            data=json.dumps(
                {**context, "phase": phase, "event_ids": [row["event_id"] for row in events]}
            ),
        )
    )
    # Same diagnostic checker as the stopped SMTP child; this checks the existing
    # main process only after actual relevant events have been delivered/processed.
    assert_worker_diagnostics(
        run([*compose, "logs", "--no-color", "api", "worker"]),
        tuple(value.encode() for value in context["metadata_markers"]),
    )
    return {**result, "main_diagnostics_checked": True}


OWNER_SETUP = """
import json,sys
from uuid import UUID
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.mail_intake import register_source
from altvia.mail_participants import register_sender,attest_requester
from altvia.mail_settings import SMTPAccount
p=json.load(sys.stdin)
with Session(make_engine(DatabaseSettings())) as db,db.begin():
    source=register_source(db,'packaged-smtp',UUID(p['queue_id']))
    account=SMTPAccount.model_validate({**p['account'],'source_id':source.id})
    register_sender(db,account)
    participant=attest_requester(db,UUID(p['ticket_id']),p['version'],'synthetic-packaged-only')
    print(json.dumps({'source_id':str(source.id),'participant_id':str(participant.id)}))
"""

OWNER_SNAPSHOT = """
import hashlib,json,sys
from uuid import UUID
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.models import OutboundMessage,OutboxEvent,ActivityEvent,AuditLog,TicketNote
p=json.load(sys.stdin)
with Session(make_engine(DatabaseSettings())) as db:
    rows=[]
    for item in p['items']:
        delivery=db.get(OutboundMessage,UUID(item['delivery_id']))
        assert delivery.ticket_id==UUID(item['ticket_id'])
        assert db.scalar(select(TicketNote.body_text).where(
            TicketNote.ticket_id==delivery.ticket_id))==p['private_marker']
        assert db.scalar(select(func.count()).select_from(OutboundMessage).where(
            OutboundMessage.message_id==delivery.message_id))==1
        rows.append({'delivery_id':str(delivery.id),'state':delivery.state,
          'attempts':delivery.attempts,
          'accepted_at':delivery.accepted_at.isoformat() if delivery.accepted_at else None,
          'wire_sha256':hashlib.sha256(delivery.wire).hexdigest(),
          'message_id_sha256':hashlib.sha256(delivery.smtp_message_id.encode()).hexdigest()})
    for model,column in ((OutboxEvent,OutboxEvent.payload),(ActivityEvent,ActivityEvent.details),
                         (AuditLog,AuditLog.details)):
        for value in db.scalars(select(column)):
            serialized=json.dumps(value)
            assert p['private_marker'] not in serialized
            assert all(item['public_marker'] not in serialized for item in p['items'])
    print(json.dumps(rows))
"""

INCOMING_PRIVILEGES = """
import json,sys
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.mail_cases_owner import main
p=json.load(sys.stdin)
with make_engine(DatabaseSettings()).connect() as db:
    assert db.scalar(text('SELECT current_user'))==p['role']
    for table in ('mailbox_sources','inbound_mail_envelopes','inbound_mail_variants',
                  'mailbox_poll_states','inbound_mail_previews','mail_case_origins'):
        for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
            assert not db.scalar(text('SELECT has_table_privilege(current_user,:t,:p)'),
                                 {'t':table,'p':privilege})
            if privilege!='DELETE':
                assert not db.scalar(text('SELECT has_any_column_privilege(current_user,:t,:p)'),
                                     {'t':table,'p':privilege})
        try:
            with db.begin_nested():
                db.execute(text('SELECT * FROM '+table+' LIMIT 0'))
        except DBAPIError as error:
            assert error.orig.sqlstate=='42501'
        else:
            raise AssertionError('Private SELECT succeeded')
import os,io
from contextlib import redirect_stdout,redirect_stderr
os.environ['ALTVIA_ALLOW_MAIL_CASES']='1'
out,err=io.StringIO(),io.StringIO()
with redirect_stdout(out),redirect_stderr(err):
    assert main(['attest','--variant-id',p['variant_id'],'--contact-id',p['contact_id'],
                 '--contact-version',str(p['contact_version']),
                 '--evidence','synthetic-packaged-incoming-only'])==1
assert out.getvalue()==''
assert err.getvalue()=='Mail case command refused; no classification acknowledged.\\n'
print(json.dumps({'role':p['role'],'table_column_and_actual_select_denial':True,
                  'owner_command_refused':True}))
"""

INCOMING_SNAPSHOT = """
import hashlib,json,sys
from uuid import UUID
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.models import (MailTriageCase,MailCaseOrigin,TicketIncomingMessage,InboundMailVariant,
    InboundMailPreview,TicketParticipant,OutboundMessage,OutboxEvent,AuditLog,ActivityEvent)
p=json.load(sys.stdin)
with Session(make_engine(DatabaseSettings())) as db:
    rows=[]
    for item in p['items']:
        case=db.get(MailTriageCase,UUID(item['case_id']))
        incoming=db.get(TicketIncomingMessage,UUID(item['incoming_message_id']))
        assert str(case.ticket_id)==item['ticket_id'] and case.incoming_message_id==incoming.id
        assert incoming.case_id==case.id
        assert db.scalar(select(func.count()).select_from(TicketIncomingMessage).where(
            TicketIncomingMessage.case_id==case.id))==1
        origin=db.get(MailCaseOrigin,UUID(item['variant_id']))
        variant=db.get(InboundMailVariant,origin.variant_id)
        preview=db.get(InboundMailPreview,(variant.id,2))
        assert hashlib.sha256(variant.raw_message).hexdigest()==item['raw_sha256']
        assert case.body_text==preview.body_text==item['body_text']
        rows.append({'case_id':str(case.id),'state':case.state,'version':case.version,
          'ticket_id':str(case.ticket_id),'incoming_message_id':str(incoming.id),
          'ticket_version':incoming.ticket_version,'received_at':case.received_at.isoformat(),
          'recorded_at':incoming.recorded_at.isoformat(),
          'raw_sha256':item['raw_sha256'],
          'text_sha256':hashlib.sha256(case.body_text.encode()).hexdigest()})
    for model,column in ((OutboxEvent,OutboxEvent.payload),(ActivityEvent,ActivityEvent.details),
                         (AuditLog,AuditLog.details)):
        for value in db.scalars(select(column)):
            serialized=json.dumps(value)
            assert all(marker not in serialized for marker in p['canaries'])
    delivery=db.get(OutboundMessage,UUID(p['delivery_id']))
    assert delivery.state=='accepted' and delivery.attempts==1
    print(json.dumps({'incoming':rows,'wire_sha256':hashlib.sha256(delivery.wire).hexdigest(),
      'accepted_at':delivery.accepted_at.isoformat(),'message_id':delivery.smtp_message_id}))
"""


def prepare_packaged_incoming(
    client, denied, reader, ticket_body, run, compose, root, secret_dir, sender_account
):
    """Ordinary scoped HTTPS writes after distinct explicit synthetic owner operations."""
    if os.environ.get("ALTVIA_ALLOW_CONTAINER_TEST") != "1":
        raise RuntimeError("Explicit synthetic container test required")

    def owner(code, payload):
        return json.loads(
            run(
                [*compose, "run", "--rm", "--no-deps", "-T", "migrate", "python", "-c", code],
                data=json.dumps(payload),
            )
        )

    nonce = uuid4().hex
    contact_path = f"/api/v1/clients/{ticket_body['client_id']}/contacts"
    created_contact = client.post(
        contact_path,
        json={
            "display_name": "Packaged classified requester",
            "email": f"classified-{nonce}@example.test",
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created_contact.status_code == 201
    contact = client.get(contact_path + "/" + created_contact.json()["contact_id"])
    assert contact.status_code == 200
    contact = contact.json()
    root_id = "<packaged-incoming-" + nonce + "@example.test>"
    private = "incoming-private-note-" + nonce
    public = "incoming-public-reply-" + nonce
    bodies = [
        "classified-first-" + nonce,
        "classified-reply-" + nonce,
        "classified-reopen-" + nonce,
    ]
    canaries = [
        private,
        public,
        *bodies,
        contact["email_normalized"],
        root_id,
        "synthetic-packaged-incoming-only",
        "synthetic-packaged-alias-only",
    ]
    imap_code = (root / "apps/api/tests/imap_fixture.py").read_text(encoding="utf-8")
    imap_code += "\n" + (root / "scripts/packaged_imap_proof.py").read_text(encoding="utf-8")
    imap_code += "\npackaged_classified_imap_proof(imap_server)\n"

    def capture(index, references=None):
        raw = (
            "From: "
            + contact["email_normalized"]
            + "\r\nMessage-ID: "
            + (root_id if index == 0 else f"<packaged-reply-{index}-{nonce}@example.test>")
            + "\r\nSubject: Synthetic incoming classified\r\n"
            + ("References: " + references + "\r\n" if references else "")
            + "Content-Type: text/plain; charset=us-ascii\r\n\r\n"
            + bodies[index]
        )
        payload = {
            "raw": raw,
            "source_key": f"classified-{index}-{nonce}",
            "queue_id": ticket_body["queue_id"],
            "contact_id": contact["id"],
            "contact_version": contact["version"],
            "cert": (secret_dir / "imap_cert").read_text(),
            "key": (secret_dir / "imap_key").read_text(),
        }
        result = json.loads(
            run(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "-e",
                    "ALTVIA_ALLOW_CONTAINER_TEST=1",
                    "migrate",
                    "python",
                    "-c",
                    imap_code,
                ],
                data=json.dumps(payload),
            )
        )
        return {**result, "raw": raw, "body_text": bodies[index]}

    operations = []

    def promotion(case, intent, expected_version=1):
        path = "/api/v1/mail-cases/" + case["case_id"] + "/promotion"
        headers = {"If-Match": f'"{expected_version}"', "Idempotency-Key": uuid4().hex}
        assert client.post(path, json=intent).status_code == 428
        assert denied.get(path.rsplit("/", 1)[0]).status_code == 404
        assert denied.post(path, json=intent, headers=headers).status_code == 404
        assert reader.get(path.rsplit("/", 1)[0]).status_code == 200
        assert reader.post(path, json=intent, headers=headers).status_code == 403
        result = client.post(path, json=intent, headers=headers)
        assert result.status_code == 201, result.text
        receipt = result.json()
        replay = client.post(path, json=intent, headers=headers)
        assert replay.status_code == 200 and replay.json() == receipt
        assert (
            client.post(
                path, json=intent, headers={**headers, "Idempotency-Key": uuid4().hex}
            ).status_code
            == 409
        )
        assert (
            client.post(
                path,
                json={**intent, "priority": "low"}
                if intent["action"] == "create"
                else {**intent, "ticket_version": intent["ticket_version"] + 1},
                headers=headers,
            ).status_code
            == 409
        )
        operations.append(
            {"path": path, "intent": intent, "headers": headers, "receipt": receipt, "case": case}
        )
        return receipt

    first = capture(0)
    receipt = promotion(
        first,
        {
            "action": "create",
            "subject": "Reviewed packaged incoming",
            "priority": "high",
            "assignee_id": ticket_body["assignee_id"],
        },
    )
    ticket_id = receipt["ticket_id"]
    path = "/api/v1/tickets/" + ticket_id
    assert client.get(path).json()["source"] == "email"
    assert client.get(path).json()["description"] == ""
    assert client.get(path + "/delivery-choices").json()["participant"] is None
    # The case classification NEVER creates the separately attested SMTP requester.
    # One immutable sender per queue. Reuse the already exercised synthetic
    # account without changing any earlier source, wire or delivery status.
    account = dict(sender_account)
    setup = owner(
        OWNER_SETUP,
        {
            "account": account,
            "ticket_id": ticket_id,
            "queue_id": ticket_body["queue_id"],
            "version": 2,
        },
    )
    account["source_id"] = setup["source_id"]
    assert setup["source_id"] != first["source_id"]
    assert (
        client.post(
            path + "/notes",
            json={"body_text": private},
            headers={"If-Match": '"2"', "Idempotency-Key": uuid4().hex},
        ).status_code
        == 201
    )
    body = "Actual public response\n" + public + "\n.literal"
    message = client.post(
        path + "/messages",
        json={"body_text": body},
        headers={"If-Match": '"3"', "Idempotency-Key": uuid4().hex},
    )
    assert message.status_code == 201
    delivery_path = path + "/messages/" + message.json()["message_id"] + "/delivery"
    queued = client.post(
        delivery_path,
        json={"source_id": setup["source_id"], "participant_id": setup["participant_id"]},
        headers={"If-Match": '"4"', "Idempotency-Key": uuid4().hex},
    )
    assert queued.status_code == 201
    code = (root / "scripts/packaged_smtp_fixture.py").read_text(encoding="utf-8")
    code += "\n" + (root / "scripts/packaged_smtp_proof.py").read_text(encoding="utf-8")
    code += "\npackaged_smtp_worker_proof(synthetic_relay)\n"
    worker = json.loads(
        run(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "-e",
                "ALTVIA_ALLOW_CONTAINER_TEST=1",
                "worker",
                "python",
                "-c",
                code,
            ],
            data=json.dumps(
                {
                    "delivery_id": queued.json()["delivery_id"],
                    "account": account,
                    "mode": "accepted",
                    "private_marker": private,
                    "public_marker": public,
                    "body_text": body,
                    "incoming_root": root_id,
                    "privacy_canaries": canaries,
                    "cert": (secret_dir / "imap_cert").read_text(),
                    "key": (secret_dir / "imap_key").read_text(),
                }
            ),
            timeout=150,
        )
    )
    status = client.get(delivery_path).json()
    assert status["state"] == "accepted" and status["attempts"] == 1
    privacy_checkpoints = []

    def privacy_context():
        return {
            "aggregate_ids": [
                ticket_id,
                *(
                    value
                    for operation in operations
                    for value in (
                        operation["case"]["source_id"],
                        operation["case"]["case_id"],
                    )
                ),
            ],
            "incoming_count": len(operations),
            "metadata_markers": list(
                dict.fromkeys(
                    [
                        *canaries,
                        account["username"],
                        account["password"],
                        account["from_email"],
                    ]
                )
            ),
        }

    second = capture(1, root_id + " " + status["smtp_message_id"])
    detail = client.get("/api/v1/mail-cases/" + second["case_id"]).json()
    assert detail["can_append"] and detail["candidate_ticket_id"] == ticket_id
    promotion(
        second, {"action": "append", "ticket_id": ticket_id, "ticket_version": 5, "reopen": False}
    )
    privacy_checkpoints.append(
        incoming_privacy_checkpoint(
            run,
            compose,
            root,
            privacy_context(),
            "after-append",
        )
    )
    for version, state in ((6, "open"), (7, "resolved"), (8, "closed")):
        changed = client.post(
            path + "/transitions",
            json={"target_status": state, "reason": "Synthetic packaged lifecycle"},
            headers={"If-Match": f'"{version}"', "Idempotency-Key": uuid4().hex},
        )
        assert changed.status_code == 200, changed.text
    third = capture(2, status["smtp_message_id"])
    detail = client.get("/api/v1/mail-cases/" + third["case_id"]).json()
    assert detail["candidate_can_reopen"]
    intent = {"action": "append", "ticket_id": ticket_id, "ticket_version": 9, "reopen": False}
    assert (
        client.post(
            "/api/v1/mail-cases/" + third["case_id"] + "/promotion",
            json=intent,
            headers={"If-Match": '"1"', "Idempotency-Key": uuid4().hex},
        ).status_code
        == 409
    )
    promotion(
        third, {**intent, "reopen": True, "reopen_reason": "Reviewed synthetic incoming reply"}
    )
    assert client.get(path).json()["version"] == 11
    assert client.get(path).json()["status"] == "open"
    privacy_checkpoints.append(
        incoming_privacy_checkpoint(
            run,
            compose,
            root,
            privacy_context(),
            "after-reopen",
        )
    )
    # Independently attested byte-identical alias after promotion, then a real raw
    # contradiction of that alias: no rewritten wire, text, timestamp or receipt.
    alias_code = """
import json,sys
from uuid import UUID
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.mail_intake import capture_message
from altvia.mail_normalize import normalize_variant
from altvia.mail_cases_owner import attest_case
p=json.load(sys.stdin);engine=make_engine(DatabaseSettings())
with Session(engine) as db,db.begin():
    alias=capture_message(db,p['source_key'],1,2,p['raw'].encode('ascii'))
normalize_variant(engine,alias.variant_id)
result=attest_case(engine,alias.variant_id,UUID(p['contact_id']),p['contact_version'],
                   'synthetic-packaged-alias-only')
assert str(result.case_id)==p['case_id']
assert result.state=='promoted' and result.disposition=='alias'
with Session(engine) as db,db.begin():
    collision=capture_message(db,p['source_key'],1,2,(p['raw']+' contradiction').encode('ascii'))
    assert collision.state=='collision'
print(json.dumps({'alias_preserved_receipt':True,'late_raw_collision':True}))
"""
    alias = owner(
        alias_code, {**first, "contact_id": contact["id"], "contact_version": contact["version"]}
    )
    assert client.get("/api/v1/mail-cases/" + first["case_id"]).json()["state"] == "collision"
    privacy_checkpoints.append(
        incoming_privacy_checkpoint(
            run,
            compose,
            root,
            privacy_context(),
            "after-collision",
        )
    )
    for operation in operations:
        for actor, status_code in ((reader, 403), (denied, 404)):
            response = actor.post(
                operation["path"], json=operation["intent"], headers=operation["headers"]
            )
            assert response.status_code == status_code
    assert (
        client.post(
            operations[0]["path"],
            json=operations[0]["intent"],
            headers={**operations[0]["headers"], "Idempotency-Key": uuid4().hex},
        ).status_code
        == 409
    )
    assert denied.get(path + "/conversation").status_code == 404
    assert (
        denied.get(path + "/incoming-messages/" + receipt["incoming_message_id"]).status_code == 404
    )
    assert reader.get(path + "/notes").status_code == 403
    reader_conversation = reader.get(path + "/conversation")
    assert reader_conversation.status_code == 200
    assert private not in json.dumps(reader_conversation.json())
    logs = run([*compose, "logs", "--no-color", "api", "worker"])
    assert all(marker not in logs for marker in canaries)
    assert_worker_diagnostics(
        logs, tuple(value.encode() for value in privacy_context()["metadata_markers"])
    )
    role_proofs = []
    for service, role in (("api", "altvia_app"), ("worker", "altvia_worker")):
        role_proofs.append(
            json.loads(
                run(
                    [*compose, "exec", "-T", service, "python", "-c", INCOMING_PRIVILEGES],
                    data=json.dumps(
                        {
                            "role": role,
                            "variant_id": first["variant_id"],
                            "contact_id": contact["id"],
                            "contact_version": contact["version"],
                        }
                    ),
                )
            )
        )
    snapshot_payload = {
        "items": [{**op["case"], **op["receipt"]} for op in operations],
        "canaries": canaries,
        "delivery_id": queued.json()["delivery_id"],
    }
    snapshot = owner(INCOMING_SNAPSHOT, snapshot_payload)
    assert snapshot["wire_sha256"] == worker["wire_sha256"]
    return {
        "operations": operations,
        "snapshot_payload": snapshot_payload,
        "snapshot": snapshot,
        "worker": worker,
        "alias": alias,
        "roles": role_proofs,
        "ticket_id": ticket_id,
        "delivery_path": delivery_path,
        "status": status,
        "private_marker": private,
        "diagnostics_private_text_excluded": True,
        "privacy_context": privacy_context(),
        "privacy_checkpoints": privacy_checkpoints,
    }


def verify_packaged_incoming_restart(client, proof, run, compose, work):
    for operation in proof["operations"]:
        result = client.post(
            operation["path"], json=operation["intent"], headers=operation["headers"]
        )
        assert result.status_code == 200 and result.json() == operation["receipt"]
        receipt = operation["receipt"]
        path = "/api/v1/tickets/" + receipt["ticket_id"]
        message = client.get(path + "/incoming-messages/" + receipt["incoming_message_id"])
        assert message.status_code == 200
        assert message.json()["body_text"] == operation["case"]["body_text"]
        assert message.json()["invalidation_warning"] == (
            "incoming_attestation_invalidated" if operation is proof["operations"][0] else None
        )
    conversation = client.get("/api/v1/tickets/" + proof["ticket_id"] + "/conversation")
    assert conversation.status_code == 200
    items = conversation.json()["items"]
    assert [item["ticket_version"] for item in items] == [2, 4, 6, 11]
    assert [item["kind"] for item in items] == ["incoming", "outbound", "incoming", "incoming"]
    assert proof["private_marker"] not in json.dumps(conversation.json())
    assert client.get(proof["delivery_path"]).json() == proof["status"]
    snapshot = json.loads(
        run(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "migrate",
                "python",
                "-c",
                INCOMING_SNAPSHOT,
            ],
            data=json.dumps(proof["snapshot_payload"]),
        )
    )
    assert snapshot == proof["snapshot"]
    after_restart = incoming_privacy_checkpoint(
        run,
        compose,
        Path(__file__).resolve().parents[1],
        proof["privacy_context"],
        "after-recreation",
    )
    (work / "incoming-conversation-proof.json").write_text(
        json.dumps(
            {
                "synthetic_only": True,
                "api_postgres_recreation": True,
                "separate_requester_attestation": True,
                "distinct_receiving_sending_sources": True,
                "protected_replay": True,
                "denied_actors": True,
                "explicit_closed_reopen": True,
                "conversation_private_note_excluded": True,
                "diagnostics_private_text_excluded": proof["diagnostics_private_text_excluded"],
                "frozen": snapshot,
                "worker": proof["worker"],
                "alias": proof["alias"],
                "roles": proof["roles"],
                "privacy_checkpoints": [*proof["privacy_checkpoints"], after_restart],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def prepare_packaged_smtp(client, ticket_body, run, compose, root, secret_dir):
    """Create independent fixtures using the current ordinary authenticated binding."""
    private_marker = "packaged-private-" + uuid4().hex
    account = {
        "source_id": str(uuid4()),
        "host": "localhost",
        "port": 20265,
        "tls_mode": "implicit",
        "username": secrets.token_urlsafe(24),
        "password": secrets.token_urlsafe(32),
        "from_email": "synthetic-support@example.test",
        "ca_file": "/tmp/packaged-smtp-ca",
    }

    def owner(code, payload):
        return json.loads(
            run(
                [*compose, "run", "--rm", "--no-deps", "-T", "migrate", "python", "-c", code],
                data=json.dumps(payload),
            )
        )

    fixture = (root / "scripts/packaged_smtp_fixture.py").read_text(encoding="utf-8")
    proof_code = (root / "scripts/packaged_smtp_proof.py").read_text(encoding="utf-8")
    records, proofs = [], []
    for mode in ("accepted", "lost", "held"):
        created = client.post(
            "/api/v1/tickets",
            json={**ticket_body, "subject": "Packaged synthetic SMTP " + mode},
            headers={"Idempotency-Key": uuid4().hex},
        )
        assert created.status_code == 201
        ticket_id = created.json()["ticket_id"]
        path = "/api/v1/tickets/" + ticket_id
        note = client.post(
            path + "/notes",
            json={"body_text": private_marker},
            headers={"If-Match": '"1"', "Idempotency-Key": uuid4().hex},
        )
        assert note.status_code == 201
        # A single-line ASCII canary survives JSON escaping at every boundary.
        public_marker = "packaged-public-" + uuid4().hex
        body = "Packaged synthetic public response " + mode + ".\n" + public_marker + "\n.literal"
        message = client.post(
            path + "/messages",
            json={"body_text": body},
            headers={"If-Match": '"2"', "Idempotency-Key": uuid4().hex},
        )
        assert message.status_code == 201
        setup = owner(
            OWNER_SETUP,
            {
                "account": account,
                "ticket_id": ticket_id,
                "queue_id": ticket_body["queue_id"],
                "version": 3,
            },
        )
        account["source_id"] = setup["source_id"]
        choices = client.get(path + "/delivery-choices")
        assert choices.status_code == 200 and choices.json()["can_send"]
        message_id = message.json()["message_id"]
        delivery_path = path + "/messages/" + message_id + "/delivery"
        payload = {"source_id": setup["source_id"], "participant_id": setup["participant_id"]}
        headers = {"If-Match": '"3"', "Idempotency-Key": uuid4().hex}
        queued = client.post(delivery_path, json=payload, headers=headers)
        assert queued.status_code == 201
        replay = client.post(delivery_path, json=payload, headers=headers)
        assert replay.status_code == 200 and replay.json() == queued.json()
        record = {
            "ticket_id": ticket_id,
            "message_id": message_id,
            "delivery_id": queued.json()["delivery_id"],
            "body_text": body,
            "public_marker": public_marker,
            "delivery_path": delivery_path,
        }
        proof = json.loads(
            run(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "-e",
                    "ALTVIA_ALLOW_CONTAINER_TEST=1",
                    "worker",
                    "python",
                    "-c",
                    fixture + "\n" + proof_code + "\npackaged_smtp_worker_proof(synthetic_relay)\n",
                ],
                data=json.dumps(
                    {
                        **record,
                        "account": account,
                        "mode": mode,
                        "private_marker": private_marker,
                        "cert": (secret_dir / "imap_cert").read_text(),
                        "key": (secret_dir / "imap_key").read_text(),
                    }
                ),
                timeout=150,
            )
        )
        status = client.get(delivery_path)
        expected = "accepted" if mode == "accepted" else "uncertain"
        assert status.status_code == 200
        assert status.json()["state"] == expected and status.json()["attempts"] == 1
        assert bool(status.json()["accepted_at"]) == (mode == "accepted")
        assert (
            hashlib.sha256(status.json()["smtp_message_id"].encode()).hexdigest()
            == proof["message_id_sha256"]
        )
        projected = client.get(path + "/messages").json()["items"]
        assert len(projected) == 1 and projected[0]["delivery_status"] == expected
        assert projected[0]["body_text"] == body
        assert client.get(path).json()["version"] == 4
        record["status"] = status.json()
        records.append(record)
        proofs.append({**proof, "protected_replay": True, "https_projection": True})
    snapshot_payload = {"items": records, "private_marker": private_marker}
    return {
        "records": records,
        "proofs": proofs,
        "snapshot_payload": snapshot_payload,
        "frozen": owner(OWNER_SNAPSHOT, snapshot_payload),
        "private_account": account,
    }


def verify_packaged_smtp_restart(client, proof, run, compose, work):
    for row in proof["records"]:
        response = client.get(row["delivery_path"])
        assert response.status_code == 200 and response.json() == row["status"]
        messages = client.get("/api/v1/tickets/" + row["ticket_id"] + "/messages")
        assert messages.status_code == 200
        assert messages.json()["items"][0]["delivery_status"] == row["status"]["state"]
    snapshot = json.loads(
        run(
            [*compose, "run", "--rm", "--no-deps", "-T", "migrate", "python", "-c", OWNER_SNAPSHOT],
            data=json.dumps(proof["snapshot_payload"]),
        )
    )
    assert snapshot == proof["frozen"]
    (work / "mail-delivery-proof.json").write_text(
        json.dumps(
            {
                "synthetic_only": True,
                "server_acceptance_only": True,
                "worker_role": "altvia_worker",
                "private_metadata_excluded": True,
                "api_postgres_recreation": True,
                "frozen": snapshot,
                "scenarios": proof["proofs"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def packaged_smtp_worker_proof(serve):
    """Run inside an ordinary worker-service container, with no owner secret mounted."""
    from altvia.config import WorkerSettings
    from altvia.database import make_engine
    from redis import Redis
    from sqlalchemy import text

    assert os.environ.get("ALTVIA_ALLOW_CONTAINER_TEST") == "1"
    payload = json.load(sys.stdin)
    identifier = UUID(payload["delivery_id"])
    settings = WorkerSettings()
    engine = make_engine(settings, worker_timeouts=True)
    redis = Redis.from_url(settings.redis_url.get_secret_value(), socket_timeout=2)
    marker = payload["private_marker"].encode()
    with engine.connect() as db:
        assert db.scalar(text("SELECT current_user")) == "altvia_worker"
        for table in (
            "ticket_notes",
            "inbound_mail_envelopes",
            "inbound_mail_variants",
            "mailbox_poll_states",
            "inbound_mail_previews",
            "mailbox_sources",
            "mail_triage_cases",
            "mail_case_origins",
            "ticket_incoming_messages",
        ):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                assert not db.scalar(
                    text("SELECT has_table_privilege(current_user,:t,:p)"),
                    {"t": table, "p": privilege},
                )
                if privilege != "DELETE":
                    assert not db.scalar(
                        text("SELECT has_any_column_privilege(current_user,:t,:p)"),
                        {"t": table, "p": privilege},
                    )
        for table in ("ticket_participants", "mail_senders"):
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                assert not db.scalar(
                    text("SELECT has_table_privilege(current_user,:t,:p)"),
                    {"t": table, "p": privilege},
                )
                if privilege != "DELETE":
                    assert not db.scalar(
                        text("SELECT has_any_column_privilege(current_user,:t,:p)"),
                        {"t": table, "p": privilege},
                    )
        for table, column in (("ticket_participants", "evidence"), ("users", "password_hash")):
            assert not db.scalar(
                text("SELECT has_column_privilege(current_user,:t,:c,'SELECT')"),
                {"t": table, "c": column},
            )

    def state():
        with engine.connect() as db:
            return db.execute(
                text(
                    "SELECT state,attempts,wire,smtp_message_id,"
                    "envelope_from,envelope_to FROM outbound_messages WHERE id=:id"
                ),
                {"id": identifier},
            ).one()

    def inspect_metadata():
        inspect_worker_metadata(redis, engine, worker_privacy_markers(payload, initial))

    process = None
    try:
        with tempfile.TemporaryDirectory(prefix="packaged-smtp-") as folder:
            folder = Path(folder)
            cert, key, accounts = folder / "cert", folder / "key", folder / "accounts"
            cert.write_text(payload["cert"], encoding="ascii")
            key.write_text(payload["key"], encoding="ascii")
            key.chmod(0o600)
            account = {**payload["account"], "ca_file": str(cert)}
            accounts.write_text(json.dumps([account]), encoding="utf-8")
            accounts.chmod(0o600)
            child_env = {
                **os.environ,
                "ALTVIA_SMTP_ACCOUNTS_FILE": str(accounts),
                "ALTVIA_WORKER_STATE_DIR": str(folder / "worker"),
            }
            with (folder / "worker.log").open("w+b") as log:
                generation = 0
                heartbeat = None

                def start():
                    nonlocal generation, heartbeat
                    generation += 1
                    state_dir = folder / ("worker-" + str(generation))
                    heartbeat = state_dir / "heartbeat"
                    return subprocess.Popen(
                        [sys.executable, "-m", "altvia.worker", "run"],
                        env={**child_env, "ALTVIA_WORKER_STATE_DIR": str(state_dir)},
                        stdout=log,
                        stderr=log,
                    )

                def stop():
                    began = time.monotonic()
                    process.send_signal(signal.SIGTERM)
                    code = process.wait(timeout=29)
                    elapsed = time.monotonic() - began
                    assert code == 0 and elapsed < 30
                    return {"exit_code": code, "elapsed_seconds": round(elapsed, 3)}

                initial = state()
                assert initial[0:2] == ("queued", 0)
                with serve(cert, key, mode=payload["mode"], port=account["port"]) as relay:
                    process = start()
                    deadline = time.monotonic() + 55
                    expected = "accepted" if payload["mode"] == "accepted" else "uncertain"
                    while time.monotonic() < deadline:
                        assert process.poll() is None, "Packaged worker exited early"
                        inspect_metadata()
                        current = state()
                        if payload["mode"] == "held" and relay.received.is_set():
                            assert current[0] == "transmitting"
                            shutdown = stop()
                            break
                        if payload["mode"] != "held" and current[0] == expected:
                            shutdown = stop()
                            break
                        time.sleep(0.05)
                    else:
                        raise RuntimeError("Packaged SMTP scenario timed out")
                    current = state()
                    assert current[0:2] == (expected, 1)
                    assert relay.data_count == 1 and relay.messages == [initial[2]]
                    assert relay.envelopes == [(initial[4], initial[5])]
                    message = BytesParser(policy=policy.default).parsebytes(relay.messages[0])
                    assert message["Message-ID"] == initial[3] == current[3]
                    assert message.get_content_type() == "text/plain" and not message.is_multipart()
                    assert (
                        message.get_content().replace("\r\n", "\n") == payload["body_text"] + "\n"
                    )
                    assert marker not in relay.messages[0]
                    if "incoming_root" in payload:
                        assert_incoming_wire(
                            relay.messages[0],
                            payload["incoming_root"],
                            payload["body_text"],
                            payload["private_marker"],
                        )
                    if payload["mode"] == "accepted":
                        assert relay.accepted_reply.wait(2)
                    assert relay.final_250_count == (payload["mode"] == "accepted")
                    # A real new main process sees terminal/uncertain SQL and emits no DATA.
                    process = start()
                    deadline = time.monotonic() + 15
                    while not heartbeat.is_file():
                        assert process.poll() is None, "Restarted main exited before readiness"
                        assert time.monotonic() < deadline, "Restarted main did not become ready"
                        inspect_metadata()
                        time.sleep(0.1)
                    deadline = time.monotonic() + 12
                    while time.monotonic() < deadline:
                        assert process.poll() is None
                        inspect_metadata()
                        assert state()[0:4] == current[0:4]
                        assert relay.data_count == 1
                        time.sleep(0.1)
                    restarted_shutdown = stop()
                    inspect_metadata()
                    log.flush()
                    log.seek(0)
                    diagnostics = log.read()
                    assert_worker_diagnostics(diagnostics, worker_privacy_markers(payload, initial))
                    print(
                        json.dumps(
                            {
                                "delivery_id": str(identifier),
                                "scenario": payload["mode"],
                                "state": current[0],
                                "attempts": current[1],
                                "smtp_data_count": relay.data_count,
                                "final_250_count": relay.final_250_count,
                                "verified_tls": True,
                                "exact_frozen_wire_envelope_body": True,
                                "message_id_sha256": hashlib.sha256(
                                    initial[3].encode()
                                ).hexdigest(),
                                "wire_sha256": hashlib.sha256(initial[2]).hexdigest(),
                                "restricted_privileges": True,
                                "private_note_excluded": True,
                                "redis_events_diagnostics_excluded": True,
                                "incoming_privacy_canaries_checked": len(
                                    payload.get("privacy_canaries", ())
                                ),
                                "restart_no_second_data": True,
                                "restarted_main_fresh_heartbeat": True,
                                "shutdown": shutdown,
                                "restarted_shutdown": restarted_shutdown,
                                "active_data_sigterm": payload["mode"] == "held",
                            }
                        )
                    )
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                # Cleanup only this task child. A kill never counts as acceptance evidence.
                process.kill()
                process.wait(timeout=5)
        redis.close()
        engine.dispose()
