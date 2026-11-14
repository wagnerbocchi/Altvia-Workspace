"""Finite owner-only SLA policy for the existing disposable TLS SMTP fixture."""

import os
import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

from altvia import management, queue_client_configuration, sla_configuration
from altvia.config import Settings
from altvia.database import make_engine
from altvia.models import Client, ClientAccessGrant, RoleBinding, SlaPolicy, TicketQueue
from altvia.sla_schemas import CalendarCreate, PolicyCreate, PolicyPatch
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

settings = Settings()
if (
    os.environ.get("ALTVIA_ALLOW_TEST_DB") != "1"
    or settings.public_origin != "https://127.0.0.1:3443"
    or make_url(settings.database_url.get_secret_value()).database != "altvia_test"
):
    raise SystemExit("Disposable local browser database required")
queue_id = UUID(os.environ["ALTVIA_E2E_NOTE_QUEUE_ID"])
client_id = UUID(os.environ["ALTVIA_E2E_TICKET_CLIENT_ID"])
engine = make_engine(settings)
try:
    with Session(engine) as db, db.begin():
        management.lock_identity_writes(db)
        queue = db.get(TicketQueue, queue_id)
        client = db.get(Client, client_id)
        if queue is None or queue.name != "Notas internas - Validacao" or client is None:
            raise SystemExit("Existing synthetic SMTP namespace required")
        if (
            db.scalar(
                select(SlaPolicy.id).where(
                    SlaPolicy.queue_id == queue_id,
                    SlaPolicy.client_id == client_id,
                    SlaPolicy.category_id.is_(None),
                    SlaPolicy.priority == "medium",
                )
            )
            is not None
        ):
            raise SystemExit("Synthetic SLA selector already configured; no mutation performed")
        # This new synthetic bootstrap identity has no previous sessions. Existing
        # browser identities and their grants/sessions remain unchanged. The real
        # configuration service still checks all three authority conjunctions.
        actor = management.create_user(
            db,
            "browser-sla-bootstrap-" + uuid4().hex + "@example.invalid",
            "Synthetic SLA bootstrap",
            secrets.token_urlsafe(32),
        )
        management.set_platform_admin(db, actor.email_normalized, True)
        db.add_all(
            [
                RoleBinding(
                    user_id=actor.id,
                    role_name="operations_manager",
                    scope_kind="client",
                    client_id=client_id,
                ),
                RoleBinding(
                    user_id=actor.id,
                    role_name="operations_manager",
                    scope_kind="queue",
                    queue_id=queue_id,
                ),
                ClientAccessGrant(
                    user_id=actor.id, client_id=client_id, created_at=datetime.now(UTC)
                ),
            ]
        )
        db.flush()
        access = queue_client_configuration.access(db, actor.id, client_id, queue_id, write=True)
        calendar = sla_configuration.create_calendar(
            db,
            actor.id,
            access,
            CalendarCreate(
                client_id=client_id,
                name="Synthetic SMTP browser calendar",
                active=True,
                timezone="UTC",
                windows=[
                    {"weekday": day, "start_minute": 0, "end_minute": 1440} for day in range(7)
                ],
                holidays=[],
            ),
            uuid4().hex,
        )
        policy = sla_configuration.create_policy(
            db,
            actor.id,
            access,
            PolicyCreate(
                client_id=client_id,
                name="Synthetic SMTP browser SLA",
                priority="medium",
                calendar_id=calendar.id,
                calendar_version=calendar.version,
                first_response_minutes=60,
                resolution_minutes=240,
                approach_minutes=5,
                pause_states=["pending_customer"],
            ),
            uuid4().hex,
        )
        sla_configuration.patch_policy(
            db, actor.id, access, policy, PolicyPatch(enabled=True), uuid4().hex
        )
finally:
    engine.dispose()
