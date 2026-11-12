"""Real PostgreSQL/S3 protected binary assets, never mocked HTTP status."""

import hashlib
from uuid import uuid4

import pytest
from file_core_support import file_path, file_services
from test_team_api import admin_client, preconditions
from test_tickets import setup, ticket

__all__ = ["admin_client", "file_services"]

pytestmark = pytest.mark.usefixtures("file_services")


def upload(
    client,
    path,
    content=b"private text\n",
    *,
    key=None,
    version=1,
    purpose="public",
    filename="proof.txt",
    **extra,
):
    return client.post(
        path + "/attachments",
        params={"purpose": purpose, "filename": filename},
        content=content,
        headers={
            **preconditions(version, key),
            "Content-Type": "application/octet-stream",
            "X-File-Bytes": str(len(content)),
            "X-File-SHA256": hashlib.sha256(content).hexdigest(),
            **extra,
        },
    )


def test_binary_upload_real_parent_receipt_and_private_metadata(
    admin_client, db_engine, seeded_user
):
    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    key = uuid4().hex
    first = upload(admin_client, parent, key=key)
    assert first.status_code == 201, first.text
    receipt = first.json()
    assert receipt["sha256"] == hashlib.sha256(b"private text\n").hexdigest()
    assert receipt["version"] == 1 and first.headers["etag"] == '"1"'
    assert admin_client.get(parent).json()["version"] == 1
    replay = upload(admin_client, parent, key=key)
    assert replay.status_code == 200 and replay.json() == receipt
    detail = admin_client.get("/api/v1/attachments/" + receipt["attachment_id"])
    assert detail.status_code == 200
    assert detail.json()["state"] == "quarantine"
    assert set(detail.json()) == {
        "id",
        "owner_type",
        "owner_id",
        "purpose",
        "filename",
        "media_type",
        "bytes",
        "state",
        "policy_version",
        "version",
        "created_at",
        "can_download",
        "can_retry_scan",
    }
    content = admin_client.get("/api/v1/attachments/" + receipt["attachment_id"] + "/content")
    assert content.status_code == 409
    listed = admin_client.get(parent + "/attachments?purpose=public").json()
    assert len(listed["items"]) == 1 and listed["can_upload"]


def test_upload_validation_current_authority_and_purpose_privacy(
    admin_client, db_engine, seeded_user
):
    from test_team_api import sign_in
    from test_ticket_notes import configure

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    assert upload(admin_client, parent, purpose="note").status_code == 404
    configure(admin_client, refs, seeded_user, "write")
    private = upload(admin_client, parent, purpose="note")
    assert private.status_code == 201, private.text
    private_id = private.json()["attachment_id"]
    for filename, data in [
        ("../x.txt", b"x"),
        ("x\u202etxt.pdf", b"%PDF-1"),
        ("x.exe", b"MZ"),
        ("x.png", b"text"),
        ("x.txt", b"\x00bad"),
        ("x.txt", b"<html>active</html>"),
    ]:
        assert upload(admin_client, parent, filename=filename, content=data).status_code == 422
    for headers, status in [
        ({"Content-Type": "text/plain"}, 415),
        ({"X-File-SHA256": "a" * 64}, 422),
        ({"X-File-Bytes": "10485761"}, 413),
    ]:
        assert upload(admin_client, parent, **headers).status_code == status
    for query in [
        "purpose=public&purpose=note",
        "purpose=public&other=1",
        "purpose=%ff",
        "purpose=%",
        "",
    ]:
        assert admin_client.get(parent + "/attachments?" + query).status_code == 422
    configure(admin_client, refs, seeded_user, "none")
    assert admin_client.get(parent + "/attachments?purpose=note").status_code == 404
    assert admin_client.get(parent + "/attachments?purpose=public").json()["items"] == []
    assert admin_client.get("/api/v1/attachments/" + private_id).status_code == 404
    sign_in(admin_client, "admin@example.test")
    assert admin_client.get("/api/v1/attachments/" + private_id).status_code == 404


