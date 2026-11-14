"""Negative controls execute the actual embedded packaged privacy/grant assertions."""

import ast
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from altvia.models import ActivityEvent, AuditLog, OutboxEvent
from sqlalchemy import select, text

PROOF = Path(__file__).resolve().parents[3] / "scripts/packaged_smtp_proof.py"
spec = importlib.util.spec_from_file_location("packaged_smtp_proof", PROOF)
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


def execute(nodes, namespace):
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(PROOF), "exec"
        ),
        namespace,
    )


def test_smtp_failure_actual_child_preserves_private_channels_and_bounded_host_error(tmp_path):
    secret = "private-filename-body-key-credential-canary"
    child = (
        "import sys;sys.path.insert(0,'scripts');"
        "from packaged_smtp_proof import smtp_worker_diagnostic\n"
        "@smtp_worker_diagnostic\n"
        "def fail(serve, diagnostic):\n"
        " diagnostic.update(scenario='lost', phase='restart_stability')\n"
        f" raise AssertionError('{secret}')\n"
        "fail(None)\n"
    )
    tree = ast.parse(PROOF.with_name("container_smoke.py").read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    run = next(n for n in main.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    namespace = {
        **vars(proof),
        "args": SimpleNamespace(files=True),
        "file_commands": [],
        "ROOT": PROOF.parents[1],
        "env": dict(os.environ),
        "work": tmp_path,
    }
    execute([run], namespace)
    with pytest.raises(RuntimeError) as caught:
        namespace["run"]([sys.executable, "-c", child])
    assert "SMTP scenario=lost phase=restart_stability error=assertion" in str(caught.value)
    assert secret not in str(caught.value)
    assert namespace["file_commands"][0]["exit"] == 1
    private = (tmp_path / "last-command.stderr").read_text()
    assert secret in private and "AssertionError" in private
    assert (tmp_path / "last-command.stdout").read_text() == ""
    safe = proof.smtp_failure_summary(private)
    assert safe == "SMTP scenario=lost phase=restart_stability error=assertion"


@pytest.mark.parametrize("field", ["schema", "phase", "scenario", "error_kind", "extra"])
def test_smtp_failure_rejects_untrusted_fields_and_duplicate_diagnostics(field):
    data = {"schema": 1, "phase": "initial", "scenario": "lost", "error_kind": "assertion"}
    valid = "ALTVIA_SMTP_PROOF_FAILURE=" + json.dumps(data)
    assert proof.smtp_failure_summary(valid + "\n" + valid) == ""
    data[field] = "private-body-key-credential"
    assert proof.smtp_failure_summary("ALTVIA_SMTP_PROOF_FAILURE=" + json.dumps(data)) == ""
    assert proof.smtp_failure_summary(valid[:-1] + ', "phase": "initial"}') == ""
    assert proof.smtp_failure_summary("ALTVIA_SMTP_PROOF_FAILURE=" + "x" * 513) == ""


def test_smtp_failure_diagnostic_does_not_replace_original_exception(capsys):
    original = subprocess.TimeoutExpired("private-command", 1, stderr="private-credentials")

    @proof.smtp_worker_diagnostic
    def fail(serve, diagnostic):
        diagnostic.update(phase="private-body", scenario="private-name", extra="private-key")
        raise original

    with pytest.raises(subprocess.TimeoutExpired) as caught:
        fail(None)
    assert caught.value is original
    channels = capsys.readouterr()
    assert channels.out == "" and "private-" not in channels.err
    assert proof.smtp_failure_summary(channels.err) == (
        "SMTP scenario=unknown phase=unknown error=timeout"
    )


def test_smtp_failure_actual_owner_entrypoint_reports_setup_denial(monkeypatch, capsys):
    monkeypatch.delenv("ALTVIA_ALLOW_CONTAINER_TEST", raising=False)
    with pytest.raises(AssertionError):
        proof.packaged_smtp_worker_proof(None)
    channels = capsys.readouterr()
    assert channels.out == ""
    assert proof.smtp_failure_summary(channels.err) == (
        "SMTP scenario=unknown phase=setup error=assertion"
    )


def test_first_incoming_reply_requires_actual_root_and_exact_decoded_body():
    from email.message import EmailMessage

    message = EmailMessage()
    message["In-Reply-To"] = "<first@example.test>"
    message["References"] = "<first@example.test>"
    body = "public-canary\n.literal"
    message.set_content(body)
    proof.assert_incoming_wire(message.as_bytes(), "<first@example.test>", body, "private-canary")
    for wire, root, text_body, private in (
        (message.as_bytes(), "<other@example.test>", body, "private-canary"),
        (message.as_bytes(), "<first@example.test>", "changed", "private-canary"),
        (message.as_bytes(), "<first@example.test>", body, "public-canary"),
    ):
        with pytest.raises(AssertionError):
            proof.assert_incoming_wire(wire, root, text_body, private)


def test_classified_imap_requires_explicit_disposable_opt_in(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "packaged_imap_proof", PROOF.with_name("packaged_imap_proof.py")
    )
    imap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imap)
    monkeypatch.delenv("ALTVIA_ALLOW_CONTAINER_TEST", raising=False)
    with pytest.raises(RuntimeError, match="Explicit synthetic container test required"):
        imap.packaged_classified_imap_proof(None)


def test_incoming_orchestration_requires_explicit_disposable_opt_in(monkeypatch):
    monkeypatch.delenv("ALTVIA_ALLOW_CONTAINER_TEST", raising=False)
    with pytest.raises(RuntimeError, match="Explicit synthetic container test required"):
        proof.prepare_packaged_incoming(*([None] * 9))


@pytest.mark.parametrize("table", ["outbox_events", "activity_events", "audit_logs"])
def test_incoming_metadata_canary_rejects_actual_multiline_json(table):
    tree = ast.parse(proof.INCOMING_SNAPSHOT)
    loop = next(
        n for n in ast.walk(tree) if isinstance(n, ast.For) and isinstance(n.target, ast.Tuple)
    )
    marker = "classified-body-canary"
    namespace = {
        "p": {"canaries": [marker]},
        "db": MetadataDB({}, table),
        "json": json,
        "select": select,
        "OutboxEvent": OutboxEvent,
        "ActivityEvent": ActivityEvent,
        "AuditLog": AuditLog,
    }
    execute([loop], namespace)
    namespace["db"].value = {"body_text": "first\n" + marker + "\nlast"}
    with pytest.raises(AssertionError):
        execute([loop], namespace)


class RedisValue:
    def __init__(self, value, kind=b"string"):
        self.value = value
        self.kind = kind

    def scan_iter(self, **kwargs):
        return [b"actor-message"]

    def type(self, key):
        return self.kind

    def get(self, key):
        return self.value

    def hscan_iter(self, key):
        return [(b"field", self.value)]

    def lrange(self, *args):
        return [self.value]

    def smembers(self, *args):
        return {self.value}

    def zrange(self, *args):
        return [self.value]

    def close(self):
        pass


class MetadataDB:
    def __init__(self, value, only_table=None):
        self.value = value
        self.only_table = only_table

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def connect(self):
        return self

    def scalars(self, query):
        if self.only_table is not None and self.only_table not in str(query):
            return [{}]
        return [self.value]


@pytest.mark.parametrize(
    "canary",
    [
        "classified-body-canary",
        "<incoming-private-id@example.test>",
        "synthetic-packaged-incoming-only",
        "synthetic-packaged-alias-only",
    ],
)
@pytest.mark.parametrize("boundary", ["redis", "worker-events", "child-diagnostics"])
def test_incoming_canaries_reject_actual_worker_checker_multiline_json(canary, boundary):
    payload = {
        "private_marker": "note-marker",
        "public_marker": "public-marker",
        "privacy_canaries": [canary],
        "account": {"username": "smtp-user", "password": "smtp-password"},
    }
    namespace = {
        **vars(proof),
        "payload": payload,
        "marker": b"note-marker",
        "initial": (None, None, None, None, "from@example.test", "to@example.test"),
        "account": payload["account"],
        "redis": RedisValue(b"safe"),
        "engine": MetadataDB({}),
        "diagnostics": b"safe",
        "diagnostic": {},
        "text": text,
    }
    worker = next(
        n
        for n in ast.parse(PROOF.read_text(encoding="utf-8")).body
        if isinstance(n, ast.FunctionDef) and n.name == "packaged_smtp_worker_proof"
    )
    if boundary == "child-diagnostics":
        nodes = [
            n
            for n in ast.walk(worker)
            if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "secret"
        ]
        if not nodes:
            nodes = [
                n
                for n in ast.walk(worker)
                if isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name)
                and n.value.func.id == "assert_worker_diagnostics"
            ]
    else:
        nodes = [
            n
            for n in ast.walk(worker)
            if isinstance(n, ast.FunctionDef) and n.name == "inspect_metadata"
        ]
        nodes += ast.parse("inspect_metadata()").body
    assert nodes, "Actual worker checker path must be located"
    execute(nodes, namespace)
    leak = json.dumps({"message": "first\n" + canary + "\nlast"})
    if boundary == "redis":
        namespace["redis"].value = leak.encode()
    elif boundary == "worker-events":
        namespace["engine"].value = json.loads(leak)
    else:
        namespace["diagnostics"] = leak.encode()
    with pytest.raises(AssertionError):
        execute(nodes, namespace)


