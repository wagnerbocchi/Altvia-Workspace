"""Owner-only pre-SLA ticket fixtures for incumbent native migration checks."""

from uuid import UUID

from sqlalchemy import Engine, text


def pre_sla_ticket(engine: Engine, identifier: UUID | str) -> None:
    """Represent a legacy ticket without deleting any obligation or source fact.

    Only the guarded disposable DB owner may remove its single new unconfigured
    tracking row. Configured cycles and every native ticket/history/message/event
    remain protected; production/runtime code never calls this fixture helper.
    """
    if engine.url.database != "altvia_test":
        raise ValueError("Legacy fixtures require the disposable test database")
    ticket_id = UUID(identifier.rsplit("/", 1)[-1]) if isinstance(identifier, str) else identifier
    params = {"id": ticket_id}
    with engine.begin() as connection:
        rows = list(
            connection.execute(
                text(
                    "SELECT cycle_number,policy_id,state FROM ticket_sla_states WHERE ticket_id=:id"
                ),
                params,
            )
        )
        assert rows == [(1, None, "unconfigured")]
        for table in ("ticket_sla_goals", "ticket_sla_acceptances", "ticket_sla_events"):
            assert (
                connection.scalar(text(f"SELECT count(*) FROM {table} WHERE ticket_id=:id"), params)
                == 0
            )
        removed = connection.execute(
            text("DELETE FROM ticket_sla_states WHERE ticket_id=:id"), params
        )
        assert removed.rowcount == 1