def test_upload_body_is_not_consumed_before_session_and_csrf(admin_client, db_engine, seeded_user):
    from starlette.testclient import TestClient

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    consumed = []

    def source():
        consumed.append(True)
        yield b"x"

    with TestClient(
        admin_client.app,
        base_url=str(admin_client.base_url),
        headers={"Origin": admin_client.headers["Origin"]},
    ) as anonymous:
        response = anonymous.post(
            parent + "/attachments?purpose=public&filename=proof.txt",
            content=source(),
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 401 and not consumed
    response = admin_client.post(
        parent + "/attachments?purpose=public&filename=proof.txt",
        content=source(),
        headers={"Content-Type": "application/octet-stream", "X-CSRF-Token": "bad"},
    )
    assert response.status_code == 403 and not consumed


def test_upload_replay_conflict_concurrency_and_atomic_orphans(
    admin_client, db_engine, seeded_user, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from altvia import attachments
    from altvia.file_storage import S3Store
    from sqlalchemy import text

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    key = uuid4().hex
    original = S3Store.put_new
    gate = Barrier(2)
    keys = []

    def concurrent(self, object_key, source, **kwargs):
        keys.append(object_key)
        original(self, object_key, source, **kwargs)
        gate.wait(timeout=10)

    monkeypatch.setattr(S3Store, "put_new", concurrent)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(admin_client, parent, key=key), range(2)))
    assert sorted(x.status_code for x in results) == [200, 201]
    assert results[0].json() == results[1].json() and len(set(keys)) == 2
    monkeypatch.setattr(S3Store, "put_new", original)
    assert upload(admin_client, parent, key=key, content=b"changed\n").status_code == 409
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM attachments")) == 1
        assert (
            db.scalar(text("SELECT count(*) FROM outbox_events WHERE event_type='file.uploaded'"))
            == 1
        )

    def fail(*args, **kwargs):
        from sqlalchemy.exc import SQLAlchemyError

        raise SQLAlchemyError("synthetic event failure")

    monkeypatch.setattr(attachments, "event", fail)
    assert upload(admin_client, parent).status_code == 503
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM attachments")) == 1


def test_work_upload_uses_project_contribution_and_immutable_parent(
    admin_client, db_engine, seeded_user
):
    from test_work_items import create_work, setup_project

    project = setup_project(admin_client, seeded_user)
    work = create_work(admin_client, project).json()["work_item_id"]
    parent = "/api/v1/work-items/" + work
    response = upload(admin_client, parent, purpose="work")
    assert response.status_code == 201, response.text
    assert response.json()["owner_type"] == "work_item"
    assert admin_client.get(parent).json()["version"] == 1
    assert upload(admin_client, parent, purpose="public").status_code == 422


def controlled_ready(client, engine, identifier, tmp_path):
    from threading import Event

    from altvia import attachment_scan as scan
    from altvia.file_storage import S3Store
    from altvia.file_storage_owner import load_storage
    from test_file_scan_transport import daemon

    claim = scan.claim(engine, identifier)
    version = f"ClamAV 1.4.6/28181/{claim.db_now.strftime('%a %b %d %H:%M:%S %Y')}\0".encode()
    storage = S3Store(load_storage(file_path("scanner")))
    try:
        with daemon(tmp_path, [version, b"stream: OK\0", version]) as (scanner, _):
            assert scan.run_claim(engine, claim, storage, scanner, Event())
    finally:
        storage.close()


def test_upload_ack_is_immutable_after_scan_progress_and_cursor_is_scoped(
    admin_client, db_engine, seeded_user, tmp_path
):
    from uuid import UUID

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    key = uuid4().hex
    initial = upload(admin_client, parent, key=key)
    identifier = UUID(initial.json()["attachment_id"])
    controlled_ready(admin_client, db_engine, identifier, tmp_path)
    replay = upload(admin_client, parent, key=key)
    assert replay.status_code == 200 and replay.json() == initial.json()
    assert replay.headers["etag"] == '"1"'
    assert admin_client.get("/api/v1/attachments/" + str(identifier)).json()["version"] == 3
    assert upload(admin_client, parent).status_code == 201
    page = admin_client.get(parent + "/attachments?purpose=public&limit=1").json()
    assert page["can_upload"] and page["next_cursor"]
    assert (
        admin_client.get(
            parent + "/attachments", params={"purpose": "public", "cursor": page["next_cursor"]}
        ).status_code
        == 200
    )
    other = ticket(admin_client, refs)
    assert (
        admin_client.get(
            other + "/attachments", params={"purpose": "public", "cursor": page["next_cursor"]}
        ).status_code
        == 422
    )


