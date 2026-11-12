"""Frozen public MIME and SQL-owned delivery leases. No network I/O here."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from altvia import tickets
from altvia.mail_delivery_schemas import DeliveryChoices, ParticipantChoice, SenderChoice
from altvia.mail_settings import SMTPAccount
from altvia.management import lock_identity_writes
from altvia.models import (
    Client,
    ClientContact,
    MailSender,
    MailTriageCase,
    OutboundMessage,
    RoleBinding,
    Team,
    Ticket,
    TicketIncomingMessage,
    TicketMailThread,
    TicketMessage,
    TicketParticipant,
    TicketQueue,
    User,
)

SAFE_ERRORS = {
    "temporary",
    "permanent",
    "transport",
    "eligibility_revoked",
    "lease_expired",
    "data_unknown",
    "retry_exhausted",
}
LEASE_SECONDS = 120
MAX_WIRE_BYTES = 262144
MAX_MESSAGE_ID_CHARS = 320


def choices(db: Session, item: Ticket, access: tickets.Access, actor_id: UUID) -> DeliveryChoices:
    sender = db.scalar(select(MailSender).where(MailSender.queue_id == item.queue_id))
    participant = (
        db.scalar(
            select(TicketParticipant).where(
                TicketParticipant.ticket_id == item.id,
                TicketParticipant.contact_id == item.requester_id,
                TicketParticipant.active,
                TicketParticipant.email == item.requester.email_normalized,
            )
        )
        if item.requester.active
        else None
    )
    active = access.active and item.status != "closed"
    return DeliveryChoices(
        sender=SenderChoice(source_id=sender.source_id, from_email=sender.from_email)
        if sender and active
        else None,
        participant=ParticipantChoice(
            participant_id=participant.id,
            email=participant.email,
            display_name=item.requester.display_name,
        )
        if participant and active
        else None,
        can_send=bool(
            sender and participant and active and tickets.can_update(item, access, actor_id)
        ),
    )


def build_wire(
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    message_id: str,
    thread_token: str,
    now: datetime,
    references: list[str],
) -> bytes:
    from altvia.mail_settings import mailbox

    sender, recipient = mailbox(sender), mailbox(recipient)
    if (
        len(subject) > 300
        or len(body) > 10000
        or any(c in subject for c in "\r\n")
        or len(references) > 16
        or any(len(r) > MAX_MESSAGE_ID_CHARS or "\r" in r or "\n" in r for r in references)
    ):
        raise ValueError("invalid_public_message")
    msg = EmailMessage(policy=SMTP)
    msg["From"], msg["To"], msg["Subject"] = sender, recipient, subject
    msg["Message-ID"] = message_id
    msg["Date"] = format_datetime(now)
    msg["X-Altvia-Thread"] = thread_token
    if references:
        msg["References"] = " ".join(references)
        msg["In-Reply-To"] = references[-1]
    msg.set_content(body, subtype="plain", charset="utf-8", cte="quoted-printable")
    wire = msg.as_bytes()
    if len(wire) > MAX_WIRE_BYTES:
        raise ValueError("message_too_large")
    return wire


def reference_ids(db: Session, item: Ticket, participant: TicketParticipant) -> list[str]:
    """Current recipient context only; preserve existing outbound ordering exactly."""
    outgoing = list(
        db.execute(
            select(OutboundMessage.created_at, OutboundMessage.id, OutboundMessage.smtp_message_id)
            .join(TicketParticipant, TicketParticipant.id == OutboundMessage.participant_id)
            .where(
                OutboundMessage.ticket_id == item.id,
                OutboundMessage.state == "accepted",
                TicketParticipant.contact_id == participant.contact_id,
                OutboundMessage.envelope_to == participant.email,
            )
            .order_by(OutboundMessage.created_at.desc(), OutboundMessage.id.desc())
            .limit(16)
        )
    )
    query = (
        select(
            TicketIncomingMessage.recorded_at, TicketIncomingMessage.id, MailTriageCase.message_id
        )
        .join(MailTriageCase, MailTriageCase.id == TicketIncomingMessage.case_id)
        .where(
            TicketIncomingMessage.ticket_id == item.id,
            MailTriageCase.state == "promoted",
            MailTriageCase.ticket_id == item.id,
            MailTriageCase.queue_id == item.queue_id,
            MailTriageCase.client_id == item.client_id,
            MailTriageCase.contact_id == participant.contact_id,
            MailTriageCase.email_snapshot == participant.email,
            MailTriageCase.message_id.is_not(None),
        )
    )
    incoming = list(
        db.execute(
            query.order_by(
                TicketIncomingMessage.recorded_at.desc(), TicketIncomingMessage.id.desc()
            ).limit(16)
        )
    )
    # created_at/id descending, then reverse, remains exact for outbound-only.
    combined = sorted([tuple(row) for row in outgoing] + [tuple(row) for row in incoming])
    selected = combined[-16:]
    if not outgoing and incoming:
        root = db.execute(
            query.order_by(TicketIncomingMessage.recorded_at, TicketIncomingMessage.id).limit(1)
        ).one()
        if tuple(root) not in selected:
            selected = [tuple(root), *selected[-15:]]
    return [row[2] for row in selected]


def freeze(
    db: Session,
    item: Ticket,
    message: TicketMessage,
    sender: MailSender,
    participant: TicketParticipant,
    actor_id: UUID,
) -> OutboundMessage:
    thread = db.get(TicketMailThread, item.id)
    if thread is None:
        thread = TicketMailThread(ticket_id=item.id, token=secrets.token_hex(32))
        db.add(thread)
        db.flush()
    references = reference_ids(db, item, participant)
    # The API caller already holds the identity/parent/ticket write locks.
    now = _clock(db)
    smtp_id = f"<{uuid4().hex}@{sender.from_email.rsplit('@', 1)[1]}>"
    row = OutboundMessage(
        ticket_id=item.id,
        message_id=message.id,
        participant_id=participant.id,
        source_id=sender.source_id,
        actor_id=actor_id,
        envelope_from=sender.from_email,
        envelope_to=participant.email,
        namespace_hash=sender.namespace_hash,
        wire=build_wire(
            sender.from_email,
            participant.email,
            item.subject,
            message.body_text,
            smtp_id,
            thread.token,
            now,
            references,
        ),
        smtp_message_id=smtp_id,
        state="queued",
        attempts=0,
        version=1,
        next_attempt_at=now,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def eligible(db: Session, row: OutboundMessage) -> bool:
    # Reuse ticket visibility owner with explicit columns: never load joined user,
    # private note, password/session hash or raw/MIME-preview entities.
    query = (
        tickets.visible(row.actor_id)
        .with_only_columns(Ticket.id)
        .join(Client, Client.id == Ticket.client_id)
        .join(User, User.id == row.actor_id)
        .where(
            Ticket.id == row.ticket_id,
            User.active,
            Client.active,
            TicketQueue.active,
            Team.active,
            Ticket.status != "closed",
            (
                (RoleBinding.role_name == "operations_manager")
                | ((RoleBinding.role_name == "agent") & (Ticket.assignee_id == row.actor_id))
            ),
        )
    )
    if db.scalar(query) is None:
        return False
    valid = (
        select(TicketParticipant.id)
        .join(Ticket, Ticket.id == TicketParticipant.ticket_id)
        .join(ClientContact, ClientContact.id == Ticket.requester_id)
        .join(MailSender, MailSender.source_id == row.source_id)
        .where(
            Ticket.id == row.ticket_id,
            TicketParticipant.id == row.participant_id,
            TicketParticipant.active,
            TicketParticipant.contact_id == Ticket.requester_id,
            ClientContact.active,
            ClientContact.client_id == Ticket.client_id,
            ClientContact.email_normalized == row.envelope_to,
            TicketParticipant.email == row.envelope_to,
            MailSender.queue_id == Ticket.queue_id,
            MailSender.from_email == row.envelope_from,
            MailSender.namespace_hash == row.namespace_hash,
        )
    )
    return db.scalar(valid) is not None


@dataclass(frozen=True)
class Claim:
    delivery_id: UUID
    token: UUID
    source_id: UUID
    lease_until: datetime


@dataclass(frozen=True)
class FrozenDelivery:
    delivery_id: UUID
    envelope_from: str
    envelope_to: str
    wire: bytes
    smtp_message_id: str


def attempt_event(
    db: Session,
    row: OutboundMessage,
    now: datetime,
    *,
    actor_kind: Literal["mail_worker", "management_command"] = "mail_worker",
) -> None:
    from altvia.models import AuditLog, OutboxEvent

    payload = {
        "actor_id": None,
        "actor_kind": actor_kind,
        "delivery_id": str(row.id),
        "state": row.state,
        "error_code": row.last_error_code,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
    }
    correlation = uuid4().hex
    db.add(
        OutboxEvent(
            schema_version=1,
            aggregate_type="mail_delivery",
            aggregate_id=row.id,
            aggregate_version=row.version,
            event_type="mail.delivery_changed",
            payload=payload,
            occurred_at=now,
            correlation_id=correlation,
            next_attempt_at=now,
        )
    )
    db.add(
        AuditLog(
            actor_id=None,
            action="mail.delivery_changed",
            resource_id=row.id,
            occurred_at=now,
            correlation_id=correlation,
            details=payload,
        )
    )
    db.flush()


def _clock(db: Session, requested: datetime | None = None) -> datetime:
    current = db.scalar(select(func.clock_timestamp()))
    assert isinstance(current, datetime)
    return max(current, requested) if requested else current


def _live(
    db: Session, identifier: UUID, token: UUID, now: datetime | None
) -> OutboundMessage | None:
    row = db.scalar(
        select(OutboundMessage)
        .where(
            OutboundMessage.id == identifier,
            OutboundMessage.lease_token == token,
            OutboundMessage.state.in_({"preparing", "transmitting"}),
        )
        .with_for_update()
    )
    # Evaluate real wall clock AFTER acquiring a possibly blocking row lock.
    if row is None or row.lease_until is None or row.lease_until <= _clock(db, now):
        return None
    return row


def claim(
    engine: Engine,
    accounts: dict[UUID, SMTPAccount],
    now: datetime | None = None,
    *,
    identifier: UUID | None = None,
) -> Claim | None:
    if not accounts:
        return None
    with Session(engine) as db, db.begin():
        lock_identity_writes(db)
        requested = now
        now = _clock(db, requested)
        for row in db.scalars(
            select(OutboundMessage)
            .where(
                OutboundMessage.state == "queued",
                OutboundMessage.source_id.in_(accounts),
                *([OutboundMessage.id == identifier] if identifier is not None else []),
                OutboundMessage.next_attempt_at <= now,
                OutboundMessage.attempts < 8,
            )
            .order_by(OutboundMessage.next_attempt_at, OutboundMessage.id)
            .limit(100)
            .with_for_update(skip_locked=True)
        ):
            account = accounts.get(row.source_id)
            if account is None or account.namespace_hash != row.namespace_hash:
                continue
            now = _clock(db, requested)
            if not eligible(db, row):
                row.state, row.last_error_code = "failed", "eligibility_revoked"
                row.version += 1
                attempt_event(db, row, now)
                continue
            row.state, row.lease_token, row.lease_until = (
                "preparing",
                uuid4(),
                now + timedelta(seconds=LEASE_SECONDS),
            )
            row.attempts += 1
            row.version += 1
            attempt_event(db, row, now)
            return Claim(row.id, row.lease_token, row.source_id, row.lease_until)
    return None


def frozen_delivery(
    engine: Engine, identifier: UUID, token: UUID, now: datetime | None = None
) -> FrozenDelivery | None:
    with Session(engine) as db, db.begin():
        row = _live(db, identifier, token, now)
        if row is None or row.state != "preparing":
            return None
        return FrozenDelivery(
            row.id, row.envelope_from, row.envelope_to, row.wire, row.smtp_message_id
        )


def pre_data(engine: Engine, identifier: UUID, token: UUID, now: datetime | None = None) -> bool:
    with Session(engine) as db, db.begin():
        lock_identity_writes(db)
        row = _live(db, identifier, token, now)
        if row is None or row.state != "preparing":
            return False
        now = _clock(db, now)
        row.version += 1
        if not eligible(db, row):
            row.state, row.last_error_code = "failed", "eligibility_revoked"
            row.lease_token = row.lease_until = None
            attempt_event(db, row, now)
            return False
        row.state = "transmitting"
        attempt_event(db, row, now)
        return True


def finalize(
    engine: Engine,
    identifier: UUID,
    token: UUID,
    outcome: Literal["accepted", "temporary", "permanent", "transport", "data_unknown"],
    now: datetime | None = None,
) -> bool:
    if outcome not in {"accepted", "temporary", "permanent", "transport", "data_unknown"}:
        raise ValueError("invalid_outcome")
    with Session(engine) as db, db.begin():
        row = _live(db, identifier, token, now)
        if (
            row is None
            or (outcome in {"accepted", "data_unknown"} and row.state != "transmitting")
            or (outcome == "transport" and row.state != "preparing")
        ):
            return False
        now = _clock(db, now)
        row.version += 1
        row.last_error_code = None if outcome == "accepted" else outcome
        if outcome == "accepted":
            row.state, row.accepted_at = "accepted", now
        elif outcome == "data_unknown":
            row.state = "uncertain"
        elif outcome == "permanent":
            row.state = "failed"
        elif row.attempts >= 8:
            row.state, row.last_error_code = "failed", "retry_exhausted"
        else:
            row.state = "queued"
            row.next_attempt_at = now + timedelta(seconds=min(3600, 30 * 2 ** (row.attempts - 1)))
        row.lease_token = row.lease_until = None
        attempt_event(db, row, now)
        return True


def recover(engine: Engine, now: datetime | None = None) -> list[UUID]:
    result = []
    with Session(engine) as db, db.begin():
        due = _clock(db, now)
        for row in db.scalars(
            select(OutboundMessage)
            .where(
                OutboundMessage.state.in_({"preparing", "transmitting"}),
                OutboundMessage.lease_until <= due,
            )
            .limit(100)
            .with_for_update(skip_locked=True)
        ):
            # Recheck the current lease only after owning its row lock.
            current = _clock(db, now)
            if row.lease_until is None or row.lease_until > current:
                continue
            row.state = (
                "uncertain"
                if row.state == "transmitting"
                else ("failed" if row.attempts >= 8 else "queued")
            )
            row.last_error_code = (
                "data_unknown"
                if row.state == "uncertain"
                else ("retry_exhausted" if row.state == "failed" else "lease_expired")
            )
            row.lease_token = row.lease_until = None
            row.next_attempt_at = current
            row.version += 1
            attempt_event(db, row, current)
            result.append(row.id)
    return result


def reconcile(
    db: Session,
    identifier: UUID,
    expected_version: int,
    decision: Literal["accepted", "not_accepted"],
    evidence: str,
    *,
    workers_drained: bool,
    accepted_at: datetime | None = None,
) -> None:
    from altvia.mail_participants import require_owner

    require_owner(db)
    if (
        not workers_drained
        or not 1 <= len(evidence) <= 200
        or decision not in {"accepted", "not_accepted"}
        or any(not (c.isascii() and (c.isalnum() or c in "._:/-")) for c in evidence)
    ):
        raise ValueError("reconciliation_requires_drained_evidence")
    lock_identity_writes(db)
    row = db.scalar(
        select(OutboundMessage).where(OutboundMessage.id == identifier).with_for_update()
    )
    if row is None or row.state != "uncertain" or row.version != expected_version:
        raise ValueError("reconciliation_conflict")
    now = _clock(db)
    if decision == "accepted" and (
        accepted_at is None
        or accepted_at.tzinfo is None
        or not row.created_at <= accepted_at <= now
    ):
        raise ValueError("invalid_acceptance_evidence_time")
    if decision == "not_accepted" and accepted_at is not None:
        raise ValueError("invalid_acceptance_evidence_time")
    row.state = (
        "accepted" if decision == "accepted" else ("queued" if row.attempts < 8 else "failed")
    )
    row.accepted_at = accepted_at if decision == "accepted" else None
    row.last_error_code = "retry_exhausted" if row.state == "failed" else None
    row.next_attempt_at = now
    row.version += 1
    # External evidence is retained only in owner audit, never shared events.
    from altvia.models import AuditLog

    db.add(
        AuditLog(
            actor_id=None,
            action="mail.delivery_reconciled",
            resource_id=row.id,
            occurred_at=now,
            correlation_id=uuid4().hex,
            details={"evidence": evidence, "decision": decision},
        )
    )
    attempt_event(db, row, now, actor_kind="management_command")


def validate_delivery_event(event: object) -> None:
    from altvia.models import OutboxEvent

    assert isinstance(event, OutboxEvent)
    from pydantic import BaseModel, ConfigDict

    class Payload(BaseModel):
        model_config = ConfigDict(extra="forbid")
        actor_id: None
        actor_kind: Literal["mail_worker", "management_command"]
        delivery_id: UUID
        state: Literal["queued", "preparing", "transmitting", "accepted", "failed", "uncertain"]
        error_code: (
            Literal[
                "temporary",
                "permanent",
                "transport",
                "eligibility_revoked",
                "lease_expired",
                "data_unknown",
                "retry_exhausted",
            ]
            | None
        )
        accepted_at: datetime | None

    payload = Payload.model_validate(event.payload)
    if (
        event.schema_version != 1
        or event.aggregate_type != "mail_delivery"
        or payload.delivery_id != event.aggregate_id
        or ((payload.state == "accepted") != (payload.accepted_at is not None))
    ):
        raise ValueError("invalid_delivery_event")
