"""Client-owned external identities; no account or permission side effects."""

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from altvia import client_registry, identity, project_registry
from altvia.models import Client, ClientContact, Project, Team

ATOM = r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+"
LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
MAILBOX = re.compile(rf"{ATOM}(?:\.{ATOM})*@{LABEL}(?:\.{LABEL})+", re.ASCII)


def normalize_contact_email(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValueError("Invalid contact email")
    normalized = identity.normalize_email(value)
    if MAILBOX.fullmatch(normalized) is None or len(normalized.split("@")[0]) > 64:
        raise ValueError("Invalid contact email")
    return normalized


def scoped_contact(
    db: Session, client_id: UUID, contact_id: UUID, *, write: bool = False
) -> ClientContact:
    query = select(ClientContact).where(
        ClientContact.client_id == client_id, ClientContact.id == contact_id
    )
    if write:
        query = query.with_for_update()
    row = db.scalar(query)
    if row is None:
        raise identity.IdentityError(404, "not_found")
    return row


def unique_email(db: Session, client_id: UUID, email: str, except_id: UUID | None = None) -> None:
    query = select(ClientContact.id).where(
        ClientContact.client_id == client_id, ClientContact.email_normalized == email
    )
    if except_id is not None:
        query = query.where(ClientContact.id != except_id)
    if db.scalar(query) is not None:
        raise identity.IdentityError(409, "contact_email_exists")


def contact_event(
    db: Session,
    client: Client,
    contact: ClientContact,
    actor_id: UUID,
    correlation_id: str,
    changes: list[str] | None = None,
) -> None:
    client_registry.advance(client)
    details = {"contact_id": str(contact.id)}
    if changes is not None:
        details["changed_fields"] = ",".join(changes)
    identity.record_event(
        db,
        actor_id,
        client.id,
        "client.contact_created" if changes is None else "client.contact_updated",
        datetime.now(UTC),
        correlation_id,
        client.version,
        aggregate_type="client",
        details=details,
    )


def require_active(client: Client) -> None:
    if not client.active:
        raise identity.IdentityError(409, "client_inactive")


def eligible_default(db: Session, actor_id: UUID, client: Client, project_id: UUID) -> None:
    require_active(client)
    query = (
        project_registry.visible_projects(actor_id)
        .join(Team, Team.id == Project.team_id)
        .where(
            Project.id == project_id,
            Project.client_id == client.id,
            Project.active.is_(True),
            Team.active.is_(True),
        )
    )
    if db.execute(query).one_or_none() is None:
        raise identity.IdentityError(422, "invalid_default_project")
