"""Native creation/history/event owner shared by HTTP and assignment execution."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from altvia import identity, work_items
from altvia.models import WorkAssignee, WorkExternalParticipant, WorkItem, WorkStatusHistory
from altvia.work_schemas import WorkCreate


def require_create(actor_id: UUID, permission: work_items.Access, body: WorkCreate) -> None:
    if not permission.manage and (
        body.owner_id != actor_id
        or body.assignee_ids
        or body.parent_id
        or body.external_participants
    ):
        raise identity.IdentityError(403, "forbidden")


def create_record(
    db: Session,
    actor_id: UUID,
    permission: work_items.Access,
    body: WorkCreate,
    *,
    now: datetime,
    correlation_id: str,
    origin: identity.AutomationOrigin | None = None,
) -> WorkItem:
    require_create(actor_id, permission, body)
    work_items.require_active(db, permission)
    contributors = work_items.validate_assignments(db, permission, body.owner_id, body.assignee_ids)
    item = WorkItem(
        id=uuid4(),
        project_id=body.project_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        work_type=body.work_type,
        status="in_progress" if body.work_type == "ongoing" else "todo",
        parent_id=body.parent_id,
        owner_id=body.owner_id,
        estimated_minutes=body.estimated_minutes,
        version=1,
        started_at=now if body.work_type == "ongoing" else None,
        created_at=now,
        updated_at=now,
    )
    work_items.validate_parent(db, item)
    work_items.set_due(db, item, body.due)
    item.assignees = [
        WorkAssignee(user_id=user, user=contributors[user]) for user in body.assignee_ids
    ]
    item.external_participants = [
        WorkExternalParticipant(unresolved_label=label) for label in body.external_participants
    ]
    db.add(item)
    db.flush()
    db.add(
        WorkStatusHistory(
            work_item_id=item.id,
            actor_id=actor_id,
            to_status=item.status,
            version=1,
            occurred_at=now,
        )
    )
    identity.record_event(
        db,
        actor_id,
        item.id,
        "work_item.created",
        datetime.now(UTC) if origin is None else now,
        correlation_id,
        item.version,
        aggregate_type="work_item",
        details={"project_id": str(item.project_id)},
        origin=origin,
    )
    return item
