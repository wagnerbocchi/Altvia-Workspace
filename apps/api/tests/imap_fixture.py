"""Controlled loopback TLS IMAP fixture; no provider or external interface."""

import shlex
import socketserver
import ssl
from contextlib import contextmanager, suppress
from threading import Thread


@contextmanager
def imap_server(cert, key, messages=None):
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            state = self.server.state
            self.connection.settimeout(5)
            self.wfile.write(b"* OK controlled fixture\r\n")
            while line := self.rfile.readline(16385):
                # Commands stay in fixture memory, never test logs/artifacts.
                state["commands"].append(line)
                words = shlex.split(line.decode("ascii"))
                tag, command = words[:2]
                if command == "CAPABILITY":
                    self.wfile.write(b"* CAPABILITY IMAP4rev1\r\n")
                elif command == "LOGIN":
                    if words[2:] != [state["username"], state["password"]]:
                        self.wfile.write(f"{tag} NO refused\r\n".encode())
                        continue
                elif command == "EXAMINE":
                    assert words[2] == "INBOX"
                    self.wfile.write(f"* {len(state['messages'])} EXISTS\r\n".encode())
                    self.wfile.write(f"* OK [UIDVALIDITY {state['validity']}] stable\r\n".encode())
                    if not state.get("omit_next"):
                        self.wfile.write(f"* OK [UIDNEXT {state['next']}] next\r\n".encode())
                    self.wfile.write(b"* FLAGS (\\Seen)\r\n")
                elif command == "UID" and words[2] == "SEARCH":
                    if state.get("search_literal"):
                        raw = b"x" * 2097152
                        self.wfile.write(b"* 1 FETCH (UID 1 BODY[] {2097152}\r\n")
                        with suppress(OSError):
                            self.wfile.write(raw + b")\r\n")
                    if state.get("long_line"):
                        self.wfile.write(b"* SEARCH " + b"1 " * 9000 + b"\r\n")
                        return
                    start, end = map(int, words[-1].split(":"))
                    uids = state.get(
                        "search", sorted(u for u in state["messages"] if start <= u <= end)
                    )
                    self.wfile.write(
                        b"* SEARCH " + b" ".join(str(u).encode() for u in uids) + b"\r\n"
                    )
                    if state.get("search_epoch"):
                        self.wfile.write(
                            f"* OK [UIDVALIDITY {state['search_epoch']}] reset\r\n".encode()
                        )
                elif command == "UID" and words[2] == "FETCH":
                    if state.get("header_burst"):
                        self.wfile.write((b"* OK " + b"a" * 150 + b"\r\n") * 100)
                    uid = int(words[3])
                    assert "BODY.PEEK[]" in line.decode()
                    if state.get("fetch_hook"):
                        state["fetch_hook"](uid)
                    if uid not in state["messages"]:
                        self.wfile.write(f"{tag} OK vanished\r\n".encode())
                        continue
                    body = state["messages"][uid]
                    response_uid = state.get("response_uid", uid)
                    declared = state.get("declared", len(body))
                    before = f"UID {response_uid} " if not state.get("uid_after") else ""
                    self.wfile.write(f"* 1 FETCH ({before}BODY[] {{{declared}}}\r\n".encode())
                    if declared > 2097152:
                        return
                    if state.get("truncate_uid") == uid:
                        self.wfile.write(body[:1])
                        return
                    self.wfile.write(body)
                    after = f" UID {response_uid}" if state.get("uid_after") else ""
                    self.wfile.write(f"{after})\r\n".encode())
                    if state.get("extra_literal"):
                        with suppress(OSError):
                            self.wfile.write(b"* 1 FETCH (UID 1 BODY[] {2097152}\r\n")
                            self.wfile.write(b"x" * 2097152 + b")\r\n")
                    if state.get("session_validity"):
                        self.wfile.write(
                            f"* OK [UIDVALIDITY {state['session_validity']}] reset\r\n".encode()
                        )
                else:
                    raise AssertionError("Unexpected state-changing fixture command")
                self.wfile.write(f"{tag} OK done\r\n".encode())

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server = Server(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    source = messages or {1: b"From: unverified@example.test\r\n\r\nOpaque input\x00\xff"}
    server.state = {
        "messages": source,
        "validity": 1,
        "next": max(source) + 1,
        "commands": [],
        "username": 'synthetic user"name',
        "password": "synthetic pass\\word",
    }
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
