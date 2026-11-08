"""Tests for table ``raw.weather_forecast`` (plan 13, migration 0004).

Reads and catalog checks use the shared ``migrated_database`` (read-only). Writes, ``upsert``
and the downgrade run on a ``fresh_database`` migrated to ``head`` by ``forecast_database``.
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
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"
GENERATED_ALWAYS_VIOLATION = "428C9"

TABLE = "raw.weather_forecast"
KEYS = ["location_id", "issued_at", "target_date"]
ISSUED = dt.date(2026, 11, 7)
INSERT = (
    "INSERT INTO raw.weather_forecast (location_id, issued_at, target_date, temp_max, temp_min, "
    "precip_mm, wind_speed_max, humidity_mean, ingested_at) "
    "VALUES (:location_id, :issued_at, :target_date, :temp_max, :temp_min, :precip_mm, "
    ":wind_speed_max, :humidity_mean, now())"
)
BASE_ROW = {
    "location_id": "sao_paulo",
    "issued_at": ISSUED,
    "target_date": dt.date(2026, 11, 10),
    "temp_max": 31.5,
    "temp_min": 19.0,
    "precip_mm": 2.4,
    "wind_speed_max": 18.0,
    "humidity_mean": 72.0,
}
WEATHER_COLUMNS = ["temp_max", "temp_min", "precip_mm", "wind_speed_max", "humidity_mean"]


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


def _table_exists(url: str) -> bool:
    return _query(url, "SELECT to_regclass('raw.weather_forecast') IS NOT NULL") == [(True,)]


def _has_privilege(url: str, role: str, privilege: str, table: str = TABLE) -> bool:
    return _query(url, f"SELECT has_table_privilege('{role}', '{table}', '{privilege}')") == [
        (True,)
    ]


def _frame(rows: list[tuple[dt.date, float]]) -> pd.DataFrame:
    """Job-shaped frame: no ``horizon_days`` and no ``ingested_at``."""
    return pd.DataFrame(
        [
            ("sao_paulo", ISSUED, target_date, temp_max, 19.0, 2.4, 18.0, 72.0)
            for target_date, temp_max in rows
        ],
        columns=["location_id", "issued_at", "target_date", *WEATHER_COLUMNS],
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


@pytest.fixture
def forecast_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database


@pytest.fixture
def stored_snapshot(forecast_database) -> str:
    """``forecast_database`` with the two rows of case 17 written by the ingestor."""
    frame = _frame([(dt.date(2026, 11, 8), 30.0), (dt.date(2026, 11, 9), 31.0)])
    _upsert_as(forecast_database, "ingestor", frame, "ignore")
    return forecast_database


# Case 1
def test_columns_types_and_nullability(migrated_database):
    columns = _query(
        migrated_database,
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 'weather_forecast' ORDER BY column_name",
    )

    assert columns == [
        ("horizon_days", "smallint", "NO"),
        ("humidity_mean", "double precision", "YES"),
        ("ingested_at", "timestamp with time zone", "NO"),
        ("issued_at", "date", "NO"),
        ("location_id", "text", "NO"),
        ("precip_mm", "double precision", "YES"),
        ("target_date", "date", "NO"),
        ("temp_max", "double precision", "YES"),
        ("temp_min", "double precision", "YES"),
        ("wind_speed_max", "double precision", "YES"),
    ]


# Case 2
def test_only_horizon_days_is_generated(migrated_database):
    generated = _query(
        migrated_database,
        "SELECT column_name, is_generated FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 'weather_forecast' ORDER BY column_name",
    )

    assert generated
    assert {name: flag for name, flag in generated} == {
        "horizon_days": "ALWAYS",
        "humidity_mean": "NEVER",
        "ingested_at": "NEVER",
        "issued_at": "NEVER",
        "location_id": "NEVER",
        "precip_mm": "NEVER",
        "target_date": "NEVER",
        "temp_max": "NEVER",
        "temp_min": "NEVER",
        "wind_speed_max": "NEVER",
    }


# Case 3
def test_primary_key_is_named_and_covers_location_issue_and_target(migrated_database):
    primary_key = _query(
        migrated_database,
        "SELECT c.conname, a.attname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
        "WHERE c.conrelid = to_regclass('raw.weather_forecast') AND c.contype = 'p' "
        "ORDER BY a.attname",
    )

    assert primary_key == [
        ("weather_forecast_pkey", "issued_at"),
        ("weather_forecast_pkey", "location_id"),
        ("weather_forecast_pkey", "target_date"),
    ]


# Case 4
def test_comments_document_timezone_and_update_exception(migrated_database):
    issued_at_comment = _query(
        migrated_database,
        "SELECT col_description(to_regclass('raw.weather_forecast'), a.attnum) "
        "FROM pg_attribute a WHERE a.attrelid = to_regclass('raw.weather_forecast') "
        "AND a.attname = 'issued_at'",
    )
    table_comment = _query(
        migrated_database, "SELECT obj_description(to_regclass('raw.weather_forecast'), 'pg_class')"
    )

    assert issued_at_comment[0][0] is not None
    assert "America/Sao_Paulo" in issued_at_comment[0][0]
    assert table_comment[0][0] is not None
    assert "UPDATE" in table_comment[0][0]


# Case 5
def test_table_starts_empty(migrated_database):
    assert _query(migrated_database, "SELECT count(*) FROM raw.weather_forecast") == [(0,)]


# Case 6
@pytest.mark.parametrize(
    ("privilege", "expected"),
    [
        ("SELECT", True),
        ("INSERT", True),
        ("UPDATE", False),
        ("DELETE", False),
        ("TRUNCATE", False),
    ],
)
def test_ingestor_privileges_on_the_table(migrated_database, privilege, expected):
    assert _has_privilege(migrated_database, "ingestor", privilege) is expected


# Case 7
def test_update_exception_is_limited_to_this_table(migrated_database):
    assert _has_privilege(migrated_database, "ingestor", "UPDATE", table="ref.locations")


# Case 8
def test_horizon_days_is_generated_from_the_dates(forecast_database):
    _execute(forecast_database, INSERT, BASE_ROW)

    assert _query(forecast_database, "SELECT horizon_days FROM raw.weather_forecast") == [(3,)]


# Case 9
def test_horizons_one_and_seven_are_accepted(forecast_database):
    _execute(forecast_database, INSERT, {**BASE_ROW, "target_date": ISSUED + dt.timedelta(days=1)})
    _execute(forecast_database, INSERT, {**BASE_ROW, "target_date": ISSUED + dt.timedelta(days=7)})

    assert _query(
        forecast_database, "SELECT horizon_days FROM raw.weather_forecast ORDER BY horizon_days"
    ) == [(1,), (7,)]


# Case 10
@pytest.mark.parametrize("offset_days", [0, -1, 8])
def test_horizon_outside_one_to_seven_is_rejected(forecast_database, offset_days):
    row = {**BASE_ROW, "target_date": ISSUED + dt.timedelta(days=offset_days)}

    error = _insert_expecting_error(forecast_database, row)

    assert error.orig.sqlstate == CHECK_VIOLATION
    assert error.orig.diag.constraint_name == "weather_forecast_horizon_days_range"


# Case 11
def test_duplicate_key_is_rejected(forecast_database):
    _execute(forecast_database, INSERT, BASE_ROW)

    error = _insert_expecting_error(forecast_database, BASE_ROW)

    assert error.orig.sqlstate == UNIQUE_VIOLATION


# Case 12
def test_same_target_date_issued_on_different_days_coexists(forecast_database):
    target_date = dt.date(2026, 11, 10)
    for issued_at in (dt.date(2026, 11, 7), dt.date(2026, 11, 8)):
        _execute(
            forecast_database,
            INSERT,
            {**BASE_ROW, "issued_at": issued_at, "target_date": target_date},
        )

    assert _query(
        forecast_database,
        "SELECT issued_at, horizon_days FROM raw.weather_forecast ORDER BY issued_at",
    ) == [(dt.date(2026, 11, 7), 3), (dt.date(2026, 11, 8), 2)]


# Case 13
def test_unknown_location_is_rejected_by_foreign_key(forecast_database):
    error = _insert_expecting_error(
        forecast_database, {**BASE_ROW, "location_id": "does_not_exist"}
    )

    assert error.orig.sqlstate == FOREIGN_KEY_VIOLATION
    assert error.orig.diag.constraint_name == "weather_forecast_location_id_fkey"


# Case 14
def test_explicit_horizon_days_is_rejected(forecast_database):
    statement = INSERT.replace("(location_id,", "(horizon_days, location_id,").replace(
        "VALUES (", "VALUES (3, "
    )

    error = _insert_expecting_error(
        forecast_database, BASE_ROW, statement=statement, error_type=DBAPIError
    )

    assert error.orig.sqlstate == GENERATED_ALWAYS_VIOLATION


# Case 15
@pytest.mark.parametrize("column", ["location_id", "issued_at", "target_date", "ingested_at"])
def test_null_in_required_column_is_rejected(forecast_database, column):
    if column == "ingested_at":
        statement = INSERT.replace(
            ":wind_speed_max, :humidity_mean, now())", ":wind_speed_max, :humidity_mean, NULL)"
        )
        row = BASE_ROW
    else:
        statement = INSERT
        row = {**BASE_ROW, column: None}

    error = _insert_expecting_error(forecast_database, row, statement=statement)

    assert error.orig.sqlstate == NOT_NULL_VIOLATION


# Case 16
def test_weather_variables_accept_null(forecast_database):
    _execute(forecast_database, INSERT, {**BASE_ROW, **{name: None for name in WEATHER_COLUMNS}})

    assert _query(
        forecast_database, "SELECT count(*) FROM raw.weather_forecast WHERE temp_max IS NULL"
    ) == [(1,)]


# Case 17
def test_ingestor_upsert_ignore_keeps_the_first_snapshot(forecast_database):
    first = _frame([(dt.date(2026, 11, 8), 30.0), (dt.date(2026, 11, 9), 31.0)])
    second = _frame([(dt.date(2026, 11, 8), 99.0), (dt.date(2026, 11, 9), 99.0)])
    select = (
        "SELECT target_date, horizon_days, temp_max, ingested_at FROM raw.weather_forecast "
        "ORDER BY target_date"
    )

    assert _upsert_as(forecast_database, "ingestor", first, "ignore") == 2
    after_first = _query(forecast_database, select)
    assert [(row[0], row[1], row[2]) for row in after_first] == [
        (dt.date(2026, 11, 8), 1, 30.0),
        (dt.date(2026, 11, 9), 2, 31.0),
    ]
    assert all(row[3] is not None for row in after_first)

    assert _upsert_as(forecast_database, "ingestor", second, "ignore") == 0
    assert _query(forecast_database, select) == after_first


# Case 18
def test_ingestor_upsert_update_is_denied_and_row_is_kept(stored_snapshot):
    select = (
        "SELECT target_date, temp_max, ingested_at FROM raw.weather_forecast ORDER BY target_date"
    )
    before = _query(stored_snapshot, select)
    changed = _frame([(dt.date(2026, 11, 8), 99.0)])

    with pytest.raises(DBAPIError) as error_info:
        _upsert_as(stored_snapshot, "ingestor", changed, "update")

    assert error_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE
    assert _query(stored_snapshot, select) == before


# Case 19
def test_ingestor_inserts_but_cannot_update_delete_or_truncate(forecast_database):
    _execute(forecast_database, INSERT, BASE_ROW, role="ingestor")
    assert _query(forecast_database, "SELECT count(*) FROM raw.weather_forecast") == [(1,)]

    _assert_denied(forecast_database, "ingestor", "UPDATE raw.weather_forecast SET temp_max = 30.0")
    _assert_denied(forecast_database, "ingestor", "DELETE FROM raw.weather_forecast")
    _assert_denied(forecast_database, "ingestor", "TRUNCATE raw.weather_forecast")

    assert _query(forecast_database, "SELECT temp_max FROM raw.weather_forecast") == [(31.5,)]


# Case 20
def test_admin_can_still_correct_a_snapshot(forecast_database):
    _execute(forecast_database, INSERT, BASE_ROW)

    _execute(forecast_database, "UPDATE raw.weather_forecast SET temp_max = 30.0")

    assert _query(forecast_database, "SELECT temp_max FROM raw.weather_forecast") == [(30.0,)]


# Case 21
@pytest.mark.parametrize("role", ["scientist", "scorer", "reader"])
def test_read_only_roles_select_but_cannot_insert_or_update(forecast_database, role):
    _execute(forecast_database, INSERT, BASE_ROW)

    assert _query(forecast_database, "SELECT count(*) FROM raw.weather_forecast", role=role) == [
        (1,)
    ]
    _assert_denied(
        forecast_database,
        role,
        INSERT,
        {**BASE_ROW, "target_date": dt.date(2026, 11, 11)},
    )
    _assert_denied(forecast_database, role, "UPDATE raw.weather_forecast SET temp_max = 30.0")


# Case 22
def test_downgrade_to_0003_drops_the_table_and_upgrade_recreates_it(forecast_database):
    config = alembic_config()
    assert _table_exists(forecast_database)

    command.downgrade(config, "0003")

    assert not _table_exists(forecast_database)
    assert _query(forecast_database, "SELECT count(*) FROM ref.locations") == [(4,)]

    command.upgrade(config, "head")

    assert _table_exists(forecast_database)
    assert _query(forecast_database, "SELECT count(*) FROM raw.weather_forecast") == [(0,)]
    assert _has_privilege(forecast_database, "ingestor", "INSERT")
    assert not _has_privilege(forecast_database, "ingestor", "UPDATE")
