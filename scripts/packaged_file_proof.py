"""Combined packaged file acceptance. Disposable fixtures; no production operations.

The host owns lifecycle and HTTPS, the existing worker owns every scan/SMTP
result. Only synthetic scheduling timestamps are accelerated for failure tests.
Snapshot contents and credentials remain private; exported proof is hash-bound.
"""

import base64
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlsplit
from uuid import uuid4

from packaged_smtp_proof import (
    OWNER_SETUP,
    assert_worker_diagnostics,
    worker_probe_command,
)
from private_file_infra_proof import require_capacity


def require_opt_in():
    if os.environ.get("ALTVIA_ALLOW_CONTAINER_TEST") != "1":
        raise RuntimeError("Explicit synthetic container test required")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def validate_browser_diagnostic(data):
    """Strict public allowlist; even a compromised child cannot export context."""
    fields = {
        "schema",
        "phase",
        "file_slot",
        "http_status",
        "scan_state",
        "page_errors",
        "error_kind",
    }
    phases = {
        "unknown",
        "launch",
        "context",
        "cookie",
        "navigate",
        "select_file",
        "upload",
        "scan_metadata",
        "refresh_files",
        "rejected_block",
        "download",
        "select_note",
        "note_fill",
        "note_save",
        "note_reload",
        "select_public",
        "draft_fill",
        "draft_review",
        "draft_save",
        "send_review",
        "send_confirm",
        "incoming_navigate",
        "incoming_review",
        "incoming_promote",
        "incoming_conversation",
        "complete",
        "close",
    }
    states = {"unknown", "invalid", "quarantine", "scanning", "ready", "rejected", "failed"}
    if (
        type(data) is not dict
        or set(data) != fields
        or type(data["schema"]) is not int
        or data["schema"] != 1
        or type(data["phase"]) is not str
        or data["phase"] not in phases
        or type(data["scan_state"]) is not str
        or data["scan_state"] not in states
        or type(data["error_kind"]) is not str
        or data["error_kind"] not in {"assertion", "timeout", "browser"}
    ):
        raise ValueError("Invalid bounded browser diagnostic")
    for field, maximum in (("file_slot", 3), ("http_status", 599), ("page_errors", 1000)):
        if type(data[field]) is not int or not 0 <= data[field] <= maximum:
            raise ValueError("Invalid bounded browser diagnostic")
    if 0 < data["http_status"] < 100:
        raise ValueError("Invalid bounded browser diagnostic")
    return dict(data)


