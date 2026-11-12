"""Protected staff promotion and context-first incoming conversation ownership."""

import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from altvia import identity, mail_cases, tickets
from altvia.admin_http import _expected_version, _operation, _remember
from altvia.mail_case_schemas import (
    IncomingMessageOutput,
    PromotionAppend,
    PromotionCreate,
    PromotionReceipt,
)
from altvia.models import (
    ClientContact,
    MailTriageCase,
    OutboundMessage,
    Ticket,
    TicketIncomingMessage,
    TicketMailThread,
    TicketParticipant,
    User,
)
from altvia.ticket_schemas import TicketCreate, TicketTransition

Case = Mapping[str, Any]


def scoped_case(db: Session, actor_id: UUID, case_id: UUID, *, lock: bool = False) -> Case:
    query = (
        mail_cases.visible(actor_id, detail=True)
        .add_columns(
            *(getattr(MailTriageCase, name) for name in sorted(mail_cases.ROUTING_COLUMNS))
        )
        .where(MailTriageCase.id == case_id)
    )
    if lock:
        query = query.with_for_update(of=MailTriageCase)
    row = db.execute(query).mappings().one_or_none()
    if row is None:
        raise identity.IdentityError(404, "not_found")
    return dict(row)


@dataclass(frozen=True)
class Candidate:
    ticket_id: UUID | None
    case_ids: tuple[UUID, ...]


def resolve_candidate(db: Session, case: Case, actor_id: UUID) -> Candidate:
    """Resolve every own contextual anchor before any eligibility/action filter.

    actor_id is deliberately not an existence filter. The selected ticket is
    separately scoped before any identity is exposed or write authorized.
    """
    identifiers = set(case["references_ids"])
    if case["in_reply_to"]:
        identifiers.add(case["in_reply_to"])
    incoming = (
        list(
            db.execute(
                select(
                    MailTriageCase.id,
                    MailTriageCase.ticket_id,
                    MailTriageCase.state,
                ).where(
                    MailTriageCase.queue_id == case["queue_id"],
                    MailTriageCase.client_id == case["client_id"],
                    MailTriageCase.contact_id == case["contact_id"],
                    MailTriageCase.email_snapshot == case["email_snapshot"],
                    MailTriageCase.message_id.in_(identifiers),
                    MailTriageCase.ticket_id.is_not(None),
                )
            )
        )
        if identifiers
        else []
    )
    outbound = (
        list(
            db.scalars(
                select(OutboundMessage.ticket_id)
                .join(Ticket, Ticket.id == OutboundMessage.ticket_id)
                .join(TicketParticipant, TicketParticipant.id == OutboundMessage.participant_id)
                .where(
                    Ticket.queue_id == case["queue_id"],
                    Ticket.client_id == case["client_id"],
                    TicketParticipant.contact_id == case["contact_id"],
                    OutboundMessage.envelope_to == case["email_snapshot"],
                    OutboundMessage.state == "accepted",
                    OutboundMessage.smtp_message_id.in_(identifiers),
                )
            )
        )
        if identifiers
        else []
    )
    targets = {row.ticket_id for row in incoming} | set(outbound)
    if len(targets) > 1 or any(row.state != "promoted" for row in incoming):
        raise identity.IdentityError(409, "incoming_thread_conflict")
    return Candidate(next(iter(targets), None), tuple(sorted(row.id for row in incoming)))


def _contact(db: Session, case: Case, *, lock: bool = False) -> bool:
    query = select(ClientContact.id).where(
        ClientContact.id == case["contact_id"],
        ClientContact.client_id == case["client_id"],
        ClientContact.active,
        ClientContact.email_normalized == case["email_snapshot"],
    )
    if lock:
        query = query.with_for_update()
    return db.scalar(query) is not None


def _append_eligible(db: Session, case: Case, item: Ticket) -> bool:
    if (item.client_id, item.queue_id, item.requester_id) != (
        case["client_id"],
        case["queue_id"],
        case["contact_id"],
    ):
        return False
    participant = db.scalar(
        select(TicketParticipant.id).where(
            TicketParticipant.ticket_id == item.id,
            TicketParticipant.contact_id == case["contact_id"],
            TicketParticipant.email == case["email_snapshot"],
            TicketParticipant.active,
        )
    )
    if participant is None:
        return False
    if case["thread_token"]:
        token = db.scalar(
            select(TicketMailThread.token).where(TicketMailThread.ticket_id == item.id)
        )
        if token is None or not hmac.compare_digest(case["thread_token"], token):
            return False
    return True