INCOMING_CANARIES = [
    "classified-body-canary",
    "<incoming-private-id@example.test>",
    "synthetic-packaged-incoming-only",
    "synthetic-packaged-alias-only",
]


@pytest.mark.parametrize("canary", INCOMING_CANARIES)
@pytest.mark.parametrize("kind", [b"string", b"hash", b"list", b"set", b"zset"])
def test_late_worker_checkpoint_rejects_actual_decoded_redis_values(
    monkeypatch, capsys, canary, kind
):
    import io
    import sys
    from types import SimpleNamespace
    from uuid import UUID

    from pydantic import SecretStr
    from redis import Redis

    event_id = UUID("f07df534-e53e-49e9-973d-cc39fb308411")

    class CompletedDB(MetadataDB):
        def scalar(self, query):
            return "altvia_worker"

        def execute(self, query):
            return SimpleNamespace(all=lambda: [(event_id, "delivered", "actual-time")])

        def dispose(self):
            pass

    redis_value = RedisValue(b"safe", kind)
    monkeypatch.setenv("ALTVIA_ALLOW_CONTAINER_TEST", "1")
    monkeypatch.setattr(
        "altvia.config.WorkerSettings",
        lambda: SimpleNamespace(redis_url=SecretStr("redis://:synthetic@localhost:6379/0")),
    )
    monkeypatch.setattr("altvia.database.make_engine", lambda *args, **kwargs: CompletedDB({}))
    monkeypatch.setattr(Redis, "from_url", lambda *args, **kwargs: redis_value)
    payload = json.dumps(
        {
            "phase": "after-collision",
            "event_ids": [str(event_id)],
            "metadata_markers": INCOMING_CANARIES,
        }
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    proof.packaged_worker_privacy_checkpoint()
    result = json.loads(capsys.readouterr().out)
    assert result["completed_events"] == 1 and result["delivered_and_processed"]
    assert result["redis_scans"] >= 2
    redis_value.value = json.dumps({"body": "first\n" + canary + "\nlast"}).encode()
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    with pytest.raises(AssertionError):
        proof.packaged_worker_privacy_checkpoint()


@pytest.mark.parametrize("canary", INCOMING_CANARIES)
def test_late_main_diagnostics_reject_actual_checker_multiline_json(canary, tmp_path):
    from uuid import uuid4

    context = {
        "aggregate_ids": [str(uuid4())],
        "incoming_count": 1,
        "metadata_markers": INCOMING_CANARIES,
    }
    logs = "safe"
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/packaged_smtp_proof.py").write_bytes(PROOF.read_bytes())

    def run(command, **kwargs):
        if "logs" in command:
            return logs
        if "worker" in command:
            return json.dumps({"completed_events": 1})
        return json.dumps(
            [{"event_id": str(uuid4()), "type": "ticket.message_received", "schema": 1}]
        )

    assert proof.incoming_privacy_checkpoint(run, [], tmp_path, context, "after-append")[
        "main_diagnostics_checked"
    ]
    logs = json.dumps({"body": "first\n" + canary + "\nlast"})
    with pytest.raises(AssertionError):
        proof.incoming_privacy_checkpoint(run, [], tmp_path, context, "after-append")


def test_event_completion_requires_every_exact_event_delivered_and_processed():
    from uuid import uuid4

    first, second = uuid4(), uuid4()
    expected = [first, second]
    complete = [(first, "delivered", "time"), (second, "delivered", "time")]
    assert proof.processed_events_complete(complete, expected)
    assert not proof.processed_events_complete(complete[:1], expected)
    assert not proof.processed_events_complete(
        complete + [(uuid4(), "delivered", "time")], expected
    )
    for status, processed in (("pending", "time"), ("dead", "time"), ("delivered", None)):
        assert not proof.processed_events_complete(
            [complete[0], (second, status, processed)], expected
        )
    with pytest.raises(AssertionError, match="empty event set"):
        proof.processed_events_complete([], [])


@pytest.mark.parametrize(
    "boundary,table",
    [
        ("owner-events-audit", "outbox_events"),
        ("owner-events-audit", "activity_events"),
        ("owner-events-audit", "audit_logs"),
        ("worker-events", "outbox_events"),
        ("worker-events", "activity_events"),
        ("redis-json", None),
        ("diagnostics-json", None),
    ],
)
def test_full_multiline_body_leak_is_rejected(boundary, table):
    marker = "packaged-public-unique-canary-1234567890"
    body = "Synthetic response\n" + marker + "\n.literal"
    payload = {
        "private_marker": "private-unique-canary",
        "public_marker": marker,
        "body_text": body,
        "items": [{"body_text": body, "public_marker": marker}],
    }
    leaked = {"body_text": body}
    namespace = {
        **vars(proof),
        "json": json,
        "p": payload,
        "payload": payload,
        "db": MetadataDB({}, table),
        "engine": MetadataDB({}, table),
        "redis": RedisValue(b"safe"),
        "marker": payload["private_marker"].encode(),
        "initial": (None, None, None, None, "from@example.test", "to@example.test"),
        "select": select,
        "text": text,
        "OutboxEvent": OutboxEvent,
        "ActivityEvent": ActivityEvent,
        "AuditLog": AuditLog,
        "account": {"username": "synthetic-user", "password": "synthetic-password"},
        "diagnostics": b"safe",
        "diagnostic": {},
    }
    payload["account"] = namespace["account"]
    tree = ast.parse(PROOF.read_text(encoding="utf-8"))
    worker = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "packaged_smtp_worker_proof"
    )
    if boundary == "owner-events-audit":
        nodes = [
            n
            for n in ast.walk(ast.parse(proof.OWNER_SNAPSHOT))
            if isinstance(n, ast.For)
            and isinstance(n.target, ast.Tuple)
            and [getattr(e, "id", None) for e in n.target.elts] == ["model", "column"]
        ]
    elif boundary == "diagnostics-json":
        nodes = [
            n
            for n in ast.walk(worker)
            if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "secret"
        ]
        if not nodes:
            nodes = [
                n
                for n in ast.walk(worker)
                if isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name)
                and n.value.func.id == "assert_worker_diagnostics"
            ]
    else:
        nodes = [
            n
            for n in ast.walk(worker)
            if isinstance(n, ast.FunctionDef) and n.name == "inspect_metadata"
        ]
        nodes += ast.parse("inspect_metadata()").body
    assert nodes, "Proof boundary no longer located; update the negative control"
    execute(nodes, namespace)  # The same assertions must permit safe metadata.
    namespace["db"].value = leaked
    namespace["engine"].value = leaked if boundary == "worker-events" else {}
    namespace["redis"].value = json.dumps(leaked).encode() if boundary == "redis-json" else b"safe"
    namespace["diagnostics"] = json.dumps(leaked).encode()
    with pytest.raises(AssertionError):
        execute(nodes, namespace)


