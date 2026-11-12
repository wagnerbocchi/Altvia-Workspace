"""Bounded binary private uploads, scoped metadata and verified downloads."""

import asyncio
import hashlib
import re
import secrets
import tempfile
from collections.abc import Callable, Iterator
from threading import BoundedSemaphore
from typing import Annotated, BinaryIO, cast
from urllib.parse import parse_qsl, quote
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Engine, select, tuple_
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from altvia import attachments, identity
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    _etag,
    _expected_version,
    _next_time_cursor,
    _operation,
    _remember,
    _time_cursor,
    authenticate_request,
)
from altvia.attachment_schemas import (
    AttachmentFilters,
    AttachmentOutput,
    AttachmentPage,
    OwnerType,
    Purpose,
    RetryReceipt,
    RetryScan,
    UploadReceipt,
)
from altvia.config import Settings
from altvia.file_settings import MAX_FILE_BYTES
from altvia.file_storage import S3Store, StorageError
from altvia.file_storage_owner import load_storage
from altvia.management import lock_identity_writes
from altvia.models import Attachment


class PrivateStream(StreamingResponse):
    """Own the verified spool even if response headers fail before iteration."""

    def __init__(
        self, content: Iterator[bytes], release: Callable[[], None], headers: dict[str, str]
    ):
        super().__init__(content, media_type="application/octet-stream", headers=headers)
        self.release = release

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.release()


def strict_query(
    request: Request, allowed: set[str], required: frozenset[str] | set[str] = frozenset()
) -> dict[str, str]:
    try:
        raw = request.scope["query_string"].decode("ascii")
        if re.search(r"%(?![0-9A-Fa-f]{2})", raw):
            raise ValueError
        pairs = parse_qsl(
            raw, keep_blank_values=True, encoding="utf-8", errors="strict", strict_parsing=True
        )
        values = dict(pairs)
        if len(values) != len(pairs) or not set(values) <= allowed or not required <= set(values):
            raise ValueError
        return values
    except (UnicodeError, ValueError):
        raise identity.IdentityError(422, "invalid_query") from None


def unique_headers(request: Request) -> None:
    for key in {
        "if-match",
        "idempotency-key",
        "x-file-bytes",
        "x-file-sha256",
        "content-type",
        "content-length",
        "transfer-encoding",
        "content-encoding",
        "origin",
        "x-csrf-token",
    }:
        if len(request.headers.getlist(key)) > 1:
            raise identity.IdentityError(422, "repeated_header")
    if request.headers.get("content-encoding") not in {None, "identity"}:
        raise identity.IdentityError(415, "unsupported_media_type")


def unavailable() -> identity.IdentityError:
    return identity.IdentityError(503, "file_unavailable", retry_after=5)


