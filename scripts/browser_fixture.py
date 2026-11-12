"""Provision synthetic browser-test identity only in the disposable test DB."""

import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from altvia.client_registry import create_client, set_client_access
from altvia.config import Settings
from altvia.database import make_engine
from altvia.identity import login
from altvia.management import (
    bootstrap_admin,
    create_user,
    hash_new_password,
    set_account_active,
    set_team_role,
)
from altvia.models import (
    Client,
    ClientAccessGrant,
    ClientContact,
    Project,
    RoleBinding,
    SessionRecord,
    Team,
    TicketCategory,
    TicketQueue,
    User,
)
from altvia.project_registry import set_project_access
from sqlalchemy import select, text, update
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
        queue_team = Team(name="Equipe de atendimento - Validacao")
        db.add(queue_team)
        db.flush()
        for kind, role in [("MANAGER", "operations_manager"), ("READER", "viewer")]:
            set_team_role(db, work_accounts[kind][0], queue_team.id, role, True)
        fixture_queues = [
            TicketQueue(team_id=queue_team.id, name=f"Fila de validacao {number:02}")
            for number in range(1, 13)
        ]
        db.add_all(fixture_queues)
        db.flush()
        queue_access_team = Team(name="Equipe de acesso a filas - Validacao")
        db.add(queue_access_team)
        db.flush()
        queue_access_queue = TicketQueue(
            team_id=queue_access_team.id, name="Fila de acessos - Validacao"
        )
        db.add(queue_access_queue)
        db.flush()
        queue_access_accounts = {}
        for kind in ["MANAGER", "VIEWER", "AGENT", "HIDDEN", "SELF", "TARGET"]:
            account_email = f"browser-queue-{kind.lower()}-{secrets.token_hex(8)}@example.invalid"
            account_password = secrets.token_urlsafe(30)
            person = create_user(db, account_email, f"Fila {kind} - Validacao", account_password)
            queue_access_accounts[kind] = (account_email, account_password, person.id)
            if kind in {"MANAGER", "SELF", "VIEWER"}:
                set_team_role(
                    db,
                    account_email,
                    queue_access_team.id,
                    "viewer" if kind == "VIEWER" else "operations_manager",
                    True,
                )
            if kind in {"AGENT", "SELF"}:
                db.add(
                    RoleBinding(
                        user_id=person.id,
                        role_name="agent",
                        scope_kind="queue",
                        queue_id=queue_access_queue.id,
                    )
                )
        external_work_project = Project(
            name="Projeto de envolvidos externos - Validacao",
            scope_kind="internal",
            team_id=work_team.id,
        )
        db.add(external_work_project)
        ticket_client = Client(
            name="Cliente de chamados - Validacao",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        ticket_queue = TicketQueue(
            team_id=queue_access_team.id, name="Atendimento manual - Validacao"
        )
        db.add_all([ticket_client, ticket_queue])
        db.flush()
        db.execute(text("ALTER SEQUENCE tickets_number_seq RESTART WITH 9007199254740993"))
        ticket_contact = ClientContact(
            client_id=ticket_client.id,
            display_name="Solicitante de validacao",
            email_normalized="ticket-requester@example.invalid",
        )
        ticket_category = TicketCategory(queue_id=ticket_queue.id, name="Infraestrutura")
        db.add_all([ticket_contact, ticket_category])
        db.add_all(
            [
                ClientContact(
                    client_id=ticket_client.id,
                    display_name=f"Solicitante extra {number:02}",
                    email_normalized=f"ticket-extra-{number}@example.invalid",
                )
                for number in range(12)
            ]
        )
        ticket_accounts = {}
        for kind, role in [
            ("MANAGER", "operations_manager"),
            ("AGENT", "agent"),
            ("VIEWER", "viewer"),
            ("CONFIG", None),
        ]:
            account_email = f"browser-ticket-{kind.lower()}-{secrets.token_hex(8)}@example.invalid"
            account_password = secrets.token_urlsafe(30)
            person = create_user(db, account_email, f"Chamados {kind}", account_password)
            ticket_accounts[kind] = (account_email, account_password, person.id)
            db.add(
                ClientAccessGrant(
                    user_id=person.id, client_id=ticket_client.id, created_at=datetime.now(UTC)
                )
            )
            if role:
                db.add(
                    RoleBinding(
                        user_id=person.id,
                        role_name=role,
                        scope_kind="queue",
                        queue_id=ticket_queue.id,
                    )
                )
            else:
                set_team_role(db, account_email, queue_access_team.id, "operations_manager", True)
        db.flush()
        for kind, role in [
            ("MANAGER", "project_manager"),
            ("AGENT", "agent"),
            ("READER", "viewer"),
        ]:
            set_project_access(db, work_accounts[kind][0], external_work_project.id, role)
        note_queue = TicketQueue(team_id=queue_access_team.id, name="Notas internas - Validacao")
        db.add(note_queue)
        db.flush()
        if os.environ.get("ALTVIA_SMTP_ACCOUNTS_FILE"):
            from altvia.mail_participants import register_sender
            from altvia.mail_settings import load_accounts
            from altvia.models import MailboxSource

            for account in load_accounts(Path(os.environ["ALTVIA_SMTP_ACCOUNTS_FILE"])).values():
                if account.host != "127.0.0.1" or account.from_email != "support@example.invalid":
                    raise SystemExit("Synthetic local relay required")
                db.add(
                    MailboxSource(
                        id=account.source_id, source_key="browser-synthetic", queue_id=note_queue.id
                    )
                )
                db.flush()
                register_sender(db, account)
        note_accounts = {}
        for kind, role, access in [
            ("AUTHOR", "operations_manager", "write"),
            ("READER", "agent", "read"),
            ("NONE", "operations_manager", "none"),
            ("VIEWER", "viewer", "none"),
            ("CONFIG", None, "none"),
            ("DELEGATE", "agent", "none"),
        ]:
            account_email = f"browser-note-{kind.lower()}-{secrets.token_hex(8)}@example.invalid"
            account_password = secrets.token_urlsafe(30)
            person = create_user(db, account_email, f"Notas {kind}", account_password)
            note_accounts[kind] = (account_email, account_password, person.id)
            db.add(
                ClientAccessGrant(
                    user_id=person.id, client_id=ticket_client.id, created_at=datetime.now(UTC)
                )
            )
            if role:
                db.add(
                    RoleBinding(
                        user_id=person.id,
                        scope_kind="queue",
                        queue_id=note_queue.id,
                        role_name=role,
                        note_access=access,
                    )
                )
            else:
                set_team_role(db, account_email, queue_access_team.id, "operations_manager", True)
        member_accounts = {}
        for kind in ["MANAGER", "VIEWER", "HIDDEN", "SELF", "TARGET"]:
            member_email = f"browser-member-{kind.lower()}-{secrets.token_hex(8)}@example.invalid"
            member_password = secrets.token_urlsafe(30)
            person = create_user(db, member_email, f"Membro {kind} - Validacao", member_password)
            member_accounts[kind] = (member_email, member_password, person.id)
        member_project = Project(
            name="Projeto de membros - Validacao", scope_kind="internal", team_id=work_team.id
        )
        db.add(member_project)
        db.flush()
        for kind, role in [
            ("MANAGER", "project_manager"),
            ("VIEWER", "viewer"),
            ("SELF", "project_manager"),
        ]:
            set_project_access(db, member_accounts[kind][0], member_project.id, role)
        contact_accounts = {}
        milestone_accounts = {
            "MANAGER": work_accounts["MANAGER"],
            "READER": work_accounts["READER"],
            "HIDDEN": member_accounts["HIDDEN"][:2],
        }
        milestone_project = Project(
            name="Projeto de marcos - Validacao", scope_kind="internal", team_id=work_team.id
        )
        db.add(milestone_project)
        db.flush()
        for kind, role in [("MANAGER", "project_manager"), ("READER", "viewer")]:
            set_project_access(db, milestone_accounts[kind][0], milestone_project.id, role)
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
            target.write(f"ALTVIA_E2E_MEMBER_PROJECT_ID={member_project.id}\n")
            target.write(f"ALTVIA_E2E_MILESTONE_PROJECT_ID={milestone_project.id}\n")
            for kind, (member_email, member_password, member_id) in member_accounts.items():
                target.write(
                    f"ALTVIA_E2E_MEMBER_{kind}_EMAIL={member_email}\n"
                    f"ALTVIA_E2E_MEMBER_{kind}_PASSWORD={member_password}\n"
                    f"ALTVIA_E2E_MEMBER_{kind}_ID={member_id}\n"
                )
            target.write(f"ALTVIA_E2E_CONTACT_CLIENT_ID={contact_client.id}\n")
            for kind, (contact_email, contact_password, _) in contact_accounts.items():
                target.write(
                    f"ALTVIA_E2E_CONTACT_{kind}_EMAIL={contact_email}\nALTVIA_E2E_CONTACT_{kind}_PASSWORD={contact_password}\n"
                )
            target.write(f"ALTVIA_E2E_WORK_PROJECT_ID={work_project.id}\n")
            target.write(f"ALTVIA_E2E_QUEUE_TEAM_ID={queue_team.id}\n")
            target.write(f"ALTVIA_E2E_QUEUE_ID={fixture_queues[0].id}\n")
            target.write(f"ALTVIA_E2E_QUEUE_ACCESS_ID={queue_access_queue.id}\n")
            target.write(f"ALTVIA_E2E_NOTE_QUEUE_ID={note_queue.id}\n")
            target.write(
                f"ALTVIA_E2E_TICKET_QUEUE_ID={ticket_queue.id}\n"
                f"ALTVIA_E2E_TICKET_CLIENT_ID={ticket_client.id}\n"
                f"ALTVIA_E2E_TICKET_REQUESTER_ID={ticket_contact.id}\n"
            )
            for kind, (
                account_email,
                account_password,
                account_id,
            ) in queue_access_accounts.items():
                target.write(
                    f"ALTVIA_E2E_QUEUE_ACCESS_{kind}_EMAIL={account_email}\n"
                    f"ALTVIA_E2E_QUEUE_ACCESS_{kind}_PASSWORD={account_password}\n"
                    f"ALTVIA_E2E_QUEUE_ACCESS_{kind}_ID={account_id}\n"
                )
            target.write(f"ALTVIA_E2E_EXTERNAL_WORK_PROJECT_ID={external_work_project.id}\n")
            for kind, (work_email, work_password) in work_accounts.items():
                target.write(
                    f"ALTVIA_E2E_WORK_{kind}_EMAIL={work_email}\nALTVIA_E2E_WORK_{kind}_PASSWORD={work_password}\n"
                )
if not os.environ.get("ALTVIA_E2E_EXPIRE") and not os.environ.get("ALTVIA_E2E_DISABLE_ROSTER"):
    # Functional contact tests reuse real password-authenticated DB sessions.
    # Login HTTP/rate-limit acceptance remains in the identity suites; do not
    # spend that suite's single-source budget on unrelated contact setup.
    with Path(".env.browser-session").open("a", encoding="utf-8") as target:
        # Visual/navigation checks share this real session without adding an
        # administrator or spending extra logins after the functional suites.
        with Session(engine) as db:
            _, _, token = login(
                db, admin_email, admin_password, "admin-fixture", "admin_fixture_session"
            )
        target.write(f"ALTVIA_E2E_ADMIN_SESSION={token}\n")
        for kind, (account_email, account_password, account_id) in note_accounts.items():
            with Session(engine) as db:
                _, _, token = login(
                    db, account_email, account_password, "note-fixture", "note_fixture_session"
                )
            target.write(
                f"ALTVIA_E2E_NOTE_{kind}_SESSION={token}\nALTVIA_E2E_NOTE_{kind}_ID={account_id}\nALTVIA_E2E_NOTE_{kind}_EMAIL={account_email}\n"
            )
        for kind, (account_email, account_password, account_id) in ticket_accounts.items():
            with Session(engine) as db:
                _, _, token = login(
                    db, account_email, account_password, "ticket-fixture", "ticket_fixture_session"
                )
            target.write(
                f"ALTVIA_E2E_TICKET_{kind}_SESSION={token}\nALTVIA_E2E_TICKET_{kind}_ID={account_id}\n"
            )
        for kind, (account_email, account_password, _) in queue_access_accounts.items():
            with Session(engine) as db:
                _, _, token = login(
                    db, account_email, account_password, "queue-fixture", "queue_fixture_session"
                )
            target.write(f"ALTVIA_E2E_QUEUE_ACCESS_{kind}_SESSION={token}\n")
        for kind, (contact_email, contact_password, _) in contact_accounts.items():
            with Session(engine) as db:
                _, _, token = login(
                    db,
                    contact_email,
                    contact_password,
                    "browser-fixture",
                    "contact_fixture_session",
                )
            target.write(f"ALTVIA_E2E_CONTACT_{kind}_SESSION={token}\n")
        for kind, (member_email, member_password, _) in member_accounts.items():
            with Session(engine) as db:
                _, _, token = login(
                    db, member_email, member_password, "member-fixture", "member_fixture_session"
                )
            target.write(f"ALTVIA_E2E_MEMBER_{kind}_SESSION={token}\n")
    Path(".env.browser-session").chmod(0o600)
    with Path(".env.browser-session").open("a", encoding="utf-8") as target:
        for kind in ["MANAGER", "AGENT", "READER"]:
            with Session(engine) as db:
                _, _, token = login(
                    db,
                    *work_accounts[kind],
                    "external-work-fixture",
                    "external_work_fixture_session",
                )
            target.write(f"ALTVIA_E2E_WORK_{kind}_SESSION={token}\n")
        for kind, (milestone_email, milestone_password) in milestone_accounts.items():
            with Session(engine) as db:
                _, _, token = login(
                    db,
                    milestone_email,
                    milestone_password,
                    "milestone-fixture",
                    "milestone_fixture_session",
                )
            target.write(f"ALTVIA_E2E_MILESTONE_{kind}_SESSION={token}\n")
engine.dispose()
