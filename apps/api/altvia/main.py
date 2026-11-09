import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from altvia import identity
from altvia.config import Settings
from altvia.database import make_engine
from altvia.http import RequestBoundary, problem


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return identity.normalize_email(value)


class UserOutput(BaseModel):
    id: UUID
    display_name: str
    email: str
    capabilities: list[str]
    csrf_token: str


class LoginOutput(BaseModel):
    user: UserOutput
    expires_at: datetime
    csrf_token: str


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    engine = make_engine(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="Altvia Workspace API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestBoundary)

    @app.exception_handler(identity.IdentityError)
    async def identity_error(request: Request, exc: identity.IdentityError) -> JSONResponse:
        return problem(
            exc.status, exc.code, request.state.correlation_id, retry_after=exc.retry_after
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"field": list(e["loc"]), "code": e["type"]} for e in exc.errors()]
        malformed = any(e["type"] == "json_invalid" for e in exc.errors())
        return problem(
            400 if malformed else 422,
            "validation_error",
            request.state.correlation_id,
            errors=errors,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return problem(503, "database_unavailable", request.state.correlation_id, retry_after=5)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return problem(
            exc.status_code,
            "not_found" if exc.status_code == 404 else "http_error",
            request.state.correlation_id,
        )

    def require_origin(request: Request) -> None:
        if request.headers.get("origin") != config.public_origin:
            raise identity.IdentityError(403, "origin_rejected")

    @app.get("/api/v1/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/ready")
    def ready() -> dict[str, str]:
        with engine.connect() as connection:
            connection.execute(text("SELECT id FROM users LIMIT 0"))
        return {"status": "ready"}

    @app.post("/api/v1/auth/sessions", response_model=LoginOutput, status_code=201)
    def login(body: LoginInput, request: Request, response: Response) -> LoginOutput:
        require_origin(request)
        with Session(engine, expire_on_commit=False) as db:
            user, session, token = identity.login(
                db,
                body.email,
                body.password,
                request.client.host if request.client else "unknown",
                request.state.correlation_id,
            )
            response.set_cookie(
                identity.COOKIE_NAME,
                token,
                max_age=43200,
                secure=True,
                httponly=True,
                samesite="lax",
                path="/",
            )
            csrf = identity.csrf_token(token)
            return LoginOutput(
                user=UserOutput(
                    id=user.id,
                    display_name=user.display_name,
                    email=user.email_normalized,
                    capabilities=identity.capabilities(db, user),
                    csrf_token=csrf,
                ),
                expires_at=session.expires_at,
                csrf_token=csrf,
            )

    @app.get("/api/v1/auth/me", response_model=UserOutput)
    def me(request: Request) -> UserOutput:
        token = request.cookies.get(identity.COOKIE_NAME)
        with Session(engine) as db, db.begin():
            user, _ = identity.authenticate(db, token)
            return UserOutput(
                id=user.id,
                display_name=user.display_name,
                email=user.email_normalized,
                capabilities=identity.capabilities(db, user),
                csrf_token=identity.csrf_token(token or ""),
            )

    @app.delete("/api/v1/auth/sessions/current", status_code=204)
    def logout(request: Request, response: Response) -> None:
        require_origin(request)
        try:
            with Session(engine) as db, db.begin():
                user, session = identity.authenticate(db, request.cookies.get(identity.COOKIE_NAME))
                provided = request.headers.get("x-csrf-token", "")
                if not hmac.compare_digest(identity.digest(provided), session.csrf_hash):
                    raise identity.IdentityError(403, "csrf_rejected")
                session.revoked_at = datetime.now(UTC)
                identity.record_event(
                    db,
                    user.id,
                    session.id,
                    "identity.session_revoked",
                    session.revoked_at,
                    request.state.correlation_id,
                    user.auth_version,
                )
        except identity.IdentityError as exc:
            if exc.status != 401:
                raise
            # An absent/expired/revoked session already satisfies logout.
        response.delete_cookie(
            identity.COOKIE_NAME, secure=True, httponly=True, samesite="lax", path="/"
        )

    return app
