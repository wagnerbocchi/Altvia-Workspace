"""Provision synthetic browser-test identity only in the disposable test DB."""

import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from altvia.config import Settings
from altvia.database import make_engine
from altvia.management import hash_new_password
from altvia.models import SessionRecord, User
from sqlalchemy import update
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
        # Credentials never go to stdout, source control or browser traces.
        Path(".env.browser-session").write_text(
            f"ALTVIA_E2E_EMAIL={email}\nALTVIA_E2E_PASSWORD={password}\n", encoding="utf-8"
        )
engine.dispose()
