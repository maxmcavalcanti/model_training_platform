"""Ingestion jobs."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import sqlalchemy

from ingestion.calendar_ref import build_calendar
from ingestion.checks import (
    CALENDAR_SCHEMA,
    WEATHER_FORECAST_SCHEMA,
    CheckFailed,
    check,
    check_ons_daily_load,
    check_weather_observed,
)
from ingestion.db import upsert
from ingestion.http import NetworkError
from ingestion.ons import fetch_load
from ingestion.openmeteo import (
    FORECAST_TIMEZONE,
    MAX_HORIZON_DAYS,
    Location,
    fetch_forecast,
    fetch_observed,
)

logger = logging.getLogger(__name__)

_FORECAST_TABLE = "raw.weather_forecast"
_FORECAST_KEYS = ["location_id", "issued_at", "target_date"]
_REREAD_STATEMENT = sqlalchemy.text(
    "SELECT location_id, issued_at, target_date, horizon_days, temp_max, temp_min, "
    "precip_mm, wind_speed_max, humidity_mean FROM raw.weather_forecast "
    "WHERE issued_at = :today"
)


class PartialIngestionError(RuntimeError):
    """Raised when the job saved what it could but some locations failed."""


def issue_date(now: datetime | None = None) -> date:
    """Return the snapshot day: the date of ``now`` in the forecast timezone."""
    if now is None:
        now = datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(ZoneInfo(FORECAST_TIMEZONE)).date()


def list_locations(conn: sqlalchemy.Connection) -> list[Location]:
    rows = conn.execute(
        sqlalchemy.text("SELECT location_id, lat, lon FROM ref.locations ORDER BY location_id")
    )
    return [Location(location_id=row[0], lat=row[1], lon=row[2]) for row in rows]


def ingest_weather_forecast(
    engine: sqlalchemy.Engine,
    client: httpx.Client,
    today: date,
    *,
    base_delay: float = 1.0,
) -> int:
    """Snapshot ``today``'s forecast for every location; return the rows inserted.

    Existing snapshots are never overwritten. A location that fails does not stop the
    others; the job still ends with an error naming the failed locations.
    """
    with engine.connect() as conn:
        locations = list_locations(conn)

    frames: list[pd.DataFrame] = []
    failed: list[str] = []
    for location in locations:
        try:
            frames.append(fetch_forecast(client, location, today, base_delay=base_delay))
        except (NetworkError, ValueError, httpx.HTTPError) as error:
            logger.error("forecast failed for %s: %s", location.location_id, error)
            failed.append(location.location_id)

    inserted = 0
    if frames:
        with engine.begin() as conn:
            inserted = upsert(
                conn,
                _FORECAST_TABLE,
                pd.concat(frames, ignore_index=True),
                keys=_FORECAST_KEYS,
                on_conflict="ignore",
            )

    with engine.connect() as conn:
        stored = pd.read_sql_query(_REREAD_STATEMENT, conn, params={"today": today})
    expected_rows = len(locations) * MAX_HORIZON_DAYS
    check_error: CheckFailed | None = None
    try:
        check(stored, WEATHER_FORECAST_SCHEMA, expected_rows=expected_rows)
    except CheckFailed as error:
        check_error = error

    if failed:
        message = f"forecast failed for locations: {', '.join(failed)}"
        if check_error is not None:
            message += f"; {check_error}"
        raise PartialIngestionError(message)
    if check_error is not None:
        raise check_error

    logger.info(
        "weather-forecast ok: %d locations, %d rows inserted, %d already existed",
        len(locations),
        inserted,
        expected_rows - inserted,
    )
    return inserted


_CALENDAR_REREAD_STATEMENT = sqlalchemy.text(
    'SELECT "date", weekday, is_national_holiday, holiday_name FROM ref.calendar '
    'WHERE "date" BETWEEN :start AND :end ORDER BY "date"'
)


def load_calendar(engine: sqlalchemy.Engine, start: date, end: date) -> int:
    """Upsert ref.calendar for ``start`` to ``end`` (inclusive) and check what was stored."""
    rows = build_calendar(start, end)
    with engine.begin() as conn:
        written = upsert(
            conn,
            "ref.calendar",
            rows,
            keys=["date"],
            on_conflict="update",
            stamp_ingested_at=False,
        )
        stored = pd.read_sql_query(
            _CALENDAR_REREAD_STATEMENT, conn, params={"start": start, "end": end}
        )
    check(stored, CALENDAR_SCHEMA, expected_rows=(end - start).days + 1)
    logger.info(
        "calendar ok: %d days from %s to %s, %d national holidays",
        len(stored),
        start,
        end,
        int(stored["is_national_holiday"].sum()),
    )
    return written


# Provisional until roadmap item 18 measures the ONS publication delay and revision depth.
ONS_WINDOW_DAYS = 30
ONS_MAX_DELAY_DAYS = 5

_ONS_TABLE = "raw.ons_daily_load"
_ONS_KEYS = ["subsystem", "date"]
_ONS_REREAD_STATEMENT = sqlalchemy.text(
    'SELECT subsystem, "date", load_avg_mw FROM raw.ons_daily_load '
    'WHERE "date" BETWEEN :start AND :end ORDER BY "date", subsystem'
)


def ingest_ons_load(
    engine: sqlalchemy.Engine,
    client: httpx.Client,
    start: date,
    end: date,
    *,
    max_delay_days: int = ONS_MAX_DELAY_DAYS,
    base_delay: float = 1.0,
) -> int:
    """Upsert ONS daily load for ``start`` to ``end`` (inclusive) and check what was stored."""
    if start > end:
        raise ValueError(f"start {start} is after end {end}")

    frames: list[pd.DataFrame] = []
    for year in range(start.year, end.year + 1):
        try:
            frames.append(fetch_load(client, year, base_delay=base_delay))
        except httpx.HTTPStatusError as error:
            if year == end.year and error.response.status_code == 404:
                logger.warning("ONS load file for %d not published yet (404)", year)
                continue
            raise

    written = 0
    if frames:
        loaded = pd.concat(frames, ignore_index=True)
        window = loaded[(loaded["date"] >= start) & (loaded["date"] <= end)]
        if not window.empty:
            with engine.begin() as conn:
                written = upsert(conn, _ONS_TABLE, window, keys=_ONS_KEYS, on_conflict="update")

    with engine.connect() as conn:
        stored = pd.read_sql_query(_ONS_REREAD_STATEMENT, conn, params={"start": start, "end": end})
    check_ons_daily_load(stored, start, end, max_delay_days)
    logger.info(
        "ons-load ok: %d rows written from %s to %s, last date %s",
        written,
        start,
        end,
        stored["date"].max(),
    )
    return written


# Provisional until roadmap item 18 measures the ERA5 delay and revisions (plan 24, D8).
OBSERVED_WINDOW_DAYS = 10
OBSERVED_MAX_DELAY_DAYS = 7
OBSERVED_END_LAG_DAYS = 1

_OBSERVED_TABLE = "raw.weather_observed"
_OBSERVED_KEYS = ["location_id", "date"]
_OBSERVED_REREAD_STATEMENT = sqlalchemy.text(
    'SELECT location_id, "date", temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean '
    'FROM raw.weather_observed WHERE "date" BETWEEN :start AND :end '
    'ORDER BY location_id, "date"'
)


def ingest_weather_observed(
    engine: sqlalchemy.Engine,
    client: httpx.Client,
    start: date,
    end: date,
    *,
    max_delay_days: int = OBSERVED_MAX_DELAY_DAYS,
    base_delay: float = 1.0,
) -> int:
    """Upsert observed weather for ``start`` to ``end`` (inclusive) and check what was stored.

    A location that fails does not stop the others; the job still ends with an error
    naming the failed locations.
    """
    if start > end:
        raise ValueError(f"start {start} is after end {end}")

    with engine.connect() as conn:
        locations = list_locations(conn)

    frames: list[pd.DataFrame] = []
    failed: list[str] = []
    for location in locations:
        try:
            frames.append(fetch_observed(client, location, start, end, base_delay=base_delay))
        except (NetworkError, ValueError, httpx.HTTPError) as error:
            logger.error("observed weather failed for %s: %s", location.location_id, error)
            failed.append(location.location_id)

    written = 0
    if frames:
        rows = pd.concat(frames, ignore_index=True)
        if not rows.empty:
            with engine.begin() as conn:
                written = upsert(
                    conn, _OBSERVED_TABLE, rows, keys=_OBSERVED_KEYS, on_conflict="update"
                )

    with engine.connect() as conn:
        stored = pd.read_sql_query(
            _OBSERVED_REREAD_STATEMENT, conn, params={"start": start, "end": end}
        )
    check_error: CheckFailed | None = None
    try:
        check_weather_observed(
            stored, [location.location_id for location in locations], start, end, max_delay_days
        )
    except CheckFailed as error:
        check_error = error

    if failed:
        message = f"observed weather failed for locations: {', '.join(failed)}"
        if check_error is not None:
            message += f"; {check_error}"
        raise PartialIngestionError(message)
    if check_error is not None:
        raise check_error

    logger.info(
        "weather-observed ok: %d locations, %d rows written from %s to %s",
        len(locations),
        written,
        start,
        end,
    )
    return written
