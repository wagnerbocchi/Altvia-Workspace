"""Finite verified-TLS SMTP attempts over immutable public delivery snapshots."""

import queue
import smtplib
import socket
import ssl
import time
from collections.abc import Buffer, Callable, Sequence
from threading import BoundedSemaphore, Event, Lock, Thread
from typing import Literal
from uuid import UUID

from sqlalchemy import Engine

from altvia import mail_delivery
from altvia.mail_delivery import FrozenDelivery
from altvia.mail_settings import SMTPAccount

Outcome = Literal["accepted", "temporary", "permanent", "transport", "data_unknown"]
ATTEMPT_SECONDS = 60.0  # Leave half the SQL lease for fenced persistence/recovery.
_RESOLVERS = BoundedSemaphore(2)


class ActiveTransports:
    """Worker-owned cancellation, including sockets still connecting/handshaking."""

    def __init__(self) -> None:
        self.stopped = Event()
        self.lock = Lock()
        self.sockets: set[socket.socket] = set()

    def replace(self, old: socket.socket | None, new: socket.socket) -> None:
        with self.lock:
            if old is not None:
                self.sockets.discard(old)
            if self.stopped.is_set():
                new.close()
                raise OSError("smtp_cancelled")
            self.sockets.add(new)

    def discard(self, connection: socket.socket) -> None:
        with self.lock:
            self.sockets.discard(connection)
        try:
            connection.close()
        except OSError:
            pass  # Cleanup cannot undo a positive final DATA250.

    def cancel(self) -> None:
        self.stopped.set()
        with self.lock:
            for connection in self.sockets:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    connection.close()
                except OSError:
                    pass
            self.sockets.clear()


