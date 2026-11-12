"""Finite owner-only synthetic attestation for disposable browser fixtures."""

import os
import sys
from uuid import UUID

from altvia.config import Settings
from altvia.database import make_engine
from altvia.mail_participants import attest_requester
from altvia.models import Ticket
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

settings = Settings()
if (
    os.environ.get("ALTVIA_ALLOW_TEST_DB") != "1"
    or os.environ.get("ALTVIA_PUBLIC_ORIGIN") != "https://127.0.0.1:3443"
    or make_url(settings.database_url.get_secret_value()).database != "altvia_test"
):
    raise SystemExit("Disposable local browser database required")
engine = make_engine(settings)
with Session(engine) as db, db.begin():
    item = db.get(Ticket, UUID(sys.argv[1]))
    if (
        not item
        or not item.subject.startswith("Delivery synthetic ")
        or item.queue_id != UUID(os.environ["ALTVIA_E2E_NOTE_QUEUE_ID"])
    ):
        raise SystemExit("Synthetic ticket required")
    attest_requester(db, item.id, item.version, "browser-synthetic-ticket-only")
engine.dispose()
