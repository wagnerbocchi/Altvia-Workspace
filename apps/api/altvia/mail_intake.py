"""Restricted durable capture of opaque mail; no identity inference or delivery."""

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.management import lock_identity_writes
from altvia.models import (
    AuditLog,
    InboundMailEnvelope,
    InboundMailVariant,
    MailboxSource,
    OutboxEvent,
    Team,
    TicketQueue,
)

MAX_RAW_BYTES = 2097152
MAX_VARIANTS = 16
MAX_VERSION = 2147483647
INTAKE_EVENTS = {
    "mailbox_source.created",
    "mailbox.message_quarantined",
    "mailbox.poll_checkpointed",
    "mailbox.message_normalized",
}


class IntakeError(ValueError):
    """A fixed safe error code, never an input-bearing diagnostic."""


@dataclass(frozen=True)
class CaptureReceipt:
    source_id: UUID
    envelope_id: UUID
    variant_id: UUID
    state: str
    replayed: bool


class IntakeEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    actor_id: None
    actor_kind: str
    source_id: UUID
    envelope_id: UUID | None = None
    variant_id: UUID | None = None
    state: str | None = None
    uid_validity: str | None = None
    last_uid: str | None = None
    reason: str | None = None
    status: str | None = None
    parser_version: str | None = None


def validate_intake_event(event: OutboxEvent) -> None:
    payload = IntakeEventPayload.model_validate(event.payload)
    expected = {"actor_id", "actor_kind", "source_id"}
    expected_schema = 1
    if event.event_type == "mailbox.message_quarantined":
        expected |= {"envelope_id", "variant_id", "state"}
        if payload.envelope_id is None or payload.variant_id is None:
            raise ValueError("Invalid intake event")
        if payload.state not in {"quarantine", "collision"}:
            raise ValueError("Invalid intake event")
    elif event.event_type == "mailbox.poll_checkpointed":
        expected |= {"uid_validity", "last_uid", "reason"}
        for value, minimum in ((payload.uid_validity, 1), (payload.last_uid, 0)):
            if (
                value is None
                or not re.fullmatch(r"0|[1-9][0-9]{0,9}", value)
                or not minimum <= int(value) <= 4294967295
            ):
                raise ValueError("Invalid poll event")
        if payload.reason not in {"initial", "epoch_changed", "message_captured", "range_scanned"}:
            raise ValueError("Invalid poll event")
    elif event.event_type == "mailbox.message_normalized":
        expected |= {"envelope_id", "variant_id", "status"}
        if event.schema_version == 2:
            expected_schema = 2
            expected |= {"parser_version"}
            if payload.parser_version != "2":
                raise ValueError("Invalid normalized parser version")
        if (
            payload.envelope_id is None
            or payload.variant_id is None
            or payload.status not in {"ready", "rejected"}
        ):
            raise ValueError("Invalid normalized event")
    if (
        event.event_type not in INTAKE_EVENTS
        or event.aggregate_type != "mailbox_source"
        or event.aggregate_id != payload.source_id
        or event.schema_version != expected_schema
        or event.aggregate_version < 1
        or payload.actor_kind != "management_command"
        or payload.model_fields_set != expected
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", event.correlation_id)
    ):
        raise ValueError("Invalid intake event")


def record_intake_event(
    db: Session,
    source: MailboxSource,
    action: str,
    details: dict[str, str] | None = None,
    *,
    schema_version: int = 1,
) -> None:
    now, correlation = datetime.now(UTC), uuid4().hex
    payload: dict[str, str | None] = {
        "actor_id": None,
        "actor_kind": "management_command",
        "source_id": str(source.id),
    }
    if details is not None:
        payload |= details
    event = OutboxEvent(
        schema_version=schema_version,
        aggregate_type="mailbox_source",
        aggregate_id=source.id,
        aggregate_version=source.version,
        event_type=action,
        payload=payload,
        occurred_at=now,
        correlation_id=correlation,
        next_attempt_at=now,
    )
    validate_intake_event(event)
    db.add(event)
    db.add(
        AuditLog(
            actor_id=None,
            action=action,
            resource_id=source.id,
            occurred_at=now,
            correlation_id=correlation,
            details=payload,
        )
    )
    db.flush()


def _check_key(key: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key):
        raise IntakeError("invalid_source_key")


def register_source(db: Session, key: str, queue_id: UUID) -> MailboxSource:
    _check_key(key)
    lock_identity_writes(db)
    existing = db.scalar(select(MailboxSource).where(MailboxSource.source_key == key))
    if existing is not None:
        if existing.queue_id != queue_id:
            raise IntakeError("source_identity_conflict")
        return existing
    team_id = db.scalar(select(TicketQueue.team_id).where(TicketQueue.id == queue_id))
    team = db.scalar(select(Team).where(Team.id == team_id).with_for_update())
    queue = db.scalar(select(TicketQueue).where(TicketQueue.id == queue_id).with_for_update())
    if team is None or queue is None or not team.active or not queue.active:
        raise IntakeError("source_parent_unavailable")
    source = MailboxSource(source_key=key, queue_id=queue_id, version=1)
    db.add(source)
    db.flush()
    record_intake_event(db, source, "mailbox_source.created")
    return source


