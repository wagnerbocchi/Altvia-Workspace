import hmac
import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from altvia import identity
from altvia.models import SessionRecord


def require_origin(request: Request, public_origin: str) -> None:
    if request.headers.get("origin") != public_origin:
        raise identity.IdentityError(403, "origin_rejected")


def require_csrf(request: Request, session: SessionRecord) -> None:
    provided = request.headers.get("x-csrf-token", "")
    if not hmac.compare_digest(identity.digest(provided), session.csrf_hash):
        raise identity.IdentityError(403, "csrf_rejected")


def problem(status: int, code: str, correlation_id: str, **extra: object) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    retry_after = extra.pop("retry_after", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        {
            "type": f"urn:altvia:problem:{code}",
            "title": code.replace("_", " "),
            "status": status,
            "code": code,
            "correlation_id": correlation_id,
            **extra,
        },
        status_code=status,
        media_type="application/problem+json",
        headers=headers,
    )


class RequestBoundary:
    """Bound current small JSON writes before parsing and redact error correlation."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        supplied = headers.get(b"x-correlation-id", b"").decode("ascii", errors="ignore")
        correlation = supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied) else uuid4().hex
        scope.setdefault("state", {})["correlation_id"] = correlation
        started = perf_counter()

        async def send_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                route = getattr(scope.get("route"), "path", "unmatched")
                logging.getLogger("altvia.requests").info(
                    "",
                    extra={
                        "event_code": "http_request",
                        "correlation_id": correlation,
                        "route": route,
                        "method": scope["method"],
                        "status": message["status"],
                        "duration_ms": round((perf_counter() - started) * 1000, 3),
                    },
                )
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-correlation-id", correlation.encode()),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        small_json = (scope["path"] == "/api/v1/auth/sessions" and scope["method"] == "POST") or (
            (
                scope["path"] in {"/api/v1/teams", "/api/v1/users"}
                or scope["path"].startswith(("/api/v1/teams/", "/api/v1/users/"))
            )
            and scope["method"] in {"POST", "PATCH"}
        )
        if small_json:
            body = bytearray()
            while True:
                chunk = await receive()
                if chunk["type"] == "http.disconnect":
                    return
                data = chunk.get("body", b"")
                if len(body) + len(data) > 16384:
                    await problem(413, "body_too_large", correlation)(scope, receive, send_headers)
                    return
                body.extend(data)
                if not chunk.get("more_body", False):
                    break
            if (
                headers.get(b"content-type", b"").split(b";")[0].strip().lower()
                != b"application/json"
            ):
                await problem(415, "unsupported_media_type", correlation)(
                    scope, receive, send_headers
                )
                return

            async def replay() -> Message:
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay, send_headers)
        else:
            await self.app(scope, receive, send_headers)
