"""Tests for the ``ons-load`` job (plan 22, cases 11 to 34).

Cases 11 to 23 carry the ``db`` marker: they run the job as the ``ingestor`` role against a
migrated ``fresh_database`` and a ``httpx.MockTransport`` that answers by the year in the URL
(``CARGA_ENERGIA_<year>.parquet``). Case 24 and the CLI cases 25 to 34 need no database: the job
and ``issue_date`` are replaced, except in case 33, which runs the real job and fails before
connecting. No test touches the network.
"""

from __future__ import annotations

import datetime as dt
import io
import re
from collections.abc import Callable, Iterator

import httpx
import pandas as pd
import pytest
from alembic import command
from sqlalchemy import create_engine, text

from ingestion.checks import CheckFailed
from ingestion.db import build_engine
from ingestion.http import NetworkError
from ingestion.jobs import ingest_ons_load
from tests.conftest import alembic_config

LOADS = {"SE": 40000.0, "S": 12000.0, "NE": 11000.0, "N": 7000.0}
SUBSYSTEM_NAMES = {
    "N": "Norte",
    "NE": "Nordeste",
    "S": "Sul",
    "SE": "Sudeste/Centro-Oeste",
}
STORED_COLUMNS = 'subsystem, "date", load_avg_mw, ingested_at'
YEAR_IN_PATH = re.compile(r"CARGA_ENERGIA_(\d{4})\.parquet$")

START = dt.date(2026, 10, 10)
END = dt.date(2026, 11, 8)

Row = tuple[str, dt.date, float]
FileFactory = Callable[[], httpx.Response]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _grid(first: dt.date, last: dt.date) -> list[Row]:
    """Every day from ``first`` to ``last`` times the four subsystems."""
    rows: list[Row] = []
    day = first
    while day <= last:
        rows.extend((code, day, load) for code, load in LOADS.items())
        day += dt.timedelta(days=1)
    return rows


def _parquet(rows: list[Row]) -> bytes:
    """Parquet with the four columns and dtypes of the ONS file."""
    frame = pd.DataFrame(
        {
            "id_subsistema": pd.Series([r[0] for r in rows], dtype="object"),
            "nom_subsistema": pd.Series([SUBSYSTEM_NAMES.get(r[0], r[0]) for r in rows]),
            "din_instante": pd.Series(
                [dt.datetime.combine(r[1], dt.time()) for r in rows], dtype="datetime64[ns]"
            ),
            "val_cargaenergiamwmed": pd.Series([r[2] for r in rows], dtype="float64"),
        }
    )
    buffer = io.BytesIO()
    frame.to_parquet(buffer)
    return buffer.getvalue()


def _file(rows: list[Row]) -> FileFactory:
    content = _parquet(rows)
    return lambda: httpx.Response(200, content=content)


def _status(code: int) -> FileFactory:
    return lambda: httpx.Response(code)


def _revised(rows: list[Row], subsystem: str, day: dt.date, value: float) -> list[Row]:
    return [(c, d, value if (c, d) == (subsystem, day) else v) for c, d, v in rows]


class Source:
    """Mock ONS bucket: answers by year, 404 for years without a file, records the requests."""

    def __init__(self, files: dict[int, FileFactory]) -> None:
        self.files = files
        self.requests: list[httpx.Request] = []
        self.client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        match = YEAR_IN_PATH.search(request.url.path)
        assert match is not None, f"unexpected URL {request.url}"
        factory = self.files.get(int(match.group(1)))
        return factory() if factory is not None else httpx.Response(404)

    @property
    def years(self) -> list[int]:
        return [int(YEAR_IN_PATH.search(r.url.path).group(1)) for r in self.requests]


def _query(url: str, statement: str) -> list[tuple]:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(statement))]
    finally:
        engine.dispose()


def _stored(url: str, where: str = "TRUE") -> list[tuple]:
    return _query(
        url,
        f'SELECT {STORED_COLUMNS} FROM raw.ons_daily_load WHERE {where} ORDER BY "date", subsystem',
    )


def _values(rows: list[tuple]) -> list[tuple]:
    """Rows without ``ingested_at``."""
    return [row[:3] for row in rows]


def _run_as_ingestor(url: str, source: Source, start: dt.date = START, end: dt.date = END) -> int:
    engine = create_engine(url, connect_args={"options": "-c role=ingestor"})
    try:
        return ingest_ons_load(engine, source.client, start, end, base_delay=0)
    finally:
        engine.dispose()


@pytest.fixture
def load_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database


def _september_to_november() -> list[Row]:
    return _grid(dt.date(2026, 9, 1), dt.date(2026, 11, 5))


