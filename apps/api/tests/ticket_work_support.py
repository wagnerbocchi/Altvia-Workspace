"""Real same-client endpoints shared by ticket/work relationship tests."""

from dataclasses import dataclass
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_project_registry import project
from test_team_api import sign_in
from test_tickets import setup, ticket
from test_work_items import create_work


@dataclass(frozen=True)
class LinkContext:
    ticket_id: UUID
    work_item_id: UUID
    project_id: UUID
    client_id: UUID
    queue_id: UUID


def make_link_context(client: TestClient, db_engine: Engine, seeded_user: UUID) -> LinkContext:
    refs = setup(client, db_engine, seeded_user)
    ticket_id = UUID(ticket(client, refs).rsplit("/", 1)[1])
    with db_engine.connect() as connection:
        team_id = connection.scalar(
            text("SELECT team_id FROM ticket_queues WHERE id=:id"), {"id": refs["queue_id"]}
        )
    sign_in(client, "admin@example.test")
    response = project(client, seeded_user, str(team_id), customer=refs["client_id"])
    assert response.status_code == 201, response.text
    project_id = UUID(response.json()["project_id"])
    sign_in(client, "employee@example.test")
    response = create_work(client, str(project_id))
    assert response.status_code == 201, response.text
    return LinkContext(
        ticket_id=ticket_id,
        work_item_id=UUID(response.json()["work_item_id"]),
        project_id=project_id,
        client_id=UUID(refs["client_id"]),
        queue_id=UUID(refs["queue_id"]),
    )
