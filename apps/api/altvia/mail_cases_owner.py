"""Explicit owner attestation of ONE immutable variant into a scoped case."""

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.mail_cases import validate_case_event
from altvia.mail_intake import MAX_VERSION, SafeMailParser
from altvia.mail_routing import RoutingError, parse_routing
from altvia.management import lock_identity_writes
from altvia.models import (
    AuditLog,
    Client,
    ClientContact,
    InboundMailEnvelope,
    InboundMailPreview,
    InboundMailVariant,
    MailboxSource,
    MailCaseOrigin,
    MailTriageCase,
    OutboundMessage,
    OutboxEvent,
    Team,
    Ticket,
    TicketParticipant,
    TicketQueue,
)


class CaseError(ValueError):
    """Fixed safe owner refusal."""


@dataclass(frozen=True)
class CaseReceipt:
    case_id: UUID
    state: str
    disposition: str
    replayed: bool


def require_owner(db: Session) -> None:
    if not db.scalar(
        text(
            "SELECT current_user=pg_get_userbyid(relowner) FROM pg_class "
            "WHERE oid='mail_triage_cases'::regclass"
        )
    ):
        raise CaseError("owner_required")


def _event(db: Session, case: MailTriageCase, event_type: str) -> None:
    instant, correlation = datetime.now(UTC), uuid4().hex
    payload = {
        "actor_id": None,
        "actor_kind": "management_command",
        "case_id": str(case.id),
        "source_id": str(case.source_id),
        "state": case.state,
    }
    event = OutboxEvent(
        schema_version=2 if event_type == "mail.case_aliased" and case.state == "promoted" else 1,
        aggregate_type="mail_case",
        aggregate_id=case.id,
        aggregate_version=case.version,
        event_type=event_type,
        payload=payload,
        occurred_at=instant,
        correlation_id=correlation,
        next_attempt_at=instant,
    )
    validate_case_event(event)
    db.add(event)
    db.add(
        AuditLog(
            actor_id=None,
            action=event_type,
            resource_id=case.id,
            occurred_at=instant,
            correlation_id=correlation,
            details=payload,
        )
    )
    db.flush()


def _parents(db: Session, client_id: UUID, queue_id: UUID, *, active: bool = True) -> None:
    client = db.scalar(select(Client).where(Client.id == client_id).with_for_update())
    team_id = db.scalar(select(TicketQueue.team_id).where(TicketQueue.id == queue_id))
    team = db.scalar(select(Team).where(Team.id == team_id).with_for_update())
    queue = db.scalar(select(TicketQueue).where(TicketQueue.id == queue_id).with_for_update())
    if (
        not client
        or not team
        or not queue
        or active
        and (not client.active or not team.active or not queue.active)
    ):
        raise CaseError("case_parent_unavailable")


def _advance(source: MailboxSource, case: MailTriageCase | None = None) -> None:
    if source.version >= MAX_VERSION or case is not None and case.version >= MAX_VERSION:
        raise CaseError("case_version_exhausted")
    source.version += 1
    if case is not None:
        case.version += 1


