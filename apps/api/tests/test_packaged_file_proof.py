"""Negative controls for the real packaged checker paths, not positive AV proof."""

import ast
import base64
import importlib.util
import io
import json
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from altvia.file_storage import StorageError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_team_api import admin_client
from test_tickets import setup, ticket

__all__ = ["admin_client"]

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "packaged_file_proof", SCRIPTS / "packaged_file_proof.py"
)
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


def execute(nodes, namespace):
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), "proof", "exec"
        ),
        namespace,
    )


def test_combined_profile_refuses_missing_opt_in_and_small_vm(monkeypatch, tmp_path):
    monkeypatch.delenv("ALTVIA_ALLOW_CONTAINER_TEST", raising=False)
    with pytest.raises(RuntimeError, match="opt|synthetic"):
        proof.configure_files(None, "docker", {}, tmp_path)
    monkeypatch.setenv("ALTVIA_ALLOW_CONTAINER_TEST", "1")
    with pytest.raises(RuntimeError, match="Docker"):
        proof.configure_files(None, "podman", {}, tmp_path)
    called = []

    def run(command):
        called.append(command)
        return str(2 * 1024**3)

    with pytest.raises(RuntimeError, match="memory"):
        proof.configure_files(run, "docker", {}, tmp_path)
    assert len(called) == 1 and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name", ["OWNER_FILES", "PRIVILEGES", "SNAPSHOT", "OBJECTS"])
def test_embedded_container_programs_compile(name):
    compile(getattr(proof, name), name, "exec")


@pytest.mark.parametrize("failure", ["body", "filename", "media", "extra", "plain"])
def test_actual_smtp_checker_refuses_corrupt_or_private_mime(failure):
    tree = ast.parse((SCRIPTS / "packaged_smtp_proof.py").read_text(encoding="utf-8"))
    checker = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.If) and ast.unparse(n.test) == "'mime_files' in payload"
    )
    message = EmailMessage()
    message.set_content("public-body")
    message.add_attachment(b"public-file", maintype="text", subtype="plain", filename="public.txt")
    payload = {
        "body_text": "public-body",
        "mime_files": [
            {
                "filename": "public.txt",
                "media_type": "text/plain",
                "base64": base64.b64encode(b"public-file").decode(),
            }
        ],
    }
    execute([checker], {"message": message, "payload": payload})
    if failure == "body":
        payload["mime_files"][0]["base64"] = base64.b64encode(b"private-note-bytes").decode()
    elif failure == "filename":
        payload["mime_files"][0]["filename"] = "private-note-name.txt"
    elif failure == "media":
        payload["mime_files"][0]["media_type"] = "text/html"
    elif failure == "extra":
        message.add_attachment(
            b"private-note-bytes", maintype="text", subtype="plain", filename="note.txt"
        )
    else:
        message = EmailMessage()
        message.set_content("public-body")
    with pytest.raises(AssertionError):
        execute([checker], {"message": message, "payload": payload})


@pytest.mark.parametrize(
    "marker",
    [
        "file-name.txt",
        "file-bytes",
        "file-sha256",
        "objects/key",
        "private-note",
        "credential-secret",
    ],
)
def test_late_service_diagnostics_reject_file_canaries(marker):
    event_id = str(uuid4())
    logs = "safe"

    def run(command, **kwargs):
        if "logs" in command:
            return logs
        if "run" in command:
            return json.dumps({"event_ids": [event_id]})
        return json.dumps({"delivered_and_processed": True})

    context = {"ids": [str(uuid4())], "ticket_id": str(uuid4()), "markers": [marker]}
    result = proof.privacy_checkpoint(run, [], SCRIPTS.parent, context, "after-recreation")
    assert result["service_diagnostics_checked"]
    logs = json.dumps({"log": "first\n" + marker + "\nlast"})
    with pytest.raises(AssertionError):
        proof.privacy_checkpoint(run, [], SCRIPTS.parent, context, "after-recreation")