def capabilities(db: Session, actor_id: UUID, case: Case) -> dict[str, Any]:
    result: dict[str, Any] = {
        "can_create": False,
        "can_append": False,
        "candidate_ticket_id": None,
        "candidate_ticket_number": None,
        "candidate_ticket_version": None,
        "candidate_ticket_status": None,
        "candidate_can_reopen": False,
    }
    if case["state"] != "ready":
        return result
    try:
        candidate = resolve_candidate(db, case, actor_id)
        access = tickets.creation_access(db, actor_id, case["client_id"], case["queue_id"])
        if not access.active or not _contact(db, case):
            return result
        if candidate.ticket_id is None:
            result["can_create"] = True
        else:
            item, target_access = tickets.scoped_ticket(db, actor_id, candidate.ticket_id)
            if not tickets.can_update(item, target_access, actor_id) or not _append_eligible(
                db, case, item
            ):
                return result
            reopen = item.status in {"closed", "resolved"} and "open" in tickets.targets(
                item, target_access, actor_id
            )
            if item.status == "closed" and not reopen:
                return result
            result.update(
                can_append=True,
                candidate_ticket_id=item.id,
                candidate_ticket_number=str(item.number),
                candidate_ticket_version=item.version,
                candidate_ticket_status=item.status,
                candidate_can_reopen=reopen,
            )
    except identity.IdentityError:
        pass
    return result


