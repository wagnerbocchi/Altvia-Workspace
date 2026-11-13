"""Typed safe metadata and protected immutable upload/retry receipts."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

Purpose = Literal["public", "note", "work"]
State = Literal["quarantine", "scanning", "ready", "rejected", "failed"]
OwnerType = Literal["ticket", "work_item"]
ReadOwnerType = Literal["ticket", "work_item", "mail_case"]
ReadPurpose = Literal["public", "note", "work", "incoming"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AttachmentOutput(Strict):
    id: UUID
    owner_type: ReadOwnerType
    owner_id: UUID
    purpose: ReadPurpose
    filename: str
    media_type: str
    bytes: int
    state: State
    policy_version: Literal[1]
    version: int
    created_at: AwareDatetime
    can_download: bool
    can_retry_scan: bool


class CaseFileSet(Strict):
    extraction_version: Literal[0, 1]
    status: Literal["legacy", "complete", "unavailable"]
    items: list[AttachmentOutput] = Field(max_length=20)


class AttachmentPage(Strict):
    items: list[AttachmentOutput]
    next_cursor: str | None
    can_upload: bool


class UploadReceipt(Strict):
    owner_type: OwnerType
    owner_id: UUID
    attachment_id: UUID
    bytes: int
    sha256: str
    version: Literal[1] = 1


class RetryReceipt(Strict):
    attachment_id: UUID
    version: int


class RetryScan(Strict):
    pass


class AttachmentFilters(Strict):
    purpose: Purpose
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=500)


class AttachmentSelection(Strict):
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("attachment_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate attachment")
        return value


class AttachmentSummary(Strict):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    filename: str
    media_type: str
    bytes: int


class TicketAttachmentFilters(AttachmentFilters):
    purpose: Literal["public", "note"]


class WorkAttachmentFilters(AttachmentFilters):
    purpose: Literal["work"]
