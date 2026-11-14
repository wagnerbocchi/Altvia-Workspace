"""Discovery must filter the full authorized set before paging or deduplication."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session
from test_team_api import admin_client, preconditions, sign_in
from test_work_items import create_work, setup_project

__all__ = ["admin_client"]


def task(client, project_id, **values):
    response = create_work(client, project_id, **values)
    assert response.status_code == 201, response.text
    return response.json()["work_item_id"]


def ids(response):
    assert response.status_code == 200, response.text
    return [row["id"] for row in response.json()["items"]]


def test_searches_title_description_and_current_edits(admin_client, seeded_user):
    p = setup_project(admin_client, seeded_user)
    a = task(admin_client, p, title="Manutenção de servidores", description="rede privada")
    b = task(admin_client, p, title="Manutenção urgente", description="banco PostgreSQL")
    task(admin_client, p, title="Verificar impressora")
    path = "/api/v1/work-items"
    for query, expected in [
        ("servidores", [a]),
        ('"rede privada"', [a]),
        ("manutenção -urgente", [a]),
        ("PostgreSQL", [b]),
        ("impossivelinexistente", []),
        ("de e a", []),
    ]:
        assert ids(admin_client.get(path, params={"project_id": p, "q": query})) == expected
    result = admin_client.patch(
        "/api/v1/work-items/" + a,
        json={"title": "Revisão", "description": "cabeamento"},
        headers=preconditions(),
    )
    assert result.status_code == 200, result.text
    assert ids(admin_client.get(path, params={"project_id": p, "q": "servidores"})) == []
    assert ids(admin_client.get(path, params={"project_id": p, "q": "cabeamento"})) == [a]


def test_typed_filters_and_exclusive_deadline_boundary(admin_client, seeded_user):
    p = setup_project(admin_client, seeded_user)
    a = task(
        admin_client,
        p,
        owner_id=str(seeded_user),
        priority="high",
        assignee_ids=[str(seeded_user)],
        due={"precision": "date", "date": "2026-11-09", "timezone": "America/Sao_Paulo"},
    )
    b = task(admin_client, p, work_type="ongoing")
    task(admin_client, p, due={"precision": "instant", "instant": "2026-11-10T04:00:00Z"})
    checks = [
        ({"status": "in_progress"}, [b]),
        ({"work_type": "ongoing"}, [b]),
        ({"priority": "high"}, [a]),
        ({"owner_id": str(seeded_user)}, [a]),
        ({"involved_user_id": str(seeded_user)}, [a]),
        ({"unassigned": True, "due_presence": "undated"}, [b]),
        ({"due_from": "2026-11-10T03:00:00Z", "due_before": "2026-11-10T04:00:00Z"}, [a]),
        ({"due_before": "2026-11-10T03:00:00Z"}, []),
        ({"priority": "high", "status": "in_progress"}, []),
    ]
    for filters, expected in checks:
        assert (
            ids(admin_client.get("/api/v1/work-items", params={"project_id": p, **filters}))
            == expected
        )


def test_filtered_cursor_binds_actor_filters_and_project(admin_client, seeded_user, db_engine):
    p = setup_project(admin_client, seeded_user)
    created = [task(admin_client, p, title="Busca", owner_id=str(seeded_user)) for _ in range(3)]
    query = {"project_id": p, "q": " Busca ", "limit": 1}
    first = admin_client.get("/api/v1/work-items", params=query)
    found = ids(first)
    cursor = first.json()["next_cursor"]
    assert cursor
    second = admin_client.get(
        "/api/v1/work-items", params={**query, "q": "Busca", "cursor": cursor}
    )
    found += ids(second)
    third = admin_client.get(
        "/api/v1/work-items", params={**query, "cursor": second.json()["next_cursor"]}
    )
    found += ids(third)
    assert found == sorted(created) and third.json()["next_cursor"] is None
    for extra in [{"q": "Outro"}, {"priority": "high"}, {"q": ""}]:
        assert (
            admin_client.get(
                "/api/v1/work-items", params={**query, "cursor": cursor, **extra}
            ).status_code
            == 422
        )
    assert admin_client.get("/api/v1/my-work", params={"cursor": cursor}).status_code == 422
    # Actor change with the same readable project cannot reuse a filtered cursor.
    from altvia.models import User
    from altvia.project_registry import set_project_access

    with Session(db_engine) as db, db.begin():
        other = db.query(User).filter_by(email_normalized="admin@example.test").one()
        set_project_access(db, other.email_normalized, UUID(p), "viewer")
    sign_in(admin_client, "admin@example.test")
    assert (
        admin_client.get("/api/v1/work-items", params={**query, "cursor": cursor}).status_code
        == 422
    )


@pytest.mark.parametrize(
    "params",
    [
        {"status": "new"},
        {"priority": "urgent"},
        {"work_type": "recurring"},
        {"owner_id": "oops"},
        {"involved_user_id": "oops"},
        {"due_presence": "overdue"},
        {"due_from": "2026-11-10T00:00:00"},
        {"due_from": "0"},
        {"q": "x" * 201},
        {"unknown": "x"},
        {"due_from": "2026-11-10T04:00:00Z", "due_before": "2026-11-10T04:00:00Z"},
        [("status", "todo"), ("status", "done")],
    ],
)
def test_discovery_rejects_invalid_or_repeated_queries(admin_client, seeded_user, params):
    p = setup_project(admin_client, seeded_user)
    pairs = list(params.items()) if isinstance(params, dict) else params
    assert (
        admin_client.get("/api/v1/work-items", params=[("project_id", p), *pairs]).status_code
        == 422
    )
    assert admin_client.get("/api/v1/my-work", params=pairs).status_code == 422


def test_personal_queue_full_set_dedup_and_revocation(admin_client, seeded_user, db_engine):
    from altvia.models import ProjectMember, RoleBinding

    p = setup_project(admin_client, seeded_user)
    mine = [
        task(admin_client, p, owner_id=str(seeded_user), assignee_ids=[str(seeded_user)]),
        task(admin_client, p, assignee_ids=[str(seeded_user)]),
    ]
    task(admin_client, p)
    result = admin_client.get("/api/v1/my-work", params={"limit": 1})
    found = ids(result)
    assert result.json()["next_cursor"]
    assert datetime.fromisoformat(result.json()["as_of"]).tzinfo is not None
    assert result.json()["items"][0]["kind"] == "work_item"
    assert result.json()["items"][0]["project_name"] == "Project"
    more = admin_client.get(
        "/api/v1/my-work", params={"limit": 1, "cursor": result.json()["next_cursor"]}
    )
    found += ids(more)
    assert found == sorted(mine) and more.json()["next_cursor"] is None
    for key in ["project_id", "client_id", "team_id"]:
        assert ids(admin_client.get("/api/v1/my-work", params={key: str(uuid4())})) == []
    # An assignment survives loss of either membership half, but is never a grant.
    with Session(db_engine) as db, db.begin():
        db.delete(db.get(ProjectMember, (UUID(p), seeded_user)))
    assert ids(admin_client.get("/api/v1/my-work")) == []
    assert (
        admin_client.get("/api/v1/work-items", params={"project_id": p, "q": "Task"}).status_code
        == 404
    )
    with Session(db_engine) as db, db.begin():
        db.add(ProjectMember(project_id=UUID(p), user_id=seeded_user))
        binding = db.query(RoleBinding).filter_by(user_id=seeded_user, project_id=UUID(p)).one()
        db.delete(binding)
    assert ids(admin_client.get("/api/v1/my-work")) == []


def test_personal_query_is_bounded_not_per_result(admin_client, seeded_user, db_engine):
    p = setup_project(admin_client, seeded_user)
    task(admin_client, p, owner_id=str(seeded_user))
    counts = []

    def count(*args):
        counts.append(1)

    event.listen(Engine, "before_cursor_execute", count)
    try:
        assert len(ids(admin_client.get("/api/v1/my-work"))) == 1
        initial = len(counts)
        assert initial > 0
    finally:
        event.remove(Engine, "before_cursor_execute", count)
    for _ in range(4):
        task(admin_client, p, owner_id=str(seeded_user))
    counts.clear()
    event.listen(Engine, "before_cursor_execute", count)
    try:
        assert len(ids(admin_client.get("/api/v1/my-work"))) == 5
        assert len(counts) == initial
    finally:
        event.remove(Engine, "before_cursor_execute", count)


def test_personal_queue_never_inherits_platform_admin(admin_client, seeded_user):
    p = setup_project(admin_client, seeded_user)
    task(admin_client, p, owner_id=str(seeded_user))
    sign_in(admin_client, "admin@example.test")
    assert ids(admin_client.get("/api/v1/my-work")) == []
    assert ids(admin_client.get("/api/v1/my-work", params={"project_id": p, "q": "Task"})) == []


def test_personal_customer_ceiling_and_multi_project_search(admin_client, seeded_user, db_engine):
    from altvia.models import ClientAccessGrant
    from test_client_registry import created as create_client
    from test_project_registry import project
    from test_team_api import created as create_team

    customer = create_client(admin_client, seeded_user)
    team = create_team(admin_client)["id"]
    projects = [
        project(admin_client, seeded_user, team, customer).json()["project_id"] for _ in range(2)
    ]
    sign_in(admin_client, "employee@example.test")
    tasks = [task(admin_client, p, title="Manutenção", owner_id=str(seeded_user)) for p in projects]
    assert ids(admin_client.get("/api/v1/my-work", params={"q": "Manutenção"})) == sorted(tasks)
    assert ids(admin_client.get("/api/v1/my-work", params={"client_id": customer})) == sorted(tasks)
    assert ids(admin_client.get("/api/v1/my-work", params={"team_id": team})) == sorted(tasks)
    assert ids(admin_client.get("/api/v1/my-work", params={"project_id": projects[0]})) == [
        tasks[0]
    ]
    # Archiving changes writes, not the existing read authority.
    archived = admin_client.patch(
        "/api/v1/projects/" + projects[0], json={"active": False}, headers=preconditions()
    )
    assert archived.status_code == 200
    assert ids(admin_client.get("/api/v1/my-work")) == sorted(tasks)
    with Session(db_engine) as db, db.begin():
        db.delete(db.get(ClientAccessGrant, (seeded_user, UUID(customer))))
    assert ids(admin_client.get("/api/v1/my-work", params={"q": "Manutenção"})) == []
    assert ids(admin_client.get("/api/v1/my-work", params={"client_id": customer})) == []


def test_discovery_index_rollback_preserves_tasks_and_history(admin_client, seeded_user, db_engine):
    from alembic import command
    from alembic.config import Config

    p = setup_project(admin_client, seeded_user)
    identifier = task(admin_client, p, owner_id=str(seeded_user))
    config = Config("apps/api/alembic.ini")
    command.downgrade(config, "b46087000008")
    try:
        assert ids(admin_client.get("/api/v1/my-work")) == [identifier]
        # Inspect preserved v8 data directly: later metadata tables were dropped,
        # so the current expanded application is not supported on this schema.
        with db_engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM work_item_status_history WHERE work_item_id=:id"),
                    {"id": UUID(identifier)},
                )
                == 1
            )
    finally:
        command.upgrade(config, "head")
    history = admin_client.get("/api/v1/work-items/" + identifier + "/status-history")
    assert history.status_code == 200 and len(history.json()["items"]) == 1
    command.check(config)


def test_search_index_is_native_and_used_for_representative_data(
    admin_client, seeded_user, db_engine
):
    p = setup_project(admin_client, seeded_user)
    task(admin_client, p, title="Seletivapalavra")
    with db_engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO work_items
            (id,project_id,title,description,status,work_type,priority,version)
            SELECT gen_random_uuid(),:project,'Atividade operacional comum',
                '','todo','one_off','medium',1
            FROM generate_series(1,6000)"""),
            {"project": p},
        )
        conn.execute(text("ANALYZE work_items"))
        plan = str(
            conn.execute(
                text("""EXPLAIN (FORMAT JSON) SELECT id FROM work_items
            WHERE to_tsvector('portuguese'::regconfig,
                coalesce(title,'') || ' ' || coalesce(description,''))
            @@ websearch_to_tsquery('portuguese'::regconfig,'Seletivapalavra')""")
            ).scalar_one()
        )
        assert "ix_work_search" in plan, plan
    assert (
        len(
            ids(
                admin_client.get(
                    "/api/v1/work-items", params={"project_id": p, "q": "Seletivapalavra"}
                )
            )
        )
        == 1
    )
