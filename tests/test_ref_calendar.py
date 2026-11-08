"""Tests for table ``ref.calendar`` (plan 19, cases 16 to 22).

Reads use the shared ``migrated_database`` (read-only). Writes and the downgrade run on a
``fresh_database`` migrated to ``head`` by the ``calendar_database`` fixture.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from ingestion.db import build_engine
from tests.conftest import alembic_config

pytestmark = pytest.mark.db

INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
UNIQUE_VIOLATION = "23505"

INSERT = (
    "INSERT INTO ref.calendar (date, weekday, is_national_holiday, holiday_name) "
    "VALUES (:date, :weekday, :is_national_holiday, :holiday_name)"
)
COMMON_MONDAY = {
    "date": dt.date(2026, 11, 9),
    "weekday": 1,
    "is_national_holiday": False,
    "holiday_name": None,
}


def _query(url: str, statement: str, role: str | None = None) -> list[tuple]:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            if role is not None:
                connection.execute(text(f"SET ROLE {role}"))
            return [tuple(row) for row in connection.execute(text(statement))]
    finally:
        engine.dispose()


def _execute(url: str, statement: str, params: dict | None = None, role: str | None = None) -> None:
    """Run ``statement`` (optionally as ``role``) on its own connection and commit."""
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            if role is not None:
                connection.execute(text(f"SET ROLE {role}"))
            connection.execute(text(statement), params or {})
            connection.commit()
    finally:
        engine.dispose()


def _insert_expecting_integrity_error(url: str, row: dict) -> IntegrityError:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            with pytest.raises(IntegrityError) as error_info:
                connection.execute(text(INSERT), row)
            return error_info.value
    finally:
        engine.dispose()


def _assert_denied(url: str, role: str, statement: str, params: dict | None = None) -> None:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text(f"SET ROLE {role}"))
            with pytest.raises(ProgrammingError) as error_info:
                connection.execute(text(statement), params or {})
            assert error_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE
    finally:
        engine.dispose()


def _table_exists(url: str, qualified_name: str) -> bool:
    return _query(url, f"SELECT to_regclass('{qualified_name}') IS NOT NULL") == [(True,)]


@pytest.fixture
def calendar_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database


# Case 16
def test_columns_types_primary_key_and_empty_table(migrated_database):
    columns = _query(
        migrated_database,
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'ref' AND table_name = 'calendar' ORDER BY column_name",
    )
    primary_key = _query(
        migrated_database,
        "SELECT a.attname FROM pg_index i "
        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = to_regclass('ref.calendar') AND i.indisprimary",
    )

    assert columns == [
        ("date", "date", "NO"),
        ("holiday_name", "text", "YES"),
        ("is_national_holiday", "boolean", "NO"),
        ("weekday", "smallint", "NO"),
    ]
    assert primary_key == [("date",)]
    assert _query(migrated_database, "SELECT count(*) FROM ref.calendar") == [(0,)]


# Case 17
def test_weekday_that_does_not_match_the_date_is_rejected(calendar_database):
    error = _insert_expecting_integrity_error(calendar_database, {**COMMON_MONDAY, "weekday": 2})

    assert error.orig.sqlstate == CHECK_VIOLATION
    assert error.orig.diag.constraint_name == "calendar_weekday_isodow"


def test_weekday_that_matches_the_date_is_accepted(calendar_database):
    _execute(calendar_database, INSERT, COMMON_MONDAY)

    assert _query(
        calendar_database,
        "SELECT date, weekday, is_national_holiday, holiday_name FROM ref.calendar",
    ) == [(dt.date(2026, 11, 9), 1, False, None)]


# Case 18
@pytest.mark.parametrize(
    ("is_national_holiday", "holiday_name"),
    [(True, None), (True, ""), (False, "Natal")],
)
def test_holiday_flag_and_name_must_be_consistent(
    calendar_database, is_national_holiday, holiday_name
):
    row = {
        **COMMON_MONDAY,
        "is_national_holiday": is_national_holiday,
        "holiday_name": holiday_name,
    }

    error = _insert_expecting_integrity_error(calendar_database, row)

    assert error.orig.sqlstate == CHECK_VIOLATION
    assert error.orig.diag.constraint_name == "calendar_holiday_name_consistency"


# Case 19
@pytest.mark.parametrize("column", ["date", "weekday", "is_national_holiday"])
def test_null_in_required_column_is_rejected(calendar_database, column):
    error = _insert_expecting_integrity_error(calendar_database, {**COMMON_MONDAY, column: None})

    assert error.orig.sqlstate == NOT_NULL_VIOLATION


def test_duplicate_date_is_rejected(calendar_database):
    _execute(calendar_database, INSERT, COMMON_MONDAY)

    error = _insert_expecting_integrity_error(calendar_database, COMMON_MONDAY)

    assert error.orig.sqlstate == UNIQUE_VIOLATION


# Case 20
def test_ingestor_inserts_and_updates_but_cannot_delete(calendar_database):
    _execute(calendar_database, INSERT, COMMON_MONDAY, role="ingestor")
    assert _query(calendar_database, "SELECT count(*) FROM ref.calendar") == [(1,)]

    _execute(
        calendar_database,
        "UPDATE ref.calendar SET is_national_holiday = true, holiday_name = 'Test' "
        "WHERE date = '2026-11-09'",
        role="ingestor",
    )
    assert _query(calendar_database, "SELECT holiday_name FROM ref.calendar") == [("Test",)]

    _assert_denied(calendar_database, "ingestor", "DELETE FROM ref.calendar")


# Case 21
@pytest.mark.parametrize("role", ["reader", "scientist", "scorer"])
def test_read_only_roles_select_but_cannot_insert(calendar_database, role):
    assert _query(calendar_database, "SELECT count(*) FROM ref.calendar", role=role) == [(0,)]

    _assert_denied(calendar_database, role, INSERT, COMMON_MONDAY)


# Case 22
def test_downgrade_to_0004_drops_only_the_table_and_upgrade_recreates_it(calendar_database):
    config = alembic_config()
    assert _table_exists(calendar_database, "ref.calendar")

    command.downgrade(config, "0004")

    assert not _table_exists(calendar_database, "ref.calendar")
    assert _table_exists(calendar_database, "ref.locations")
    assert _table_exists(calendar_database, "raw.weather_forecast")

    command.upgrade(config, "head")

    assert _table_exists(calendar_database, "ref.calendar")
    assert _query(calendar_database, "SELECT count(*) FROM ref.calendar") == [(0,)]
