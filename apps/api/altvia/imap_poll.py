"""Finite read-only IMAPS collection into private, fenced quarantine."""

import hashlib
import imaplib
import ipaddress
import json
import os
import re
import ssl
import sys
from collections.abc import Buffer
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic
from uuid import UUID, uuid4

from pydantic import Field, SecretStr, field_validator
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.mail_intake import (
    MAX_RAW_BYTES,
    MAX_VERSION,
    SafeMailParser,
    capture_message,
    record_intake_event,
)
from altvia.models import MailboxPollState, MailboxSource

SCAN_WINDOW = 1000
BATCH_SIZE = 25
LEASE_SECONDS = 120
WIRE_SECONDS = 90
SOCKET_SECONDS = 10
MAX_LINE = 16384
CONTROL_BYTES = 4 * MAX_LINE


class PollError(ValueError):
    """Fixed private error codes; never echo server responses or credentials."""


class IMAPPollSettings(DatabaseSettings):
    imap_host: str = Field(min_length=1, max_length=253)
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_username: SecretStr
    imap_password: SecretStr
    imap_ca_file: Path | None = None

    @field_validator("imap_host")
    @classmethod
    def host(cls, value: str) -> str:
        value = value.lower().rstrip(".")
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            if not value.isascii() or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in value.split(".")
            ):
                raise ValueError("Invalid IMAP host") from None
        return value

    @field_validator("imap_username", "imap_password")
    @classmethod
    def login_field(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not 1 <= len(raw) <= 1024 or any(not 32 <= ord(c) <= 126 for c in raw):
            raise ValueError("Unsupported IMAP login value")
        return value

    @property
    def namespace_hash(self) -> str:
        value = [self.imap_host, self.imap_port, self.imap_username.get_secret_value(), "INBOX"]
        return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class PollLease:
    source_id: UUID
    token: UUID
    namespace_hash: str


@dataclass(frozen=True)
class PollReceipt:
    source_id: str
    uid_validity: int
    last_uid: int
    captured: int
    replayed: int
    more: bool


def _now(db: Session) -> datetime:
    value = db.scalar(select(func.clock_timestamp()))
    if not isinstance(value, datetime):
        raise PollError("mail_poll_clock_unavailable")
    return value


def _acquire(engine: Engine, key: str, namespace: str) -> PollLease:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key):
        raise PollError("mail_poll_source_unavailable")
    with Session(engine) as db, db.begin():
        source = db.scalar(
            select(MailboxSource).where(MailboxSource.source_key == key).with_for_update()
        )
        if source is None:
            raise PollError("mail_poll_source_unavailable")
        state = db.get(MailboxPollState, source.id)
        now = _now(db)
        if state is None:
            state = MailboxPollState(source_id=source.id, last_uid=0)
            db.add(state)
        if state.namespace_hash is not None and state.namespace_hash != namespace:
            raise PollError("mail_poll_namespace_conflict")
        if state.lease_until is not None and state.lease_until > now:
            raise PollError("mail_poll_busy")
        token = uuid4()
        state.lease_token, state.lease_until = token, now + timedelta(seconds=LEASE_SECONDS)
        return PollLease(source.id, token, namespace)


def _locked(db: Session, lease: PollLease) -> tuple[MailboxSource, MailboxPollState]:
    source = db.scalar(
        select(MailboxSource).where(MailboxSource.id == lease.source_id).with_for_update()
    )
    state = db.get(MailboxPollState, lease.source_id)
    if (
        source is None
        or state is None
        or state.lease_token != lease.token
        or state.lease_until is None
        or state.lease_until <= _now(db)
    ):
        raise PollError("mail_poll_lease_expired")
    if state.namespace_hash is not None and state.namespace_hash != lease.namespace_hash:
        raise PollError("mail_poll_namespace_conflict")
    return source, state


def _event(db: Session, source: MailboxSource, state: MailboxPollState, reason: str) -> None:
    if source.version >= MAX_VERSION:
        raise PollError("mail_poll_version_exhausted")
    source.version += 1
    record_intake_event(
        db,
        source,
        "mailbox.poll_checkpointed",
        {
            "uid_validity": str(state.uid_validity),
            "last_uid": str(state.last_uid),
            "reason": reason,
        },
    )


def _initialize(engine: Engine, lease: PollLease, validity: int) -> int:
    with Session(engine) as db, db.begin():
        source, state = _locked(db, lease)
        if state.uid_validity != validity:
            reason = "initial" if state.uid_validity is None else "epoch_changed"
            state.namespace_hash, state.uid_validity, state.last_uid = (
                lease.namespace_hash,
                validity,
                0,
            )
            _event(db, source, state, reason)
        return state.last_uid


def _save_message(engine: Engine, lease: PollLease, validity: int, uid: int, raw: bytes) -> bool:
    with Session(engine) as db, db.begin():
        source, state = _locked(db, lease)
        if state.uid_validity != validity or uid <= state.last_uid:
            raise PollError("mail_poll_stale_progress")
        receipt = capture_message(db, source.source_key, validity, uid, raw)
        state.last_uid = uid
        _event(db, source, state, "message_captured")
        return receipt.replayed