@pytest.mark.parametrize("corruption", [None, "length", "hash", "restore-bytes"])
def test_matching_object_export_restore_checks_actual_streamed_integrity(
    monkeypatch, capsys, corruption
):
    content = b"synthetic matching file bytes\n"
    key = "objects/" + "a" * 64
    row = {"object_key": key, "bytes": len(content), "sha256": proof.digest(content)}

    class SDK:
        def get_object(self, **kwargs):
            return {"ContentLength": len(content), "Body": io.BytesIO(content)}

        def put_object(self, **kwargs):
            assert kwargs["IfNoneMatch"] == "*"
            assert kwargs["Body"].read() == content

        def close(self):
            pass

    monkeypatch.setattr("altvia.file_storage.s3_client", lambda settings: SDK())
    monkeypatch.setattr("altvia.file_storage_owner.load_storage", lambda path: None)
    if corruption == "length":
        row["bytes"] += 1
    elif corruption == "hash":
        row["sha256"] = "b" * 64
    payload = {"mode": "export", "files": [row]}
    if corruption == "restore-bytes":
        payload["mode"] = "restore"
        row["base64"] = base64.b64encode(b"wrong").decode()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    if corruption:
        with pytest.raises(StorageError):
            exec(proof.OBJECTS, {})
        assert capsys.readouterr().out == ""
    else:
        exec(proof.OBJECTS, {})
        exported = json.loads(capsys.readouterr().out)
        assert base64.b64decode(exported[0]["base64"]) == content
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({"mode": "restore", "files": exported}))
        )
        exec(proof.OBJECTS, {})
        assert json.loads(capsys.readouterr().out) == exported


@pytest.mark.parametrize(
    "role,table,column,privilege",
    [
        ("altvia_worker", "attachments", "filename", "SELECT"),
        ("altvia_worker", "ticket_notes", "body_text", "SELECT"),
        ("altvia_worker", "ticket_note_attachments", "attachment_id", "SELECT"),
        ("altvia_app", "attachment_scan_attempts", "reason", "SELECT"),
        ("altvia_app", "attachments", "lease_token", "UPDATE"),
    ],
)
def test_actual_column_only_grant_is_detected(db_engine, role, table, column, privilege):
    tree = ast.parse(proof.PRIVILEGES)
    body = next(n for n in tree.body if isinstance(n, ast.With)).body[1:]
    temporary = "proof_" + uuid4().hex
    with db_engine.begin() as db:
        db.execute(text('CREATE ROLE "' + temporary + '"'))
        db.execute(text('GRANT USAGE ON SCHEMA public TO "' + temporary + '"'))
        db.execute(text('SET LOCAL ROLE "' + temporary + '"'))
        namespace = {
            "db": db,
            "p": {"role": role},
            "text": text,
            "DBAPIError": DBAPIError,
            "json": json,
        }
        execute(body, namespace)
        db.execute(text("RESET ROLE"))
        db.execute(text(f'GRANT {privilege} ({column}) ON {table} TO "{temporary}"'))
        db.execute(text('SET LOCAL ROLE "' + temporary + '"'))
        with pytest.raises(AssertionError):
            execute(body, namespace)
        db.execute(text("RESET ROLE"))
        db.execute(text('DROP OWNED BY "' + temporary + '"'))
        db.execute(text('DROP ROLE "' + temporary + '"'))


