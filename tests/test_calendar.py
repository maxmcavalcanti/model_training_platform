"""Tests for ``build_calendar``, ``CALENDAR_SCHEMA``, ``load_calendar`` and the CLI (plan 19).

Cases 1 to 15 and 28 need no database. Cases 23 to 27 and 29 carry the ``db`` marker: the job
runs as the ``ingestor`` role against a migrated ``fresh_database``. No test touches the network.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pandas as pd
import pytest
from alembic import command
from sqlalchemy import create_engine, text

from ingestion.calendar_ref import build_calendar
from ingestion.checks import CALENDAR_SCHEMA, CheckFailed, check
from ingestion.db import build_engine
from ingestion.jobs import load_calendar
from tests.conftest import alembic_config

COLUMNS = ["date", "weekday", "is_national_holiday", "holiday_name"]
HOLIDAYS_2026 = [
    dt.date(2026, 1, 1),
    dt.date(2026, 4, 3),
    dt.date(2026, 4, 21),
    dt.date(2026, 5, 1),
    dt.date(2026, 9, 7),
    dt.date(2026, 10, 12),
    dt.date(2026, 11, 2),
    dt.date(2026, 11, 15),
    dt.date(2026, 11, 20),
    dt.date(2026, 12, 25),
]
NEW_YEAR_NAME = "Confraternização Universal"
BLACK_CONSCIOUSNESS_NAME = "Dia Nacional de Zumbi e da Consciência Negra"
CHRISTMAS_NAME = "Natal"
FULL_RANGE_START = dt.date(2015, 1, 1)
FULL_RANGE_END = dt.date(2030, 12, 31)
FULL_RANGE_DAYS = 5844
FULL_RANGE_HOLIDAYS = 151
SELECT_ALL = (
    "SELECT date, weekday, is_national_holiday, holiday_name FROM ref.calendar ORDER BY date"
)


def _row(df: pd.DataFrame, day: dt.date) -> pd.Series:
    matches = df[df["date"] == day]
    assert len(matches) == 1
    return matches.iloc[0]


def _year_2026() -> pd.DataFrame:
    return build_calendar(dt.date(2026, 1, 1), dt.date(2026, 12, 31))


# ---------------------------------------------------------------------------
# build_calendar (no database)
# ---------------------------------------------------------------------------


# Case 1
def test_year_has_one_row_per_day_with_exact_columns():
    df = _year_2026()

    assert list(df.columns) == COLUMNS
    assert len(df) == 365
    expected = [dt.date(2026, 1, 1) + dt.timedelta(days=n) for n in range(365)]
    assert list(df["date"]) == expected


# Case 2
def test_leap_year_has_366_rows():
    assert len(build_calendar(dt.date(2024, 1, 1), dt.date(2024, 12, 31))) == 366


def test_single_day_range_has_one_row():
    assert len(build_calendar(dt.date(2026, 3, 10), dt.date(2026, 3, 10))) == 1


# Case 3
def test_start_after_end_raises_value_error_naming_both_dates():
    with pytest.raises(ValueError, match=r"2026-02-01.*2026-01-31|2026-01-31.*2026-02-01"):
        build_calendar(dt.date(2026, 2, 1), dt.date(2026, 1, 31))


# Case 4
def test_2026_national_holidays_are_exactly_the_ten_expected_dates():
    df = _year_2026()

    assert list(df.loc[df["is_national_holiday"], "date"]) == HOLIDAYS_2026


# Case 5
def test_new_years_day_is_a_thursday_holiday_with_its_name():
    row = _row(_year_2026(), dt.date(2026, 1, 1))

    assert bool(row["is_national_holiday"]) is True
    assert row["weekday"] == 4
    assert row["holiday_name"] == NEW_YEAR_NAME


# Case 6
def test_black_consciousness_day_2026_is_a_friday_holiday():
    row = _row(_year_2026(), dt.date(2026, 11, 20))

    assert bool(row["is_national_holiday"]) is True
    assert row["weekday"] == 5
    assert row["holiday_name"] == BLACK_CONSCIOUSNESS_NAME


def test_republic_day_2026_is_a_sunday_holiday():
    row = _row(_year_2026(), dt.date(2026, 11, 15))

    assert bool(row["is_national_holiday"]) is True
    assert row["weekday"] == 7


# Case 7
def test_black_consciousness_day_was_not_national_in_2023():
    df = build_calendar(dt.date(2023, 11, 1), dt.date(2023, 11, 30))

    assert bool(_row(df, dt.date(2023, 11, 20))["is_national_holiday"]) is False


# Case 8
@pytest.mark.parametrize(
    "day",
    [
        dt.date(2026, 2, 16),
        dt.date(2026, 2, 17),
        dt.date(2026, 2, 18),
        dt.date(2026, 6, 4),
        dt.date(2026, 12, 24),
        dt.date(2026, 12, 31),
    ],
)
def test_optional_days_are_not_national_holidays(day):
    row = _row(_year_2026(), day)

    assert bool(row["is_national_holiday"]) is False
    assert pd.isna(row["holiday_name"])


# Case 9
def test_ordinary_monday_is_not_a_holiday():
    row = _row(_year_2026(), dt.date(2026, 11, 9))

    assert bool(row["is_national_holiday"]) is False
    assert pd.isna(row["holiday_name"])
    assert row["weekday"] == 1


# Case 10
def test_full_range_weekday_name_consistency_and_holiday_total():
    df = build_calendar(FULL_RANGE_START, FULL_RANGE_END)

    assert len(df) == FULL_RANGE_DAYS
    assert all(
        weekday == day.isoweekday() for day, weekday in zip(df["date"], df["weekday"], strict=True)
    )
    named = df["holiday_name"].map(lambda name: isinstance(name, str) and name != "")
    assert (named == df["is_national_holiday"].astype(bool)).all()
    assert int(df["is_national_holiday"].sum()) == FULL_RANGE_HOLIDAYS


# Case 11
def test_same_input_gives_equal_dataframes():
    first = build_calendar(dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    second = build_calendar(dt.date(2026, 1, 1), dt.date(2026, 12, 31))

    pd.testing.assert_frame_equal(first, second)


# ---------------------------------------------------------------------------
# CALENDAR_SCHEMA (no database)
# ---------------------------------------------------------------------------


# Case 12
def test_built_calendar_passes_the_schema_check():
    check(_year_2026(), CALENDAR_SCHEMA, expected_rows=365)


# Case 13
def test_weekday_out_of_range_fails_citing_weekday():
    df = _year_2026()
    df.loc[df["date"] == dt.date(2026, 11, 9), "weekday"] = 8

    with pytest.raises(CheckFailed, match="weekday"):
        check(df, CALENDAR_SCHEMA)


def test_weekday_not_matching_the_date_fails():
    df = _year_2026()
    df.loc[df["date"] == dt.date(2026, 11, 9), "weekday"] = 2

    with pytest.raises(CheckFailed):
        check(df, CALENDAR_SCHEMA)


# Case 14
def test_holiday_without_name_fails():
    df = _year_2026()
    df.loc[df["date"] == dt.date(2026, 1, 1), "holiday_name"] = None

    with pytest.raises(CheckFailed):
        check(df, CALENDAR_SCHEMA)


def test_non_holiday_with_name_fails():
    df = _year_2026()
    df.loc[df["date"] == dt.date(2026, 11, 9), "holiday_name"] = CHRISTMAS_NAME

    with pytest.raises(CheckFailed):
        check(df, CALENDAR_SCHEMA)


# Case 15
def test_duplicate_date_fails():
    df = _year_2026()
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)

    with pytest.raises(CheckFailed):
        check(df, CALENDAR_SCHEMA)


def test_wrong_row_count_fails_with_expected_and_actual():
    with pytest.raises(CheckFailed, match="expected 366 rows, got 365"):
        check(_year_2026(), CALENDAR_SCHEMA, expected_rows=366)


# ---------------------------------------------------------------------------
# load_calendar (database)
# ---------------------------------------------------------------------------


def _query(url: str, statement: str) -> list[tuple]:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(statement))]
    finally:
        engine.dispose()


def _execute(url: str, statement: str) -> None:
    engine = build_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text(statement))
    finally:
        engine.dispose()


def _load_as_ingestor(url: str, start: dt.date, end: dt.date) -> int:
    engine = create_engine(url, connect_args={"options": "-c role=ingestor"})
    try:
        return load_calendar(engine, start, end)
    finally:
        engine.dispose()


@pytest.fixture
def calendar_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database


# Case 23
@pytest.mark.db
def test_full_range_load_is_idempotent(calendar_database):
    _load_as_ingestor(calendar_database, FULL_RANGE_START, FULL_RANGE_END)

    first = _query(calendar_database, SELECT_ALL)
    assert len(first) == FULL_RANGE_DAYS
    assert sum(1 for row in first if row[2]) == FULL_RANGE_HOLIDAYS

    _load_as_ingestor(calendar_database, FULL_RANGE_START, FULL_RANGE_END)

    assert _query(calendar_database, SELECT_ALL) == first


# Case 24
@pytest.mark.db
def test_reload_corrects_a_wrong_day_and_leaves_other_rows_alone(calendar_database):
    _load_as_ingestor(calendar_database, dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    for day in ("2026-12-25", "2026-11-20"):
        _execute(
            calendar_database,
            "UPDATE ref.calendar SET is_national_holiday = false, holiday_name = NULL "
            f"WHERE date = '{day}'",
        )

    _load_as_ingestor(calendar_database, dt.date(2026, 12, 1), dt.date(2026, 12, 31))

    select_day = "SELECT is_national_holiday, holiday_name FROM ref.calendar WHERE date = '{}'"
    assert _query(calendar_database, select_day.format("2026-12-25")) == [(True, CHRISTMAS_NAME)]
    assert _query(calendar_database, select_day.format("2026-11-20")) == [(False, None)]


# Case 25
@pytest.mark.db
def test_partial_load_followed_by_larger_range_has_no_duplicates(calendar_database):
    _load_as_ingestor(calendar_database, dt.date(2026, 1, 1), dt.date(2026, 1, 31))
    assert _query(calendar_database, "SELECT count(*) FROM ref.calendar") == [(31,)]

    _load_as_ingestor(calendar_database, dt.date(2026, 1, 1), dt.date(2026, 12, 31))

    assert _query(calendar_database, "SELECT count(*) FROM ref.calendar") == [(365,)]
    assert _query(calendar_database, "SELECT count(DISTINCT date) FROM ref.calendar") == [(365,)]


# Case 26
@pytest.mark.db
def test_start_after_end_raises_and_leaves_the_table_empty(calendar_database):
    with pytest.raises(ValueError):
        _load_as_ingestor(calendar_database, dt.date(2026, 2, 1), dt.date(2026, 1, 31))

    assert _query(calendar_database, "SELECT count(*) FROM ref.calendar") == [(0,)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _effective_code(argv: list[str]) -> int:
    from ingestion.cli import main

    try:
        code = main(argv)
    except SystemExit as exit_info:
        code = exit_info.code
    return 0 if code is None else code


# Case 27
@pytest.mark.db
def test_cli_loads_the_requested_range(calendar_database, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", calendar_database)

    code = _effective_code(["calendar", "--start", "2026-01-01", "--end", "2026-01-31"])

    assert code == 0
    assert _query(calendar_database, "SELECT count(*) FROM ref.calendar") == [(31,)]


# Case 28
def test_cli_rejects_an_invalid_date_with_usage_error():
    assert _effective_code(["calendar", "--start", "2026-13-01", "--end", "2026-12-31"]) == 2


def test_cli_requires_end():
    assert _effective_code(["calendar", "--start", "2026-01-01"]) == 2


def test_cli_help_exits_zero_and_lists_both_options(capsys):
    assert _effective_code(["calendar", "--help"]) == 0

    output = capsys.readouterr().out
    assert "--start" in output
    assert "--end" in output


# Case 29
@pytest.mark.db
def test_cli_returns_one_with_value_error_traceback_when_start_is_after_end(
    calendar_database, monkeypatch, capsys
):
    monkeypatch.setenv("DATABASE_URL", calendar_database)

    code = _effective_code(["calendar", "--start", "2026-02-01", "--end", "2026-01-31"])

    assert code == 1
    assert "ValueError" in capsys.readouterr().err
