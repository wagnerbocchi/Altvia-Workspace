"""A separately fenced assignment effect; activity delivery grants no authority."""

import random
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import Engine, func, or_, select, text, update
from sqlalchemy.orm import Session

from altvia import automation_rules, identity, ticket_work, tickets, work_creation, work_items
from altvia.activity import TicketEventPayload
from altvia.management import lock_identity_writes
from altvia.models import (
    AutomationEffect,
    AutomationExecution,
    AutomationRule,
    AutomationRuleRevision,
    OutboxEvent,
    Ticket,
    TicketWorkItem,
    User,
    WorkItem,
)
from altvia.work_schemas import WorkCreate

MAX_VERSION = 2147483647


class LostLease(Exception):
    """The complete effect transaction must roll back, including new history."""


class Triage(Exception):
    def __init__(self, code: str):
        self.code = code


def _clock(db: Session) -> datetime:
    value = db.scalar(select(func.clock_timestamp()))
    assert isinstance(value, datetime)
    return value


def _owned(db: Session, identifier: UUID, token: UUID) -> AutomationExecution | None:
    entry = db.scalar(
        select(AutomationExecution)
        .where(
            AutomationExecution.id == identifier,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        entry is None
        or entry.state != "processing"
        or entry.lease_token != token
        or entry.lease_until is None
        or entry.lease_until <= _clock(db)
    ):
        return None
    return entry


def _finish(
    db: Session,
    entry: AutomationExecution,
    token: UUID,
    state: str,
    code: str | None,
    correlation_id: str,
    *,
    next_attempt_at: datetime | None = None,
) -> None:
    # The final database-clock predicate also fences a lease expiring DURING a
    # slow mutation. Failure raises outside the transaction, rolling back ALL of it.
    now = _clock(db)
    values: dict[str, object] = dict(
        state=state,
        error_code=code,
        lease_token=None,
        lease_until=None,
        version=entry.version + 1,
        updated_at=now,
    )
    if next_attempt_at is not None:
        values["next_attempt_at"] = next_attempt_at
    version = db.scalar(
        update(AutomationExecution)
        .where(
            AutomationExecution.id == entry.id,
            AutomationExecution.state == "processing",
            AutomationExecution.lease_token == token,
            AutomationExecution.lease_until > func.clock_timestamp(),
            AutomationExecution.version < MAX_VERSION,
        )
        .values(**values)
        .returning(AutomationExecution.version)
        .execution_options(synchronize_session=False)
    )
    if version is None:
        raise LostLease
    identity.record_event(
        db,
        None,
        entry.id,
        "automation.execution_changed",
        now,
        correlation_id,
        version,
        aggregate_type="automation_execution",
        details={
            "execution_id": str(entry.id),
            "ticket_id": str(entry.ticket_id),
            "client_id": str(entry.client_id),
            "queue_id": str(entry.queue_id),
            "rule_id": str(entry.rule_id),
            "state": state,
            "error_code": code,
        },
    )


def claim_due(engine: Engine, now: datetime, limit: int = 20) -> list[tuple[UUID, UUID]]:
    if not 1 <= limit <= 100:
        raise ValueError("Invalid claim bound")
    with Session(engine) as db, db.begin():
        current = _clock(db)
        rows = db.scalars(
            select(AutomationExecution)
            .where(
                AutomationExecution.version < MAX_VERSION - 1,
                or_(
                    (AutomationExecution.state == "pending")
                    & (AutomationExecution.next_attempt_at <= current),
                    (AutomationExecution.state == "processing")
                    & (AutomationExecution.lease_until <= current),
                ),
            )
            .order_by(AutomationExecution.next_attempt_at, AutomationExecution.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        claimed = []
        for entry in rows:
            entry.version += 1
            entry.updated_at = current
            if entry.attempts >= 8:
                entry.state, entry.error_code = "dead", "attempts_exhausted"
                entry.lease_token = entry.lease_until = None
                continue
            token = uuid4()
            entry.state, entry.attempts = "processing", entry.attempts + 1
            entry.lease_token, entry.lease_until = token, current + timedelta(seconds=30)
            claimed.append((entry.id, token))
        return claimed


def publication_failed(engine: Engine, execution_id: UUID, token: UUID, now: datetime) -> bool:
    try:
        with Session(engine) as db, db.begin():
            entry = _owned(db, execution_id, token)
            if entry is None:
                return False
            delay = min(900, 5 * 2 ** max(0, entry.attempts - 1))
            retry_at = _clock(db) + timedelta(
                seconds=delay + random.SystemRandom().uniform(0, delay / 5)
            )
            _finish(
                db,
                entry,
                token,
                "dead" if entry.attempts >= 8 else "pending",
                "broker_unavailable",
                str(entry.id),
                next_attempt_at=retry_at,
            )
            return True
    except LostLease:
        return False


def _effect(
    db: Session,
    entry: AutomationExecution,
    revision: AutomationRuleRevision,
    ticket: Ticket,
    permission: tickets.Access,
    correlation_id: str,
) -> None:
    key = (entry.rule_id, entry.action_id, entry.ticket_id)
    if db.get(AutomationEffect, key) is not None:
        # A committed mapping is not permission to undo an intentional unlink,
        # transfer the old executor, or apply a newly configured default project.
        return
    tickets.require_update(ticket, permission, revision.authorizer_id)
    tickets.require_active(permission, ticket)
    if ticket.status not in revision.ticket_statuses:
        raise Triage("ticket_state_changed")
    project_id = permission.client.default_project_id
    if project_id is None:
        raise Triage("project_unavailable")
    try:
        project = work_items.access(
            db, revision.authorizer_id, project_id, write=True, metadata_only=True
        )
        if not project.manage or project.project.client_id != ticket.client_id:
            raise Triage("project_unavailable")
        work_items.require_active(db, project)
    except identity.IdentityError as error:
        raise Triage("project_unavailable") from error
    if (
        ticket.assignee_id is None
        or db.scalar(
            tickets.candidates(ticket.queue_id, ticket.client_id)
            .with_only_columns(User.id)
            .where(User.id == ticket.assignee_id)
        )
        is None
    ):
        raise Triage("assignee_unavailable")
    try:
        work_items.validate_assignments(db, project, ticket.assignee_id, [])
    except identity.IdentityError as error:
        raise Triage("assignee_unavailable") from error
    linked = list(
        db.scalars(
            select(TicketWorkItem.work_item_id)
            .join(
                WorkItem,
                WorkItem.id == TicketWorkItem.work_item_id,
            )
            .where(TicketWorkItem.ticket_id == ticket.id, WorkItem.project_id == project_id)
            .order_by(TicketWorkItem.work_item_id)
            .limit(2)
        )
    )
    if len(linked) > 1:
        raise Triage("existing_work_needs_review")
    current = _clock(db)
    origin = identity.AutomationOrigin(entry.id)
    if linked:
        try:
            item, project = work_items.scoped_work(
                db, revision.authorizer_id, linked[0], write=True, metadata_only=True
            )
            work_items.require_update(item, project, revision.authorizer_id)
        except identity.IdentityError as error:
            raise Triage("existing_work_needs_review") from error
        mode = "adopted"
    else:
        item = work_creation.create_record(
            db,
            revision.authorizer_id,
            project,
            WorkCreate(
                project_id=project_id,
                title=revision.title,
                priority=revision.priority,
                work_type="one_off",
                owner_id=ticket.assignee_id,
            ),
            now=current,
            correlation_id=correlation_id,
            origin=origin,
        )
        ticket_work.change_link(
            db,
            revision.authorizer_id,
            ticket_work.TicketWorkPair(ticket, permission, item, project),
            linked=True,
            now=current,
            correlation_id=correlation_id,
            origin=origin,
        )
        mode = "created"
    db.add(
        AutomationEffect(
            rule_id=entry.rule_id,
            action_id=entry.action_id,
            ticket_id=ticket.id,
            client_id=ticket.client_id,
            queue_id=ticket.queue_id,
            work_item_id=item.id,
            project_id=item.project_id,
            origin_execution_id=entry.id,
            mode=mode,
            created_at=current,
        )
    )
    db.flush()


def source_payload(db: Session, entry: AutomationExecution, ticket: Ticket) -> TicketEventPayload:
    event = db.execute(
        text("SELECT * FROM public.automation_assignment_sources WHERE execution_id=:id"),
        {"id": entry.id},
    ).one_or_none()
    if event is None:
        raise ValueError("Missing assignment source")
    payload = TicketEventPayload.model_validate(event.payload)
    if (
        event.event_type != "ticket.assigned"
        or event.unexpected_fields
        or event.schema_version != 1
        or event.aggregate_type != "ticket"
        or event.aggregate_id != ticket.id
        or payload.ticket_id != entry.ticket_id
        or payload.client_id != entry.client_id
        or payload.queue_id != entry.queue_id
        or payload.new_assignee_id is None
        or payload.new_assignee_id == payload.old_assignee_id
        or not payload.changed_fields
        or "assignee_id" not in payload.changed_fields.split(",")
        or event.aggregate_version < 1
        or event.aggregate_version > ticket.version
    ):
        raise ValueError("Invalid assignment source")
    return payload


def require_retry(
    db: Session, entry: AutomationExecution, ticket: Ticket, permission: tickets.Access
) -> None:
    if entry.state not in {"triage", "dead"}:
        raise identity.IdentityError(409, "execution_not_retryable")
    rule = db.get(AutomationRule, entry.rule_id)
    assert rule is not None
    revision = db.get(AutomationRuleRevision, (entry.rule_id, entry.rule_version))
    assert revision is not None
    if (
        not automation_rules.current_revision(db, rule).enabled
        or entry.rule_version <= rule.cancelled_through_version
    ):
        raise identity.IdentityError(409, "rule_disabled")
    tickets.require_active(permission, ticket)
    try:
        payload = source_payload(db, entry, ticket)
    except (ValueError, ValidationError):
        raise identity.IdentityError(409, "invalid_event") from None
    if payload.new_assignee_id != ticket.assignee_id:
        raise identity.IdentityError(409, "source_superseded")
    if ticket.status not in revision.ticket_statuses:
        raise identity.IdentityError(409, "ticket_state_changed")
    if db.get(AutomationEffect, (entry.rule_id, entry.action_id, entry.ticket_id)) is not None:
        raise identity.IdentityError(409, "execution_not_retryable")
    if entry.version >= MAX_VERSION - 2:
        raise identity.IdentityError(409, "version_exhausted")


def retry(db: Session, actor_id: UUID, entry: AutomationExecution, correlation_id: str) -> None:
    now = _clock(db)
    entry.state, entry.attempts, entry.error_code = "pending", 0, None
    entry.lease_token = entry.lease_until = None
    entry.version += 1
    entry.updated_at = entry.next_attempt_at = now
    identity.record_event(
        db,
        actor_id,
        entry.id,
        "automation.execution_retried",
        now,
        correlation_id,
        entry.version,
        aggregate_type="automation_execution",
        details={
            "execution_id": str(entry.id),
            "ticket_id": str(entry.ticket_id),
            "client_id": str(entry.client_id),
            "queue_id": str(entry.queue_id),
            "rule_id": str(entry.rule_id),
            "state": entry.state,
            "error_code": None,
        },
    )


def consume(engine: Engine, execution_id: UUID, token: UUID, now: datetime) -> bool:
    try:
        with Session(engine) as db, db.begin():
            lock_identity_writes(db)
            pointer = db.get(AutomationExecution, execution_id)
            if pointer is None:
                return False
            rule = db.get(AutomationRule, pointer.rule_id)
            assert rule is not None
            revision = db.get(AutomationRuleRevision, (pointer.rule_id, pointer.rule_version))
            assert revision is not None
            current_revision = automation_rules.current_revision(db, rule)
            # Cancellation/denial paths acquire no later domain lock, so their
            # private rule/execution locks cannot invert ticket-before-graph.
            cancelled = (
                not current_revision.enabled
                or pointer.rule_version <= rule.cancelled_through_version
            )
            active = db.scalar(select(User.active).where(User.id == revision.authorizer_id))
            denied = None
            ticket = permission = None
            if not cancelled and active:
                try:
                    ticket, permission = tickets.scoped_ticket(
                        db,
                        revision.authorizer_id,
                        pointer.ticket_id,
                        write=True,
                        metadata_only=True,
                    )
                    automation_rules.access(
                        db, revision.authorizer_id, pointer.client_id, pointer.queue_id
                    )
                except identity.IdentityError:
                    denied = "authorization_lost"
            elif not active:
                denied = "authorization_lost"
            db.scalar(select(AutomationRule).where(AutomationRule.id == rule.id).with_for_update())
            entry = _owned(db, execution_id, token)
            if entry is None:
                return False
            if cancelled:
                _finish(db, entry, token, "cancelled", "rule_disabled", str(entry.id))
                return False
            if denied:
                _finish(db, entry, token, "triage", denied, str(entry.id))
                return False
            assert ticket is not None and permission is not None
            event = db.get(OutboxEvent, entry.source_event_id)
            try:
                payload = source_payload(db, entry, ticket)
            except (ValueError, ValidationError):
                _finish(db, entry, token, "dead", "invalid_event", str(entry.id))
                return False
            assert event is not None
            if payload.new_assignee_id != ticket.assignee_id:
                _finish(db, entry, token, "superseded", "source_superseded", event.correlation_id)
                return False
            try:
                with db.begin_nested():
                    _effect(db, entry, revision, ticket, permission, event.correlation_id)
                    _finish(db, entry, token, "succeeded", None, event.correlation_id)
            except (Triage, identity.IdentityError) as error:
                code = error.code if isinstance(error, Triage) else "ticket_state_changed"
                _finish(db, entry, token, "triage", code, event.correlation_id)
                return False
            return True
    except LostLease:
        return False
