"""Actual controlled TLS, real PostgreSQL and fenced native IMAPS progress."""

import os
import subprocess
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from altvia import imap_poll
from altvia.activity import consume_event
from altvia.models import ActivityEvent, InboundMailVariant, MailboxPollState, OutboxEvent
from imap_fixture import imap_server
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_mail_intake import source

__all__ = ["source"]


@pytest.fixture(scope="session")
def imap_cert(tmp_path_factory):
    directory = tmp_path_factory.mktemp("imap-tls")
    subprocess.run(
        ["node", "scripts/imap_test_certificate.mjs", str(directory)],
        env={**os.environ, "ALTVIA_ALLOW_IMAP_TEST": "1"},
        check=True,
        capture_output=True,
    )
    return directory / "imap_cert", directory / "imap_key"


@pytest.fixture
def server(imap_cert):
    with imap_server(*imap_cert) as fixture:
        yield fixture


def settings(engine, server, imap_cert, **overrides):
    values = {
        "_env_file": None,
        "_secrets_dir": None,
        "database_url": engine.url.render_as_string(hide_password=False),
        "imap_host": "localhost",
        "imap_port": server.server_address[1],
        "imap_username": server.state["username"],
        "imap_password": server.state["password"],
        "imap_ca_file": imap_cert[0],
    }
    return imap_poll.IMAPPollSettings(**(values | overrides))


def poll(engine, server, cert, **overrides):
    return imap_poll.poll_once(
        engine, settings(engine, server, cert, **overrides), "synthetic-source"
    )


def cursor(engine, source):
    with Session(engine) as db:
        state = db.get(MailboxPollState, source)
        return state.uid_validity, state.last_uid, state.lease_token


def test_imap_actual_tls_peek_capture_resume_and_no_network_transaction(
    db_engine, source, server, imap_cert
):
    def check_unlocked(uid):
        with db_engine.begin() as connection:
            connection.execute(text("SELECT id FROM mailbox_sources FOR UPDATE NOWAIT"))

    server.state["fetch_hook"] = check_unlocked
    first = poll(db_engine, server, imap_cert)
    assert first.captured == 1 and first.last_uid == 1 and first.uid_validity == 1
    assert poll(db_engine, server, imap_cert).captured == 0
    assert cursor(db_engine, source) == (1, 1, None)
    commands = server.state["commands"]
    assert any(b"EXAMINE INBOX" in c for c in commands)
    assert sum(b"UID FETCH" in c for c in commands) == 1
    assert not any(b" STORE " in c or b" EXPUNGE" in c or b"SELECT INBOX" in c for c in commands)
    with Session(db_engine) as db:
        assert db.query(InboundMailVariant).one().raw_message == server.state["messages"][1]
        events = list(db.scalars(select(OutboxEvent.event_id)))
    for event in events:
        assert consume_event(db_engine, event, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(ActivityEvent)) == 0


def test_imap_epoch_reset_preserves_separate_receipts_and_uid_after_literal(
    db_engine, source, server, imap_cert
):
    poll(db_engine, server, imap_cert)
    server.state.update(validity=2, uid_after=True)
    assert poll(db_engine, server, imap_cert).captured == 1
    assert cursor(db_engine, source) == (2, 1, None)
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(InboundMailVariant)) == 2


def test_imap_gap_and_batch_resume_are_bounded(db_engine, source, server, imap_cert):
    server.state.update(messages={i: f"raw {i}".encode() for i in range(1, 29)}, next=31)
    first = poll(db_engine, server, imap_cert)
    assert first.captured == 25 and first.last_uid == 25 and first.more
    second = poll(db_engine, server, imap_cert)
    assert second.captured == 3 and second.last_uid == 30 and not second.more
    server.state.update(messages={}, next=2031)
    assert poll(db_engine, server, imap_cert).last_uid == 1030
    assert poll(db_engine, server, imap_cert).last_uid == 2030


def test_imap_partial_failure_retries_without_skipping_uid(db_engine, source, server, imap_cert):
    server.state.update(messages={1: b"one", 2: b"two"}, next=3, truncate_uid=2)
    with pytest.raises(imap_poll.PollError):
        poll(db_engine, server, imap_cert)
    assert cursor(db_engine, source) == (1, 1, None)
    server.state.pop("truncate_uid")
    assert poll(db_engine, server, imap_cert).captured == 1
    assert cursor(db_engine, source) == (1, 2, None)


