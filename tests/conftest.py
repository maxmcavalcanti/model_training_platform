"""Shared fixtures for db-marked tests.

``temp_database_url`` gives a session-wide throwaway Postgres database,
``fresh_database`` an empty one per test and ``migrated_database`` one per session at ``head``.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

DEFAULT_DATABASE_URL_TEST = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres"
UNAVAILABLE_MESSAGE = (
    "Test Postgres unavailable: run docker compose -f infra/docker-compose.dev.yml up -d"
)
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@contextmanager
def _throwaway_database() -> Iterator[str]:
    """Create ``ml_test_<8 hex>``, yield its URL, drop it on exit.

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


def alembic_config() -> Config:
    """Alembic config with absolute paths, independent of the current directory."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    return config


@pytest.fixture(scope="session")
def temp_database_url() -> Iterator[str]:
    """Create ``ml_test_<8 hex>`` once per session, yield its URL, drop it at the end."""
    with _throwaway_database() as url:
        yield url


@pytest.fixture
def fresh_database() -> Iterator[str]:
    """Empty ``ml_test_<8 hex>`` database for one test; dropped at teardown."""
    with _throwaway_database() as url:
        yield url


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    """``ml_test_<8 hex>`` database at Alembic ``head``, shared by the session. Read-only use."""
    with _throwaway_database() as url:
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setenv("DATABASE_URL_ADMIN", url)
            command.upgrade(alembic_config(), "head")
        yield url
