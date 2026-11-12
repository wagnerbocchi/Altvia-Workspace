"""Trusted, bounded standard-library TLS relay for synthetic packaged proof only."""

import socketserver
import ssl
from contextlib import contextmanager
from threading import Event, Thread


@contextmanager
def synthetic_relay(cert, key, *, mode, port=20265):
    """Accept one isolated scenario: final250, lost final reply or held final reply."""
    assert mode in {"accepted", "lost", "held"}
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(5)
            sender = recipient = None
            self.wfile.write(b"220 synthetic loopback\r\n")
            for _ in range(12):
                line = self.rfile.readline(2049)
                if not line or len(line) > 2048:
                    return
                verb = line.split(b" ", 1)[0].strip().upper()
                if verb == b"EHLO":
                    self.wfile.write(b"250-loopback\r\n250 AUTH PLAIN\r\n")
                elif verb == b"AUTH":
                    self.wfile.write(b"235 synthetic authenticated\r\n")
                elif verb in {b"MAIL", b"RCPT"}:
                    mailbox = line.split(b"<", 1)[1].split(b">", 1)[0].decode("ascii")
                    if verb == b"MAIL":
                        sender = mailbox
                    else:
                        recipient = mailbox
                    self.wfile.write(b"250 synthetic envelope\r\n")
                elif verb == b"DATA":
                    self.server.data_count += 1
                    self.wfile.write(b"354 synthetic data\r\n")
                    body = bytearray()
                    while len(body) <= 262144:
                        part = self.rfile.readline(262147)
                        if part == b".\r\n":
                            break
                        if not part:
                            return
                        body.extend(part[1:] if part.startswith(b"..") else part)
                    else:
                        return
                    self.server.messages.append(bytes(body))
                    self.server.envelopes.append((sender, recipient))
                    self.server.received.set()
                    if mode == "held":
                        self.server.release.wait(30)
                        return
                    if mode == "lost":
                        return
                    self.wfile.write(b"250 synthetic accepted\r\n")
                    self.server.final_250_count += 1
                    self.server.accepted_reply.set()
                    return
                else:
                    return

    class Relay(socketserver.ThreadingTCPServer):
        daemon_threads = True
        block_on_close = False

        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(5)
            try:
                return context.wrap_socket(connection, server_side=True), address
            except OSError:
                connection.close()
                raise

        def handle_error(self, request, client_address):
            # Peer cancellation is expected. No raw protocol or credentials in logs.
            return

    with Relay(("127.0.0.1", port), Handler) as server:
        server.messages, server.envelopes = [], []
        server.data_count = server.final_250_count = 0
        server.received, server.release = Event(), Event()
        server.accepted_reply = Event()
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.release.set()
            server.shutdown()
            thread.join(2)
            assert not thread.is_alive()
