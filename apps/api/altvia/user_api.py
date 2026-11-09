"""Account security administration; domain invariants remain in management."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, field_validator
from sqlalchemy import Engine, and_, select
from sqlalchemy.orm import Session

from altvia import identity, management
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    _collection_query,
    _cursor,
    _etag,
    _expected_version,
    _next_cursor,
    _operation,
    _remember,
    require_admin,
)
from altvia.config import Settings
from altvia.models import RoleBinding, Team, User


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr = Field(repr=False)

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if len(password) < 14 or len(password.encode()) > 1024:
            raise ValueError("Password length is invalid")
        return value


class UserCreate(PasswordInput):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=150)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return identity.normalize_email(value)

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ActivationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: StrictBool


class PlatformAdminInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


class TeamRoleInput(PlatformAdminInput):
    team_id: UUID
    role_name: Literal["viewer", "operations_manager"]


class UserAdminOutput(BaseModel):
    id: UUID
    display_name: str
    email: str
    active: bool
    platform_admin: bool
    version: int
    created_at: datetime


class TeamRoleOutput(BaseModel):
    id: UUID
    team_id: UUID
    team_name: str
    team_active: bool
    role_name: Literal["viewer", "operations_manager"]


class TeamRolePage(BaseModel):
    items: list[TeamRoleOutput]
    next_cursor: str | None


def _account(db: Session, user_id: UUID, expected: int | None = None) -> User:
    query = select(User).where(User.id == user_id)
    if expected is not None:
        query = query.with_for_update(key_share=True)
    user = db.scalar(query)
    if user is None:
        raise identity.IdentityError(404, "account_not_found")
    if expected is not None and user.auth_version != expected:
        raise identity.IdentityError(409, "version_conflict")
    return user


def _output(db: Session, user: User) -> UserAdminOutput:
    # One SQL snapshot for fields and role, even on reads concurrent with writes.
    admin = (
        select(RoleBinding.id)
        .where(
            RoleBinding.user_id == User.id,
            RoleBinding.scope_kind == "global",
            RoleBinding.role_name == "platform_admin",
        )
        .exists()
    )
    row, is_admin = db.execute(
        select(User, admin).where(User.id == user.id).execution_options(populate_existing=True)
    ).one()
    return UserAdminOutput(
        id=row.id,
        display_name=row.display_name,
        email=row.email_normalized,
        active=row.active,
        platform_admin=is_admin,
        version=row.auth_version,
        created_at=row.created_at,
    )


def create_user_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/users", tags=["Identity administration"])

    @router.post(
        "",
        response_model=UserAdminOutput,
        status_code=201,
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create_account(body: UserCreate, request: Request, response: Response) -> UserAdminOutput:
        with Session(engine) as db, db.begin():
            actor = require_admin(db, request, settings, write=True)
            route = "/api/v1/users"
            payload: dict[str, object] = {
                "email": body.email,
                "display_name": body.display_name,
                "password": body.password.get_secret_value(),
            }
            key, fingerprint, saved = _operation(
                db, actor, request, route, payload, credential=True
            )
            if saved is not None:
                result = UserAdminOutput.model_validate(saved.result)
            else:
                user = management.create_user(
                    db,
                    body.email,
                    body.display_name,
                    body.password.get_secret_value(),
                    actor_id=actor.id,
                    correlation_id=request.state.correlation_id,
                )
                result = _output(db, user)
                _remember(db, actor, route, key, fingerprint, result, 201)
            _etag(response, result.version)
            return result

    @router.get("/{user_id}", response_model=UserAdminOutput)
    def get_account(user_id: UUID, request: Request, response: Response) -> UserAdminOutput:
        with Session(engine) as db, db.begin():
            require_admin(db, request, settings)
            result = _output(db, _account(db, user_id))
            _etag(response, result.version)
            return result

    @router.get("/{user_id}/team-roles", response_model=TeamRolePage)
    def get_roles(
        user_id: UUID,
        request: Request,
        response: Response,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> TeamRolePage:
        with Session(engine) as db, db.begin():
            require_admin(db, request, settings)
            _collection_query(request)
            scope = f"user-roles:{user_id}"
            last = _cursor(cursor, scope)
            conditions = [RoleBinding.user_id == User.id, RoleBinding.scope_kind == "team"]
            if last is not None:
                conditions.append(RoleBinding.id > last)
            # Outer join preserves an account/version row for an empty page.
            # The version and role metadata come from one statement snapshot.
            rows = db.execute(
                select(User.auth_version, RoleBinding, Team)
                .select_from(User)
                .outerjoin(RoleBinding, and_(*conditions))
                .outerjoin(Team, Team.id == RoleBinding.team_id)
                .where(User.id == user_id)
                .order_by(RoleBinding.id)
                .limit(limit + 1)
            ).all()
            if not rows:
                raise identity.IdentityError(404, "account_not_found")
            _etag(response, rows[0][0])
            items = [
                TeamRoleOutput(
                    id=binding.id,
                    team_id=team.id,
                    team_name=team.name,
                    team_active=team.active,
                    role_name=binding.role_name,
                )
                for _, binding, team in rows[:limit]
                if binding is not None and team is not None
            ]
            return TeamRolePage(
                items=items,
                next_cursor=_next_cursor(scope, items[-1].id) if len(rows) > limit else None,
            )

    def change(
        user_id: UUID,
        suffix: str,
        body: PasswordInput | ActivationInput | PlatformAdminInput | TeamRoleInput,
        request: Request,
        response: Response,
    ) -> UserAdminOutput:
        with Session(engine) as db, db.begin():
            actor = require_admin(db, request, settings, write=True)
            expected = _expected_version(request)
            payload = body.model_dump(mode="json")
            if isinstance(body, PasswordInput):
                payload["password"] = body.password.get_secret_value()
            payload["version"] = expected
            route = f"/api/v1/users/{user_id}/{suffix}"
            key, fingerprint, saved = _operation(
                db,
                actor,
                request,
                route,
                payload,
                credential=isinstance(body, PasswordInput),
            )
            if saved is not None:
                result = UserAdminOutput.model_validate(saved.result)
            else:
                user = _account(db, user_id, expected)
                attribution = {"actor_id": actor.id, "correlation_id": request.state.correlation_id}
                if isinstance(body, PasswordInput):
                    management.reset_password(
                        db, user.email_normalized, body.password.get_secret_value(), **attribution
                    )
                elif isinstance(body, ActivationInput):
                    management.set_account_active(
                        db, user.email_normalized, body.active, **attribution
                    )
                elif isinstance(body, TeamRoleInput):
                    management.set_team_role(
                        db,
                        user.email_normalized,
                        body.team_id,
                        body.role_name,
                        body.enabled,
                        **attribution,
                    )
                else:
                    management.set_platform_admin(
                        db, user.email_normalized, body.enabled, **attribution
                    )
                db.flush()
                result = _output(db, user)
                _remember(db, actor, route, key, fingerprint, result, 200)
                if user.id == actor.id and result.version != expected:
                    response.headers["X-Session-Revoked"] = "true"
                    response.delete_cookie(
                        identity.COOKIE_NAME, secure=True, httponly=True, samesite="lax", path="/"
                    )
            _etag(response, result.version)
            return result

    write_contract = {"parameters": [IF_MATCH, IDEMPOTENCY_KEY]}

    @router.post(
        "/{user_id}/activation", response_model=UserAdminOutput, openapi_extra=write_contract
    )
    def activation(
        user_id: UUID, body: ActivationInput, request: Request, response: Response
    ) -> UserAdminOutput:
        return change(user_id, "activation", body, request, response)

    @router.post(
        "/{user_id}/password", response_model=UserAdminOutput, openapi_extra=write_contract
    )
    def password(
        user_id: UUID, body: PasswordInput, request: Request, response: Response
    ) -> UserAdminOutput:
        return change(user_id, "password", body, request, response)

    @router.post(
        "/{user_id}/platform-admin", response_model=UserAdminOutput, openapi_extra=write_contract
    )
    def platform_admin(
        user_id: UUID, body: PlatformAdminInput, request: Request, response: Response
    ) -> UserAdminOutput:
        return change(user_id, "platform-admin", body, request, response)

    @router.post(
        "/{user_id}/team-roles", response_model=UserAdminOutput, openapi_extra=write_contract
    )
    def team_role(
        user_id: UUID, body: TeamRoleInput, request: Request, response: Response
    ) -> UserAdminOutput:
        return change(user_id, "team-roles", body, request, response)

    return router
