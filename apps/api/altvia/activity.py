"""Durable identity projection; Redis messages carry only authoritative event IDs."""

import random
import re
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from altvia.models import ActivityEvent, AuditLog, OutboxEvent, ProcessedEvent
from altvia.work_schemas import WORK_TRANSITIONS

CONSUMER = "identity_activity_v1"
MAX_ATTEMPTS = 8
EVENT_TYPES = {
    "identity.session_created",
    "identity.session_revoked",
    "identity.admin_bootstrapped",
    "identity.user_created",
    "identity.user_enabled",
    "identity.user_disabled",
    "identity.password_reset",
    "identity.admin_granted",
    "identity.admin_revoked",
    "identity.team_role_granted",
    "identity.team_role_revoked",
    "identity.team_created",
    "identity.team_updated",
    "identity.team_member_added",
    "identity.team_member_removed",
}
CLIENT_EVENT_TYPES = {
    "client.created",
    "client.updated",
    "client.access_changed",
    "client.contact_created",
    "client.contact_updated",
}
PROJECT_EVENT_TYPES = {"project.created", "project.updated", "project.access_changed"}
MILESTONE_EVENT_TYPES = {"project.milestone_created", "project.milestone_updated"}
AREA_EVENT_TYPES = {"operational_area.created", "operational_area.updated"}
WORK_EVENT_TYPES = {
    "work_item.created",
    "work_item.updated",
    "work_item.assigned",
    "work_item.blocked",
    "work_item.completed",
    "work_item.status_changed",
    "work_item.commented",
}


class MilestoneEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    actor_id: UUID
    actor_kind: Literal["user"]
    milestone_id: UUID
    changed_fields: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def valid_changes(self) -> "MilestoneEventPayload":
        if self.changed_fields is not None:
            fields = self.changed_fields.split(",")
            if len(fields) != len(set(fields)) or not set(fields).issubset(
                {"title", "due", "state"}
            ):
                raise ValueError("Invalid milestone changes")
        return self


class WorkEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    actor_id: UUID | None
    actor_kind: Literal["user", "management_command"]
    project_id: UUID
    changed_fields: str | None = Field(default=None, max_length=150)
    from_status: Literal["todo", "in_progress", "blocked", "done", "cancelled"] | None = None
    to_status: Literal["todo", "in_progress", "blocked", "done", "cancelled"] | None = None
    comment_id: UUID | None = None

    @model_validator(mode="after")
    def valid_fields(self) -> "WorkEventPayload":
        if (self.actor_kind == "user") != (self.actor_id is not None):
            raise ValueError("Invalid actor")
        if self.changed_fields is not None:
            fields = self.changed_fields.split(",")
            if len(fields) != len(set(fields)) or not set(fields).issubset(
                {
                    "title",
                    "description",
                    "priority",
                    "parent_id",
                    "owner_id",
                    "assignee_ids",
                    "due",
                    "estimated_minutes",
                }
            ):
                raise ValueError("Invalid changed fields")
        return self


class EventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    actor_id: UUID | None
    actor_kind: Literal["user", "management_command"]
    team_id: UUID | None = None
    role_name: Literal["viewer", "operations_manager"] | None = None
    member_user_id: UUID | None = None
    changed_fields: str | None = Field(
        default=None, pattern=r"^(name|active)(,(name|active))?$", max_length=20
    )

    @model_validator(mode="after")
    def actor_matches_kind(self) -> "EventPayload":
        if (self.actor_kind == "user") != (self.actor_id is not None):
            raise ValueError("Actor kind does not match identifier")
        return self


class ClientEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    actor_id: UUID | None
    actor_kind: Literal["user", "management_command"]
    manager_user_id: UUID | None = None
    member_user_id: UUID | None = None
    contact_id: UUID | None = None
    role_name: Literal["viewer", "operations_manager", "none"] | None = None
    changed_fields: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def actor_matches_kind(self) -> "ClientEventPayload":
        if (self.actor_kind == "user") != (self.actor_id is not None):
            raise ValueError("Actor kind does not match identifier")
        if self.changed_fields is not None:
            fields = self.changed_fields.split(",")
            if len(fields) != len(set(fields)) or not set(fields).issubset(
                {"name", "active", "default_project_id", "display_name", "email"}
            ):
                raise ValueError("Invalid changed fields")
        return self


class RegistryEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    actor_id: UUID | None
    actor_kind: Literal["user", "management_command"]
    manager_user_id: UUID | None = None
    member_user_id: UUID | None = None
    role_name: Literal["viewer", "agent", "project_manager", "none"] | None = None
    changed_fields: str | None = Field(
        default=None,
        pattern=r"^(name|active|operational_area_id)(,(name|active|operational_area_id)){0,2}$",
        max_length=40,
    )

    @model_validator(mode="after")
    def actor_matches_kind(self) -> "RegistryEventPayload":
        if (self.actor_kind == "user") != (self.actor_id is not None):
            raise ValueError("Actor kind does not match identifier")
        return self


def claim_events(engine: Engine, now: datetime, limit: int = 25) -> list[tuple[UUID, datetime]]:
    if not 1 <= limit <= 100:
        raise ValueError("Invalid dispatch batch")
    with Session(engine) as db, db.begin():
        events = db.scalars(
            select(OutboxEvent)
            .where(
                or_(
                    and_(OutboxEvent.status == "pending", OutboxEvent.next_attempt_at <= now),
                    and_(OutboxEvent.status == "processing", OutboxEvent.lease_until <= now),
                )
            )
            .order_by(OutboxEvent.next_attempt_at, OutboxEvent.event_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        leases = []
        for event in events:
            if event.attempts >= MAX_ATTEMPTS:
                event.status, event.last_error_code, event.lease_until = (
                    "dead",
                    "attempts_exhausted",
                    None,
                )
                continue
            event.status = "processing"
            event.attempts += 1
            event.lease_until = now + timedelta(seconds=30)
            leases.append((event.event_id, event.lease_until))
        return leases


def publication_failed(
    engine: Engine,
    event_id: UUID,
    lease: datetime,
    now: datetime,
    code: Literal["broker_unavailable", "processing_failed"],
) -> bool:
    with Session(engine) as db, db.begin():
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_id == event_id).with_for_update()
        )
        if event is None or event.status != "processing" or event.lease_until != lease:
            return False
        event.last_error_code = code
        event.status = "dead" if event.attempts >= MAX_ATTEMPTS else "pending"
        event.lease_until = None
        delay = min(900, 5 * 2 ** (event.attempts - 1))
        event.next_attempt_at = now + timedelta(
            seconds=delay + random.SystemRandom().uniform(0, delay / 5)
        )
        return True