def test_upload_and_download_reauthorize_after_actual_s3_without_network_held_locks(
    admin_client, db_engine, seeded_user, tmp_path, monkeypatch
):
    from contextlib import contextmanager
    from uuid import UUID

    from altvia.file_storage import S3Store
    from sqlalchemy import text

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    response = upload(admin_client, parent)
    identifier = UUID(response.json()["attachment_id"])
    controlled_ready(admin_client, db_engine, identifier, tmp_path)
    actual = S3Store.verified_spool

    @contextmanager
    def revoked(self, *args, **kwargs):
        with actual(self, *args, **kwargs) as source:
            with db_engine.begin() as db:
                db.execute(text("SET LOCAL lock_timeout='1s'"))
                db.execute(
                    text("DELETE FROM client_access_grants WHERE user_id=:user"),
                    {"user": seeded_user},
                )
            yield source

    monkeypatch.setattr(S3Store, "verified_spool", revoked)
    download = admin_client.get("/api/v1/attachments/" + str(identifier) + "/content")
    assert download.status_code == 404 and b"private text" not in download.content
    monkeypatch.setattr(S3Store, "verified_spool", actual)
    # Restoring test scope is not production reauthorization; this is an owner fixture.
    with db_engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO client_access_grants(user_id,client_id,created_at) "
                "VALUES (:user,:client,clock_timestamp())"
            ),
            {"user": seeded_user, "client": UUID(refs["client_id"])},
        )
    put = S3Store.put_new

    def invalidate(self, *args, **kwargs):
        put(self, *args, **kwargs)
        from altvia.management import reset_password
        from conftest import TEST_PASSWORD
        from sqlalchemy.orm import Session

        with Session(db_engine) as db, db.begin():
            db.execute(text("SET LOCAL lock_timeout='1s'"))
            reset_password(db, "employee@example.test", TEST_PASSWORD)

    monkeypatch.setattr(S3Store, "put_new", invalidate)
    assert upload(admin_client, parent).status_code == 401
    with db_engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM attachments")) == 1


def test_corrupt_ready_object_releases_zero_bytes_and_fixed_503(
    admin_client, db_engine, seeded_user, tmp_path
):
    from uuid import UUID

    from altvia.file_storage import BUCKET, s3_client
    from altvia.file_storage_owner import load_storage
    from sqlalchemy import text

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    identifier = UUID(upload(admin_client, parent).json()["attachment_id"])
    controlled_ready(admin_client, db_engine, identifier, tmp_path)
    with db_engine.connect() as db:
        key = db.scalar(text("SELECT object_key FROM attachments WHERE id=:id"), {"id": identifier})
    owner = s3_client(load_storage(file_path("owner")))
    try:
        owner.put_object(Bucket=BUCKET, Key=key, Body=b"corrupt bytes")
    finally:
        owner.close()
    response = admin_client.get("/api/v1/attachments/" + str(identifier) + "/content")
    assert response.status_code == 503 and response.json()["code"] == "file_unavailable"
    assert response.headers["retry-after"] == "5"
    assert key not in response.text and "corrupt bytes" not in response.text


def test_payload_specific_duplicate_headers_and_stream_budget(
    admin_client, db_engine, seeded_user, monkeypatch
):
    import asyncio

    import httpx
    from altvia import attachment_api

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    headers = list(
        {
            **preconditions(),
            "Content-Type": "application/octet-stream",
            "X-File-Bytes": "1",
            "X-File-SHA256": hashlib.sha256(b"x").hexdigest(),
        }.items()
    )
    for key in ["X-File-Bytes", "X-File-SHA256", "If-Match", "Idempotency-Key", "Content-Type"]:
        response = admin_client.post(
            parent + "/attachments?purpose=public&filename=x.txt",
            content=b"x",
            headers=headers + [(key, dict(headers)[key])],
        )
        assert response.status_code == 422, response.text
    timeout = asyncio.timeout
    monkeypatch.setattr(attachment_api.asyncio, "timeout", lambda seconds: timeout(0.02))

    async def request():
        async def slow():
            await asyncio.sleep(0.1)
            yield b"x"

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=admin_client.app),
            base_url=str(admin_client.base_url),
            cookies=dict(admin_client.cookies),
            headers=dict(admin_client.headers),
        ) as client:
            response = await client.post(
                parent + "/attachments?purpose=public&filename=x.txt",
                content=slow(),
                headers=dict(headers),
            )
            assert response.status_code == 408, response.text

    asyncio.run(request())