def promote(
    db: Session,
    actor: User,
    case_id: UUID,
    body: PromotionCreate | PromotionAppend,
    request: Request,
) -> tuple[PromotionReceipt, bool]:
    from altvia.ticket_api import _event, create_record

    case = scoped_case(db, actor.id, case_id)
    access = tickets.creation_access(db, actor.id, case["client_id"], case["queue_id"], write=True)
    if (
        isinstance(body, PromotionCreate)
        and not access.manage
        and body.assignee_id not in {None, actor.id}
    ):
        raise identity.IdentityError(403, "forbidden")
    version = _expected_version(request)
    route = f"mail-promotion:{case_id}"
    key, fingerprint, saved = _operation(
        db, actor, request, route, {"case_version": version, "body": body.model_dump(mode="json")}
    )
    # Invalidated anchors still need their locks: gather IDs without filtering
    # invalidation, then resolve again after stable ordered case acquisition.
    identifiers = set(case["references_ids"]) | (
        {case["in_reply_to"]} if case["in_reply_to"] else set()
    )
    relevant = select(MailTriageCase.id).where(
        MailTriageCase.queue_id == case["queue_id"],
        MailTriageCase.client_id == case["client_id"],
        MailTriageCase.contact_id == case["contact_id"],
        MailTriageCase.email_snapshot == case["email_snapshot"],
        MailTriageCase.message_id.in_(identifiers),
        MailTriageCase.ticket_id.is_not(None),
    )
    case_ids = set(db.scalars(relevant)) | {case_id}
    db.execute(
        select(MailTriageCase.id)
        .where(MailTriageCase.id.in_(case_ids))
        .order_by(MailTriageCase.id)
        .with_for_update()
    ).all()
    case = scoped_case(db, actor.id, case_id)
    candidate = resolve_candidate(db, case, actor.id) if saved is None else None
    if isinstance(body, PromotionAppend):
        item, target_access = tickets.scoped_ticket(db, actor.id, body.ticket_id)
        if (item.client_id, item.queue_id) != (case["client_id"], case["queue_id"]):
            raise identity.IdentityError(409, "incoming_thread_conflict")
        item, target_access = tickets.scoped_ticket(db, actor.id, body.ticket_id, write=True)
        tickets.require_update(item, target_access, actor.id)
    if saved is not None:
        receipt = PromotionReceipt.model_validate(saved.result)
        item, target_access = tickets.scoped_ticket(
            db, actor.id, receipt.ticket_id, write=isinstance(body, PromotionAppend)
        )
        if isinstance(body, PromotionAppend):
            tickets.require_update(item, target_access, actor.id)
        return receipt, True
    if case["version"] != version:
        raise identity.IdentityError(409, "version_conflict")
    if case["state"] != "ready" or case["ticket_id"] is not None:
        raise identity.IdentityError(409, "incoming_case_ineligible")
    if case["version"] >= 2147483647:
        raise identity.IdentityError(409, "version_exhausted")
    assert candidate is not None
    now = db.scalar(select(func.clock_timestamp()))
    if isinstance(body, PromotionCreate):
        if candidate.ticket_id is not None:
            raise identity.IdentityError(409, "incoming_thread_conflict")
        if not _contact(db, case, lock=True):
            raise identity.IdentityError(409, "incoming_contact_changed")
        item = create_record(
            db,
            actor,
            access,
            TicketCreate(
                client_id=case["client_id"],
                queue_id=case["queue_id"],
                requester_id=case["contact_id"],
                subject=body.subject,
                priority=body.priority,
                category_id=body.category_id,
                assignee_id=body.assignee_id,
            ),
            request,
            source="email",
            now=now,
        )
    else:
        if candidate.ticket_id != item.id:
            raise identity.IdentityError(409, "incoming_thread_conflict")
        tickets.require_active(target_access)
        if not _contact(db, case, lock=True) or not _append_eligible(db, case, item):
            raise identity.IdentityError(409, "incoming_target_ineligible")
        if item.version != body.ticket_version:
            raise identity.IdentityError(409, "version_conflict")
        if body.reopen:
            if item.status not in {"resolved", "closed"}:
                raise identity.IdentityError(409, "invalid_ticket_transition")
            history = tickets.transition(
                db,
                item,
                target_access,
                actor.id,
                TicketTransition(target_status="open", reason=body.reopen_reason),
                now=now,
            )
            assert history is not None
            _event(
                db,
                actor,
                item,
                request,
                "status_changed",
                now=now,
                from_status=history.from_status,
                to_status=history.to_status,
                history_id=str(history.id),
            )
        elif item.status == "closed":
            raise identity.IdentityError(409, "ticket_closed")
        elif body.reopen_reason is not None:
            raise identity.IdentityError(422, "unexpected_reopen_reason")
    tickets.advance(item, now=now)
    db.flush()
    incoming = TicketIncomingMessage(
        case_id=case_id,
        ticket_id=item.id,
        client_id=case["client_id"],
        queue_id=case["queue_id"],
        ticket_version=item.version,
        actor_id=actor.id,
        received_at=case["received_at"],
        recorded_at=now,
    )
    db.add(incoming)
    db.flush()
    # Explicit columns only: source/origin/raw are never loaded by runtime.
    db.execute(
        update(MailTriageCase)
        .where(MailTriageCase.id == case_id)
        .values(
            ticket_id=item.id,
            incoming_message_id=incoming.id,
            state="promoted",
            version=case["version"] + 1,
        )
    )
    _event(
        db, actor, item, request, "message_received", now=now, incoming_message_id=str(incoming.id)
    )
    receipt = PromotionReceipt(case_id=case_id, ticket_id=item.id, incoming_message_id=incoming.id)
    _remember(db, actor, route, key, fingerprint, receipt, 201)
    return receipt, False


def incoming_outputs(
    db: Session, rows: list[TicketIncomingMessage]
) -> dict[UUID, IncomingMessageOutput]:
    cases = {
        case.id: case
        for case in db.execute(
            select(
                MailTriageCase.id,
                MailTriageCase.client_id,
                MailTriageCase.queue_id,
                MailTriageCase.contact_name,
                MailTriageCase.email_snapshot,
                MailTriageCase.subject,
                MailTriageCase.body_text,
                MailTriageCase.state,
            ).where(MailTriageCase.id.in_([row.case_id for row in rows]))
        )
    }
    result = {}
    for row in rows:
        case = cases[row.case_id]
        if (case.client_id, case.queue_id) != (row.client_id, row.queue_id):
            raise identity.IdentityError(404, "not_found")
        result[row.id] = IncomingMessageOutput(
            id=row.id,
            case_id=row.case_id,
            ticket_id=row.ticket_id,
            ticket_version=row.ticket_version,
            actor_id=row.actor_id,
            received_at=row.received_at,
            recorded_at=row.recorded_at,
            contact_name=case.contact_name,
            email_snapshot=case.email_snapshot,
            subject=case.subject,
            body_text=case.body_text,
            invalidation_warning="incoming_attestation_invalidated"
            if case.state in {"collision", "revoked"}
            else None,
        )
    return result


def incoming_output(db: Session, row: TicketIncomingMessage) -> IncomingMessageOutput:
    return incoming_outputs(db, [row])[row.id]
