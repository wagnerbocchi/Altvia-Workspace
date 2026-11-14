"""Management eligibility and complete-set aggregation share one SQL snapshot."""

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    and_,
    case,
    cast,
    func,
    literal,
    or_,
    select,
    text,
    true,
    tuple_,
    union,
    union_all,
)
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by
from sqlalchemy.dialects.postgresql import UUID as SQLUUID
from sqlalchemy.orm import Session

from altvia import identity, project_registry, tickets
from altvia.analytics_schemas import (
    ActiveWorkCounts,
    AnalyticsFilters,
    AnalyticsOverview,
    AnalyticsScopePage,
    AnalyticsWorkloadPage,
    ScopeFilters,
    WorkloadFilters,
)
from altvia.models import (
    Client,
    RoleBinding,
    Team,
    Ticket,
    TicketQueue,
    TicketSlaEvent,
    TicketSlaState,
    TicketWorkItem,
    User,
    WorkItem,
)

WORK_STATUSES = ("todo", "in_progress", "blocked", "done", "cancelled")
TICKET_STATUSES = ("new", "open", "pending_customer", "pending_third_party", "resolved", "closed")
PRIORITIES = ("low", "medium", "high", "critical")
ZERO_UUID = UUID(int=0)


@dataclass(frozen=True)
class AnalyticsCursor:
    rank: int
    identifier: UUID


def _scope(actor_id: UUID, filters: AnalyticsFilters | ScopeFilters) -> str:
    values = filters.model_dump(mode="json", exclude={"limit", "cursor"}, exclude_none=True)
    collection = "scopes" if isinstance(filters, ScopeFilters) else "workload"
    raw = json.dumps([str(actor_id), collection, values], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _cursor(value: str | None, scope: str, *, nullable: bool) -> AnalyticsCursor | None:
    if value is None:
        return None
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,320}", value):
            raise ValueError("Invalid encoding")
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        version, current_scope, rank, identifier = raw.decode("ascii").split("|")
        parsed = UUID(identifier)
        if (
            version != "v1"
            or current_scope != scope
            or rank not in ({"0", "1"} if nullable else {"1"})
            or (rank == "0" and parsed != ZERO_UUID)
            or str(parsed) != identifier
            or base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value
        ):
            raise ValueError("Invalid cursor")
        return AnalyticsCursor(int(rank), parsed)
    except (ValueError, UnicodeError):
        raise identity.IdentityError(422, "invalid_cursor") from None


def _encode_cursor(scope: str, identifier: UUID | None) -> str:
    rank = 0 if identifier is None else 1
    raw = f"v1|{scope}|{rank}|{identifier if identifier is not None else ZERO_UUID}"
    return base64.urlsafe_b64encode(raw.encode("ascii")).decode("ascii").rstrip("=")


def managed_projects(actor_id: UUID) -> Any:
    native = project_registry.visible_projects(actor_id)
    return native.where(native.selected_columns.can_manage).cte("analytics_managed_projects")


def _managed_work(projects: Any) -> Any:
    return select(
        WorkItem.id,
        WorkItem.project_id,
        WorkItem.owner_id.label("responsible_id"),
        WorkItem.status,
        WorkItem.work_type,
        WorkItem.priority,
        WorkItem.due_at,
        WorkItem.due_precision,
        WorkItem.created_at,
    ).join(projects, projects.c.id == WorkItem.project_id)


def _managed_tickets(actor_id: UUID) -> Any:
    return (
        tickets.visible(actor_id)
        .with_only_columns(
            Ticket.id,
            Ticket.assignee_id.label("responsible_id"),
            Ticket.status,
            Ticket.priority,
            Ticket.created_at,
        )
        .where(RoleBinding.role_name == "operations_manager")
    )


def eligible(actor_id: UUID, filters: AnalyticsFilters) -> tuple[Any, Any]:
    projects = managed_projects(actor_id)
    work = _managed_work(projects)
    ticket = _managed_tickets(actor_id)
    for value, work_column, ticket_column in (
        (filters.priority, WorkItem.priority, Ticket.priority),
        (filters.client_id, projects.c.client_id, Ticket.client_id),
        (filters.team_id, projects.c.team_id, TicketQueue.team_id),
        (filters.responsible_id, WorkItem.owner_id, Ticket.assignee_id),
    ):
        if value is not None:
            work, ticket = work.where(work_column == value), ticket.where(ticket_column == value)
    if filters.unassigned:
        work = work.where(WorkItem.owner_id.is_(None))
        ticket = ticket.where(Ticket.assignee_id.is_(None))
    if filters.created_from is not None:
        work = work.where(WorkItem.created_at >= filters.created_from)
        ticket = ticket.where(Ticket.created_at >= filters.created_from)
    if filters.created_before is not None:
        work = work.where(WorkItem.created_at < filters.created_before)
        ticket = ticket.where(Ticket.created_at < filters.created_before)
    if filters.project_id is not None:
        work = work.where(WorkItem.project_id == filters.project_id)
        linked = (
            select(TicketWorkItem.work_item_id)
            .join(WorkItem, WorkItem.id == TicketWorkItem.work_item_id)
            .join(projects, projects.c.id == WorkItem.project_id)
            .where(
                TicketWorkItem.ticket_id == Ticket.id,
                projects.c.id == filters.project_id,
            )
            .correlate(Ticket)
            .exists()
        )
        ticket = ticket.where(linked)
    return work.cte("analytics_work"), ticket.cte("analytics_tickets")