def test_two_actual_transfers_immediately_refuse_third(
    admin_client, db_engine, seeded_user, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    from altvia.file_storage import S3Store

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    original = S3Store.put_new
    occupied, release, lock = Event(), Event(), Lock()
    count = 0

    def hold(self, *args, **kwargs):
        nonlocal count
        original(self, *args, **kwargs)
        with lock:
            count += 1
            if count == 2:
                occupied.set()
        assert release.wait(8)

    monkeypatch.setattr(S3Store, "put_new", hold)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = (
            pool.submit(upload, admin_client, parent),
            pool.submit(upload, admin_client, parent),
        )
        try:
            assert occupied.wait(5)
            refused = upload(admin_client, parent)
            assert refused.status_code == 503 and refused.headers["retry-after"] == "5"
        finally:
            release.set()
        assert first.result(timeout=5).status_code == second.result(timeout=5).status_code == 201


def test_migration_roundtrip_refusal_and_identity_immutability(
    admin_client, db_engine, seeded_user
):
    import pytest
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import DBAPIError

    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000024")
    assert not inspect(db_engine).has_table("attachments")
    command.upgrade(config, "head")
    assert inspect(db_engine).has_table("attachment_scan_attempts")
    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    assert upload(admin_client, parent).status_code == 201
    for statement in [
        "UPDATE attachments SET filename='other.txt',version=version+1",
        "UPDATE attachments SET state='ready',version=version+1",
        "DELETE FROM attachments",
        "UPDATE attachments SET generation=generation+1,version=version+1",
    ]:
        with db_engine.begin() as db, pytest.raises(DBAPIError):
            db.execute(text(statement))
    with pytest.raises(DBAPIError, match="Cannot contract private files/history"):
        command.downgrade(config, "b46087000024")
    assert inspect(db_engine).has_table("attachments")


def test_disconnect_before_first_download_byte_releases_transfer_slot(
    admin_client, db_engine, seeded_user, tmp_path
):
    import asyncio
    from uuid import UUID

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    identifier = UUID(upload(admin_client, parent).json()["attachment_id"])
    controlled_ready(admin_client, db_engine, identifier, tmp_path)
    route = "/api/v1/attachments/" + str(identifier) + "/content"

    async def disconnected():
        request = admin_client.build_request("GET", route)
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": route,
            "raw_path": route.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(key.lower(), value) for key, value in request.headers.raw],
            "client": ("127.0.0.1", 12345),
            "server": ("altvia.test", 443),
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        statuses = []

        async def send(message):
            if message["type"] == "http.response.start":
                statuses.append(message["status"])
                raise RuntimeError("synthetic client disconnected before bytes")

        with pytest.raises(RuntimeError, match="synthetic client disconnected"):
            await admin_client.app(scope, receive, send)
        assert statuses == [200]

    asyncio.run(disconnected())
    asyncio.run(disconnected())
    assert upload(admin_client, parent).status_code == 201


def test_note_upload_action_is_independent_of_public_assignee(admin_client, db_engine, seeded_user):
    from test_team_api import sign_in
    from test_ticket_notes import configure

    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    configure(admin_client, refs, refs["agent_id"], "write", "agent")
    sign_in(admin_client, "agent@example.test")
    assert not admin_client.get(parent).json()["can_update"]
    assert upload(admin_client, parent).status_code == 403
    assert upload(admin_client, parent, purpose="note").status_code == 201
    configure(admin_client, refs, refs["agent_id"], "read", "agent")
    sign_in(admin_client, "agent@example.test")
    assert upload(admin_client, parent, purpose="note").status_code == 403
    assert len(admin_client.get(parent + "/attachments?purpose=note").json()["items"]) == 1


def test_unowned_work_contribution_can_upload_without_item_update(
    admin_client, db_engine, seeded_user
):
    from uuid import UUID

    from altvia import management
    from altvia.models import ProjectMember, RoleBinding
    from conftest import TEST_PASSWORD
    from sqlalchemy.orm import Session
    from test_team_api import sign_in
    from test_work_items import create_work, setup_project

    project = setup_project(admin_client, seeded_user)
    work = create_work(admin_client, project).json()["work_item_id"]
    parent = "/api/v1/work-items/" + work
    with Session(db_engine) as db, db.begin():
        contributor = management.create_user(
            db, "file-agent@example.test", "File contributor", TEST_PASSWORD
        )
        db.add(ProjectMember(project_id=UUID(project), user_id=contributor.id))
        db.add(
            RoleBinding(
                user_id=contributor.id,
                role_name="agent",
                scope_kind="project",
                project_id=UUID(project),
            )
        )
    sign_in(admin_client, "file-agent@example.test")
    assert not admin_client.get(parent).json()["can_update"]
    assert upload(admin_client, parent, purpose="work").status_code == 201


def test_actual_streamed_size_limit_includes_exact_ten_mib(admin_client, db_engine, seeded_user):
    refs = setup(admin_client, db_engine, seeded_user)
    parent = ticket(admin_client, refs)
    content = b"x" * 10485760
    assert upload(admin_client, parent, content=content).status_code == 201
    oversized = admin_client.post(
        parent + "/attachments?purpose=public&filename=large.txt",
        content=iter([content, b"x"]),
        headers={
            **preconditions(),
            "Content-Type": "application/octet-stream",
            "X-File-Bytes": "10485760",
            "X-File-SHA256": hashlib.sha256(content).hexdigest(),
        },
    )
    assert oversized.status_code == 413