def attest_case(
    engine: Engine, variant_id: UUID, contact_id: UUID, contact_version: int, evidence: str
) -> CaseReceipt:
    if (
        type(contact_version) is not int
        or not 1 <= contact_version <= MAX_VERSION
        or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,200}", evidence)
    ):
        raise CaseError("invalid_case_intent")
    with Session(engine) as db:
        require_owner(db)
        variant = db.get(InboundMailVariant, variant_id)
        if variant is None:
            raise CaseError("variant_unavailable")
        raw = variant.raw_message
    try:
        routing = parse_routing(raw)
    except RoutingError as error:
        raise CaseError("invalid_routing") from error
    with Session(engine) as db, db.begin():
        require_owner(db)
        lock_identity_writes(db)
        variant = db.get(InboundMailVariant, variant_id)
        contact = db.get(ClientContact, contact_id)
        envelope = db.get(InboundMailEnvelope, variant.envelope_id) if variant else None
        source = db.get(MailboxSource, envelope.source_id) if envelope else None
        if not variant or not contact or not envelope or not source:
            raise CaseError("case_input_unavailable")
        _parents(db, contact.client_id, source.queue_id)
        source = db.scalar(
            select(MailboxSource)
            .where(MailboxSource.id == source.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert source is not None
        envelope = db.get(InboundMailEnvelope, envelope.id, populate_existing=True)
        assert envelope is not None
        existing = db.get(MailCaseOrigin, variant_id)
        query = select(MailTriageCase).where(
            MailTriageCase.source_id == source.id,
            MailTriageCase.client_id == contact.client_id,
            MailTriageCase.contact_id == contact.id,
            MailTriageCase.email_snapshot == routing.from_email,
            MailTriageCase.message_id == routing.message_id,
        )
        if existing:
            query = select(MailTriageCase).where(MailTriageCase.id == existing.case_id)
        case = (
            db.scalar(
                query.order_by(MailTriageCase.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if routing.message_id or existing
            else None
        )
        contact = db.scalar(
            select(ClientContact)
            .where(ClientContact.id == contact_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            not contact
            or not contact.active
            or contact.version != contact_version
            or contact.email_normalized != routing.from_email
        ):
            raise CaseError("reviewed_contact_unavailable")
        if existing:
            if (
                existing.contact_id != contact_id
                or existing.contact_version != contact_version
                or existing.evidence != evidence
                or existing.email_snapshot != routing.from_email
            ):
                raise CaseError("variant_intent_conflict")
            assert case is not None
            return CaseReceipt(case.id, case.state, existing.disposition, True)
        if envelope.state != "quarantine":
            raise CaseError("receipt_collision")
        preview = db.get(InboundMailPreview, (variant_id, 2))
        if (
            not preview
            or preview.status != "ready"
            or preview.subject is None
            or preview.body_text is None
        ):
            raise CaseError("parser2_required")
        # Outgoing IDs are reserved for every persisted delivery state, scoped
        # before lookup. Intake and outgoing sources may differ in this queue.
        reserved = (
            db.scalar(
                select(OutboundMessage.id)
                .join(Ticket, Ticket.id == OutboundMessage.ticket_id)
                .join(TicketParticipant, TicketParticipant.id == OutboundMessage.participant_id)
                .where(
                    Ticket.queue_id == source.queue_id,
                    Ticket.client_id == contact.client_id,
                    TicketParticipant.contact_id == contact.id,
                    OutboundMessage.envelope_to == contact.email_normalized,
                    OutboundMessage.smtp_message_id == routing.message_id,
                )
            )
            if routing.message_id
            else None
        )
        if reserved:
            raise CaseError("reserved_message_id")
        disposition = "primary"
        if case:
            primary = db.get(InboundMailVariant, case.primary_variant_id)
            assert primary is not None
            equivalent = primary.raw_sha256 == variant.raw_sha256 and primary.raw_message == raw
            disposition = "alias" if equivalent else "collision"
            if equivalent and case.state not in {"ready", "promoted"}:
                raise CaseError("case_invalidated")
            _advance(source, case)
            if not equivalent:
                case.state = "collision"
        else:
            _advance(source)
            case = MailTriageCase(
                source_id=source.id,
                queue_id=source.queue_id,
                client_id=contact.client_id,
                contact_id=contact.id,
                primary_variant_id=variant_id,
                email_snapshot=contact.email_normalized,
                contact_name=contact.display_name,
                subject=preview.subject,
                body_text=preview.body_text,
                routing_version=1,
                message_id=routing.message_id,
                in_reply_to=routing.in_reply_to,
                references_ids=list(routing.references),
                thread_token=routing.thread_token,
                received_at=envelope.created_at,
                state="ready",
                version=1,
            )
            db.add(case)
        db.flush()
        db.add(
            MailCaseOrigin(
                variant_id=variant_id,
                case_id=case.id,
                source_id=source.id,
                envelope_id=envelope.id,
                raw_sha256=variant.raw_sha256,
                client_id=contact.client_id,
                contact_id=contact.id,
                email_snapshot=contact.email_normalized,
                contact_version=contact_version,
                evidence=evidence,
                routing_version=1,
                parser_version=2,
                disposition=disposition,
            )
        )
        _event(
            db,
            case,
            {
                "primary": "mail.case_published",
                "alias": "mail.case_aliased",
                "collision": "mail.case_collided",
            }[disposition],
        )
        return CaseReceipt(case.id, case.state, disposition, False)


def revoke_case(engine: Engine, case_id: UUID, expected_version: int) -> None:
    with Session(engine) as db, db.begin():
        require_owner(db)
        lock_identity_writes(db)
        case = db.get(MailTriageCase, case_id)
        if case is None:
            raise CaseError("case_unavailable")
        _parents(db, case.client_id, case.queue_id, active=False)
        source = db.scalar(
            select(MailboxSource).where(MailboxSource.id == case.source_id).with_for_update()
        )
        case = db.scalar(
            select(MailTriageCase)
            .where(MailTriageCase.id == case_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert case is not None and source is not None
        db.execute(
            select(ClientContact.id).where(ClientContact.id == case.contact_id).with_for_update()
        ).one()
        if case.version != expected_version or case.state not in {"ready", "promoted"}:
            raise CaseError("case_version_conflict")
        _advance(source, case)
        case.state = "revoked"
        _event(db, case, "mail.case_revoked")


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("ALTVIA_ALLOW_MAIL_CASES") != "1":
        print("Explicit ALTVIA_ALLOW_MAIL_CASES=1 is required.", file=sys.stderr)
        return 1
    parser = SafeMailParser(description="Owner classified mail publication", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    attest = commands.add_parser("attest", allow_abbrev=False)
    attest.add_argument("--variant-id", required=True, type=UUID)
    attest.add_argument("--contact-id", required=True, type=UUID)
    attest.add_argument("--contact-version", required=True, type=int)
    attest.add_argument("--evidence", required=True)
    revoke = commands.add_parser("revoke", allow_abbrev=False)
    revoke.add_argument("--case-id", required=True, type=UUID)
    revoke.add_argument("--version", required=True, type=int)
    inspect = commands.add_parser("inspect", allow_abbrev=False)
    inspect.add_argument("--case-id", required=True, type=UUID)
    args = parser.parse_args(argv)
    engine = None
    try:
        engine = make_engine(DatabaseSettings())
        if args.command == "attest":
            output = asdict(
                attest_case(
                    engine, args.variant_id, args.contact_id, args.contact_version, args.evidence
                )
            )
        elif args.command == "revoke":
            revoke_case(engine, args.case_id, args.version)
            output = {"case_id": str(args.case_id), "state": "revoked"}
        else:
            with Session(engine) as db:
                require_owner(db)
                case = db.get(MailTriageCase, args.case_id)
                if case is None:
                    raise CaseError("case_unavailable")
                output = {"case_id": str(case.id), "version": case.version, "state": case.state}
    except (ValueError, SQLAlchemyError, OSError, OverflowError):
        print("Mail case command refused; no classification acknowledged.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(output, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
