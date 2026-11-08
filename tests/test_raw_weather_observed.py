"""Tests for table ``raw.weather_observed`` (plan 25, migration 0007).

Unlike ``raw.weather_forecast``, the ``ingestor`` keeps ``UPDATE`` here: the daily job rewrites
the recent window with ``on_conflict="update"`` because recent ERA5 values may change.

Reads and catalog checks use the shared ``migrated_database`` (read-only). Writes, ``upsert``
and the downgrades run on a ``fresh_database`` migrated to ``head`` by ``observed_database``.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pandas as pd
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from ingestion.db import build_engine, upsert
from tests.conftest import alembic_config

pytestmark = pytest.mark.db

INSUFFICIENT_PRIVILEGE = "42501"
NOT_NULL_VIOLATION = "23502"
UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"

TABLE = "raw.weather_observed"
KEYS = ["location_id", "date"]
DAY = dt.date(2026, 11, 5)
NEXT_DAY = dt.date(2026, 11, 6)
INSERT = (
    'INSERT INTO raw.weather_observed (location_id, "date", temp_max, temp_min, precip_mm, '
    "wind_speed_max, humidity_mean, ingested_at) "
    "VALUES (:location_id, :date, :temp_max, :temp_min, :precip_mm, :wind_speed_max, "
    ":humidity_mean, now())"
)
BASE_ROW = {
    "location_id": "recife",
    "date": DAY,
    "temp_max": 30.5,
    "temp_min": 24.0,
    "precip_mm": 3.2,
    "wind_speed_max": 22.0,
    "humidity_mean": 78.0,
}
WEATHER_COLUMNS = ["temp_max", "temp_min", "precip_mm", "wind_speed_max", "humidity_mean"]
LOCATIONS = ["sao_paulo", "porto_alegre", "recife", "belem"]
SELECT_VALUES = 'SELECT "date", precip_mm, ingested_at FROM raw.weather_observed ORDER BY "date"'


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


def _insert_expecting_error(
    url: str, row: dict, statement: str = INSERT, error_type: type[DBAPIError] = IntegrityError
) -> DBAPIError:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            with pytest.raises(error_type) as error_info:
                connection.execute(text(statement), row)
            return error_info.value
    finally:
        engine.dispose()


def _assert_denied(url: str, role: str, statement: str, params: dict | None = None) -> None:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text(f"SET ROLE {role}"))
            with pytest.raises(DBAPIError) as error_info:
                connection.execute(text(statement), params or {})
            assert error_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE
    finally:
        engine.dispose()


def _table_exists(url: str, table: str = TABLE) -> bool:
    return _query(url, f"SELECT to_regclass('{table}') IS NOT NULL") == [(True,)]


def _has_privilege(url: str, role: str, privilege: str, table: str = TABLE) -> bool:
    return _query(url, f"SELECT has_table_privilege('{role}', '{table}', '{privilege}')") == [
        (True,)
    ]


def _frame(rows: list[tuple[dt.date, float, float]]) -> pd.DataFrame:
    """Job-shaped frame (``date``, ``precip_mm``, ``humidity_mean`` vary): no ``ingested_at``."""
    return pd.DataFrame(
        [("recife", day, 30.5, 24.0, precip, 22.0, humidity) for day, precip, humidity in rows],
        columns=["location_id", "date", *WEATHER_COLUMNS],
    )


def _upsert_as(url: str, role: str, frame: pd.DataFrame, on_conflict: str) -> int:
    """Run ``upsert`` as ``role`` in its own transaction and commit."""
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text(f"SET ROLE {role}"))
            written = upsert(connection, TABLE, frame, keys=KEYS, on_conflict=on_conflict)
            connection.commit()
            return written
    finally:
        engine.dispose()


def _comments(url: str) -> dict[str, str | None]:
    """Table comment under ``"<table>"`` and column comments by column name."""
    rows = _query(
        url,
        "SELECT a.attname, col_description(a.attrelid, a.attnum) FROM pg_attribute a "
        "WHERE a.attrelid = to_regclass('raw.weather_observed') AND a.attnum > 0 "
        "AND NOT a.attisdropped",
    )
    comments = {name: comment for name, comment in rows}
    table = _query(url, "SELECT obj_description(to_regclass('raw.weather_observed'), 'pg_class')")
    comments["<table>"] = table[0][0]
    return comments


@pytest.fixture
def observed_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database


@pytest.fixture
def stored_rows(observed_database) -> str:
    """``observed_database`` with the two rows of case 16 written by the ingestor."""
    frame = _frame([(DAY, 3.2, 78.0), (NEXT_DAY, 3.2, 80.0)])
    _upsert_as(observed_database, "ingestor", frame, "update")
    return observed_database


# Case 1
def test_columns_types_and_nullability(migrated_database):
    columns = _query(
        migrated_database,
        "SELECT column_name, data_type, is_nullable, is_generated FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 'weather_observed' ORDER BY column_name",
    )

    assert columns == [
        ("date", "date", "NO", "NEVER"),
        ("humidity_mean", "double precision", "YES", "NEVER"),
        ("ingested_at", "timestamp with time zone", "NO", "NEVER"),
        ("location_id", "text", "NO", "NEVER"),
        ("precip_mm", "double precision", "YES", "NEVER"),
        ("temp_max", "double precision", "YES", "NEVER"),
        ("temp_min", "double precision", "YES", "NEVER"),
        ("wind_speed_max", "double precision", "YES", "NEVER"),
    ]


# Case 2
@pytest.mark.parametrize("column", WEATHER_COLUMNS)
def test_weather_variables_match_the_forecast_table(migrated_database, column):
    statement = (
        "SELECT data_type, is_nullable FROM information_schema.columns "
        f"WHERE table_schema = 'raw' AND table_name = '{{table}}' AND column_name = '{column}'"
    )

    observed = _query(migrated_database, statement.format(table="weather_observed"))
    forecast = _query(migrated_database, statement.format(table="weather_forecast"))

    assert observed
    assert observed == forecast


# Case 3
def test_constraints_are_named_primary_key_and_foreign_key_only(migrated_database):
    constraints = _query(
        migrated_database,
        "SELECT conname, contype FROM pg_constraint "
        "WHERE conrelid = to_regclass('raw.weather_observed') ORDER BY conname",
    )
    primary_key = _query(
        migrated_database,
        "SELECT a.attname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
        "WHERE c.conrelid = to_regclass('raw.weather_observed') AND c.contype = 'p' "
        "ORDER BY a.attname",
    )
    foreign_key = _query(
        migrated_database,
        "SELECT a.attname, c.confrelid::regclass::text, fa.attname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
        "JOIN pg_attribute fa ON fa.attrelid = c.confrelid AND fa.attnum = ANY(c.confkey) "
        "WHERE c.conrelid = to_regclass('raw.weather_observed') AND c.contype = 'f'",
    )

    assert constraints == [
        ("weather_observed_location_id_fkey", "f"),
        ("weather_observed_pkey", "p"),
    ]
    assert primary_key == [("date",), ("location_id",)]
    assert foreign_key == [("location_id", "ref.locations", "location_id")]


# Case 4
@pytest.mark.parametrize(
    ("name", "fragments"),
    [
        ("<table>", ["ERA5", "UPDATE"]),
        ("date", ["America/Sao_Paulo"]),
        ("temp_max", ["degrees Celsius"]),
        ("temp_min", ["degrees Celsius"]),
        ("precip_mm", ["mm"]),
        ("wind_speed_max", ["km/h"]),
        ("humidity_mean", ["percent"]),
        ("ingested_at", ["last write"]),
    ],
)
def test_comments_document_source_units_and_timezone(migrated_database, name, fragments):
    comment = _comments(migrated_database).get(name)

    assert comment is not None
    for fragment in fragments:
        assert fragment in comment


# Case 5
def test_table_starts_empty(migrated_database):
    assert _query(migrated_database, "SELECT count(*) FROM raw.weather_observed") == [(0,)]


# Case 6
@pytest.mark.parametrize(
    ("privilege", "expected"),
    [
        ("SELECT", True),
        ("INSERT", True),
        ("UPDATE", True),
        ("DELETE", False),
        ("TRUNCATE", False),
    ],
)
def test_ingestor_privileges_on_the_table(migrated_database, privilege, expected):
    assert _has_privilege(migrated_database, "ingestor", privilege) is expected


# Case 7
@pytest.mark.parametrize("role", ["scientist", "scorer", "reader"])
@pytest.mark.parametrize(
    ("privilege", "expected"), [("SELECT", True), ("INSERT", False), ("UPDATE", False)]
)
def test_other_roles_only_read(migrated_database, role, privilege, expected):
    assert _has_privilege(migrated_database, role, privilege) is expected


# Case 8
def test_base_row_is_accepted_and_read_back(observed_database):
    _execute(observed_database, INSERT, BASE_ROW)

    rows = _query(
        observed_database,
        'SELECT location_id, "date", temp_max, temp_min, precip_mm, wind_speed_max, '
        "humidity_mean, ingested_at FROM raw.weather_observed",
    )

    assert len(rows) == 1
    assert rows[0][:7] == (
        "recife",
        DAY,
        30.5,
        24.0,
        3.2,
        22.0,
        78.0,
    )
    assert rows[0][7] is not None


# Case 9
def test_four_locations_and_two_dates_coexist(observed_database):
    for location in LOCATIONS:
        _execute(observed_database, INSERT, {**BASE_ROW, "location_id": location})
    _execute(observed_database, INSERT, {**BASE_ROW, "date": NEXT_DAY})

    assert _query(observed_database, "SELECT count(*) FROM raw.weather_observed") == [(5,)]


# Case 10
def test_duplicate_key_is_rejected(observed_database):
    _execute(observed_database, INSERT, BASE_ROW)

    error = _insert_expecting_error(observed_database, BASE_ROW)

    assert error.orig.sqlstate == UNIQUE_VIOLATION


# Case 11
def test_unknown_location_is_rejected_by_foreign_key(observed_database):
    error = _insert_expecting_error(
        observed_database, {**BASE_ROW, "location_id": "does_not_exist"}
    )

    assert error.orig.sqlstate == FOREIGN_KEY_VIOLATION
    assert error.orig.diag.constraint_name == "weather_observed_location_id_fkey"


# Case 12
@pytest.mark.parametrize("column", ["location_id", "date", "ingested_at"])
def test_null_in_required_column_is_rejected(observed_database, column):
    if column == "ingested_at":
        statement = INSERT.replace(":humidity_mean, now())", ":humidity_mean, NULL)")
        row = BASE_ROW
    else:
        statement = INSERT
        row = {**BASE_ROW, column: None}

    error = _insert_expecting_error(observed_database, row, statement=statement)

    assert error.orig.sqlstate == NOT_NULL_VIOLATION


# Case 13
@pytest.mark.parametrize(
    "nulled", [WEATHER_COLUMNS, ["humidity_mean"]], ids=["all_variables", "only_humidity"]
)
def test_weather_variables_accept_null(observed_database, nulled):
    _execute(observed_database, INSERT, {**BASE_ROW, **{name: None for name in nulled}})

    assert _query(observed_database, "SELECT count(*) FROM raw.weather_observed") == [(1,)]
    assert _query(observed_database, "SELECT humidity_mean FROM raw.weather_observed") == [(None,)]


# Case 14
def test_values_outside_plausible_range_are_accepted(observed_database):
    row = {
        **BASE_ROW,
        "temp_min": 35.0,
        "temp_max": 20.0,
        "humidity_mean": 120.0,
        "precip_mm": -1.0,
    }

    _execute(observed_database, INSERT, row)

    assert _query(
        observed_database, "SELECT temp_min, temp_max, humidity_mean, precip_mm FROM " + TABLE
    ) == [(35.0, 20.0, 120.0, -1.0)]


# Case 15
def test_foreign_key_protects_history_from_location_delete(observed_database):
    _execute(observed_database, INSERT, BASE_ROW)

    error = _insert_expecting_error(
        observed_database,
        {},
        statement="DELETE FROM ref.locations WHERE location_id = 'recife'",
    )

    assert error.orig.sqlstate == FOREIGN_KEY_VIOLATION
    assert _query(observed_database, "SELECT count(*) FROM ref.locations") == [(4,)]
    assert _query(observed_database, "SELECT count(*) FROM raw.weather_observed") == [(1,)]


# Case 16
def test_ingestor_upsert_update_writes_rows_with_ingested_at(observed_database):
    frame = _frame([(DAY, 3.2, 78.0), (NEXT_DAY, 3.2, 80.0)])

    assert _upsert_as(observed_database, "ingestor", frame, "update") == 2

    rows = _query(observed_database, SELECT_VALUES)
    assert [(row[0], row[1]) for row in rows] == [(DAY, 3.2), (NEXT_DAY, 3.2)]
    assert all(row[2] is not None for row in rows)


# Case 17
def test_ingestor_upsert_update_rewrites_changed_rows(stored_rows):
    before = _query(stored_rows, SELECT_VALUES)
    revised = _frame([(DAY, 3.2, 78.0), (NEXT_DAY, 5.0, 80.0)])

    _upsert_as(stored_rows, "ingestor", revised, "update")

    after = _query(stored_rows, SELECT_VALUES)
    assert [(row[0], row[1]) for row in after] == [(DAY, 3.2), (NEXT_DAY, 5.0)]
    assert len(after) == 2
    assert all(new[2] > old[2] for new, old in zip(after, before, strict=True))


# Case 18
def test_repeated_identical_upsert_is_idempotent(stored_rows):
    same = _frame([(DAY, 3.2, 78.0), (NEXT_DAY, 3.2, 80.0)])

    _upsert_as(stored_rows, "ingestor", same, "update")

    assert [(row[0], row[1]) for row in _query(stored_rows, SELECT_VALUES)] == [
        (DAY, 3.2),
        (NEXT_DAY, 3.2),
    ]


# Case 19
def test_upsert_stores_nan_as_null(observed_database):
    frame = _frame([(DAY, 3.2, float("nan"))])

    _upsert_as(observed_database, "ingestor", frame, "update")

    assert _query(observed_database, "SELECT humidity_mean FROM raw.weather_observed") == [(None,)]


# Case 20
def test_ingestor_inserts_and_updates_but_cannot_delete_or_truncate(observed_database):
    _execute(observed_database, INSERT, BASE_ROW, role="ingestor")
    assert _query(observed_database, "SELECT count(*) FROM raw.weather_observed") == [(1,)]

    _execute(observed_database, "UPDATE raw.weather_observed SET precip_mm = 0.0", role="ingestor")
    assert _query(observed_database, "SELECT precip_mm FROM raw.weather_observed") == [(0.0,)]

    _assert_denied(observed_database, "ingestor", "DELETE FROM raw.weather_observed")
    _assert_denied(observed_database, "ingestor", "TRUNCATE raw.weather_observed")

    assert _query(observed_database, "SELECT count(*) FROM raw.weather_observed") == [(1,)]


# Case 21
@pytest.mark.parametrize("role", ["scientist", "scorer", "reader"])
def test_read_only_roles_select_but_cannot_insert_or_update(observed_database, role):
    _execute(observed_database, INSERT, BASE_ROW)

    assert _query(observed_database, "SELECT count(*) FROM raw.weather_observed", role=role) == [
        (1,)
    ]
    _assert_denied(observed_database, role, INSERT, {**BASE_ROW, "date": NEXT_DAY})
    _assert_denied(observed_database, role, "UPDATE raw.weather_observed SET precip_mm = 0.0")


# Case 22
def test_downgrade_to_0006_drops_the_table_and_upgrade_recreates_it(observed_database):
    config = alembic_config()
    assert _table_exists(observed_database)

    command.downgrade(config, "0006")

    assert not _table_exists(observed_database)
    for table in ("raw.ons_daily_load", "ref.calendar", "raw.weather_forecast", "ref.locations"):
        assert _table_exists(observed_database, table)
    assert _query(observed_database, "SELECT count(*) FROM ref.locations") == [(4,)]

    command.upgrade(config, "head")

    assert _table_exists(observed_database)
    assert _query(observed_database, "SELECT count(*) FROM raw.weather_observed") == [(0,)]
    assert _has_privilege(observed_database, "ingestor", "UPDATE")
    assert _has_privilege(observed_database, "reader", "SELECT")
    assert not _has_privilege(observed_database, "reader", "INSERT")
    assert _query(
        observed_database,
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = to_regclass('raw.weather_observed') AND contype = 'f'",
    ) == [("weather_observed_location_id_fkey",)]


# Case 23
def test_downgrade_to_0002_with_a_stored_row_drops_both_tables(observed_database):
    _execute(observed_database, INSERT, BASE_ROW)

    command.downgrade(alembic_config(), "0002")

    assert not _table_exists(observed_database)
    assert not _table_exists(observed_database, "ref.locations")
