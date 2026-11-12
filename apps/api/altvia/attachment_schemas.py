"""Typed safe metadata and protected immutable upload/retry receipts."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Purpose = Literal["public", "note", "work"]
State = Literal["quarantine", "scanning", "ready", "rejected", "failed"]
OwnerType = Literal["ticket", "work_item"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AttachmentOutput(Strict):
    id: UUID
    owner_type: OwnerType
    owner_id: UUID
    purpose: Purpose
    filename: str
    media_type: str
    bytes: int
    state: State
    policy_version: Literal[1]
    version: int
    created_at: AwareDatetime
    can_download: bool
    can_retry_scan: bool


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