def test_new_file_ticket_reuses_current_sender_without_mutating_old_wire(
    admin_client,
    db_engine,
    seeded_user,
    monkeypatch,
    capsys,
):
    from altvia.mail_settings import SMTPAccount
    from altvia.models import MailSender, OutboundMessage
    from test_mail_delivery import enqueue
    from test_ticket_messages import append

    refs = setup(admin_client, db_engine, seeded_user)
    old_path = ticket(admin_client, refs)
    account = {
        "source_id": str(uuid4()),
        "host": "localhost",
        "port": 20265,
        "tls_mode": "implicit",
        "username": "synthetic-owner",
        "password": "synthetic-owner-secret",
        "from_email": "synthetic-support@example.test",
        "ca_file": None,
    }
    monkeypatch.setattr("altvia.database.make_engine", lambda settings: db_engine)

    def run(command, *, data=None):
        monkeypatch.setattr(sys, "stdin", io.StringIO(data))
        exec(command[-1], {})
        return capsys.readouterr().out

    old = proof.owner(
        run,
        [],
        proof.OWNER_SETUP,
        {
            "account": account,
            "ticket_id": old_path.rsplit("/", 1)[1],
            "queue_id": refs["queue_id"],
            "version": 1,
        },
    )
    account["source_id"] = old["source_id"]
    original_account = dict(account)
    message = append(admin_client, old_path).json()["message_id"]
    queued = enqueue(
        admin_client, old_path, message, SMTPAccount.model_validate(account), old["participant_id"]
    )
    assert queued.status_code == 201
    delivery_id = UUID(queued.json()["delivery_id"])
    with Session(db_engine) as db:
        delivery = db.get(OutboundMessage, delivery_id)
        frozen = (delivery.wire, delivery.smtp_message_id, delivery.created_at)
        sender = db.get(MailSender, UUID(old["source_id"]))
        sender_identity = (
            sender.source_id,
            sender.queue_id,
            sender.from_email,
            sender.namespace_hash,
        )
    new_path = ticket(admin_client, refs)
    new_account, new = proof.prepare_file_sender(
        run,
        [],
        new_path.rsplit("/", 1)[1],
        refs["queue_id"],
        account,
    )
    assert old_path != new_path and new["participant_id"] != old["participant_id"]
    assert new["source_id"] == old["source_id"] and new_account == account == original_account
    assert admin_client.get(new_path + "/delivery-choices").json()["can_send"]
    with Session(db_engine) as db:
        delivery = db.get(OutboundMessage, delivery_id)
        assert (delivery.wire, delivery.smtp_message_id, delivery.created_at) == frozen
        sender = db.get(MailSender, UUID(old["source_id"]))
        assert (
            sender.source_id,
            sender.queue_id,
            sender.from_email,
            sender.namespace_hash,
        ) == sender_identity


