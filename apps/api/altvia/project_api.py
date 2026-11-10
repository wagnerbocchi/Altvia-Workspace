"""Typed project registry and classification routes; linked IDs never bypass ACL."""

from datetime import UTC, datetime
from typing import Annotated, Literal
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
from altvia import project_registry as registry
from altvia.activity_api import ActivityPage, activity_page
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
    authenticate_request,
    require_admin,
)
from altvia.config import Settings
from altvia.models import ActivityEvent, OperationalArea, Project, ProjectMember, RoleBinding, User


def _trim(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


RecordName = Annotated[str, BeforeValidator(_trim), Field(min_length=1, max_length=150)]


class AreaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: RecordName


class AreaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})
    name: RecordName | SkipJsonSchema[None] = None
    active: StrictBool | SkipJsonSchema[None] = None

    @field_validator("name", "active")
    @classmethod
    def non_null(cls, value: str | bool | None) -> str | bool:
        if value is None:
            raise ValueError("A non-null value is required")
        return value

    @model_validator(mode="after")
    def nonempty(self) -> "AreaPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class AreaOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class AreaPage(BaseModel):
    items: list[AreaOutput]
    next_cursor: str | None


class ProjectCreate(AreaCreate):
    scope_kind: Literal["internal", "client"]
    client_id: UUID | None = None
    team_id: UUID
    operational_area_id: UUID | None = None
    manager_user_id: UUID

    @model_validator(mode="after")
    def scope_matches(self) -> "ProjectCreate":
        if (self.scope_kind == "client") != (self.client_id is not None):
            raise ValueError("Client scope requires exactly one client")
        return self


class ProjectCreation(BaseModel):
    project_id: UUID
    manager_user_id: UUID


class ProjectPatch(AreaPatch):
    operational_area_id: UUID | None = None


class ProjectOutput(AreaOutput):
    scope_kind: str
    client_id: UUID | None
    team_id: UUID
    operational_area_id: UUID | None
    operational_area_name: str | None
    can_manage: bool


class ProjectPage(BaseModel):
    items: list[ProjectOutput]
    next_cursor: str | None


class ProjectMemberOutput(BaseModel):
    id: UUID
    display_name: str
    active: bool
    role_name: str


class ProjectMemberPage(BaseModel):
    items: list[ProjectMemberOutput]
    next_cursor: str | None


def _output(project: Project, manage: bool) -> ProjectOutput:
    return ProjectOutput(
        **AreaOutput.model_validate(project).model_dump(),
        scope_kind=project.scope_kind,
        client_id=project.client_id,
        team_id=project.team_id,
        operational_area_id=project.operational_area_id,
        operational_area_name=project.operational_area.name if project.operational_area else None,
        can_manage=manage,
    )


