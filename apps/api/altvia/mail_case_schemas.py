"""Published mail case read contracts; no provenance or routing identifiers."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CaseState = Literal["ready", "collision", "revoked"]


class CaseFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=600)
    queue_id: UUID | None = None
    client_id: UUID | None = None
    state: CaseState | None = None


class CaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    queue_id: UUID
    client_id: UUID
    contact_id: UUID
    contact_name: str
    subject: str
    received_at: datetime
    created_at: datetime
    state: CaseState
    version: int


class CaseDetail(CaseSummary):
    email_snapshot: str
    body_text: str


class CasePage(BaseModel):
    items: list[CaseSummary]
    next_cursor: str | None
