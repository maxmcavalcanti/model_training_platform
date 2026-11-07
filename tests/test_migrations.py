"""Tests for the Alembic migrations (plan 06). The round trip covers every future migration."""

from __future__ import annotations

import re

import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from ingestion.db import build_engine
from tests.conftest import alembic_config

EXPECTED_SCHEMAS = {"raw", "ref", "features", "predictions", "monitoring"}


def _existing_schemas(url: str) -> set[str]:
    engine = build_engine(url)
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT schema_name FROM information_schema.schemata"))
        names = {row[0] for row in rows}
    engine.dispose()
    return names & EXPECTED_SCHEMAS


def _current_revision(url: str) -> str | None:
    engine = build_engine(url)
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
    engine.dispose()
    return revision


@pytest.mark.db
def test_upgrade_head_creates_the_five_schemas(migrated_database):
    assert _existing_schemas(migrated_database) == EXPECTED_SCHEMAS


@pytest.mark.db
def test_upgrade_downgrade_upgrade_round_trip(fresh_database, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    config = alembic_config()

    command.upgrade(config, "head")
    assert _existing_schemas(fresh_database) == EXPECTED_SCHEMAS

    command.downgrade(config, "base")
    assert _existing_schemas(fresh_database) == set()

    command.upgrade(config, "head")
    assert _existing_schemas(fresh_database) == EXPECTED_SCHEMAS


@pytest.mark.db
def test_upgrade_head_twice_is_a_no_op(fresh_database, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    config = alembic_config()

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    head = ScriptDirectory.from_config(config).get_current_head()
    assert _current_revision(fresh_database) == head
    assert _existing_schemas(fresh_database) == EXPECTED_SCHEMAS


@pytest.mark.db
def test_upgrade_without_database_url_fails_mentioning_database_url(fresh_database, monkeypatch):
    monkeypatch.delenv("DATABASE_URL_ADMIN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(Exception, match="DATABASE_URL"):
        command.upgrade(alembic_config(), "head")


def test_revisions_have_four_digit_ids_and_a_single_head():
    script = ScriptDirectory.from_config(alembic_config())

    revision_ids = [revision.revision for revision in script.walk_revisions()]

    assert revision_ids, "expected at least one revision in migrations/versions"
    assert all(re.fullmatch(r"\d{4}", revision_id) for revision_id in revision_ids)
    assert len(script.get_heads()) == 1
