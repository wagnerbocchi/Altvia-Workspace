"""Customer-scoped registry endpoints and minimal configuration creation receipts."""

from datetime import UTC, datetime
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

from altvia import client_registry, identity
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
from altvia.models import ActivityEvent, Client, User


def _trim(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


ClientName = Annotated[str, BeforeValidator(_trim), Field(min_length=1, max_length=150)]


class ClientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ClientName
    manager_user_id: UUID


class ClientCreation(BaseModel):
    client_id: UUID
    manager_user_id: UUID


class ClientPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})
    name: ClientName | SkipJsonSchema[None] = None
    active: StrictBool | SkipJsonSchema[None] = None

    @field_validator("name", "active")
    @classmethod
    def forbid_null(cls, value: str | bool | None) -> str | bool:
        if value is None:
            raise ValueError("A non-null value is required")
        return value

    @model_validator(mode="after")
    def require_field(self) -> "ClientPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class ClientOutput(BaseModel):
    id: UUID
    name: str
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    can_manage: bool


class ClientPage(BaseModel):
    items: list[ClientOutput]
    next_cursor: str | None


def _output(client: Client, role: str) -> ClientOutput:
    return ClientOutput(
        id=client.id,
        name=client.name,
        active=client.active,
        version=client.version,
        created_at=client.created_at,
        updated_at=client.updated_at,
        can_manage=role == "operations_manager",
    )


def create_client_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Clients"])

    def authenticate(db: Session, request: Request, *, write: bool = False) -> User:
        return authenticate_request(db, request, settings, write=write)

    @router.get("/clients", response_model=ClientPage)
    def list_clients(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> ClientPage:
        with Session(engine) as db, db.begin():
            user = authenticate(db, request)
            _collection_query(request)
            scope = f"clients:{user.id}"
            last = _cursor(cursor, scope)
            query = client_registry.visible_clients(user.id).order_by(Client.id).limit(limit + 1)
            if last is not None:
                query = query.where(Client.id > last)
            rows = list(db.execute(query))
            return ClientPage(
                items=[_output(client, role) for client, role in rows[:limit]],
                next_cursor=_next_cursor(scope, rows[limit - 1][0].id)
                if len(rows) > limit
                else None,
            )

    @router.post(
        "/clients",
        response_model=ClientCreation,
        status_code=201,
        responses={200: {"model": ClientCreation}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create(body: ClientCreate, request: Request, response: Response) -> ClientCreation:
        with Session(engine) as db, db.begin():
            actor = require_admin(db, request, settings, write=True)
            route = "/api/v1/clients"
            key, request_hash, saved = _operation(
                db, actor, request, route, body.model_dump(mode="json")
            )
            if saved is not None:
                response.status_code = 200
                return ClientCreation.model_validate(saved.result)
            client = client_registry.create_client(
                db, body.name, body.manager_user_id, actor, request.state.correlation_id
            )
            result = ClientCreation(client_id=client.id, manager_user_id=body.manager_user_id)
            _remember(db, actor, route, key, request_hash, result, 201)
            return result

    @router.get("/clients/{client_id}", response_model=ClientOutput)
    def get(client_id: UUID, request: Request, response: Response) -> ClientOutput:
        with Session(engine) as db, db.begin():
            user = authenticate(db, request)
            client, role = client_registry.scoped_client(db, user.id, client_id)
            _etag(response, client.version)
            return _output(client, role)

    @router.patch(
        "/clients/{client_id}",
        response_model=ClientOutput,
        openapi_extra={"parameters": [IF_MATCH]},
    )
    def patch(
        client_id: UUID, body: ClientPatch, request: Request, response: Response
    ) -> ClientOutput:
        with Session(engine) as db, db.begin():
            user = authenticate(db, request, write=True)
            client, role = client_registry.scoped_client(db, user.id, client_id, write=True)
            if client.version != _expected_version(request):
                raise identity.IdentityError(409, "version_conflict")
            changes = []
            if body.name is not None and client.name != body.name:
                client.name = body.name
                changes.append("name")
            if body.active is not None and client.active != body.active:
                client.active = body.active
                changes.append("active")
            if changes:
                client_registry.advance(client)
                identity.record_event(
                    db,
                    user.id,
                    client.id,
                    "client.updated",
                    datetime.now(UTC),
                    request.state.correlation_id,
                    client.version,
                    aggregate_type="client",
                    details={"changed_fields": ",".join(changes)},
                )
            _etag(response, client.version)
            return _output(client, role)

    @router.get("/clients/{client_id}/activity", response_model=ActivityPage)
    def history(
        client_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=250)] = None,
    ) -> ActivityPage:
        with Session(engine) as db, db.begin():
            user = authenticate(db, request)
            client_registry.scoped_client(db, user.id, client_id)
            _collection_query(request)
            query = select(ActivityEvent).where(
                ActivityEvent.resource_type == "client", ActivityEvent.resource_id == client_id
            )
            return activity_page(db, query, f"client-activity:{client_id}", limit, cursor)

    return router