def export_browser_failure(work):
    """Private child input becomes an explicit validated failure-only artifact."""

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate diagnostic field")
            result[key] = value
        return result

    result = {"schema": 1, "diagnostic_status": "unavailable"}
    try:
        with (work / "file-browser-diagnostic.private.json").open("rb") as source:
            raw = source.read(2049)
        if len(raw) > 2048:
            raise ValueError("Oversized diagnostic")
        data = json.loads(raw, object_pairs_hook=unique_object)
        result = {
            "schema": 1,
            "diagnostic_status": "valid",
            "diagnostic": validate_browser_diagnostic(data),
        }
    except OSError:
        pass
    except (ValueError, TypeError, UnicodeError, RecursionError):
        result["diagnostic_status"] = "invalid"
    (work / "file-browser-failure.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )


def run_file_browser(run, work, payload):
    try:
        return json.loads(
            run(
                ["node", "scripts/packaged_file_browser.mjs", str(work)],
                data=json.dumps(payload),
                timeout=360,
            )
        )
    except Exception:
        try:
            export_browser_failure(work)
        except OSError:
            pass  # Failure to persist diagnostics cannot replace the child error.
        raise  # Retain the original child failure, never normalize it to success.


def source_hashes(root):
    """Current explicit local COPY/context/Compose and invoked proof/check inputs.

    Patterns follow infra/*.Dockerfile and .dockerignore, not a custom ignore
    parser. Downloaded inputs are separately pinned/inventoried by those builds.
    """
    patterns = (
        "apps/api/altvia/*.py",
        "apps/api/migrations/**/*.py",
        "apps/api/migrations/*.mako",
        "apps/web/src/**/*.ts",
        "apps/web/src/**/*.tsx",
        "apps/web/src/**/*.css",
        "infra/*.Dockerfile",
        "infra/*.sh",
        "infra/*.go.mod",
        "infra/*.go.sum",
        "scripts/*.py",
        "scripts/*.mjs",
        "scripts/*.sh",
        "apps/api/tests/test_packaged*.py",
    )
    paths = {p for pattern in patterns for p in root.glob(pattern)}
    paths.update(
        root / name
        for name in (
            ".dockerignore",
            "pyproject.toml",
            "uv.lock",
            "package.json",
            "pnpm-lock.yaml",
            "pnpm-workspace.yaml",
            "apps/api/alembic.ini",
            "apps/api/tests/imap_fixture.py",
            "apps/api/tests/test_file_storage.py",
            "apps/api/tests/test_file_scan_transport.py",
            "apps/api/tests/test_private_file_infra_proof.py",
            "apps/web/package.json",
            "apps/web/next.config.ts",
            "apps/web/tsconfig.json",
            "apps/web/next-env.d.ts",
            "apps/web/postcss.config.mjs",
            "infra/nginx.conf",
            "infra/clamd.conf",
            "infra/freshclam.conf",
            "infra/compose.yaml",
            "infra/compose.files.yaml",
            "infra/compose.smtp.yaml",
            ".github/workflows/container-ci.yml",
        )
    )
    generated = {"node_modules", ".next", "__pycache__", ".pytest_cache", ".git", ".superpowers"}
    return {
        str(p.relative_to(root)): digest(p.read_bytes())
        for p in sorted(paths)
        if p.is_file()
        and not any(
            part in generated or part.startswith(".env") for part in p.relative_to(root).parts
        )
        and p.suffix not in {".pem", ".key"}
    }


def inventory_files(run, compose, engine, project, work):
    """Record actual image/native identity and enforced new-service boundaries."""
    inventory = {}
    for service, network, memory, cpus, pids in (
        ("storage", "objects", 256, 1_000_000_000, 128),
        ("clamd", "scan", 2048, 2_000_000_000, 64),
        ("freshclam", "definition_download", 1536, 1_000_000_000, 32),
    ):
        identifier = run([*compose, "ps", "-q", service]).strip()
        host = json.loads(run([engine, "inspect", "--format", "{{json .HostConfig}}", identifier]))
        assert (
            run([engine, "inspect", "--format", "{{.Config.User}}", identifier]).strip()
            == "10001:10001"
        )
        assert (
            host["ReadonlyRootfs"] and not host.get("Privileged") and not host.get("PortBindings")
        )
        assert "ALL" in [v.upper().removeprefix("CAP_") for v in host["CapDrop"]]
        assert any("no-new-privileges" in v for v in host["SecurityOpt"])
        networks = json.loads(
            run([engine, "inspect", "--format", "{{json .NetworkSettings.Networks}}", identifier])
        )
        assert set(networks) == {project + "_" + network}
        internal = run(
            [engine, "network", "inspect", "--format", "{{.Internal}}", project + "_" + network]
        ).strip()
        assert internal == ("false" if service == "freshclam" else "true")
        assert (
            host["Memory"] == memory * 1024**2
            and host["NanoCpus"] == cpus
            and host["PidsLimit"] == pids
        )
        controls = run(
            [
                *compose,
                "exec",
                "-T",
                service,
                "sh",
                "-ec",
                "cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max /sys/fs/cgroup/pids.max; "
                "grep '^CapEff:' /proc/self/status",
            ]
        ).splitlines()
        assert int(controls[0]) == memory * 1024**2 and int(controls[2]) == pids
        quota, period = map(int, controls[1].split())
        assert quota * 1_000_000_000 == cpus * period
        assert controls[3].split() == ["CapEff:", "0000000000000000"]
        inventory[service] = {
            "image": run([engine, "inspect", "--format", "{{.Image}}", identifier]).strip(),
            "nonroot_readonly_private": True,
            "actual_cgroup_limits": True,
        }
    for service in ("api", "postgres", "web", "redis", "ingress", "worker"):
        identifier = run([*compose, "ps", "-q", service]).strip()
        inventory[service] = {
            "image": run([engine, "inspect", "--format", "{{.Image}}", identifier]).strip()
        }
    storage = run(
        [
            *compose,
            "exec",
            "-T",
            "storage",
            "sh",
            "-ec",
            "cat /usr/share/altvia-storage/packages.txt "
            "/usr/share/altvia-storage/go-build-info.txt /usr/share/altvia-storage/toolchain.txt "
            "/usr/share/altvia-storage/binary.sha256",
        ]
    )
    scanner = run(
        [
            *compose,
            "exec",
            "-T",
            "clamd",
            "sh",
            "-ec",
            "clamd --version; cat /usr/share/altvia-clamav/packages.txt "
            "/usr/share/altvia-clamav/native.sha256; "
            "for f in /var/lib/clamav/*.cvd /var/lib/clamav/*.cld; do "
            'test -f "$f" || continue; sha256sum "$f"; sigtool --info "$f"; done',
        ]
    )
    assert "GOAMD64=v1" in storage and "CGO_ENABLED=0" in storage and "clamav" in scanner.lower()
    for name, value in (("storage", storage), ("clamav", scanner)):
        (work / ("file-inventory-" + name + ".txt")).write_text(value, encoding="utf-8")
        inventory[name + "_inventory_sha256"] = digest(value.encode())
    return inventory


def configure_files(run, engine, env, secret_dir):
    require_opt_in()
    if engine != "docker":
        raise RuntimeError("Combined signed profile requires adequately provisioned Docker")
    require_capacity(int(run([engine, "info", "--format", "{{.MemTotal}}"])))
    env["ALTVIA_ALLOW_FILE_INFRA_TEST"] = "1"
    run(["node", "scripts/file_test_certificate.mjs", str(secret_dir)])
    for role in ("owner", "api", "scanner"):
        config = {
            "endpoint": "https://storage:8443",
            "ca_file": "/run/secrets/storage_ca",
            "access_key": secrets.token_hex(16),
            "secret_key": secrets.token_hex(32),
        }
        (secret_dir / ("storage_" + role)).write_text(json.dumps(config), encoding="utf-8")
        if role == "owner":
            (secret_dir / "storage_root_access").write_text(config["access_key"])
            (secret_dir / "storage_root_secret").write_text(config["secret_key"])
    for path in secret_dir.glob("storage_*"):
        path.chmod(0o444)


def start_files(run, compose):
    run([*compose, "up", "-d", "--no-build", "--wait", "storage"])
    run([*compose, "run", "--rm", "--no-deps", "-T", "storage-bootstrap"])
    run([*compose, "run", "--rm", "--no-deps", "freshclam", "--stdout"], timeout=1200)
    run(
        [*compose, "up", "-d", "--no-build", "--wait", "--wait-timeout", "300", "clamd"],
        timeout=420,
    )


def owner(run, compose, code, payload=None):
    fixture_environment = []
    if payload and payload.get("accelerate") is True:
        require_opt_in()
        fixture_environment = ["-e", "ALTVIA_ALLOW_CONTAINER_TEST=1"]
    return json.loads(
        run(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                *fixture_environment,
                "migrate",
                "python",
                "-c",
                code,
            ],
            data=json.dumps(payload),
        )
    )


