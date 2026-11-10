import argparse
import getpass
import sys
import warnings
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from altvia.client_registry import set_client_access
from altvia.config import Settings
from altvia.database import make_engine
from altvia.identity import IdentityError, normalize_email
from altvia.management import (
    bootstrap_admin,
    create_user,
    reset_password,
    set_account_active,
    set_platform_admin,
    set_team_role,
)
from altvia.policy import TEAM_READ_ROLES
from altvia.project_registry import PROJECT_ROLES, set_project_access


def main() -> int:
    password_commands = {"bootstrap-admin", "create-user", "reset-password"}
    team_commands = {"grant-team-role", "revoke-team-role"}
    client_commands = {"grant-client-access", "revoke-client-access"}
    project_commands = {"grant-project-access", "revoke-project-access"}
    parser = argparse.ArgumentParser(
        description="Restricted Altvia identity management", exit_on_error=False, allow_abbrev=False
    )
    parser.add_argument(
        "command",
        choices=[
            "bootstrap-admin",
            "create-user",
            "reset-password",
            "disable-user",
            "enable-user",
            "grant-admin",
            "revoke-admin",
            "grant-team-role",
            "revoke-team-role",
            "grant-client-access",
            "revoke-client-access",
            "grant-project-access",
            "revoke-project-access",
        ],
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--name")
    parser.add_argument("--team-id", type=UUID)
    parser.add_argument("--client-id", type=UUID)
    parser.add_argument("--project-id", type=UUID)
    parser.add_argument("--role", choices=sorted(TEAM_READ_ROLES | PROJECT_ROLES))
    # argparse's default errors echo unknown arguments and invalid values. An
    # accidentally supplied credential must not be copied into logs or stderr.
    try:
        args, unknown = parser.parse_known_args()
    except argparse.ArgumentError:
        parser.error("Invalid command arguments; use --help for supported options")
    if unknown:
        parser.error("Unsupported arguments; passwords are accepted only through hidden prompts")
    if args.command in project_commands:
        if args.project_id is None or args.team_id is not None or args.client_id is not None:
            parser.error("--project-id is required without team/client scope")
        if (args.role is not None) != (args.command == "grant-project-access"):
            parser.error("--role is required only for granting project access")
        if args.role is not None and args.role not in PROJECT_ROLES:
            parser.error("Invalid project role")
    elif args.project_id is not None:
        parser.error("--project-id is only valid for project access changes")
    elif args.command in client_commands:
        if args.client_id is None or args.team_id is not None:
            parser.error("--client-id is required and --team-id is not allowed")
        if (args.role is not None) != (args.command == "grant-client-access"):
            parser.error("--role is required only for granting client access")
        if args.role is not None and args.role not in TEAM_READ_ROLES:
            parser.error("Invalid client role")
    elif args.client_id is not None:
        parser.error("--client-id is only valid for client access changes")
    elif args.command in team_commands:
        if args.team_id is None or args.role not in TEAM_READ_ROLES:
            parser.error("--team-id and --role are required for team role changes")
    elif args.team_id is not None or args.role is not None:
        parser.error("--team-id and --role are only valid for team role changes")
    needs_name = args.command in {"bootstrap-admin", "create-user"}
    if needs_name and not args.name:
        parser.error("--name is required for account creation")
    if not needs_name and args.name is not None:
        parser.error("--name is only valid for account creation")
    if needs_name and not 1 <= len(args.name.strip()) <= 150:
        parser.error("--name must contain 1 to 150 characters")
    try:
        email = normalize_email(args.email)
    except ValueError:
        parser.error("A valid account e-mail is required")
    if not sys.stdin.isatty():
        parser.error("An interactive terminal is required; passwords are never CLI arguments")
    password = ""
    try:
        if args.command in password_commands:
            # getpass otherwise warns and falls back to echoed input when the
            # terminal cannot disable echo. Fail before reading in that case.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Password: ")
                if password != getpass.getpass("Confirm password: "):
                    print("Passwords do not match.", file=sys.stderr)
                    return 1
        else:
            entered = input(f"Type the target account email to confirm {args.command}: ")
            try:
                confirmed = normalize_email(entered) == email
            except ValueError:
                confirmed = False
            if not confirmed:
                print("Confirmation did not match; no change made.", file=sys.stderr)
                return 1
            if args.command in team_commands | client_commands | project_commands:
                target_kind = (
                    "project"
                    if args.command in project_commands
                    else ("client" if args.command in client_commands else "team")
                )
                target_id = (
                    args.project_id
                    if args.command in project_commands
                    else (args.client_id if args.command in client_commands else args.team_id)
                )
                entered_team = input(f"Type the target {target_kind} UUID to confirm: ")
                try:
                    confirmed_team = UUID(entered_team.strip()) == target_id
                except ValueError:
                    confirmed_team = False
                if not confirmed_team:
                    print("Confirmation did not match; no change made.", file=sys.stderr)
                    return 1
    except (EOFError, getpass.GetPassWarning):
        print("Secure input unavailable or cancelled; no change made.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Operation cancelled; no change made.", file=sys.stderr)
        return 130
    engine = None
    try:
        settings = Settings()
        engine = make_engine(settings)
        with Session(engine) as db, db.begin():
            if args.command == "bootstrap-admin":
                bootstrap_admin(db, email, args.name, password)
            elif args.command == "create-user":
                create_user(db, email, args.name, password)
            elif args.command == "reset-password":
                reset_password(db, email, password)
            elif args.command in {"disable-user", "enable-user"}:
                set_account_active(db, email, args.command == "enable-user")
            elif args.command in team_commands:
                assert args.team_id is not None and args.role is not None
                set_team_role(db, email, args.team_id, args.role, args.command == "grant-team-role")
            elif args.command in client_commands:
                if args.client_id is None:
                    raise ValueError("Client identifier required")
                set_client_access(db, email, args.client_id, args.role)
            elif args.command in project_commands:
                if args.project_id is None:
                    raise ValueError("Project identifier required")
                set_project_access(db, email, args.project_id, args.role)
            else:
                set_platform_admin(db, email, args.command == "grant-admin")
    except ValidationError:
        print("Invalid configuration; check the database URL and HTTPS origin.", file=sys.stderr)
        return 1
    except IdentityError as exc:
        print(exc.code, file=sys.stderr)
        return 1
    except (SQLAlchemyError, ValueError):
        print("Identity operation failed; check configuration and account state.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print("Identity operation committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
