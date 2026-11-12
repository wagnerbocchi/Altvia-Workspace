"""Strict private Clamd VERSION/INSTREAM transport; no raw engine text escapes."""

import re
import socket
import struct
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import BinaryIO, Literal

from altvia.file_settings import MAX_FILE_BYTES, ScannerSettings

Disposition = Literal["clean", "infected", "failed"]
Reason = Literal[
    "clean",
    "infected",
    "encrypted",
    "limit",
    "scan_error",
    "protocol",
    "unavailable",
    "cancelled",
    "timeout",
    "database_invalid",
    "database_changed",
]


@dataclass(frozen=True)
class ScanResult:
    disposition: Disposition
    reason: Reason
    engine: str | None = None
    database_version: int | None = None
    database_date: datetime | None = None


class _ScanFailure(Exception):
    def __init__(self, reason: Reason):
        self.reason = reason


def _version(raw: bytes, expected: str, now: datetime) -> tuple[str, int, datetime]:
    match = re.fullmatch(
        rb"ClamAV ([0-9]+\.[0-9]+\.[0-9]+)/([1-9][0-9]{0,9})/"
        rb"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
        rb" ?([0-9]{1,2}) ([0-9]{2}):([0-9]{2}):([0-9]{2}) ([0-9]{4})",
        raw,
    )
    if not match:
        raise _ScanFailure("database_invalid")
    engine, sequence, weekday, month, day, hour, minute, second, year = match.groups()
    try:
        date = datetime(
            int(year),
            [
                b"Jan",
                b"Feb",
                b"Mar",
                b"Apr",
                b"May",
                b"Jun",
                b"Jul",
                b"Aug",
                b"Sep",
                b"Oct",
                b"Nov",
                b"Dec",
            ].index(month)
            + 1,
            int(day),
            int(hour),
            int(minute),
            int(second),
            tzinfo=UTC,
        )
    except ValueError:
        raise _ScanFailure("database_invalid") from None
    if (
        engine.decode("ascii") != expected
        or now.tzinfo is None
        or weekday != [b"Mon", b"Tue", b"Wed", b"Thu", b"Fri", b"Sat", b"Sun"][date.weekday()]
        or now - date > timedelta(hours=48)
        or date - now > timedelta(minutes=5)
    ):
        raise _ScanFailure("database_invalid")
    return engine.decode("ascii"), int(sequence), date


class ClamClient:
    def __init__(self, settings: ScannerSettings) -> None:
        self.settings = settings

    def scan(self, source: BinaryIO, *, db_now: datetime, stop: Event | None = None) -> ScanResult:
        deadline = time.monotonic() + 30
        identity: tuple[str, int, datetime] | None = None

        def remaining() -> float:
            if stop is not None and stop.is_set():
                raise _ScanFailure("cancelled")
            left = deadline - time.monotonic()
            if left <= 0:
                raise _ScanFailure("timeout")
            return min(5, left)

        def exchange(command: bytes, stream: BinaryIO | None = None) -> bytes:
            with socket.socket(getattr(socket, "AF_UNIX", 0), socket.SOCK_STREAM) as conn:
                conn.settimeout(remaining())
                conn.connect(str(self.settings.socket_path))

                def send(data: bytes) -> None:
                    conn.settimeout(remaining())
                    conn.sendall(data)

                send(command)
                if stream is not None:
                    count = 0
                    while True:
                        remaining()
                        chunk = stream.read(65536)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > MAX_FILE_BYTES:
                            raise _ScanFailure("limit")
                        send(struct.pack("!I", len(chunk)) + chunk)
                    if count == 0:
                        raise _ScanFailure("limit")
                    send(b"\x00\x00\x00\x00")
                reply = bytearray()
                while not reply.endswith(b"\0"):
                    conn.settimeout(remaining())
                    part = conn.recv(1025 - len(reply))
                    if not part or len(reply) + len(part) > 1024 or b"\0" in part[:-1]:
                        raise _ScanFailure("protocol")
                    reply.extend(part)
                # Clamd closes each non-session command. Require EOF to reject
                # extra frames, even when they arrive in a separate network read.
                conn.settimeout(remaining())
                if conn.recv(1):
                    raise _ScanFailure("protocol")
                return bytes(reply[:-1])

        try:
            remaining()
            if not hasattr(socket, "AF_UNIX"):
                raise _ScanFailure("unavailable")
            identity = _version(exchange(b"zVERSION\0"), self.settings.engine, db_now)
            reply = exchange(b"zINSTREAM\0", source)
            after = _version(exchange(b"zVERSION\0"), self.settings.engine, db_now)
            if after != identity:
                raise _ScanFailure("database_changed")
            disposition: Disposition = "failed"
            reason: Reason = "protocol"
            if reply == b"stream: OK":
                disposition, reason = "clean", "clean"
            elif re.fullmatch(rb"stream: [A-Za-z0-9_.()-]{1,200} FOUND", reply):
                if b"Heuristics.Encrypted." in reply:
                    reason = "encrypted"
                elif b"Heuristics.Limits.Exceeded" in reply:
                    reason = "limit"
                else:
                    disposition, reason = "infected", "infected"
            elif reply.endswith(b" ERROR"):
                reason = "scan_error"
            return ScanResult(disposition, reason, *identity)
        except _ScanFailure as error:
            return ScanResult("failed", error.reason, *(identity or (None, None, None)))
        except TimeoutError:
            return ScanResult("failed", "timeout", *(identity or (None, None, None)))
        except (OSError, ValueError):
            return ScanResult("failed", "unavailable", *(identity or (None, None, None)))
