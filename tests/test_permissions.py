"""Tests for the Postgres roles and per-schema permissions (plan 07).

Each test acts as a role through ``SET ROLE`` on a database migrated to ``head`` where the admin
created table ``x`` afterwards, which exercises the default privileges.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator

import psycopg
import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from ingestion.db import build_engine
from tests.conftest import alembic_config

ROLES = ("ingestor", "scientist", "scorer", "reader")
SCHEMAS = ("raw", "ref", "features", "predictions", "monitoring")
LOCKED_SCHEMAS = ("raw", "ref", "predictions", "monitoring")
INSUFFICIENT_PRIVILEGE = "42501"


def _execute_as(url: str, role: str, statement: str) -> None:
    """Run ``statement`` as ``role`` on its own connection and commit."""
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text(f"SET ROLE {role}"))
            connection.execute(text(statement))
            connection.commit()
    finally:
        engine.dispose()


def _assert_denied(url: str, role: str, statement: str) -> None:
    """Assert ``statement`` fails for ``role`` with permission denied (SQLSTATE 42501)."""
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text(f"SET ROLE {role}"))
            with pytest.raises(ProgrammingError) as error_info:
                connection.execute(text(statement))
            assert error_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE
    finally:
        engine.dispose()


def _admin_query(url: str, statement: str) -> list[tuple]:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(statement))]
    finally:
        engine.dispose()


def _psycopg_dsn(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.fixture
def permissions_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database at ``head`` where the admin then created ``x`` in the locked schemas."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    engine = build_engine(fresh_database)
    try:
        with engine.begin() as connection:
            for schema in LOCKED_SCHEMAS:
                connection.execute(text(f"CREATE TABLE {schema}.x (id int PRIMARY KEY)"))
    finally:
        engine.dispose()
    yield fresh_database


# Case 1
@pytest.mark.db
@pytest.mark.parametrize("schema", ["raw", "ref"])
def test_ingestor_inserts_and_updates_in_raw_and_ref(permissions_database, schema):
    _execute_as(permissions_database, "ingestor", f"INSERT INTO {schema}.x (id) VALUES (1)")
    _execute_as(permissions_database, "ingestor", f"UPDATE {schema}.x SET id = 2 WHERE id = 1")


@pytest.mark.db
@pytest.mark.parametrize("schema", ["raw", "ref"])
def test_ingestor_upsert_works_in_raw_and_ref(permissions_database, schema):
    upsert = f"INSERT INTO {schema}.x (id) VALUES (1) ON CONFLICT (id) DO UPDATE SET id = 1"

    _execute_as(permissions_database, "ingestor", upsert)
    _execute_as(permissions_database, "ingestor", upsert)


@pytest.mark.db
def test_ingestor_cannot_insert_into_predictions(permissions_database):
    _assert_denied(permissions_database, "ingestor", "INSERT INTO predictions.x (id) VALUES (1)")


# Case 2
@pytest.mark.db
def test_ingestor_cannot_delete_from_raw(permissions_database):
    _assert_denied(permissions_database, "ingestor", "DELETE FROM raw.x")


# Case 3
@pytest.mark.db
@pytest.mark.parametrize("schema", ["predictions", "monitoring"])
def test_scorer_inserts_into_predictions_and_monitoring(permissions_database, schema):
    _execute_as(permissions_database, "scorer", f"INSERT INTO {schema}.x (id) VALUES (1)")


@pytest.mark.db
def test_scorer_cannot_insert_into_raw(permissions_database):
    _assert_denied(permissions_database, "scorer", "INSERT INTO raw.x (id) VALUES (1)")


# Case 4
@pytest.mark.db
@pytest.mark.parametrize("schema", LOCKED_SCHEMAS)
def test_reader_selects_everywhere(permissions_database, schema):
    _execute_as(permissions_database, "reader", f"SELECT * FROM {schema}.x")


@pytest.mark.db
@pytest.mark.parametrize("schema", LOCKED_SCHEMAS)
def test_reader_cannot_insert(permissions_database, schema):
    _assert_denied(permissions_database, "reader", f"INSERT INTO {schema}.x (id) VALUES (1)")


# Case 5
@pytest.mark.db
def test_scientist_creates_table_in_features_and_others_can_read_it(permissions_database):
    _execute_as(permissions_database, "scientist", "CREATE TABLE features.mine (id int)")

    _execute_as(permissions_database, "reader", "SELECT * FROM features.mine")
    _execute_as(permissions_database, "scorer", "SELECT * FROM features.mine")


# Case 6
@pytest.mark.db
def test_scientist_cannot_create_table_in_raw(permissions_database):
    _assert_denied(permissions_database, "scientist", "CREATE TABLE raw.y (id int)")


@pytest.mark.db
def test_scientist_cannot_insert_into_raw(permissions_database):
    _assert_denied(permissions_database, "scientist", "INSERT INTO raw.x (id) VALUES (1)")


@pytest.mark.db
def test_scientist_selects_from_raw(permissions_database):
    _execute_as(permissions_database, "scientist", "SELECT * FROM raw.x")


# Case 7
@pytest.mark.db
@pytest.mark.parametrize("schema", LOCKED_SCHEMAS)
@pytest.mark.parametrize("role", ROLES)
def test_no_role_can_create_table_in_locked_schemas(permissions_database, role, schema):
    _assert_denied(permissions_database, role, f"CREATE TABLE {schema}.z (id int)")


# Case 8
@pytest.mark.db
def test_upgrade_head_succeeds_when_roles_already_exist(
    migrated_database, fresh_database, monkeypatch
):
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    config = alembic_config()

    command.upgrade(config, "head")

    engine = build_engine(fresh_database)
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
    assert current == ScriptDirectory.from_config(config).get_current_head()


# Case 9
@pytest.mark.db
def test_roles_exist_with_login_and_no_elevated_attributes(migrated_database):
    rows = _admin_query(
        migrated_database,
        "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
        "WHERE rolname IN ('ingestor', 'scientist', 'scorer', 'reader')",
    )

    assert {row[0]: row[1:] for row in rows} == {
        role: (True, False, False, False) for role in ROLES
    }


# Case 10
@pytest.mark.db
def test_upgrade_keeps_a_password_already_set_on_a_role(
    migrated_database, fresh_database, monkeypatch
):
    password = secrets.token_hex(16)
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    with psycopg.connect(_psycopg_dsn(fresh_database), autocommit=True) as connection:
        connection.execute(sql.SQL("ALTER ROLE ingestor PASSWORD {}").format(sql.Literal(password)))
        try:
            command.upgrade(alembic_config(), "head")

            row = connection.execute(
                "SELECT rolpassword FROM pg_authid WHERE rolname = 'ingestor'"
            ).fetchone()
            assert row is not None
            assert row[0] is not None
        finally:
            connection.execute("ALTER ROLE ingestor PASSWORD NULL")


# Case 11
@pytest.mark.db
def test_downgrade_to_0001_revokes_everything_but_keeps_the_roles(fresh_database, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    config = alembic_config()
    command.upgrade(config, "head")

    command.downgrade(config, "0001")

    existing = _admin_query(
        fresh_database,
        "SELECT rolname FROM pg_roles "
        "WHERE rolname IN ('ingestor', 'scientist', 'scorer', 'reader')",
    )
    assert {row[0] for row in existing} == set(ROLES)
    for role in ROLES:
        for schema in SCHEMAS:
            granted = _admin_query(
                fresh_database,
                f"SELECT has_schema_privilege('{role}', '{schema}', 'USAGE')",
            )
            assert granted == [(False,)], f"{role} still has USAGE on {schema}"
    assert _admin_query(fresh_database, "SELECT count(*) FROM pg_default_acl") == [(0,)]
