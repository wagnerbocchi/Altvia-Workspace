"""Queue configuration DTOs, independent of customer ticket content."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema


def _name(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        if any(character in value for character in ("\0", "\r", "\n")):
            raise ValueError("A single-line name is required")
    return value


QueueName = Annotated[str, BeforeValidator(_name), Field(min_length=1, max_length=150)]


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: QueueName


class QueueCreate(CategoryCreate):
    team_id: UUID


class QueuePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})
    name: QueueName | SkipJsonSchema[None] = None
    active: StrictBool | SkipJsonSchema[None] = None

    @field_validator("name", "active")
    @classmethod
    def non_null(cls, value: str | bool | None) -> str | bool:
        if value is None:
            raise ValueError("A non-null value is required")
        return value

    @model_validator(mode="after")
    def nonempty(self) -> "QueuePatch":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class QueueRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class QueueOutput(QueueRecord):
    team_id: UUID
    team_name: str
    team_active: bool
    can_manage: bool


class CategoryOutput(QueueRecord):
    queue_id: UUID


class QueuePage(BaseModel):
    items: list[QueueOutput]
    next_cursor: str | None
    can_create: bool


class CategoryPage(BaseModel):
    items: list[CategoryOutput]
    next_cursor: str | None


class QueueTeam(BaseModel):
    id: UUID
    name: str
    active: bool
    can_manage: bool


class QueueTeamPage(BaseModel):
    items: list[QueueTeam]
    next_cursor: str | None


class QueueReceipt(BaseModel):
    queue_id: UUID


class CategoryReceipt(QueueReceipt):
    category_id: UUID
