"""Parent/action ownership and immutable safe file metadata, without network I/O."""

import re
import unicodedata
from dataclasses import dataclass
from typing import BinaryIO, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from altvia import identity, mail_cases, tickets, work_items
from altvia.attachment_schemas import (
    AttachmentOutput,
    CaseFileSet,
    ReadOwnerType,
    ReadPurpose,
    State,
)
from altvia.models import Attachment, Client, MailTriageCase, RoleBinding, Team, Ticket, TicketQueue

CASE_FILE_COLUMNS = {"file_extraction_version", "file_set_status"}


@dataclass(frozen=True)
class Parent:
    identifier: UUID
    version: int
    owner_type: ReadOwnerType
    purpose: ReadPurpose
    can_write: bool
    active: bool
    valid: bool = True

    def fresh(self, expected: int) -> None:
        if self.version != expected:
            raise identity.IdentityError(409, "version_conflict")
        if not self.active:
            raise identity.IdentityError(409, "attachment_parent_inactive")


def parent(
    db: Session,
    actor: UUID,
    owner: ReadOwnerType,
    identifier: UUID,
    purpose: ReadPurpose,
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
        result = Parent(
            item.id,
            item.version,
            owner,
            purpose,
            can_write,
            access.active and item.status != "closed",
        )
    elif owner == "work_item":
        if purpose != "work":
            raise identity.IdentityError(422, "invalid_purpose")
        work, permission = work_items.scoped_work(db, actor, identifier, write=write)
        result = Parent(
            work.id, work.version, owner, purpose, permission.contribute, permission.writable
        )
    elif owner == "mail_case":
        if purpose != "incoming":
            raise identity.IdentityError(404, "not_found")
        if write:
            from altvia.mail_promotion import scoped_case

            case = scoped_case(db, actor, identifier)
            access = tickets.creation_access(
                db, actor, case["client_id"], case["queue_id"], write=True
            )
            case = scoped_case(db, actor, identifier, lock=True)
            can_write = access.manage
            valid = case["state"] in {"ready", "promoted"}
            active = access.active and valid
            if case["ticket_id"] is not None:
                target, target_access = tickets.scoped_ticket(
                    db, actor, case["ticket_id"], write=True
                )
                can_write = can_write and tickets.can_update(target, target_access, actor)
                active = active and target_access.active and target.status != "closed"
            result = Parent(identifier, case["version"], owner, purpose, can_write, active, valid)
        else:
            rows = _case_scopes(db, actor, [identifier])
            if identifier not in rows:
                raise identity.IdentityError(404, "not_found")
            result = rows[identifier][0]
    else:
        raise identity.IdentityError(404, "not_found")
    if write and not result.can_write:
        raise identity.IdentityError(403, "forbidden")
    return result


def _case_scopes(
    db: Session, actor: UUID, case_ids: list[UUID]
) -> dict[UUID, tuple[Parent, int, str]]:
    """Batch the existing case and resulting-ticket visibility predicates."""
    if not case_ids:
        return {}
    cases = (
        db.execute(
            mail_cases.visible(actor)
            .add_columns(
                MailTriageCase.ticket_id,
                *(getattr(MailTriageCase, name) for name in sorted(CASE_FILE_COLUMNS)),
                RoleBinding.role_name,
                Client.active.label("client_active"),
                TicketQueue.active.label("queue_active"),
                Team.active.label("team_active"),
            )
            .join(Team, Team.id == TicketQueue.team_id)
            .where(MailTriageCase.id.in_(case_ids))
        )
        .mappings()
        .all()
    )
    ticket_ids = {case["ticket_id"] for case in cases if case["ticket_id"] is not None}
    targets = (
        {
            item.id: (item, tickets.Access(item.client, item.queue, role, team_active, note_access))
            for item, role, team_active, note_access in db.execute(
                tickets.visible(actor).where(Ticket.id.in_(ticket_ids))
            )
        }
        if ticket_ids
        else {}
    )
    result = {}
    for case in cases:
        if case["ticket_id"] is not None and case["ticket_id"] not in targets:
            continue
        valid = case["state"] in {"ready", "promoted"}
        active = valid and case["client_active"] and case["queue_active"] and case["team_active"]
        can_write = case["role_name"] == "operations_manager"
        if case["ticket_id"] is not None:
            item, access = targets[case["ticket_id"]]
            can_write = can_write and tickets.can_update(item, access, actor)
            active = active and access.active and item.status != "closed"
        result[case["id"]] = (
            Parent(case["id"], case["version"], "mail_case", "incoming", can_write, active, valid),
            case["file_extraction_version"],
            case["file_set_status"],
        )
    return result


def case_file_sets(db: Session, actor_id: UUID, case_ids: list[UUID]) -> dict[UUID, CaseFileSet]:
    scopes = _case_scopes(db, actor_id, case_ids)
    result = {
        identifier: CaseFileSet.model_validate(
            {"extraction_version": version, "status": status, "items": []}
        )
        for identifier, (_, version, status) in scopes.items()
    }
    if scopes:
        for row in db.scalars(
            select(Attachment)
            .where(Attachment.mail_case_id.in_(scopes))
            .order_by(Attachment.mail_case_id, Attachment.file_position)
        ):
            assert row.mail_case_id is not None
            result[row.mail_case_id].items.append(output(row, scopes[row.mail_case_id][0]))
    return result


def scoped(
    db: Session, actor: UUID, identifier: UUID, *, write: bool = False
) -> tuple[Attachment, Parent]:
    row = db.get(Attachment, identifier)
    if row is None:
        raise identity.IdentityError(404, "not_found")
    owner: ReadOwnerType
    if row.ticket_id is not None:
        owner = "ticket"
    elif row.work_item_id is not None:
        owner = "work_item"
    elif row.mail_case_id is not None:
        owner = "mail_case"
    else:
        raise identity.IdentityError(404, "not_found")
    scope = parent(
        db,
        actor,
        owner,
        row.ticket_id or row.work_item_id or cast(UUID, row.mail_case_id),
        cast(ReadPurpose, row.purpose),
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
        owner_id=scope.identifier,
        purpose=scope.purpose,
        filename=row.filename,
        media_type=row.media_type,
        bytes=row.bytes,
        state=cast(State, row.state),
        policy_version=1,
        version=row.version,
        created_at=row.created_at,
        can_download=row.state == "ready" and scope.valid,
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
