from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Binding:
    role: str
    scope_kind: str
    scope_id: UUID | None


@dataclass(frozen=True)
class Resource:
    client_id: UUID | None
    project_id: UUID | None = None
    team_id: UUID | None = None
    queue_id: UUID | None = None
    owner_id: UUID | None = None
    assignee_ids: frozenset[UUID] = frozenset()


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    active: bool
    bindings: tuple[Binding, ...] = ()
    client_ids: frozenset[UUID] = frozenset()
    project_ids: frozenset[UUID] = frozenset()


def can(principal: Principal, action: str, resource: Resource) -> bool:
    if not principal.active:
        return False
    if resource.client_id is not None and resource.client_id not in principal.client_ids:
        return False
    work_actions = {"work.read", "work.create", "work.update", "work.transition", "work.comment"}
    ticket_actions = {
        "ticket.read",
        "ticket.create",
        "ticket.reply",
        "ticket.update",
        "ticket.transition",
        "ticket.claim",
        "ticket.assign",
    }
    read_actions = {"work.read", "ticket.read", "project.read", "client.read"}
    for binding in principal.bindings:
        matches = binding.scope_id is not None and binding.scope_id == {
            "client": resource.client_id,
            "project": resource.project_id,
            "team": resource.team_id,
            "queue": resource.queue_id,
        }.get(binding.scope_kind)
        if not matches:
            continue
        if binding.role == "operations_manager" and binding.scope_kind in {"client", "team"}:
            if action in work_actions | ticket_actions | read_actions:
                return True
        if binding.role == "project_manager" and binding.scope_kind == "project":
            if action in work_actions | {"project.read", "project.manage"}:
                return True
        if binding.role == "viewer" and action in read_actions:
            return True
        if binding.role != "agent":
            continue
        if binding.scope_kind == "project" and resource.project_id in principal.project_ids:
            if action in {"work.read", "work.create", "work.comment", "project.read"}:
                return True
            if action in {"work.update", "work.transition"} and (
                principal.user_id == resource.owner_id or principal.user_id in resource.assignee_ids
            ):
                return True
        if binding.scope_kind == "queue":
            if action in {"ticket.read", "ticket.create", "ticket.reply"}:
                return True
            if action in {"ticket.update", "ticket.transition"} and (
                principal.user_id in resource.assignee_ids
            ):
                return True
    return False
