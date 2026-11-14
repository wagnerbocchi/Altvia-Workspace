"""Versioned automation metadata and native domain provenance; no actor grants."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from altvia.automation_schemas import ExecutionError, ExecutionState
from altvia.models import AutomationEffect, AutomationExecution, AutomationRuleRevision, OutboxEvent

DOMAIN_EVENTS = frozenset({"work_item.created", "ticket.work_linked", "work_item.ticket_linked"})


class _RuleMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    actor_id: UUID
    actor_kind: Literal["user"]
    rule_id: UUID
    queue_id: UUID
    client_id: UUID
    changed_fields: str | None = Field(default=None, max_length=100)


class _ExecutionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    actor_id: UUID | None
    actor_kind: Literal["user", "management_command"]
    execution_id: UUID
    ticket_id: UUID
    client_id: UUID
    queue_id: UUID
    rule_id: UUID
    state: ExecutionState
    error_code: ExecutionError | None


def validate_private_event(event: OutboxEvent) -> None:
    if event.schema_version != 1 or event.aggregate_version < 1:
        raise ValueError("Invalid automation envelope")
    if event.event_type in {"automation.execution_changed", "automation.execution_retried"}:
        execution = _ExecutionMetadata.model_validate(event.payload)
        system = event.event_type == "automation.execution_changed"
        if (
            event.aggregate_type != "automation_execution"
            or event.aggregate_id != execution.execution_id
            or execution.actor_kind != ("management_command" if system else "user")
            or (execution.actor_id is None) != system
        ):
            raise ValueError("Invalid execution metadata")
        return
    payload = _RuleMetadata.model_validate(event.payload)
    if event.aggregate_type != "automation_rule" or event.aggregate_id != payload.rule_id:
        raise ValueError("Invalid rule metadata")
    if event.event_type == "automation.rule_created":
        if "changed_fields" in event.payload:
            raise ValueError("Unexpected creation fields")
    elif event.event_type == "automation.rule_updated":
        names = payload.changed_fields.split(",") if payload.changed_fields else []
        if (
            not names
            or len(set(names)) != len(names)
            or not set(names) <= {"enabled", "title", "priority", "ticket_statuses"}
        ):
            raise ValueError("Invalid updated fields")
    else:
        raise ValueError("Unsupported automation metadata")


class _Automated(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    actor_id: None
    actor_kind: Literal["automation"]
    authorizer_id: UUID
    execution_id: UUID
    project_id: UUID


class AutomatedCreated(_Automated):
    pass


class AutomatedLink(_Automated):
    ticket_id: UUID
    work_item_id: UUID
    client_id: UUID
    queue_id: UUID
    relation_type: Literal["related"]


def validate_domain_event(db: Session, event: OutboxEvent) -> AutomatedCreated | AutomatedLink:
    if (
        event.schema_version != 2
        or event.event_type not in DOMAIN_EVENTS
        or event.aggregate_version < 1
    ):
        raise ValueError("Invalid automated domain envelope")
    payload = (
        AutomatedCreated.model_validate(event.payload)
        if event.event_type == "work_item.created"
        else AutomatedLink.model_validate(event.payload)
    )
    effect = db.scalar(
        select(AutomationEffect).where(
            AutomationEffect.origin_execution_id == payload.execution_id,
        )
    )
    if effect is None or effect.mode != "created" or effect.project_id != payload.project_id:
        raise ValueError("Missing automated provenance")
    execution = db.get(AutomationExecution, payload.execution_id)
    assert execution is not None
    revision = db.get(AutomationRuleRevision, (execution.rule_id, execution.rule_version))
    if revision is None or revision.authorizer_id != payload.authorizer_id:
        raise ValueError("Wrong automated authorizer")
    if isinstance(payload, AutomatedCreated):
        if (
            event.aggregate_type != "work_item"
            or event.aggregate_id != effect.work_item_id
            or event.aggregate_version != 1
        ):
            raise ValueError("Wrong automated creation")
    else:
        ticket_side = event.event_type == "ticket.work_linked"
        expected_type, expected_id = (
            ("ticket", effect.ticket_id) if ticket_side else ("work_item", effect.work_item_id)
        )
        if (
            event.aggregate_type != expected_type
            or event.aggregate_id != expected_id
            or payload.ticket_id != effect.ticket_id
            or payload.work_item_id != effect.work_item_id
            or payload.client_id != effect.client_id
            or payload.queue_id != effect.queue_id
        ):
            raise ValueError("Wrong automated relationship")
    return payload