def browser_diagnostic():
    return {
        "schema": 1,
        "phase": "scan_metadata",
        "file_slot": 1,
        "http_status": 201,
        "scan_state": "unknown",
        "page_errors": 0,
        "error_kind": "browser",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("phase", "private-filename.txt"),
        ("scan_state", "private-note-bytes"),
        ("error_kind", "https://private/?credential=secret"),
        ("extra", "objects/private-key"),
        ("file_slot", True),
        ("file_slot", 4),
        ("http_status", 600),
        ("http_status", 99),
        ("page_errors", -1),
        ("schema", True),
        ("phase", ["private-data"]),
    ],
)
def test_browser_diagnostic_strict_parent_rejects_disclosure_and_malformed_values(
    tmp_path, field, value
):
    data = browser_diagnostic()
    data[field] = value
    with pytest.raises(ValueError, match="Invalid bounded"):
        proof.validate_browser_diagnostic(data)
    (tmp_path / "file-browser-diagnostic.private.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    proof.export_browser_failure(tmp_path)
    assert json.loads((tmp_path / "file-browser-failure.json").read_text()) == {
        "schema": 1,
        "diagnostic_status": "invalid",
    }


@pytest.mark.parametrize(
    "raw",
    [b"{", b"[]", b"\xff", b" " * 2049, b'{"phase":"private-secret","phase":"scan_metadata"}'],
)
def test_browser_diagnostic_invalid_encoding_size_and_duplicate_fields_are_not_exported(
    tmp_path, raw
):
    (tmp_path / "file-browser-diagnostic.private.json").write_bytes(raw)
    proof.export_browser_failure(tmp_path)
    assert json.loads((tmp_path / "file-browser-failure.json").read_text()) == {
        "schema": 1,
        "diagnostic_status": "invalid",
    }


def test_browser_failure_actual_child_preserves_nonzero_and_exports_only_validated_state(tmp_path):
    support = (SCRIPTS / "packaged_file_browser_support.mjs").as_uri()
    child = (
        "import {emitBrowserFailure,initialDiagnostic} from " + json.dumps(support) + ";"
        "const d=initialDiagnostic();d.phase='scan_metadata';d.file_slot=1;d.http_status=201;"
        "d.extra='private-note-filename-bytes-hash-key-credential';"
        "await emitBrowserFailure(process.argv[1],d,new Error(d.extra));"
    )
    original = None

    def run(command, **kwargs):
        nonlocal original
        assert command[0] == "node" and kwargs["timeout"] == 360
        result = subprocess.run(
            ["node", "--input-type=module", "-e", child, str(tmp_path)],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 1
        assert result.stdout == b"" and result.stderr == b"Packaged file browser proof failed.\n"
        original = subprocess.CalledProcessError(
            result.returncode, ["node"], result.stdout, result.stderr
        )
        raise original

    with pytest.raises(subprocess.CalledProcessError) as caught:
        proof.run_file_browser(run, tmp_path, {"session": "private-session-canary"})
    assert caught.value is original and caught.value.returncode == 1
    exported = json.loads((tmp_path / "file-browser-failure.json").read_text())
    assert exported == {
        "schema": 1,
        "diagnostic_status": "valid",
        "diagnostic": browser_diagnostic(),
    }
    assert "private-" not in json.dumps(exported)


def test_browser_failure_missing_diagnostic_remains_failure_with_explicit_unavailable_artifact(
    tmp_path,
):
    original = RuntimeError("fixed child failure")

    def run(*args, **kwargs):
        raise original

    with pytest.raises(RuntimeError) as caught:
        proof.run_file_browser(run, tmp_path, {})
    assert caught.value is original
    assert json.loads((tmp_path / "file-browser-failure.json").read_text()) == {
        "schema": 1,
        "diagnostic_status": "unavailable",
    }


def test_packaged_timeout_acceleration_preserves_completed_lifecycle(
    admin_client,
    db_engine,
    seeded_user,
    monkeypatch,
    capsys,
):
    from altvia import attachment_scan as scan
    from altvia.models import Attachment, AttachmentScanAttempt
    from sqlalchemy import select
    from test_attachments import upload

    parent = ticket(admin_client, setup(admin_client, db_engine, seeded_user))
    uploaded = upload(admin_client, parent, filename="timeout-packaged-owner.txt")
    assert uploaded.status_code == 201
    identifier = UUID(uploaded.json()["attachment_id"])
    payload = {"ids": [str(identifier)], "ticket_id": parent.rsplit("/", 1)[1]}
    monkeypatch.setattr("altvia.database.make_engine", lambda settings: db_engine)
    monkeypatch.setenv("ALTVIA_ALLOW_CONTAINER_TEST", "1")

    def run(command, *, data=None):
        monkeypatch.setattr(sys, "stdin", io.StringIO(data))
        if json.loads(data).get("accelerate"):
            assert "ALTVIA_ALLOW_CONTAINER_TEST=1" in command
        exec(command[-1], {})
        return capsys.readouterr().out

    claimed = scan.claim(db_engine, identifier)
    assert claimed is not None
    pending = proof.owner(run, [], proof.OWNER_FILES, payload)
    assert pending["files"][0]["state"] == "scanning" and pending["attempts"] == []
    with pytest.raises(AssertionError):
        proof.owner(run, [], proof.OWNER_FILES, {**payload, "accelerate": True})
    # Controlled negative result exercises the real DB lifecycle only. This
    # regression is not actual timeout/signed-scanner positive acceptance.
    assert scan.finalize(db_engine, claimed, scan.Failure("timeout"))
    completed = proof.owner(run, [], proof.OWNER_FILES, payload)
    assert completed["files"][0]["state"] == "quarantine"
    assert len(completed["attempts"]) == 1 and completed["attempts"][0]["reason"] == "timeout"
    with Session(db_engine) as db:
        row = db.get(Attachment, identifier)
        before = (row.version, row.state, row.attempts, row.generation, row.next_attempt_at)
        history = db.scalar(
            select(AttachmentScanAttempt).where(AttachmentScanAttempt.attachment_id == identifier)
        )
        immutable_history = (history.token, history.claimed_at, history.finished_at, history.reason)
    failure = None
    try:
        accelerated = proof.owner(run, [], proof.OWNER_FILES, {**payload, "accelerate": True})
    except DBAPIError as error:
        # RED evidence is bounded: never print live SQL parameters/identifiers.
        failure = (
            type(error).__name__,
            error.orig.sqlstate,
            "immutable_identity"
            if error.orig.diag.message_primary == "Immutable attachment identity"
            else "unclassified",
        )
    assert failure is None, f"Owner acceleration refused: {failure}"
    assert accelerated == completed
    with Session(db_engine) as db:
        row = db.get(Attachment, identifier)
        assert (row.version, row.state, row.attempts, row.generation) == before[:4]
        assert row.next_attempt_at < before[4]
        assert row.next_attempt_at <= db.scalar(text("SELECT clock_timestamp()"))
        history = db.scalar(
            select(AttachmentScanAttempt).where(AttachmentScanAttempt.attachment_id == identifier)
        )
        assert (
            history.token,
            history.claimed_at,
            history.finished_at,
            history.reason,
        ) == immutable_history
        assert (
            db.scalar(text("SELECT tgenabled FROM pg_trigger WHERE tgname='attachment_guard'"))
            == "O"
        )
    with pytest.raises(DBAPIError) as guarded:
        with db_engine.begin() as db:
            db.execute(
                text("UPDATE attachments SET next_attempt_at=clock_timestamp() WHERE id=:id"),
                {"id": identifier},
            )
    assert guarded.value.orig.sqlstate == "P0001"
    with monkeypatch.context() as missing_opt_in:
        missing_opt_in.delenv("ALTVIA_ALLOW_CONTAINER_TEST")
        with pytest.raises(RuntimeError, match="synthetic"):
            proof.owner(run, [], proof.OWNER_FILES, {**payload, "accelerate": True})
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({**payload, "accelerate": True})))
        with pytest.raises(AssertionError):
            exec(proof.OWNER_FILES, {})
    for refused in (
        {**payload, "ticket_id": str(uuid4()), "accelerate": True},
        {**payload, "ids": [str(identifier), str(identifier)], "accelerate": True},
    ):
        with pytest.raises(AssertionError):
            proof.owner(run, [], proof.OWNER_FILES, refused)


