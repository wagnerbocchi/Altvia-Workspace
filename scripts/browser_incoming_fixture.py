"""Owner-only synthetic incoming fixtures in the opted-in disposable browser DB."""

import json
import os
import sys
from uuid import UUID, uuid4

from altvia.config import Settings
from altvia.database import make_engine
from altvia.mail_cases_owner import attest_case, revoke_case
from altvia.mail_intake import capture_message, register_source
from altvia.mail_normalize import normalize_variant
from altvia.mail_participants import attest_requester
from altvia.models import ClientContact, MailTriageCase, Ticket, TicketQueue
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
options = json.load(sys.stdin)
queue_id = UUID(os.environ["ALTVIA_E2E_NOTE_QUEUE_ID"])
if options.get("action") == "policy":
    with Session(engine) as db, db.begin():
        queue = db.get(TicketQueue, queue_id)
        assert queue is not None and queue.name == "Notas internas - Validacao"
        queue.allow_reopen = True
        queue.allow_manual_close = True
elif options.get("action") == "attest":
    with Session(engine) as db, db.begin():
        ticket = db.get(Ticket, UUID(options["ticket"]))
        if (
            not ticket
            or ticket.queue_id != queue_id
            or not ticket.subject.startswith("Inbound synthetic")
        ):
            raise SystemExit("Synthetic incoming ticket required")
        attest_requester(db, ticket.id, ticket.version, "browser-synthetic-incoming-only")
elif options.get("action") == "revoke":
    with Session(engine) as db:
        case = db.get(MailTriageCase, UUID(options["case"]))
        if not case or case.queue_id != queue_id:
            raise SystemExit("Synthetic incoming case required")
        version = case.version
    revoke_case(engine, case.id, version)
else:
    key = "browser-incoming-" + uuid4().hex
    identifier = "<" + uuid4().hex + "@example.invalid>"
    subject = options.get("subject", "Incoming synthetic request")
    body = options.get(
        "body", "Synthetic received text <script>window.injected=true</script>\nSecond line"
    )
    with Session(engine) as db, db.begin():
        contact = db.get(ClientContact, UUID(os.environ["ALTVIA_E2E_TICKET_REQUESTER_ID"]))
        assert contact is not None
        contact_id, version, email = contact.id, contact.version, contact.email_normalized
        register_source(db, key, queue_id)
    references = options.get("references")
    raw = (
        f"From: {email}\r\n"
        + (f"Message-ID: {identifier}\r\n" if not options.get("missing_id") else "")
        + (f"References: {references}\r\n" if references else "")
        + f"Subject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
        + body
    ).encode()
    with Session(engine) as db, db.begin():
        receipt = capture_message(db, key, 1, 1, raw)
    normalize_variant(engine, receipt.variant_id)
    published = attest_case(
        engine, receipt.variant_id, contact_id, version, "browser-synthetic-variant-only"
    )
    with Session(engine) as db:
        case = db.get(MailTriageCase, published.case_id)
        assert case is not None
        subject, body = case.subject, case.body_text
    print(
        json.dumps(
            {
                "case_id": str(published.case_id),
                "message_id": identifier,
                "subject": subject,
                "body": body,
            }
        )
    )
engine.dispose()
