"""Actual loopback TLS SMTP, never a provider or real recipient."""

import shutil
import socket
import ssl
import subprocess
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Event, Thread
from uuid import uuid4

import pytest
from altvia.mail_delivery import FrozenDelivery, build_wire
from altvia.mail_settings import SMTPAccount


@pytest.fixture(scope="module")
def certificate(tmp_path_factory):
    folder = tmp_path_factory.mktemp("smtp-tls")
    cert, key = folder / "cert.pem", folder / "key.pem"
    openssl = shutil.which("openssl") or "C:/Program Files/Git/usr/bin/openssl.exe"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


@contextmanager
def smtp_server(certificate, mode="implicit", fault=None, before_data=None):
    cert, key = certificate
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    commands, messages = [], []
    stopped, waiting = Event(), Event()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    listener.settimeout(0.2)
    active = []

    def serve():
        while not stopped.is_set():
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            active.append(connection)
            try:
                connection.settimeout(2)
                secure = mode == "implicit"
                if fault == "tls_stall":
                    waiting.set()
                    stopped.wait(3)
                    continue
                if secure:
                    connection = context.wrap_socket(connection, server_side=True)
                    active.append(connection)
                if fault == "greeting_stall":
                    waiting.set()
                    stopped.wait(3)
                    continue
                if fault == "oversized":
                    connection.sendall(b"220 " + b"x" * 20000 + b"\r\n")
                    continue
                if fault == "multiline":
                    connection.sendall(b"220-loop\r\n" * 1000)
                    continue
                if fault == "trickle":
                    for byte in b"220-very slow greeting\r\n" * 20:
                        connection.sendall(bytes([byte]))
                        if stopped.wait(0.03):
                            break
                    continue
                connection.sendall(b"220 local synthetic SMTP\r\n")
                stream = connection.makefile("rb")
                while not stopped.is_set():
                    line = stream.readline(300000)
                    if not line:
                        break
                    verb = line.split(b" ", 1)[0].strip().upper()
                    commands.append((secure, line))
                    if verb == b"EHLO":
                        connection.sendall(
                            b"250 local\r\n"
                            if not secure and fault == "no_starttls"
                            else b"250-local\r\n250 AUTH PLAIN LOGIN\r\n"
                            if secure
                            else b"250-local\r\n250 STARTTLS\r\n"
                        )
                    elif verb == b"STARTTLS":
                        connection.sendall(b"220 TLS required\r\n")
                        stream.close()
                        connection = context.wrap_socket(connection, server_side=True)
                        active.append(connection)
                        stream = connection.makefile("rb")
                        secure = True
                    elif verb == b"AUTH":
                        connection.sendall(b"535 refused\r\n" if fault == "auth" else b"235 OK\r\n")
                    elif verb == b"MAIL":
                        if fault == "disconnect":
                            break
                        connection.sendall(b"250 OK\r\n")
                    elif verb == b"RCPT":
                        if before_data:
                            before_data()
                        connection.sendall(
                            {"rcpt4": b"450 no\r\n", "rcpt5": b"550 no\r\n"}.get(
                                fault, b"250 OK\r\n"
                            )
                        )
                    elif verb == b"DATA":
                        if fault == "data_stall":
                            waiting.set()
                            stopped.wait(3)
                            break
                        if fault in {"data4", "data5"}:
                            connection.sendall(b"450 no\r\n" if fault == "data4" else b"550 no\r\n")
                            continue
                        connection.sendall(b"354 continue\r\n")
                        body = bytearray()
                        while True:
                            part = stream.readline(300000)
                            if part == b".\r\n" or not part:
                                break
                            body.extend(part[1:] if part.startswith(b"..") else part)
                        messages.append(bytes(body))
                        if fault == "lost":
                            break
                        if fault == "final_oversized":
                            connection.sendall(b"250 " + b"x" * 20000 + b"\r\n")
                            continue
                        if fault == "once_temporary" and len(messages) == 1:
                            connection.sendall(b"450 retry later\r\n")
                            continue
                        connection.sendall(
                            {
                                "final4": b"450 no\r\n",
                                "final5": b"550 no\r\n",
                                "positive": b"251 unexpected\r\n",
                                "malformed": b"oops\r\n",
                            }.get(fault, b"250 accepted\r\n")
                        )
                    elif verb == b"QUIT":
                        if fault != "quit":
                            connection.sendall(b"221 bye\r\n")
                        break
                    else:
                        connection.sendall(b"500 invalid\r\n")
                stream.close()
            except (OSError, ssl.SSLError):
                pass
            finally:
                connection.close()

    thread = Thread(target=serve, daemon=True)
    thread.start()
    account = SMTPAccount(
        source_id=uuid4(),
        host="127.0.0.1",
        port=listener.getsockname()[1],
        tls_mode=mode,
        username="synthetic",
        password="synthetic",
        from_email="support@example.test",
        ca_file=cert,
    )
    try:
        yield account, commands, messages, waiting
    finally:
        stopped.set()
        listener.close()
        for connection in active:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        thread.join(3)
        assert not thread.is_alive()


def frozen():
    wire = build_wire(
        "support@example.test",
        "requester@example.test",
        "Synthetic",
        "Plain public response\n.dot\n",
        "<fixed@example.test>",
        "ticket-token",
        datetime(2026, 11, 12, tzinfo=UTC),
        [],
    )
    return FrozenDelivery(
        uuid4(), "support@example.test", "requester@example.test", wire, "<fixed@example.test>"
    )


