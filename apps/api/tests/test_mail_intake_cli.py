"""Restricted binary-stdin command, safe failures and actual persisted receipts."""

import io
import json

import pytest
from altvia import mail_intake
from altvia.models import InboundMailVariant, MailboxSource
from sqlalchemy.orm import Session
from test_mail_intake import source

__all__ = ["source"]


def test_intake_cli_requires_explicit_opt_in(monkeypatch, capsys):
    monkeypatch.delenv("ALTVIA_ALLOW_MAIL_INTAKE", raising=False)
    assert mail_intake.main(["capture", "--source-key", "secret@example.test"]) == 1
    assert "secret@example.test" not in str(capsys.readouterr())


@pytest.mark.parametrize(
    "args",
    [
        ["capture", "--source-key", "synthetic", "--uid", "private-marker"],
        ["register-source", "--password", "private-marker"],
        [
            "capture",
            "--source-key",
            "synthetic",
            "--uid-validity",
            "1",
            "--uid",
            "1",
            "private-marker",
        ],
    ],
)
def test_intake_cli_argument_errors_never_echo_input(monkeypatch, capsys, args):
    monkeypatch.setenv("ALTVIA_ALLOW_MAIL_INTAKE", "1")
    with pytest.raises(SystemExit) as exc:
        mail_intake.main(args)
    assert exc.value.code == 2
    assert "private-marker" not in str(capsys.readouterr())


def test_intake_cli_actual_capture_replay_and_registration(db_engine, source, monkeypatch, capsys):
    monkeypatch.setenv("ALTVIA_ALLOW_MAIL_INTAKE", "1")
    raw = b"From: hidden@example.test\r\n\r\nprivate-cli-body\x00\xff"
    args = ["capture", "--source-key", "synthetic-source", "--uid-validity", "1", "--uid", "1"]
    receipts = []
    for _ in range(2):
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(raw)))
        assert mail_intake.main(args) == 0
        out = capsys.readouterr()
        assert (
            not out.err
            and "hidden@example.test" not in out.out
            and "private-cli-body" not in out.out
        )
        receipts.append(json.loads(out.out))
    assert receipts[0]["envelope_id"] == receipts[1]["envelope_id"]
    assert receipts[0]["replayed"] is False and receipts[1]["replayed"] is True
    with Session(db_engine) as db:
        assert db.query(InboundMailVariant).one().raw_message == raw
        queue = db.get(MailboxSource, source).queue_id
    assert (
        mail_intake.main(
            ["register-source", "--source-key", "other-source", "--queue-id", str(queue)]
        )
        == 0
    )
    assert set(json.loads(capsys.readouterr().out)) == {"source_id"}


@pytest.mark.parametrize("raw", [b"", b"x" * 2097153])
def test_intake_cli_bounded_stdin_refuses_empty_or_oversize(monkeypatch, capsys, raw):
    monkeypatch.setenv("ALTVIA_ALLOW_MAIL_INTAKE", "1")
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(raw)))
    assert (
        mail_intake.main(
            ["capture", "--source-key", "synthetic", "--uid-validity", "1", "--uid", "1"]
        )
        == 1
    )
    assert "x" * 50 not in str(capsys.readouterr())


def test_intake_cli_configuration_errors_do_not_echo_secret(monkeypatch, capsys):
    monkeypatch.setenv("ALTVIA_ALLOW_MAIL_INTAKE", "1")
    monkeypatch.setenv("ALTVIA_DATABASE_URL", "invalid-private-credential")
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"untrusted private input")))
    assert (
        mail_intake.main(
            ["capture", "--source-key", "synthetic", "--uid-validity", "1", "--uid", "1"]
        )
        == 1
    )
    output = str(capsys.readouterr())
    assert "invalid-private-credential" not in output and "untrusted private input" not in output
