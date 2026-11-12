from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALTVIA_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
        secrets_dir=Path("/run/secrets") if Path("/run/secrets").is_dir() else None,
    )

    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("A PostgreSQL psycopg URL is required")
        return value


class Settings(DatabaseSettings):
    storage_file: Path | None = None
    public_origin: str

    @field_validator("public_origin")
    @classmethod
    def require_https_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("An exact HTTPS origin without credentials/path is required")
        return value.rstrip("/")


class WorkerSettings(DatabaseSettings):
    redis_url: SecretStr
    worker_state_dir: Path = Path("/run/altvia")
    smtp_accounts_file: Path | None = None
    scanner_storage_file: Path | None = None
    scanner_socket: Path = Path("/run/clamav/clamd.sock")

    @field_validator("redis_url")
    @classmethod
    def require_authenticated_redis(cls, value: SecretStr) -> SecretStr:
        parsed = urlsplit(value.get_secret_value())
        if (
            parsed.scheme != "redis"
            or not parsed.hostname
            or not parsed.password
            or parsed.path not in ("", "/0")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("An authenticated private Redis database 0 URL is required")
        return value
