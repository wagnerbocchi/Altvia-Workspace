"""Project-owned milestones: scoped SQL, reviewed versions and minimal receipts."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from altvia import deadlines, identity, project_registry
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
)
from altvia.config import Settings
from altvia.models import Client, Project, ProjectMilestone, Team
from altvia.work_schemas import Title

State = Literal["planned", "done", "cancelled"]
TRANSITIONS = {"planned": {"done", "cancelled"}, "done": {"planned"}, "cancelled": {"planned"}}


class MilestoneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    due: deadlines.Due | None = None


class MilestonePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})
    title: Title | None = None
    due: deadlines.Due | None = None
    state: State | None = None

    @field_validator("title", "state")
    @classmethod
    def non_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("A non-null value is required")
        return value

    @model_validator(mode="after")
    def nonempty(self) -> "MilestonePatch":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class MilestoneOutput(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    state: State
    due: deadlines.Due | None
    due_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    can_manage: bool
    project_writable: bool


class MilestonePage(BaseModel):
    items: list[MilestoneOutput]
    next_cursor: str | None
    project_writable: bool


class MilestoneReceipt(BaseModel):
    project_id: UUID
    milestone_id: UUID


def _output(row: ProjectMilestone, manage: bool, writable: bool) -> MilestoneOutput:
    return MilestoneOutput(
        **{
            key: getattr(row, key)
            for key in MilestoneOutput.model_fields
            if key not in {"due", "can_manage", "project_writable"}
        },
        due=deadlines.due_output(row),
        can_manage=manage,
        project_writable=writable,
    )


def _writable(db: Session, parent: Project) -> bool:
    team = db.get(Team, parent.team_id)
    customer = db.get(Client, parent.client_id) if parent.client_id else None
    return not (
        not parent.active
        or team is None
        or not team.active
        or (parent.client_id is not None and (customer is None or not customer.active))
    )


def _active(db: Session, parent: Project) -> None:
    if not _writable(db, parent):
        raise identity.IdentityError(409, "project_inactive")


def _event(
    db: Session,
    parent: Project,
    row: ProjectMilestone,
    actor_id: UUID,
    correlation: str,
    changes: list[str] | None = None,
) -> None:
    project_registry.advance(parent)
    details = {"milestone_id": str(row.id)}
    if changes is not None:
        details["changed_fields"] = ",".join(changes)
    identity.record_event(
        db,
        actor_id,
        parent.id,
        "project.milestone_created" if changes is None else "project.milestone_updated",
        datetime.now(UTC),
        correlation,
        parent.version,
        aggregate_type="project",
        details=details,
    )


def create_milestone_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/milestones", tags=["Project milestones"]
    )

    @router.get("", response_model=MilestonePage)
    def listing(
        project_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> MilestonePage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            parent, manage = project_registry.scoped_project(db, actor.id, project_id)
            writable = _writable(db, parent)
            _collection_query(request)
            if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
                raise identity.IdentityError(422, "unsupported_query")
            scope = f"project-milestones:{actor.id}:{project_id}"
            last = _cursor(cursor, scope)
            query = (
                select(ProjectMilestone)
                .where(ProjectMilestone.project_id == project_id)
                .order_by(ProjectMilestone.id)
                .limit(limit + 1)
            )
            if last is not None:
                query = query.where(ProjectMilestone.id > last)
            rows = list(db.scalars(query))
            return MilestonePage(
                project_writable=writable,
                items=[_output(row, manage, writable) for row in rows[:limit]],
                next_cursor=_next_cursor(scope, rows[limit - 1].id) if len(rows) > limit else None,
            )

    @router.post(
        "",
        response_model=MilestoneReceipt,
        status_code=201,
        responses={200: {"model": MilestoneReceipt}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create(
        project_id: UUID, body: MilestoneCreate, request: Request, response: Response
    ) -> MilestoneReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            parent, _ = project_registry.scoped_project(db, actor.id, project_id, write=True)
            route = f"/api/v1/projects/{project_id}/milestones"
            key, digest, saved = _operation(db, actor, request, route, body.model_dump(mode="json"))
            if saved is not None:
                response.status_code = 200
                return MilestoneReceipt.model_validate(saved.result)
            _active(db, parent)
            row = ProjectMilestone(project_id=project_id, title=body.title)
            deadlines.set_due(db, row, body.due)
            db.add(row)
            db.flush()
            _event(db, parent, row, actor.id, request.state.correlation_id)
            receipt = MilestoneReceipt(project_id=project_id, milestone_id=row.id)
            _remember(db, actor, route, key, digest, receipt, 201)
            return receipt

    def scoped(
        db: Session, project_id: UUID, milestone_id: UUID, *, write: bool = False
    ) -> ProjectMilestone:
        query = select(ProjectMilestone).where(
            ProjectMilestone.id == milestone_id, ProjectMilestone.project_id == project_id
        )
        if write:
            query = query.with_for_update()
        row = db.scalar(query)
        if row is None:
            raise identity.IdentityError(404, "not_found")
        return row

    @router.get("/{milestone_id}", response_model=MilestoneOutput)
    def get(
        project_id: UUID, milestone_id: UUID, request: Request, response: Response
    ) -> MilestoneOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            parent, manage = project_registry.scoped_project(db, actor.id, project_id)
            row = scoped(db, project_id, milestone_id)
            _etag(response, row.version)
            return _output(row, manage, _writable(db, parent))

    @router.patch(
        "/{milestone_id}", response_model=MilestoneOutput, openapi_extra={"parameters": [IF_MATCH]}
    )
    def patch(
        project_id: UUID,
        milestone_id: UUID,
        body: MilestonePatch,
        request: Request,
        response: Response,
    ) -> MilestoneOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            parent, manage = project_registry.scoped_project(db, actor.id, project_id, write=True)
            row = scoped(db, project_id, milestone_id, write=True)
            if row.version != _expected_version(request):
                raise identity.IdentityError(409, "version_conflict")
            changes = []
            if body.title is not None and body.title != row.title:
                row.title = body.title
                changes.append("title")
            if "due" in body.model_fields_set:
                before = (row.due_at, row.due_precision, row.due_date_local, row.due_timezone)
                deadlines.set_due(db, row, body.due)
                if before != (row.due_at, row.due_precision, row.due_date_local, row.due_timezone):
                    changes.append("due")
            if body.state is not None and body.state != row.state:
                if body.state not in TRANSITIONS[row.state]:
                    raise identity.IdentityError(409, "invalid_milestone_transition")
                row.state = body.state
                changes.append("state")
            if changes:
                _active(db, parent)
                project_registry.advance(row)
                _event(db, parent, row, actor.id, request.state.correlation_id, changes)
            _etag(response, row.version)
            return _output(row, manage, _writable(db, parent))

    return router
