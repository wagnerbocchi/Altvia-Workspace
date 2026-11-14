"""Native assignment configuration and transactional source staging ownership."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from altvia import identity, queue_registry
from altvia.automation_schemas import RuleCreate, RuleOutput, RulePatch
from altvia.models import (
    AutomationExecution,
    AutomationRule,
    AutomationRuleRevision,
    OutboxEvent,
    Ticket,
)
from altvia.queue_client_configuration import ConfigurationAccess as RuleAccess
from altvia.queue_client_configuration import access as access
from altvia.queue_client_configuration import require_active as require_active


def current_revision(db: Session, rule: AutomationRule) -> AutomationRuleRevision:
    revision = db.get(AutomationRuleRevision, (rule.id, rule.version))
    if revision is None:
        raise identity.IdentityError(503, "automation_configuration_unavailable")
    return revision


def output(
    rule: AutomationRule, revision: AutomationRuleRevision, queue_version: int
) -> RuleOutput:
    return RuleOutput(
        id=rule.id,
        queue_id=rule.queue_id,
        client_id=rule.client_id,
        action_id=rule.action_id,
        version=rule.version,
        queue_version=queue_version,
        enabled=revision.enabled,
        title=revision.title,
        priority=revision.priority,
        ticket_statuses=revision.ticket_statuses,
        authorizer_id=revision.authorizer_id,
        cancelled_through_version=rule.cancelled_through_version,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _event(
    db: Session,
    actor_id: UUID,
    rule: AutomationRule,
    now: datetime,
    correlation_id: str,
    changed: list[str] | None = None,
) -> None:
    details = {
        "rule_id": str(rule.id),
        "queue_id": str(rule.queue_id),
        "client_id": str(rule.client_id),
    }
    if changed is not None:
        details["changed_fields"] = ",".join(changed)
    identity.record_event(
        db,
        actor_id,
        rule.id,
        "automation.rule_updated" if changed is not None else "automation.rule_created",
        now,
        correlation_id,
        rule.version,
        aggregate_type="automation_rule",
        details=details,
    )


def create(
    db: Session, actor_id: UUID, permission: RuleAccess, body: RuleCreate, correlation_id: str
) -> AutomationRule:
    require_active(permission)
    if (
        db.scalar(
            select(AutomationRule.id).where(
                AutomationRule.client_id == permission.client.id,
                AutomationRule.queue_id == permission.queue.id,
            )
        )
        is not None
    ):
        raise identity.IdentityError(409, "automation_rule_exists")
    now = datetime.now(UTC)
    rule = AutomationRule(
        client_id=permission.client.id,
        queue_id=permission.queue.id,
        version=1,
        cancelled_through_version=0,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    db.flush()
    db.add(
        AutomationRuleRevision(
            rule_id=rule.id,
            version=1,
            enabled=False,
            title=body.title,
            priority=body.priority,
            ticket_statuses=body.ticket_statuses,
            authorizer_id=actor_id,
            created_at=now,
        )
    )
    queue_registry.advance(permission.queue)
    _event(db, actor_id, rule, now, correlation_id)
    return rule


def patch(
    db: Session,
    actor_id: UUID,
    permission: RuleAccess,
    rule: AutomationRule,
    body: RulePatch,
    correlation_id: str,
) -> None:
    previous = current_revision(db, rule)
    values = body.model_dump(exclude_unset=True)
    changed = sorted(name for name, value in values.items() if getattr(previous, name) != value)
    if not changed:
        return
    if any(name != "enabled" for name in changed) or body.enabled is True:
        require_active(permission)
    if rule.version >= 2147483647:
        raise identity.IdentityError(409, "version_exhausted")
    now = datetime.now(UTC)
    rule.version += 1
    rule.updated_at = now
    if "enabled" in changed and body.enabled is False:
        rule.cancelled_through_version = rule.version
    db.add(
        AutomationRuleRevision(
            rule_id=rule.id,
            version=rule.version,
            enabled=values.get("enabled", previous.enabled),
            title=values.get("title", previous.title),
            priority=values.get("priority", previous.priority),
            ticket_statuses=values.get("ticket_statuses", previous.ticket_statuses),
            authorizer_id=actor_id,
            created_at=now,
        )
    )
    queue_registry.advance(permission.queue)
    _event(db, actor_id, rule, now, correlation_id, changed)


def stage_assignment(db: Session, event: OutboxEvent, ticket: Ticket) -> None:
    rule = db.scalar(
        select(AutomationRule).where(
            AutomationRule.client_id == ticket.client_id,
            AutomationRule.queue_id == ticket.queue_id,
        )
    )
    if rule is None:
        return
    revision = current_revision(db, rule)
    if not revision.enabled:
        return
    # Trusted producer still proves its exact native identity before staging.
    from altvia.activity import TicketEventPayload

    payload = TicketEventPayload.model_validate(event.payload)
    if (
        event.event_type != "ticket.assigned"
        or event.schema_version != 1
        or event.aggregate_type != "ticket"
        or event.aggregate_id != ticket.id
        or payload.ticket_id != ticket.id
        or payload.client_id != ticket.client_id
        or payload.queue_id != ticket.queue_id
        or payload.new_assignee_id != ticket.assignee_id
        or payload.new_assignee_id is None
    ):
        raise identity.IdentityError(503, "invalid_assignment_source")
    db.add(
        AutomationExecution(
            rule_id=rule.id,
            action_id=rule.action_id,
            rule_version=revision.version,
            client_id=ticket.client_id,
            queue_id=ticket.queue_id,
            ticket_id=ticket.id,
            source_event_id=event.event_id,
        )
    )
