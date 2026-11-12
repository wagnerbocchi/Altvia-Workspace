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
        forbidden = [
            marker,
            payload["public_marker"].encode(),
            payload["account"]["username"].encode(),
            payload["account"]["password"].encode(),
            initial[4].encode(),
            initial[5].encode(),
        ]
        for key in redis.scan_iter(count=100):
            assert all(value not in key for value in forbidden)
            kind = redis.type(key)
            # Decode actual values; Redis DUMP may compress a leaked marker.
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
                    assert payload["private_marker"] not in json.dumps(value)
                    assert payload["public_marker"] not in json.dumps(value)

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
                    for secret in (
                        payload["private_marker"],
                        payload["public_marker"],
                        account["password"],
                        account["username"],
                        initial[4],
                        initial[5],
                    ):
                        assert secret.encode() not in diagnostics
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
                                "restricted_privileges": True,
                                "private_note_excluded": True,
                                "redis_events_diagnostics_excluded": True,
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
