from alembic import context
from altvia import models  # noqa: F401
from altvia.config import Settings
from altvia.database import Base, make_engine

config = context.config
engine = make_engine(Settings())
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
