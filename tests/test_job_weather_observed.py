"""Tests for the ``weather-observed`` job (plan 26, cases 17 to 43).

Cases 17 to 32 carry the ``db`` marker: they run the job as the ``ingestor`` role against a
migrated ``fresh_database`` and a ``httpx.MockTransport`` that builds the archive response for
the ``start_date``/``end_date`` of each request. Case 33 and the CLI cases 34 to 43 need no
database: the job and ``issue_date`` are replaced, except in case 42, which runs the real job and
fails before connecting. No test touches the network.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator

import httpx
import pytest
from alembic import command
from sqlalchemy import create_engine, text

from ingestion.checks import CheckFailed
from ingestion.db import build_engine
from ingestion.jobs import PartialIngestionError, ingest_weather_observed
from tests.conftest import alembic_config

END = dt.date(2026, 11, 7)
START = END - dt.timedelta(days=9)
LOCATION_IDS = ["belem", "porto_alegre", "recife", "sao_paulo"]
UNITS = {
    "time": "iso8601",
    "temperature_2m_max": "°C",
    "temperature_2m_min": "°C",
    "precipitation_sum": "mm",
    "wind_speed_10m_max": "km/h",
    "relative_humidity_2m_mean": "%",
}
VALUES = {
    "temperature_2m_max": 30.0,
    "temperature_2m_min": 20.0,
    "precipitation_sum": 1.0,
    "wind_speed_10m_max": 10.0,
    "relative_humidity_2m_mean": 70.0,
}
STORED_COLUMNS = (
    'location_id, "date", temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean, ingested_at'
)

Payload = dict
Mutation = Callable[[Payload], None]
Responder = Callable[[httpx.Request], httpx.Response]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _days(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + dt.timedelta(days=n) for n in range((last - first).days + 1)]


def _payload(first: dt.date, last: dt.date) -> Payload:
    """Archive response for ``first..last`` with the plausible fixed values."""
    days = _days(first, last)
    return {
        "latitude": 0.0,
        "longitude": 0.0,
        "timezone": "America/Sao_Paulo",
        "daily_units": dict(UNITS),
        "daily": {
            "time": [day.isoformat() for day in days],
            **{name: [value] * len(days) for name, value in VALUES.items()},
        },
    }


def _answer(*mutations: Mutation) -> Responder:
    """Responder that builds the payload for the requested interval and applies the mutations."""

    def respond(request: httpx.Request) -> httpx.Response:
        first = dt.date.fromisoformat(request.url.params["start_date"])
        last = dt.date.fromisoformat(request.url.params["end_date"])
        payload = _payload(first, last)
        for mutation in mutations:
            mutation(payload)
        return httpx.Response(200, json=payload)

    return respond


def _status(code: int) -> Responder:
    return lambda request: httpx.Response(code)


def _bad_request(request: httpx.Request) -> httpx.Response:
    return httpx.Response(400, json={"error": True, "reason": "Parameter is out of range"})


def _position(payload: Payload, day: dt.date) -> int:
    return payload["daily"]["time"].index(day.isoformat())


def _null_days(*days: dt.date) -> Mutation:
    def mutate(payload: Payload) -> None:
        for day in days:
            index = _position(payload, day)
            for name in VALUES:
                payload["daily"][name][index] = None

    return mutate


def _null_last_days(count: int) -> Mutation:
    def mutate(payload: Payload) -> None:
        for name in VALUES:
            for index in range(
                len(payload["daily"]["time"]) - count, len(payload["daily"]["time"])
            ):
                payload["daily"][name][index] = None

    return mutate


def _set_value(variable: str, day: dt.date, value) -> Mutation:
    def mutate(payload: Payload) -> None:
        payload["daily"][variable][_position(payload, day)] = value

    return mutate


def _set_unit(variable: str, unit: str) -> Mutation:
    def mutate(payload: Payload) -> None:
        payload["daily_units"][variable] = unit

    return mutate


def _set_time(index: int, value) -> Mutation:
    def mutate(payload: Payload) -> None:
        payload["daily"]["time"][index] = value

    return mutate


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


def _coordinates(url: str) -> dict[str, tuple[float, float]]:
    rows = _query(url, "SELECT location_id, lat, lon FROM ref.locations")
    return {location_id: (lat, lon) for location_id, lat, lon in rows}


class Source:
    """Mock archive: answers by the location nearest to the request; records the requests."""

    def __init__(
        self,
        url: str,
        default: Responder | None = None,
        per_location: dict[str, Responder] | None = None,
    ) -> None:
        self.coordinates = _coordinates(url)
        self.default = default or _answer()
        self.per_location = per_location or {}
        self.requests: list[tuple[str, httpx.Request]] = []
        self.client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        lat = float(request.url.params["latitude"])
        lon = float(request.url.params["longitude"])
        location_id = min(
            self.coordinates,
            key=lambda key: (
                (self.coordinates[key][0] - lat) ** 2 + (self.coordinates[key][1] - lon) ** 2
            ),
        )
        self.requests.append((location_id, request))
        return self.per_location.get(location_id, self.default)(request)

    def requests_for(self, location_id: str) -> list[httpx.Request]:
        return [request for key, request in self.requests if key == location_id]


def _stored(url: str, where: str = "TRUE") -> list[tuple]:
    return _query(
        url,
        f"SELECT {STORED_COLUMNS} FROM raw.weather_observed WHERE {where} "
        'ORDER BY location_id, "date"',
    )


def _values(rows: list[tuple]) -> list[tuple]:
    """Rows without ``ingested_at``."""
    return [row[:-1] for row in rows]


def _run_as_ingestor(
    url: str,
    source: Source,
    start: dt.date = START,
    end: dt.date = END,
    **kwargs,
) -> int:
    engine = create_engine(url, connect_args={"options": "-c role=ingestor"})
    try:
        return ingest_weather_observed(engine, source.client, start, end, base_delay=0, **kwargs)
    finally:
        engine.dispose()


@pytest.fixture
def observed_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database


# ---------------------------------------------------------------------------
# Job (database)
# ---------------------------------------------------------------------------


# Case 17
@pytest.mark.db
def test_window_run_writes_ten_days_per_location_with_one_request_each(observed_database):
    source = Source(observed_database)

    written = _run_as_ingestor(observed_database, source)

    assert written == 40
    rows = _stored(observed_database)
    assert len(rows) == 40
    for location_id in LOCATION_IDS:
        dates = [row[1] for row in rows if row[0] == location_id]
        assert dates == _days(START, END)
    assert all(row[-1] is not None for row in rows)
    assert len(source.requests) == 4
    assert sorted(key for key, _ in source.requests) == LOCATION_IDS
    for _, request in source.requests:
        assert request.url.params["start_date"] == "2026-10-29"
        assert request.url.params["end_date"] == "2026-11-07"


# Case 18
@pytest.mark.db
def test_second_run_with_the_same_responses_keeps_rows_and_values(observed_database):
    _run_as_ingestor(observed_database, Source(observed_database))
    first = _stored(observed_database)

    _run_as_ingestor(observed_database, Source(observed_database))

    second = _stored(observed_database)
    assert len(second) == 40
    assert _values(second) == _values(first)


# Case 19
@pytest.mark.db
def test_value_corrected_by_the_source_is_rewritten_and_refreshes_ingested_at(observed_database):
    _run_as_ingestor(observed_database, Source(observed_database))
    first = _stored(observed_database)

    revised = Source(
        observed_database,
        per_location={
            "recife": _answer(_set_value("precipitation_sum", dt.date(2026, 11, 5), 7.5))
        },
    )
    _run_as_ingestor(observed_database, revised)

    second = _stored(observed_database)
    assert len(second) == 40
    key = ("recife", dt.date(2026, 11, 5))
    changed = [row for row in second if row[:2] == key]
    original = [row for row in first if row[:2] == key]
    assert changed[0][4] == 7.5
    assert changed[0][-1] > original[0][-1]
    assert _values([row for row in second if row[:2] != key]) == _values(
        [row for row in first if row[:2] != key]
    )


# Case 20
@pytest.mark.db
def test_source_delay_within_the_limit_writes_the_published_days_and_passes(observed_database):
    source = Source(observed_database, _answer(_null_last_days(5)))

    written = _run_as_ingestor(observed_database, source)

    assert written == 20
    rows = _stored(observed_database)
    assert len(rows) == 20
    assert max(row[1] for row in rows) == dt.date(2026, 11, 2)


# Case 21
@pytest.mark.db
def test_source_delay_beyond_a_tighter_limit_writes_then_fails_as_stale(observed_database):
    source = Source(observed_database, _answer(_null_last_days(5)))

    with pytest.raises(CheckFailed) as error_info:
        _run_as_ingestor(observed_database, source, max_delay_days=3)

    assert "stale" in str(error_info.value)
    assert len(_stored(observed_database)) == 20


# Case 22
@pytest.mark.db
def test_reread_is_limited_to_the_interval_and_ignores_older_rows(observed_database):
    _execute(
        observed_database,
        'INSERT INTO raw.weather_observed (location_id, "date", temp_max, ingested_at) '
        "VALUES ('sao_paulo', '2026-10-20', 80.0, now())",
    )
    before = _stored(observed_database, "\"date\" = '2026-10-20'")
    assert len(before) == 1

    written = _run_as_ingestor(observed_database, Source(observed_database))

    assert written == 40
    assert _stored(observed_database, "\"date\" = '2026-10-20'") == before
    assert len(_stored(observed_database)) == 41


# Case 23
@pytest.mark.db
def test_location_with_repeated_503_fails_partially_and_the_others_are_written(observed_database):
    source = Source(observed_database, per_location={"belem": _status(503)})

    with pytest.raises(PartialIngestionError) as error_info:
        _run_as_ingestor(observed_database, source)

    assert "belem" in str(error_info.value)
    rows = _stored(observed_database)
    assert len(rows) == 30
    assert {row[0] for row in rows} == {"porto_alegre", "recife", "sao_paulo"}
    assert len(source.requests_for("belem")) == 3


# Case 24
@pytest.mark.db
def test_run_after_a_partial_failure_completes_the_table_and_keeps_earlier_rows(
    observed_database,
):
    failing = Source(observed_database, per_location={"belem": _status(503)})
    with pytest.raises(PartialIngestionError):
        _run_as_ingestor(observed_database, failing)
    first = _stored(observed_database)

    _run_as_ingestor(observed_database, Source(observed_database))

    second = _stored(observed_database)
    assert len(second) == 40
    assert _values([row for row in second if row[0] != "belem"]) == _values(first)


# Case 25
@pytest.mark.db
def test_client_error_400_fails_the_location_without_retry(observed_database):
    source = Source(observed_database, per_location={"recife": _bad_request})

    with pytest.raises(PartialIngestionError) as error_info:
        _run_as_ingestor(observed_database, source)

    assert "recife" in str(error_info.value)
    assert len(_stored(observed_database)) == 30
    assert len(source.requests_for("recife")) == 1


# Case 26
@pytest.mark.db
def test_unexpected_unit_fails_only_that_location(observed_database):
    source = Source(
        observed_database,
        per_location={"recife": _answer(_set_unit("wind_speed_10m_max", "m/s"))},
    )

    with pytest.raises(PartialIngestionError) as error_info:
        _run_as_ingestor(observed_database, source)

    assert "recife" in str(error_info.value)
    assert len(_stored(observed_database)) == 30


# Case 27
@pytest.mark.db
def test_malformed_values_fail_their_locations_without_a_type_error(observed_database):
    source = Source(
        observed_database,
        per_location={
            "porto_alegre": _answer(_set_time(3, None)),
            "sao_paulo": _answer(_set_value("temperature_2m_max", dt.date(2026, 11, 1), "abc")),
        },
    )

    with pytest.raises(PartialIngestionError) as error_info:
        _run_as_ingestor(observed_database, source)

    message = str(error_info.value)
    assert "porto_alegre" in message
    assert "sao_paulo" in message
    rows = _stored(observed_database)
    assert len(rows) == 20
    assert {row[0] for row in rows} == {"belem", "recife"}


# Case 28
@pytest.mark.db
def test_all_null_day_in_the_middle_is_a_continuity_failure_after_writing(observed_database):
    day = dt.date(2026, 11, 2)
    source = Source(observed_database, per_location={"sao_paulo": _answer(_null_days(day))})

    with pytest.raises(CheckFailed) as error_info:
        _run_as_ingestor(observed_database, source)

    message = str(error_info.value)
    assert "sao_paulo" in message
    assert "2026-11-02" in message
    assert len(_stored(observed_database)) == 39


# Case 29
@pytest.mark.db
def test_temp_min_above_temp_max_is_stored_and_then_fails_the_check(observed_database):
    day = dt.date(2026, 11, 1)
    source = Source(
        observed_database,
        per_location={
            "belem": _answer(
                _set_value("temperature_2m_min", day, 25.0),
                _set_value("temperature_2m_max", day, 20.0),
            )
        },
    )

    with pytest.raises(CheckFailed) as error_info:
        _run_as_ingestor(observed_database, source)

    assert "temp_min must not exceed temp_max" in str(error_info.value)
    stored = _stored(observed_database)
    assert len(stored) == 40
    bad = [row for row in stored if row[:2] == ("belem", day)]
    assert (bad[0][2], bad[0][3]) == (20.0, 25.0)


# Case 30
@pytest.mark.db
def test_location_failure_and_check_failure_are_reported_together(observed_database):
    source = Source(
        observed_database,
        per_location={
            "belem": _status(503),
            "sao_paulo": _answer(_set_value("temperature_2m_max", dt.date(2026, 11, 1), 80.0)),
        },
    )

    with pytest.raises(PartialIngestionError) as error_info:
        _run_as_ingestor(observed_database, source)

    message = str(error_info.value)
    assert "belem" in message
    assert "temp_max" in message
    assert len(_stored(observed_database)) == 30


# Case 31
@pytest.mark.db
def test_all_locations_failing_leaves_the_existing_rows_untouched(observed_database):
    _run_as_ingestor(observed_database, Source(observed_database))
    first = _stored(observed_database)
    assert len(first) == 40

    with pytest.raises(PartialIngestionError) as error_info:
        _run_as_ingestor(observed_database, Source(observed_database, _status(503)))

    message = str(error_info.value)
    for location_id in LOCATION_IDS:
        assert location_id in message
    assert _stored(observed_database) == first


# Case 32
@pytest.mark.db
def test_backfill_of_a_closed_year_uses_one_request_per_location_and_passes(observed_database):
    source = Source(observed_database)

    written = _run_as_ingestor(
        observed_database, source, start=dt.date(2015, 1, 1), end=dt.date(2015, 12, 31)
    )

    assert written == 1460
    assert len(_stored(observed_database)) == 1460
    assert len(source.requests) == 4
    assert sorted(key for key, _ in source.requests) == LOCATION_IDS
    for _, request in source.requests:
        assert request.url.params["start_date"] == "2015-01-01"
        assert request.url.params["end_date"] == "2015-12-31"


# Case 33 (no database: it must fail before any connection or request)
def test_start_after_end_raises_value_error_before_any_request():
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    engine = create_engine("postgresql+psycopg://user:secret@127.0.0.1:1/none")
    try:
        with pytest.raises(ValueError) as error_info:
            ingest_weather_observed(
                engine, client, dt.date(2026, 11, 8), dt.date(2026, 11, 1), base_delay=0
            )
    finally:
        engine.dispose()

    message = str(error_info.value)
    assert "2026-11-08" in message
    assert "2026-11-01" in message
    assert requests == []


# ---------------------------------------------------------------------------
# CLI (no database)
# ---------------------------------------------------------------------------

DUMMY_DATABASE_URL = "postgresql+psycopg://user:secret@127.0.0.1:1/none"
TODAY = dt.date(2026, 11, 8)


def _effective_code(argv: list[str]) -> int:
    from ingestion.cli import main

    try:
        code = main(argv)
    except SystemExit as exit_info:
        code = exit_info.code
    return 0 if code is None else code


def _fake_job(monkeypatch) -> list[tuple[dt.date, dt.date, float | None]]:
    """Replace the job and ``issue_date``; return what the job receives.

    Each item is ``(start, end, read timeout of the client)``.
    """
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)
    received: list[tuple[dt.date, dt.date, float | None]] = []

    def fake_job(engine, client, start, end, **kwargs) -> int:
        received.append((start, end, client.timeout.read))
        return 0

    monkeypatch.setattr("ingestion.jobs.ingest_weather_observed", fake_job)
    monkeypatch.setattr("ingestion.jobs.issue_date", lambda *args, **kwargs: TODAY)
    return received


# Case 34
def test_cli_default_is_a_ten_day_window_ending_yesterday(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["weather-observed"]) == 0
    assert received == [(dt.date(2026, 10, 29), dt.date(2026, 11, 7), 30)]


# Case 35
def test_cli_days_sets_the_window_length_ending_yesterday(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["weather-observed", "--days", "3"]) == 0
    assert received == [(dt.date(2026, 11, 5), dt.date(2026, 11, 7), 30)]


# Case 36
def test_cli_start_and_end_are_passed_through_with_the_backfill_timeout(monkeypatch):
    received = _fake_job(monkeypatch)

    assert (
        _effective_code(["weather-observed", "--start", "2015-01-01", "--end", "2015-12-31"]) == 0
    )
    assert received == [(dt.date(2015, 1, 1), dt.date(2015, 12, 31), 120)]


# Case 37
def test_cli_start_alone_ends_yesterday_with_the_backfill_timeout(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["weather-observed", "--start", "2015-01-01"]) == 0
    assert received == [(dt.date(2015, 1, 1), dt.date(2026, 11, 7), 120)]


# Case 38
def test_cli_end_alone_gives_a_ten_day_window_ending_there(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["weather-observed", "--end", "2026-01-31"]) == 0
    assert received == [(dt.date(2026, 1, 22), dt.date(2026, 1, 31), 30)]


# Case 39
@pytest.mark.parametrize(("days", "timeout"), [("10", 30), ("11", 120)])
def test_cli_timeout_switches_when_the_interval_exceeds_ten_days(monkeypatch, days, timeout):
    received = _fake_job(monkeypatch)

    assert _effective_code(["weather-observed", "--days", days]) == 0
    assert [item[2] for item in received] == [timeout]


# Case 40
@pytest.mark.parametrize(
    "argv",
    [
        ["weather-observed", "--start", "2026-11-01", "--days", "5"],
        ["weather-observed", "--days", "0"],
        ["weather-observed", "--start", "2026-13-01"],
    ],
)
def test_cli_rejects_invalid_arguments_with_usage_error(monkeypatch, argv):
    received = _fake_job(monkeypatch)

    assert _effective_code(argv) == 2
    assert received == []


# Case 41
@pytest.mark.parametrize(
    "error",
    [
        CheckFailed("stale: sao_paulo: last date 2026-10-01 is older than 2026-10-31"),
        PartialIngestionError("observed weather failed for locations: belem"),
    ],
)
def test_cli_returns_one_when_the_job_raises(monkeypatch, error):
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)

    def failing_job(*args, **kwargs) -> int:
        raise error

    monkeypatch.setattr("ingestion.jobs.ingest_weather_observed", failing_job)
    monkeypatch.setattr("ingestion.jobs.issue_date", lambda *args, **kwargs: TODAY)

    assert _effective_code(["weather-observed"]) == 1


# Case 42
def test_cli_returns_one_with_value_error_when_start_is_after_end(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)

    code = _effective_code(["weather-observed", "--start", "2026-02-01", "--end", "2026-01-01"])

    assert code == 1
    assert "ValueError" in capsys.readouterr().err


# Case 43
def test_cli_without_database_url_returns_one_and_names_the_variable(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("ingestion.jobs.ingest_weather_observed", lambda *a, **k: 0)
    monkeypatch.setattr("ingestion.jobs.issue_date", lambda *args, **kwargs: TODAY)

    assert _effective_code(["weather-observed"]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err
