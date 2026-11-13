"""Parent/action ownership and immutable safe file metadata, without network I/O."""

import re
import unicodedata
from dataclasses import dataclass
from typing import BinaryIO, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from altvia import identity, tickets, work_items
from altvia.attachment_schemas import AttachmentOutput, OwnerType, Purpose, State
from altvia.models import Attachment, Ticket, WorkItem


@dataclass(frozen=True)
class Parent:
    item: Ticket | WorkItem
    owner_type: OwnerType
    purpose: Purpose
    can_write: bool
    active: bool

    def fresh(self, expected: int) -> None:
        if self.item.version != expected:
            raise identity.IdentityError(409, "version_conflict")
        if not self.active:
            raise identity.IdentityError(409, "attachment_parent_inactive")


def parent(
    db: Session,
    actor: UUID,
    owner: OwnerType,
    identifier: UUID,
    purpose: Purpose,
    *,
    write: bool = False,
) -> Parent:
    if owner == "ticket":
        if purpose not in {"public", "note"}:
            raise identity.IdentityError(422, "invalid_purpose")
        item, access = tickets.scoped_ticket(db, actor, identifier, write=write)
        if purpose == "note" and not tickets.can_read_notes(access):
            raise identity.IdentityError(404, "not_found")
        can_write = (
            access.note_access == "write"
            if purpose == "note"
            else tickets.can_update(item, access, actor)
        )
        result = Parent(item, owner, purpose, can_write, access.active and item.status != "closed")
    else:
        if purpose != "work":
            raise identity.IdentityError(422, "invalid_purpose")
        work, permission = work_items.scoped_work(db, actor, identifier, write=write)
        result = Parent(work, owner, purpose, permission.contribute, permission.writable)
    if write and not result.can_write:
        raise identity.IdentityError(403, "forbidden")
    return result


def scoped(
    db: Session, actor: UUID, identifier: UUID, *, write: bool = False
) -> tuple[Attachment, Parent]:
    row = db.get(Attachment, identifier)
    if row is None:
        raise identity.IdentityError(404, "not_found")
    owner: OwnerType
    if row.ticket_id is not None:
        owner = "ticket"
    elif row.work_item_id is not None:
        owner = "work_item"
    else:
        # Producer rollout precedes authorized incoming-file reads. Never fall
        # through to another parent's purpose validation (an existence leak).
        raise identity.IdentityError(404, "not_found")
    scope = parent(
        db,
        actor,
        owner,
        row.ticket_id or cast(UUID, row.work_item_id),
        cast(Purpose, row.purpose),
        write=write,
    )
    if write:
        row = db.scalars(
            select(Attachment)
            .where(Attachment.id == identifier)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()
    return row, scope


def output(row: Attachment, scope: Parent) -> AttachmentOutput:
    return AttachmentOutput(
        id=row.id,
        owner_type=scope.owner_type,
        owner_id=scope.item.id,
        purpose=scope.purpose,
        filename=row.filename,
        media_type=row.media_type,
        bytes=row.bytes,
        state=cast(State, row.state),
        policy_version=1,
        version=row.version,
        created_at=row.created_at,
        can_download=row.state == "ready",
        can_retry_scan=row.state == "failed" and scope.can_write and scope.active,
    )


def event(
    db: Session, row: Attachment, event_type: str, actor_id: UUID | None, correlation: str
) -> None:
    now = db.scalar(select(func.clock_timestamp()))
    assert now is not None
    identity.record_event(
        db,
        actor_id,
        row.id,
        event_type,
        now,
        correlation,
        row.version,
        aggregate_type="attachment",
        details={"attachment_id": str(row.id), "state": row.state},
    )


def validate_filename(name: str) -> None:
    if (
        not name
        or len(name.encode("utf-8")) > 255
        or name.strip() != name
        or name in {".", ".."}
        or name.startswith(".")
        or name.endswith(".")
        or any(c in "/\\" or unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in name)
    ):
        raise identity.IdentityError(422, "invalid_filename")


def media_type(source: BinaryIO, filename: str) -> str:
    source.seek(0)
    head = source.read(16)
    suffix = filename.rsplit(".", 1)[-1].lower()
    result = None
    if suffix == "pdf" and head.startswith(b"%PDF-"):
        result = "application/pdf"
    elif suffix == "png" and head.startswith(b"\x89PNG\r\n\x1a\n"):
        result = "image/png"
    elif suffix in {"jpg", "jpeg"} and head.startswith(b"\xff\xd8\xff"):
        result = "image/jpeg"
    elif suffix in {"txt", "log"}:
        source.seek(0)
        try:
            text = source.read().decode("utf-8", errors="strict")
            sniffing_text = text.removeprefix("\ufeff")
            if not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text) and not re.match(
                r"\s*(?:<!doctype\s+html|<html|<svg|<script|<\?xml)", sniffing_text, re.I
            ):
                result = "text/plain"
        except UnicodeError:
            pass
    source.seek(0)
    if result is None:
        raise identity.IdentityError(422, "invalid_file_type")
    return result