def storage_checkpoint(run, compose, previous=None):
    """Reuse the native owner proof with THIS stack's actual mounted credentials."""
    return json.loads(
        run(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "-e",
                "ALTVIA_ALLOW_FILE_INFRA_TEST=1",
                "file-infra-proof",
                "--inside",
                "storage",
            ],
            data=json.dumps(previous or {}),
        )
    )


OWNER_FILES = """
import json,os,sys
from uuid import UUID
from sqlalchemy import select,text,func,update
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.models import Attachment,AttachmentScanAttempt,OutboxEvent,AuditLog,ActivityEvent
p=json.load(sys.stdin)
with Session(make_engine(DatabaseSettings())) as db,db.begin():
    ids=[UUID(v) for v in p['ids']]
    if p.get('accelerate'):
        assert p['accelerate'] is True and os.environ.get('ALTVIA_ALLOW_CONTAINER_TEST')=='1'
        assert len(ids)==1
        assert db.scalar(text("SELECT current_database()='altvia_test' AND "
            "current_user=pg_get_userbyid(relowner) FROM pg_class "
            "WHERE oid='attachments'::regclass"))
        # Owner-only synthetic due-time fixture, matching test_attachment_scan.
        # The exclusive lock/DDL/update/reenable share this transaction. No
        # concurrent writer sees an unguarded table; any error rolls back DDL.
        db.execute(text('LOCK TABLE attachments IN ACCESS EXCLUSIVE MODE'))
        row=db.get(Attachment,ids[0])
        assert row is not None and row.ticket_id==UUID(p['ticket_id'])
        assert row.purpose=='public' and row.filename.startswith('timeout-')
        assert row.state=='quarantine' and 1<=row.attempts<8
        finished=db.get(AttachmentScanAttempt,(row.id,row.generation,row.attempts))
        assert finished is not None and finished.reason=='timeout'
        db.execute(text('ALTER TABLE attachments DISABLE TRIGGER attachment_guard'))
        db.execute(update(Attachment.__table__).where(
            Attachment.id==row.id,Attachment.ticket_id==row.ticket_id
        ).values(next_attempt_at=func.clock_timestamp()))
        db.execute(text('ALTER TABLE attachments ENABLE TRIGGER attachment_guard'))
    files=[{'id':str(r.id),'filename':r.filename,'bytes':r.bytes,'sha256':r.sha256,
            'key':r.object_key,'purpose':r.purpose,'state':r.state,'generation':r.generation}
           for r in db.scalars(select(Attachment).where(Attachment.id.in_(ids))
                               .order_by(Attachment.id))]
    attempts=[{'id':str(r.attachment_id),'generation':r.generation,'attempt':r.attempt,
               'reason':r.reason,'engine':r.engine,'database_version':r.database_version,
               'database_date':r.database_date.isoformat() if r.database_date else None}
              for r in db.scalars(select(AttachmentScanAttempt).where(
                  AttachmentScanAttempt.attachment_id.in_(ids)).order_by(
                  AttachmentScanAttempt.attachment_id,AttachmentScanAttempt.generation,
                  AttachmentScanAttempt.attempt))]
    for model,column in ((OutboxEvent,OutboxEvent.payload),(AuditLog,AuditLog.details),
                          (ActivityEvent,ActivityEvent.details)):
        for value in db.scalars(select(column)):
            serialized=json.dumps(value)
            assert all(v not in serialized for v in p.get('markers',[]))
    events=[str(v) for v in db.scalars(select(OutboxEvent.event_id).where(
        OutboxEvent.aggregate_id.in_(ids+[UUID(p['ticket_id'])]+
                                    [UUID(v) for v in p.get('extra_aggregate_ids',[])])))]
    assert files and events
    print(json.dumps({'files':files,'attempts':attempts,'event_ids':events}))
"""