@pytest.mark.parametrize(
    "table,column,privilege",
    [
        ("ticket_notes", "body_text", "SELECT"),
        ("mail_senders", "from_email", "UPDATE"),
        ("ticket_participants", "evidence", "INSERT"),
        ("mail_case_origins", "evidence", "SELECT"),
        ("mail_triage_cases", "body_text", "SELECT"),
        ("ticket_incoming_messages", "case_id", "INSERT"),
    ],
)
def test_column_only_grants_fail_packaged_probe(db_engine, table, column, privilege):
    """A disposable role receives only a column grant, never application-role grants."""
    from uuid import uuid4

    role = "proof_" + uuid4().hex
    tree = ast.parse(PROOF.read_text(encoding="utf-8"))
    worker = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "packaged_smtp_worker_proof"
    )
    privileges = next(n for n in worker.body if isinstance(n, ast.With))
    # Use the actual probe loops but substitute the disposable role for its
    # initial current_user assertion. SET ROLE supplies all effective checks.
    loops = privileges.body[1:]
    if table == "mail_case_origins":
        loops = [
            next(
                n
                for n in ast.walk(ast.parse(proof.INCOMING_PRIVILEGES))
                if isinstance(n, ast.For)
                and isinstance(n.target, ast.Name)
                and n.target.id == "table"
            )
        ]
    with db_engine.begin() as db:
        db.execute(text('CREATE ROLE "' + role + '"'))
        # Runtime provisioning deliberately revokes PUBLIC schema access.
        db.execute(text('GRANT USAGE ON SCHEMA public TO "' + role + '"'))
        db.execute(text(f'GRANT {privilege} ({column}) ON {table} TO "{role}"'))
        db.execute(text('SET LOCAL ROLE "' + role + '"'))
        assert not db.scalar(
            text("SELECT has_table_privilege(current_user,:t,:p)"), {"t": table, "p": privilege}
        )
        assert db.scalar(
            text("SELECT has_any_column_privilege(current_user,:t,:p)"),
            {"t": table, "p": privilege},
        )
        with pytest.raises(AssertionError):
            from sqlalchemy.exc import DBAPIError

            execute(loops, {"db": db, "text": text, "DBAPIError": DBAPIError})
        db.execute(text("RESET ROLE"))
        db.execute(text('DROP OWNED BY "' + role + '"'))
        db.execute(text('DROP ROLE "' + role + '"'))