def work_active(work: Any) -> Any:
    return work.c.status.not_in(("done", "cancelled"))


def ticket_active(ticket: Any) -> Any:
    return ticket.c.status.not_in(("resolved", "closed"))


def work_predicates(work: Any, filters: AnalyticsFilters) -> dict[str, Any]:
    active = work_active(work)
    ordinary = and_(active, work.c.work_type == "one_off")
    dated = and_(ordinary, work.c.due_at.is_not(None))
    overdue = or_(
        and_(work.c.due_precision == "date", work.c.due_at <= filters.reference_at),
        and_(work.c.due_precision == "instant", work.c.due_at < filters.reference_at),
    )
    return {
        "active_work_item_count": active,
        "blocked_work_item_count": work.c.status == "blocked",
        "ongoing_work_item_count": and_(active, work.c.work_type == "ongoing"),
        "active_no_due_date_count": and_(ordinary, work.c.due_at.is_(None)),
        "overdue_work_item_count": and_(dated, overdue),
        "due_soon_work_item_count": and_(dated, ~overdue, work.c.due_at <= filters.due_through),
        "later_due_work_item_count": and_(dated, ~overdue, work.c.due_at > filters.due_through),
        "all_missing_deadline_count": work.c.due_at.is_(None),
        "unassigned_work_item_count": and_(active, work.c.responsible_id.is_(None)),
    }


def _distribution(column: Any, values: tuple[str, ...]) -> Any:
    pairs = [part for value in values for part in (value, func.count().filter(column == value))]
    return cast(func.jsonb_build_object(*pairs), JSONB)


def represented(work: Any, ticket: Any, *, active: bool = False) -> Any:
    linked = (
        select(TicketWorkItem.work_item_id)
        .join(work, work.c.id == TicketWorkItem.work_item_id)
        .where(TicketWorkItem.ticket_id == ticket.c.id)
    )
    if active:
        linked = linked.where(work_active(work))
    return linked.correlate(ticket).exists()


def _sla_statistics(ticket: Any) -> Any:
    latest = (
        select(TicketSlaState.ticket_id, func.max(TicketSlaState.cycle_number).label("number"))
        .join(ticket, ticket.c.id == TicketSlaState.ticket_id)
        .group_by(TicketSlaState.ticket_id)
        .cte("analytics_latest_sla")
    )

    def observed(kind: str) -> Any:
        return (
            select(TicketSlaEvent.event_id)
            .where(
                TicketSlaEvent.ticket_id == TicketSlaState.ticket_id,
                TicketSlaEvent.cycle_number == TicketSlaState.cycle_number,
                TicketSlaEvent.kind == kind,
            )
            .correlate(TicketSlaState)
            .exists()
        )

    current = (
        select(
            ticket.c.id,
            TicketSlaState.cycle_number,
            TicketSlaState.policy_id,
            observed("breached").label("breached"),
            observed("corrected").label("corrected"),
        )
        .select_from(
            ticket.outerjoin(latest, latest.c.ticket_id == ticket.c.id).outerjoin(
                TicketSlaState,
                and_(
                    TicketSlaState.ticket_id == ticket.c.id,
                    TicketSlaState.cycle_number == latest.c.number,
                ),
            )
        )
        .cte("analytics_current_sla")
    )
    last_observation = (
        select(func.max(TicketSlaEvent.occurred_at))
        .join(
            current,
            and_(
                current.c.id == TicketSlaEvent.ticket_id,
                current.c.cycle_number == TicketSlaEvent.cycle_number,
            ),
        )
        .where(current.c.policy_id.is_not(None))
        .scalar_subquery()
    )
    configured = current.c.policy_id.is_not(None)
    return (
        select(
            func.count().filter(current.c.cycle_number.is_(None)).label("sla_legacy_ticket_count"),
            func.count()
            .filter(and_(current.c.cycle_number.is_not(None), ~configured))
            .label("sla_unconfigured_ticket_count"),
            func.count().filter(configured).label("sla_configured_ticket_count"),
            func.count()
            .filter(and_(configured, current.c.breached))
            .label("sla_recorded_breach_ticket_count"),
            func.count()
            .filter(and_(configured, current.c.breached, current.c.corrected))
            .label("sla_corrected_ticket_count"),
            last_observation.label("sla_last_observation_at"),
        )
        .select_from(current)
        .cte("analytics_sla_counts")
    )


