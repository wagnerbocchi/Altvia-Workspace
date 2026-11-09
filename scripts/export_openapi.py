"""Export the API contract without connecting to a database or loading secrets."""

import json
from pathlib import Path

from altvia.config import Settings
from altvia.main import create_app
from pydantic import SecretStr

app = create_app(
    Settings(
        _env_file=None,
        database_url=SecretStr("postgresql+psycopg://unused@localhost/unused"),
        public_origin="https://localhost",
    )
)
Path("docs/contracts/openapi.json").write_text(
    json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