PRIVILEGES = """
import json,sys
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from altvia.config import DatabaseSettings
from altvia.database import make_engine
p=json.load(sys.stdin)
with make_engine(DatabaseSettings()).connect() as db:
    assert db.scalar(text('SELECT current_user'))==p['role']
    checks=[]
    for table in ('mailbox_sources','inbound_mail_envelopes','inbound_mail_variants',
                  'mailbox_poll_states','inbound_mail_previews','mail_case_origins'):
        for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
            assert not db.scalar(text('SELECT has_table_privilege(current_user,:t,:p)'),
                                 {'t':table,'p':privilege})
            if privilege!='DELETE':
                assert not db.scalar(text('SELECT has_any_column_privilege(current_user,:t,:p)'),
                                     {'t':table,'p':privilege})
        checks.append('SELECT * FROM '+table+' LIMIT 0')
    if p['role']=='altvia_worker':
        for table in ('ticket_notes','ticket_note_attachments','ticket_message_attachments',
                      'work_comment_attachments','mail_triage_cases','ticket_incoming_messages'):
            for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
                assert not db.scalar(text('SELECT has_table_privilege(current_user,:t,:p)'),
                                     {'t':table,'p':privilege})
                if privilege!='DELETE':
                    assert not db.scalar(text(
                        'SELECT has_any_column_privilege(current_user,:t,:p)'),
                                         {'t':table,'p':privilege})
            checks.append('SELECT * FROM '+table+' LIMIT 0')
        for column in ('filename','purpose','creator_id','ticket_id','work_item_id',
                       'mail_case_id','file_position'):
            assert not db.scalar(text(
                "SELECT has_column_privilege(current_user,'attachments',:c,'SELECT')"),
                {'c':column})
            checks.append('SELECT '+column+' FROM attachments LIMIT 0')
    else:
        for column in ('source_id','primary_variant_id','file_count','file_rejection_reason'):
            assert not db.scalar(text(
                "SELECT has_column_privilege(current_user,'mail_triage_cases',:c,'SELECT')"),
                {'c':column})
            checks.append('SELECT '+column+' FROM mail_triage_cases LIMIT 0')
        for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
            assert not db.scalar(text(
                "SELECT has_table_privilege(current_user,'attachment_scan_attempts',:p)"),
                {'p':privilege})
            if privilege!='DELETE':
                assert not db.scalar(text(
                    "SELECT has_any_column_privilege(current_user,'attachment_scan_attempts',:p)"),
                    {'p':privilege})
        checks.append('SELECT * FROM attachment_scan_attempts LIMIT 0')
        for column in ('lease_token','lease_until'):
            assert not db.scalar(text(
                "SELECT has_column_privilege(current_user,'attachments',:c,'UPDATE')"),
                {'c':column})
            checks.append('UPDATE attachments SET '+column+'='+column+' WHERE false')
    for sql in checks:
        try:
            with db.begin_nested(): db.execute(text(sql))
        except DBAPIError as error: assert error.orig.sqlstate=='42501'
        else: raise AssertionError('Private query succeeded')
    print(json.dumps({'role':p['role'],'actual_queries':len(checks),
                      'table_and_column_denials':True}))
"""


def wait_state(client, identifier, expected, *, timeout=150):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get("/api/v1/attachments/" + identifier)
        assert response.status_code == 200
        if response.json()["state"] == expected:
            return response.json()
        time.sleep(0.5)
    raise RuntimeError("Packaged file state did not reach expected result")


def privacy_checkpoint(run, compose, root, context, phase):
    snapshot = owner(run, compose, OWNER_FILES, context)
    markers = context["markers"]
    code = (root / "scripts/packaged_smtp_proof.py").read_text(encoding="utf-8")
    code += (
        "\nos.environ['ALTVIA_ALLOW_CONTAINER_TEST']='1'\npackaged_worker_privacy_checkpoint()\n"
    )
    checkpoint = json.loads(
        run(
            worker_probe_command(compose, root, code),
            data=json.dumps(
                {"phase": phase, "event_ids": snapshot["event_ids"], "metadata_markers": markers}
            ),
        )
    )
    grants = []
    for service, role in (("api", "altvia_app"), ("worker", "altvia_worker")):
        grants.append(
            json.loads(
                run(
                    worker_probe_command(compose, root, PRIVILEGES)
                    if service == "worker"
                    else [*compose, "exec", "-T", service, "python", "-c", PRIVILEGES],
                    data=json.dumps({"role": role}),
                )
            )
        )
    assert_worker_diagnostics(
        run(
            [
                *compose,
                "logs",
                "--no-color",
                "api",
                "postgres",
                "storage",
                "worker",
                "clamd",
                "freshclam",
            ]
        ),
        tuple(v.encode() for v in markers),
    )
    return {**checkpoint, "grants": grants, "service_diagnostics_checked": True}


