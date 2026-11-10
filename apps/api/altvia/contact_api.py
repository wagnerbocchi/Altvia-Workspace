"""Nested scoped contact configuration, independent of internal user accounts."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    StrictBool,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from altvia import client_contacts, client_registry, identity
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
from altvia.client_api import ClientName
from altvia.config import Settings
from altvia.models import ClientContact

ContactEmail = Annotated[str, BeforeValidator(client_contacts.normalize_contact_email)]


class ContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: ClientName
    email: ContactEmail


class ContactPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})
    display_name: ClientName | SkipJsonSchema[None] = None
    email: ContactEmail | SkipJsonSchema[None] = None
    active: StrictBool | SkipJsonSchema[None] = None

    @field_validator("display_name", "email", "active")
    @classmethod
    def non_null(cls, value: str | bool | None) -> str | bool:
        if value is None:
            raise ValueError("A non-null value is required")
        return value

    @model_validator(mode="after")
    def nonempty(self) -> "ContactPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class ContactOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    client_id: UUID
    display_name: str
    email_normalized: str
    active: bool
    verification_state: Literal["unverified"]
    version: int
    created_at: datetime
    updated_at: datetime


class ContactPage(BaseModel):
    items: list[ContactOutput]
    next_cursor: str | None


class ContactCreation(BaseModel):
    client_id: UUID
    contact_id: UUID


def create_contact_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/clients/{client_id}/contacts", tags=["Client contacts"])

    @router.get("", response_model=ContactPage)
    def listing(
        client_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> ContactPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            client_registry.scoped_client(db, actor.id, client_id)
            _collection_query(request)
            if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
                raise identity.IdentityError(422, "unsupported_query")
            scope = f"contacts:{actor.id}:{client_id}"
            last = _cursor(cursor, scope)
            query = (
                select(ClientContact)
                .where(ClientContact.client_id == client_id)
                .order_by(ClientContact.id)
                .limit(limit + 1)
            )
            if last is not None:
                query = query.where(ClientContact.id > last)
            rows = list(db.scalars(query))
            return ContactPage(
                items=[ContactOutput.model_validate(row) for row in rows[:limit]],
                next_cursor=_next_cursor(scope, rows[limit - 1].id) if len(rows) > limit else None,
            )

    @router.post(
        "",
        response_model=ContactCreation,
        status_code=201,
        responses={200: {"model": ContactCreation}},
        openapi_extra={"parameters": [IDEMPOTENCY_KEY]},
    )
    def create(
        client_id: UUID, body: ContactCreate, request: Request, response: Response
    ) -> ContactCreation:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            client, _ = client_registry.scoped_client(db, actor.id, client_id, write=True)
            route = f"/api/v1/clients/{client_id}/contacts"
            key, digest, saved = _operation(db, actor, request, route, body.model_dump(mode="json"))
            if saved is not None:
                response.status_code = 200
                return ContactCreation.model_validate(saved.result)
            client_contacts.require_active(client)
            client_contacts.unique_email(db, client_id, body.email)
            contact = ClientContact(
                client_id=client_id, display_name=body.display_name, email_normalized=body.email
            )
            db.add(contact)
            db.flush()
            client_contacts.contact_event(
                db, client, contact, actor.id, request.state.correlation_id
            )
            receipt = ContactCreation(client_id=client_id, contact_id=contact.id)
            _remember(db, actor, route, key, digest, receipt, 201)
            return receipt

    @router.get("/{contact_id}", response_model=ContactOutput)
    def get(
        client_id: UUID, contact_id: UUID, request: Request, response: Response
    ) -> ContactOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            client_registry.scoped_client(db, actor.id, client_id)
            row = client_contacts.scoped_contact(db, client_id, contact_id)
            _etag(response, row.version)
            return ContactOutput.model_validate(row)

    @router.patch(
        "/{contact_id}", response_model=ContactOutput, openapi_extra={"parameters": [IF_MATCH]}
    )
    def patch(
        client_id: UUID, contact_id: UUID, body: ContactPatch, request: Request, response: Response
    ) -> ContactOutput:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings, write=True)
            client, _ = client_registry.scoped_client(db, actor.id, client_id, write=True)
            row = client_contacts.scoped_contact(db, client_id, contact_id, write=True)
            if row.version != _expected_version(request):
                raise identity.IdentityError(409, "version_conflict")
            changes = []
            for field, attribute in [
                ("display_name", "display_name"),
                ("email", "email_normalized"),
                ("active", "active"),
            ]:
                value = getattr(body, field)
                if value is not None and getattr(row, attribute) != value:
                    if field == "email":
                        client_contacts.unique_email(db, client_id, value, row.id)
                    setattr(row, attribute, value)
                    changes.append(field)
            if changes:
                client_contacts.require_active(client)
                if row.version >= 2147483647:
                    raise identity.IdentityError(409, "version_exhausted")
                row.version += 1
                row.updated_at = datetime.now(UTC)
                client_contacts.contact_event(
                    db, client, row, actor.id, request.state.correlation_id, changes
                )
            _etag(response, row.version)
            return ContactOutput.model_validate(row)

    return router
