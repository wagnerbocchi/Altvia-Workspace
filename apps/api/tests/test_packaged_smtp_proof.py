"""Negative controls execute the actual embedded packaged privacy/grant assertions."""

import ast
import importlib.util
import json
from pathlib import Path

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


class RedisValue:
    def __init__(self, value):
        self.value = value

    def scan_iter(self, **kwargs):
        return [b"actor-message"]

    def type(self, key):
        return b"string"

    def get(self, key):
        return self.value


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
            execute(loops, {"db": db, "text": text})
        db.execute(text("RESET ROLE"))
        db.execute(text('DROP OWNED BY "' + role + '"'))
        db.execute(text('DROP ROLE "' + role + '"'))