@pytest.mark.parametrize(
    "mutation", ["oversize", "uid", "duplicate_search", "outside_search", "bad_epoch"]
)
def test_imap_hostile_protocol_never_advances_checkpoint(
    db_engine, source, server, imap_cert, mutation
):
    if mutation == "oversize":
        server.state["declared"] = 2097153
    elif mutation == "uid":
        server.state["response_uid"] = 2
    elif mutation == "duplicate_search":
        server.state["search"] = [1, 1]
    elif mutation == "outside_search":
        server.state["search"] = [2]
    else:
        server.state["validity"] = 0
    with pytest.raises(imap_poll.PollError):
        poll(db_engine, server, imap_cert)
    assert cursor(db_engine, source)[1:] == (0, None)
    with Session(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(InboundMailVariant)) == 0


@pytest.mark.parametrize("failure", ["untrusted", "hostname", "password"])
def test_imap_tls_and_auth_failure_do_not_bind_namespace(
    db_engine, source, server, imap_cert, failure
):
    overrides = (
        {"imap_ca_file": None}
        if failure == "untrusted"
        else {"imap_host": "127.0.0.1"}
        if failure == "hostname"
        else {"imap_password": "wrong"}
    )
    with pytest.raises(imap_poll.PollError):
        poll(db_engine, server, imap_cert, **overrides)
    with Session(db_engine) as db:
        state = db.get(MailboxPollState, source)
        assert state.namespace_hash is None and state.uid_validity is None
        assert state.last_uid == 0 and state.lease_token is None


def test_imap_password_rotation_preserves_namespace_but_account_change_is_refused(
    db_engine, source, server, imap_cert
):
    poll(db_engine, server, imap_cert)
    server.state["password"] = "rotated test password"
    assert poll(db_engine, server, imap_cert).captured == 0
    with pytest.raises(imap_poll.PollError, match="namespace"):
        poll(db_engine, server, imap_cert, imap_username="different")


def test_imap_expired_token_cannot_reset_or_release_new_poll(db_engine, source, server, imap_cert):
    config = settings(db_engine, server, imap_cert)
    old = imap_poll._acquire(db_engine, "synthetic-source", config.namespace_hash)
    with pytest.raises(imap_poll.PollError, match="busy"):
        imap_poll._acquire(db_engine, "synthetic-source", config.namespace_hash)
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE mailbox_poll_states SET lease_until=now()-interval '1 second'")
        )
    new = imap_poll._acquire(db_engine, "synthetic-source", config.namespace_hash)
    imap_poll._initialize(db_engine, new, 2)
    with pytest.raises(imap_poll.PollError, match="lease"):
        imap_poll._initialize(db_engine, old, 1)
    imap_poll._release(db_engine, old)
    assert cursor(db_engine, source) == (2, 0, new.token)
    imap_poll._release(db_engine, new)


def test_imap_checkpoint_event_failure_rolls_back_raw_and_progress(
    db_engine, source, server, imap_cert
):
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE outbox_events ADD CONSTRAINT test_reject_poll "
                "CHECK(event_type <> 'mailbox.poll_checkpointed' "
                "OR payload->>'reason' <> 'message_captured')"
            )
        )
    try:
        with pytest.raises(imap_poll.PollError):
            poll(db_engine, server, imap_cert)
        assert cursor(db_engine, source) == (1, 0, None)
        with Session(db_engine) as db:
            assert db.scalar(select(func.count()).select_from(InboundMailVariant)) == 0
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE outbox_events DROP CONSTRAINT test_reject_poll"))


def test_imap_guarded_migration_and_sql_cursor_identity(db_engine, source, server, imap_cert):
    poll(db_engine, server, imap_cert)
    for query in [
        "UPDATE mailbox_poll_states SET last_uid=0",
        "UPDATE mailbox_poll_states SET namespace_hash=repeat('0',64)",
    ]:
        with pytest.raises(DBAPIError), db_engine.begin() as connection:
            connection.execute(text(query))
    with pytest.raises(DBAPIError):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000017")


def test_imap_empty_migration_roundtrip(db_engine, seeded_user):
    cfg = Config("apps/api/alembic.ini")
    command.downgrade(cfg, "b46087000017")
    command.upgrade(cfg, "head")
    command.check(cfg)


def test_imap_cli_guard_and_argument_redaction(monkeypatch, capsys):
    monkeypatch.delenv("ALTVIA_ALLOW_IMAP_POLL", raising=False)
    assert imap_poll.main(["--password", "private-marker"]) == 1
    monkeypatch.setenv("ALTVIA_ALLOW_IMAP_POLL", "1")
    with pytest.raises(SystemExit):
        imap_poll.main(["--password", "private-marker"])
    assert "private-marker" not in str(capsys.readouterr())


@pytest.mark.parametrize("update", ["namespace_hash=repeat('0',64)", "uid_validity=1"])
def test_imap_sql_rejects_halfbound_namespace(db_engine, source, update):
    imap_poll._acquire(db_engine, "synthetic-source", "0" * 64)
    with pytest.raises(DBAPIError), db_engine.begin() as connection:
        connection.execute(text("UPDATE mailbox_poll_states SET " + update))


