"""Argument validation of ``upsert`` (hardening follow-ups plan H1, cases 3 to 6).

No database: the connection is a double that fails on any attribute access, so these tests prove
that invalid ``keys`` and ``on_conflict`` are rejected before the database is touched.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from ingestion.db import upsert

TABLE = "raw.upsert_test"


class ConnectionDouble:
    """Records every attribute access and fails if the connection is used."""

    def __init__(self) -> None:
        self.accesses: list[str] = []

    def __getattr__(self, name: str):
        self.accesses.append(name)
        raise AssertionError(f"connection used: {name}")


def _rows() -> pd.DataFrame:
    return pd.DataFrame({"k1": ["a", "b"], "k2": [dt.date(2024, 1, 1)] * 2, "value": [1.0, 2.0]})


def _empty_rows() -> pd.DataFrame:
    return _rows().iloc[0:0]


# H1 case 3
def test_empty_keys_with_rows_raises_before_touching_the_connection():
    conn = ConnectionDouble()

    with pytest.raises(ValueError, match="keys"):
        upsert(conn, TABLE, _rows(), [])

    assert conn.accesses == []


# H1 case 4
def test_empty_keys_with_empty_frame_raises_instead_of_returning_zero():
    conn = ConnectionDouble()

    with pytest.raises(ValueError, match="keys"):
        upsert(conn, TABLE, _empty_rows(), [])

    assert conn.accesses == []


# H1 case 5
@pytest.mark.parametrize("on_conflict", ["replace", "UPDATE", "", None])
def test_invalid_on_conflict_with_rows_raises_before_touching_the_connection(on_conflict):
    conn = ConnectionDouble()

    with pytest.raises(ValueError, match="on_conflict") as error_info:
        upsert(conn, TABLE, _rows(), ["k1", "k2"], on_conflict=on_conflict)

    assert repr(on_conflict) in str(error_info.value)
    assert conn.accesses == []


# H1 case 6
def test_invalid_on_conflict_with_empty_frame_raises():
    conn = ConnectionDouble()

    with pytest.raises(ValueError, match="on_conflict"):
        upsert(conn, TABLE, _empty_rows(), ["k1", "k2"], on_conflict="replace")

    assert conn.accesses == []