def create_project_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Projects"])

    @router.get("/operational-areas", response_model=AreaPage)
    def areas(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> AreaPage:
        with Session(engine) as db, db.begin():
            authenticate_request(db, request, settings)
            _collection_query(request)
            last = _cursor(cursor, "operational-areas")
            query = select(OperationalArea).order_by(OperationalArea.id).limit(limit + 1)
            if last is not None:
                query = query.where(OperationalArea.id > last)
            rows = list(db.scalars(query))
            return AreaPage(
                items=[AreaOutput.model_validate(row) for row in rows[:limit]],
                next_cursor=_next_cursor("operational-areas", rows[limit - 1].id)
                if len(rows) > limit
                else None,
            )

    @router.post(
        "/operational-areas",
        response_model=AreaOutput,
        status_code=201,
        responses={200: {"model": AreaOutput}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create_area(body: AreaCreate, request: Request, response: Response) -> AreaOutput:
        with Session(engine) as db, db.begin():
            actor = require_admin(db, request, settings, write=True)
            route = "/api/v1/operational-areas"
            key, digest, saved = _operation(db, actor, request, route, body.model_dump(mode="json"))
            if saved is not None:
                response.status_code = 200
                return AreaOutput.model_validate(saved.result)
            registry.unique_area_name(db, body.name)
            row = OperationalArea(name=body.name, active=True, version=1)
            db.add(row)
            db.flush()
            identity.record_event(
                db,
                actor.id,
                row.id,
                "operational_area.created",
                datetime.now(UTC),
                request.state.correlation_id,
                1,
                aggregate_type="operational_area",
            )
            result = AreaOutput.model_validate(row)
            _remember(db, actor, route, key, digest, result, 201)
            _etag(response, row.version)
            return result

    @router.patch(
        "/operational-areas/{area_id}",
        response_model=AreaOutput,
        openapi_extra={"parameters": [IF_MATCH]},
    )
    def patch_area(
        area_id: UUID, body: AreaPatch, request: Request, response: Response
    ) -> AreaOutput:
        with Session(engine) as db, db.begin():
            actor = require_admin(db, request, settings, write=True)
            row = db.scalar(
                select(OperationalArea).where(OperationalArea.id == area_id).with_for_update()
            )
            if row is None:
                raise identity.IdentityError(404, "not_found")
            if row.version != _expected_version(request):
                raise identity.IdentityError(409, "version_conflict")
            changes = []
            if body.name is not None and body.name != row.name:
                registry.unique_area_name(db, body.name, row.id)
                row.name = body.name
                changes.append("name")
            if body.active is not None and body.active != row.active:
                row.active = body.active
                changes.append("active")
            if changes:
                registry.advance(row)
                identity.record_event(
                    db,
                    actor.id,
                    row.id,
                    "operational_area.updated",
                    datetime.now(UTC),
                    request.state.correlation_id,
                    row.version,
                    aggregate_type="operational_area",
                    details={"changed_fields": ",".join(changes)},
                )
            _etag(response, row.version)
            return AreaOutput.model_validate(row)

    @router.get("/projects", response_model=ProjectPage)
    def projects(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
        client_id: UUID | None = None,
    ) -> ProjectPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            if not set(request.query_params).issubset({"limit", "cursor", "client_id"}):
                raise identity.IdentityError(422, "unsupported_query")
            scope = f"projects:{actor.id}:{client_id or 'all'}"
            last = _cursor(cursor, scope)
            query = registry.visible_projects(actor.id).order_by(Project.id).limit(limit + 1)
            if client_id is not None:
                query = query.where(Project.client_id == client_id)
            if last is not None:
                query = query.where(Project.id > last)
            rows = list(db.execute(query))
            return ProjectPage(
                items=[_output(row, manage) for row, manage in rows[:limit]],
                next_cursor=_next_cursor(scope, rows[limit - 1][0].id)
                if len(rows) > limit
                else None,
            )

    @router.post(
        "/projects",
        response_model=ProjectCreation,
        status_code=201,
        responses={200: {"model": ProjectCreation}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create(body: ProjectCreate, request: Request, response: Response) -> ProjectCreation:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            registry.creation_authority(
                db, actor, body.client_id, body.team_id, body.manager_user_id
            )
            route = "/api/v1/projects"
            key, digest, saved = _operation(db, actor, request, route, body.model_dump(mode="json"))
            if saved is not None:
                response.status_code = 200
                return ProjectCreation.model_validate(saved.result)
            row = registry.create_project(
                db,
                actor,
                body.name,
                body.scope_kind,
                body.client_id,
                body.team_id,
                body.operational_area_id,
                body.manager_user_id,
                request.state.correlation_id,
            )
            result = ProjectCreation(project_id=row.id, manager_user_id=body.manager_user_id)
            _remember(db, actor, route, key, digest, result, 201)
            return result

    @router.get("/projects/{project_id}", response_model=ProjectOutput)
    def get(project_id: UUID, request: Request, response: Response) -> ProjectOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            row, manage = registry.scoped_project(db, actor.id, project_id)
            _etag(response, row.version)
            return _output(row, manage)

    @router.patch(
        "/projects/{project_id}",
        response_model=ProjectOutput,
        openapi_extra={"parameters": [IF_MATCH]},
    )
    def patch(
        project_id: UUID, body: ProjectPatch, request: Request, response: Response
    ) -> ProjectOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            row, manage = registry.scoped_project(db, actor.id, project_id, write=True)
            if row.version != _expected_version(request):
                raise identity.IdentityError(409, "version_conflict")
            changes = []
            if body.name is not None and body.name != row.name:
                row.name = body.name
                changes.append("name")
            if body.active is not None and body.active != row.active:
                row.active = body.active
                changes.append("active")
            if (
                "operational_area_id" in body.model_fields_set
                and body.operational_area_id != row.operational_area_id
            ):
                row.operational_area = (
                    registry.active_area(db, body.operational_area_id)
                    if body.operational_area_id is not None
                    else None
                )
                changes.append("operational_area_id")
            if changes:
                registry.advance(row)
                identity.record_event(
                    db,
                    actor.id,
                    row.id,
                    "project.updated",
                    datetime.now(UTC),
                    request.state.correlation_id,
                    row.version,
                    aggregate_type="project",
                    details={"changed_fields": ",".join(changes)},
                )
            db.flush()
            _etag(response, row.version)
            return _output(row, manage)

    @router.get("/projects/{project_id}/members", response_model=ProjectMemberPage)
    def members(
        project_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> ProjectMemberPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_project(db, actor.id, project_id)
            _collection_query(request)
            scope = f"project-members:{project_id}"
            last = _cursor(cursor, scope)
            query = (
                select(User, RoleBinding.role_name)
                .join(ProjectMember, ProjectMember.user_id == User.id)
                .join(
                    RoleBinding,
                    (RoleBinding.user_id == User.id)
                    & (RoleBinding.project_id == ProjectMember.project_id),
                )
                .where(
                    ProjectMember.project_id == project_id,
                    RoleBinding.scope_kind == "project",
                    RoleBinding.role_name.in_(registry.PROJECT_ROLES),
                )
                .order_by(User.id)
                .limit(limit + 1)
            )
            if last is not None:
                query = query.where(User.id > last)
            rows = list(db.execute(query))
            return ProjectMemberPage(
                items=[
                    ProjectMemberOutput(
                        id=user.id,
                        display_name=user.display_name,
                        active=user.active,
                        role_name=role,
                    )
                    for user, role in rows[:limit]
                ],
                next_cursor=_next_cursor(scope, rows[limit - 1][0].id)
                if len(rows) > limit
                else None,
            )

    @router.get("/projects/{project_id}/activity", response_model=ActivityPage)
    def history(
        project_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> ActivityPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            registry.scoped_project(db, actor.id, project_id)
            _collection_query(request)
            return activity_page(
                db,
                select(ActivityEvent).where(
                    ActivityEvent.resource_type == "project",
                    ActivityEvent.resource_id == project_id,
                ),
                f"project-activity:{project_id}",
                limit,
                cursor,
            )

    return router
