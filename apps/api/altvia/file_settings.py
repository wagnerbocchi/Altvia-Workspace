"""Owner-selected private endpoints; credentials never come from ambient AWS state."""

import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

MAX_FILE_BYTES = 10 * 1024 * 1024


class StorageSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    endpoint: str
    ca_file: Path
    access_key: SecretStr
    secret_key: SecretStr

    @field_validator("endpoint")
    @classmethod
    def private_tls_endpoint(cls, value: str) -> str:
        try:
            url = urlsplit(value)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.path not in ("", "/")
                or url.query
                or url.fragment
                or not value.isascii()
                or any(ord(c) <= 32 for c in value)
                or url.port == 0
            ):
                raise ValueError
        except ValueError:
            raise ValueError("invalid_storage_endpoint") from None
        return value.rstrip("/")

    @field_validator("ca_file")
    @classmethod
    def explicit_ca(cls, value: Path) -> Path:
        if not value.is_absolute() or not value.is_file():
            raise ValueError("invalid_storage_ca")
        return value

    @field_validator("access_key", "secret_key")
    @classmethod
    def credential(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not re.fullmatch(r"[A-Za-z0-9_+=.,@/-]{1,128}", raw):
            raise ValueError("invalid_storage_credential")
        return value


class ScannerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    socket_path: Path = Path("/run/clamav/clamd.sock")
    engine: str = Field(default="1.4.6", pattern=r"^1\.4\.6$")

    @field_validator("socket_path")
    @classmethod
    def private_socket(cls, value: Path) -> Path:
        if not value.is_absolute() or ".." in value.parts or "\x00" in str(value):
            raise ValueError("invalid_scanner_socket")
        return value
