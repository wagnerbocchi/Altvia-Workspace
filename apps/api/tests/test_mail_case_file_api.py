"""Current incoming-file scope with actual PostgreSQL, API and private S3."""

from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from altvia.file_storage import S3Store
from altvia.models import MailTriageCase
from file_core_support import file_path, file_services
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_attachments import controlled_ready
from test_mail_case_files import assets, attest, case_values, message, variant
from test_mail_cases import context
from test_mail_promotion import promote
from test_team_api import admin_client, preconditions, sign_in

__all__ = ["admin_client", "context", "file_services"]
pytestmark = pytest.mark.usefixtures("file_services")


def published(engine, refs):
    receipt = attest(engine, refs, variant(engine), file_path("api"))
    return receipt, assets(engine)[0]


def test_current_detail_summary_and_incoming_projection(db_engine, context, admin_client):
    case, asset = published(db_engine, context)
    path = f"/api/v1/mail-cases/{case.case_id}"
    detail = admin_client.get(path)
    assert detail.status_code == 200, detail.text
    files = detail.json()["files"]
    assert files["extraction_version"] == 1 and files["status"] == "complete"
    assert len(files["items"]) == 1
    item = files["items"][0]
    assert (item["id"], item["owner_type"], item["owner_id"], item["purpose"]) == (
        str(asset.id),
        "mail_case",
        str(case.case_id),
        "incoming",
    )
    assert not item["can_download"] and not item["can_retry_scan"]
    assert admin_client.get(f"/api/v1/attachments/{asset.id}").json() == item
    summary = admin_client.get("/api/v1/mail-cases").json()["items"][0]
    assert set(summary) == {
        "id",
        "queue_id",
        "queue_name",
        "client_id",
        "client_name",
        "contact_id",
        "contact_name",
        "subject",
        "received_at",
        "created_at",
        "state",
        "version",
    }
    key = uuid4().hex
    promotion = promote(admin_client, case.case_id, key=key)
    assert promotion.status_code == 201, promotion.text
    receipt = promotion.json()
    assert set(receipt) == {"case_id", "ticket_id", "incoming_message_id"}
    assert promote(admin_client, case.case_id, key=key).json() == receipt
    ticket = "/api/v1/tickets/" + receipt["ticket_id"]
    incoming = admin_client.get(ticket + "/incoming-messages/" + receipt["incoming_message_id"])
    assert incoming.json()["files"] == files
    assert admin_client.get(ticket + "/conversation").json()["items"][0] == incoming.json()
    assert admin_client.get(path).headers["etag"] == '"2"'


@pytest.mark.parametrize("change", ["admin", "ceiling", "queue"])
def test_no_file_identity_without_current_case_authority(
    db_engine, context, admin_client, seeded_user, monkeypatch, change
):
    case, asset = published(db_engine, context)
    if change == "admin":
        sign_in(admin_client, "admin@example.test")
    else:
        with db_engine.begin() as db:
            db.execute(
                text(
                    "DELETE FROM client_access_grants WHERE user_id=:id"
                    if change == "ceiling"
                    else "DELETE FROM role_bindings WHERE user_id=:id AND scope_kind='queue'"
                ),
                {"id": seeded_user},
            )
    monkeypatch.setattr(S3Store, "verified_spool", lambda *a, **k: pytest.fail("S3 reached"))
    for suffix in ("", "/content", "/scan-retries"):

        def call(identifier, suffix=suffix):
            path = f"/api/v1/attachments/{identifier}{suffix}"
            return (
                admin_client.post(path, json={}, headers=preconditions())
                if suffix == "/scan-retries"
                else admin_client.get(path)
            )

        # Content is GET; retry is the only POST.
        path = f"/api/v1/attachments/{asset.id}{suffix}"
        response = (
            admin_client.post(path, json={}, headers=preconditions())
            if suffix == "/scan-retries"
            else admin_client.get(path)
        )
        assert response.status_code == 404, response.text
        missing = call(uuid4())
        assert missing.status_code == 404
        assert {k: v for k, v in response.json().items() if k != "correlation_id"} == {
            k: v for k, v in missing.json().items() if k != "correlation_id"
        }
        assert str(asset.id) not in response.text and asset.filename not in response.text
    assert admin_client.get(f"/api/v1/mail-cases/{case.case_id}").status_code == 404


