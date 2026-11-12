from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase

from altvia.config import DatabaseSettings


class Base(DeclarativeBase):
    pass


def make_engine(settings: DatabaseSettings, *, worker_timeouts: bool = False) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            **(
                {"options": "-c statement_timeout=5000 -c lock_timeout=3000"}
                if worker_timeouts
                else {}
            ),
        },
    )