def create_attachment_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Private files"])
    transfers = BoundedSemaphore(2)

    def store() -> S3Store:
        try:
            if settings.storage_file is None:
                raise ValueError
            return S3Store(load_storage(settings.storage_file))
        except (ValueError, OSError):
            raise unavailable() from None

    def inspect_upload(
        request: Request, owner: OwnerType, identifier: UUID, purpose: Purpose
    ) -> int:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            attachments.parent(db, actor.id, owner, identifier, purpose, write=True)
            expected = _expected_version(request)
            key = request.headers.get("idempotency-key", "")
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
                raise identity.IdentityError(
                    422 if key else 428,
                    "invalid_idempotency_key" if key else "idempotency_key_required",
                )
            return expected

    def upload_effect(
        request: Request,
        response: Response,
        owner: OwnerType,
        identifier: UUID,
        purpose: Purpose,
        filename: str,
        expected: int,
        size: int,
        digest: str,
        media: str,
        source: BinaryIO,
    ) -> UploadReceipt:
        route = f"file-upload:{owner}:{identifier}"
        intent: dict[str, object] = {
            "owner_type": owner,
            "owner_id": str(identifier),
            "purpose": purpose,
            "filename": filename,
            "bytes": size,
            "sha256": digest,
            "media_type": media,
            "parent_version": expected,
        }

        # Matching original intent avoids another PUT, including progressed files.
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            parent = attachments.parent(db, actor.id, owner, identifier, purpose, write=True)
            key, fingerprint, saved = _operation(db, actor, request, route, intent)
            if saved is not None:
                response.status_code = 200
                receipt = UploadReceipt.model_validate(saved.result)
                _etag(response, receipt.version)
                return receipt
            parent.fresh(expected)
        object_key = "objects/" + secrets.token_hex(32)
        storage = store()
        try:
            storage.put_new(object_key, source, size=size, sha256=digest)
        except StorageError:
            raise unavailable() from None
        finally:
            storage.close()
        # An interrupted/stale final commit leaves only an opaque private orphan.
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            parent = attachments.parent(db, actor.id, owner, identifier, purpose, write=True)
            key, fingerprint, saved = _operation(db, actor, request, route, intent)
            if saved is not None:
                response.status_code = 200
                receipt = UploadReceipt.model_validate(saved.result)
            else:
                parent.fresh(expected)
                row = Attachment(
                    ticket_id=identifier if owner == "ticket" else None,
                    work_item_id=identifier if owner == "work_item" else None,
                    purpose=purpose,
                    filename=filename,
                    media_type=media,
                    bytes=size,
                    sha256=digest,
                    object_key=object_key,
                    creator_id=actor.id,
                    parent_version=expected,
                )
                db.add(row)
                db.flush()
                attachments.event(db, row, "file.uploaded", actor.id, request.state.correlation_id)
                receipt = UploadReceipt(
                    owner_type=owner,
                    owner_id=identifier,
                    attachment_id=row.id,
                    bytes=size,
                    sha256=digest,
                )
                _remember(db, actor, route, key, fingerprint, receipt, 201)
            _etag(response, receipt.version)
            return receipt

    async def upload(
        identifier: UUID, request: Request, response: Response, owner: OwnerType
    ) -> UploadReceipt:
        unique_headers(request)
        values = strict_query(request, {"filename", "purpose"}, {"filename", "purpose"})
        filename = values["filename"]
        attachments.validate_filename(filename)
        purpose = cast(Purpose, values["purpose"])
        expected = await run_in_threadpool(inspect_upload, request, owner, identifier, purpose)
        if request.headers.get("content-type", "").lower() != "application/octet-stream":
            raise identity.IdentityError(415, "unsupported_media_type")
        claimed = request.headers.get("x-file-bytes", "")
        digest = request.headers.get("x-file-sha256", "")
        if not re.fullmatch(r"[1-9][0-9]{0,9}", claimed) or not re.fullmatch(
            r"[0-9a-f]{64}", digest
        ):
            raise identity.IdentityError(422, "invalid_file_metadata")
        size = int(claimed)
        if size > MAX_FILE_BYTES:
            raise identity.IdentityError(413, "body_too_large")
        length = request.headers.get("content-length")
        if length is not None and (not re.fullmatch(r"[0-9]{1,10}", length) or int(length) != size):
            raise identity.IdentityError(422, "invalid_file_metadata")
        if not transfers.acquire(blocking=False):
            raise unavailable()
        try:
            with cast(BinaryIO, tempfile.TemporaryFile(mode="w+b")) as spool:
                count, actual = 0, hashlib.sha256()
                try:
                    async with asyncio.timeout(60):
                        async for chunk in request.stream():
                            count += len(chunk)
                            if count > MAX_FILE_BYTES:
                                raise identity.IdentityError(413, "body_too_large")
                            if count > size:
                                raise identity.IdentityError(422, "file_mismatch")
                            actual.update(chunk)
                            spool.write(chunk)
                except TimeoutError:
                    raise identity.IdentityError(408, "body_timeout") from None
                if count != size or actual.hexdigest() != digest:
                    raise identity.IdentityError(422, "file_mismatch")
                media = attachments.media_type(spool, filename)
                return await run_in_threadpool(
                    upload_effect,
                    request,
                    response,
                    owner,
                    identifier,
                    purpose,
                    filename,
                    expected,
                    size,
                    digest,
                    media,
                    spool,
                )
        finally:
            transfers.release()

    binary = {
        "parameters": [
            IF_MATCH,
            IDEMPOTENCY_KEY,
            {
                "name": "X-File-Bytes",
                "in": "header",
                "required": True,
                "schema": {"type": "integer", "minimum": 1, "maximum": MAX_FILE_BYTES},
            },
            {
                "name": "X-File-SHA256",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            {"name": "filename", "in": "query", "required": True, "schema": {"type": "string"}},
            {
                "name": "purpose",
                "in": "query",
                "required": True,
                "schema": {"type": "string", "enum": ["public", "note", "work"]},
            },
        ],
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        },
    }

    @router.post(
        "/tickets/{identifier}/attachments",
        response_model=UploadReceipt,
        status_code=201,
        responses={200: {"model": UploadReceipt}},
        openapi_extra=binary,
    )
    async def ticket_upload(
        identifier: UUID, request: Request, response: Response
    ) -> UploadReceipt:
        return await upload(identifier, request, response, "ticket")

    @router.post(
        "/work-items/{identifier}/attachments",
        response_model=UploadReceipt,
        status_code=201,
        responses={200: {"model": UploadReceipt}},
        openapi_extra=binary,
    )
    async def work_upload(identifier: UUID, request: Request, response: Response) -> UploadReceipt:
        return await upload(identifier, request, response, "work_item")

    def listing(
        owner: OwnerType, identifier: UUID, request: Request, filters: AttachmentFilters
    ) -> AttachmentPage:
        strict_query(request, {"purpose", "limit", "cursor"}, {"purpose"})
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            parent = attachments.parent(db, actor.id, owner, identifier, filters.purpose)
            scope = f"files:{actor.id}:{owner}:{identifier}:{filters.purpose}"
            last = _time_cursor(filters.cursor, scope)
            column = Attachment.ticket_id if owner == "ticket" else Attachment.work_item_id
            query = (
                select(Attachment)
                .where(column == identifier, Attachment.purpose == filters.purpose)
                .order_by(Attachment.created_at, Attachment.id)
                .limit(filters.limit + 1)
            )
            if last:
                query = query.where(tuple_(Attachment.created_at, Attachment.id) > last)
            rows = list(db.scalars(query))
            return AttachmentPage(
                items=[attachments.output(row, parent) for row in rows[: filters.limit]],
                next_cursor=_next_time_cursor(
                    scope, rows[filters.limit - 1].created_at, rows[filters.limit - 1].id
                )
                if len(rows) > filters.limit
                else None,
                can_upload=parent.can_write and parent.active,
            )

    @router.get("/tickets/{identifier}/attachments", response_model=AttachmentPage)
    def ticket_list(
        identifier: UUID, request: Request, filters: Annotated[AttachmentFilters, Query()]
    ) -> AttachmentPage:
        return listing("ticket", identifier, request, filters)

    @router.get("/work-items/{identifier}/attachments", response_model=AttachmentPage)
    def work_list(
        identifier: UUID, request: Request, filters: Annotated[AttachmentFilters, Query()]
    ) -> AttachmentPage:
        return listing("work_item", identifier, request, filters)

    @router.get("/attachments/{identifier}", response_model=AttachmentOutput)
    def detail(identifier: UUID, request: Request, response: Response) -> AttachmentOutput:
        strict_query(request, set())
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            row, scope = attachments.scoped(db, actor.id, identifier)
            _etag(response, row.version)
            return attachments.output(row, scope)

    @router.post(
        "/attachments/{identifier}/scan-retries",
        response_model=RetryReceipt,
        status_code=201,
        responses={200: {"model": RetryReceipt}},
        openapi_extra={"parameters": [IF_MATCH, IDEMPOTENCY_KEY]},
    )
    def retry(
        identifier: UUID, body: RetryScan, request: Request, response: Response
    ) -> RetryReceipt:
        unique_headers(request)
        strict_query(request, set())
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            row, scope = attachments.scoped(db, actor.id, identifier, write=True)
            version = _expected_version(request)
            route = "file-retry:" + str(identifier)
            key, fingerprint, saved = _operation(db, actor, request, route, {"version": version})
            if saved is not None:
                response.status_code = 200
                result = RetryReceipt.model_validate(saved.result)
            else:
                if not scope.active:
                    raise identity.IdentityError(409, "attachment_parent_inactive")
                if row.version != version:
                    raise identity.IdentityError(409, "version_conflict")
                if row.state != "failed":
                    raise identity.IdentityError(409, "scan_retry_unavailable")
                row.state, row.generation, row.attempts = "quarantine", row.generation + 1, 0
                from sqlalchemy import func

                now = db.scalar(select(func.clock_timestamp()))
                assert now is not None
                row.next_attempt_at = now
                row.version += 1
                db.flush()
                attachments.event(
                    db, row, "file.scan_retried", actor.id, request.state.correlation_id
                )
                result = RetryReceipt(attachment_id=row.id, version=row.version)
                _remember(db, actor, route, key, fingerprint, result, 201)
            _etag(response, result.version)
            return result

    @router.get(
        "/attachments/{identifier}/content",
        response_class=StreamingResponse,
        responses={
            200: {
                "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
                }
            }
        },
    )
    async def content(identifier: UUID, request: Request) -> StreamingResponse:
        strict_query(request, set())

        def authorized() -> tuple[str, int, str, str]:
            with Session(engine) as db, db.begin():
                lock_identity_writes(db)
                actor = authenticate_request(db, request, settings)
                row, _ = attachments.scoped(db, actor.id, identifier)
                if row.state != "ready":
                    raise identity.IdentityError(409, "attachment_not_ready")
                return row.object_key, row.bytes, row.sha256, row.filename

        key, size, digest, filename = await run_in_threadpool(authorized)
        if not transfers.acquire(blocking=False):
            raise unavailable()
        storage = None
        context = None
        try:
            storage = store()
            context = storage.verified_spool(key, size=size, sha256=digest)
            spool = await run_in_threadpool(context.__enter__)
            await run_in_threadpool(authorized)
        except BaseException as error:
            if context is not None:
                context.__exit__(None, None, None)
            if storage is not None:
                storage.close()
            transfers.release()
            if isinstance(error, StorageError):
                raise unavailable() from None
            raise

        def stream() -> Iterator[bytes]:
            while chunk := spool.read(65536):
                yield chunk

        def release() -> None:
            try:
                context.__exit__(None, None, None)
            finally:
                storage.close()
                transfers.release()

        return PrivateStream(
            stream(),
            release,
            headers={
                "Content-Length": str(size),
                "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