@pytest.mark.parametrize("kind", ["legacy", "unavailable", "empty"])
def test_fixed_legacy_unavailable_and_empty_headers(db_engine, context, admin_client, kind):
    from test_mail_cases import RAW

    raw = message(name=b"hostile.zip") if kind == "unavailable" else RAW
    identifier = variant(db_engine, raw)
    if kind == "legacy":
        with Session(db_engine) as db, db.begin():
            case = MailTriageCase(**case_values(db, context, identifier))
            db.add(case)
            db.flush()
            case_id = case.id
    else:
        case_id = attest(db_engine, context, identifier).case_id
    response = admin_client.get(f"/api/v1/mail-cases/{case_id}")
    assert response.status_code == 200, response.text
    assert response.json()["files"] == {
        "extraction_version": 0 if kind == "legacy" else 1,
        "status": "complete" if kind == "empty" else kind,
        "items": [],
    }
    assert "hostile" not in response.text and "file_rejection_reason" not in response.text


@pytest.mark.parametrize("change,status", [("ceiling", 404), ("collision", 409), ("session", 401)])
def test_download_rechecks_after_actual_s3(
    db_engine, context, admin_client, seeded_user, tmp_path, monkeypatch, change, status
):
    from altvia.management import reset_password
    from conftest import TEST_PASSWORD
    from test_mail_intake import capture

    case, asset = published(db_engine, context)
    controlled_ready(admin_client, db_engine, asset.id, tmp_path)
    route = f"/api/v1/attachments/{asset.id}"
    assert admin_client.get(route).json()["can_download"]
    assert admin_client.get(route + "/content").content == b"private file\n"
    original = S3Store.verified_spool

    @contextmanager
    def changed(self, *args, **kwargs):
        with original(self, *args, **kwargs) as source:
            if change == "collision":
                capture(db_engine, message() + b"changed", uid=1)
            else:
                with Session(db_engine) as db, db.begin():
                    db.execute(text("SET LOCAL lock_timeout='1s'"))
                    if change == "ceiling":
                        db.execute(
                            text("DELETE FROM client_access_grants WHERE user_id=:id"),
                            {"id": seeded_user},
                        )
                    else:
                        reset_password(db, "employee@example.test", TEST_PASSWORD)
            yield source

    monkeypatch.setattr(S3Store, "verified_spool", changed)
    result = admin_client.get(route + "/content")
    assert result.status_code == status, result.text
    assert b"private file" not in result.content
    if change == "collision":
        monkeypatch.setattr(
            S3Store, "verified_spool", lambda *a, **k: pytest.fail("invalidated S3")
        )
        assert not admin_client.get(route).json()["can_download"]
        assert admin_client.get(route + "/content").status_code == 409
        assert admin_client.get(f"/api/v1/mail-cases/{case.case_id}").json()["files"]["items"][0][
            "id"
        ] == str(asset.id)


def failed(engine, identifier):
    from altvia import attachment_scan as scan

    for number in range(1, 9):
        claim = scan.claim(engine, identifier)
        assert claim.attempt == number
        assert scan.finalize(engine, claim, scan.ScanResult("failed", "unavailable"))
        if number < 8:
            with engine.begin() as db:
                db.execute(text("ALTER TABLE attachments DISABLE TRIGGER attachment_guard"))
                db.execute(
                    text("UPDATE attachments SET next_attempt_at=clock_timestamp() WHERE id=:id"),
                    {"id": identifier},
                )
                db.execute(text("ALTER TABLE attachments ENABLE TRIGGER attachment_guard"))


