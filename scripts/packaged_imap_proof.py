"""Synthetic proof executed with the reviewed loopback fixture in an owner container."""

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from uuid import UUID

from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.imap_poll import main
from altvia.mail_intake import record_intake_event, register_source
from altvia.mail_normalize import main as normalize_main
from altvia.models import InboundMailEnvelope, InboundMailPreview, InboundMailVariant, MailboxSource
from sqlalchemy import select
from sqlalchemy.orm import Session


def packaged_imap_proof(serve):
    if os.environ.get("ALTVIA_ALLOW_CONTAINER_TEST") != "1":
        raise RuntimeError("Explicit synthetic container test required")
    payload = json.load(sys.stdin)
    engine = make_engine(DatabaseSettings())
    with Session(engine) as db, db.begin():
        register_source(db, "packaged-imaps", UUID(payload["queue_id"]))
    try:
        with tempfile.TemporaryDirectory() as directory:
            cert, key = Path(directory) / "cert", Path(directory) / "key"
            cert.write_text(payload["cert"], encoding="ascii")
            key.write_text(payload["key"], encoding="ascii")
            key.chmod(0o600)
            with serve(cert, key) as server:
                server.state["messages"][1] = (
                    b"Subject: Synthetic private MIME\r\nContent-Type: text/html\r\n\r\n"
                    b"<p>Synthetic private text</p><script>never-visible</script>"
                )
                os.environ.update(
                    {
                        "ALTVIA_ALLOW_IMAP_POLL": "1",
                        "ALTVIA_IMAP_HOST": "localhost",
                        "ALTVIA_IMAP_PORT": str(server.server_address[1]),
                        "ALTVIA_IMAP_USERNAME": server.state["username"],
                        "ALTVIA_IMAP_PASSWORD": server.state["password"],
                        "ALTVIA_IMAP_CA_FILE": str(cert),
                    }
                )
                receipts = []
                for _ in range(2):
                    captured = io.StringIO()
                    with redirect_stdout(captured):
                        assert main(["--source-key", "packaged-imaps"]) == 0
                    receipts.append(json.loads(captured.getvalue()))
                assert receipts[0]["captured"] == 1 and receipts[1]["captured"] == 0
                assert receipts[1]["last_uid"] == receipts[0]["last_uid"] == 1
                assert sum(b"UID FETCH" in c for c in server.state["commands"]) == 1
                with Session(engine) as db:
                    variant = db.scalar(
                        select(InboundMailVariant)
                        .join(
                            InboundMailEnvelope,
                            InboundMailVariant.envelope_id == InboundMailEnvelope.id,
                        )
                        .where(InboundMailEnvelope.source_id == UUID(receipts[0]["source_id"]))
                    )
                    assert variant.raw_message == server.state["messages"][1]
                    variant_id = variant.id
                    envelope_id = variant.envelope_id
                # Represent an existing immutable historical interpretation; the
                # PostgreSQL migration tests separately prove actual v1 upgrade.
                with Session(engine) as db, db.begin():
                    source = db.scalar(
                        select(MailboxSource)
                        .where(MailboxSource.id == UUID(receipts[0]["source_id"]))
                        .with_for_update()
                    )
                    db.add(
                        InboundMailPreview(
                            variant_id=variant_id,
                            parser_version=1,
                            status="ready",
                            subject="Synthetic legacy subject",
                            body_text="Synthetic legacy interpretation",
                            part_count=1,
                            attachment_count=0,
                        )
                    )
                    source.version += 1
                    db.flush()
                    record_intake_event(
                        db,
                        source,
                        "mailbox.message_normalized",
                        {
                            "envelope_id": str(envelope_id),
                            "variant_id": str(variant_id),
                            "status": "ready",
                        },
                    )
                os.environ["ALTVIA_ALLOW_MAIL_NORMALIZE"] = "1"
                for replay in (False, True):
                    captured = io.StringIO()
                    with redirect_stdout(captured):
                        assert normalize_main(["--variant-id", str(variant_id)]) == 0
                    receipt = json.loads(captured.getvalue())
                    assert receipt["replayed"] is replay and receipt["status"] == "ready"
                    assert receipt["parser_version"] == 2
                    assert "Synthetic private" not in captured.getvalue()
                with Session(engine) as db:
                    preview = db.get(InboundMailPreview, (variant_id, 2))
                    assert preview.body_text == "Synthetic private text" and preview.reason is None
                    legacy = db.get(InboundMailPreview, (variant_id, 1))
                    assert legacy.body_text == "Synthetic legacy interpretation"
        print(
            json.dumps(
                {
                    "source_id": receipts[0]["source_id"],
                    "last_uid": 1,
                    "variant_id": str(variant_id),
                }
            )
        )
    finally:
        engine.dispose()


