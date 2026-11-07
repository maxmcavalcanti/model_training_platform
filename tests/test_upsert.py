"""Tests for the idempotent ``upsert`` function (plan 08).

Tables ``raw.upsert_test`` and ``raw.upsert_test_unstamped`` are created by the admin after
``upgrade head`` so the default privileges of the roles apply to them.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import numpy as np
import pandas as pd
import pytest
from alembic import command
from sqlalchemy import text

from ingestion.db import build_engine, upsert
from tests.conftest import alembic_config

pytestmark = pytest.mark.db

TABLE = "raw.upsert_test"
UNSTAMPED_TABLE = "raw.upsert_test_unstamped"
KEYS = ["k1", "k2"]
DAY_1 = dt.date(2024, 1, 1)
DAY_2 = dt.date(2024, 1, 2)
DAY_3 = dt.date(2024, 1, 3)


@pytest.fixture
def upsert_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Database at ``head`` with the two upsert test tables created by the admin."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    engine = build_engine(fresh_database)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE raw.upsert_test ("
                    "k1 text, k2 date, value double precision, "
                    "ingested_at timestamptz NOT NULL, PRIMARY KEY (k1, k2))"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE raw.upsert_test_unstamped ("
                    "k1 text PRIMARY KEY, value double precision)"
                )
            )
    finally:
        engine.dispose()
    yield fresh_database


@pytest.fixture
def engine(upsert_database):
    engine = build_engine(upsert_database)
    yield engine
    engine.dispose()


def _frame(rows: list[tuple[str, dt.date, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["k1", "k2", "value"])


def _select(engine, statement: str) -> list[tuple]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(statement))]


def _count(engine, table: str = TABLE) -> int:
    return _select(engine, f"SELECT count(*) FROM {table}")[0][0]


def _three_rows() -> pd.DataFrame:
    return _frame([("a", DAY_1, 1.0), ("b", DAY_1, 2.0), ("c", DAY_1, 3.0)])


def test_inserts_new_rows_with_server_stamp(engine):
    with engine.begin() as conn:
        returned = upsert(conn, TABLE, _three_rows(), KEYS)

    assert returned == 3
    assert _count(engine) == 3
    assert _select(engine, f"SELECT count(*) FROM {TABLE} WHERE ingested_at IS NULL")[0][0] == 0


def test_same_upsert_twice_does_not_duplicate(engine):
    with engine.begin() as conn:
        upsert(conn, TABLE, _three_rows(), KEYS)
    with engine.begin() as conn:
        second = upsert(conn, TABLE, _three_rows(), KEYS)

    assert _count(engine) == 3
    assert second == 3


def test_update_overwrites_value_and_advances_ingested_at(engine):
    with engine.begin() as conn:
        upsert(conn, TABLE, _frame([("a", DAY_1, 1.0)]), KEYS)
    first = _select(engine, f"SELECT value, ingested_at FROM {TABLE}")[0]

    with engine.begin() as conn:
        upsert(conn, TABLE, _frame([("a", DAY_1, 9.0)]), KEYS)
    second = _select(engine, f"SELECT value, ingested_at FROM {TABLE}")[0]

    assert first[0] == 1.0
    assert second[0] == 9.0
    assert second[1] > first[1]


def test_ignore_preserves_existing_row_and_returns_zero(engine):
    with engine.begin() as conn:
        upsert(conn, TABLE, _frame([("a", DAY_1, 1.0)]), KEYS)
    first = _select(engine, f"SELECT value, ingested_at FROM {TABLE}")[0]

    with engine.begin() as conn:
        returned = upsert(conn, TABLE, _frame([("a", DAY_1, 9.0)]), KEYS, on_conflict="ignore")
    second = _select(engine, f"SELECT value, ingested_at FROM {TABLE}")[0]

    assert returned == 0
    assert second == first
    assert second[0] == 1.0


def test_ignore_mixed_load_inserts_only_the_new_key(engine):
    with engine.begin() as conn:
        upsert(conn, TABLE, _frame([("a", DAY_1, 1.0)]), KEYS)

    with engine.begin() as conn:
        returned = upsert(
            conn,
            TABLE,
            _frame([("a", DAY_1, 9.0), ("b", DAY_1, 2.0)]),
            KEYS,
            on_conflict="ignore",
        )

    assert returned == 1
    assert _select(engine, f"SELECT k1, value FROM {TABLE} ORDER BY k1") == [
        ("a", 1.0),
        ("b", 2.0),
    ]


@pytest.mark.parametrize(
    "value_column",
    [
        pd.Series([np.nan, 5.0], dtype="float64"),
        pd.Series([pd.NA, 5.0], dtype="Float64"),
    ],
    ids=["nan_float64", "na_nullable_float64"],
)
def test_missing_values_become_null(engine, value_column):
    rows = pd.DataFrame({"k1": ["a", "b"], "k2": [DAY_1, DAY_1], "value": value_column})

    with engine.begin() as conn:
        upsert(conn, TABLE, rows, KEYS)

    assert _select(engine, f"SELECT k1, value FROM {TABLE} ORDER BY k1") == [
        ("a", None),
        ("b", 5.0),
    ]


def test_empty_dataframe_returns_zero_and_leaves_table_unchanged(engine):
    with engine.begin() as conn:
        returned = upsert(conn, TABLE, _frame([]), KEYS)

    assert returned == 0
    assert _count(engine) == 0


def test_unknown_column_raises_and_writes_nothing(engine):
    rows = _three_rows().assign(nonexistent=1)

    with pytest.raises(ValueError, match="nonexistent"):
        with engine.begin() as conn:
            upsert(conn, TABLE, rows, KEYS)

    assert _count(engine) == 0


def test_missing_key_column_raises(engine):
    rows = _three_rows().drop(columns=["k2"])

    with pytest.raises(ValueError, match="k2"):
        with engine.begin() as conn:
            upsert(conn, TABLE, rows, KEYS)

    assert _count(engine) == 0


def test_ingested_at_in_dataframe_raises_when_stamping(engine):
    rows = _three_rows().assign(ingested_at=pd.Timestamp("2020-01-01", tz="UTC"))

    with pytest.raises(ValueError, match="ingested_at"):
        with engine.begin() as conn:
            upsert(conn, TABLE, rows, KEYS)

    assert _count(engine) == 0


@pytest.mark.parametrize("on_conflict", ["update", "ignore"])
def test_duplicate_key_inside_dataframe_raises(engine, on_conflict):
    rows = _frame([("a", DAY_1, 1.0), ("a", DAY_1, 2.0)])

    with pytest.raises(ValueError, match="duplicate"):
        with engine.begin() as conn:
            upsert(conn, TABLE, rows, KEYS, on_conflict=on_conflict)

    assert _count(engine) == 0


def test_table_without_schema_raises(engine):
    with pytest.raises(ValueError):
        with engine.begin() as conn:
            upsert(conn, "upsert_test", _three_rows(), KEYS)


def test_many_rows_span_several_batches(engine):
    rows = pd.DataFrame(
        {
            "k1": [f"key{index}" for index in range(12_000)],
            "k2": [DAY_1] * 12_000,
            "value": [float(index) for index in range(12_000)],
        }
    )

    with engine.begin() as conn:
        returned = upsert(conn, TABLE, rows, KEYS)

    assert returned == 12_000
    assert _count(engine) == 12_000


def test_exception_after_upsert_rolls_back(engine):
    with pytest.raises(RuntimeError, match="boom"):
        with engine.begin() as conn:
            upsert(conn, TABLE, _three_rows(), KEYS)
            raise RuntimeError("boom")

    assert _count(engine) == 0


def test_works_under_ingestor_role(engine):
    with engine.begin() as conn:
        conn.execute(text("SET ROLE ingestor"))
        upsert(conn, TABLE, _frame([("a", DAY_1, 1.0)]), KEYS)
    with engine.begin() as conn:
        conn.execute(text("SET ROLE ingestor"))
        upsert(conn, TABLE, _frame([("a", DAY_1, 7.0)]), KEYS)

    assert _select(engine, f"SELECT value FROM {TABLE}") == [(7.0,)]


def test_unstamped_table_updates_without_ingested_at(engine):
    first = pd.DataFrame({"k1": ["a"], "value": [1.0]})
    second = pd.DataFrame({"k1": ["a"], "value": [2.0]})

    with engine.begin() as conn:
        first_returned = upsert(conn, UNSTAMPED_TABLE, first, ["k1"], stamp_ingested_at=False)
    with engine.begin() as conn:
        second_returned = upsert(conn, UNSTAMPED_TABLE, second, ["k1"], stamp_ingested_at=False)

    assert first_returned == 1
    assert second_returned == 1
    assert _select(engine, f"SELECT k1, value FROM {UNSTAMPED_TABLE}") == [("a", 2.0)]


def test_stamping_a_table_without_ingested_at_raises(engine):
    rows = pd.DataFrame({"k1": ["a"], "value": [1.0]})

    with pytest.raises(ValueError, match="ingested_at"):
        with engine.begin() as conn:
            upsert(conn, UNSTAMPED_TABLE, rows, ["k1"])

    assert _count(engine, UNSTAMPED_TABLE) == 0


def test_only_key_columns_behaves_like_ignore(engine):
    with engine.begin() as conn:
        upsert(
            conn,
            UNSTAMPED_TABLE,
            pd.DataFrame({"k1": ["a"], "value": [1.0]}),
            ["k1"],
            stamp_ingested_at=False,
        )

    with engine.begin() as conn:
        returned = upsert(
            conn,
            UNSTAMPED_TABLE,
            pd.DataFrame({"k1": ["a"]}),
            ["k1"],
            on_conflict="update",
            stamp_ingested_at=False,
        )

    assert returned == 0
    assert _select(engine, f"SELECT k1, value FROM {UNSTAMPED_TABLE}") == [("a", 1.0)]