def test_manager_retry_protected_receipt_and_history(db_engine, context, admin_client):
    from altvia import attachment_scan as scan
    from altvia.models import AttachmentScanAttempt

    _, asset = published(db_engine, context)
    failed(db_engine, asset.id)
    route = f"/api/v1/attachments/{asset.id}"
    detail = admin_client.get(route).json()
    assert detail["can_retry_scan"]
    headers = preconditions(detail["version"])
    result = admin_client.post(route + "/scan-retries", json={}, headers=headers)
    assert result.status_code == 201, result.text
    claim = scan.claim(db_engine, asset.id)
    assert claim.generation == 2 and claim.attempt == 1
    replay = admin_client.post(route + "/scan-retries", json={}, headers=headers)
    assert replay.status_code == 200 and replay.json() == result.json()
    with Session(db_engine) as db:
        assert len(list(db.scalars(select(AttachmentScanAttempt)))) == 8
    sign_in(admin_client, "agent@example.test")
    assert not admin_client.get(route).json()["can_retry_scan"]
    assert admin_client.post(route + "/scan-retries", json={}, headers=headers).status_code == 403


@pytest.mark.parametrize(
    "change,status",
    [
        ("agent", 403),
        ("viewer", 403),
        ("ticket_queues", 409),
        ("clients", 409),
        ("teams", 409),
        ("revoked", 409),
        ("closed", 409),
    ],
)
def test_retry_current_action_and_fresh_eligibility(
    db_engine, context, admin_client, change, status
):
    from altvia.mail_cases_owner import revoke_case

    case, asset = published(db_engine, context)
    failed(db_engine, asset.id)
    route = f"/api/v1/attachments/{asset.id}"
    version = admin_client.get(route).json()["version"]
    if change in {"agent", "viewer"}:
        sign_in(admin_client, change + "@example.test")
    elif change in {"ticket_queues", "clients", "teams"}:
        with db_engine.begin() as db:
            db.execute(text(f"UPDATE {change} SET active=false,version=version+1"))
    elif change == "revoked":
        revoke_case(db_engine, case.case_id, 1)
    else:
        result = promote(admin_client, case.case_id)
        assert result.status_code == 201
        with db_engine.begin() as db:
            db.execute(
                text(
                    "UPDATE tickets SET status='closed',resolved_at=clock_timestamp(),"
                    "closed_at=clock_timestamp(),version=version+1"
                )
            )
    assert not admin_client.get(route).json()["can_retry_scan"]
    response = admin_client.post(route + "/scan-retries", json={}, headers=preconditions(version))
    assert response.status_code == status, response.text


def test_promoted_target_scope_suppresses_entire_block_and_global_reads(
    db_engine, context, admin_client, monkeypatch
):
    from altvia import tickets
    from altvia.models import Ticket

    case, asset = published(db_engine, context)
    receipt = promote(admin_client, case.case_id).json()
    # Current immutable parents share grants. Narrow the real target query to
    # exercise the independent resulting-ticket guard, not a fabricated HTTP error.
    original = tickets.visible
    monkeypatch.setattr(
        tickets,
        "visible",
        lambda actor: original(actor).where(Ticket.id != UUID(receipt["ticket_id"])),
    )
    monkeypatch.setattr(S3Store, "verified_spool", lambda *a, **k: pytest.fail("hidden S3"))
    detail = admin_client.get(f"/api/v1/mail-cases/{case.case_id}")
    assert detail.status_code == 200
    assert detail.json()["files"] is None and detail.json()["promotion_receipt"] is None
    assert asset.filename not in detail.text and str(asset.id) not in detail.text
    for suffix in ("", "/content", "/scan-retries"):
        route = f"/api/v1/attachments/{asset.id}{suffix}"
        result = (
            admin_client.post(route, json={}, headers=preconditions())
            if suffix == "/scan-retries"
            else admin_client.get(route)
        )
        assert result.status_code == 404, result.text