def test_packaged_timeout_acceleration_error_restores_guard_and_schedule(
    admin_client,
    db_engine,
    seeded_user,
    monkeypatch,
    capsys,
):
    from altvia import attachment_scan as scan
    from altvia.models import Attachment
    from sqlalchemy import event
    from test_attachments import upload

    parent = ticket(admin_client, setup(admin_client, db_engine, seeded_user))
    uploaded = upload(admin_client, parent, filename="timeout-rollback-owner.txt")
    assert uploaded.status_code == 201
    identifier = UUID(uploaded.json()["attachment_id"])
    claimed = scan.claim(db_engine, identifier)
    assert scan.finalize(db_engine, claimed, scan.Failure("timeout"))
    with Session(db_engine) as db:
        row = db.get(Attachment, identifier)
        before = (row.version, row.state, row.attempts, row.generation, row.next_attempt_at)
    monkeypatch.setattr("altvia.database.make_engine", lambda settings: db_engine)
    monkeypatch.setenv("ALTVIA_ALLOW_CONTAINER_TEST", "1")
    payload = {"ids": [str(identifier)], "ticket_id": parent.rsplit("/", 1)[1], "accelerate": True}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    disabled = False

    def fail_update(conn, cursor, statement, parameters, context, executemany):
        nonlocal disabled
        if statement.startswith("ALTER TABLE attachments DISABLE TRIGGER"):
            disabled = True
        if statement.startswith("UPDATE attachments SET next_attempt_at"):
            assert disabled
            raise RuntimeError("synthetic_schedule_failure")

    event.listen(db_engine, "before_cursor_execute", fail_update)
    try:
        with pytest.raises(RuntimeError, match="synthetic_schedule_failure"):
            exec(proof.OWNER_FILES, {})
    finally:
        event.remove(db_engine, "before_cursor_execute", fail_update)
    assert disabled
    with Session(db_engine) as db:
        row = db.get(Attachment, identifier)
        assert (row.version, row.state, row.attempts, row.generation, row.next_attempt_at) == before
        assert (
            db.scalar(text("SELECT tgenabled FROM pg_trigger WHERE tgname='attachment_guard'"))
            == "O"
        )
    with pytest.raises(DBAPIError) as guarded:
        with db_engine.begin() as db:
            db.execute(
                text("UPDATE attachments SET next_attempt_at=clock_timestamp() WHERE id=:id"),
                {"id": identifier},
            )
    assert guarded.value.orig.sqlstate == "P0001"


