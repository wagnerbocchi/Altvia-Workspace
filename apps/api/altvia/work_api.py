"""Project-scoped work HTTP ownership; existing protected-write protocols are shared."""

import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Engine, select, tuple_
from sqlalchemy.orm import Session, noload

from altvia import attachment_links, identity, project_registry, work_queries
from altvia import work_items as work
from altvia.activity_api import ActivityPage, activity_page
from altvia.admin_http import (
    IDEMPOTENCY_KEY,
    IF_MATCH,
    _cursor,
    _etag,
    _expected_version,
    _next_cursor,
    _next_time_cursor,
    _operation,
    _remember,
    _time_cursor,
    authenticate_request,
)
from altvia.config import Settings
from altvia.models import (
    ActivityEvent,
    User,
    WorkAssignee,
    WorkComment,
    WorkExternalParticipant,
    WorkItem,
    WorkStatusHistory,
)
from altvia.work_schemas import (
    Candidate,
    CandidatePage,
    CommentCreate,
    CommentOutput,
    CommentPage,
    MyWorkFilters,
    MyWorkItem,
    MyWorkPage,
    ProjectWorkFilters,
    StateOutput,
    StatePage,
    Transition,
    WorkCreate,
    WorkOutput,
    WorkPage,
    WorkPatch,
    WorkReceipt,
)


def _query(request: Request, extra: set[str] | None = None) -> None:
    if not set(request.query_params).issubset({"limit", "cursor"} | (extra or set())):
        raise identity.IdentityError(422, "unsupported_query")


def _event(
    db: Session, actor: User, item: WorkItem, request: Request, event: str, **details: str
) -> None:
    identity.record_event(
        db,
        actor.id,
        item.id,
        "work_item." + event,
        datetime.now(UTC),
        request.state.correlation_id,
        item.version,
        aggregate_type="work_item",
        details={"project_id": str(item.project_id), **details},
    )


def _version(item: WorkItem, request: Request) -> None:
    if item.version != _expected_version(request):
        raise identity.IdentityError(409, "version_conflict")


