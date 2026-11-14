"""Shared current authority and lock order for queue/customer configuration."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from altvia import client_registry, identity, queue_registry, tickets
from altvia.models import Client, TicketQueue


@dataclass(frozen=True)
class ConfigurationAccess:
    client: Client
    queue: TicketQueue
    team_active: bool

    @property
    def active(self) -> bool:
        return self.client.active and self.team_active and self.queue.active


def access(
    db: Session, actor_id: UUID, client_id: UUID, queue_id: UUID, *, write: bool = False
) -> ConfigurationAccess:
    client, client_role = client_registry.scoped_client(db, actor_id, client_id)
    queue, _, active, configuration_manager = queue_registry.scoped_queue(db, actor_id, queue_id)
    _, queue_role, _ = tickets.scoped_queue(db, actor_id, queue_id)
    if (
        client_role != "operations_manager"
        or queue_role != "operations_manager"
        or not configuration_manager
    ):
        raise identity.IdentityError(403, "forbidden")
    if write:
        # Same parent order as native ticket writes; never queue before client.
        client, _ = client_registry.scoped_client(db, actor_id, client_id, write=True)
        queue, _, active, _ = queue_registry.scoped_queue(db, actor_id, queue_id, write=True)
    return ConfigurationAccess(client, queue, active)


def require_active(permission: ConfigurationAccess) -> None:
    if not permission.client.active:
        raise identity.IdentityError(409, "client_inactive")
    queue_registry.require_active(permission.team_active, permission.queue.active)