# ---------------------------------------------------------------------------
# Job (database)
# ---------------------------------------------------------------------------


# Case 11
@pytest.mark.db
def test_window_run_writes_only_days_from_start_and_stamps_ingested_at(load_database):
    source = Source({2026: _file(_september_to_november())})

    written = _run_as_ingestor(load_database, source)

    assert written == 108
    rows = _stored(load_database)
    assert len(rows) == 108
    assert min(row[1] for row in rows) == START
    assert max(row[1] for row in rows) == dt.date(2026, 11, 5)
    assert all(row[3] is not None for row in rows)
    assert len(source.requests) == 1
    assert source.requests[0].url.path.endswith("CARGA_ENERGIA_2026.parquet")


# Case 12
@pytest.mark.db
def test_second_run_with_the_same_file_keeps_rows_and_values(load_database):
    source = Source({2026: _file(_september_to_november())})
    _run_as_ingestor(load_database, source)
    first = _stored(load_database)

    _run_as_ingestor(load_database, source)

    second = _stored(load_database)
    assert len(second) == 108
    assert _values(second) == _values(first)


# Case 13
@pytest.mark.db
def test_ons_revision_updates_the_value_and_refreshes_ingested_at(load_database):
    rows = _september_to_november()
    _run_as_ingestor(load_database, Source({2026: _file(rows)}))
    first = _stored(load_database)

    revised = _revised(rows, "SE", dt.date(2026, 10, 15), 40500.0)
    _run_as_ingestor(load_database, Source({2026: _file(revised)}))

    second = _stored(load_database)
    assert len(second) == 108
    key = ("SE", dt.date(2026, 10, 15))
    changed = [row for row in second if row[:2] == key]
    original = [row for row in first if row[:2] == key]
    assert changed[0][2] == 40500.0
    assert changed[0][3] > original[0][3]
    assert _values([row for row in second if row[:2] != key]) == _values(
        [row for row in first if row[:2] != key]
    )


# Case 14
@pytest.mark.db
def test_revision_before_start_is_not_written(load_database):
    rows = _september_to_november()
    _run_as_ingestor(load_database, Source({2026: _file(rows)}))

    revised = _revised(rows, "SE", dt.date(2026, 9, 15), 39000.0)
    _run_as_ingestor(load_database, Source({2026: _file(revised)}))

    assert _stored(load_database, "\"date\" = '2026-09-15'") == []
    assert len(_stored(load_database)) == 108


# Case 15
@pytest.mark.db
def test_window_across_new_year_reads_both_yearly_files(load_database):
    source = Source(
        {
            2026: _file(_grid(dt.date(2026, 12, 1), dt.date(2026, 12, 31))),
            2027: _file(_grid(dt.date(2027, 1, 1), dt.date(2027, 1, 3))),
        }
    )

    written = _run_as_ingestor(
        load_database, source, start=dt.date(2026, 12, 20), end=dt.date(2027, 1, 5)
    )

    assert sorted(source.years) == [2026, 2027]
    assert written == 60
    assert len(_stored(load_database)) == 60


# Case 16
@pytest.mark.db
def test_unpublished_new_year_file_is_tolerated_when_data_is_fresh(load_database, caplog):
    source = Source(
        {
            2026: _file(_grid(dt.date(2026, 11, 1), dt.date(2026, 12, 31))),
            2027: _status(404),
        }
    )

    with caplog.at_level("WARNING"):
        written = _run_as_ingestor(
            load_database, source, start=dt.date(2026, 12, 4), end=dt.date(2027, 1, 2)
        )

    assert written == 112
    assert len(_stored(load_database)) == 112
    assert any("2027" in record.getMessage() for record in caplog.records)


# Case 17
@pytest.mark.db
def test_unpublished_new_year_file_with_old_data_writes_then_fails_as_stale(load_database):
    source = Source(
        {
            2026: _file(_grid(dt.date(2026, 11, 1), dt.date(2026, 12, 26))),
            2027: _status(404),
        }
    )

    with pytest.raises(CheckFailed) as error_info:
        _run_as_ingestor(load_database, source, start=dt.date(2026, 12, 4), end=dt.date(2027, 1, 2))

    assert "stale" in str(error_info.value)
    assert len(_stored(load_database)) == 92


# Case 18
@pytest.mark.db
def test_missing_file_for_a_year_before_the_end_year_is_an_error(load_database):
    source = Source({2016: _file(_grid(dt.date(2016, 1, 1), dt.date(2016, 12, 31)))})

    with pytest.raises(httpx.HTTPStatusError) as error_info:
        _run_as_ingestor(
            load_database, source, start=dt.date(2015, 1, 1), end=dt.date(2016, 12, 31)
        )

    assert error_info.value.response.status_code == 404
    assert _stored(load_database) == []