def test_batched_case_sets_keep_query_growth_bounded(db_engine, context, admin_client, seeded_user):
    from altvia.attachments import case_file_sets
    from sqlalchemy import event

    identifiers = []
    for number in range(1, 6):
        raw = message().replace(
            b"<incoming@example.test>", f"<incoming{number}@example.test>".encode()
        )
        case = attest(db_engine, context, variant(db_engine, raw, number), file_path("api"))
        assert promote(admin_client, case.case_id).status_code == 201
        identifiers.append(case.case_id)
    queries = []

    def observed(connection, cursor, statement, parameters, execution_context, many):
        queries.append(statement)

    event.listen(db_engine, "before_cursor_execute", observed)
    try:
        with Session(db_engine) as db:
            single = case_file_sets(db, seeded_user, identifiers[:1])
        single_count = len(queries)
        queries.clear()
        with Session(db_engine) as db:
            batch = case_file_sets(db, seeded_user, identifiers)
        assert len(queries) == single_count == 3
        assert len(batch) == 5 and batch[identifiers[0]] == single[identifiers[0]]
        assert all(len(value.items) == 1 for value in batch.values())
    finally:
        event.remove(db_engine, "before_cursor_execute", observed)


def test_actual_runtime_header_only_grants_and_file_reads(db_engine, context, settings, tmp_path):
    from altvia.attachment_scan import SCAN_COLUMNS
    from altvia.mail_cases import READ_COLUMNS, ROUTING_COLUMNS
    from altvia.main import create_app
    from altvia.provision import APP_COLUMN_READS, WORKER_COLUMN_READS, provision_runtime
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError
    from test_runtime_provision import runtime_url

    case, asset = published(db_engine, context)
    api_url = runtime_url(db_engine)
    worker_url = api_url.set(username="altvia_worker")
    provision_runtime(
        db_engine,
        api_url.render_as_string(hide_password=False),
        worker_url.render_as_string(hide_password=False),
    )
    assert APP_COLUMN_READS["mail_triage_cases"] - READ_COLUMNS - ROUTING_COLUMNS == {
        "file_extraction_version",
        "file_set_status",
    }
    assert WORKER_COLUMN_READS["attachments"] == SCAN_COLUMNS
    runtime = settings.model_copy(
        update={"database_url": SecretStr(api_url.render_as_string(hide_password=False))}
    )
    with TestClient(
        create_app(runtime),
        base_url=settings.public_origin,
        headers={"Origin": settings.public_origin},
    ) as client:
        sign_in(client, "employee@example.test")
        assert client.get(f"/api/v1/mail-cases/{case.case_id}").json()["files"]["items"][0][
            "id"
        ] == str(asset.id)
        route = f"/api/v1/attachments/{asset.id}"
        failed(db_engine, asset.id)
        version = client.get(route).json()["version"]
        assert (
            client.post(
                route + "/scan-retries", json={}, headers=preconditions(version)
            ).status_code
            == 201
        )
        controlled_ready(client, db_engine, asset.id, tmp_path)
        assert client.get(route + "/content").content == b"private file\n"
        receipt = promote(client, case.case_id).json()
        path = "/api/v1/tickets/" + receipt["ticket_id"]
        assert client.get(path + "/conversation").json()["items"][0]["files"]["items"][0][
            "can_download"
        ]
    for url in (api_url, worker_url):
        engine = create_engine(url, hide_parameters=True)
        try:
            statements = [
                "SELECT * FROM mail_triage_cases",
                "SELECT file_rejection_reason FROM mail_triage_cases",
                "SELECT file_count FROM mail_triage_cases",
                "SELECT source_id,primary_variant_id FROM mail_triage_cases",
                "SELECT * FROM mail_case_origins",
                "SELECT * FROM inbound_mail_variants",
                "SELECT * FROM inbound_mail_previews",
                "SELECT * FROM mailbox_poll_states",
            ]
            if url.username == "altvia_worker":
                statements.extend(
                    [
                        "SELECT id FROM mail_triage_cases",
                        "SELECT file_extraction_version,file_set_status FROM mail_triage_cases",
                        "SELECT filename FROM attachments",
                        "SELECT mail_case_id,file_position FROM attachments",
                        "SELECT ticket_id,work_item_id FROM attachments",
                    ]
                )
            else:
                with engine.connect() as db:
                    assert db.execute(
                        text(
                            "SELECT file_extraction_version,file_set_status FROM mail_triage_cases"
                        )
                    ).one() == (1, "complete")
            for statement in statements:
                with pytest.raises(DBAPIError) as denied, engine.begin() as db:
                    db.execute(text(statement))
                assert denied.value.orig.sqlstate == "42501"
        finally:
            engine.dispose()


