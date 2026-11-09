import argparse
import getpass
import sys
import warnings

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from altvia.config import Settings
from altvia.database import make_engine
from altvia.identity import IdentityError, normalize_email
from altvia.management import (
    bootstrap_admin,
    create_user,
    reset_password,
    set_account_active,
    set_platform_admin,
)


def main() -> int:
    password_commands = {"bootstrap-admin", "create-user", "reset-password"}
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
        ],
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--name")
    # argparse's default errors echo unknown arguments and invalid values. An
    # accidentally supplied credential must not be copied into logs or stderr.
    try:
        args, unknown = parser.parse_known_args()
    except argparse.ArgumentError:
        parser.error("Invalid command arguments; use --help for supported options")
    if unknown:
        parser.error("Unsupported arguments; passwords are accepted only through hidden prompts")
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
