"""Concrete ordered immutable content sets; callers own current parent authority."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from altvia import identity
from altvia.attachment_schemas import AttachmentSummary, OwnerType, Purpose
from altvia.models import (
    Attachment,
    TicketMessageAttachment,
    TicketNoteAttachment,
    WorkCommentAttachment,
)


def intent(body: BaseModel, *, mode: Literal["json", "python"] = "json") -> dict[str, object]:
    # Exclude only the newly omitted field, preserving every old default/value.
    return body.model_dump(
        mode=mode,
        exclude={"attachment_ids"} if "attachment_ids" not in body.model_fields_set else set(),
    )


def locked(
    db: Session, owner: OwnerType, parent: UUID, purpose: Purpose, ids: list[UUID]
) -> list[Attachment]:
    column = Attachment.ticket_id if owner == "ticket" else Attachment.work_item_id
    rows = list(
        db.scalars(
            select(Attachment)
            .where(Attachment.id.in_(ids), column == parent, Attachment.purpose == purpose)
            .order_by(Attachment.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(rows) != len(ids):
        raise identity.IdentityError(404, "not_found")
    if any(row.state != "ready" or row.policy_version != 1 for row in rows):
        raise identity.IdentityError(409, "attachment_not_ready")
    indexed = {row.id: row for row in rows}
    return [indexed[i] for i in ids]


def attach(
    db: Session, identifier: UUID, parent: UUID, purpose: Purpose, rows: list[Attachment]
) -> None:
    link: TicketMessageAttachment | TicketNoteAttachment | WorkCommentAttachment
    for position, row in enumerate(rows):
        if purpose == "public":
            link = TicketMessageAttachment(
                message_id=identifier,
                ticket_id=parent,
                purpose=purpose,
                attachment_id=row.id,
                position=position,
            )
        elif purpose == "note":
            link = TicketNoteAttachment(
                note_id=identifier,
                ticket_id=parent,
                purpose=purpose,
                attachment_id=row.id,
                position=position,
            )
        else:
            link = WorkCommentAttachment(
                comment_id=identifier,
                work_item_id=parent,
                purpose=purpose,
                attachment_id=row.id,
                position=position,
            )
        db.add(link)
    db.flush()


def summaries(rows: list[Attachment]) -> list[AttachmentSummary]:
    return [
        AttachmentSummary(
            id=row.id, filename=row.filename, media_type=row.media_type, bytes=row.bytes
        )
        for row in rows
    ]