@pytest.mark.parametrize("mutation", ["long_line", "session_validity", "omit_next"])
def test_imap_wire_metadata_rejection_keeps_cursor_zero(
    db_engine, source, server, imap_cert, mutation
):
    server.state[mutation] = 2 if mutation == "session_validity" else True
    with pytest.raises(imap_poll.PollError):
        poll(db_engine, server, imap_cert)
    assert cursor(db_engine, source)[1:] == (0, None)


def test_imap_exact_literal_limit_and_regressed_uidnext(db_engine, source, server, imap_cert):
    server.state["messages"][1] = b"x" * 2097152
    assert poll(db_engine, server, imap_cert).captured == 1
    server.state["next"] = 1
    with pytest.raises(imap_poll.PollError, match="uidnext"):
        poll(db_engine, server, imap_cert)
    assert cursor(db_engine, source) == (1, 1, None)


def test_imap_wire_deadline_closes_without_capture(
    db_engine, source, server, imap_cert, monkeypatch
):
    monkeypatch.setattr(imap_poll, "WIRE_SECONDS", 0)
    with pytest.raises(imap_poll.PollError, match="deadline"):
        poll(db_engine, server, imap_cert)
    assert cursor(db_engine, source)[1:] == (0, None)


@pytest.mark.parametrize(
    "field,value",
    [
        ("reason", "unknown"),
        ("last_uid", "4294967296"),
        ("uid_validity", "0"),
        ("host", "private-host"),
    ],
)
def test_imap_private_event_rejects_poisoned_metadata(
    db_engine, source, server, imap_cert, field, value
):
    poll(db_engine, server, imap_cert)
    with Session(db_engine) as db, db.begin():
        event = db.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "mailbox.poll_checkpointed")
        )
        event.payload = {**event.payload, field: value}
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"
        assert db.scalar(select(func.count()).select_from(ActivityEvent)) == 0


def test_imap_poll_state_remains_inaccessible_to_runtime_roles(
    db_engine, source, server, imap_cert
):
    from altvia.provision import provision_runtime
    from sqlalchemy import create_engine
    from test_runtime_provision import runtime_url

    poll(db_engine, server, imap_cert)
    api = runtime_url(db_engine)
    worker = api.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        api.render_as_string(hide_password=False),
        worker.render_as_string(hide_password=False),
    )
    for credential in [api, worker]:
        engine = create_engine(credential, hide_parameters=True)
        try:
            with pytest.raises(DBAPIError), engine.begin() as connection:
                connection.execute(text("SELECT * FROM mailbox_poll_states"))
        finally:
            engine.dispose()


def test_imap_actual_cli_safe_receipt(db_engine, source, server, imap_cert, monkeypatch, capsys):
    monkeypatch.setenv("ALTVIA_ALLOW_IMAP_POLL", "1")
    for name, value in {
        "ALTVIA_IMAP_HOST": "localhost",
        "ALTVIA_IMAP_PORT": str(server.server_address[1]),
        "ALTVIA_IMAP_USERNAME": server.state["username"],
        "ALTVIA_IMAP_PASSWORD": server.state["password"],
        "ALTVIA_IMAP_CA_FILE": str(imap_cert[0]),
    }.items():
        monkeypatch.setenv(name, value)
    assert imap_poll.main(["--source-key", "synthetic-source"]) == 0
    output = capsys.readouterr()
    assert '"captured": 1' in output.out and not output.err
    assert server.state["username"] not in output.out and server.state["password"] not in output.out


@pytest.mark.parametrize("empty", [True, False])
def test_imap_search_epoch_change_never_advances_old_cursor(
    db_engine, source, server, imap_cert, empty
):
    server.state.update(search_epoch=2, next=10)
    if empty:
        server.state["messages"] = {}
    with pytest.raises(imap_poll.PollError, match="epoch"):
        poll(db_engine, server, imap_cert)
    assert cursor(db_engine, source) == (1, 0, None)


@pytest.mark.parametrize("during_search", [False, True])
def test_imap_aggregate_literal_budget_precedes_buffering(
    db_engine, source, server, imap_cert, monkeypatch, during_search
):
    returned = []
    original = imap_poll._BoundedIMAPS.read

    def observed_read(client, size):
        value = original(client, size)
        returned.append(len(value))
        return value

    monkeypatch.setattr(imap_poll._BoundedIMAPS, "read", observed_read)
    if during_search:
        server.state["search_literal"] = True
    else:
        server.state["messages"][1] = b"r" * 2097152
        server.state["extra_literal"] = True
    with pytest.raises(imap_poll.PollError, match="budget"):
        poll(db_engine, server, imap_cert)
    assert returned == ([] if during_search else [2097152])
    assert cursor(db_engine, source)[1:] == (0, None)
