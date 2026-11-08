"""Tests for the ``weather-forecast`` job (plan 15, cases 13 to 28).

Cases 13 to 15 (``issue_date``) and 25 to 28 (CLI) need no database. Cases 16 to 24 carry the
``db`` marker: they run the job as the ``ingestor`` role (no ``UPDATE`` on the table) against a
migrated ``fresh_database`` and a ``httpx.MockTransport`` that replays the recorded API response
(``tests/fixtures/openmeteo_forecast_sao_paulo.json``). No test touches the network.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from sqlalchemy import create_engine, text

from ingestion.checks import CheckFailed
from ingestion.db import build_engine
from ingestion.jobs import (
    PartialIngestionError,
    ingest_weather_forecast,
    issue_date,
    list_locations,
)
from ingestion.openmeteo import Location
from tests.conftest import alembic_config

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "openmeteo_forecast_sao_paulo.json"
RECORDING = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
TODAY = dt.date.fromisoformat(RECORDING["daily"]["time"][0])
LOCATION_IDS = ["belem", "porto_alegre", "recife", "sao_paulo"]
STORED_COLUMNS = (
    "location_id, issued_at, target_date, horizon_days, temp_max, temp_min, precip_mm, "
    "wind_speed_max, humidity_mean, ingested_at"
)

ResponseFactory = Callable[[], httpx.Response]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload(day_shift: int = 0, temp_max_delta: float = 0.0) -> dict:
    payload = copy.deepcopy(RECORDING)
    payload["daily"]["time"] = [
        (dt.date.fromisoformat(day) + dt.timedelta(days=day_shift)).isoformat()
        for day in payload["daily"]["time"]
    ]
    payload["daily"]["temperature_2m_max"] = [
        value + temp_max_delta for value in payload["daily"]["temperature_2m_max"]
    ]
    return payload


def _ok(payload: dict | None = None) -> ResponseFactory:
    body = payload if payload is not None else _payload()
    return lambda: httpx.Response(200, json=body)


def _unavailable() -> httpx.Response:
    return httpx.Response(503)


def _query(url: str, statement: str) -> list[tuple]:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(statement))]
    finally:
        engine.dispose()


def _coordinates(url: str) -> dict[str, tuple[float, float]]:
    rows = _query(url, "SELECT location_id, lat, lon FROM ref.locations")
    return {location_id: (lat, lon) for location_id, lat, lon in rows}


def _client(
    url: str,
    default: ResponseFactory | None = None,
    per_location: dict[str, ResponseFactory] | None = None,
) -> httpx.Client:
    """Client that answers by the ``latitude``/``longitude`` of the request."""
    coordinates = _coordinates(url)
    default = default or _ok()
    per_location = per_location or {}

    def handle(request: httpx.Request) -> httpx.Response:
        lat = float(request.url.params["latitude"])
        lon = float(request.url.params["longitude"])
        location_id = min(
            coordinates,
            key=lambda key: (coordinates[key][0] - lat) ** 2 + (coordinates[key][1] - lon) ** 2,
        )
        return per_location.get(location_id, default)()

    return httpx.Client(transport=httpx.MockTransport(handle))


def _run_as_ingestor(url: str, client: httpx.Client, today: dt.date = TODAY) -> int:
    engine = create_engine(url, connect_args={"options": "-c role=ingestor"})
    try:
        return ingest_weather_forecast(engine, client, today, base_delay=0)
    finally:
        engine.dispose()


def _stored(url: str, where: str = "TRUE") -> list[tuple]:
    return _query(
        url,
        f"SELECT {STORED_COLUMNS} FROM raw.weather_forecast WHERE {where} "
        "ORDER BY location_id, issued_at, target_date",
    )


@pytest.fixture
def forecast_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database


# ---------------------------------------------------------------------------
# issue_date (no database)
# ---------------------------------------------------------------------------


# Case 13
def test_issue_date_before_sao_paulo_midnight_is_the_previous_day():
    now = dt.datetime(2026, 11, 8, 2, 30, tzinfo=dt.UTC)

    assert issue_date(now) == dt.date(2026, 11, 7)


# Case 14
def test_issue_date_at_sao_paulo_midnight_is_the_same_day():
    now = dt.datetime(2026, 11, 8, 3, 0, tzinfo=dt.UTC)

    assert issue_date(now) == dt.date(2026, 11, 8)


# Case 15
def test_issue_date_rejects_naive_datetime():
    with pytest.raises(ValueError):
        issue_date(dt.datetime(2026, 11, 8, 12, 0))


# ---------------------------------------------------------------------------
# Job (database)
# ---------------------------------------------------------------------------


# Case 16
@pytest.mark.db
def test_list_locations_returns_the_four_locations_in_order(forecast_database):
    expected = _query(
        forecast_database, "SELECT location_id, lat, lon FROM ref.locations ORDER BY location_id"
    )
    engine = build_engine(forecast_database)
    try:
        with engine.connect() as connection:
            locations = list_locations(connection)
    finally:
        engine.dispose()

    assert [location.location_id for location in locations] == LOCATION_IDS
    assert all(isinstance(location, Location) for location in locations)
    assert [(loc.location_id, loc.lat, loc.lon) for loc in locations] == expected


# Case 17
@pytest.mark.db
def test_first_run_inserts_seven_horizons_for_each_location(forecast_database):
    inserted = _run_as_ingestor(forecast_database, _client(forecast_database))

    assert inserted == 28
    rows = _stored(forecast_database)
    assert len(rows) == 28
    assert {row[1] for row in rows} == {TODAY}
    for location_id in LOCATION_IDS:
        own = [row for row in rows if row[0] == location_id]
        assert [row[3] for row in own] == list(range(1, 8))
        assert [row[2] for row in own] == [TODAY + dt.timedelta(days=n) for n in range(1, 8)]
    assert all(row[9] is not None for row in rows)


# Case 18
@pytest.mark.db
def test_second_run_same_day_keeps_the_first_snapshot(forecast_database):
    _run_as_ingestor(forecast_database, _client(forecast_database))
    first = _stored(forecast_database)

    changed = _client(forecast_database, default=_ok(_payload(temp_max_delta=5.0)))
    inserted = _run_as_ingestor(forecast_database, changed)

    assert inserted == 0
    second = _stored(forecast_database)
    assert len(second) == 28
    assert second == first


# Case 19
@pytest.mark.db
def test_next_day_adds_a_new_snapshot_and_leaves_the_old_one_intact(forecast_database):
    _run_as_ingestor(forecast_database, _client(forecast_database))
    first = _stored(forecast_database)

    next_day = TODAY + dt.timedelta(days=1)
    shifted = _client(forecast_database, default=_ok(_payload(day_shift=1)))
    inserted = _run_as_ingestor(forecast_database, shifted, today=next_day)

    assert inserted == 28
    assert len(_stored(forecast_database)) == 56
    assert _stored(forecast_database, f"issued_at = '{TODAY.isoformat()}'") == first
    assert len(_stored(forecast_database, f"issued_at = '{next_day.isoformat()}'")) == 28


# Case 20
@pytest.mark.db
def test_network_failure_for_one_location_saves_the_others_and_raises(forecast_database):
    client = _client(forecast_database, per_location={"recife": _unavailable})

    with pytest.raises(PartialIngestionError) as error_info:
        _run_as_ingestor(forecast_database, client)

    assert "recife" in str(error_info.value)
    rows = _stored(forecast_database)
    assert len(rows) == 21
    assert {row[0] for row in rows} == {"belem", "porto_alegre", "sao_paulo"}
    for location_id in ("belem", "porto_alegre", "sao_paulo"):
        assert len([row for row in rows if row[0] == location_id]) == 7


# Case 21
@pytest.mark.db
def test_rerun_after_partial_failure_completes_the_missing_location(forecast_database):
    failing = _client(forecast_database, per_location={"recife": _unavailable})
    with pytest.raises(PartialIngestionError):
        _run_as_ingestor(forecast_database, failing)
    partial = _stored(forecast_database)

    _run_as_ingestor(forecast_database, _client(forecast_database))

    rows = _stored(forecast_database)
    assert len(rows) == 28
    assert [row for row in rows if row[0] != "recife"] == partial


# Case 22
@pytest.mark.db
def test_invalid_response_for_one_location_saves_the_others_and_raises(forecast_database):
    bad = _payload()
    bad["daily_units"]["wind_speed_10m_max"] = "m/s"
    client = _client(forecast_database, per_location={"belem": _ok(bad)})

    with pytest.raises(PartialIngestionError) as error_info:
        _run_as_ingestor(forecast_database, client)

    assert "belem" in str(error_info.value)
    rows = _stored(forecast_database)
    assert len(rows) == 21
    assert "belem" not in {row[0] for row in rows}


# Case 23
@pytest.mark.db
def test_out_of_range_value_is_stored_and_then_fails_the_check(forecast_database):
    outlier = _payload()
    outlier["daily"]["temperature_2m_max"][3] = 80
    client = _client(forecast_database, per_location={"sao_paulo": _ok(outlier)})

    with pytest.raises(CheckFailed) as error_info:
        _run_as_ingestor(forecast_database, client)

    assert "temp_max" in str(error_info.value)
    rows = _stored(forecast_database)
    assert len(rows) == 28
    assert 80.0 in {row[4] for row in rows}


# Case 24
@pytest.mark.db
def test_all_locations_failing_over_a_partial_snapshot_lists_all_and_changes_nothing(
    forecast_database,
):
    for location_id in ("belem", "porto_alegre", "sao_paulo"):
        for n in range(1, 8):
            target = TODAY + dt.timedelta(days=n)
            engine = build_engine(forecast_database)
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO raw.weather_forecast (location_id, issued_at, "
                            "target_date, temp_max, temp_min, precip_mm, wind_speed_max, "
                            "humidity_mean, ingested_at) VALUES (:location_id, :issued_at, "
                            ":target_date, 25, 15, 1, 10, 80, now())"
                        ),
                        {"location_id": location_id, "issued_at": TODAY, "target_date": target},
                    )
            finally:
                engine.dispose()
    before = _stored(forecast_database)
    assert len(before) == 21

    client = _client(forecast_database, default=_unavailable)
    with pytest.raises(PartialIngestionError) as error_info:
        _run_as_ingestor(forecast_database, client)

    message = str(error_info.value)
    for location_id in LOCATION_IDS:
        assert location_id in message
    assert _stored(forecast_database) == before


# ---------------------------------------------------------------------------
# CLI (no database)
# ---------------------------------------------------------------------------


def _effective_code(argv: list[str]) -> int:
    from ingestion.cli import main

    try:
        code = main(argv)
    except SystemExit as exit_info:
        code = exit_info.code
    return 0 if code is None else code


DUMMY_DATABASE_URL = "postgresql+psycopg://user:secret@127.0.0.1:1/none"


# Case 25
def test_cli_returns_one_when_the_job_raises_check_failed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)

    def failing_job(*args, **kwargs) -> int:
        raise CheckFailed("expected 28 rows, got 21")

    monkeypatch.setattr("ingestion.jobs.ingest_weather_forecast", failing_job)

    assert _effective_code(["weather-forecast"]) == 1


# Case 26
def test_cli_returns_zero_and_passes_issue_date_to_the_job(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)
    received: list[dt.date] = []

    def fake_job(*args, **kwargs) -> int:
        received.append(kwargs["today"] if "today" in kwargs else args[2])
        return 28

    monkeypatch.setattr("ingestion.jobs.ingest_weather_forecast", fake_job)
    monkeypatch.setattr("ingestion.jobs.issue_date", lambda *args, **kwargs: dt.date(2026, 11, 8))

    assert _effective_code(["weather-forecast"]) == 0
    assert received == [dt.date(2026, 11, 8)]


# Case 27
def test_cli_without_database_url_returns_one_and_names_the_variable(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("ingestion.jobs.ingest_weather_forecast", lambda *a, **k: 28)

    assert _effective_code(["weather-forecast"]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err


# Case 28
def test_cli_rejects_a_date_argument_with_usage_error():
    assert _effective_code(["weather-forecast", "--date", "2026-11-08"]) == 2
