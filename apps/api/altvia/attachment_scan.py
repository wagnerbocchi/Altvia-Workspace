"""Durable DB-clock fenced file scanner. All object/socket I/O is outside locks."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Event
from typing import cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, Select, func, select
from sqlalchemy.orm import Session, load_only

from altvia.file_scan_transport import ClamClient, ScanResult
from altvia.file_storage import S3Store, StorageError
from altvia.models import Attachment, AttachmentScanAttempt, AuditLog, OutboxEvent

SCAN_COLUMNS = {
    "id",
    "object_key",
    "bytes",
    "sha256",
    "policy_version",
    "version",
    "state",
    "generation",
    "attempts",
    "next_attempt_at",
    "lease_token",
    "lease_until",
}
SCAN_UPDATES = {"version", "state", "attempts", "next_attempt_at", "lease_token", "lease_until"}
RETRY_UPDATES = {"version", "state", "generation", "attempts", "next_attempt_at"}
REASONS = {
    "clean",
    "infected",
    "encrypted",
    "limit",
    "scan_error",
    "protocol",
    "unavailable",
    "cancelled",
    "timeout",
    "database_invalid",
    "database_changed",
    "storage_unavailable",
    "storage_integrity",
    "lease_expired",
}


@dataclass(frozen=True)
class Failure:
    reason: str
    disposition: str = "failed"
    engine: None = None
    database_version: None = None
    database_date: None = None


@dataclass(frozen=True)
class Claim:
    id: UUID
    generation: int
    attempt: int
    token: UUID
    db_now: datetime
    lease_until: datetime
    object_key: str
    bytes: int
    sha256: str


def clock(db: Session) -> datetime:
    now = db.scalar(select(func.clock_timestamp()))
    assert now is not None
    return cast(datetime, now)


def query() -> Select[tuple[Attachment]]:
    # The worker must never load filename, purpose, creator or parent context.
    return select(Attachment).options(
        load_only(*(getattr(Attachment, c) for c in SCAN_COLUMNS), raiseload=True)
    )


def event(db: Session, row: Attachment, now: datetime) -> None:
    correlation = uuid4().hex
    payload = {
        "actor_id": None,
        "actor_kind": "file_worker",
        "attachment_id": str(row.id),
        "state": row.state,
    }
    db.add(
        OutboxEvent(
            aggregate_type="attachment",
            aggregate_id=row.id,
            aggregate_version=row.version,
            event_type="file.scan_changed",
            schema_version=1,
            payload=payload,
            occurred_at=now,
            correlation_id=correlation,
            next_attempt_at=now,
        )
    )
    db.add(
        AuditLog(
            actor_id=None,
            action="file.scan_changed",
            resource_id=row.id,
            occurred_at=now,
            correlation_id=correlation,
            details=payload,
        )
    )
    db.flush()


def claim(engine: Engine, identifier: UUID) -> Claim | None:
    with Session(engine) as db, db.begin():
        row = db.scalar(query().where(Attachment.id == identifier).with_for_update())
        now = clock(db)  # DB clock is read only after owning the row lock.
        if (
            row is None
            or row.state != "quarantine"
            or row.attempts >= 8
            or row.next_attempt_at > now
        ):
            return None
        row.state, row.lease_token, row.lease_until = (
            "scanning",
            uuid4(),
            now + timedelta(seconds=60),
        )
        row.attempts += 1
        row.version += 1
        event(db, row, now)
        return Claim(
            row.id,
            row.generation,
            row.attempts,
            row.lease_token,
            now,
            row.lease_until,
            row.object_key,
            row.bytes,
            row.sha256,
        )


def history(db: Session, row: Attachment, now: datetime, result: ScanResult | Failure) -> None:
    assert row.lease_until is not None and row.lease_token is not None
    db.add(
        AttachmentScanAttempt(
            attachment_id=row.id,
            generation=row.generation,
            attempt=row.attempts,
            token=row.lease_token,
            claimed_at=row.lease_until - timedelta(seconds=60),
            lease_until=row.lease_until,
            finished_at=now,
            disposition=result.disposition,
            reason=result.reason,
            engine=result.engine,
            database_version=result.database_version,
            database_date=result.database_date,
        )
    )
    db.flush()


def finalize(
    engine: Engine, owned: Claim, result: ScanResult | Failure, stop: Event | None = None
) -> bool:
    if result.reason not in REASONS or result.disposition not in {"clean", "infected", "failed"}:
        raise ValueError("invalid_scan_result")
    with Session(engine) as db, db.begin():
        row = db.scalar(query().where(Attachment.id == owned.id).with_for_update())
        now = clock(db)
        if stop is not None and stop.is_set():
            return False
        if (
            row is None
            or row.state != "scanning"
            or row.generation != owned.generation
            or row.attempts != owned.attempt
            or row.lease_token != owned.token
            or row.lease_until is None
            or row.lease_until <= now
        ):
            return False
        # A date fresh at transport start may be stale after waiting for this lock.
        clean = (
            result.disposition == "clean"
            and result.reason == "clean"
            and result.engine == "1.4.6"
            and type(result.database_version) is int
            and result.database_version > 0
            and result.database_date is not None
            and result.database_date.tzinfo is not None
            and now - timedelta(hours=48) <= result.database_date <= now + timedelta(minutes=5)
        )
        if result.disposition == "clean" and not clean:
            result = ScanResult(
                "failed",
                "database_invalid",
                result.engine,
                result.database_version,
                result.database_date,
            )
        history(db, row, now, result)
        row.state = (
            "ready"
            if clean
            else "rejected"
            if result.reason in {"infected", "encrypted", "limit"}
            else "failed"
            if row.attempts >= 8
            else "quarantine"
        )
        row.next_attempt_at = now + timedelta(seconds=min(3600, 30 * 2 ** (row.attempts - 1)))
        row.lease_token = row.lease_until = None
        row.version += 1
        event(db, row, now)
        return True


def recover(engine: Engine) -> list[UUID]:
    recovered = []
    with Session(engine) as db, db.begin():
        rows = db.scalars(
            query()
            .where(Attachment.state == "scanning", Attachment.lease_until <= func.clock_timestamp())
            .order_by(Attachment.id)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        for row in rows:
            now = clock(db)
            if row.lease_until is None or row.lease_until > now:
                continue
            history(db, row, now, Failure("lease_expired"))
            row.state = "failed" if row.attempts >= 8 else "quarantine"
            row.next_attempt_at = now + timedelta(seconds=min(3600, 30 * 2 ** (row.attempts - 1)))
            row.lease_token = row.lease_until = None
            row.version += 1
            event(db, row, now)
            recovered.append(row.id)
    return recovered


def run_claim(
    engine: Engine, owned: Claim, storage: S3Store, scanner: ClamClient, stop: Event
) -> bool:
    if stop.is_set():
        return False
    try:
        with storage.verified_spool(
            owned.object_key, size=owned.bytes, sha256=owned.sha256
        ) as source:
            if stop.is_set():
                return False
            result: ScanResult | Failure = scanner.scan(source, db_now=owned.db_now, stop=stop)
    except StorageError as error:
        reason = "storage_integrity" if str(error) == "storage_integrity" else "storage_unavailable"
        result = Failure(reason)
    if stop.is_set():
        return False
    return finalize(engine, owned, result, stop)


def scan_once(
    engine: Engine, identifier: UUID, storage: S3Store, scanner: ClamClient, stop: Event
) -> bool:
    if stop.is_set():
        return False
    owned = claim(engine, identifier)
    return run_claim(engine, owned, storage, scanner, stop) if owned is not None else False


def validate_event(event: OutboxEvent) -> None:
    from typing import Literal

    from altvia.attachment_schemas import State

    class Payload(BaseModel):
        model_config = ConfigDict(extra="forbid")
        actor_id: UUID | None
        actor_kind: Literal["user", "file_worker"]
        attachment_id: UUID
        state: State

    if event.schema_version == 2:

        class OwnerPayload(BaseModel):
            model_config = ConfigDict(extra="forbid")
            actor_id: None
            actor_kind: Literal["management_command"]
            attachment_id: UUID
            state: Literal["quarantine"]

        owner = OwnerPayload.model_validate(event.payload)
        if (
            event.aggregate_type != "attachment"
            or event.event_type != "file.uploaded"
            or event.aggregate_version != 1
            or owner.attachment_id != event.aggregate_id
        ):
            raise ValueError("invalid_file_event")
        return

    payload = Payload.model_validate(event.payload)
    if (
        event.aggregate_type != "attachment"
        or event.schema_version != 1
        or payload.attachment_id != event.aggregate_id
        or event.event_type not in {"file.uploaded", "file.scan_changed", "file.scan_retried"}
        or (event.event_type == "file.scan_changed") != (payload.actor_kind == "file_worker")
        or (payload.actor_id is None) != (payload.actor_kind == "file_worker")
        or (
            event.event_type in {"file.uploaded", "file.scan_retried"}
            and payload.state != "quarantine"
        )
    ):
        raise ValueError("invalid_file_event")
