"""Tests for ``ingestion.checks`` with ``WEATHER_FORECAST_SCHEMA`` (plan 15, cases 1 to 12).

No database: every test builds a small DataFrame in memory. The valid frame is 4 locations times
horizons 1 to 7, with the columns that the job rereads from ``raw.weather_forecast``.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from ingestion.checks import WEATHER_FORECAST_SCHEMA, CheckFailed, check

ISSUED = dt.date(2026, 11, 8)
LOCATIONS = ["belem", "porto_alegre", "recife", "sao_paulo"]
EXPECTED_ROWS = 28


def _valid_frame() -> pd.DataFrame:
    rows = []
    for location_id in LOCATIONS:
        for horizon in range(1, 8):
            rows.append(
                {
                    "location_id": location_id,
                    "issued_at": ISSUED,
                    "target_date": ISSUED + dt.timedelta(days=horizon),
                    "horizon_days": horizon,
                    "temp_max": 25.0 + horizon,
                    "temp_min": 15.0 + horizon,
                    "precip_mm": 1.5,
                    "wind_speed_max": 12.0,
                    "humidity_mean": 80.0,
                }
            )
    return pd.DataFrame(rows)


def _expect_failure(frame: pd.DataFrame, expected_rows: int | None = EXPECTED_ROWS) -> str:
    with pytest.raises(CheckFailed) as error_info:
        check(frame, WEATHER_FORECAST_SCHEMA, expected_rows=expected_rows)
    return str(error_info.value)


# Case 1
def test_valid_frame_with_expected_rows_passes():
    check(_valid_frame(), WEATHER_FORECAST_SCHEMA, expected_rows=EXPECTED_ROWS)


# Case 2
def test_row_count_mismatch_fails_and_names_both_numbers():
    frame = _valid_frame().iloc[:27]

    message = _expect_failure(frame)

    assert "28" in message
    assert "27" in message


# Case 3
def test_temp_max_above_fifty_fails_and_names_the_column():
    frame = _valid_frame()
    frame.loc[3, "temp_max"] = 51.0

    assert "temp_max" in _expect_failure(frame)


# Case 4
def test_temp_min_below_minus_ten_fails_and_names_the_column():
    frame = _valid_frame()
    frame.loc[3, "temp_min"] = -10.5

    assert "temp_min" in _expect_failure(frame)


# Case 5
def test_temp_min_greater_than_temp_max_fails():
    frame = _valid_frame()
    frame.loc[3, "temp_max"] = 10.0
    frame.loc[3, "temp_min"] = 20.0

    _expect_failure(frame)


# Case 6
def test_negative_precipitation_fails_and_names_the_column():
    frame = _valid_frame()
    frame.loc[3, "precip_mm"] = -0.1

    assert "precip_mm" in _expect_failure(frame)


# Case 7
def test_humidity_above_hundred_fails_and_names_the_column():
    frame = _valid_frame()
    frame.loc[3, "humidity_mean"] = 101.0

    assert "humidity_mean" in _expect_failure(frame)


# Case 8
def test_null_location_id_fails():
    frame = _valid_frame()
    frame["location_id"] = frame["location_id"].astype(object)
    frame.loc[3, "location_id"] = None

    _expect_failure(frame)


# Case 9
def test_horizon_zero_fails():
    frame = _valid_frame()
    frame.loc[3, "horizon_days"] = 0

    _expect_failure(frame)


# Case 10
def test_duplicate_key_fails():
    frame = _valid_frame()
    frame.loc[1, "target_date"] = frame.loc[0, "target_date"]

    _expect_failure(frame)


# Case 11
def test_null_temperatures_in_a_row_are_allowed():
    frame = _valid_frame()
    frame.loc[3, "temp_max"] = float("nan")
    frame.loc[3, "temp_min"] = float("nan")

    check(frame, WEATHER_FORECAST_SCHEMA, expected_rows=EXPECTED_ROWS)


# Case 12
def test_two_failures_at_once_raise_a_single_error_naming_both_columns():
    frame = _valid_frame()
    frame.loc[2, "temp_max"] = 51.0
    frame.loc[9, "precip_mm"] = -1.0

    message = _expect_failure(frame)

    assert "temp_max" in message
    assert "precip_mm" in message