def _overview_statement(work: Any, ticket: Any, filters: AnalyticsFilters) -> Any:
    work_counts = (
        select(
            func.count().label("work_item_count"),
            *(
                func.count().filter(predicate).label(name)
                for name, predicate in work_predicates(work, filters).items()
            ),
            _distribution(work.c.status, WORK_STATUSES).label("work_status_counts"),
            _distribution(work.c.priority, PRIORITIES).label("work_priority_counts"),
        )
        .select_from(work)
        .cte("analytics_work_counts")
    )
    ticket_counts = (
        select(
            func.count().label("ticket_count"),
            func.count().filter(ticket_active(ticket)).label("active_ticket_count"),
            func.count()
            .filter(and_(ticket_active(ticket), ticket.c.responsible_id.is_(None)))
            .label("unassigned_ticket_count"),
            func.count()
            .filter(ticket.c.status == "pending_customer")
            .label("pending_customer_ticket_count"),
            func.count()
            .filter(ticket.c.status == "pending_third_party")
            .label("pending_third_party_ticket_count"),
            _distribution(ticket.c.status, TICKET_STATUSES).label("ticket_status_counts"),
            _distribution(ticket.c.priority, PRIORITIES).label("ticket_priority_counts"),
        )
        .select_from(ticket)
        .cte("analytics_ticket_counts")
    )
    representation = (
        select(
            func.count().filter(represented(work, ticket)).label("represented_ticket_count"),
            func.count()
            .filter(and_(ticket_active(ticket), represented(work, ticket, active=True)))
            .label("active_represented"),
        )
        .select_from(ticket)
        .cte("analytics_representation")
    )
    sla = _sla_statistics(ticket)
    return select(
        *work_counts.c,
        *ticket_counts.c,
        representation.c.represented_ticket_count,
        (ticket_counts.c.ticket_count - representation.c.represented_ticket_count).label(
            "standalone_ticket_count"
        ),
        (
            work_counts.c.work_item_count
            + ticket_counts.c.ticket_count
            - representation.c.represented_ticket_count
        ).label("unified_count"),
        (
            work_counts.c.active_work_item_count
            + ticket_counts.c.active_ticket_count
            - representation.c.active_represented
        ).label("active_unified_count"),
        *sla.c,
    ).select_from(
        work_counts.join(ticket_counts, true()).join(representation, true()).join(sla, true())
    )


def overview_statement(actor_id: UUID, filters: AnalyticsFilters) -> Any:
    work, ticket = eligible(actor_id, filters)
    return _overview_statement(work, ticket, filters)


def workload_statement(
    actor_id: UUID, filters: AnalyticsFilters, limit: int, after: AnalyticsCursor | None
) -> Any:
    work, ticket = eligible(actor_id, filters)
    counts = tuple(ActiveWorkCounts.model_fields)
    predicates = work_predicates(work, filters)
    work_totals = (
        select(
            work.c.responsible_id,
            *(
                (
                    literal(0)
                    if name == "active_ticket_count"
                    else func.count().filter(predicates[name])
                ).label(name)
                for name in counts
            ),
        )
        .where(work_active(work))
        .group_by(work.c.responsible_id)
    )
    ticket_totals = (
        select(
            ticket.c.responsible_id,
            *(
                (func.count() if name == "active_ticket_count" else literal(0)).label(name)
                for name in counts
            ),
        )
        .where(ticket_active(ticket))
        .group_by(ticket.c.responsible_id)
    )
    domains = union_all(work_totals, ticket_totals).cte("analytics_principal_domains")
    totals = (
        select(
            domains.c.responsible_id,
            *(func.sum(domains.c[name]).label(name) for name in counts),
        )
        .group_by(domains.c.responsible_id)
        .cte("analytics_principal_counts")
    )
    rank = case((totals.c.responsible_id.is_(None), 0), else_=1)
    identifier = func.coalesce(totals.c.responsible_id, literal(ZERO_UUID, type_=SQLUUID))
    page = select(
        totals.c.responsible_id.label("user_id"),
        User.display_name.label("name"),
        *(totals.c[name] for name in counts),
        rank.label("rank"),
        identifier.label("identifier"),
    ).select_from(totals.outerjoin(User, User.id == totals.c.responsible_id))
    if after is not None:
        page = page.where(
            tuple_(rank, identifier)
            > tuple_(literal(after.rank), literal(after.identifier, type_=SQLUUID))
        )
    page_rows = page.order_by(rank, identifier).limit(limit + 1).cte("analytics_principal_page")
    payload = func.jsonb_build_object(
        *[part for name in ("user_id", "name", *counts) for part in (name, page_rows.c[name])]
    )
    page_values = (
        select(
            func.coalesce(
                func.jsonb_agg(
                    aggregate_order_by(payload, page_rows.c.rank, page_rows.c.identifier)
                ),
                cast(literal("[]"), JSONB),
            ).label("items")
        )
        .select_from(page_rows)
        .cte("analytics_principal_json")
    )
    overview = _overview_statement(work, ticket, filters).cte("analytics_overview")
    return select(*overview.c, page_values.c["items"]).select_from(
        overview.join(page_values, true())
    )


