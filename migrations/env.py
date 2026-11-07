import os
from logging.config import fileConfig

from alembic import context

from ingestion.db import build_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = None


def run_migrations_online() -> None:
    engine = build_engine(os.environ.get("DATABASE_URL_ADMIN") or os.environ.get("DATABASE_URL"))
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
