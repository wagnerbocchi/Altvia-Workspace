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
from altvia.mail_intake import register_source
from altvia.mail_normalize import main as normalize_main
from altvia.models import InboundMailEnvelope, InboundMailPreview, InboundMailVariant
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
                os.environ["ALTVIA_ALLOW_MAIL_NORMALIZE"] = "1"
                for replay in (False, True):
                    captured = io.StringIO()
                    with redirect_stdout(captured):
                        assert normalize_main(["--variant-id", str(variant_id)]) == 0
                    receipt = json.loads(captured.getvalue())
                    assert receipt["replayed"] is replay and receipt["status"] == "ready"
                    assert "Synthetic private" not in captured.getvalue()
                with Session(engine) as db:
                    preview = db.get(InboundMailPreview, variant_id)
                    assert preview.body_text == "Synthetic private text" and preview.reason is None
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
