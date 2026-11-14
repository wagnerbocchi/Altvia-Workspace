"""Current authenticated management scope before every reporting statement."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from altvia import analytics_queries, identity
from altvia.admin_http import authenticate_request
from altvia.analytics_schemas import (
    AnalyticsFilters,
    AnalyticsOverview,
    AnalyticsScopePage,
    AnalyticsWorkloadPage,
    ScopeFilters,
    WorkloadFilters,
)
from altvia.config import Settings
from altvia.models import User


def create_analytics_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Management analytics"])

    def authorize(db: Session, request: Request) -> User:
        actor = authenticate_request(db, request, settings)
        if not identity.analytics_available(db, actor.id):
            raise identity.IdentityError(403, "forbidden")
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise identity.IdentityError(422, "repeated_query")
        return actor

    @router.get("/analytics/overview", response_model=AnalyticsOverview)
    def overview(
        request: Request, filters: Annotated[AnalyticsFilters, Query()]
    ) -> AnalyticsOverview:
        with Session(engine) as db, db.begin():
            actor = authorize(db, request)
            analytics_queries.validate_timezone(db, filters)
            return analytics_queries.overview(db, actor.id, filters)

    @router.get("/analytics/team-workload", response_model=AnalyticsWorkloadPage)
    def workload(
        request: Request, filters: Annotated[WorkloadFilters, Query()]
    ) -> AnalyticsWorkloadPage:
        with Session(engine) as db, db.begin():
            actor = authorize(db, request)
            analytics_queries.validate_timezone(db, filters)
            return analytics_queries.workload(db, actor.id, filters)

    @router.get("/analytics/scopes", response_model=AnalyticsScopePage)
    def scopes(request: Request, filters: Annotated[ScopeFilters, Query()]) -> AnalyticsScopePage:
        with Session(engine) as db, db.begin():
            actor = authorize(db, request)
            return analytics_queries.scopes(db, actor.id, filters)

    return router
