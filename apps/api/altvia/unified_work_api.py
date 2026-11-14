"""Read-only unified queue under the native authenticated session boundary."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from altvia import identity, unified_work
from altvia.admin_http import authenticate_request
from altvia.config import Settings
from altvia.unified_work_schemas import UnifiedWorkFilters, UnifiedWorkPage


def create_unified_work_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Personal work"])

    @router.get("/my-work/unified", response_model=UnifiedWorkPage)
    def listing(
        request: Request, filters: Annotated[UnifiedWorkFilters, Query()]
    ) -> UnifiedWorkPage:
        with Session(engine) as db, db.begin():
            actor = authenticate_request(db, request, settings)
            if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
                raise identity.IdentityError(422, "repeated_query")
            bound_scope = unified_work.scope(actor.id, filters)
            last = unified_work.cursor(filters.cursor, bound_scope)
            return unified_work.page(db, actor.id, filters, last)

    return router
