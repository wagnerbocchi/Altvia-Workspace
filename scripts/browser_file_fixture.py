"""Disposable browser scan-protocol fault fixture; never signed ClamAV acceptance."""

import argparse
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Event, Thread
from uuid import UUID

from altvia import attachment_scan
from altvia.config import Settings
from altvia.database import make_engine
from altvia.file_scan_transport import ClamClient
from altvia.file_settings import ScannerSettings
from altvia.file_storage import S3Store
from altvia.file_storage_owner import load_storage
from altvia.models import Attachment, AttachmentScanAttempt, MailTriageCase, Ticket, WorkItem
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("id", type=UUID)
    parser.add_argument("result", choices=["clean", "infected", "failed"])
    parser.add_argument("--hold", type=int, default=0, choices=range(31))
    args = parser.parse_args()
    settings = Settings()
    if (
        os.environ.get("ALTVIA_ALLOW_TEST_DB") != "1"
        or os.environ.get("ALTVIA_E2E_FILE_PROTOCOL") != "1"
        or settings.public_origin != "https://127.0.0.1:3443"
        or make_url(settings.database_url.get_secret_value()).database != "altvia_test"
    ):
        raise SystemExit("Explicit disposable browser protocol fixture required")
    if not hasattr(socket, "AF_UNIX"):
        # Windows Python has no AF_UNIX. The same guarded owner script runs in
        # the isolated local Podman VM using its real loopback test services.
        env_file = Path(os.environ["ALTVIA_FILE_PROTOCOL_CONTAINER_ENV"])
        private = env_file.parent
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                "podman",
                "run",
                "--rm",
                "--pull=never",
                "--network",
                "host",
                "--cgroups=disabled",
                "--read-only",
                "--tmpfs",
                "/tmp:size=32m",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "-v",
                f"{root}:/workspace:ro",
                "-v",
                f"{private}:/run/secrets:ro",
                "--env-file",
                str(env_file),
                "-e",
                "ALTVIA_E2E_NOTE_QUEUE_ID",
                "-w",
                "/workspace",
                "--entrypoint",
                "python",
                "localhost/altvia-task2:complete-test",
                "scripts/browser_file_fixture.py",
                *sys.argv[1:],
            ],
            capture_output=True,
            check=False,
        )
        sys.stdout.buffer.write(result.stdout)
        sys.stderr.buffer.write(result.stderr)
        raise SystemExit(result.returncode)
    engine = make_engine(settings)
    with Session(engine) as db:
        row = db.get(Attachment, args.id)
        if row is None or not row.filename.startswith("browser-file-"):
            raise SystemExit("Named synthetic attachment required")
        if row.ticket_id:
            parent = db.get(Ticket, row.ticket_id)
            if not parent or not parent.subject.startswith("Delivery synthetic files "):
                raise SystemExit("Named synthetic ticket required")
        elif row.work_item_id:
            parent = db.get(WorkItem, row.work_item_id)
            if not parent or not parent.title.startswith("Browser file work "):
                raise SystemExit("Named synthetic work required")
        elif row.mail_case_id:
            parent = db.get(MailTriageCase, row.mail_case_id)
            if (
                not parent
                or not parent.subject.startswith("Browser incoming files ")
                or parent.queue_id != UUID(os.environ["ALTVIA_E2E_NOTE_QUEUE_ID"])
                or row.purpose != "incoming"
                or row.creator_id is not None
            ):
                raise SystemExit("Named synthetic incoming case required")
        else:
            raise SystemExit("Concrete synthetic parent required")
        # With scanner storage removed only from the browser worker environment,
        # no file actor exists and dispatch returns before enqueueing any claim.
        assert row.state == "quarantine" and row.attempts == 0
        assert row.lease_token is None and row.lease_until is None
    storage = S3Store(load_storage(Path(os.environ["ALTVIA_FILE_PROTOCOL_STORAGE_FILE"])))
    try:
        for index in range(8 if args.result == "failed" else 1):
            if index:
                # Controlled owner scheduling fault removes waiting only. The real
                # protocol, claim, lease, history and state transition still run.
                with engine.begin() as connection:
                    connection.execute(
                        text("ALTER TABLE attachments DISABLE TRIGGER attachment_guard")
                    )
                    connection.execute(
                        text(
                            "UPDATE attachments SET next_attempt_at=clock_timestamp() WHERE id=:id"
                        ),
                        {"id": args.id},
                    )
                    connection.execute(
                        text("ALTER TABLE attachments ENABLE TRIGGER attachment_guard")
                    )
            claim = attachment_scan.claim(engine, args.id)
            assert claim is not None and claim.attempt == index + 1
            assert attachment_scan.claim(engine, args.id) is None
            if args.hold and index == 0:
                time.sleep(args.hold)
            replies = [
                f"ClamAV 1.4.6/28181/{claim.db_now.strftime('%a %b %d %H:%M:%S %Y')}\0".encode(),
                b"stream: Eicar-Test-Signature FOUND\0"
                if args.result == "infected"
                else b"stream: synthetic ERROR\0"
                if args.result == "failed"
                else b"stream: OK\0",
            ]
            replies.append(replies[0])
            with tempfile.TemporaryDirectory(prefix="av-") as directory:
                path = Path(directory) / "s"
                listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                listener.bind(str(path))
                listener.listen(4)
                listener.settimeout(5)
                received = []
                errors = []

                def serve(replies=replies, listener=listener, received=received, errors=errors):
                    try:
                        for reply in replies:
                            with listener.accept()[0] as conn:
                                conn.settimeout(5)
                                command = bytearray()
                                while not command.endswith(b"\0"):
                                    command.extend(conn.recv(1))
                                if command == b"zINSTREAM\0":
                                    body = bytearray()

                                    def exact(length):
                                        result = bytearray()
                                        while len(result) < length:
                                            part = conn.recv(length - len(result))
                                            if not part:
                                                raise ValueError("Truncated fixture stream")
                                            result.extend(part)
                                        return result

                                    while length := struct.unpack("!I", exact(4))[0]:
                                        body.extend(exact(length))
                                    received.append(bytes(body))
                                conn.sendall(reply)
                    except (OSError, ValueError) as error:
                        errors.append(type(error).__name__)
                    finally:
                        listener.close()

                thread = Thread(target=serve, daemon=True)
                thread.start()
                assert attachment_scan.run_claim(
                    engine, claim, storage, ClamClient(ScannerSettings(socket_path=path)), Event()
                )
                thread.join(timeout=6)
                assert not thread.is_alive() and not errors
                assert len(received) == 1 and len(received[0]) == claim.bytes
        with Session(engine) as db:
            row = db.get(Attachment, args.id)
            assert (
                row.state
                == {"clean": "ready", "infected": "rejected", "failed": "failed"}[args.result]
            )
            assert db.scalar(
                select(func.count())
                .select_from(AttachmentScanAttempt)
                .where(
                    AttachmentScanAttempt.attachment_id == args.id,
                    AttachmentScanAttempt.generation == row.generation,
                )
            ) == (8 if args.result == "failed" else 1)
        print("Controlled scan protocol completed; signed-engine acceptance not inferred")
    finally:
        storage.close()
        engine.dispose()


if __name__ == "__main__":
    main()