def test_packaged_saved_session_is_revoked_by_later_team_role_change(
    admin_client,
    db_engine,
    seeded_user,
):
    import os

    from altvia.file_storage import S3Store
    from altvia.file_storage_owner import load_storage
    from altvia.management import set_team_role
    from altvia.models import Attachment, TicketQueue
    from test_attachments import upload
    from test_team_api import sign_in

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    uploaded = upload(admin_client, parent)
    assert uploaded.status_code == 201
    identifier = uploaded.json()["attachment_id"]
    route = "/api/v1/attachments/" + identifier
    original_session = admin_client.cookies.get("__Host-altvia_session")
    file_proof = {
        "session": original_session,
        "author_id": str(seeded_user),
        "context": {"ticket_id": parent.rsplit("/", 1)[1], "markers": [original_session]},
        "browser": {"ids": [identifier, identifier]},
        "public_body": "private text\n",
        "note_body": "unused",
    }
    assert admin_client.get(route).status_code == 200
    # No fake-ready result: the real uploaded object remains quarantined.
    assert admin_client.get(route + "/content").status_code == 409
    with Session(db_engine) as db, db.begin():
        team = db.get(TicketQueue, UUID(refs["queue_id"])).team_id
        assert set_team_role(db, "employee@example.test", team, "viewer", True)
    assert admin_client.get("/api/v1/auth/me").status_code == 401
    assert admin_client.get(route).status_code == 401
    assert admin_client.get(route + "/content").status_code == 401
    with pytest.raises(AssertionError):
        proof.assert_current_access(admin_client, admin_client, file_proof)
    sign_in(admin_client, "employee@example.test")
    assert admin_client.cookies.get("__Host-altvia_session") != original_session
    proof.capture_current_file_author(admin_client, file_proof)
    assert file_proof["current_session"] in file_proof["context"]["markers"]
    assert original_session in file_proof["context"]["markers"]
    assert proof.select_current_file_author(admin_client, file_proof) == {
        "revoked_file_session_status": 401,
        "current_actor_bound": True,
    }
    assert admin_client.get(route).status_code == 200
    assert admin_client.get(route + "/content").status_code == 409
    with pytest.raises(AssertionError):
        proof.capture_current_file_author(admin_client, {**file_proof, "author_id": str(uuid4())})
    with pytest.raises(AssertionError):
        proof.select_current_file_author(
            admin_client, {**file_proof, "current_session": original_session}
        )
    proof.select_current_file_author(admin_client, file_proof)
    # Independently prove the actual S3 bytes survived the identity mutation.
    with Session(db_engine) as db:
        row = db.get(Attachment, UUID(identifier))
        store = S3Store(load_storage(Path(os.environ["ALTVIA_STORAGE_FILE"])))
        try:
            with store.verified_spool(row.object_key, size=row.bytes, sha256=row.sha256) as content:
                assert content.read() == b"private text\n"
        finally:
            store.close()