@pytest.mark.parametrize("mode", ["implicit", "starttls"])
def test_verified_tls_exact_frozen_wire_and_envelope(certificate, mode):
    from altvia.smtp_transport import transmit

    item = frozen()
    with smtp_server(certificate, mode) as (account, commands, messages, _):
        assert transmit(account, item, lambda: True) == "accepted"
        assert messages == [item.wire]
        assert (True, b"mail FROM:<support@example.test>\r\n") in commands
        assert (True, b"rcpt TO:<requester@example.test>\r\n") in commands
        assert all(
            secure for secure, line in commands if line.upper().startswith((b"AUTH", b"DATA"))
        )
        if mode == "starttls":
            assert [secure for secure, line in commands if line.upper().startswith(b"EHLO")] == [
                False,
                True,
            ]


@pytest.mark.parametrize(
    "fault,want",
    [
        ("auth", "permanent"),
        ("disconnect", "transport"),
        ("rcpt4", "temporary"),
        ("rcpt5", "permanent"),
        ("data4", "temporary"),
        ("data5", "permanent"),
        ("final4", "temporary"),
        ("final5", "permanent"),
        ("lost", "data_unknown"),
        ("malformed", "data_unknown"),
        ("positive", "data_unknown"),
        ("quit", "accepted"),
        ("oversized", "transport"),
        ("multiline", "transport"),
        ("final_oversized", "data_unknown"),
    ],
)
def test_definite_rejection_only_safe_retry_and_final250_acceptance(certificate, fault, want):
    from altvia.smtp_transport import transmit

    with smtp_server(certificate, fault=fault) as (account, _, _, _):
        assert transmit(account, frozen(), lambda: True) == want


def test_untrusted_certificate_never_authenticates_or_sends(certificate):
    from altvia.smtp_transport import transmit

    with smtp_server(certificate) as (account, commands, messages, _):
        account = account.model_copy(update={"ca_file": None})
        assert transmit(account, frozen(), lambda: True) == "transport"
        assert commands == [] and messages == []


def test_greeting_has_total_deadline_and_cancel_closes_active_socket(certificate):
    from altvia.smtp_transport import ActiveTransports, transmit

    with smtp_server(certificate, fault="greeting_stall") as (account, _, _, waiting):
        started = time.monotonic()
        assert transmit(account, frozen(), lambda: True, budget=0.3) == "transport"
        assert time.monotonic() - started < 1.5
    with smtp_server(certificate, fault="greeting_stall") as (account, _, _, waiting):
        active, result = ActiveTransports(), []
        thread = Thread(
            target=lambda: result.append(transmit(account, frozen(), lambda: True, active=active))
        )
        thread.start()
        assert waiting.wait(2)
        active.cancel()
        thread.join(1)
        assert not thread.is_alive() and result == ["transport"]


def test_pre_data_authority_fence_prevents_body(certificate):
    from altvia.smtp_transport import transmit

    with smtp_server(certificate) as (account, commands, messages, _):
        assert transmit(account, frozen(), lambda: False) is None
        assert messages == [] and not any(line.upper().startswith(b"DATA") for _, line in commands)


def test_optional_worker_config_defaults_to_absent():
    from altvia.config import WorkerSettings

    assert (
        WorkerSettings(
            database_url="postgresql+psycopg://unused/unused",
            redis_url="redis://:synthetic@localhost/0",
        ).smtp_accounts_file
        is None
    )


@pytest.mark.parametrize("fault", ["tls_stall", "trickle"])
def test_total_deadline_bounds_tls_and_byte_trickle(certificate, fault):
    from altvia.smtp_transport import transmit

    with smtp_server(certificate, fault=fault) as (account, _, _, _):
        started = time.monotonic()
        assert transmit(account, frozen(), lambda: True, budget=0.2) == "transport"
        assert time.monotonic() - started < 1.5


def test_required_starttls_never_downgrades(certificate):
    from altvia.smtp_transport import transmit

    with smtp_server(certificate, mode="starttls", fault="no_starttls") as (
        account,
        commands,
        messages,
        _,
    ):
        assert transmit(account, frozen(), lambda: True) == "permanent"
        assert messages == []
        assert not any(line.upper().startswith((b"AUTH", b"MAIL", b"DATA")) for _, line in commands)


def test_blocked_dns_is_deadline_bounded_and_cancellable(monkeypatch):
    from altvia.smtp_transport import ActiveTransports, transmit

    release = Event()
    started = Event()

    def blocked(*args, **kwargs):
        started.set()
        release.wait(5)
        raise OSError("synthetic_dns_failure")

    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    account = SMTPAccount(
        source_id=uuid4(),
        host="smtp.example.test",
        port=465,
        tls_mode="implicit",
        username="synthetic",
        password="synthetic",
        from_email="support@example.test",
    )
    try:
        began = time.monotonic()
        assert transmit(account, frozen(), lambda: True, budget=0.1) == "transport"
        assert time.monotonic() - began < 0.5
        active, result = ActiveTransports(), []
        thread = Thread(
            target=lambda: result.append(transmit(account, frozen(), lambda: True, active=active))
        )
        thread.start()
        assert started.wait(1)
        active.cancel()
        thread.join(0.5)
        assert not thread.is_alive() and result == ["transport"]
    finally:
        release.set()
