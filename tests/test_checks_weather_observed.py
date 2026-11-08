"""Tests for ``check_weather_observed`` and ``WEATHER_OBSERVED_SCHEMA`` (plan 26, cases 1 to 12).

No database and no network: every test builds a DataFrame in memory with the columns that the job
rereads from ``raw.weather_observed`` (``location_id``, ``date`` and the five variables).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from ingestion.checks import CheckFailed, check_weather_observed

END = dt.date(2026, 11, 7)
START = END - dt.timedelta(days=9)
MAX_DELAY_DAYS = 7
LOCATION_IDS = ["belem", "porto_alegre", "recife", "sao_paulo"]
VARIABLES = {
    "temp_max": 30.0,
    "temp_min": 20.0,
    "precip_mm": 1.0,
    "wind_speed_max": 10.0,
    "humidity_mean": 70.0,
}
COLUMNS = ["location_id", "date", *VARIABLES]


def _days(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + dt.timedelta(days=n) for n in range((last - first).days + 1)]


def _grid(first: dt.date, last: dt.date, location_ids: list[str] | None = None) -> pd.DataFrame:
    """Every day from ``first`` to ``last`` times the given locations (default: the four)."""
    rows = [
        {"location_id": location_id, "date": day, **VARIABLES}
        for location_id in (location_ids if location_ids is not None else LOCATION_IDS)
        for day in _days(first, last)
    ]
    return pd.DataFrame(rows, columns=COLUMNS)


def _valid_frame() -> pd.DataFrame:
    return _grid(START, END)


def _drop(frame: pd.DataFrame, location_id: str, *days: dt.date) -> pd.DataFrame:
    mask = (frame["location_id"] == location_id) & frame["date"].isin(days)
    return frame[~mask].reset_index(drop=True)


def _set(frame: pd.DataFrame, location_id: str, day: dt.date, column: str, value) -> pd.DataFrame:
    frame = frame.copy()
    mask = (frame["location_id"] == location_id) & (frame["date"] == day)
    assert mask.sum() == 1
    frame.loc[mask, column] = value
    return frame


def _check(frame: pd.DataFrame, start: dt.date = START, end: dt.date = END) -> None:
    check_weather_observed(frame, LOCATION_IDS, start, end, MAX_DELAY_DAYS)


def _expect_failure(frame: pd.DataFrame, start: dt.date = START, end: dt.date = END) -> str:
    with pytest.raises(CheckFailed) as error_info:
        _check(frame, start, end)
    return str(error_info.value)


# Case 1
def test_complete_grid_for_the_window_passes():
    frame = _valid_frame()

    assert len(frame) == 40
    _check(frame)


# Case 2
def test_missing_day_in_the_middle_of_one_location_fails_and_cites_location_and_date():
    frame = _drop(_valid_frame(), "sao_paulo", dt.date(2026, 11, 2))

    message = _expect_failure(frame)

    assert "sao_paulo" in message
    assert "2026-11-02" in message


# Case 3
def test_location_starting_late_fails_and_cites_the_missing_first_days():
    frame = _drop(_valid_frame(), "recife", dt.date(2026, 10, 29), dt.date(2026, 10, 30))

    message = _expect_failure(frame)

    assert "recife" in message
    assert "2026-10-29" in message
    assert "2026-10-30" in message


# Case 4
def test_data_up_to_the_delay_limit_passes():
    _check(_grid(START, dt.date(2026, 10, 31)))


# Case 4
def test_one_location_older_than_the_delay_limit_fails_as_stale():
    frame = pd.concat(
        [
            _grid(START, dt.date(2026, 10, 30), ["belem"]),
            _grid(START, END, ["porto_alegre", "recife", "sao_paulo"]),
        ],
        ignore_index=True,
    )

    message = _expect_failure(frame)

    assert "stale" in message
    assert "belem" in message


# Case 5
def test_location_without_rows_fails_with_no_rows():
    frame = _grid(START, END, ["belem", "recife", "sao_paulo"])

    message = _expect_failure(frame)

    assert "porto_alegre" in message
    assert "no rows" in message


# Case 6
def test_empty_frame_fails_citing_the_four_locations():
    frame = pd.DataFrame(
        {
            "location_id": pd.Series([], dtype="object"),
            "date": pd.Series([], dtype="object"),
            **{name: pd.Series([], dtype="float64") for name in VARIABLES},
        }
    )

    message = _expect_failure(frame)

    assert message.count("no rows") >= 4
    for location_id in LOCATION_IDS:
        assert location_id in message


# Case 7
@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("temp_max", 51.0),
        ("temp_min", -11.0),
        ("precip_mm", -0.1),
        ("wind_speed_max", -1.0),
        ("humidity_mean", 101.0),
    ],
)
def test_value_out_of_range_fails_and_cites_the_column(column, value):
    frame = _set(_valid_frame(), "recife", dt.date(2026, 11, 1), column, value)

    assert column in _expect_failure(frame)


# Case 8
def test_temp_min_above_temp_max_fails_with_the_rule_message():
    frame = _valid_frame()
    frame = _set(frame, "belem", dt.date(2026, 11, 1), "temp_min", 25.0)
    frame = _set(frame, "belem", dt.date(2026, 11, 1), "temp_max", 20.0)

    assert "temp_min must not exceed temp_max" in _expect_failure(frame)


# Case 9
def test_partial_nulls_in_the_variables_pass():
    frame = _set(_valid_frame(), "recife", dt.date(2026, 11, 1), "humidity_mean", float("nan"))
    frame = _set(frame, "belem", dt.date(2026, 11, 3), "temp_max", float("nan"))

    _check(frame)


# Case 10
def test_duplicated_key_fails():
    frame = _valid_frame()
    duplicate = frame[
        (frame["location_id"] == "sao_paulo") & (frame["date"] == dt.date(2026, 11, 1))
    ]
    frame = pd.concat([frame, duplicate], ignore_index=True)

    _expect_failure(frame)


# Case 10
def test_null_location_id_fails():
    frame = _valid_frame()
    frame.loc[0, "location_id"] = None

    _expect_failure(frame)


# Case 11
def test_two_problems_are_reported_in_a_single_check_failed():
    frame = _drop(_valid_frame(), "recife", dt.date(2026, 11, 2))
    frame = _set(frame, "belem", dt.date(2026, 11, 4), "temp_max", 80.0)

    message = _expect_failure(frame)

    assert "2026-11-02" in message
    assert "temp_max" in message


# Case 12
def test_backfill_of_a_closed_year_passes_because_delay_counts_from_end():
    start = dt.date(2015, 1, 1)
    end = dt.date(2015, 12, 31)
    frame = _grid(start, end)

    assert len(frame) == 1460
    check_weather_observed(frame, LOCATION_IDS, start, end, MAX_DELAY_DAYS)


# ---------------------------------------------------------------------------
# Hardening follow-ups plan H1, cases 9 to 11: all-NULL columns reread as ``object``
# ---------------------------------------------------------------------------


def _object_column(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    frame = frame.copy()
    frame[column] = pd.Series([None] * len(frame), dtype="object")
    return frame


# H1 case 9
@pytest.mark.parametrize("column", list(VARIABLES))
def test_all_null_object_variable_passes(column):
    _check(_object_column(_valid_frame(), column))


# H1 case 10
def test_object_column_with_one_out_of_range_value_still_fails_on_the_range():
    frame = _object_column(_valid_frame(), "humidity_mean")
    frame.loc[3, "humidity_mean"] = 101.0

    assert "humidity_mean" in _expect_failure(frame)


# H1 case 11
def test_object_column_with_non_numeric_text_fails_as_a_check_failure():
    frame = _object_column(_valid_frame(), "precip_mm")
    frame.loc[3, "precip_mm"] = "abc"

    assert "precip_mm" in _expect_failure(frame)
