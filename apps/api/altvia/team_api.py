"""Identity metadata administration; team membership never grants content scope."""

import base64
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from altvia import identity
from altvia.config import Settings
from altvia.http import require_csrf, require_origin
from altvia.management import lock_identity_writes
from altvia.models import IdempotencyRecord, Team, TeamMember, User


def _trim_name(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


TeamName = Annotated[str, BeforeValidator(_trim_name), Field(min_length=1, max_length=150)]


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: TeamName


class TeamPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})
    name: TeamName | SkipJsonSchema[None] = None
    active: StrictBool | SkipJsonSchema[None] = None

    @field_validator("name", "active")
    @classmethod
    def forbid_explicit_null(cls, value: str | bool | None) -> str | bool:
        if value is None:
            raise ValueError("A non-null value is required")
        return value

    @model_validator(mode="after")
    def require_change_field(self) -> "TeamPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class TeamOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    display_name: str
    email: str = Field(validation_alias="email_normalized")
    active: bool


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID


class MemberOutput(BaseModel):
    user_id: UUID
    display_name: str
    account_active: bool


class MemberChange(BaseModel):
    team_id: UUID
    user_id: UUID
    team_version: int


class TeamPage(BaseModel):
    items: list[TeamOutput]
    next_cursor: str | None


class UserPage(BaseModel):
    items: list[UserSummary]
    next_cursor: str | None


class MemberPage(BaseModel):
    items: list[MemberOutput]
    next_cursor: str | None


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


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _expected_version(request: Request) -> int:
    value = request.headers.get("if-match")
    if value is None:
        raise identity.IdentityError(428, "version_required")
    if not re.fullmatch(r'"[1-9][0-9]{0,9}"', value):
        raise identity.IdentityError(422, "invalid_version")
    version = int(value[1:-1])
    if version > 2147483647:
        raise identity.IdentityError(422, "invalid_version")
    return version


def _team(db: Session, team_id: UUID, expected: int | None = None) -> Team:
    query = select(Team).where(Team.id == team_id)
    if expected is not None:
        query = query.with_for_update(key_share=True)
    team = db.scalar(query)
    if team is None:
        raise identity.IdentityError(404, "not_found")
    if expected is not None and team.version != expected:
        raise identity.IdentityError(409, "version_conflict")
    return team


def _operation(
    db: Session,
    actor: User,
    request: Request,
    route: str,
    body: dict[str, object],
) -> tuple[str, str, IdempotencyRecord | None]:
    # The router holds the identity write lock before this lookup, including
    # before authentication. Never reuse this protocol without serialization.
    key = request.headers.get("idempotency-key")
    if key is None:
        raise identity.IdentityError(428, "idempotency_key_required")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise identity.IdentityError(422, "invalid_idempotency_key")
    request_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    saved = db.get(IdempotencyRecord, (actor.id, route, key))
    if saved is not None and saved.request_hash != request_hash:
        raise identity.IdentityError(409, "idempotency_conflict")
    return key, request_hash, saved


