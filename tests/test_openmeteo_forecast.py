"""Tests for ``ingestion.openmeteo.fetch_forecast`` (plan 14, cases 15 to 22).

The API response is a real recording (``tests/fixtures/openmeteo_forecast_sao_paulo.json``).
Variations are built in memory from a deep copy. No test touches the network. Only case 22 needs
Postgres and carries the ``db`` marker.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pandas as pd
import pytest
from alembic import command
from ingestion.http import NetworkError
from ingestion.openmeteo import (
    DAILY_VARIABLES,
    FORECAST_URL,
    Location,
    fetch_forecast,
)
from sqlalchemy import text

from ingestion.db import build_engine, upsert
from tests.conftest import alembic_config

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "openmeteo_forecast_sao_paulo.json"
RECORDING = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
D = dt.date.fromisoformat(RECORDING["daily"]["time"][0])
LOCATION = Location("sao_paulo", -23.55, -46.63)
OUTPUT_COLUMNS = [
    "location_id",
    "issued_at",
    "target_date",
    "temp_max",
    "temp_min",
    "precip_mm",
    "wind_speed_max",
    "humidity_mean",
]
TABLE = "raw.weather_forecast"
KEYS = ["location_id", "issued_at", "target_date"]

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
    payload: dict | None = None, issued_at: dt.date = D, days: int | None = None
) -> tuple[pd.DataFrame, Harness]:
    harness = Harness([_ok(payload)])
    kwargs = {} if days is None else {"days": days}
    frame = fetch_forecast(harness.client, LOCATION, issued_at, sleep=harness.sleep, **kwargs)
    return frame, harness


def _expect_value_error(payload: dict | None = None, issued_at: dt.date = D, days: int = 7):
    harness = Harness([_ok(payload)])
    with pytest.raises(ValueError) as error_info:
        fetch_forecast(harness.client, LOCATION, issued_at, days=days, sleep=harness.sleep)
    return error_info


# Case 15
def test_seven_rows_from_next_day_to_day_seven_with_date_values():
    frame, _ = _fetch()

    assert len(frame) == 7
    assert list(frame["target_date"]) == [D + dt.timedelta(days=n) for n in range(1, 8)]
    assert set(frame["location_id"]) == {"sao_paulo"}
    assert set(frame["issued_at"]) == {D}
    for value in [*frame["issued_at"], *frame["target_date"]]:
        assert type(value) is dt.date


# Case 16
def test_columns_order_and_float_dtypes():
    frame, _ = _fetch()

    assert list(frame.columns) == OUTPUT_COLUMNS
    assert "horizon_days" not in frame.columns
    assert "ingested_at" not in frame.columns
    for column in DAILY_VARIABLES.values():
        assert frame[column].dtype == "float64"
    assert list(frame.index) == list(range(7))


# Case 17
def test_values_match_the_recording_and_drop_the_issue_day():
    frame, _ = _fetch()

    for api_name, column in DAILY_VARIABLES.items():
        recorded = RECORDING["daily"][api_name]
        assert frame[column].iloc[0] == recorded[1]
        assert frame[column].iloc[6] == recorded[7]
        assert list(frame[column]) == [float(value) for value in recorded[1:8]]


# Case 18
def test_request_goes_to_forecast_url_with_exact_params():
    _, harness = _fetch()

    assert len(harness.requests) == 1
    request = harness.requests[0]
    assert FORECAST_URL == "https://api.open-meteo.com/v1/forecast"
    assert str(request.url).split("?")[0] == FORECAST_URL
    params = request.url.params
    assert params["latitude"] == "-23.55"
    assert params["longitude"] == "-46.63"
    assert params["timezone"] == "America/Sao_Paulo"
    assert params["forecast_days"] == "8"
    assert params["daily"] == ",".join(DAILY_VARIABLES)
    assert set(params.keys()) == {"latitude", "longitude", "daily", "timezone", "forecast_days"}


# Case 19
def test_days_argument_shortens_the_window_and_the_request():
    frame, harness = _fetch(days=3)

    assert list(frame["target_date"]) == [D + dt.timedelta(days=n) for n in range(1, 4)]
    assert harness.requests[0].url.params["forecast_days"] == "4"


# Case 19
@pytest.mark.parametrize("days", [0, 8])
def test_days_outside_one_to_seven_is_rejected_before_any_request(days):
    harness = Harness([_ok()])

    with pytest.raises(ValueError):
        fetch_forecast(harness.client, LOCATION, D, days=days, sleep=harness.sleep)

    assert harness.requests == []


# Case 20a
def test_null_value_becomes_nan_and_leaves_other_cells_untouched():
    baseline, _ = _fetch()
    payload = _payload()
    payload["daily"]["precipitation_sum"][2] = None

    frame, _ = _fetch(payload)

    assert pd.isna(frame["precip_mm"].iloc[1])
    assert frame["precip_mm"].dtype == "float64"
    assert frame["precip_mm"].drop(index=1).tolist() == baseline["precip_mm"].drop(index=1).tolist()
    other_columns = [column for column in OUTPUT_COLUMNS if column != "precip_mm"]
    pd.testing.assert_frame_equal(frame[other_columns], baseline[other_columns])


# Case 20b
@pytest.mark.parametrize("offset_days", [1, -1])
def test_issue_day_different_from_first_api_day_is_rejected(offset_days):
    wrong = D + dt.timedelta(days=offset_days)

    error_info = _expect_value_error(issued_at=wrong)

    message = str(error_info.value)
    assert D.isoformat() in message
    assert wrong.isoformat() in message


# Case 20c
def test_missing_variable_is_rejected_and_named():
    payload = _payload()
    del payload["daily"]["relative_humidity_2m_mean"]

    error_info = _expect_value_error(payload)

    assert "relative_humidity_2m_mean" in str(error_info.value)


# Case 20d
def test_unexpected_unit_is_rejected_and_names_the_variable():
    payload = _payload()
    payload["daily_units"]["wind_speed_10m_max"] = "m/s"

    error_info = _expect_value_error(payload)

    message = str(error_info.value)
    assert "wind_speed_10m_max" in message
    assert "m/s" in message


# Case 20e
def test_response_with_fewer_than_days_plus_one_days_is_rejected():
    payload = _payload()
    payload["daily"] = {name: values[:7] for name, values in payload["daily"].items()}

    _expect_value_error(payload, days=7)


# Case 20f
def test_variable_shorter_than_time_is_rejected():
    payload = _payload()
    payload["daily"]["temperature_2m_min"] = payload["daily"]["temperature_2m_min"][:-1]

    _expect_value_error(payload)


# Case 21
def test_transient_503_is_retried_by_the_fetch_json_layer():
    harness = Harness([_unavailable, _unavailable, _ok()])

    frame = fetch_forecast(harness.client, LOCATION, D, sleep=harness.sleep)

    assert len(frame) == 7
    assert len(harness.requests) == 3


# Case 21
def test_persistent_503_raises_network_error():
    harness = Harness([_unavailable])

    with pytest.raises(NetworkError):
        fetch_forecast(harness.client, LOCATION, D, sleep=harness.sleep)

    assert len(harness.requests) == 3


@pytest.fixture
def forecast_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database


def _upsert_as_ingestor(url: str, frame: pd.DataFrame) -> int:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SET ROLE ingestor"))
            written = upsert(connection, TABLE, frame, keys=KEYS, on_conflict="ignore")
            connection.commit()
            return written
    finally:
        engine.dispose()


def _stored_rows(url: str) -> list[tuple]:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            return [
                tuple(row)
                for row in connection.execute(
                    text(
                        "SELECT issued_at, horizon_days FROM raw.weather_forecast "
                        "ORDER BY target_date"
                    )
                )
            ]
    finally:
        engine.dispose()


# Case 22
@pytest.mark.db
def test_client_output_is_written_as_ingestor_and_second_run_is_ignored(forecast_database):
    frame, _ = _fetch()

    assert _upsert_as_ingestor(forecast_database, frame) == 7
    assert _stored_rows(forecast_database) == [(D, horizon) for horizon in range(1, 8)]

    assert _upsert_as_ingestor(forecast_database, frame) == 0
    assert len(_stored_rows(forecast_database)) == 7
