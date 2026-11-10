"""Provision synthetic browser-test identity only in the disposable test DB."""

import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from altvia.client_registry import create_client, set_client_access
from altvia.config import Settings
from altvia.database import make_engine
from altvia.management import (
    bootstrap_admin,
    create_user,
    hash_new_password,
    set_account_active,
)
from altvia.models import Project, SessionRecord, Team, User
from altvia.project_registry import set_project_access
from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

settings = Settings()
if (
    os.environ.get("ALTVIA_ALLOW_TEST_DB") != "1"
    or make_url(settings.database_url.get_secret_value()).database != "altvia_test"
):
    raise SystemExit("Browser fixtures require an explicitly enabled altvia_test database")

engine = make_engine(settings)
with Session(engine) as db, db.begin():
    if os.environ.get("ALTVIA_E2E_EXPIRE") == "1":
        email = os.environ["ALTVIA_E2E_EMAIL"]
        user_id = db.query(User.id).filter(User.email_normalized == email).scalar()
        if user_id is None:
            raise SystemExit("Browser fixture identity not found")
        db.execute(
            update(SessionRecord)
            .where(SessionRecord.user_id == user_id)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    elif os.environ.get("ALTVIA_E2E_DISABLE_ROSTER") == "1":
        set_account_active(db, "browser-roster-12@example.invalid", False)
    else:
        email = f"browser-{secrets.token_hex(8)}@example.invalid"
        password = secrets.token_urlsafe(30)
        db.add(
            User(
                email_normalized=email,
                display_name="Operacao Altvia - Validacao",
                password_hash=hash_new_password(password),
                active=True,
                auth_version=1,
                created_at=datetime.now(UTC),
            )
        )
        admin_email = f"browser-admin-{secrets.token_hex(8)}@example.invalid"
        admin_password = secrets.token_urlsafe(30)
        bootstrap_admin(db, admin_email, "Administrador - Validacao", admin_password)
        client_admin_email = f"browser-client-admin-{secrets.token_hex(8)}@example.invalid"
        client_admin_password = secrets.token_urlsafe(30)
        create_user(db, client_admin_email, "Gestor de clientes - Validacao", client_admin_password)
        project_admin_email = f"browser-project-admin-{secrets.token_hex(8)}@example.invalid"
        project_admin_password = secrets.token_urlsafe(30)
        create_user(
            db, project_admin_email, "Gestor de projetos - Validacao", project_admin_password
        )
        work_accounts = {}
        for kind, label in [
            ("MANAGER", "Gestor de tarefas"),
            ("AGENT", "Agente de tarefas"),
            ("READER", "Leitor de tarefas"),
            ("REVIEW_MANAGER", "Gestor de revisão"),
            ("REVIEW_AGENT", "Agente de revisão"),
        ]:
            work_email = f"browser-work-{kind.lower()}-{secrets.token_hex(8)}@example.invalid"
            work_password = secrets.token_urlsafe(30)
            create_user(db, work_email, label, work_password)
            work_accounts[kind] = (work_email, work_password)
        work_team = Team(name="Equipe de tarefas - Validacao")
        db.add(work_team)
        db.flush()
        work_project = Project(
            name="Projeto de tarefas - Validacao", scope_kind="internal", team_id=work_team.id
        )
        db.add(work_project)
        db.flush()
        for kind, role in [
            ("MANAGER", "project_manager"),
            ("AGENT", "agent"),
            ("READER", "viewer"),
            ("REVIEW_MANAGER", "project_manager"),
            ("REVIEW_AGENT", "agent"),
        ]:
            set_project_access(db, work_accounts[kind][0], work_project.id, role)
        roster_hash = hash_new_password(secrets.token_urlsafe(30))
        contact_accounts = {}
        for kind in ["MANAGER", "VIEWER", "HIDDEN"]:
            contact_email = f"browser-contact-{kind.lower()}-{secrets.token_hex(8)}@example.invalid"
            contact_password = secrets.token_urlsafe(30)
            person = create_user(db, contact_email, f"Contato {kind} - Validacao", contact_password)
            contact_accounts[kind] = (contact_email, contact_password, person.id)
        admin_actor = db.scalar(select(User).where(User.email_normalized == admin_email))
        contact_client = create_client(
            db,
            "Cliente de contatos - Validacao",
            contact_accounts["MANAGER"][2],
            admin_actor,
            "contact_fixture",
        )
        set_client_access(db, contact_accounts["VIEWER"][0], contact_client.id, "viewer")
        for index in range(12):
            db.add(
                Project(
                    name=f"Projeto de contato {index:02d}",
                    scope_kind="client",
                    client_id=contact_client.id,
                    team_id=work_team.id,
                )
            )
        for index in range(14):
            db.add(
                User(
                    email_normalized=f"browser-roster-{index:02d}@example.invalid",
                    display_name=f"Pessoa de validacao {index:02d}",
                    password_hash=roster_hash,
                    active=index != 13,
                    auth_version=1,
                    created_at=datetime.now(UTC),
                )
            )
        # Credentials never go to stdout, source control or browser traces.
        Path(".env.browser-session").write_text(
            f"ALTVIA_E2E_EMAIL={email}\nALTVIA_E2E_PASSWORD={password}\n"
            f"ALTVIA_E2E_ADMIN_EMAIL={admin_email}\nALTVIA_E2E_ADMIN_PASSWORD={admin_password}\n"
            f"ALTVIA_E2E_CLIENT_ADMIN_EMAIL={client_admin_email}\n"
            f"ALTVIA_E2E_CLIENT_ADMIN_PASSWORD={client_admin_password}\n"
            f"ALTVIA_E2E_PROJECT_ADMIN_EMAIL={project_admin_email}\n"
            f"ALTVIA_E2E_PROJECT_ADMIN_PASSWORD={project_admin_password}\n",
            encoding="utf-8",
        )
        with Path(".env.browser-session").open("a", encoding="utf-8") as target:
            target.write(f"ALTVIA_E2E_CONTACT_CLIENT_ID={contact_client.id}\n")
            for kind, (contact_email, contact_password, _) in contact_accounts.items():
                target.write(
                    f"ALTVIA_E2E_CONTACT_{kind}_EMAIL={contact_email}\nALTVIA_E2E_CONTACT_{kind}_PASSWORD={contact_password}\n"
                )
            target.write(f"ALTVIA_E2E_WORK_PROJECT_ID={work_project.id}\n")
            for kind, (work_email, work_password) in work_accounts.items():
                target.write(
                    f"ALTVIA_E2E_WORK_{kind}_EMAIL={work_email}\nALTVIA_E2E_WORK_{kind}_PASSWORD={work_password}\n"
                )
engine.dispose()
