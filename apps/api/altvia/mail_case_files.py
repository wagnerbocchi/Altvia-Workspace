"""Private object staging and immutable case-set persistence; no resource reads."""

import hashlib
import io
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from altvia.attachment_scan import validate_event
from altvia.file_storage import S3Store, StorageError
from altvia.file_storage_owner import load_storage
from altvia.mail_mime import ExtractedFiles
from altvia.models import Attachment, AuditLog, MailTriageCase, OutboxEvent


@dataclass(frozen=True)
class PreparedCaseFile:
    filename: str
    media_type: str
    bytes: int
    sha256: str
    object_key: str


@dataclass(frozen=True)
class PreparedCaseFiles:
    status: Literal["complete", "unavailable"]
    files: tuple[PreparedCaseFile, ...] = ()
    reason: str | None = None


def stage_case_files(extracted: ExtractedFiles, storage_file: Path | None) -> PreparedCaseFiles:
    # Text-only and unavailable sets require neither config nor an S3 connection.
    if not extracted.files:
        return PreparedCaseFiles(extracted.status, reason=extracted.reason)
    if storage_file is None:
        raise StorageError("storage_unavailable")
    store = S3Store(load_storage(storage_file))
    staged = []
    try:
        for item in extracted.files:
            prepared = PreparedCaseFile(
                item.filename,
                item.media_type,
                len(item.content),
                hashlib.sha256(item.content).hexdigest(),
                "objects/" + secrets.token_hex(32),
            )
            with io.BytesIO(item.content) as source:
                store.put_new(
                    prepared.object_key, source, size=prepared.bytes, sha256=prepared.sha256
                )
            staged.append(prepared)
    finally:
        store.close()
    return PreparedCaseFiles(extracted.status, tuple(staged), extracted.reason)


def persist_case_files(
    db: Session, case: MailTriageCase, prepared: PreparedCaseFiles
) -> tuple[Attachment, ...]:
    """Called only in owner publication after the immutable case header is flushed."""
    from altvia.mail_cases_owner import require_owner

    require_owner(db)
    rows = tuple(
        Attachment(
            mail_case_id=case.id,
            file_position=position,
            purpose="incoming",
            creator_id=None,
            parent_version=1,
            filename=item.filename,
            media_type=item.media_type,
            bytes=item.bytes,
            sha256=item.sha256,
            object_key=item.object_key,
        )
        for position, item in enumerate(prepared.files)
    )
    db.add_all(rows)
    db.flush()
    for row in rows:
        now = db.scalar(select(func.clock_timestamp()))
        assert now is not None
        correlation = uuid4().hex
        payload = {
            "actor_id": None,
            "actor_kind": "management_command",
            "attachment_id": str(row.id),
            "state": "quarantine",
        }
        event = OutboxEvent(
            aggregate_type="attachment",
            aggregate_id=row.id,
            aggregate_version=1,
            event_type="file.uploaded",
            schema_version=2,
            payload=payload,
            occurred_at=now,
            correlation_id=correlation,
            next_attempt_at=now,
        )
        validate_event(event)
        db.add(event)
        db.add(
            AuditLog(
                actor_id=None,
                action="file.uploaded",
                resource_id=row.id,
                occurred_at=now,
                correlation_id=correlation,
                details=payload,
            )
        )
    db.flush()
    return rows
