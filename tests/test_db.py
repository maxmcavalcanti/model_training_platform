"""Tests for ``ingestion.db.build_engine`` and the ``temp_database_url`` fixture (plan 05)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

# Database name seen by the first test of case 5, compared by the second one.
_seen_database_names: list[str] = []


def test_build_engine_without_url_or_environment_raises_missing_configuration(monkeypatch):
    from ingestion.db import MissingConfiguration, build_engine

    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(MissingConfiguration, match="DATABASE_URL"):
        build_engine()


def test_build_engine_explicit_url_takes_precedence_over_environment(monkeypatch):
    from ingestion.db import build_engine

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://env_user:p@env-host/env_db")

    engine = build_engine("postgresql+psycopg://arg_user:p@arg-host/arg_db")

    assert engine.url.host == "arg-host"
    assert engine.url.database == "arg_db"
    engine.dispose()


def test_build_engine_reads_database_url_from_environment(monkeypatch):
    from ingestion.db import build_engine

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://env_user:p@env-host/env_db")

    engine = build_engine()

    assert engine.url.host == "env-host"
    engine.dispose()


def test_build_engine_normalizes_plain_postgresql_scheme_to_psycopg():
    from ingestion.db import build_engine

    engine = build_engine("postgresql://u:p@h/db")

    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.host == "h"
    assert engine.url.database == "db"
    engine.dispose()


@pytest.mark.db
def test_temp_database_runs_postgres_16_or_newer(temp_database_url):
    from ingestion.db import build_engine

    engine = build_engine(temp_database_url)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT current_setting('server_version_num')::int"))
        assert version.scalar_one() >= 160000
    engine.dispose()


@pytest.mark.db
def test_temp_database_name_has_ml_test_prefix(temp_database_url):
    database_name = make_url(temp_database_url).database
    assert database_name.startswith("ml_test_")
    _seen_database_names.append(database_name)


@pytest.mark.db
def test_temp_database_is_shared_within_the_session(temp_database_url):
    assert _seen_database_names, "depends on the previous test, which records the name"
    assert make_url(temp_database_url).database == _seen_database_names[0]
