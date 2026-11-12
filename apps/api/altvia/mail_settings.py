"""Bounded owner-selected SMTP accounts; never log configuration input."""

import hashlib
import ipaddress
import json
import re
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


def mailbox(value: str) -> str:
    from altvia.client_contacts import normalize_contact_email

    try:
        return normalize_contact_email(value)
    except ValueError:
        raise ValueError("invalid_mailbox") from None


class SMTPAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    source_id: UUID
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    tls_mode: Literal["implicit", "starttls"]
    username: SecretStr
    password: SecretStr
    from_email: str
    ca_file: Path | None = None

    @field_validator("from_email")
    @classmethod
    def valid_mailbox(cls, value: str) -> str:
        return mailbox(value)

    @field_validator("host")
    @classmethod
    def valid_host(cls, value: str) -> str:
        value = value.lower().rstrip(".")
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            if not value.isascii() or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in value.split(".")
            ):
                raise ValueError("invalid_host") from None
        return value

    @field_validator("username", "password")
    @classmethod
    def bounded_secret(cls, value: SecretStr) -> SecretStr:
        if not 1 <= len(value.get_secret_value()) <= 1024 or any(
            not 32 <= ord(c) <= 126 for c in value.get_secret_value()
        ):
            raise ValueError("invalid_credential")
        return value

    @property
    def namespace_hash(self) -> str:
        values = [
            str(self.source_id),
            self.host,
            self.port,
            self.tls_mode,
            self.username.get_secret_value(),
            self.from_email,
        ]
        return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def load_accounts(path: Path) -> dict[UUID, SMTPAccount]:
    try:
        with path.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("invalid_smtp_configuration")
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) > 16:
            raise ValueError("invalid_smtp_configuration")
        result = {}
        for entry in data:
            account = SMTPAccount.model_validate(entry)
            if account.source_id in result:
                raise ValueError("invalid_smtp_configuration")
            result[account.source_id] = account
        return result
    except (ValueError, OSError, TypeError, RecursionError):
        raise ValueError("invalid_smtp_configuration") from None
