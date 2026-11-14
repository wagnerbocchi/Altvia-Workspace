"""Shared date/instant deadline value and PostgreSQL boundary semantics."""

import re
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from altvia import identity
from altvia.models import ProjectMilestone, WorkItem


class DateDue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    precision: Literal["date"]
    date: date
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator("date", mode="before")
    @classmethod
    def iso_date(cls, value: object) -> object:
        if type(value) is date or (
            isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        ):
            return value
        raise ValueError("An ISO date is required")


class InstantDue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    precision: Literal["instant"]
    instant: AwareDatetime

    @field_validator("instant", mode="before")
    @classmethod
    def iso_instant(cls, value: object) -> object:
        if isinstance(value, datetime) or (isinstance(value, str) and "T" in value):
            return value
        raise ValueError("A timezone-aware ISO timestamp is required")


Due = Annotated[DateDue | InstantDue, Field(discriminator="precision")]


def set_due(db: Session, item: WorkItem | ProjectMilestone, due: Due | None) -> None:
    item.due_at = item.due_precision = item.due_date_local = item.due_timezone = None
    if isinstance(due, InstantDue):
        item.due_at, item.due_precision = due.instant.astimezone(UTC), "instant"
    elif isinstance(due, DateDue):
        known = db.scalar(
            text("SELECT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=:zone)"),
            {"zone": due.timezone},
        )
        if not known or due.date.year >= 9999:
            raise identity.IdentityError(422, "invalid_due")
        result = db.execute(
            text("""SELECT
            altvia_work_day_start(CAST(:day AS date)+1, :zone) AS boundary,
            (altvia_work_day_start(CAST(:day AS date), :zone)
                AT TIME ZONE :zone)::date AS roundtrip"""),
            {"day": due.date, "zone": due.timezone},
        ).one()
        if result.roundtrip != due.date:
            raise identity.IdentityError(422, "invalid_due")
        item.due_at, item.due_precision = result.boundary, "date"
        item.due_date_local, item.due_timezone = due.date, due.timezone


def due_output(item: WorkItem | ProjectMilestone) -> Due | None:
    return due_value(item.due_precision, item.due_at, item.due_date_local, item.due_timezone)


def due_value(
    precision: str | None, instant: datetime | None, local_date: date | None, timezone: str | None
) -> Due | None:
    """Format the same deadline from ORM owners or a bounded SQL projection."""
    due: Due | None = None
    if precision == "date" and local_date and timezone:
        due = DateDue(precision="date", date=local_date, timezone=timezone)
    elif instant:
        due = InstantDue(precision="instant", instant=instant)
    return due