def test_snapshot_fourth_timeout_filename_is_rejected_by_actual_diagnostic_guard():
    fourth = "timeout-authoritative-" + uuid4().hex + ".txt"
    snapshot = {
        "files": [
            {"filename": "browser-public.txt", "key": "objects/first"},
            {"filename": "browser-note.txt", "key": "objects/second"},
            {"filename": "browser-eicar.txt", "key": "objects/third"},
            {"filename": fourth, "key": "objects/fourth"},
        ]
    }
    context = {
        "ids": [str(uuid4())],
        "ticket_id": str(uuid4()),
        "markers": proof.snapshot_file_markers(snapshot),
    }
    logs = "safe"

    def run(command, **kwargs):
        if "logs" in command:
            return logs
        if "run" in command:
            return json.dumps({"event_ids": [str(uuid4())]})
        return json.dumps({"delivered_and_processed": True})

    proof.privacy_checkpoint(run, [], SCRIPTS.parent, context, "after-recreation")
    logs = json.dumps({"details": {"filename": fourth}})
    with pytest.raises(AssertionError):
        proof.privacy_checkpoint(run, [], SCRIPTS.parent, context, "after-recreation")


@pytest.mark.parametrize(
    "relative",
    [
        "apps/api/migrations/versions/owner.py",
        "apps/api/migrations/env.py",
        "apps/api/migrations/script.py.mako",
        "apps/api/alembic.ini",
        "apps/web/src/app/globals.css",
        "apps/web/package.json",
        "apps/web/next.config.ts",
        "apps/web/tsconfig.json",
        "apps/web/next-env.d.ts",
        "apps/web/postcss.config.mjs",
        "package.json",
        "pnpm-workspace.yaml",
        ".dockerignore",
        "scripts/check_api_runtime.py",
        "scripts/check_web_native.mjs",
        "scripts/check_web_runtime.mjs",
        "scripts/container_tls.mjs",
        "apps/api/tests/imap_fixture.py",
        "infra/nginx.conf",
    ],
)
def test_source_inventory_detects_actual_build_and_proof_input_mutation(tmp_path, relative):
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("first input", encoding="utf-8")
    before = proof.source_hashes(tmp_path)
    target.write_text("other input", encoding="utf-8")
    after = proof.source_hashes(tmp_path)
    assert before[str(Path(relative))] != after[str(Path(relative))]
    assert before != after


def test_source_inventory_excludes_generated_private_and_operational_files(tmp_path):
    included = tmp_path / "apps/web/src/app/page.tsx"
    included.parent.mkdir(parents=True)
    included.write_text("source", encoding="utf-8")
    before = proof.source_hashes(tmp_path)
    for relative in (
        "apps/web/.next/cache/generated.ts",
        "apps/web/node_modules/package/index.ts",
        "apps/web/src/.next/generated.ts",
        "apps/api/altvia/__pycache__/generated.py",
        "apps/api/migrations/__pycache__/generated.py",
        "scripts/.env.private.py",
        "apps/web/src/.env.private.ts",
        "apps/web/tsconfig.tsbuildinfo",
        "infra/storage.key",
        "infra/smtp-accounts.json",
        "infra/production.conf",
        "infra/compose.local.yaml",
        ".env.browser-session",
        ".superpowers/private/owner.py",
        "docs/raw-client.xlsx",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("private/generated fixture", encoding="utf-8")
    assert proof.source_hashes(tmp_path) == before