def packaged_classified_imap_proof(serve):
    """A NEW source, distinct text, actual poll/parser2/owner command boundary."""
    import hashlib

    from altvia.mail_cases_owner import main as cases_main

    if os.environ.get("ALTVIA_ALLOW_CONTAINER_TEST") != "1":
        raise RuntimeError("Explicit synthetic container test required")
    payload = json.load(sys.stdin)
    engine = make_engine(DatabaseSettings())
    raw = payload["raw"].encode("ascii")
    try:
        with Session(engine) as db, db.begin():
            source = register_source(db, payload["source_key"], UUID(payload["queue_id"]))
            source_id = str(source.id)
        with tempfile.TemporaryDirectory() as directory:
            cert, key = Path(directory) / "cert", Path(directory) / "key"
            cert.write_text(payload["cert"], encoding="ascii")
            key.write_text(payload["key"], encoding="ascii")
            key.chmod(0o600)
            with serve(cert, key, messages={1: raw}) as server:
                os.environ.update(
                    {
                        "ALTVIA_ALLOW_IMAP_POLL": "1",
                        "ALTVIA_IMAP_HOST": "localhost",
                        "ALTVIA_IMAP_PORT": str(server.server_address[1]),
                        "ALTVIA_IMAP_USERNAME": server.state["username"],
                        "ALTVIA_IMAP_PASSWORD": server.state["password"],
                        "ALTVIA_IMAP_CA_FILE": str(cert),
                        "ALTVIA_ALLOW_MAIL_NORMALIZE": "1",
                        "ALTVIA_ALLOW_MAIL_CASES": "1",
                    }
                )
                polls = []
                for _ in range(2):
                    output = io.StringIO()
                    with redirect_stdout(output):
                        assert main(["--source-key", payload["source_key"]]) == 0
                    polls.append(json.loads(output.getvalue()))
                assert [p["captured"] for p in polls] == [1, 0]
                assert sum(b"UID FETCH" in c for c in server.state["commands"]) == 1
        with Session(engine) as db:
            variant = db.scalar(
                select(InboundMailVariant)
                .join(InboundMailEnvelope, InboundMailVariant.envelope_id == InboundMailEnvelope.id)
                .where(InboundMailEnvelope.source_id == UUID(source_id))
            )
            assert variant.raw_message == raw
            variant_id = str(variant.id)
        output = io.StringIO()
        with redirect_stdout(output):
            assert normalize_main(["--variant-id", variant_id]) == 0
        normalized = json.loads(output.getvalue())
        assert normalized["parser_version"] == 2 and normalized["status"] == "ready"
        receipts = []
        for _ in range(2):
            output = io.StringIO()
            with redirect_stdout(output):
                assert (
                    cases_main(
                        [
                            "attest",
                            "--variant-id",
                            variant_id,
                            "--contact-id",
                            payload["contact_id"],
                            "--contact-version",
                            str(payload["contact_version"]),
                            "--evidence",
                            "synthetic-packaged-incoming-only",
                        ]
                    )
                    == 0
                )
            receipts.append(json.loads(output.getvalue()))
        assert not receipts[0]["replayed"] and receipts[1]["replayed"]
        assert receipts[0]["case_id"] == receipts[1]["case_id"]
        print(
            json.dumps(
                {
                    "source_id": source_id,
                    "source_key": payload["source_key"],
                    "variant_id": variant_id,
                    "case_id": receipts[0]["case_id"],
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    "parser_version": 2,
                    "verified_imaps": True,
                    "poll_and_attestation_replay": True,
                }
            )
        )
    finally:
        engine.dispose()
