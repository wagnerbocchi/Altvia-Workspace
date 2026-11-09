import argparse
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from altvia.config import Settings
from altvia.database import make_engine
from altvia.identity import IdentityError
from altvia.management import bootstrap_admin, reset_password


def main() -> int:
    parser = argparse.ArgumentParser(description="Restricted Altvia identity management")
    parser.add_argument("command", choices=["bootstrap-admin", "reset-password"])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("An interactive terminal is required; passwords are never CLI arguments")
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1
    try:
        settings = Settings()
    except ValidationError:
        print("Invalid configuration; check the database URL and HTTPS origin.", file=sys.stderr)
        return 1
    engine = make_engine(settings)
    try:
        with Session(engine) as db, db.begin():
            if args.command == "bootstrap-admin":
                if not args.name:
                    parser.error("--name is required for bootstrap-admin")
                bootstrap_admin(db, args.email, args.name, password)
            else:
                reset_password(db, args.email, password)
    except IdentityError as exc:
        print(exc.code, file=sys.stderr)
        return 1
    except (SQLAlchemyError, ValueError):
        print("Identity operation failed; check configuration and account state.", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print("Identity operation committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
