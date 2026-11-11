from dataclasses import dataclass
from uuid import UUID

TEAM_READ_ROLES = frozenset({"viewer", "operations_manager"})


@dataclass(frozen=True)
class Binding:
    role: str
    scope_kind: str
    scope_id: UUID | None
    note_access: str = "none"


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
    if action == "team.read":
        if resource.client_id is not None or resource.team_id is None:
            return False
        return any(
            (
                binding.role == "platform_admin"
                and binding.scope_kind == "global"
                and binding.scope_id is None
            )
            or (
                binding.role in TEAM_READ_ROLES
                and binding.scope_kind == "team"
                and binding.scope_id == resource.team_id
            )
            for binding in principal.bindings
        )
    if resource.client_id is not None and resource.client_id not in principal.client_ids:
        return False
    if action in {"note.read", "note.write"}:
        return can(principal, "ticket.read", resource) and any(
            binding.scope_kind == "queue"
            and binding.scope_id == resource.queue_id
            and binding.role in {"agent", "operations_manager"}
            and (
                binding.note_access == "write"
                or (action == "note.read" and binding.note_access == "read")
            )
            for binding in principal.bindings
        )
    if action in {"project.read", "project.manage"}:
        if resource.project_id is None:
            return False
        for binding in principal.bindings:
            if (
                resource.client_id is not None
                and binding.scope_kind == "client"
                and binding.scope_id == resource.client_id
            ):
                if binding.role == "operations_manager" or (
                    binding.role == "viewer" and action == "project.read"
                ):
                    return True
            if (
                binding.scope_kind == "project"
                and binding.scope_id == resource.project_id
                and resource.project_id in principal.project_ids
            ):
                if binding.role == "project_manager" or (
                    binding.role in {"viewer", "agent"} and action == "project.read"
                ):
                    return True
        return False
    work_actions = {"work.read", "work.create", "work.update", "work.transition", "work.comment"}
    if action in work_actions:
        if not can(principal, "project.read", resource):
            return False
        if action == "work.read" or can(principal, "project.manage", resource):
            return True
        agent = any(
            binding.scope_kind == "project"
            and binding.scope_id == resource.project_id
            and binding.role == "agent"
            and resource.project_id in principal.project_ids
            for binding in principal.bindings
        )
        return agent and (
            action in {"work.create", "work.comment"}
            or (
                principal.user_id == resource.owner_id or principal.user_id in resource.assignee_ids
            )
        )
    ticket_actions = {
        "ticket.read",
        "ticket.create",
        "ticket.reply",
        "ticket.update",
        "ticket.transition",
        "ticket.claim",
        "ticket.assign",
    }
    if action in ticket_actions:
        if resource.client_id is None or resource.queue_id is None:
            return False
        for binding in principal.bindings:
            if binding.scope_kind != "queue" or binding.scope_id != resource.queue_id:
                continue
            if binding.role == "operations_manager":
                return True
            if binding.role == "viewer" and action == "ticket.read":
                return True
            if binding.role == "agent":
                if action in {"ticket.read", "ticket.create", "ticket.reply", "ticket.claim"}:
                    return True
                if action in {"ticket.update", "ticket.transition"}:
                    return principal.user_id in resource.assignee_ids
        return False
    if action in {"client.read", "client.manage"} and resource.client_id is not None:
        return any(
            binding.scope_kind == "client"
            and binding.scope_id == resource.client_id
            and (
                binding.role == "operations_manager"
                or (binding.role == "viewer" and action == "client.read")
            )
            for binding in principal.bindings
        )
    return False
