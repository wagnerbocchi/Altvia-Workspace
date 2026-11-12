"""Actual controlled socket framing/faults; never substitutes for signed AV acceptance."""

import io
import socket
import struct
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Event, Thread

import pytest
from altvia.file_scan_transport import ClamClient
from altvia.file_settings import ScannerSettings

NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
VERSION = b"ClamAV 1.4.6/28000/Thu Nov 12 09:00:00 2026\0"
pytestmark = pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="POSIX socket required")


@contextmanager
def daemon(tmp_path, replies):
    path = tmp_path / "clamd.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(4)
    received = []
    errors = []
    finished = Event()
    listener.settimeout(0.2)

    def serve():
        try:
            for reply in replies:
                while not finished.is_set():
                    try:
                        conn, _ = listener.accept()
                        break
                    except TimeoutError:
                        continue
                else:
                    return
                with conn:
                    conn.settimeout(3)
                    command = bytearray()
                    while not command.endswith(b"\0"):
                        command.extend(conn.recv(1))
                    if command == b"zINSTREAM\0":
                        body = bytearray()
                        while True:
                            header = conn.recv(4)
                            while len(header) < 4:
                                header += conn.recv(4 - len(header))
                            length = struct.unpack("!I", header)[0]
                            if length == 0:
                                break
                            while length:
                                part = conn.recv(length)
                                body.extend(part)
                                length -= len(part)
                        received.append(bytes(body))
                    conn.sendall(reply)
        except (OSError, ValueError) as exc:
            if not finished.is_set():
                errors.append(type(exc).__name__)
        finally:
            listener.close()

    thread = Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield ClamClient(ScannerSettings(socket_path=path)), received
    finally:
        finished.set()
        listener.close()
        thread.join(timeout=4)
        assert not thread.is_alive()
        assert not errors


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="POSIX socket transport required")
def test_clean_requires_both_matching_versions_and_exact_stream_reply(tmp_path):
    with daemon(tmp_path, [VERSION, b"stream: OK\0", VERSION]) as (client, received):
        result = client.scan(io.BytesIO(b"real bytes"), db_now=NOW)
        assert (result.disposition, result.reason) == ("clean", "clean")
        assert result.engine == "1.4.6" and result.database_version == 28000
        assert result.database_date == datetime(2026, 11, 12, 9, tzinfo=UTC)
        assert received == [b"real bytes"]


@pytest.mark.parametrize(
    "version",
    [
        b"ClamAV 1.4.5/28000/Thu Nov 12 09:00:00 2026\0",
        b"ClamAV 1.4.6/28000/Mon Nov 09 09:00:00 2026\0",
        b"ClamAV 1.4.6/28000/Thu Nov 12 12:06:00 2026\0",
        b"ClamAV 1.4.6\0",
        b"garbage\0",
        b"x" * 1025 + b"\0",
        VERSION[:-1],
    ],
)
def test_bad_version_never_streams_or_releases(tmp_path, version):
    with daemon(tmp_path, [version]) as (client, received):
        result = client.scan(io.BytesIO(b"bytes"), db_now=NOW)
        assert result.disposition == "failed"
        assert received == []


@pytest.mark.parametrize(
    "reply,disposition,reason",
    [
        (b"stream: Win.Test.EICAR_HDB-1 FOUND\0", "infected", "infected"),
        (b"stream: Heuristics.Encrypted.Zip FOUND\0", "failed", "encrypted"),
        (b"stream: Heuristics.Limits.Exceeded.MaxFileSize FOUND\0", "failed", "limit"),
        (b"stream: read ERROR\0", "failed", "scan_error"),
        (b"stream: OK\0junk", "failed", "protocol"),
        (b"stream: OK", "failed", "protocol"),
        (b"other: OK\0", "failed", "protocol"),
    ],
)
def test_nonclean_or_malformed_scan_cannot_release(tmp_path, reply, disposition, reason):
    with daemon(tmp_path, [VERSION, reply, VERSION]) as (client, _):
        result = client.scan(io.BytesIO(b"bytes"), db_now=NOW)
        assert (result.disposition, result.reason) == (disposition, reason)


def test_database_change_discards_clean(tmp_path):
    after = VERSION.replace(b"28000", b"28001")
    with daemon(tmp_path, [VERSION, b"stream: OK\0", after]) as (client, _):
        result = client.scan(io.BytesIO(b"bytes"), db_now=NOW)
        assert (result.disposition, result.reason) == ("failed", "database_changed")


def test_refusal_and_cancellation_are_fixed_failed_results(tmp_path):
    client = ClamClient(ScannerSettings(socket_path=tmp_path / "absent"))
    assert client.scan(io.BytesIO(b"bytes"), db_now=NOW).disposition == "failed"
    stop = Event()
    stop.set()
    assert client.scan(io.BytesIO(b"bytes"), db_now=NOW, stop=stop).reason == "cancelled"
