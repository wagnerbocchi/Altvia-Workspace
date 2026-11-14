"""Dedicated synthetic assignment actors; never populated outside guarded test DB."""

import os
import secrets
from datetime import UTC, datetime

from altvia.client_registry import create_client
from altvia.identity import login
from altvia.management import create_user, set_team_role
from altvia.models import (
    ClientAccessGrant,
    ClientContact,
    Project,
    RoleBinding,
    Team,
    TicketQueue,
    User,
)
from altvia.project_registry import set_project_access
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session


def automation_fixture(engine: Engine, admin_email: str) -> dict[str, str]:
    if os.environ.get("ALTVIA_ALLOW_TEST_DB") != "1" or engine.url.database != "altvia_test":
        raise ValueError("Automation fixtures require an explicitly disposable test DB")
    accounts = {}
    with Session(engine) as db, db.begin():
        administrator = db.scalars(select(User).where(User.email_normalized == admin_email)).one()
        for kind in ["MANAGER", "AGENT", "WORK_ONLY"]:
            email = f"browser-automation-{kind.lower()}-{secrets.token_hex(8)}@example.invalid"
            password = secrets.token_urlsafe(30)
            person = create_user(db, email, "Automacao " + kind, password)
            accounts[kind] = (email, password, person.id)
        client = create_client(
            db,
            "Cliente de automacao - Validacao",
            accounts["MANAGER"][2],
            administrator,
            "automation_browser_fixture",
        )
        team = Team(name="Equipe de automacao - Validacao")
        db.add(team)
        db.flush()
        project = Project(
            name="Projeto de automacao - Validacao",
            scope_kind="client",
            client_id=client.id,
            team_id=team.id,
        )
        queue = TicketQueue(
            name="Fila de automacao - Validacao",
            team_id=team.id,
            allow_manual_close=True,
            allow_reopen=True,
        )
        requester = ClientContact(
            client_id=client.id,
            display_name="Solicitante de automacao",
            email_normalized="automation-requester@example.invalid",
        )
        db.add_all([project, queue, requester])
        db.flush()
        client.default_project_id = project.id
        set_team_role(db, accounts["MANAGER"][0], team.id, "operations_manager", True)
        for kind, (email, _, identifier) in accounts.items():
            if kind != "MANAGER":
                db.add(
                    ClientAccessGrant(
                        user_id=identifier, client_id=client.id, created_at=datetime.now(UTC)
                    )
                )
                db.flush()
            set_project_access(db, email, project.id, "agent")
            if kind != "WORK_ONLY":
                db.add(
                    RoleBinding(
                        user_id=identifier,
                        scope_kind="queue",
                        queue_id=queue.id,
                        role_name="operations_manager" if kind == "MANAGER" else "agent",
                    )
                )
        result = {
            "CLIENT": str(client.id),
            "QUEUE": str(queue.id),
            "PROJECT": str(project.id),
            "REQUESTER": str(requester.id),
            "AGENT_ID": str(accounts["AGENT"][2]),
        }
    for kind, (email, password, _) in accounts.items():
        with Session(engine) as db:
            _, _, token = login(db, email, password, "automation-fixture", "automation_fixture")
        result[kind + "_SESSION"] = token
    return {"ALTVIA_E2E_AUTOMATION_" + key: value for key, value in result.items()}
