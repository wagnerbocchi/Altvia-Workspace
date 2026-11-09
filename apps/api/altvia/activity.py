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
CLIENT_EVENT_TYPES = {"client.created", "client.updated", "client.access_changed"}


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
    role_name: Literal["viewer", "operations_manager", "none"] | None = None
    changed_fields: str | None = Field(
        default=None, pattern=r"^(name|active)(,(name|active))?$", max_length=20
    )

    @model_validator(mode="after")
    def actor_matches_kind(self) -> "ClientEventPayload":
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
        if event.event_type not in EVENT_TYPES | CLIENT_EVENT_TYPES or event.schema_version != 1:
            event.status, event.last_error_code, event.lease_until = (
                "dead",
                "unsupported_event",
                None,
            )
            return False
        try:
            payload: EventPayload | ClientEventPayload
            if event.event_type in CLIENT_EVENT_TYPES:
                payload = ClientEventPayload.model_validate(event.payload)
                if event.aggregate_type != "client":
                    raise ValueError("Event resource mismatch")
                fields = set(payload.model_dump(exclude_none=True)) - {"actor_id", "actor_kind"}
                expected_fields = {
                    "client.created": {"manager_user_id"},
                    "client.updated": {"changed_fields"},
                    "client.access_changed": {"member_user_id", "role_name"},
                }[event.event_type]
                if fields != expected_fields:
                    raise ValueError("Invalid client event fields")
            else:
                payload = EventPayload.model_validate(event.payload)
            if (
                event.aggregate_type not in {"identity", "team", "client"}
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
            if (event.aggregate_type == "team") != team_event or (
                (event.aggregate_type == "client") != (event.event_type in CLIENT_EVENT_TYPES)
            ):
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