def create_work_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Work items"])

    @router.get("/work-items", response_model=WorkPage)
    def listing(
        request: Request,
        filters: Annotated[ProjectWorkFilters, Query()],
    ) -> WorkPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            permission = work.access(db, actor.id, filters.project_id)
            scope = work_queries.scope(request, filters, actor.id, "work-items")
            last = _cursor(filters.cursor, scope)
            limit = filters.limit
            query = (
                work_queries.filtered(
                    select(WorkItem).where(WorkItem.project_id == filters.project_id), filters
                )
                .order_by(WorkItem.id)
                .limit(limit + 1)
            )
            if last:
                query = query.where(WorkItem.id > last)
            rows = list(db.scalars(query))
            return WorkPage(
                items=[work.output(item, permission, actor.id) for item in rows[:limit]],
                next_cursor=_next_cursor(scope, rows[limit - 1].id) if len(rows) > limit else None,
                can_create=permission.contribute,
                can_manage=permission.manage,
                project_writable=permission.writable,
            )

    @router.get("/my-work", response_model=MyWorkPage)
    def my_work(request: Request, filters: Annotated[MyWorkFilters, Query()]) -> MyWorkPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            scope = work_queries.scope(request, filters, actor.id, "my-work")
            last = _cursor(filters.cursor, scope)
            projects = project_registry.visible_projects(actor.id).subquery()
            query = (
                select(WorkItem, projects.c.name)
                .join(projects, projects.c.id == WorkItem.project_id)
                .where(work_queries.involved(actor.id))
                # Summary needs no account/assignment directory or per-project
                # permission lookups. Detail rechecks all write capabilities.
                .options(
                    noload(WorkItem.owner),
                    noload(WorkItem.assignees),
                    noload(WorkItem.external_participants),
                )
            )
            for field in ("project_id", "client_id", "team_id"):
                value = getattr(filters, field)
                if value is not None:
                    column = projects.c.id if field == "project_id" else projects.c[field]
                    query = query.where(column == value)
            query = (
                work_queries.filtered(query, filters).order_by(WorkItem.id).limit(filters.limit + 1)
            )
            if last:
                query = query.where(WorkItem.id > last)
            rows = list(db.execute(query))
            return MyWorkPage(
                items=[
                    MyWorkItem(
                        **{
                            key: getattr(item, key)
                            for key in (
                                "id",
                                "project_id",
                                "title",
                                "status",
                                "priority",
                                "work_type",
                                "due_at",
                            )
                        },
                        project_name=name,
                        due=work.due_output(item),
                    )
                    for item, name in rows[: filters.limit]
                ],
                next_cursor=_next_cursor(scope, rows[filters.limit - 1][0].id)
                if len(rows) > filters.limit
                else None,
                as_of=datetime.now(UTC),
            )

    @router.post(
        "/work-items",
        response_model=WorkReceipt,
        status_code=201,
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create(body: WorkCreate, request: Request, response: Response) -> WorkReceipt:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            permission = work.access(db, actor.id, body.project_id, write=True)
            if not permission.manage and (
                body.owner_id != actor.id
                or body.assignee_ids
                or body.parent_id
                or body.external_participants
            ):
                raise identity.IdentityError(403, "forbidden")
            route = "work-create:" + str(body.project_id)
            canonical = body.model_dump(mode="json")
            if not body.external_participants:
                # Preserve request hashes from before this optional field existed.
                canonical.pop("external_participants")
            key, fingerprint, saved = _operation(db, actor, request, route, canonical)
            if saved:
                response.status_code = 200
                return WorkReceipt.model_validate(saved.result)
            work.require_active(db, permission)
            contributors = work.validate_assignments(
                db, permission, body.owner_id, body.assignee_ids
            )
            now = datetime.now(UTC)
            item = WorkItem(
                id=uuid4(),
                project_id=body.project_id,
                title=body.title,
                description=body.description,
                priority=body.priority,
                work_type=body.work_type,
                status="in_progress" if body.work_type == "ongoing" else "todo",
                parent_id=body.parent_id,
                owner_id=body.owner_id,
                estimated_minutes=body.estimated_minutes,
                version=1,
                started_at=now if body.work_type == "ongoing" else None,
                created_at=now,
                updated_at=now,
            )
            work.validate_parent(db, item)
            work.set_due(db, item, body.due)
            item.assignees = [
                WorkAssignee(user_id=user, user=contributors[user]) for user in body.assignee_ids
            ]
            item.external_participants = [
                WorkExternalParticipant(unresolved_label=label)
                for label in body.external_participants
            ]
            db.add(item)
            db.flush()
            db.add(
                WorkStatusHistory(
                    work_item_id=item.id,
                    actor_id=actor.id,
                    to_status=item.status,
                    version=1,
                    occurred_at=now,
                )
            )
            _event(db, actor, item, request, "created")
            receipt = WorkReceipt(work_item_id=item.id, project_id=item.project_id)
            _remember(db, actor, route, key, fingerprint, receipt, 201)
            return receipt

    @router.get("/work-items/{identifier}", response_model=WorkOutput)
    def detail(identifier: UUID, request: Request, response: Response) -> WorkOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            item, permission = work.scoped_work(db, actor.id, identifier)
            _etag(response, item.version)
            return work.output(item, permission, actor.id)

    @router.patch(
        "/work-items/{identifier}",
        response_model=WorkOutput,
        openapi_extra={"parameters": [IF_MATCH]},
    )
    def patch(
        identifier: UUID, body: WorkPatch, request: Request, response: Response
    ) -> WorkOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            item, permission = work.scoped_work(db, actor.id, identifier, write=True)
            work.require_update(item, permission, actor.id)
            if not permission.manage and body.model_fields_set & {
                "parent_id",
                "owner_id",
                "assignee_ids",
                "external_participants",
            }:
                raise identity.IdentityError(403, "forbidden")
            work.require_active(db, permission)
            _version(item, request)
            before = work.output(item, permission, actor.id).model_dump()
            owner_changed = "owner_id" in body.model_fields_set and body.owner_id != item.owner_id
            if body.model_fields_set & {"owner_id", "assignee_ids"}:
                previous = {row.user_id for row in item.assignees}
                added = set(body.assignee_ids or []) - previous
                contributors = work.validate_assignments(
                    db, permission, body.owner_id if owner_changed else None, list(added)
                )
            with db.no_autoflush:
                for field in body.model_fields_set - {
                    "due",
                    "assignee_ids",
                    "external_participants",
                }:
                    setattr(item, field, getattr(body, field))
                if owner_changed:
                    item.owner = contributors.get(body.owner_id) if body.owner_id else None
                if "due" in body.model_fields_set:
                    work.set_due(db, item, body.due)
                if body.assignee_ids is not None:
                    existing = {row.user_id: row for row in item.assignees}
                    item.assignees = [
                        existing.get(user) or WorkAssignee(user_id=user, user=contributors[user])
                        for user in body.assignee_ids
                    ]
                if body.external_participants is not None:
                    current_labels = {
                        row.unresolved_label: row for row in item.external_participants
                    }
                    item.external_participants = [
                        current_labels.get(label) or WorkExternalParticipant(unresolved_label=label)
                        for label in body.external_participants
                    ]
                work.validate_parent(db, item)
                after = work.output(item, permission, actor.id).model_dump()
                changes = sorted(
                    field for field in body.model_fields_set if before[field] != after[field]
                )
            if changes:
                work.advance(item)
                _event(
                    db,
                    actor,
                    item,
                    request,
                    "assigned" if set(changes) & {"owner_id", "assignee_ids"} else "updated",
                    changed_fields=",".join(changes),
                )
            db.flush()
            _etag(response, item.version)
            return work.output(item, permission, actor.id)

    @router.post(
        "/work-items/{identifier}/transitions",
        response_model=WorkOutput,
        openapi_extra={"parameters": [IF_MATCH, IDEMPOTENCY_KEY]},
    )
    def transition(
        identifier: UUID, body: Transition, request: Request, response: Response
    ) -> WorkOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            item, permission = work.scoped_work(db, actor.id, identifier, write=True)
            work.require_update(item, permission, actor.id)
            route = "work-transition:" + str(identifier)
            expected = _expected_version(request)
            key, fingerprint, saved = _operation(
                db, actor, request, route, body.model_dump(mode="json")
            )
            if saved:
                result = WorkOutput.model_validate(saved.result)
                result = result.model_copy(
                    update={
                        "can_manage": permission.manage,
                        "can_update": work.can_update(item, permission, actor.id),
                        "can_comment": permission.contribute,
                        "project_writable": permission.writable,
                    }
                )
                _etag(response, result.version)
                return result
            work.require_active(db, permission)
            if item.version != expected:
                raise identity.IdentityError(409, "version_conflict")
            old = item.status
            if work.transition(db, item, permission, actor.id, body):
                event = (
                    "completed"
                    if item.status == "done"
                    else "blocked"
                    if item.status == "blocked"
                    else "status_changed"
                )
                _event(db, actor, item, request, event, from_status=old, to_status=item.status)
            db.flush()
            result = work.output(item, permission, actor.id)
            _remember(db, actor, route, key, fingerprint, result, 200)
            _etag(response, item.version)
            return result

    @router.get("/projects/{project_id}/work-candidates", response_model=CandidatePage)
    def contributors(
        project_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> CandidatePage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            permission = work.access(db, actor.id, project_id)
            if not permission.contribute:
                raise identity.IdentityError(403, "forbidden")
            _query(request)
            scope = f"work-candidates:{project_id}"
            last = _cursor(cursor, scope)
            query = work.candidates(permission.project).order_by(User.id).limit(limit + 1)
            if last:
                query = query.where(User.id > last)
            rows = list(db.scalars(query))
            return CandidatePage(
                items=[Candidate(id=row.id, display_name=row.display_name) for row in rows[:limit]],
                next_cursor=_next_cursor(scope, rows[limit - 1].id) if len(rows) > limit else None,
            )

    @router.get("/work-items/{identifier}/comments", response_model=CommentPage)
    def comments(
        identifier: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> CommentPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            work.scoped_work(db, actor.id, identifier)
            _query(request)
            scope = f"work-comments:{identifier}"
            last = _time_cursor(cursor, scope)
            query = (
                select(WorkComment)
                .where(WorkComment.work_item_id == identifier)
                .order_by(WorkComment.created_at, WorkComment.id)
                .limit(limit + 1)
            )
            if last:
                query = query.where(tuple_(WorkComment.created_at, WorkComment.id) > last)
            rows = list(db.scalars(query))
            return CommentPage(
                items=[CommentOutput.model_validate(row) for row in rows[:limit]],
                next_cursor=_next_time_cursor(scope, rows[limit - 1].created_at, rows[limit - 1].id)
                if len(rows) > limit
                else None,
            )

    @router.post(
        "/work-items/{identifier}/comments",
        response_model=CommentOutput,
        status_code=201,
        openapi_extra={"parameters": [IF_MATCH, IDEMPOTENCY_KEY]},
    )
    def comment(
        identifier: UUID, body: CommentCreate, request: Request, response: Response
    ) -> CommentOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            item, permission = work.scoped_work(db, actor.id, identifier, write=True)
            route = "work-comment:" + str(identifier)
            expected = _expected_version(request)
            key, fingerprint, saved = _operation(
                db, actor, request, route, attachment_links.intent(body, mode="json")
            )
            if saved:
                response.status_code = 200
                return CommentOutput.model_validate(saved.result)
            work.require_active(db, permission)
            if item.version != expected:
                raise identity.IdentityError(409, "version_conflict")
            files = attachment_links.locked(db, "work_item", item.id, "work", body.attachment_ids)
            row = WorkComment(
                work_item_id=item.id,
                author_id=actor.id,
                body=body.body,
                attachment_count=len(files),
            )
            db.add(row)
            db.flush()
            attachment_links.attach(db, row.id, item.id, "work", files)
            work.advance(item)
            _event(db, actor, item, request, "commented", comment_id=str(row.id))
            result = CommentOutput.model_validate(row)
            _remember(db, actor, route, key, fingerprint, result, 201)
            return result

    @router.get("/work-items/{identifier}/activity", response_model=ActivityPage)
    def history(
        identifier: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> ActivityPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            work.scoped_work(db, actor.id, identifier)
            _query(request)
            return activity_page(
                db,
                select(ActivityEvent).where(
                    ActivityEvent.resource_type == "work_item",
                    ActivityEvent.resource_id == identifier,
                ),
                f"work-activity:{identifier}",
                limit,
                cursor,
            )

    @router.get("/work-items/{identifier}/status-history", response_model=StatePage)
    def states(
        identifier: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> StatePage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            work.scoped_work(db, actor.id, identifier)
            _query(request)
            scope = f"v1|work-states:{identifier}|"
            query = (
                select(WorkStatusHistory)
                .where(WorkStatusHistory.work_item_id == identifier)
                .order_by(WorkStatusHistory.version.desc())
                .limit(limit + 1)
            )
            if cursor is not None:
                if not cursor.startswith(scope) or not re.fullmatch(
                    r"[1-9][0-9]{0,9}", cursor[len(scope) :]
                ):
                    raise identity.IdentityError(422, "invalid_cursor")
                version = int(cursor[len(scope) :])
                if version > 2147483647:
                    raise identity.IdentityError(422, "invalid_cursor")
                query = query.where(WorkStatusHistory.version < version)
            rows = list(db.scalars(query))
            return StatePage(
                items=[StateOutput.model_validate(row) for row in rows[:limit]],
                next_cursor=scope + str(rows[limit - 1].version) if len(rows) > limit else None,
            )

    return router
