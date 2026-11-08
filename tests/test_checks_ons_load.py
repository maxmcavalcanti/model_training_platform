"""Tests for ``check_ons_daily_load`` and ``ONS_DAILY_LOAD_SCHEMA`` (plan 22, cases 1 to 10).

No database and no network: every test builds a small DataFrame in memory with the columns that
the job rereads from ``raw.ons_daily_load`` (``subsystem``, ``date``, ``load_avg_mw``).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from ingestion.checks import CheckFailed, check_ons_daily_load

START = dt.date(2026, 10, 10)
END = dt.date(2026, 11, 8)
MAX_DELAY_DAYS = 5
LOADS = {"SE": 40000.0, "S": 12000.0, "NE": 11000.0, "N": 7000.0}
COLUMNS = ["subsystem", "date", "load_avg_mw"]


def _grid(first: dt.date, last: dt.date) -> pd.DataFrame:
    """Every day from ``first`` to ``last`` times the four subsystems."""
    rows = []
    day = first
    while day <= last:
        for code, load in LOADS.items():
            rows.append({"subsystem": code, "date": day, "load_avg_mw": load})
        day += dt.timedelta(days=1)
    return pd.DataFrame(rows, columns=COLUMNS)


def _valid_frame() -> pd.DataFrame:
    return _grid(START, dt.date(2026, 11, 5))


def _expect_failure(frame: pd.DataFrame) -> str:
    with pytest.raises(CheckFailed) as error_info:
        check_ons_daily_load(frame, START, END, MAX_DELAY_DAYS)
    return str(error_info.value)


def _drop(frame: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    return frame[~mask].reset_index(drop=True)


# Case 1
def test_complete_grid_up_to_three_days_before_end_passes():
    check_ons_daily_load(_valid_frame(), START, END, MAX_DELAY_DAYS)


# Case 2
def test_day_with_three_subsystems_fails_and_cites_the_date():
    frame = _valid_frame()
    frame = _drop(frame, (frame["date"] == dt.date(2026, 10, 25)) & (frame["subsystem"] == "N"))

    assert "2026-10-25" in _expect_failure(frame)


# Case 3
def test_day_missing_for_all_subsystems_fails_and_cites_the_date():
    frame = _valid_frame()
    frame = _drop(frame, frame["date"] == dt.date(2026, 10, 20))

    assert "2026-10-20" in _expect_failure(frame)


# Case 4
def test_grid_starting_after_start_fails_and_cites_the_missing_leading_days():
    message = _expect_failure(_grid(dt.date(2026, 10, 12), dt.date(2026, 11, 5)))

    assert "2026-10-10" in message
    assert "2026-10-11" in message


# Case 5
def test_last_date_six_days_before_end_is_stale():
    message = _expect_failure(_grid(START, dt.date(2026, 11, 2)))

    assert "stale" in message


# Case 5 (boundary)
def test_last_date_exactly_max_delay_days_before_end_passes():
    check_ons_daily_load(_grid(START, dt.date(2026, 11, 3)), START, END, MAX_DELAY_DAYS)


# Case 6
@pytest.mark.parametrize("value", [0.0, -1.0, 150000.0])
def test_load_outside_the_plausible_range_fails_and_names_the_column(value):
    frame = _valid_frame()
    frame.loc[5, "load_avg_mw"] = value

    assert "load_avg_mw" in _expect_failure(frame)


# Case 7
def test_unknown_subsystem_fails():
    frame = _valid_frame()
    frame.loc[5, "subsystem"] = "SIN"

    _expect_failure(frame)


# Case 8
def test_duplicate_subsystem_date_row_fails():
    frame = _valid_frame()
    duplicate = frame[(frame["subsystem"] == "SE") & (frame["date"] == dt.date(2026, 10, 15))]
    frame = pd.concat([frame, duplicate], ignore_index=True)

    _expect_failure(frame)


# Case 9
def test_empty_frame_fails_with_no_rows():
    frame = pd.DataFrame(
        {
            "subsystem": pd.Series([], dtype="object"),
            "date": pd.Series([], dtype="object"),
            "load_avg_mw": pd.Series([], dtype="float64"),
        }
    )

    assert "no rows" in _expect_failure(frame)


# Case 10
def test_two_problems_are_reported_together_in_a_single_failure():
    frame = _valid_frame()
    frame.loc[5, "load_avg_mw"] = 0.0
    frame = _drop(frame, frame["date"] == dt.date(2026, 10, 20))

    message = _expect_failure(frame)

    assert "load_avg_mw" in message
    assert "2026-10-20" in message


# ---------------------------------------------------------------------------
# ONS source-gaps plan (2026-11-08), cases 28 to 35: known whole-day gaps of the source
# ---------------------------------------------------------------------------

GAP_DAY = dt.date(2015, 4, 9)
YEAR_2015_START = dt.date(2015, 1, 1)
YEAR_2015_END = dt.date(2015, 12, 31)


def _year_2015_without(*days: dt.date) -> pd.DataFrame:
    frame = _grid(YEAR_2015_START, YEAR_2015_END)
    return _drop(frame, frame["date"].isin(days))


def _check_2015(frame: pd.DataFrame, **kwargs) -> None:
    check_ons_daily_load(frame, YEAR_2015_START, YEAR_2015_END, MAX_DELAY_DAYS, **kwargs)


def _expect_2015_failure(frame: pd.DataFrame, **kwargs) -> str:
    with pytest.raises(CheckFailed) as error_info:
        _check_2015(frame, **kwargs)
    return str(error_info.value)


# Case 28
def test_known_gaps_constant_lists_the_three_surveyed_days():
    # Imported here so the missing constant fails only this case, not the whole module.
    from ingestion.ons import ONS_KNOWN_GAPS

    assert ONS_KNOWN_GAPS == frozenset(
        {dt.date(2013, 12, 1), dt.date(2014, 2, 1), dt.date(2015, 4, 9)}
    )


# Case 29
def test_known_gap_day_missing_for_all_subsystems_passes():
    frame = _year_2015_without(GAP_DAY)

    assert len(frame) == 1456
    _check_2015(frame)


# Case 30
def test_unknown_gap_next_to_a_known_one_fails_citing_only_the_unknown():
    message = _expect_2015_failure(_year_2015_without(GAP_DAY, dt.date(2015, 4, 10)))

    assert "2015-04-10" in message
    assert "2015-04-09" not in message


# Case 31
def test_known_gap_day_with_three_subsystems_fails_and_cites_the_date():
    frame = _year_2015_without()
    frame = _drop(frame, (frame["date"] == GAP_DAY) & (frame["subsystem"] == "N"))

    assert "2015-04-09" in _expect_2015_failure(frame)


# Case 32
def test_known_gap_day_present_with_four_subsystems_passes():
    _check_2015(_year_2015_without())


# Case 33
def test_range_starting_on_the_known_gap_passes():
    frame = _grid(dt.date(2015, 4, 10), dt.date(2015, 4, 30))

    check_ons_daily_load(frame, GAP_DAY, dt.date(2015, 4, 30), MAX_DELAY_DAYS)


# Case 34
def test_known_gaps_parameter_accepts_a_synthetic_gap():
    frame = _grid(dt.date(2026, 10, 10), dt.date(2026, 11, 5))
    frame = _drop(frame, frame["date"] == dt.date(2026, 10, 20))

    check_ons_daily_load(
        frame, START, END, MAX_DELAY_DAYS, known_gaps=frozenset({dt.date(2026, 10, 20)})
    )


# Case 34 (second half)
def test_empty_known_gaps_makes_the_2015_gap_fail_again():
    message = _expect_2015_failure(_year_2015_without(GAP_DAY), known_gaps=frozenset())

    assert "2015-04-09" in message


# Case 35
def test_empty_frame_on_a_known_gap_day_still_fails_with_no_rows():
    frame = pd.DataFrame(
        {
            "subsystem": pd.Series([], dtype="object"),
            "date": pd.Series([], dtype="object"),
            "load_avg_mw": pd.Series([], dtype="float64"),
        }
    )

    with pytest.raises(CheckFailed) as error_info:
        check_ons_daily_load(frame, GAP_DAY, GAP_DAY, MAX_DELAY_DAYS)

    assert "no rows" in str(error_info.value)