def prepare_file_sender(run, compose, ticket_id, queue_id, existing_account):
    # Sender identity is unique per queue. Reuse its actual current account;
    # a new ticket/file context never mutates the historical sender or wires.
    account = dict(existing_account)
    setup = owner(
        run,
        compose,
        OWNER_SETUP,
        {
            "account": account,
            "ticket_id": ticket_id,
            "queue_id": queue_id,
            "version": 1,
        },
    )
    assert setup["source_id"] == account["source_id"]
    return account, setup


def prepare_packaged_files(
    client, reader, ticket_body, run, compose, root, secret_dir, work, existing_account
):
    require_opt_in()
    author = client.get("/api/v1/auth/me")
    assert author.status_code == 200
    storage = storage_checkpoint(run, compose)
    created = client.post(
        "/api/v1/tickets",
        json={**ticket_body, "subject": "Packaged independent synthetic file context"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created.status_code == 201
    ticket_id = created.json()["ticket_id"]
    account, setup = prepare_file_sender(
        run,
        compose,
        ticket_id,
        ticket_body["queue_id"],
        existing_account,
    )
    files = [
        {
            "filename": "public-" + uuid4().hex + ".txt",
            "body": "public-bytes-" + uuid4().hex + "\n",
            "purpose": "public",
        },
        {
            "filename": "note-" + uuid4().hex + ".txt",
            "body": "note-bytes-" + uuid4().hex + "\n",
            "purpose": "note",
        },
        {
            "filename": "eicar-" + uuid4().hex + ".txt",
            "body": "X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*",
            "purpose": "public",
        },
    ]
    private_marker, public_marker = "note-body-" + uuid4().hex, "public-body-" + uuid4().hex
    browser_input = {
        "origin": str(client.base_url).rstrip("/"),
        "ticket_id": ticket_id,
        "session": client.cookies.get("__Host-altvia_session"),
        "files": files,
        "private_marker": private_marker,
        "public_marker": public_marker,
        "source_id": setup["source_id"],
        "participant_id": setup["participant_id"],
    }
    browser = run_file_browser(run, work, browser_input)
    ids = browser["ids"]
    # A paused REAL daemon accepts no response; the actual transport times out.
    # Only this new synthetic file's due timestamp is accelerated between attempts.
    run([*compose, "pause", "clamd"])
    try:
        fault = b"timeout-bytes-" + uuid4().hex.encode()
        path = "/api/v1/tickets/" + ticket_id
        version = client.get(path).json()["version"]
        uploaded = client.post(
            path + "/attachments",
            params={"filename": "timeout-" + uuid4().hex + ".txt", "purpose": "public"},
            content=fault,
            headers={
                "Content-Type": "application/octet-stream",
                "If-Match": f'"{version}"',
                "Idempotency-Key": uuid4().hex,
                "X-File-Bytes": str(len(fault)),
                "X-File-SHA256": digest(fault),
            },
        )
        assert uploaded.status_code == 201
        timeout_id = uploaded.json()["attachment_id"]
        ids.append(timeout_id)
        for attempt in range(1, 9):
            deadline = time.monotonic() + 90
            while True:
                state = owner(
                    run, compose, OWNER_FILES, {"ids": [timeout_id], "ticket_id": ticket_id}
                )
                if len(state["attempts"]) == attempt:
                    assert state["attempts"][-1]["reason"] == "timeout"
                    break
                assert time.monotonic() < deadline, "Real scanner timeout was not persisted"
                time.sleep(0.5)
            if attempt < 8:
                owner(
                    run,
                    compose,
                    OWNER_FILES,
                    {"ids": [timeout_id], "ticket_id": ticket_id, "accelerate": True},
                )
        failed = wait_state(client, timeout_id, "failed")
        assert client.get("/api/v1/attachments/" + timeout_id + "/content").status_code == 409
    finally:
        run([*compose, "unpause", "clamd"])
    retry_path = "/api/v1/attachments/" + timeout_id + "/scan-retries"
    headers = {"If-Match": f'"{failed["version"]}"', "Idempotency-Key": uuid4().hex}
    retried = client.post(retry_path, json={}, headers=headers)
    assert retried.status_code == 201
    replay = client.post(retry_path, json={}, headers=headers)
    assert replay.status_code == 200 and replay.json() == retried.json()
    wait_state(client, timeout_id, "ready")
    assert client.get("/api/v1/attachments/" + timeout_id + "/content").content == fault
    snapshot = owner(run, compose, OWNER_FILES, {"ids": ids, "ticket_id": ticket_id})
    clean = [r for r in snapshot["attempts"] if r["reason"] == "clean"]
    assert len(clean) == 3 and all(
        r["engine"] == "1.4.6" and r["database_version"] and r["database_date"] for r in clean
    )
    assert sum(r["reason"] == "infected" for r in snapshot["attempts"]) == 1
    assert sum(r["reason"] == "timeout" for r in snapshot["attempts"]) == 8
    assert next(r for r in snapshot["files"] if r["id"] == timeout_id)["generation"] == 2
    markers = [
        private_marker,
        public_marker,
        fault.decode(),
        digest(fault),
        account["username"],
        account["password"],
    ]
    for file in files:
        markers.extend([file["filename"], file["body"].strip(), digest(file["body"].encode())])
    markers.extend(snapshot_file_markers(snapshot))
    for role in ("owner", "api", "scanner"):
        config = json.loads((secret_dir / ("storage_" + role)).read_text())
        markers.extend([config["access_key"], config["secret_key"]])
    # Check both full URLs and their actual generated passwords in child/main/
    # service diagnostics. The existing global log guard also covers the login
    # password, which is never supplied to this helper or its worker child.
    for name in ("owner_database_url", "runtime_database_url", "worker_database_url", "redis_url"):
        value = (secret_dir / name).read_text(encoding="utf-8")
        markers.extend([value, urlsplit(value).password])
    markers.extend(
        [
            browser_input["session"],
            reader.cookies.get("__Host-altvia_session"),
            client.headers["X-CSRF-Token"],
        ]
    )
    assert all(markers)
    context = {"ids": ids, "ticket_id": ticket_id, "markers": markers}
    checkpoints = [privacy_checkpoint(run, compose, root, context, "after-files-and-links")]
    # Reuse real worker child lifecycle/TLS/privacy and restart no-second-DATA.
    smtp_code = (root / "scripts/packaged_smtp_fixture.py").read_text(encoding="utf-8")
    smtp_code += "\n" + (root / "scripts/packaged_smtp_proof.py").read_text(encoding="utf-8")
    smtp_code += "\npackaged_smtp_worker_proof(synthetic_relay)\n"
    smtp = json.loads(
        run(
            worker_probe_command(compose, root, smtp_code),
            data=json.dumps(
                {
                    **browser,
                    "account": account,
                    "mode": "accepted",
                    "private_marker": private_marker,
                    "public_marker": public_marker,
                    "body_text": public_marker,
                    "mime_files": [
                        {
                            "filename": files[0]["filename"],
                            "media_type": "text/plain",
                            "base64": base64.b64encode(files[0]["body"].encode()).decode(),
                        }
                    ],
                    "privacy_canaries": markers,
                    "cert": (secret_dir / "imap_cert").read_text(),
                    "key": (secret_dir / "imap_key").read_text(),
                }
            ),
            timeout=150,
        )
    )
    assert client.get(browser["delivery_path"]).json()["state"] == "accepted"
    assert reader.get("/api/v1/tickets/" + ticket_id + "/notes").status_code == 403
    note_id = ids[1]
    for suffix in ("", "/content"):
        assert reader.get("/api/v1/attachments/" + note_id + suffix).status_code == 404
    assert (
        reader.get(
            "/api/v1/tickets/" + ticket_id + "/attachments", params={"purpose": "note"}
        ).status_code
        == 404
    )
    checkpoints.append(
        privacy_checkpoint(run, compose, root, context, "after-delivered-and-processed")
    )
    return {
        "context": context,
        "browser": browser,
        "smtp": smtp,
        "checkpoints": checkpoints,
        "timeout_retry": {"timeouts": 8, "protected_retry": True, "actual_ready_after_retry": True},
        "public_body": files[0]["body"],
        "note_body": files[1]["body"],
        "session": browser_input["session"],
        "author_id": author.json()["id"],
        "reader_session": reader.cookies.get("__Host-altvia_session"),
        "storage": storage,
        "scan_evidence": [
            {k: v for k, v in row.items() if k != "id"} for row in snapshot["attempts"]
        ],
    }


def snapshot_file_markers(snapshot):
    return [value for row in snapshot["files"] for value in (row["filename"], row["key"])]


def capture_current_file_author(client, proof):
    """Reuse baseline's ordinary fresh login, bound to the original file actor."""
    current = client.get("/api/v1/auth/me")
    assert current.status_code == 200 and current.json()["id"] == proof["author_id"]
    session = client.cookies.get("__Host-altvia_session")
    assert session and session != proof["session"]
    proof["current_session"] = session
    proof["context"]["markers"].extend([session, current.json()["csrf_token"]])


def select_current_file_author(client, proof):
    # Baseline's team-role mutation correctly revoked the old saved session.
    # Prove that denial, then use its already-authenticated replacement. This
    # changes only this proof client's cookie, never a grant or session row.
    client.cookies.clear()
    client.cookies.set(
        "__Host-altvia_session", proof["session"], domain=client.base_url.host, path="/"
    )
    assert client.get("/api/v1/auth/me").status_code == 401
    denied = client.get("/api/v1/attachments/" + proof["browser"]["ids"][0] + "/content")
    assert denied.status_code == 401, f"Revoked file session status={denied.status_code}"
    client.cookies.clear()
    client.cookies.set(
        "__Host-altvia_session", proof["current_session"], domain=client.base_url.host, path="/"
    )
    current = client.get("/api/v1/auth/me")
    assert current.status_code == 200 and current.json()["id"] == proof["author_id"]
    return {"revoked_file_session_status": 401, "current_actor_bound": True}


SNAPSHOT = """
import hashlib,json
from uuid import UUID
from sqlalchemy import text
from altvia.config import DatabaseSettings
from altvia.database import make_engine
with make_engine(DatabaseSettings()).connect() as db:
    files=[dict(r) for r in db.execute(text(
        'SELECT id,object_key,bytes,sha256,state,purpose,filename,media_type,'
        'ticket_id,work_item_id,mail_case_id,file_position,parent_version,creator_id,'
        'version,generation FROM attachments ORDER BY id'
    )).mappings()]
    for r in files:
        for key,value in r.items():
            if isinstance(value,UUID): r[key]=str(value)
    case_headers=[r[0] for r in db.execute(text(
        'SELECT row_to_json(t)::text FROM (SELECT id,source_id,primary_variant_id,'
        'file_extraction_version,file_set_status,file_count,file_rejection_reason,'
        'ticket_id,incoming_message_id FROM mail_triage_cases ORDER BY id) t'))]
    incoming=[r[0] for r in db.execute(text(
        'SELECT row_to_json(t)::text FROM ticket_incoming_messages t ORDER BY id'))]
    links={}
    for table in ('ticket_message_attachments','ticket_note_attachments',
                  'work_comment_attachments'):
        links[table]=[r[0] for r in db.execute(text(
            'SELECT row_to_json(t)::text FROM '+table+' t ORDER BY attachment_id'))]
    wires=[{'id':str(r.id),'format':r.wire_format,'bytes':len(r.wire),
            'sha256':hashlib.sha256(r.wire).hexdigest(),
            'state':r.state,'attempts':r.attempts,'accepted_at':str(r.accepted_at)}
           for r in db.execute(text(
               'SELECT id,wire_format,wire,state,attempts,accepted_at '
               'FROM outbound_messages ORDER BY id'))]
    assert files and any(w['format']==2 and w['state']=='accepted' for w in wires)
    print(json.dumps({'files':files,'links':links,'wires':wires,
                      'case_headers':case_headers,'incoming':incoming},sort_keys=True))
"""

OBJECTS = """
import base64,io,json,sys
from pathlib import Path
from altvia.file_storage import S3Store
from altvia.file_storage_owner import load_storage
p=json.load(sys.stdin)
store=S3Store(load_storage(Path('/run/secrets/storage_owner')))
try:
    result=[]
    for row in p['files']:
        if p['mode']=='restore':
            store.put_new(row['object_key'],io.BytesIO(base64.b64decode(
                row['base64'],validate=True)),size=row['bytes'],sha256=row['sha256'])
        with store.verified_spool(row['object_key'],size=row['bytes'],
                                  sha256=row['sha256']) as source:
            result.append({**row,'base64':base64.b64encode(source.read()).decode()})
    print(json.dumps(result,sort_keys=True))
finally: store.close()
"""


def object_snapshot(run, compose, rows, mode):
    return json.loads(
        run(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "storage-bootstrap",
                "python",
                "-c",
                OBJECTS,
            ],
            data=json.dumps({"mode": mode, "files": rows}),
        )
    )


def assert_current_access(client, reader, proof):
    ticket = "/api/v1/tickets/" + proof["context"]["ticket_id"]
    ids = proof["browser"]["ids"]
    for slot, (identifier, body) in enumerate(
        ((ids[0], proof["public_body"]), (ids[1], proof["note_body"]))
    ):
        content = client.get("/api/v1/attachments/" + identifier + "/content")
        equal = content.content == body.encode()
        assert content.status_code == 200 and equal, (
            f"Current file access slot={slot} status={content.status_code} bytes_equal={equal}"
        )
    notes = client.get(ticket + "/notes").json()["items"]
    assert len(notes) == 1 and [r["id"] for r in notes[0]["attachments"]] == [ids[1]]
    messages = client.get(ticket + "/messages").json()["items"]
    assert len(messages) == 1 and [r["id"] for r in messages[0]["attachments"]] == [ids[0]]
    assert client.get(proof["browser"]["delivery_path"]).json()["state"] == "accepted"
    assert reader.get(ticket).status_code == 200
    assert (
        reader.get("/api/v1/attachments/" + ids[0] + "/content").content
        == proof["public_body"].encode()
    )
    assert reader.get(ticket + "/notes").status_code == 403
    for suffix in ("", "/content"):
        assert reader.get("/api/v1/attachments/" + ids[1] + suffix).status_code == 404
    if "incoming" in proof:
        from packaged_incoming_file_proof import assert_incoming_access

        assert_incoming_access(client, proof["incoming"])
        assert_incoming_access(reader, proof["incoming"])


def verify_packaged_files(run, compose, root, secret_dir, work, proof, origin):
    """Recreate the actual services, then restore into a distinct disposable project.

    All writers are quiescent for this synthetic snapshot. This deliberately
    makes no online production snapshot or encrypted-backup/rollback claim.
    """
    import httpx

    require_opt_in()
    kwargs = {
        "base_url": origin,
        "verify": str(secret_dir / "tls_cert"),
        "trust_env": False,
        "timeout": 15,
    }
    with httpx.Client(**kwargs) as client, httpx.Client(**kwargs) as reader:
        client.cookies.set(
            "__Host-altvia_session", proof["session"], domain="workspace.altvia.test", path="/"
        )
        reader.cookies.set(
            "__Host-altvia_session",
            proof["reader_session"],
            domain="workspace.altvia.test",
            path="/",
        )
        for service in ("api", "postgres", "storage", "worker"):
            run(
                [
                    *compose,
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "--force-recreate",
                    "--wait",
                    service,
                ],
                timeout=150,
            )
        for _ in range(90):
            if client.get("/api/v1/health/ready").status_code == 200:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Combined recreated API did not become ready")
        session_evidence = select_current_file_author(client, proof)
        assert_current_access(client, reader, proof)
        storage_recreated = storage_checkpoint(run, compose, proof["storage"])
        proof["checkpoints"].append(
            privacy_checkpoint(
                run, compose, root, proof["context"], "after-api-pg-s3-worker-recreation"
            )
        )
        run([*compose, "stop", "-t", "30", "api", "worker"])
        snapshot = owner(run, compose, SNAPSHOT)
        objects = object_snapshot(run, compose, snapshot["files"], "export")
        dump = run(
            [
                *compose,
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "-U",
                "altvia_owner",
                "-d",
                "altvia_test",
                "--clean",
                "--if-exists",
            ]
        )
        # Only explicitly selected proof artifacts are uploaded. Preserve private
        # matching snapshot material locally without exposing dump/session data.
        private = work / "private-file-snapshot"
        private.mkdir(mode=0o700)
        (private / "database.sql").write_text(dump, encoding="utf-8")
        (private / "objects.json").write_text(json.dumps(objects), encoding="utf-8")
        restored = [*compose[:-1], compose[-1] + "-file-restore"]
        run([*compose, "stop", "ingress"])
        try:
            run([*restored, "up", "-d", "--no-build", "--wait", "postgres", "storage"], timeout=150)
            run([*restored, "run", "--rm", "--no-deps", "migrate"])
            run(
                [
                    *restored,
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-X",
                    "-q",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    "altvia_owner",
                    "-d",
                    "altvia_test",
                ],
                data=dump,
            )
            run([*restored, "run", "--rm", "--no-deps", "storage-bootstrap"])
            assert object_snapshot(run, restored, objects, "restore") == objects
            assert owner(run, restored, SNAPSHOT) == snapshot
            # No scanner is needed for restored historically-ready files. There
            # is no worker here: no post-snapshot writer can change the evidence.
            run(
                [*restored, "up", "-d", "--no-build", "--wait", "api", "web", "ingress"],
                timeout=180,
            )
            assert select_current_file_author(client, proof) == session_evidence
            assert_current_access(client, reader, proof)
            restored_snapshot = owner(run, restored, SNAPSHOT)
            assert restored_snapshot == snapshot
            restored_grants = json.loads(
                run(
                    [*restored, "exec", "-T", "api", "python", "-c", PRIVILEGES],
                    data=json.dumps({"role": "altvia_app"}),
                )
            )
            assert_worker_diagnostics(
                run([*restored, "logs", "--no-color"]),
                tuple(v.encode() for v in proof["context"]["markers"]),
            )
        finally:
            run([*restored, "down"], timeout=90)
            run(
                [*compose, "up", "-d", "--no-build", "--wait", "api", "worker", "ingress"],
                timeout=180,
            )
    safe = {
        "schema": 1,
        "synthetic_only": True,
        "profile": "combined-packaged-actual-signed-current",
        "browser": {k: v for k, v in proof["browser"].items() if isinstance(v, bool)},
        "smtp": proof["smtp"],
        "privacy_checkpoints": proof["checkpoints"],
        "timeout_retry": proof["timeout_retry"],
        "current_session_continuity": session_evidence,
        "actual_scan_history": proof["scan_evidence"],
        "incoming_files": proof.get("incoming", {}).get("safe"),
        "actual_current_storage_credentials": {
            "initial": proof["storage"]["checks"],
            "after_recreation": storage_recreated["checks"],
        },
        "matching_logical_restore": {
            "isolated_project": True,
            "quiesced_writers": True,
            "every_referenced_object_verified": True,
            "objects": len(objects),
            "snapshot_sha256": digest(json.dumps(snapshot, sort_keys=True).encode()),
            "links_and_frozen_wires_identical": True,
            "incoming_headers_and_immutable_relationships_identical": "incoming" in proof,
            "current_acl": True,
            "restored_api_grants": restored_grants,
        },
        "encrypted_backup_and_compatible_image_rollback_tested": False,
        "target_cpu_qualified": False,
    }
    (work / "packaged-file-proof.json").write_text(
        json.dumps(safe, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Combined packaged signed file/browser/MIME2/privacy/recreation/"
        "isolated logical restore passed."
    )