def _save_scan(engine: Engine, lease: PollLease, validity: int, end: int) -> int:
    with Session(engine) as db, db.begin():
        source, state = _locked(db, lease)
        if state.uid_validity != validity or end < state.last_uid:
            raise PollError("mail_poll_stale_progress")
        if end > state.last_uid:
            state.last_uid = end
            _event(db, source, state, "range_scanned")
        return state.last_uid


def _release(engine: Engine, lease: PollLease) -> None:
    with Session(engine) as db, db.begin():
        db.scalar(
            select(MailboxSource).where(MailboxSource.id == lease.source_id).with_for_update()
        )
        state = db.get(MailboxPollState, lease.source_id)
        if state is not None and state.lease_token == lease.token:
            state.lease_token, state.lease_until = None, None


class _BoundedIMAPS(imaplib.IMAP4_SSL):
    def __init__(self, settings: IMAPPollSettings):
        self._bounded_buffer = bytearray()
        self._wire_deadline = monotonic() + WIRE_SECONDS
        self._metadata_bytes = CONTROL_BYTES
        self.response_budget(CONTROL_BYTES, 0)
        context = ssl.create_default_context(cafile=settings.imap_ca_file)
        try:
            super().__init__(
                settings.imap_host, settings.imap_port, ssl_context=context, timeout=SOCKET_SECONDS
            )
        except Exception:
            self.close_wire()
            raise

    def _budget(self) -> None:
        remaining = self._wire_deadline - monotonic()
        if remaining <= 0:
            raise PollError("mail_poll_wire_deadline")
        self.sock.settimeout(min(SOCKET_SECONDS, remaining))

    def _receive(self, limit: int) -> bytes:
        self._budget()
        if self._response_bytes <= 0:
            raise PollError("mail_poll_response_budget")
        data = self.sock.recv(min(limit, self._response_bytes + 1))
        if len(data) > self._response_bytes:
            raise PollError("mail_poll_response_budget")
        self._response_bytes -= len(data)
        if not data:
            raise PollError("mail_poll_connection_ended")
        return data

    def read(self, size: int) -> bytes:
        # imaplib asks for the declared literal length before allocating/reading.
        if self._response_literals < 1 or size - len(self._bounded_buffer) > self._response_bytes:
            raise PollError("mail_poll_response_budget")
        self._response_literals -= 1
        if not 0 <= size <= MAX_RAW_BYTES:
            raise PollError("mail_poll_literal_limit")
        while len(self._bounded_buffer) < size:
            self._bounded_buffer.extend(self._receive(min(65536, size - len(self._bounded_buffer))))
        value = bytes(self._bounded_buffer[:size])
        del self._bounded_buffer[:size]
        return value

    def readline(self) -> bytes:
        while True:
            newline = self._bounded_buffer.find(b"\n")
            if newline >= 0:
                if newline + 1 > MAX_LINE:
                    raise PollError("mail_poll_line_limit")
                # Other untagged response classes can survive command boundaries
                # inside imaplib. Cap retained metadata across the entire poll.
                if newline + 1 > self._metadata_bytes:
                    raise PollError("mail_poll_response_budget")
                self._metadata_bytes -= newline + 1
                value = bytes(self._bounded_buffer[: newline + 1])
                del self._bounded_buffer[: newline + 1]
                return value
            if len(self._bounded_buffer) >= MAX_LINE:
                raise PollError("mail_poll_line_limit")
            self._bounded_buffer.extend(
                self._receive(min(4096, MAX_LINE - len(self._bounded_buffer)))
            )

    def send(self, data: Buffer) -> None:
        self._budget()
        self.sock.sendall(data)

    def response_budget(self, byte_limit: int, literals: int) -> None:
        # imaplib retains all unsolicited responses until the tagged completion.
        # Bound that total before it can accumulate valid-size bodies or lines.
        self._response_bytes = byte_limit - len(self._bounded_buffer)
        self._response_literals = literals
        if self._response_bytes < 0:
            raise PollError("mail_poll_response_budget")

    def close_wire(self) -> None:
        for name in ("file", "sock"):
            part = getattr(self, name, None)
            if part is not None:
                with suppress(OSError):
                    part.close()


def _number(data: bytes) -> int:
    if not re.fullmatch(rb"[0-9]{1,10}", data):
        raise PollError("mail_poll_invalid_uid")
    value = int(data)
    if not 1 <= value <= 4294967295:
        raise PollError("mail_poll_invalid_uid")
    return value


def _selected_number(client: _BoundedIMAPS, name: str) -> int:
    _, data = client.response(name)
    if data is None or len(data) != 1 or not isinstance(data[0], bytes):
        raise PollError("mail_poll_missing_epoch")
    return _number(data[0])