def workload(db: Session, actor_id: UUID, filters: WorkloadFilters) -> AnalyticsWorkloadPage:
    report_filters = AnalyticsFilters.model_validate(
        filters.model_dump(exclude={"limit", "cursor"})
    )
    scope = _scope(actor_id, report_filters)
    after = _cursor(filters.cursor, scope, nullable=True)
    values = dict(
        db.execute(workload_statement(actor_id, report_filters, filters.limit, after))
        .mappings()
        .one()
    )
    items = values.pop("items")
    more = len(items) > filters.limit
    items = items[: filters.limit]
    identifier = items[-1]["user_id"] if more else None
    return AnalyticsWorkloadPage(
        items=items,
        next_cursor=(
            _encode_cursor(scope, UUID(identifier) if identifier is not None else None)
            if more
            else None
        ),
        overview=AnalyticsOverview(observed_at=datetime.now(UTC), filters=report_filters, **values),
    )


def scopes_statement(actor_id: UUID, filters: ScopeFilters, after: AnalyticsCursor | None) -> Any:
    projects = managed_projects(actor_id)
    if filters.kind == "project":
        choices = select(projects.c.id, projects.c.name)
    else:
        model: type[User] | type[Client] | type[Team]
        if filters.kind == "responsible":
            candidates = union(
                _managed_work(projects).with_only_columns(WorkItem.owner_id.label("id")),
                _managed_tickets(actor_id).with_only_columns(Ticket.assignee_id.label("id")),
            ).cte("analytics_scope_ids")
            model, name = User, User.display_name
        elif filters.kind == "client":
            candidates = union(
                select(projects.c.client_id.label("id")),
                _managed_tickets(actor_id).with_only_columns(Ticket.client_id.label("id")),
            ).cte("analytics_scope_ids")
            model, name = Client, Client.name
        else:
            candidates = union(
                select(projects.c.team_id.label("id")),
                _managed_tickets(actor_id).with_only_columns(TicketQueue.team_id.label("id")),
            ).cte("analytics_scope_ids")
            model, name = Team, Team.name
        choices = select(candidates.c.id, name.label("name")).join(
            model, model.id == candidates.c.id
        )
    choice_rows = choices.subquery("analytics_scope_choices")
    query = select(choice_rows)
    if after is not None:
        query = query.where(choice_rows.c.id > after.identifier)
    return query.order_by(choice_rows.c.id).limit(filters.limit + 1)


def scopes(db: Session, actor_id: UUID, filters: ScopeFilters) -> AnalyticsScopePage:
    scope = _scope(actor_id, filters)
    after = _cursor(filters.cursor, scope, nullable=False)
    rows = db.execute(scopes_statement(actor_id, filters, after)).mappings().all()
    return AnalyticsScopePage(
        items=rows[: filters.limit],
        next_cursor=(
            _encode_cursor(scope, rows[filters.limit - 1]["id"])
            if len(rows) > filters.limit
            else None
        ),
    )


def validate_timezone(db: Session, filters: AnalyticsFilters) -> None:
    known = db.scalar(
        text("SELECT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=:zone)"),
        {"zone": filters.timezone},
    )
    if not known:
        raise identity.IdentityError(422, "invalid_analytics_timezone")


def overview(db: Session, actor_id: UUID, filters: AnalyticsFilters) -> AnalyticsOverview:
    values = db.execute(overview_statement(actor_id, filters)).mappings().one()
    return AnalyticsOverview(observed_at=datetime.now(UTC), filters=filters, **values)
