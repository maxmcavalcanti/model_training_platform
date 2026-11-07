"""Shared fixtures. ``temp_database_url`` gives db-marked tests a throwaway Postgres database."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

DEFAULT_DATABASE_URL_TEST = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres"
UNAVAILABLE_MESSAGE = (
    "Test Postgres unavailable: run docker compose -f infra/docker-compose.dev.yml up -d"
)


@pytest.fixture(scope="session")
def temp_database_url() -> Iterator[str]:
    """Create ``ml_test_<8 hex>`` once per session, yield its URL, drop it at the end.

    Fails (never skips) when the server does not answer.
    """
    admin_url = make_url(os.environ.get("DATABASE_URL_TEST", DEFAULT_DATABASE_URL_TEST))
    database_name = f"ml_test_{secrets.token_hex(4)}"
    admin_engine = create_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5}
    )
    try:
        try:
            with admin_engine.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        except OperationalError:
            pytest.fail(UNAVAILABLE_MESSAGE, pytrace=False)
        try:
            yield admin_url.set(database=database_name).render_as_string(hide_password=False)
        finally:
            with admin_engine.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
    finally:
        admin_engine.dispose()