def test_retry_protocol_saved_authority_and_no_malware_release(
    db_engine, context, admin_client, seeded_user
):
    from altvia import attachment_scan as scan

    _, asset = published(db_engine, context)
    failed(db_engine, asset.id)
    route = f"/api/v1/attachments/{asset.id}"
    version = admin_client.get(route).json()["version"]
    headers = preconditions(version)
    assert admin_client.post(route + "/scan-retries", json={}).status_code == 428
    assert (
        admin_client.post(
            route + "/scan-retries", json={"state": "ready"}, headers=headers
        ).status_code
        == 422
    )
    assert (
        admin_client.post(route + "/scan-retries", json={}, headers=preconditions(1)).status_code
        == 409
    )
    first = admin_client.post(route + "/scan-retries", json={}, headers=headers)
    assert first.status_code == 201
    claimed = scan.claim(db_engine, asset.id)
    assert scan.finalize(
        db_engine, claimed, scan.ScanResult("infected", "infected", "1.4.6", 28181, claimed.db_now)
    )
    detail = admin_client.get(route).json()
    assert (
        detail["state"] == "rejected"
        and not detail["can_download"]
        and not detail["can_retry_scan"]
    )
    assert (
        admin_client.post(
            route + "/scan-retries", json={}, headers=preconditions(detail["version"])
        ).status_code
        == 409
    )
    replay = admin_client.post(route + "/scan-retries", json={}, headers=headers)
    assert replay.status_code == 200 and replay.json() == first.json()
    with db_engine.begin() as db:
        db.execute(
            text(
                "UPDATE role_bindings SET role_name='agent' "
                "WHERE user_id=:id AND scope_kind='queue'"
            ),
            {"id": seeded_user},
        )
    assert admin_client.post(route + "/scan-retries", json={}, headers=headers).status_code == 403


def test_actual_object_integrity_before_bytes(db_engine, context, admin_client, tmp_path):
    from altvia.file_storage import BUCKET, s3_client
    from altvia.file_storage_owner import load_storage

    _, asset = published(db_engine, context)
    controlled_ready(admin_client, db_engine, asset.id, tmp_path)
    owner = s3_client(load_storage(file_path("owner")))
    try:
        owner.put_object(Bucket=BUCKET, Key=asset.object_key, Body=b"corrupt bytes")
    finally:
        owner.close()
    result = admin_client.get(f"/api/v1/attachments/{asset.id}/content")
    assert result.status_code == 503 and result.json()["code"] == "file_unavailable"
    assert result.headers["retry-after"] == "5"
    assert b"private file" not in result.content and "corrupt bytes" not in result.text


def test_ordered_readable_files_never_become_upload_inputs(db_engine, context, admin_client):
    from test_attachments import upload
    from test_tickets import ticket

    raw = message()
    part = raw[raw.index(b"--b\r\nContent-Type: application") : raw.index(b"--b--")]
    raw = raw.replace(b"--b--", part.replace(b"proof.txt", b"second.log") + b"--b--")
    case = attest(db_engine, context, variant(db_engine, raw), file_path("api"))
    for actor in ("employee", "agent", "viewer"):
        sign_in(admin_client, actor + "@example.test")
        detail = admin_client.get(f"/api/v1/mail-cases/{case.case_id}")
        assert detail.status_code == 200
        assert [item["filename"] for item in detail.json()["files"]["items"]] == [
            "proof.txt",
            "second.log",
        ]
    sign_in(admin_client, "employee@example.test")
    parent = ticket(admin_client, context)
    assert upload(admin_client, parent, purpose="incoming").status_code == 422
    assert admin_client.get(parent + "/attachments?purpose=incoming").status_code == 422
    assert (
        admin_client.post(
            f"/api/v1/mail-cases/{case.case_id}/attachments", content=b"x"
        ).status_code
        == 404
    )
    assert admin_client.get(f"/api/v1/mail-cases/{case.case_id}/attachments").status_code == 404
