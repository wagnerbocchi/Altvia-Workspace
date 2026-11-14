"""Shared identity-administration HTTP protocols, under the identity write lock."""

import base64
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2.low_level import Type, hash_secret_raw
from fastapi import Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from altvia import identity
from altvia.config import Settings
from altvia.http import require_csrf, require_origin
from altvia.management import lock_identity_writes
from altvia.models import IdempotencyRecord, User


def authenticate_request(
    db: Session, request: Request, settings: Settings, *, write: bool = False
) -> User:
    if write:
        require_origin(request, settings.public_origin)
        lock_identity_writes(db)
    user, session = identity.authenticate(db, request.cookies.get(identity.COOKIE_NAME))
    if write:
        require_csrf(request, session)
    return user


def require_admin(
    db: Session, request: Request, settings: Settings, *, write: bool = False
) -> User:
    user = authenticate_request(db, request, settings, write=write)
    if "identity.manage" not in identity.capabilities(db, user):
        raise identity.IdentityError(403, "forbidden")
    return user


IF_MATCH = {
    "name": "If-Match",
    "in": "header",
    "required": True,
    "schema": {"type": "string", "pattern": '^"[1-9][0-9]{0,9}"$'},
}
IDEMPOTENCY_KEY = {
    "name": "Idempotency-Key",
    "in": "header",
    "required": True,
    "schema": {"type": "string", "pattern": "^[A-Za-z0-9._:-]{1,128}$"},
}
IF_MATCH_QUEUE = {**IF_MATCH, "name": "If-Match-Queue", "description": "Reviewed queue version"}


def configuration_query(request: Request, *, listing: bool = False) -> None:
    allowed = {"client_id", "limit", "cursor"} if listing else set()
    if not set(request.query_params) <= allowed:
        raise identity.IdentityError(422, "unsupported_query")
    if any(len(request.query_params.getlist(name)) != 1 for name in request.query_params):
        raise identity.IdentityError(422, "repeated_query")


def queue_configuration_versions(
    request: Request, *, patch: bool = False
) -> tuple[int, int | None]:
    for header in ("if-match", "if-match-queue", "idempotency-key"):
        if len(request.headers.getlist(header)) > 1:
            raise identity.IdentityError(422, "invalid_precondition")
    reviewed = _expected_version(request)
    queue = (
        _expected_version(
            request,
            header="if-match-queue",
            required_code="queue_version_required",
            invalid_code="invalid_queue_version",
        )
        if patch
        else None
    )
    return reviewed, queue


def _cursor(value: str | None, scope: str) -> UUID | None:
    if value is None:
        return None
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        version, bound_scope, last_id = decoded.decode("ascii").split("|")
        if version != "v1" or bound_scope != scope:
            raise ValueError("Cursor does not match this collection")
        return UUID(last_id)
    except (ValueError, UnicodeError):
        raise identity.IdentityError(422, "invalid_cursor") from None


def _collection_query(request: Request) -> None:
    if not set(request.query_params).issubset({"limit", "cursor"}):
        raise identity.IdentityError(422, "unsupported_query")


def _next_cursor(scope: str, last_id: UUID) -> str:
    return base64.urlsafe_b64encode(f"v1|{scope}|{last_id}".encode()).decode().rstrip("=")


def _time_cursor(value: str | None, scope: str) -> tuple[datetime, UUID] | None:
    if value is None:
        return None
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        ).decode("ascii")
        bound_scope, instant, identifier = raw.split("|")
        stamp, row_id = datetime.fromisoformat(instant), UUID(identifier)
        if bound_scope != scope or stamp.tzinfo is None:
            raise ValueError("Invalid cursor")
        return stamp, row_id
    except (ValueError, UnicodeError):
        raise identity.IdentityError(422, "invalid_cursor") from None


def _next_time_cursor(scope: str, instant: datetime, row_id: UUID) -> str:
    raw = f"{scope}|{instant.astimezone(UTC).isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _expected_version(
    request: Request,
    *,
    header: str = "if-match",
    required_code: str = "version_required",
    invalid_code: str = "invalid_version",
) -> int:
    value = request.headers.get(header)
    if value is None:
        raise identity.IdentityError(428, required_code)
    if not re.fullmatch(r'"[1-9][0-9]{0,9}"', value):
        raise identity.IdentityError(422, invalid_code)
    version = int(value[1:-1])
    if version > 2147483647:
        raise identity.IdentityError(422, invalid_code)
    return version


def _operation(
    db: Session,
    actor: User,
    request: Request,
    route: str,
    body: dict[str, object],
    *,
    credential: bool = False,
) -> tuple[str, str, IdempotencyRecord | None]:
    # The router holds the identity write lock before this lookup, including
    # before authentication. Never reuse this protocol without serialization.
    key = request.headers.get("idempotency-key")
    if key is None:
        raise identity.IdentityError(428, "idempotency_key_required")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise identity.IdentityError(422, "invalid_idempotency_key")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    if credential:
        # A leaked receipt must not become a fast password-guessing oracle.
        salt = hashlib.sha256(
            json.dumps([str(actor.id), route, key], separators=(",", ":")).encode()
        ).digest()[:16]
        request_hash = hash_secret_raw(canonical, salt, 3, 65536, 1, 32, Type.ID).hex()
    else:
        request_hash = hashlib.sha256(canonical).hexdigest()
    saved = db.get(IdempotencyRecord, (actor.id, route, key))
    if saved is not None and not hmac.compare_digest(saved.request_hash, request_hash):
        raise identity.IdentityError(409, "idempotency_conflict")
    return key, request_hash, saved


def _remember(
    db: Session,
    actor: User,
    route: str,
    key: str,
    request_hash: str,
    result: BaseModel,
    status: int,
) -> None:
    now = datetime.now(UTC)
    db.add(
        IdempotencyRecord(
            actor_id=actor.id,
            route=route,
            key=key,
            request_hash=request_hash,
            status_code=status,
            result=result.model_dump(mode="json"),
            created_at=now,
            expires_at=now + timedelta(days=7),
        )
    )