# Case 19
@pytest.mark.db
def test_backfill_of_a_closed_year_passes_the_delay_check(load_database):
    source = Source({2015: _file(_grid(dt.date(2015, 1, 1), dt.date(2015, 12, 31)))})

    written = _run_as_ingestor(
        load_database, source, start=dt.date(2015, 1, 1), end=dt.date(2015, 12, 31)
    )

    assert written == 1460
    assert len(_stored(load_database)) == 1460


# Case 20
@pytest.mark.db
def test_day_with_three_subsystems_fails_the_check_and_keeps_the_rows(load_database):
    rows = [row for row in _september_to_november() if row[:2] != ("N", dt.date(2026, 10, 25))]

    with pytest.raises(CheckFailed) as error_info:
        _run_as_ingestor(load_database, Source({2026: _file(rows)}))

    assert "2026-10-25" in str(error_info.value)
    assert len(_stored(load_database)) == 107


# Case 21
@pytest.mark.db
def test_zero_load_is_stored_and_then_fails_the_check(load_database):
    rows = _revised(_september_to_november(), "S", dt.date(2026, 10, 20), 0.0)

    with pytest.raises(CheckFailed) as error_info:
        _run_as_ingestor(load_database, Source({2026: _file(rows)}))

    assert "load_avg_mw" in str(error_info.value)
    stored = _stored(load_database)
    assert len(stored) == 108
    assert 0.0 in {row[2] for row in stored}


# Case 22
@pytest.mark.db
def test_unknown_subsystem_in_the_file_raises_and_writes_nothing(load_database):
    rows = _september_to_november()
    rows[0] = ("SE/CO", rows[0][1], rows[0][2])

    with pytest.raises(ValueError):
        _run_as_ingestor(load_database, Source({2026: _file(rows)}))

    assert _stored(load_database) == []


# Case 23
@pytest.mark.db
def test_repeated_server_error_raises_network_error_and_writes_nothing(load_database):
    source = Source({2026: _status(503)})

    with pytest.raises(NetworkError):
        _run_as_ingestor(load_database, source)

    assert _stored(load_database) == []


# Case 24 (no database: it must fail before any connection)
def test_start_after_end_raises_value_error_before_any_request():
    source = Source({2026: _file(_september_to_november())})
    engine = create_engine("postgresql+psycopg://user:secret@127.0.0.1:1/none")
    try:
        with pytest.raises(ValueError) as error_info:
            ingest_ons_load(
                engine, source.client, dt.date(2026, 11, 8), dt.date(2026, 11, 1), base_delay=0
            )
    finally:
        engine.dispose()

    message = str(error_info.value)
    assert "2026-11-08" in message
    assert "2026-11-01" in message
    assert source.requests == []


# ---------------------------------------------------------------------------
# ONS source-gaps plan (2026-11-08), cases 36 to 38: 2015 file with text load and empty days
# ---------------------------------------------------------------------------

TextRow = tuple[str, dt.date, str]
GAP_DAY = dt.date(2015, 4, 9)


def _text_parquet(rows: list[TextRow]) -> bytes:
    """Parquet like ``_parquet`` but with the load as text, as in ONS files up to 2021."""
    frame = pd.DataFrame(
        {
            "id_subsistema": pd.Series([r[0] for r in rows], dtype="object"),
            "nom_subsistema": pd.Series([SUBSYSTEM_NAMES.get(r[0], r[0]) for r in rows]),
            "din_instante": pd.Series(
                [dt.datetime.combine(r[1], dt.time()) for r in rows], dtype="datetime64[ns]"
            ),
            "val_cargaenergiamwmed": pd.Series([r[2] for r in rows], dtype="object"),
        }
    )
    buffer = io.BytesIO()
    frame.to_parquet(buffer)
    return buffer.getvalue()


def _text_year_2015(empty: set[tuple[str, dt.date]]) -> FileFactory:
    """Full 2015 grid, load as text, with ``""`` for the given (subsystem, date) keys."""
    rows: list[TextRow] = [
        (code, day, "" if (code, day) in empty else str(load))
        for code, day, load in _grid(dt.date(2015, 1, 1), dt.date(2015, 12, 31))
    ]
    content = _text_parquet(rows)
    return lambda: httpx.Response(200, content=content)


def _backfill_2015(url: str, source: Source) -> int:
    return _run_as_ingestor(url, source, start=dt.date(2015, 1, 1), end=dt.date(2015, 12, 31))