def _remember(
    db: Session,
    actor: User,
    route: str,
    key: str,
    request_hash: str,
    result: TeamOutput | MemberChange,
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


def _advance(team: Team) -> None:
    team.version += 1
    team.updated_at = datetime.now(UTC)


def _event(
    db: Session,
    actor: User,
    team: Team,
    action: str,
    request: Request,
    details: dict[str, str] | None = None,
) -> None:
    identity.record_event(
        db,
        actor.id,
        team.id,
        action,
        team.updated_at,
        request.state.correlation_id,
        team.version,
        aggregate_type="team",
        details=details,
    )


def create_team_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Identity administration"])

    def admin(db: Session, request: Request, *, write: bool = False) -> User:
        if write:
            require_origin(request, settings.public_origin)
            lock_identity_writes(db)
        user, session = identity.authenticate(db, request.cookies.get(identity.COOKIE_NAME))
        if write:
            require_csrf(request, session)
        if "identity.manage" not in identity.capabilities(db, user):
            raise identity.IdentityError(403, "forbidden")
        return user

    @router.get("/users", response_model=UserPage)
    def list_users(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> UserPage:
        with Session(engine) as db, db.begin():
            admin(db, request)
            _collection_query(request)
            last = _cursor(cursor, "users")
            query = select(User).order_by(User.id).limit(limit + 1)
            if last is not None:
                query = query.where(User.id > last)
            rows = list(db.scalars(query))
            return UserPage(
                items=[UserSummary.model_validate(row) for row in rows[:limit]],
                next_cursor=_next_cursor("users", rows[limit - 1].id)
                if len(rows) > limit
                else None,
            )

    @router.get("/teams", response_model=TeamPage)
    def list_teams(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> TeamPage:
        with Session(engine) as db, db.begin():
            admin(db, request)
            _collection_query(request)
            last = _cursor(cursor, "teams")
            query = select(Team).order_by(Team.id).limit(limit + 1)
            if last is not None:
                query = query.where(Team.id > last)
            rows = list(db.scalars(query))
            return TeamPage(
                items=[TeamOutput.model_validate(row) for row in rows[:limit]],
                next_cursor=_next_cursor("teams", rows[limit - 1].id)
                if len(rows) > limit
                else None,
            )

    @router.post(
        "/teams",
        response_model=TeamOutput,
        status_code=201,
        responses={200: {"model": TeamOutput}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create_team(body: TeamCreate, request: Request, response: Response) -> TeamOutput:
        with Session(engine) as db, db.begin():
            actor = admin(db, request, write=True)
            route = "/api/v1/teams"
            key, request_hash, saved = _operation(db, actor, request, route, {"name": body.name})
            if saved is not None:
                result = TeamOutput.model_validate(saved.result)
                response.status_code = 200
            else:
                now = datetime.now(UTC)
                team = Team(name=body.name, active=True, version=1, created_at=now, updated_at=now)
                db.add(team)
                db.flush()
                _event(db, actor, team, "identity.team_created", request)
                result = TeamOutput.model_validate(team)
                _remember(db, actor, route, key, request_hash, result, 201)
            _etag(response, result.version)
            return result

    @router.get("/teams/{team_id}", response_model=TeamOutput)
    def get_team(team_id: UUID, request: Request, response: Response) -> TeamOutput:
        with Session(engine) as db, db.begin():
            admin(db, request)
            team = _team(db, team_id)
            _etag(response, team.version)
            return TeamOutput.model_validate(team)

    @router.patch(
        "/teams/{team_id}", response_model=TeamOutput, openapi_extra={"parameters": [IF_MATCH]}
    )
    def patch_team(
        team_id: UUID, body: TeamPatch, request: Request, response: Response
    ) -> TeamOutput:
        with Session(engine) as db, db.begin():
            actor = admin(db, request, write=True)
            team = _team(db, team_id, _expected_version(request))
            changed = []
            if body.name is not None and team.name != body.name:
                team.name = body.name
                changed.append("name")
            if body.active is not None and team.active != body.active:
                team.active = body.active
                changed.append("active")
            if changed:
                _advance(team)
                _event(
                    db,
                    actor,
                    team,
                    "identity.team_updated",
                    request,
                    {"changed_fields": ",".join(changed)},
                )
            _etag(response, team.version)
            return TeamOutput.model_validate(team)

    @router.get("/teams/{team_id}/members", response_model=MemberPage)
    def list_members(
        team_id: UUID,
        request: Request,
        response: Response,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> MemberPage:
        with Session(engine) as db, db.begin():
            admin(db, request)
            _collection_query(request)
            team = _team(db, team_id)
            scope = f"members:{team_id}"
            last = _cursor(cursor, scope)
            query = (
                select(User)
                .join(TeamMember, TeamMember.user_id == User.id)
                .where(
                    TeamMember.team_id == team_id,
                    TeamMember.active.is_(True),
                )
                .order_by(User.id)
                .limit(limit + 1)
            )
            if last is not None:
                query = query.where(User.id > last)
            rows = list(db.scalars(query))
            _etag(response, team.version)
            return MemberPage(
                items=[
                    MemberOutput(
                        user_id=row.id, display_name=row.display_name, account_active=row.active
                    )
                    for row in rows[:limit]
                ],
                next_cursor=_next_cursor(scope, rows[limit - 1].id) if len(rows) > limit else None,
            )

    @router.post(
        "/teams/{team_id}/members",
        response_model=MemberChange,
        status_code=201,
        responses={200: {"model": MemberChange}},
        openapi_extra={"parameters": [IF_MATCH, IDEMPOTENCY_KEY]},
    )
    def add_member(
        team_id: UUID, body: MemberCreate, request: Request, response: Response
    ) -> MemberChange:
        with Session(engine) as db, db.begin():
            actor = admin(db, request, write=True)
            expected = _expected_version(request)
            route = f"/api/v1/teams/{team_id}/members"
            key, request_hash, saved = _operation(
                db,
                actor,
                request,
                route,
                {
                    "user_id": str(body.user_id),
                    "version": expected,
                },
            )
            if saved is not None:
                result = MemberChange.model_validate(saved.result)
                response.status_code = 200
            else:
                team = _team(db, team_id, expected)
                if not team.active:
                    raise identity.IdentityError(409, "team_inactive")
                user = db.scalar(
                    select(User).where(User.id == body.user_id).with_for_update(key_share=True)
                )
                if user is None:
                    raise identity.IdentityError(404, "account_not_found")
                if not user.active:
                    raise identity.IdentityError(409, "account_inactive")
                member = db.get(TeamMember, (team_id, body.user_id))
                changed = member is None or not member.active
                if changed:
                    now = datetime.now(UTC)
                    if member is None:
                        db.add(
                            TeamMember(
                                team_id=team_id,
                                user_id=body.user_id,
                                active=True,
                                created_at=now,
                                updated_at=now,
                            )
                        )
                    else:
                        member.active, member.updated_at = True, now
                    _advance(team)
                    _event(
                        db,
                        actor,
                        team,
                        "identity.team_member_added",
                        request,
                        {"member_user_id": str(body.user_id)},
                    )
                result = MemberChange(
                    team_id=team_id, user_id=body.user_id, team_version=team.version
                )
                response.status_code = 201 if changed else 200
                _remember(db, actor, route, key, request_hash, result, response.status_code)
            _etag(response, result.team_version)
            return result

    @router.delete(
        "/teams/{team_id}/members/{user_id}",
        status_code=204,
        openapi_extra={"parameters": [IF_MATCH]},
    )
    def remove_member(team_id: UUID, user_id: UUID, request: Request, response: Response) -> None:
        with Session(engine) as db, db.begin():
            actor = admin(db, request, write=True)
            team = _team(db, team_id, _expected_version(request))
            member = db.get(TeamMember, (team_id, user_id))
            if member is not None and member.active:
                member.active, member.updated_at = False, datetime.now(UTC)
                _advance(team)
                _event(
                    db,
                    actor,
                    team,
                    "identity.team_member_removed",
                    request,
                    {"member_user_id": str(user_id)},
                )
            _etag(response, team.version)

    return router
