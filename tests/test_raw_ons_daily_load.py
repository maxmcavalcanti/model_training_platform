"""Tests for table ``raw.ons_daily_load`` (plan 21, migration 0006).

Reads and catalog checks use the shared ``migrated_database`` (read-only). Writes, ``upsert``
and the downgrade run on a ``fresh_database`` migrated to ``head`` by ``load_database``.
Unlike ``raw.weather_forecast``, the ingestor keeps UPDATE here: ONS revises published days.
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

TABLE = "raw.ons_daily_load"
KEYS = ["subsystem", "date"]
DAY = dt.date(2026, 11, 5)
INSERT = (
    'INSERT INTO raw.ons_daily_load (subsystem, "date", load_avg_mw, ingested_at) '
    "VALUES (:subsystem, :date, :load_avg_mw, now())"
)
BASE_ROW = {"subsystem": "SE", "date": DAY, "load_avg_mw": 40000.0}
SELECT_ALL = (
    'SELECT subsystem, "date", load_avg_mw, ingested_at FROM raw.ons_daily_load ORDER BY subsystem'
)


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
    return _query(url, "SELECT to_regclass('raw.ons_daily_load') IS NOT NULL") == [(True,)]


def _has_privilege(url: str, role: str, privilege: str, table: str = TABLE) -> bool:
    return _query(url, f"SELECT has_table_privilege('{role}', '{table}', '{privilege}')") == [
        (True,)
    ]


def _frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    """Job-shaped frame: only ``subsystem``, ``date`` and ``load_avg_mw``."""
    return pd.DataFrame(
        [(subsystem, DAY, load) for subsystem, load in rows],
        columns=["subsystem", "date", "load_avg_mw"],
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
def load_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database


# Case 1
def test_columns_types_and_nullability(migrated_database):
    columns = _query(
        migrated_database,
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 'ons_daily_load' ORDER BY column_name",
    )

    assert columns == [
        ("date", "date", "NO"),
        ("ingested_at", "timestamp with time zone", "NO"),
        ("load_avg_mw", "double precision", "NO"),
        ("subsystem", "text", "NO"),
    ]


# Case 2
def test_primary_key_is_named_and_covers_subsystem_and_date(migrated_database):
    primary_key = _query(
        migrated_database,
        "SELECT c.conname, a.attname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
        "WHERE c.conrelid = to_regclass('raw.ons_daily_load') AND c.contype = 'p' "
        "ORDER BY a.attname",
    )

    assert primary_key == [
        ("ons_daily_load_pkey", "date"),
        ("ons_daily_load_pkey", "subsystem"),
    ]


# Case 3
def test_table_starts_empty(migrated_database):
    assert _query(migrated_database, "SELECT count(*) FROM raw.ons_daily_load") == [(0,)]


# Case 4
def test_comments_document_units_codes_and_update(migrated_database):
    table_comment = _query(
        migrated_database, "SELECT obj_description(to_regclass('raw.ons_daily_load'), 'pg_class')"
    )
    column_comments = dict(
        _query(
            migrated_database,
            "SELECT a.attname, col_description(a.attrelid, a.attnum) FROM pg_attribute a "
            "WHERE a.attrelid = to_regclass('raw.ons_daily_load') AND a.attnum > 0 "
            "AND NOT a.attisdropped",
        )
    )

    assert table_comment[0][0] is not None
    assert "UPDATE" in table_comment[0][0]
    assert column_comments["load_avg_mw"] is not None
    assert "MWmed" in column_comments["load_avg_mw"]
    assert column_comments["subsystem"] is not None
    assert "Sudeste/Centro-Oeste" in column_comments["subsystem"]
    assert column_comments["ingested_at"] is not None
    assert "last write" in column_comments["ingested_at"]


# Case 5
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


# Case 6
@pytest.mark.parametrize("role", ["scientist", "scorer", "reader"])
@pytest.mark.parametrize(
    ("privilege", "expected"), [("SELECT", True), ("INSERT", False), ("UPDATE", False)]
)
def test_read_only_roles_privileges_on_the_table(migrated_database, role, privilege, expected):
    assert _has_privilege(migrated_database, role, privilege) is expected


# Case 7
def test_baseline_row_is_accepted_and_read_back(load_database):
    _execute(load_database, INSERT, BASE_ROW)

    rows = _query(load_database, SELECT_ALL)

    assert [(row[0], row[1], row[2]) for row in rows] == [("SE", DAY, 40000.0)]
    assert rows[0][3] is not None


# Case 8
def test_the_four_subsystem_codes_are_accepted_on_the_same_date(load_database):
    for code in ("SE", "S", "NE", "N"):
        _execute(load_database, INSERT, {**BASE_ROW, "subsystem": code})

    assert _query(load_database, "SELECT subsystem FROM raw.ons_daily_load ORDER BY subsystem") == [
        ("N",),
        ("NE",),
        ("S",),
        ("SE",),
    ]


# Case 9
def test_same_subsystem_on_different_dates_and_same_date_on_different_subsystems_coexist(
    load_database,
):
    _execute(load_database, INSERT, BASE_ROW)
    _execute(load_database, INSERT, {**BASE_ROW, "date": dt.date(2026, 11, 6)})
    _execute(load_database, INSERT, {**BASE_ROW, "subsystem": "S"})

    assert _query(load_database, "SELECT count(*) FROM raw.ons_daily_load") == [(3,)]


# Case 10
def test_duplicate_key_is_rejected(load_database):
    _execute(load_database, INSERT, BASE_ROW)

    error = _insert_expecting_error(load_database, BASE_ROW)

    assert error.orig.sqlstate == UNIQUE_VIOLATION


# Case 11
@pytest.mark.parametrize("subsystem", ["SIN", "SE/CO", "se", ""])
def test_unknown_subsystem_code_is_rejected(load_database, subsystem):
    error = _insert_expecting_error(load_database, {**BASE_ROW, "subsystem": subsystem})

    assert error.orig.sqlstate == CHECK_VIOLATION
    assert error.orig.diag.constraint_name == "ons_daily_load_subsystem_code"


# Case 12
@pytest.mark.parametrize("column", ["subsystem", "date", "load_avg_mw", "ingested_at"])
def test_null_in_any_column_is_rejected(load_database, column):
    if column == "ingested_at":
        statement = INSERT.replace(":load_avg_mw, now())", ":load_avg_mw, NULL)")
        row = BASE_ROW
    else:
        statement = INSERT
        row = {**BASE_ROW, column: None}

    error = _insert_expecting_error(load_database, row, statement=statement)

    assert error.orig.sqlstate == NOT_NULL_VIOLATION


# Case 13
def test_zero_and_negative_load_are_accepted_by_the_database(load_database):
    _execute(load_database, INSERT, {**BASE_ROW, "load_avg_mw": 0.0})
    _execute(load_database, INSERT, {**BASE_ROW, "subsystem": "S", "load_avg_mw": -1.0})

    assert _query(
        load_database, "SELECT subsystem, load_avg_mw FROM raw.ons_daily_load ORDER BY subsystem"
    ) == [("S", -1.0), ("SE", 0.0)]


# Case 14
def test_ingestor_upsert_update_writes_rows_and_stamps_ingested_at(load_database):
    frame = _frame([("SE", 40000.0), ("S", 12000.0)])

    assert _upsert_as(load_database, "ingestor", frame, "update") == 2

    rows = _query(load_database, SELECT_ALL)
    assert [(row[0], row[2]) for row in rows] == [("S", 12000.0), ("SE", 40000.0)]
    assert all(row[3] is not None for row in rows)


# Case 15
def test_ons_revision_overwrites_the_value_and_advances_ingested_at(load_database):
    first = _frame([("SE", 40000.0), ("S", 12000.0)])
    revised = _frame([("SE", 40500.0), ("S", 12000.0)])
    _upsert_as(load_database, "ingestor", first, "update")
    after_first = {row[0]: row for row in _query(load_database, SELECT_ALL)}

    _upsert_as(load_database, "ingestor", revised, "update")

    after_revision = {row[0]: row for row in _query(load_database, SELECT_ALL)}
    assert len(after_revision) == 2
    assert after_revision["SE"][2] == 40500.0
    assert after_revision["S"][2] == 12000.0
    for subsystem in ("SE", "S"):
        assert after_revision[subsystem][3] > after_first[subsystem][3]


# Case 16
def test_repeating_the_same_upsert_is_idempotent(load_database):
    frame = _frame([("SE", 40000.0), ("S", 12000.0)])

    _upsert_as(load_database, "ingestor", frame, "update")
    _upsert_as(load_database, "ingestor", frame, "update")

    rows = _query(load_database, SELECT_ALL)
    assert [(row[0], row[2]) for row in rows] == [("S", 12000.0), ("SE", 40000.0)]


# Case 17
def test_ingestor_inserts_and_updates_but_cannot_delete_or_truncate(load_database):
    _execute(load_database, INSERT, BASE_ROW, role="ingestor")
    assert _query(load_database, "SELECT count(*) FROM raw.ons_daily_load") == [(1,)]

    _execute(load_database, "UPDATE raw.ons_daily_load SET load_avg_mw = 41000.0", role="ingestor")
    assert _query(load_database, "SELECT load_avg_mw FROM raw.ons_daily_load") == [(41000.0,)]

    _assert_denied(load_database, "ingestor", "DELETE FROM raw.ons_daily_load")
    _assert_denied(load_database, "ingestor", "TRUNCATE raw.ons_daily_load")

    assert _query(load_database, "SELECT count(*) FROM raw.ons_daily_load") == [(1,)]


# Case 18
@pytest.mark.parametrize("role", ["scientist", "scorer", "reader"])
def test_read_only_roles_select_but_cannot_insert_or_update(load_database, role):
    _execute(load_database, INSERT, BASE_ROW)

    assert _query(load_database, "SELECT count(*) FROM raw.ons_daily_load", role=role) == [(1,)]
    _assert_denied(load_database, role, INSERT, {**BASE_ROW, "subsystem": "S"})
    _assert_denied(load_database, role, "UPDATE raw.ons_daily_load SET load_avg_mw = 1.0")


# Case 19
def test_downgrade_to_0005_drops_the_table_and_upgrade_recreates_it(load_database):
    config = alembic_config()
    assert _table_exists(load_database)

    command.downgrade(config, "0005")

    assert not _table_exists(load_database)
    assert _query(load_database, "SELECT to_regclass('ref.calendar') IS NOT NULL") == [(True,)]
    assert _query(load_database, "SELECT count(*) FROM ref.locations") == [(4,)]
    assert _query(load_database, "SELECT to_regclass('raw.weather_forecast') IS NOT NULL") == [
        (True,)
    ]

    command.upgrade(config, "head")

    assert _table_exists(load_database)
    assert _query(load_database, "SELECT count(*) FROM raw.ons_daily_load") == [(0,)]
    assert _has_privilege(load_database, "ingestor", "UPDATE")
