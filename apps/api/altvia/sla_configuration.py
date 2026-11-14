"""Immutable SLA configuration revisions under native queue/customer authority."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from altvia import business_time, identity, queue_registry
from altvia.models import (
    BusinessCalendar,
    BusinessCalendarRevision,
    OutboxEvent,
    SlaPolicy,
    SlaPolicyRevision,
)
from altvia.queue_client_configuration import ConfigurationAccess, require_active
from altvia.sla_schemas import (
    CalendarCreate,
    CalendarOutput,
    CalendarPatch,
    CalendarSummary,
    PolicyCalendarSnapshot,
    PolicyCreate,
    PolicyOutput,
    PolicyPatch,
)
from altvia.work_schemas import StrictModel


class _ConfigurationEvent(StrictModel):
    actor_id: UUID
    actor_kind: Literal["user"]
    queue_id: UUID
    client_id: UUID
    changed_fields: str | None = Field(default=None, max_length=160)


class _CalendarEvent(_ConfigurationEvent):
    calendar_id: UUID


class _PolicyEvent(_ConfigurationEvent):
    policy_id: UUID


def validate_private_event(event: OutboxEvent) -> None:
    calendar_event = event.event_type.startswith("business_calendar.")
    kind = "business_calendar" if calendar_event else "sla_policy"
    payload = (_CalendarEvent if calendar_event else _PolicyEvent).model_validate(event.payload)
    identifier = payload.calendar_id if isinstance(payload, _CalendarEvent) else payload.policy_id
    if (
        event.schema_version != 1
        or event.aggregate_type != kind
        or event.aggregate_id != identifier
    ):
        raise ValueError("Invalid SLA configuration envelope")
    if event.event_type == kind + ".created":
        if event.aggregate_version != 1 or "changed_fields" in event.payload:
            raise ValueError("Invalid configuration creation")
    elif event.event_type == kind + ".updated":
        allowed = (
            {"name", "active", "timezone", "windows", "holidays"}
            if calendar_event
            else {
                "name",
                "enabled",
                "calendar_id",
                "calendar_version",
                "first_response_minutes",
                "resolution_minutes",
                "approach_minutes",
                "pause_states",
            }
        )
        fields = payload.changed_fields.split(",") if payload.changed_fields else []
        if (
            event.aggregate_version < 2
            or not fields
            or fields != sorted(set(fields))
            or not set(fields) <= allowed
        ):
            raise ValueError("Invalid configuration changed fields")
    else:
        raise ValueError("Unsupported SLA configuration metadata")


def calendar(
    db: Session, queue_id: UUID, identifier: UUID, *, write: bool = False
) -> BusinessCalendar:
    query = select(BusinessCalendar).where(
        BusinessCalendar.id == identifier, BusinessCalendar.queue_id == queue_id
    )
    if write:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise identity.IdentityError(404, "not_found")
    return row


def policy(db: Session, queue_id: UUID, identifier: UUID, *, write: bool = False) -> SlaPolicy:
    query = select(SlaPolicy).where(SlaPolicy.id == identifier, SlaPolicy.queue_id == queue_id)
    if write:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise identity.IdentityError(404, "not_found")
    return row


def calendar_revision(db: Session, row: BusinessCalendar) -> BusinessCalendarRevision:
    revision = db.get(BusinessCalendarRevision, (row.id, row.version))
    if revision is None:
        raise identity.IdentityError(503, "sla_configuration_unavailable")
    return revision


def policy_revision(db: Session, row: SlaPolicy) -> SlaPolicyRevision:
    revision = db.get(SlaPolicyRevision, (row.id, row.version))
    if revision is None:
        raise identity.IdentityError(503, "sla_configuration_unavailable")
    return revision


def calendar_summary(
    db: Session, row: BusinessCalendar, permission: ConfigurationAccess
) -> CalendarSummary:
    revision = calendar_revision(db, row)
    return CalendarSummary(
        id=row.id,
        client_id=row.client_id,
        queue_id=row.queue_id,
        version=row.version,
        queue_version=permission.queue.version,
        name=revision.name,
        active=revision.active,
        timezone=revision.timezone,
        can_edit=permission.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def calendar_output(
    db: Session, row: BusinessCalendar, permission: ConfigurationAccess
) -> CalendarOutput:
    revision = calendar_revision(db, row)
    return CalendarOutput.model_validate(
        {
            **calendar_summary(db, row, permission).model_dump(),
            "windows": revision.windows,
            "holidays": revision.holidays,
            "tzif_sha256": revision.tzif_sha256,
        }
    )


def policy_output(db: Session, row: SlaPolicy, permission: ConfigurationAccess) -> PolicyOutput:
    revision = policy_revision(db, row)
    return PolicyOutput.model_validate(
        {
            "id": row.id,
            "client_id": row.client_id,
            "queue_id": row.queue_id,
            "category_id": row.category_id,
            "priority": row.priority,
            "version": row.version,
            "queue_version": permission.queue.version,
            "can_edit": permission.active,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            **{
                name: getattr(revision, name)
                for name in (
                    "enabled",
                    "name",
                    "calendar_id",
                    "calendar_version",
                    "first_response_minutes",
                    "resolution_minutes",
                    "approach_minutes",
                    "pause_states",
                    "authorizer_id",
                )
            },
        }
    )


def policy_calendar_output(db: Session, row: SlaPolicy) -> PolicyCalendarSnapshot:
    selected = policy_revision(db, row)
    frozen = db.get(BusinessCalendarRevision, (selected.calendar_id, selected.calendar_version))
    current = calendar(db, row.queue_id, selected.calendar_id)
    if frozen is None:
        raise identity.IdentityError(503, "sla_configuration_unavailable")
    return PolicyCalendarSnapshot.model_validate(
        {
            "policy_version": row.version,
            "calendar_id": frozen.calendar_id,
            "version": frozen.version,
            "name": frozen.name,
            "timezone": frozen.timezone,
            "windows": frozen.windows,
            "holidays": frozen.holidays,
            "calendar_active": calendar_revision(db, current).active,
        }
    )


def _event(
    db: Session,
    actor_id: UUID,
    row: BusinessCalendar | SlaPolicy,
    now: datetime,
    correlation_id: str,
    changed: list[str] | None = None,
) -> None:
    kind = "business_calendar" if isinstance(row, BusinessCalendar) else "sla_policy"
    identifier_name = "calendar_id" if isinstance(row, BusinessCalendar) else "policy_id"
    details = {
        identifier_name: str(row.id),
        "queue_id": str(row.queue_id),
        "client_id": str(row.client_id),
    }
    if changed is not None:
        details["changed_fields"] = ",".join(changed)
    identity.record_event(
        db,
        actor_id,
        row.id,
        kind + (".updated" if changed is not None else ".created"),
        now,
        correlation_id,
        row.version,
        aggregate_type=kind,
        details=details,
    )


def _zone(name: str) -> business_time.FrozenZone:
    try:
        return business_time.freeze_timezone(name)
    except ValueError:
        raise identity.IdentityError(422, "invalid_timezone") from None


def create_calendar(
    db: Session,
    actor_id: UUID,
    permission: ConfigurationAccess,
    body: CalendarCreate,
    correlation_id: str,
) -> BusinessCalendar:
    require_active(permission)
    zone = _zone(body.timezone)
    now = datetime.now(UTC)
    row = BusinessCalendar(
        client_id=permission.client.id,
        queue_id=permission.queue.id,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    values = body.model_dump(mode="json", exclude={"client_id"})
    db.add(
        BusinessCalendarRevision(
            calendar_id=row.id,
            client_id=row.client_id,
            queue_id=row.queue_id,
            version=1,
            **values,
            tzif=zone.tzif,
            tzif_sha256=zone.sha256,
            created_at=now,
        )
    )
    queue_registry.advance(permission.queue)
    _event(db, actor_id, row, now, correlation_id)
    return row


def patch_calendar(
    db: Session,
    actor_id: UUID,
    permission: ConfigurationAccess,
    row: BusinessCalendar,
    body: CalendarPatch,
    correlation_id: str,
) -> None:
    previous = calendar_revision(db, row)
    values = body.model_dump(mode="json", include=body.model_fields_set)
    # Explicit timezone intent refreshes installed rules. Omission preserves bytes.
    zone = _zone(body.timezone) if body.timezone is not None else None
    changed = sorted(name for name, value in values.items() if getattr(previous, name) != value)
    if zone is not None and zone.tzif != previous.tzif and "timezone" not in changed:
        changed = sorted([*changed, "timezone"])
    if not changed:
        return
    if any(name != "active" for name in changed) or body.active is True:
        require_active(permission)
    if row.version >= 2147483647:
        raise identity.IdentityError(409, "version_exhausted")
    now = datetime.now(UTC)
    row.version += 1
    row.updated_at = now
    db.add(
        BusinessCalendarRevision(
            calendar_id=row.id,
            client_id=row.client_id,
            queue_id=row.queue_id,
            version=row.version,
            **{
                name: values.get(name, getattr(previous, name))
                for name in ("active", "name", "timezone", "windows", "holidays")
            },
            tzif=zone.tzif if zone else previous.tzif,
            tzif_sha256=zone.sha256 if zone else previous.tzif_sha256,
            created_at=now,
        )
    )
    queue_registry.advance(permission.queue)
    _event(db, actor_id, row, now, correlation_id, changed)


def check_references(
    db: Session,
    client_id: UUID,
    queue_id: UUID,
    category_id: UUID | None,
    calendar_id: UUID,
    calendar_version: int,
) -> BusinessCalendarRevision:
    row = calendar(db, queue_id, calendar_id)
    if row.client_id != client_id:
        raise identity.IdentityError(404, "not_found")
    snapshot = db.get(BusinessCalendarRevision, (row.id, calendar_version))
    if snapshot is None:
        raise identity.IdentityError(404, "not_found")
    if not calendar_revision(db, row).active:
        raise identity.IdentityError(409, "sla_configuration_unavailable")
    if category_id is not None:
        category = queue_registry.scoped_category(db, queue_id, category_id)
        if not category.active:
            raise identity.IdentityError(409, "sla_configuration_unavailable")
    return snapshot


def select_revision(
    db: Session, client_id: UUID, queue_id: UUID, category_id: UUID | None, priority: str
) -> tuple[SlaPolicy, SlaPolicyRevision, BusinessCalendarRevision] | None:
    """Caller owns native ticket locks. Selection precedes reference eligibility."""
    result = db.execute(
        select(SlaPolicy, SlaPolicyRevision)
        .outerjoin(
            SlaPolicyRevision,
            (SlaPolicyRevision.policy_id == SlaPolicy.id)
            & (SlaPolicyRevision.version == SlaPolicy.version),
        )
        .where(
            SlaPolicy.client_id == client_id,
            SlaPolicy.queue_id == queue_id,
            or_(SlaPolicy.category_id == category_id, SlaPolicy.category_id.is_(None)),
            or_(SlaPolicy.priority == priority, SlaPolicy.priority.is_(None)),
            or_(SlaPolicyRevision.enabled.is_(True), SlaPolicyRevision.policy_id.is_(None)),
        )
        .order_by(SlaPolicy.category_id.is_not(None).desc(), SlaPolicy.priority.is_not(None).desc())
        .limit(1)
    ).one_or_none()
    if result is None:
        return None
    row, revision = result
    if revision is None:
        raise identity.IdentityError(503, "sla_configuration_unavailable")
    snapshot = check_references(
        db, client_id, queue_id, row.category_id, revision.calendar_id, revision.calendar_version
    )
    return row, revision, snapshot


def create_policy(
    db: Session,
    actor_id: UUID,
    permission: ConfigurationAccess,
    body: PolicyCreate,
    correlation_id: str,
) -> SlaPolicy:
    require_active(permission)
    check_references(
        db,
        permission.client.id,
        permission.queue.id,
        body.category_id,
        body.calendar_id,
        body.calendar_version,
    )
    existing = db.scalar(
        select(SlaPolicy.id).where(
            SlaPolicy.client_id == permission.client.id,
            SlaPolicy.queue_id == permission.queue.id,
            SlaPolicy.category_id == body.category_id,
            SlaPolicy.priority == body.priority,
        )
    )
    if existing is not None:
        raise identity.IdentityError(409, "sla_policy_exists")
    now = datetime.now(UTC)
    row = SlaPolicy(
        client_id=permission.client.id,
        queue_id=permission.queue.id,
        category_id=body.category_id,
        priority=body.priority,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    values = body.model_dump(exclude={"client_id", "category_id", "priority"})
    db.add(
        SlaPolicyRevision(
            policy_id=row.id,
            client_id=row.client_id,
            queue_id=row.queue_id,
            version=1,
            enabled=False,
            authorizer_id=actor_id,
            created_at=now,
            **values,
        )
    )
    queue_registry.advance(permission.queue)
    _event(db, actor_id, row, now, correlation_id)
    return row


def patch_policy(
    db: Session,
    actor_id: UUID,
    permission: ConfigurationAccess,
    row: SlaPolicy,
    body: PolicyPatch,
    correlation_id: str,
) -> None:
    previous = policy_revision(db, row)
    values = body.model_dump(exclude_unset=True)
    changed = sorted(name for name, value in values.items() if getattr(previous, name) != value)
    if not changed:
        return
    if any(name != "enabled" for name in changed) or body.enabled is True:
        require_active(permission)
        check_references(
            db,
            row.client_id,
            row.queue_id,
            row.category_id,
            body.calendar_id if body.calendar_id is not None else previous.calendar_id,
            body.calendar_version
            if body.calendar_version is not None
            else previous.calendar_version,
        )
    if row.version >= 2147483647:
        raise identity.IdentityError(409, "version_exhausted")
    now = datetime.now(UTC)
    row.version += 1
    row.updated_at = now
    db.add(
        SlaPolicyRevision(
            policy_id=row.id,
            client_id=row.client_id,
            queue_id=row.queue_id,
            version=row.version,
            **{
                name: values.get(name, getattr(previous, name))
                for name in (
                    "enabled",
                    "name",
                    "calendar_id",
                    "calendar_version",
                    "first_response_minutes",
                    "resolution_minutes",
                    "approach_minutes",
                    "pause_states",
                )
            },
            authorizer_id=actor_id,
            created_at=now,
        )
    )
    queue_registry.advance(permission.queue)
    _event(db, actor_id, row, now, correlation_id, changed)