def _check_epoch(client: _BoundedIMAPS, validity: int) -> None:
    _, epoch = client.response("UIDVALIDITY")
    if (
        epoch
        and epoch != [None]
        and (len(epoch) != 1 or not isinstance(epoch[0], bytes) or _number(epoch[0]) != validity)
    ):
        raise PollError("mail_poll_session_epoch_changed")


def _search(client: _BoundedIMAPS, start: int, end: int, validity: int) -> list[int]:
    client.response_budget(CONTROL_BYTES, 0)
    status, data = client.uid("SEARCH", "UID", f"{start}:{end}")
    _check_epoch(client, validity)
    if status != "OK" or len(data) != 1 or not isinstance(data[0], bytes):
        raise PollError("mail_poll_invalid_search")
    words = data[0].split()
    if len(words) > SCAN_WINDOW:
        raise PollError("mail_poll_search_limit")
    uids = [_number(value) for value in words]
    if len(uids) != len(set(uids)) or any(not start <= uid <= end for uid in uids):
        raise PollError("mail_poll_invalid_search")
    return sorted(uids)


def _fetch(client: _BoundedIMAPS, uid: int, validity: int) -> bytes:
    client.response_budget(MAX_RAW_BYTES + 2 * MAX_LINE, 1)
    status, data = client.uid("FETCH", str(uid), "(UID BODY.PEEK[])")
    if (
        status != "OK"
        or len(data) != 2
        or not isinstance(data[0], tuple)
        or not isinstance(data[1], bytes)
    ):
        raise PollError("mail_poll_invalid_fetch")
    prefix, raw = data[0]
    if not isinstance(prefix, bytes) or not isinstance(raw, bytes):
        raise PollError("mail_poll_invalid_fetch")
    metadata = prefix + data[1]
    match = re.fullmatch(
        rb"[0-9]+ \((?:UID ([0-9]{1,10}) BODY\[\] \{([0-9]+)\}|"
        rb"BODY\[\] \{([0-9]+)\} UID ([0-9]{1,10}))\)",
        metadata,
    )
    if match is None:
        raise PollError("mail_poll_invalid_fetch")
    received_uid, length = (match[1], match[2]) if match[1] is not None else (match[4], match[3])
    if (
        _number(received_uid) != uid
        or not 1 <= len(raw) <= MAX_RAW_BYTES
        or int(length) != len(raw)
    ):
        raise PollError("mail_poll_invalid_fetch")
    _check_epoch(client, validity)
    return raw


def poll_once(engine: Engine, settings: IMAPPollSettings, key: str) -> PollReceipt:
    lease = _acquire(engine, key, settings.namespace_hash)
    client = None
    try:
        client = _BoundedIMAPS(settings)
        username = settings.imap_username.get_secret_value()
        quoted = '"' + username.replace("\\", "\\\\").replace('"', '\\"') + '"'
        client.response_budget(CONTROL_BYTES, 0)
        client.login(quoted, settings.imap_password.get_secret_value())
        client.response_budget(CONTROL_BYTES, 0)
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise PollError("mail_poll_select_failed")
        validity = _selected_number(client, "UIDVALIDITY")
        next_uid = _selected_number(client, "UIDNEXT")
        last = _initialize(engine, lease, validity)
        if next_uid <= last:
            raise PollError("mail_poll_regressed_uidnext")
        end = min(last + SCAN_WINDOW, next_uid - 1)
        captured = replayed = 0
        uids = _search(client, last + 1, end, validity) if end > last else []
        for uid in uids[:BATCH_SIZE]:
            raw = _fetch(client, uid, validity)
            replay = _save_message(engine, lease, validity, uid, raw)
            replayed += int(replay)
            captured += int(not replay)
            last = uid
        if len(uids) <= BATCH_SIZE and end > last:
            last = _save_scan(engine, lease, validity, end)
        return PollReceipt(
            str(lease.source_id), validity, last, captured, replayed, last < next_uid - 1
        )
    except (imaplib.IMAP4.error, OSError, SQLAlchemyError, ValueError) as exc:
        if isinstance(exc, PollError):
            raise
        raise PollError("mail_poll_failed") from None
    finally:
        if client is not None:
            client.close_wire()
        _release(engine, lease)


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("ALTVIA_ALLOW_IMAP_POLL") != "1":
        print("Explicit ALTVIA_ALLOW_IMAP_POLL=1 is required.", file=sys.stderr)
        return 1
    parser = SafeMailParser(
        description="Restricted read-only IMAPS quarantine poll", allow_abbrev=False
    )
    parser.add_argument("--source-key", required=True)
    args = parser.parse_args(argv)
    engine = None
    try:
        settings = IMAPPollSettings()
        engine = make_engine(settings)
        receipt = poll_once(engine, settings, args.source_key)
    except (ValueError, SQLAlchemyError, OSError):
        print(
            "IMAP poll failed; no completion receipt. Committed quarantine remains safe to retry.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(asdict(receipt)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