class _SMTP(smtplib.SMTP):
    def __init__(self, deadline: float, active: ActiveTransports) -> None:
        # An empty host avoids smtplib's unguarded constructor greeting/connect.
        super().__init__(local_hostname="altvia.invalid")
        self.deadline, self.active = deadline, active

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if self.active.stopped.is_set() or remaining <= 0:
            raise TimeoutError("smtp_deadline_or_cancel")
        return min(5.0, remaining)

    def send(self, s: Buffer | str) -> None:
        if self.sock is None:
            raise smtplib.SMTPServerDisconnected("smtp_disconnected")
        self.sock.settimeout(self.remaining())
        super().send(s)

    def getreply(self) -> tuple[int, bytes]:
        # Public smtplib extension point. Never use its file/parser internals:
        # every byte read refreshes the absolute deadline, before the greeting too.
        if self.sock is None:
            raise smtplib.SMTPServerDisconnected("smtp_disconnected")
        total, expected, parts = 0, None, []
        for _ in range(64):
            line = bytearray()
            while not line.endswith(b"\r\n"):
                self.sock.settimeout(self.remaining())
                part = self.sock.recv(1)
                if not part:
                    raise smtplib.SMTPServerDisconnected("smtp_disconnected")
                line.extend(part)
                total += 1
                if len(line) > 2048 or total > 16384:
                    raise smtplib.SMTPException("smtp_reply_limit")
            if (
                len(line) < 6
                or not all(48 <= c <= 57 for c in line[:3])
                or line[3] not in (32, 45)
                or any(c < 32 and c != 9 for c in line[4:-2])
            ):
                raise smtplib.SMTPException("smtp_invalid_reply")
            code = int(line[:3])
            if not 100 <= code <= 599 or (expected is not None and expected != code):
                raise smtplib.SMTPException("smtp_invalid_reply")
            expected = code
            parts.append(bytes(line[4:-2]))
            if line[3] == 32:
                return code, b"\n".join(parts)
        raise smtplib.SMTPException("smtp_reply_limit")

    def open(self, account: SMTPAccount) -> None:
        # getaddrinfo has no socket timeout. Bound callers and outstanding daemon
        # lookups: at most two can remain in the OS resolver after cancellation.
        if not _RESOLVERS.acquire(blocking=False):
            raise OSError("smtp_resolver_busy")
        result: queue.Queue[Sequence[tuple[int, int, int, str, tuple[object, ...]]] | OSError]
        result = queue.Queue(maxsize=1)

        def resolve() -> None:
            try:
                result.put(socket.getaddrinfo(account.host, account.port, type=socket.SOCK_STREAM))
            except OSError as error:
                result.put(error)
            finally:
                _RESOLVERS.release()

        Thread(target=resolve, daemon=True, name="smtp-dns").start()
        while True:
            try:
                addresses = result.get(timeout=min(0.05, self.remaining()))
                break
            except queue.Empty:
                continue
        if isinstance(addresses, OSError):
            raise OSError("smtp_dns_failure") from None
        for family, kind, protocol, _, address in addresses[:8]:
            connection = socket.socket(family, kind, protocol)
            self.active.replace(None, connection)
            self.sock = connection
            try:
                connection.settimeout(self.remaining())
                connection.connect(address)
                break
            except OSError:
                self.active.discard(connection)
                self.sock = None
        if self.sock is None:
            raise OSError("smtp_connect_failure")
        if account.tls_mode == "implicit":
            self.secure(account)
        code, _ = self.getreply()
        self.require(code, 220)

    def secure(self, account: SMTPAccount) -> None:
        assert self.sock is not None
        context = ssl.create_default_context(cafile=account.ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.sock.settimeout(self.remaining())
        # Register the wrapped socket BEFORE the handshake, so shutdown can close it.
        with self.active.lock:
            old = self.sock
            if self.active.stopped.is_set():
                raise OSError("smtp_cancelled")
            self.sock = context.wrap_socket(
                old, server_hostname=account.host, do_handshake_on_connect=False
            )
            self.active.sockets.discard(old)
            self.active.sockets.add(self.sock)
        self.sock.settimeout(self.remaining())
        self.sock.do_handshake()

    @staticmethod
    def require(code: int, expected: int) -> None:
        if code != expected:
            raise smtplib.SMTPResponseException(code, b"smtp_rejected")

    def close(self) -> None:
        if self.sock is not None:
            self.active.discard(self.sock)
            self.sock = None


def transmit(
    account: SMTPAccount,
    item: FrozenDelivery,
    before_data: Callable[[], bool],
    *,
    active: ActiveTransports | None = None,
    budget: float = ATTEMPT_SECONDS,
) -> Outcome | None:
    """Return fixed outcomes only; None means the SQL eligibility fence refused."""
    active = active or ActiveTransports()
    smtp = _SMTP(time.monotonic() + min(ATTEMPT_SECONDS, max(0.0, budget)), active)
    transmitting = False
    try:
        smtp.open(account)
        smtp.require(smtp.ehlo()[0], 250)
        if account.tls_mode == "starttls":
            if not smtp.has_extn("starttls"):
                return "permanent"
            smtp.require(smtp.docmd("STARTTLS")[0], 220)
            smtp.secure(account)
            # Explicit fresh EHLO discards all untrusted pre-TLS capabilities.
            smtp.esmtp_features = {}
            smtp.require(smtp.ehlo()[0], 250)
        smtp.login(account.username.get_secret_value(), account.password.get_secret_value())
        smtp.require(smtp.mail(item.envelope_from)[0], 250)
        code, _ = smtp.rcpt(item.envelope_to)
        if code not in (250, 251):
            smtp.require(code, 250)
        smtp.remaining()
        if not before_data():
            return None
        transmitting = True  # SQL is committed to transmitting before any DATA I/O.
        smtp.remaining()  # The DB fence may have waited; never reuse the old budget.
        code, _ = smtp.data(item.wire)  # stdlib dot-stuffs the frozen CRLF bytes.
        if code == 250:
            # Closing directly avoids any cleanup round-trip delaying persistence.
            return "accepted"
        smtp.require(code, 250)
    except smtplib.SMTPResponseException as error:
        if 400 <= error.smtp_code <= 499:
            return "temporary"
        if 500 <= error.smtp_code <= 599:
            return "permanent"
        return "data_unknown" if transmitting else "transport"
    except (OSError, smtplib.SMTPException, ValueError):
        return "data_unknown" if transmitting else "transport"
    finally:
        smtp.close()
    return "data_unknown" if transmitting else "transport"


def deliver_once(
    engine: Engine,
    delivery_id: UUID,
    accounts: dict[UUID, SMTPAccount],
    *,
    active: ActiveTransports | None = None,
) -> bool:
    if active is not None and active.stopped.is_set():
        return False
    began = time.monotonic()
    claimed = mail_delivery.claim(engine, accounts, identifier=delivery_id)
    if claimed is None:
        return False
    item = mail_delivery.frozen_delivery(engine, delivery_id, claimed.token)
    if item is None:
        return False
    # SQL alone decides lease expiry. Charge preparation time to the finite
    # monotonic attempt budget, leaving the other half of its lease to persist.
    budget = ATTEMPT_SECONDS - (time.monotonic() - began)
    outcome: Outcome | None = "transport"
    if budget > 0:
        outcome = transmit(
            accounts[claimed.source_id],
            item,
            lambda: mail_delivery.pre_data(engine, delivery_id, claimed.token),
            active=active,
            budget=budget,
        )
    if outcome is None:
        return False
    return mail_delivery.finalize(engine, delivery_id, claimed.token, outcome)
