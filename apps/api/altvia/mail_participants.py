"""Owner-only registration and ticket-bound synthetic/operator attestations."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from altvia import tickets
from altvia.mail_settings import SMTPAccount, mailbox
from altvia.management import lock_identity_writes
from altvia.models import (
    AuditLog,
    ClientContact,
    MailboxSource,
    MailSender,
    Ticket,
    TicketParticipant,
)


def require_owner(db: Session) -> None:
    if not db.scalar(
        text(
            "SELECT current_user = pg_get_userbyid(relowner) FROM pg_class "
            "WHERE oid='outbound_messages'::regclass"
        )
    ):
        raise ValueError("owner_required")


def audit(db: Session, action: str, identifier: UUID) -> None:
    db.add(
        AuditLog(
            actor_id=None,
            action=action,
            resource_id=identifier,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid4().hex,
            details={"actor_kind": "management_command"},
        )
    )
    db.flush()


def register_sender(db: Session, account: SMTPAccount) -> MailSender:
    require_owner(db)
    lock_identity_writes(db)
    source = db.get(MailboxSource, account.source_id)
    if source is None:
        raise ValueError("source_unavailable")
    from altvia.models import Team, TicketQueue

    queue = db.get(TicketQueue, source.queue_id)
    team = db.get(Team, queue.team_id) if queue else None
    if not queue or not team or not queue.active or not team.active:
        raise ValueError("sender_parent_unavailable")
    existing = db.get(MailSender, source.id)
    if existing:
        if (
            existing.from_email != account.from_email
            or existing.namespace_hash != account.namespace_hash
        ):
            raise ValueError("sender_identity_conflict")
        return existing
    sender = MailSender(
        source_id=source.id,
        queue_id=source.queue_id,
        from_email=account.from_email,
        namespace_hash=account.namespace_hash,
    )
    db.add(sender)
    db.flush()
    audit(db, "mail.sender_registered", source.id)
    return sender


def locked_ticket(db: Session, ticket_id: UUID) -> Ticket:
    item = db.get(Ticket, ticket_id)
    if item is None:
        raise ValueError("ticket_unavailable")
    tickets._lock_parents(db, item.client, item.queue)
    item = db.scalar(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .with_for_update(of=Ticket)
        .execution_options(populate_existing=True)
    )
    assert item is not None
    return item


def attest_requester(
    db: Session, ticket_id: UUID, expected_version: int, evidence: str
) -> TicketParticipant:
    if not 1 <= len(evidence) <= 200 or any(
        not (c.isascii() and (c.isalnum() or c in "._:/-")) for c in evidence
    ):
        raise ValueError("invalid_attestation_evidence")
    require_owner(db)
    lock_identity_writes(db)
    item = locked_ticket(db, ticket_id)
    if item.version != expected_version:
        raise ValueError("version_conflict")
    contact = db.scalar(
        select(ClientContact).where(ClientContact.id == item.requester_id).with_for_update()
    )
    if (
        not contact
        or not contact.active
        or contact.client_id != item.client_id
        or not item.client.active
        or not item.queue.active
    ):
        raise ValueError("requester_unavailable")
    from altvia.models import Team

    if not db.scalar(select(Team.active).where(Team.id == item.queue.team_id)):
        raise ValueError("requester_unavailable")
    if db.scalar(
        select(TicketParticipant.id).where(
            TicketParticipant.ticket_id == item.id, TicketParticipant.active
        )
    ):
        raise ValueError("requester_already_attested")
    participant = TicketParticipant(
        ticket_id=item.id,
        contact_id=contact.id,
        email=mailbox(contact.email_normalized),
        evidence=evidence,
        attested_at=datetime.now(UTC),
        active=True,
        version=1,
    )
    db.add(participant)
    db.flush()
    audit(db, "mail.participant_attested", participant.id)
    return participant


def revoke_requester(db: Session, participant_id: UUID, expected_version: int) -> None:
    require_owner(db)
    lock_identity_writes(db)
    participant = db.get(TicketParticipant, participant_id)
    if participant is None:
        raise ValueError("participant_unavailable")
    locked_ticket(db, participant.ticket_id)
    if participant.version != expected_version or not participant.active:
        raise ValueError("version_conflict")
    participant.active = False
    participant.version += 1
    audit(db, "mail.participant_revoked", participant.id)


def main() -> int:
    """Finite owner commands. No API attestation or reconciliation write path."""
    import argparse
    import sys
    from pathlib import Path

    from sqlalchemy.exc import SQLAlchemyError

    from altvia.config import DatabaseSettings
    from altvia.database import make_engine
    from altvia.mail_settings import load_accounts

    parser = argparse.ArgumentParser(description="Owner-only verified public mail records")
    commands = parser.add_subparsers(dest="command", required=True)
    sender = commands.add_parser("register-sender")
    sender.add_argument("--accounts", type=Path, required=True)
    sender.add_argument("--source-id", type=UUID, required=True)
    attest = commands.add_parser("attest-requester")
    attest.add_argument("--ticket-id", type=UUID, required=True)
    attest.add_argument("--version", type=int, required=True)
    attest.add_argument("--evidence", required=True)
    revoke = commands.add_parser("revoke-requester")
    revoke.add_argument("--participant-id", type=UUID, required=True)
    revoke.add_argument("--version", type=int, required=True)
    reconcile_parser = commands.add_parser("reconcile")
    reconcile_parser.add_argument("--delivery-id", type=UUID, required=True)
    reconcile_parser.add_argument("--version", type=int, required=True)
    reconcile_parser.add_argument("--decision", choices=["accepted", "not_accepted"], required=True)
    reconcile_parser.add_argument("--evidence", required=True)
    reconcile_parser.add_argument("--workers-drained", action="store_true")
    reconcile_parser.add_argument("--accepted-at", type=datetime.fromisoformat)
    args = parser.parse_args()
    engine = None
    try:
        engine = make_engine(DatabaseSettings())
        with Session(engine) as db, db.begin():
            if args.command == "register-sender":
                accounts = load_accounts(args.accounts)
                if args.source_id not in accounts:
                    raise ValueError("source_configuration_missing")
                register_sender(db, accounts[args.source_id])
            elif args.command == "attest-requester":
                attest_requester(db, args.ticket_id, args.version, args.evidence)
            elif args.command == "revoke-requester":
                revoke_requester(db, args.participant_id, args.version)
            else:
                from altvia.mail_delivery import reconcile

                reconcile(
                    db,
                    args.delivery_id,
                    args.version,
                    args.decision,
                    args.evidence,
                    workers_drained=args.workers_drained,
                    accepted_at=args.accepted_at,
                )
    except (ValueError, OSError, SQLAlchemyError):
        print("Owner mail command refused; inspect configuration safely.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print("Owner mail command completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