def capture_message(
    db: Session, key: str, uid_validity: int, uid: int, raw: bytes
) -> CaptureReceipt:
    _check_key(key)
    if any(type(value) is not int or not 1 <= value <= 4294967295 for value in (uid_validity, uid)):
        raise IntakeError("invalid_mail_identity")
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RAW_BYTES:
        raise IntakeError("invalid_mail_size")
    source = db.scalar(
        select(MailboxSource).where(MailboxSource.source_key == key).with_for_update()
    )
    if source is None:
        raise IntakeError("source_unavailable")
    envelope = db.scalar(
        select(InboundMailEnvelope).where(
            InboundMailEnvelope.source_id == source.id,
            InboundMailEnvelope.uid_validity == uid_validity,
            InboundMailEnvelope.uid == uid,
        )
    )
    raw_hash = hashlib.sha256(raw).hexdigest()
    if envelope is not None:
        variant = db.scalar(
            select(InboundMailVariant).where(
                InboundMailVariant.envelope_id == envelope.id,
                InboundMailVariant.raw_sha256 == raw_hash,
            )
        )
        if variant is not None:
            if variant.raw_message != raw:
                raise IntakeError("mail_digest_conflict")
            return CaptureReceipt(source.id, envelope.id, variant.id, envelope.state, True)
        variants = db.scalar(
            select(func.count())
            .select_from(InboundMailVariant)
            .where(InboundMailVariant.envelope_id == envelope.id)
        )
        if variants is not None and variants >= MAX_VARIANTS:
            raise IntakeError("mail_variant_limit")
    if source.version >= MAX_VERSION:
        raise IntakeError("source_version_exhausted")
    if envelope is None:
        envelope = InboundMailEnvelope(source_id=source.id, uid_validity=uid_validity, uid=uid)
        db.add(envelope)
        db.flush()
    else:
        envelope.state = "collision"
    variant = InboundMailVariant(envelope_id=envelope.id, raw_message=raw, raw_sha256=raw_hash)
    db.add(variant)
    source.version += 1
    db.flush()
    receipt = CaptureReceipt(source.id, envelope.id, variant.id, envelope.state, False)
    record_intake_event(
        db,
        source,
        "mailbox.message_quarantined",
        {
            "envelope_id": str(receipt.envelope_id),
            "variant_id": str(receipt.variant_id),
            "state": receipt.state,
        },
    )
    return receipt


class SafeMailParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's normal diagnostic includes invalid values and unknown args.
        print("Invalid mail intake arguments; use --help for supported options.", file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("ALTVIA_ALLOW_MAIL_INTAKE") != "1":
        print("Explicit ALTVIA_ALLOW_MAIL_INTAKE=1 is required.", file=sys.stderr)
        return 1
    parser = SafeMailParser(
        description="Restricted owner-side opaque mail quarantine", allow_abbrev=False
    )
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register-source", allow_abbrev=False)
    register.add_argument("--source-key", required=True)
    register.add_argument("--queue-id", required=True, type=UUID)
    capture = commands.add_parser("capture", allow_abbrev=False)
    capture.add_argument("--source-key", required=True)
    capture.add_argument("--uid-validity", required=True, type=int)
    capture.add_argument("--uid", required=True, type=int)
    args = parser.parse_args(argv)
    engine = None
    try:
        raw = b""
        if args.command == "capture":
            raw = sys.stdin.buffer.read(MAX_RAW_BYTES + 1)
            if not 1 <= len(raw) <= MAX_RAW_BYTES:
                raise IntakeError("invalid_mail_size")
        engine = make_engine(DatabaseSettings())
        output: dict[str, str | bool]
        with Session(engine) as db, db.begin():
            if args.command == "register-source":
                source = register_source(db, args.source_key, args.queue_id)
                output = {"source_id": str(source.id)}
            else:
                receipt = capture_message(db, args.source_key, args.uid_validity, args.uid, raw)
                output = {
                    "source_id": str(receipt.source_id),
                    "envelope_id": str(receipt.envelope_id),
                    "variant_id": str(receipt.variant_id),
                    "state": receipt.state,
                    "replayed": receipt.replayed,
                }
    except (ValueError, SQLAlchemyError, OSError, AttributeError):
        print(
            "Mail intake failed; no acknowledgement. Check input and owner configuration.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    # Output after commit: an interrupted write never receives a false receipt.
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