def consume_event(engine: Engine, event_id: UUID, now: datetime) -> bool:
    with Session(engine) as db, db.begin():
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_id == event_id).with_for_update()
        )
        if event is None or event.status in {"dead", "delivered"}:
            return False
        if db.get(ProcessedEvent, (CONSUMER, event_id)) is not None:
            event.status, event.lease_until, event.last_error_code = "delivered", None, None
            return False
        if (
            event.event_type
            not in EVENT_TYPES
            | CLIENT_EVENT_TYPES
            | PROJECT_EVENT_TYPES
            | AREA_EVENT_TYPES
            | WORK_EVENT_TYPES
            | MILESTONE_EVENT_TYPES
            or event.schema_version != 1
        ):
            event.status, event.last_error_code, event.lease_until = (
                "dead",
                "unsupported_event",
                None,
            )
            return False
        try:
            payload: (
                EventPayload
                | ClientEventPayload
                | RegistryEventPayload
                | WorkEventPayload
                | MilestoneEventPayload
            )
            if event.event_type in MILESTONE_EVENT_TYPES:
                payload = MilestoneEventPayload.model_validate(event.payload)
                if (payload.changed_fields is not None) != (
                    event.event_type == "project.milestone_updated"
                ):
                    raise ValueError("Invalid milestone event fields")
            elif event.event_type in WORK_EVENT_TYPES:
                payload = WorkEventPayload.model_validate(event.payload)
                fields = set(payload.model_dump(exclude_none=True)) - {
                    "actor_id",
                    "actor_kind",
                    "project_id",
                }
                expected_work_fields = (
                    {"changed_fields"}
                    if event.event_type in {"work_item.updated", "work_item.assigned"}
                    else {"comment_id"}
                    if event.event_type == "work_item.commented"
                    else set()
                    if event.event_type == "work_item.created"
                    else {"from_status", "to_status"}
                )
                if (
                    fields != expected_work_fields
                    or (event.event_type == "work_item.blocked" and payload.to_status != "blocked")
                    or (event.event_type == "work_item.completed" and payload.to_status != "done")
                ):
                    raise ValueError("Invalid work event")
                if payload.changed_fields is not None:
                    assigned = bool(
                        set(payload.changed_fields.split(",")) & {"owner_id", "assignee_ids"}
                    )
                    if assigned != (event.event_type == "work_item.assigned"):
                        raise ValueError("Mismatched assignment event")
                if payload.from_status is not None:
                    expected_work_event = (
                        "work_item.completed"
                        if payload.to_status == "done"
                        else "work_item.blocked"
                        if payload.to_status == "blocked"
                        else "work_item.status_changed"
                    )
                    if (
                        payload.to_status not in WORK_TRANSITIONS[payload.from_status]
                        or event.event_type != expected_work_event
                    ):
                        raise ValueError("Invalid transition event")
            elif event.event_type in PROJECT_EVENT_TYPES | AREA_EVENT_TYPES:
                payload = RegistryEventPayload.model_validate(event.payload)
                resource = (
                    "project" if event.event_type in PROJECT_EVENT_TYPES else "operational_area"
                )
                fields = set(payload.model_dump(exclude_none=True)) - {"actor_id", "actor_kind"}
                expected = {
                    "project.created": {"manager_user_id"},
                    "project.updated": {"changed_fields"},
                    "project.access_changed": {"member_user_id", "role_name"},
                    "operational_area.created": set(),
                    "operational_area.updated": {"changed_fields"},
                }[event.event_type]
                if event.aggregate_type != resource or fields != expected:
                    raise ValueError("Invalid registry event fields")
                if (
                    resource == "operational_area"
                    and payload.changed_fields is not None
                    and "operational_area_id" in payload.changed_fields
                ):
                    raise ValueError("Invalid area change")
            elif event.event_type in CLIENT_EVENT_TYPES:
                payload = ClientEventPayload.model_validate(event.payload)
                if event.aggregate_type != "client":
                    raise ValueError("Event resource mismatch")
                fields = set(payload.model_dump(exclude_none=True)) - {"actor_id", "actor_kind"}
                expected_fields = {
                    "client.created": {"manager_user_id"},
                    "client.updated": {"changed_fields"},
                    "client.access_changed": {"member_user_id", "role_name"},
                    "client.contact_created": {"contact_id"},
                    "client.contact_updated": {"contact_id", "changed_fields"},
                }[event.event_type]
                if fields != expected_fields:
                    raise ValueError("Invalid client event fields")
                if payload.changed_fields is not None:
                    allowed = (
                        {"display_name", "email", "active"}
                        if event.event_type == "client.contact_updated"
                        else {"name", "active", "default_project_id"}
                    )
                    if not set(payload.changed_fields.split(",")).issubset(allowed):
                        raise ValueError("Invalid client change")
            else:
                payload = EventPayload.model_validate(event.payload)
            if (
                event.aggregate_type
                not in {"identity", "team", "client", "project", "operational_area", "work_item"}
                or event.aggregate_version < 1
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", event.correlation_id)
            ):
                raise ValueError("Invalid event envelope")
            team_event = event.event_type in {
                "identity.team_created",
                "identity.team_updated",
                "identity.team_member_added",
                "identity.team_member_removed",
            }
            expected_resource = (
                "work_item"
                if event.event_type in WORK_EVENT_TYPES
                else "project"
                if event.event_type in PROJECT_EVENT_TYPES | MILESTONE_EVENT_TYPES
                else "operational_area"
                if event.event_type in AREA_EVENT_TYPES
                else "client"
                if event.event_type in CLIENT_EVENT_TYPES
                else "team"
                if team_event
                else "identity"
            )
            if event.aggregate_type != expected_resource:
                raise ValueError("Event resource mismatch")
        except (ValueError, ValidationError):
            event.status, event.last_error_code, event.lease_until = "dead", "invalid_event", None
            return False
        details = {
            k: str(v)
            for k, v in payload.model_dump(exclude_none=True).items()
            if k not in {"actor_id", "actor_kind"}
        }
        db.add(ProcessedEvent(consumer=CONSUMER, event_id=event_id, processed_at=now))
        db.add(
            ActivityEvent(
                event_id=event_id,
                resource_type=event.aggregate_type,
                resource_id=event.aggregate_id,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                actor_id=payload.actor_id,
                actor_kind=payload.actor_kind,
                aggregate_version=event.aggregate_version,
                correlation_id=event.correlation_id,
                details=details,
            )
        )
        event.status, event.lease_until, event.last_error_code = "delivered", None, None
        return True


def replay_event(engine: Engine, event_id: UUID, now: datetime) -> bool:
    with Session(engine) as db, db.begin():
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_id == event_id).with_for_update()
        )
        if event is None or event.status != "dead":
            return False
        event.status, event.attempts, event.lease_until = "pending", 0, None
        event.next_attempt_at, event.last_error_code = now, None
        db.add(
            AuditLog(
                actor_id=None,
                action="identity.outbox_replayed",
                resource_id=event.aggregate_id,
                occurred_at=now,
                correlation_id=event.correlation_id,
                details={"actor_kind": "management_command", "event_id": str(event_id)},
            )
        )
        return True