# Case 36
@pytest.mark.db
def test_backfill_of_2015_with_the_empty_known_gap_day_passes(load_database):
    empty = {(code, GAP_DAY) for code in LOADS}
    source = Source({2015: _text_year_2015(empty)})

    written = _backfill_2015(load_database, source)

    assert written == 1456
    assert len(_stored(load_database)) == 1456
    assert _stored(load_database, "\"date\" = '2015-04-09'") == []
    assert len(source.requests) == 1
    assert source.requests[0].url.path.endswith("CARGA_ENERGIA_2015.parquet")


# Case 37
@pytest.mark.db
def test_backfill_of_2015_with_an_unknown_empty_day_writes_then_fails(load_database):
    other_day = dt.date(2015, 7, 1)
    empty = {(code, day) for code in LOADS for day in (GAP_DAY, other_day)}
    source = Source({2015: _text_year_2015(empty)})

    with pytest.raises(CheckFailed) as error_info:
        _backfill_2015(load_database, source)

    assert "2015-07-01" in str(error_info.value)
    assert len(_stored(load_database)) == 1452


# Case 38
@pytest.mark.db
def test_backfill_of_2015_with_a_partial_known_gap_day_writes_then_fails(load_database):
    empty = {(code, GAP_DAY) for code in ("SE", "S", "NE")}
    source = Source({2015: _text_year_2015(empty)})

    with pytest.raises(CheckFailed) as error_info:
        _backfill_2015(load_database, source)

    assert "2015-04-09" in str(error_info.value)
    assert len(_stored(load_database)) == 1457


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


def _fake_job(monkeypatch) -> list[tuple[dt.date, dt.date]]:
    """Replace the job and ``issue_date``; return the ``(start, end)`` pairs the job receives."""
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)
    received: list[tuple[dt.date, dt.date]] = []

    def fake_job(engine, client, start, end, **kwargs) -> int:
        received.append((start, end))
        return 0

    monkeypatch.setattr("ingestion.jobs.ingest_ons_load", fake_job)
    monkeypatch.setattr("ingestion.jobs.issue_date", lambda *args, **kwargs: TODAY)
    return received


# Case 25
def test_cli_default_is_a_thirty_day_window_ending_today(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["ons-load"]) == 0
    assert received == [(dt.date(2026, 10, 10), dt.date(2026, 11, 8))]


# Case 26
def test_cli_days_sets_the_window_length(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["ons-load", "--days", "10"]) == 0
    assert received == [(dt.date(2026, 10, 30), dt.date(2026, 11, 8))]


# Case 27
def test_cli_start_and_end_are_passed_through(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["ons-load", "--start", "2015-01-01", "--end", "2015-12-31"]) == 0
    assert received == [(dt.date(2015, 1, 1), dt.date(2015, 12, 31))]


# Case 28
def test_cli_end_alone_gives_a_thirty_day_window_ending_there(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["ons-load", "--end", "2026-01-31"]) == 0
    assert received == [(dt.date(2026, 1, 2), dt.date(2026, 1, 31))]


# Case 29
def test_cli_start_alone_ends_today(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["ons-load", "--start", "2026-11-01"]) == 0
    assert received == [(dt.date(2026, 11, 1), dt.date(2026, 11, 8))]


# Case 30
def test_cli_start_and_days_are_mutually_exclusive(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["ons-load", "--start", "2026-11-01", "--days", "5"]) == 2
    assert received == []


# Case 31
def test_cli_rejects_zero_days_with_usage_error(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["ons-load", "--days", "0"]) == 2
    assert received == []


# Case 31 (invalid date)
def test_cli_rejects_an_invalid_date_with_usage_error(monkeypatch):
    received = _fake_job(monkeypatch)

    assert _effective_code(["ons-load", "--start", "2026-13-01"]) == 2
    assert received == []


# Case 32
def test_cli_returns_one_when_the_job_raises_check_failed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)

    def failing_job(*args, **kwargs) -> int:
        raise CheckFailed("stale: last date 2026-10-01 is older than 2026-11-03")

    monkeypatch.setattr("ingestion.jobs.ingest_ons_load", failing_job)
    monkeypatch.setattr("ingestion.jobs.issue_date", lambda *args, **kwargs: TODAY)

    assert _effective_code(["ons-load"]) == 1


# Case 33
def test_cli_returns_one_with_value_error_when_start_is_after_end(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)

    code = _effective_code(["ons-load", "--start", "2026-02-01", "--end", "2026-01-01"])

    assert code == 1
    assert "ValueError" in capsys.readouterr().err


# Case 34
def test_cli_without_database_url_returns_one_and_names_the_variable(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("ingestion.jobs.ingest_ons_load", lambda *a, **k: 0)
    monkeypatch.setattr("ingestion.jobs.issue_date", lambda *args, **kwargs: TODAY)

    assert _effective_code(["ons-load"]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err
