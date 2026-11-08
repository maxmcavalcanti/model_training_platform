"""Tests for ``ingestion.openmeteo.fetch_observed`` (plan 24, cases 1 to 15).

The API response is a real recording (``tests/fixtures/openmeteo_archive_sao_paulo.json``).
Variations are built in memory from a deep copy. No test touches the network and none needs
Postgres. The forecast tests (``test_openmeteo_forecast.py``) must keep passing unedited.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pandas as pd
import pytest

from ingestion.http import NetworkError
from ingestion.openmeteo import (
    ARCHIVE_URL,
    DAILY_VARIABLES,
    Location,
    fetch_observed,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "openmeteo_archive_sao_paulo.json"
RECORDING = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
START = dt.date.fromisoformat(RECORDING["daily"]["time"][0])
END = dt.date.fromisoformat(RECORDING["daily"]["time"][-1])
N = len(RECORDING["daily"]["time"])
LOCATION = Location("sao_paulo", -23.55, -46.63)
OUTPUT_COLUMNS = ["location_id", "date", *DAILY_VARIABLES.values()]
VARIABLE_NAMES = list(DAILY_VARIABLES)
ONE_DAY = dt.timedelta(days=1)

Step = Callable[[httpx.Request], httpx.Response]


def _payload() -> dict:
    return copy.deepcopy(RECORDING)


def _ok(payload: dict | None = None) -> Step:
    body = payload if payload is not None else _payload()
    return lambda request: httpx.Response(200, json=body)


def _unavailable(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503)


class Harness:
    """Client whose n-th request is answered by the n-th step; records requests and sleeps."""

    def __init__(self, steps: list[Step]) -> None:
        self.steps = steps
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.steps[min(len(self.requests), len(self.steps)) - 1](request)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _fetch(
    payload: dict | None = None, start: dt.date = START, end: dt.date = END
) -> tuple[pd.DataFrame, Harness]:
    harness = Harness([_ok(payload)])
    frame = fetch_observed(harness.client, LOCATION, start, end, sleep=harness.sleep)
    return frame, harness


def _expect_value_error(payload: dict | None = None, start: dt.date = START, end: dt.date = END):
    harness = Harness([_ok(payload)])
    with pytest.raises(ValueError) as error_info:
        fetch_observed(harness.client, LOCATION, start, end, sleep=harness.sleep)
    return error_info


def _null_days(payload: dict, positions: list[int], variables: list[str] | None = None) -> dict:
    for name in variables if variables is not None else VARIABLE_NAMES:
        for position in positions:
            payload["daily"][name][position] = None
    return payload


def _drop_positions(payload: dict, positions: set[int]) -> dict:
    payload["daily"] = {
        name: [value for index, value in enumerate(values) if index not in positions]
        for name, values in payload["daily"].items()
    }
    return payload


# Case 1
def test_one_row_per_day_from_start_to_end_with_date_values():
    frame, _ = _fetch()

    assert len(frame) == N
    assert list(frame["date"]) == [START + dt.timedelta(days=n) for n in range(N)]
    assert frame["date"].iloc[-1] == END
    assert set(frame["location_id"]) == {"sao_paulo"}
    for value in frame["date"]:
        assert type(value) is dt.date
    assert list(frame.index) == list(range(N))


# Case 2
def test_columns_order_and_float_dtypes():
    frame, _ = _fetch()

    assert list(frame.columns) == OUTPUT_COLUMNS
    for forbidden in ("ingested_at", "issued_at", "target_date"):
        assert forbidden not in frame.columns
    for column in DAILY_VARIABLES.values():
        assert frame[column].dtype == "float64"


# Case 3
def test_values_match_the_recording_including_first_and_last_day():
    frame, _ = _fetch()

    for api_name, column in DAILY_VARIABLES.items():
        recorded = RECORDING["daily"][api_name]
        assert frame[column].iloc[0] == recorded[0]
        assert frame[column].iloc[-1] == recorded[-1]
        assert list(frame[column]) == [float(value) for value in recorded]


# Case 4
def test_request_goes_to_archive_url_with_exact_params():
    _, harness = _fetch()

    assert len(harness.requests) == 1
    assert harness.sleeps == []
    request = harness.requests[0]
    assert ARCHIVE_URL == "https://archive-api.open-meteo.com/v1/archive"
    assert str(request.url).split("?")[0] == ARCHIVE_URL
    params = request.url.params
    assert params["latitude"] == "-23.55"
    assert params["longitude"] == "-46.63"
    assert params["start_date"] == START.isoformat()
    assert params["end_date"] == END.isoformat()
    assert params["daily"] == ",".join(DAILY_VARIABLES)
    assert params["timezone"] == "America/Sao_Paulo"
    assert set(params.keys()) == {
        "latitude",
        "longitude",
        "start_date",
        "end_date",
        "daily",
        "timezone",
    }


# Case 5
def test_trailing_all_null_days_are_dropped():
    baseline, _ = _fetch()
    payload = _null_days(_payload(), [N - 3, N - 2, N - 1])

    frame, _ = _fetch(payload)

    assert len(frame) == N - 3
    assert frame["date"].iloc[-1] == END - 3 * ONE_DAY
    pd.testing.assert_frame_equal(frame, baseline.iloc[: N - 3])


# Case 6
def test_all_null_day_in_the_middle_is_dropped_without_error():
    baseline, _ = _fetch()
    payload = _null_days(_payload(), [4])

    frame, _ = _fetch(payload)

    assert len(frame) == N - 1
    assert START + 4 * ONE_DAY not in list(frame["date"])
    expected = baseline.drop(index=4).reset_index(drop=True)
    pd.testing.assert_frame_equal(frame, expected)


# Case 7
def test_partial_null_day_is_kept_with_nan():
    baseline, _ = _fetch()
    payload = _null_days(_payload(), [3], ["relative_humidity_2m_mean"])

    frame, _ = _fetch(payload)

    assert len(frame) == N
    assert pd.isna(frame["humidity_mean"].iloc[3])
    assert frame["humidity_mean"].dtype == "float64"
    others = [column for column in DAILY_VARIABLES.values() if column != "humidity_mean"]
    for column in others:
        assert frame[column].iloc[3] == baseline[column].iloc[3]
        assert frame[column].dtype == "float64"


# Case 8
def test_day_with_only_precipitation_is_kept():
    baseline, _ = _fetch()
    others = [name for name in VARIABLE_NAMES if name != "precipitation_sum"]
    payload = _null_days(_payload(), [2], others)

    frame, _ = _fetch(payload)

    assert len(frame) == N
    assert frame["precip_mm"].iloc[2] == baseline["precip_mm"].iloc[2]
    for column in DAILY_VARIABLES.values():
        if column != "precip_mm":
            assert pd.isna(frame[column].iloc[2])


# Case 9
def test_all_days_null_returns_empty_frame_with_columns_and_dtypes():
    payload = _null_days(_payload(), list(range(N)))

    frame, _ = _fetch(payload)

    assert len(frame) == 0
    assert list(frame.columns) == OUTPUT_COLUMNS
    for column in DAILY_VARIABLES.values():
        assert frame[column].dtype == "float64"


# Case 10
def test_single_day_interval_returns_one_row():
    payload = _payload()
    payload["daily"] = {name: values[:1] for name, values in payload["daily"].items()}

    frame, harness = _fetch(payload, start=START, end=START)

    assert len(frame) == 1
    assert frame["date"].iloc[0] == START
    params = harness.requests[0].url.params
    assert params["start_date"] == START.isoformat()
    assert params["end_date"] == START.isoformat()


# Case 11
def test_start_after_end_is_rejected_before_any_request():
    harness = Harness([_ok()])

    with pytest.raises(ValueError):
        fetch_observed(harness.client, LOCATION, END, START, sleep=harness.sleep)

    assert harness.requests == []


# Case 12a
def test_response_without_daily_section_is_rejected():
    payload = _payload()
    del payload["daily"]

    error_info = _expect_value_error(payload)

    assert "sao_paulo" in str(error_info.value)


# Case 12b
def test_missing_variable_is_rejected_and_named():
    payload = _payload()
    del payload["daily"]["relative_humidity_2m_mean"]

    error_info = _expect_value_error(payload)

    message = str(error_info.value)
    assert "sao_paulo" in message
    assert "relative_humidity_2m_mean" in message


# Case 12c
def test_unexpected_unit_is_rejected_and_names_the_variable():
    payload = _payload()
    payload["daily_units"]["wind_speed_10m_max"] = "m/s"

    error_info = _expect_value_error(payload)

    message = str(error_info.value)
    assert "sao_paulo" in message
    assert "wind_speed_10m_max" in message
    assert "m/s" in message


# Case 12d
def test_variable_shorter_than_time_is_rejected():
    payload = _payload()
    payload["daily"]["temperature_2m_min"] = payload["daily"]["temperature_2m_min"][:-1]

    error_info = _expect_value_error(payload)

    assert "sao_paulo" in str(error_info.value)


# Case 12e
def test_response_starting_after_requested_start_is_rejected_with_both_dates():
    requested = START - ONE_DAY

    error_info = _expect_value_error(start=requested)

    message = str(error_info.value)
    assert "sao_paulo" in message
    assert requested.isoformat() in message
    assert START.isoformat() in message


# Case 12f
def test_response_ending_before_requested_end_is_rejected():
    payload = _drop_positions(_payload(), {N - 1})

    error_info = _expect_value_error(payload)

    assert "sao_paulo" in str(error_info.value)


# Case 12g
def test_response_with_a_gap_in_time_is_rejected():
    payload = _drop_positions(_payload(), {4})

    error_info = _expect_value_error(payload)

    assert "sao_paulo" in str(error_info.value)


# Case 13
def test_transient_503_is_retried_by_the_fetch_json_layer():
    harness = Harness([_unavailable, _unavailable, _ok()])

    frame = fetch_observed(harness.client, LOCATION, START, END, sleep=harness.sleep)

    assert len(frame) == N
    assert len(harness.requests) == 3
    assert harness.sleeps == [1.0, 2.0]


# Case 14
def test_persistent_503_raises_network_error():
    harness = Harness([_unavailable])

    with pytest.raises(NetworkError):
        fetch_observed(harness.client, LOCATION, START, END, sleep=harness.sleep)

    assert len(harness.requests) == 3


# Case 15
def test_client_error_400_is_not_retried_and_is_not_a_network_error():
    body = {"error": True, "reason": "Parameter 'start_date' is out of allowed range"}
    harness = Harness([lambda request: httpx.Response(400, json=body)])

    with pytest.raises(httpx.HTTPStatusError) as error_info:
        fetch_observed(harness.client, LOCATION, START, END, sleep=harness.sleep)

    assert not isinstance(error_info.value, NetworkError)
    assert len(harness.requests) == 1
    assert harness.sleeps == []
