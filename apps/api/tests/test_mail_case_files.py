"""Actual owner PG/S3 publication and closed runtime boundary for incoming files."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from altvia.mail_cases_owner import CaseError, attest_case
from altvia.mail_normalize import normalize_variant
from altvia.models import Attachment, MailCaseOrigin, MailTriageCase, OutboxEvent
from file_core_support import file_path, file_services
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_mail_cases import RAW, context
from test_mail_intake import capture
from test_team_api import admin_client, preconditions

__all__ = ["admin_client", "context", "file_services"]


def message(content=b"cHJpdmF0ZSBmaWxlCg==", name=b"proof.txt"):
    return (
        RAW.split(b"Subject:")[0]
        + b'Subject: files\r\nMIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary="b"'
        + b"\r\n\r\n--b\r\nContent-Type: text/plain\r\n\r\nbody\r\n--b\r\n"
        + b'Content-Type: application/octet-stream\r\nContent-Disposition: attachment; filename="'
        + name
        + b'"\r\nContent-Transfer-Encoding: base64\r\n\r\n'
        + content
        + b"\r\n--b--\r\n"
    )


def variant(engine, raw=None, uid=1):
    result = capture(engine, message() if raw is None else raw, uid=uid)
    normalize_variant(engine, result.variant_id)
    return result.variant_id


def attest(engine, refs, identifier, storage=None):
    return attest_case(
        engine, identifier, UUID(refs["requester_id"]), 1, "synthetic:proof", storage_file=storage
    )


def assets(engine):
    with Session(engine) as db:
        return list(db.scalars(select(Attachment).order_by(Attachment.file_position)))


@pytest.mark.parametrize(
    "raw,status,reason",
    [(RAW, "complete", None), (message(name=b"x.zip"), "unavailable", "file_type")],
)
def test_empty_and_unavailable_need_no_storage(db_engine, context, raw, status, reason):
    receipt = attest(db_engine, context, variant(db_engine, raw), Path("missing-config"))
    with Session(db_engine) as db:
        case = db.get(MailTriageCase, receipt.case_id)
        assert (case.file_extraction_version, case.file_set_status, case.file_count) == (
            1,
            status,
            0,
        )
        assert case.file_rejection_reason == reason
        assert not list(db.scalars(select(Attachment)))


@pytest.mark.usefixtures("file_services")
def test_real_files_immutable_set_replay_alias_collision(db_engine, context):
    from altvia.file_storage import S3Store
    from altvia.file_storage_owner import load_storage

    identifier = variant(db_engine)
    receipt = attest(db_engine, context, identifier, file_path("api"))
    rows = assets(db_engine)
    assert len(rows) == 1
    row = rows[0]
    assert (row.mail_case_id, row.file_position, row.creator_id, row.parent_version) == (
        receipt.case_id,
        0,
        None,
        1,
    )
    assert (row.purpose, row.state, row.filename, row.media_type) == (
        "incoming",
        "quarantine",
        "proof.txt",
        "text/plain",
    )
    store = S3Store(load_storage(file_path("api")))
    try:
        with store.verified_spool(row.object_key, size=row.bytes, sha256=row.sha256) as stream:
            assert stream.read() == b"private file\n"
    finally:
        store.close()
    assert attest(db_engine, context, identifier).replayed
    alias = attest(db_engine, context, variant(db_engine, uid=2))
    assert alias.case_id == receipt.case_id and alias.disposition == "alias"
    conflict = attest(db_engine, context, variant(db_engine, message(content=b"Y2hhbmdlZA=="), 3))
    assert conflict.case_id == receipt.case_id and conflict.state == "collision"
    assert [a.id for a in assets(db_engine)] == [row.id]
    with Session(db_engine) as db:
        case = db.get(MailTriageCase, receipt.case_id)
        assert (case.file_extraction_version, case.file_set_status, case.file_count) == (
            1,
            "complete",
            1,
        )


@pytest.mark.usefixtures("file_services")
def test_hidden_case_global_reader_indistinguishable_404_before_storage(
    db_engine, context, admin_client, monkeypatch
):
    from altvia.file_storage import S3Store
    from test_team_api import sign_in

    attest(db_engine, context, variant(db_engine), file_path("api"))
    identifier = assets(db_engine)[0].id
    sign_in(admin_client, "admin@example.test")

    def forbidden(*args, **kwargs):
        pytest.fail("Hidden parent reached S3")

    monkeypatch.setattr(S3Store, "verified_spool", forbidden)
    for suffix in ("", "/content", "/scan-retries"):

        def call(key, suffix=suffix):
            return (
                admin_client.post(
                    f"/api/v1/attachments/{key}{suffix}", json={}, headers=preconditions(1)
                )
                if suffix == "/scan-retries"
                else admin_client.get(f"/api/v1/attachments/{key}{suffix}")
            )

        denied, missing = call(identifier), call(uuid4())
        assert denied.status_code == missing.status_code == 404
        assert {k: v for k, v in denied.json().items() if k != "correlation_id"} == {
            k: v for k, v in missing.json().items() if k != "correlation_id"
        }


@pytest.mark.parametrize("failure", ["put", "config"])
@pytest.mark.usefixtures("file_services")
def test_still_new_storage_failure_has_no_db_effect(db_engine, context, monkeypatch, failure):
    from altvia.file_storage import S3Store, StorageError
    from altvia.models import MailboxSource

    identifier = variant(db_engine)
    with Session(db_engine) as db:
        before = db.scalar(select(MailboxSource.version))

    def unavailable(*args, **kwargs):
        raise StorageError("storage_unavailable")

    monkeypatch.setattr(S3Store, "put_new", unavailable)
    with pytest.raises(CaseError, match="case_storage_unavailable"):
        attest(
            db_engine,
            context,
            identifier,
            file_path("api") if failure == "put" else Path("missing-config"),
        )
    with Session(db_engine) as db:
        assert not list(db.scalars(select(MailTriageCase)))
        assert not list(db.scalars(select(MailCaseOrigin)))
        assert db.scalar(select(MailboxSource.version)) == before


@pytest.mark.usefixtures("file_services")
@pytest.mark.parametrize("fail", [False, True])
def test_contradictory_publication_during_staging_commits_even_on_put_failure(
    db_engine, context, monkeypatch, fail
):
    from altvia.file_storage import S3Store, StorageError

    identifier = variant(db_engine)
    entered, release = Event(), Event()
    original = S3Store.put_new

    def blocked(self, *args, **kwargs):
        entered.set()
        assert release.wait(15)
        if fail:
            raise StorageError("storage_unavailable")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(S3Store, "put_new", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(attest, db_engine, context, identifier, file_path("api"))
        try:
            assert entered.wait(10)
            other = attest(db_engine, context, variant(db_engine, RAW, 2))
        finally:
            release.set()
        result = future.result(timeout=15)
    assert result.case_id == other.case_id and result.disposition == "collision"
    with Session(db_engine) as db:
        assert db.get(MailTriageCase, result.case_id).state == "collision"
        assert db.get(MailCaseOrigin, identifier).disposition == "collision"
        assert not list(db.scalars(select(Attachment)))


@pytest.mark.usefixtures("file_services")
def test_concurrent_same_variant_has_one_file_set(db_engine, context, monkeypatch):
    from altvia.file_storage import S3Store

    identifier = variant(db_engine)
    barrier, staged = Barrier(4), []
    original = S3Store.put_new

    def concurrent(self, key, source, **kwargs):
        original(self, key, source, **kwargs)
        staged.append(key)
        barrier.wait(timeout=15)

    monkeypatch.setattr(S3Store, "put_new", concurrent)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: attest(db_engine, context, identifier, file_path("api")), range(4))
        )
    assert len({r.case_id for r in results}) == 1
    assert sum(not r.replayed for r in results) == 1
    assert len(assets(db_engine)) == 1
    assert len(set(staged)) == 4


@pytest.mark.usefixtures("file_services")
@pytest.mark.parametrize("change", ["contact", "event", "count"])
def test_final_change_rolls_back_metadata_and_retains_private_object(
    db_engine, context, monkeypatch, change
):
    from altvia import mail_cases_owner
    from altvia.file_storage import S3Store
    from altvia.file_storage_owner import load_storage
    from altvia.models import MailboxSource

    identifier = variant(db_engine)
    with Session(db_engine) as db:
        source_version = db.scalar(select(MailboxSource.version))
    if change == "count":
        monkeypatch.setattr(mail_cases_owner, "persist_case_files", lambda *args: ())
    original, staged = S3Store.put_new, []

    def changed(self, key, source, **kwargs):
        original(self, key, source, **kwargs)
        staged.append((key, kwargs))
        with db_engine.begin() as connection:
            if change == "contact":
                connection.execute(text("UPDATE client_contacts SET version=version+1"))
            elif change == "event":
                connection.execute(
                    text(
                        "ALTER TABLE outbox_events ADD CONSTRAINT refuse_file "
                        "CHECK(event_type<>'file.uploaded')"
                    )
                )

    monkeypatch.setattr(S3Store, "put_new", changed)
    try:
        with pytest.raises((CaseError, DBAPIError)):
            attest(db_engine, context, identifier, file_path("api"))
        assert len(staged) == 1
        with Session(db_engine) as db:
            assert not list(db.scalars(select(MailTriageCase)))
            assert not list(db.scalars(select(Attachment)))
            assert not list(db.scalars(select(MailCaseOrigin)))
            assert db.scalar(select(MailboxSource.version)) == source_version
        store = S3Store(load_storage(file_path("api")))
        try:
            with store.verified_spool(staged[0][0], **staged[0][1]) as source:
                assert source.read() == b"private file\n"
        finally:
            store.close()
    finally:
        if change == "event":
            with db_engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE outbox_events DROP CONSTRAINT IF EXISTS refuse_file")
                )


def case_values(db, refs, identifier, **extra):
    from altvia.models import (
        ClientContact,
        InboundMailEnvelope,
        InboundMailPreview,
        InboundMailVariant,
        MailboxSource,
    )

    source = db.scalar(select(MailboxSource))
    raw = db.get(InboundMailVariant, identifier)
    envelope = db.get(InboundMailEnvelope, raw.envelope_id)
    preview = db.get(InboundMailPreview, (identifier, 2))
    contact = db.get(ClientContact, UUID(refs["requester_id"]))
    return dict(
        source_id=source.id,
        queue_id=source.queue_id,
        client_id=UUID(refs["client_id"]),
        contact_id=UUID(refs["requester_id"]),
        primary_variant_id=identifier,
        email_snapshot="requester@example.test",
        contact_name=contact.display_name,
        subject=preview.subject,
        body_text=preview.body_text,
        references_ids=[],
        received_at=envelope.created_at,
        state="ready",
        version=1,
        **extra,
    )


def file_values(case_id, **extra):
    return (
        dict(
            mail_case_id=case_id,
            file_position=0,
            purpose="incoming",
            creator_id=None,
            parent_version=1,
            filename="proof.txt",
            media_type="text/plain",
            bytes=1,
            sha256=hashlib.sha256(b"x").hexdigest(),
            object_key="objects/" + uuid4().hex + uuid4().hex,
        )
        | extra
    )


def test_sql_header_defaults_count_positions_and_identity(db_engine, context):
    identifier = variant(db_engine)
    with Session(db_engine) as db, db.begin():
        legacy = MailTriageCase(**case_values(db, context, identifier))
        db.add(legacy)
        db.flush()
        legacy_id = legacy.id
        assert (legacy.file_extraction_version, legacy.file_set_status, legacy.file_count) == (
            0,
            "legacy",
            0,
        )
    for header, files in [
        ({"file_count": 1}, []),
        ({"file_count": 0}, [0]),
        ({"file_count": 2}, [0]),
        ({"file_count": 2}, [0, 0]),
        ({"file_count": 2}, [0, 2]),
        (
            {
                "file_set_status": "unavailable",
                "file_rejection_reason": "file_type",
                "file_count": 1,
            },
            [0],
        ),
        ({"file_set_status": "unavailable", "file_rejection_reason": "private-input"}, []),
        ({"file_set_status": "complete", "file_rejection_reason": "file_type"}, []),
    ]:
        with pytest.raises(DBAPIError), Session(db_engine) as db, db.begin():
            case = MailTriageCase(
                **case_values(
                    db,
                    context,
                    identifier,
                    **(
                        {
                            "file_extraction_version": 1,
                            "file_set_status": "complete",
                            "file_count": 0,
                        }
                        | header
                    ),
                )
            )
            db.add(case)
            db.flush()
            db.add_all(Attachment(**file_values(case.id, file_position=p)) for p in files)
    with pytest.raises(DBAPIError), Session(db_engine) as db, db.begin():
        db.add(Attachment(**file_values(legacy_id)))
    with Session(db_engine) as db, db.begin():
        case = MailTriageCase(
            **case_values(
                db,
                context,
                identifier,
                file_extraction_version=1,
                file_set_status="complete",
                file_count=2,
            )
        )
        db.add(case)
        db.flush()
        db.add_all(Attachment(**file_values(case.id, file_position=p)) for p in (1, 0))
        case_id = case.id
    for statement in (
        "UPDATE mail_triage_cases SET file_count=0,version=version+1",
        "UPDATE mail_triage_cases SET file_extraction_version=0,version=version+1",
        "UPDATE attachments SET file_position=3,version=version+1",
        "UPDATE attachments SET mail_case_id=NULL,version=version+1",
        "DELETE FROM attachments",
    ):
        with pytest.raises(DBAPIError), db_engine.begin() as connection:
            connection.execute(text(statement))
    assert [r.file_position for r in assets(db_engine) if r.mail_case_id == case_id] == [0, 1]


@pytest.mark.parametrize(
    "bad",
    [
        {"creator_id": "actor"},
        {"mail_case_id": None},
        {"purpose": "public"},
        {"parent_version": 2},
        {"file_position": None},
        {"file_position": -1},
        {"ticket_id": "ticket"},
        {"work_item_id": "work"},
    ],
)
def test_sql_exact_case_provenance(db_engine, context, seeded_user, bad):
    identifier = variant(db_engine)
    with pytest.raises(DBAPIError), Session(db_engine) as db, db.begin():
        case = MailTriageCase(
            **case_values(
                db,
                context,
                identifier,
                file_extraction_version=1,
                file_set_status="complete",
                file_count=1,
            )
        )
        db.add(case)
        db.flush()
        override = {
            key: seeded_user
            if value == "actor"
            else uuid4()
            if value in ("ticket", "work")
            else value
            for key, value in bad.items()
        }
        db.add(Attachment(**file_values(case.id, **override)))


@pytest.mark.usefixtures("file_services")
def test_worker_real_credentials_scan_without_parent_or_name_grants(db_engine, context, tmp_path):
    from datetime import UTC, datetime

    from altvia import attachment_scan as scan
    from altvia.activity import consume_event
    from altvia.file_storage import S3Store
    from altvia.file_storage_owner import load_storage
    from altvia.provision import WORKER_COLUMN_READS, provision_runtime
    from sqlalchemy import create_engine
    from test_file_scan_transport import daemon
    from test_runtime_provision import runtime_url

    attest(db_engine, context, variant(db_engine), file_path("api"))
    identifier = assets(db_engine)[0].id
    api_url = runtime_url(db_engine)
    worker_url = api_url.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        api_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    worker, api = (
        create_engine(worker_url, hide_parameters=True),
        create_engine(api_url, hide_parameters=True),
    )
    assert WORKER_COLUMN_READS["attachments"] == scan.SCAN_COLUMNS
    try:
        with worker.connect() as connection:
            for table in ("mail_triage_cases", "mail_case_origins", "inbound_mail_variants"):
                assert not connection.scalar(
                    text("SELECT has_table_privilege(current_user,:t,'SELECT')"), {"t": table}
                )
            for column in (
                "filename",
                "mail_case_id",
                "file_position",
                "ticket_id",
                "work_item_id",
            ):
                assert not connection.scalar(
                    text("SELECT has_column_privilege(current_user,'attachments',:c,'SELECT')"),
                    {"c": column},
                )
        for statement in (
            "SELECT file_rejection_reason FROM mail_triage_cases",
            "SELECT * FROM mail_case_origins",
            "SELECT * FROM inbound_mail_variants",
            "SELECT * FROM inbound_mail_previews",
            "SELECT * FROM mailbox_poll_states",
        ):
            with pytest.raises(DBAPIError) as denied, api.begin() as connection:
                connection.execute(text(statement))
            assert denied.value.orig.sqlstate == "42501"
        for statement in (
            "SELECT * FROM mail_triage_cases",
            "SELECT id FROM mail_triage_cases",
            "SELECT filename FROM attachments",
            "SELECT mail_case_id FROM attachments",
            "SELECT file_position FROM attachments",
            "SELECT ticket_id,work_item_id FROM attachments",
            "SELECT * FROM mail_case_origins",
            "SELECT * FROM inbound_mail_variants",
            "SELECT * FROM inbound_mail_previews",
            "SELECT * FROM mailbox_poll_states",
        ):
            with pytest.raises(DBAPIError) as denied, worker.begin() as connection:
                connection.execute(text(statement))
            assert denied.value.orig.sqlstate == "42501"
        with pytest.raises(DBAPIError) as denied, Session(api) as db, db.begin():
            db.add(Attachment(**file_values(assets(db_engine)[0].mail_case_id, file_position=1)))
        assert "owner" in str(denied.value).lower()
        owned = scan.claim(worker, identifier)
        assert owned is not None
        version = f"ClamAV 1.4.6/28181/{owned.db_now.strftime('%a %b %d %H:%M:%S %Y')}\0".encode()
        store = S3Store(load_storage(file_path("scanner")))
        try:
            with daemon(tmp_path, [version, b"stream: OK\0", version]) as (scanner, received):
                assert scan.run_claim(worker, owned, store, scanner, Event())
                assert received == [b"private file\n"]
        finally:
            store.close()
        assert assets(db_engine)[0].state == "ready"
        with Session(db_engine) as db:
            events = list(
                db.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.aggregate_id == identifier)
                    .order_by(OutboxEvent.aggregate_version)
                )
            )
            assert [e.schema_version for e in events] == [2, 1, 1]
            assert [e.payload["actor_kind"] for e in events] == [
                "management_command",
                "file_worker",
                "file_worker",
            ]
        for event in events:
            assert consume_event(worker, event.event_id, datetime.now(UTC))
            assert not consume_event(worker, event.event_id, datetime.now(UTC))
    finally:
        worker.dispose()
        api.dispose()


@pytest.mark.usefixtures("file_services")
def test_ordered_duplicate_files_and_owner_events_consumed_privately(db_engine, context):
    from datetime import UTC, datetime

    from altvia.activity import consume_event
    from altvia.models import ActivityEvent, AuditLog, ProcessedEvent

    raw = message()
    part = raw[raw.index(b"--b\r\nContent-Type: application") : raw.index(b"--b--")]
    raw = raw.replace(b"--b--", part + b"--b--")
    receipt = attest(db_engine, context, variant(db_engine, raw), file_path("api"))
    rows = assets(db_engine)
    assert [row.file_position for row in rows] == [0, 1]
    assert rows[0].object_key != rows[1].object_key
    assert rows[0].sha256 == rows[1].sha256
    with Session(db_engine) as db:
        assert db.get(MailTriageCase, receipt.case_id).file_count == 2
        events = list(
            db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "file.uploaded"))
        )
        for event in events:
            assert event.schema_version == 2 and event.aggregate_version == 1
            assert event.payload == {
                "actor_id": None,
                "actor_kind": "management_command",
                "attachment_id": str(event.aggregate_id),
                "state": "quarantine",
            }
            audit = db.scalar(
                select(AuditLog).where(
                    AuditLog.resource_id == event.aggregate_id, AuditLog.action == "file.uploaded"
                )
            )
            assert audit.details == event.payload
        assert len(events) == 2
    for event in events:
        assert consume_event(db_engine, event.event_id, datetime.now(UTC))
        assert not consume_event(db_engine, event.event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert not list(
            db.scalars(select(ActivityEvent).where(ActivityEvent.event_type.like("file.%")))
        )
        assert (
            len(
                list(
                    db.scalars(
                        select(ProcessedEvent).where(
                            ProcessedEvent.event_id.in_([e.event_id for e in events])
                        )
                    )
                )
            )
            == 2
        )


def test_configuration_failure_still_commits_concurrent_collision(db_engine, context, monkeypatch):
    from altvia import mail_case_files

    identifier = variant(db_engine)
    entered, release = Event(), Event()

    def invalid_config(path):
        entered.set()
        assert release.wait(15)
        raise ValueError("invalid_storage_configuration")

    monkeypatch.setattr(mail_case_files, "load_storage", invalid_config)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(attest, db_engine, context, identifier, Path("missing-config"))
        try:
            assert entered.wait(10)
            winner = attest(db_engine, context, variant(db_engine, RAW, 2))
        finally:
            release.set()
        result = future.result(timeout=15)
    assert result.case_id == winner.case_id and result.state == "collision"
    with Session(db_engine) as db:
        assert db.get(MailCaseOrigin, identifier).disposition == "collision"


def test_old_staff_creator_and_position_requirements(db_engine, context, admin_client, seeded_user):
    from test_tickets import ticket

    ticket_id = UUID(ticket(admin_client, context).rsplit("/", 1)[1])
    for override in ({"creator_id": None}, {"file_position": 0}, {"purpose": "incoming"}):
        with pytest.raises(DBAPIError) as denied, Session(db_engine) as db, db.begin():
            db.add(
                Attachment(
                    **file_values(
                        None,
                        **(
                            {
                                "ticket_id": ticket_id,
                                "file_position": None,
                                "purpose": "public",
                                "creator_id": seeded_user,
                            }
                            | override
                        ),
                    )
                )
            )
        assert denied.value.orig.diag.constraint_name == "ck_attachment_owner"
    with Session(db_engine) as db, db.begin():
        db.add(
            Attachment(
                **file_values(
                    None,
                    ticket_id=ticket_id,
                    file_position=None,
                    purpose="public",
                    creator_id=seeded_user,
                )
            )
        )


def test_migration_preserves_legacy_case_origin_staff_file_and_replays_without_storage(
    db_engine, context, admin_client, seeded_user
):
    from alembic import command
    from alembic.config import Config
    from altvia.models import InboundMailEnvelope, InboundMailVariant
    from test_tickets import ticket

    identifier = variant(db_engine)
    ticket_id = UUID(ticket(admin_client, context).rsplit("/", 1)[1])
    from sla_migration_support import pre_sla_ticket

    pre_sla_ticket(db_engine, ticket_id)
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000026")
    case_id, file_id = uuid4(), uuid4()
    try:
        with Session(db_engine) as db, db.begin():
            values = case_values(
                db, context, identifier, id=case_id, message_id="<incoming@example.test>"
            )
            db.execute(MailTriageCase.__table__.insert().values(**values))
            raw = db.get(InboundMailVariant, identifier)
            envelope = db.get(InboundMailEnvelope, raw.envelope_id)
            db.add(
                MailCaseOrigin(
                    variant_id=identifier,
                    case_id=case_id,
                    source_id=envelope.source_id,
                    envelope_id=envelope.id,
                    raw_sha256=raw.raw_sha256,
                    client_id=UUID(context["client_id"]),
                    contact_id=UUID(context["requester_id"]),
                    email_snapshot="requester@example.test",
                    contact_version=1,
                    evidence="synthetic:proof",
                    routing_version=1,
                    parser_version=2,
                    disposition="primary",
                )
            )
            file = file_values(
                None, id=file_id, ticket_id=ticket_id, purpose="public", creator_id=seeded_user
            )
            del file["mail_case_id"]
            del file["file_position"]
            db.execute(Attachment.__table__.insert().values(**file))
        command.upgrade(config, "head")
        command.check(config)
        with Session(db_engine) as db:
            case = db.get(MailTriageCase, case_id)
            assert (
                case.file_extraction_version,
                case.file_set_status,
                case.file_count,
                case.file_rejection_reason,
            ) == (0, "legacy", 0, None)
            file = db.get(Attachment, file_id)
            assert (
                file.creator_id == seeded_user
                and file.mail_case_id is None
                and file.file_position is None
            )
        assert attest(db_engine, context, identifier, Path("missing-config")).replayed
        alias = attest(db_engine, context, variant(db_engine, uid=2), Path("missing-config"))
        assert alias.case_id == case_id and alias.disposition == "alias"
        with Session(db_engine) as db:
            assert db.get(MailTriageCase, case_id).file_extraction_version == 0
        command.downgrade(config, "b46087000026")
        command.upgrade(config, "head")
        command.check(config)
    finally:
        command.upgrade(config, "head")


@pytest.mark.parametrize("kind", ["empty", "unavailable", "event", "audit"])
def test_migration_refuses_new_interpretation_and_private_history(db_engine, context, kind):
    from datetime import UTC, datetime

    from alembic import command
    from alembic.config import Config
    from altvia.models import AuditLog

    if kind in {"empty", "unavailable"}:
        attest(
            db_engine,
            context,
            variant(db_engine, RAW if kind == "empty" else message(name=b"x.zip")),
        )
    else:
        with Session(db_engine) as db, db.begin():
            identifier, now = uuid4(), datetime.now(UTC)
            payload = {
                "actor_id": None,
                "actor_kind": "management_command",
                "attachment_id": str(identifier),
                "state": "quarantine",
            }
            if kind == "event":
                db.add(
                    OutboxEvent(
                        aggregate_type="attachment",
                        aggregate_id=identifier,
                        aggregate_version=1,
                        event_type="file.uploaded",
                        schema_version=2,
                        payload=payload,
                        occurred_at=now,
                        correlation_id=uuid4().hex,
                        next_attempt_at=now,
                    )
                )
            else:
                db.add(
                    AuditLog(
                        actor_id=None,
                        action="file.uploaded",
                        resource_id=identifier,
                        occurred_at=now,
                        correlation_id=uuid4().hex,
                        details=payload,
                    )
                )
    with pytest.raises(DBAPIError, match="Cannot contract incoming files/history"):
        command.downgrade(Config("apps/api/alembic.ini"), "b46087000026")


@pytest.mark.usefixtures("file_services")
@pytest.mark.parametrize(
    "poison", [{"filename": "private-poison"}, {"actor_kind": "user"}, {"state": "ready"}]
)
def test_owner_file_consumer_rejects_invalid_metadata_without_activity(db_engine, context, poison):
    from datetime import UTC, datetime

    from altvia.activity import consume_event
    from altvia.models import ActivityEvent, ProcessedEvent

    attest(db_engine, context, variant(db_engine), file_path("api"))
    identifier = assets(db_engine)[0].id
    with Session(db_engine) as db, db.begin():
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == identifier))
        event.payload = {**event.payload, **poison}
        event_id = event.event_id
    assert not consume_event(db_engine, event_id, datetime.now(UTC))
    with Session(db_engine) as db:
        assert db.get(OutboxEvent, event_id).last_error_code == "invalid_event"
        assert not list(
            db.scalars(select(ProcessedEvent).where(ProcessedEvent.event_id == event_id))
        )
        assert not list(
            db.scalars(select(ActivityEvent).where(ActivityEvent.event_type.like("file.%")))
        )
