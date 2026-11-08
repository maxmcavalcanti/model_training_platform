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
)
from ingestion.db import upsert
from ingestion.http import NetworkError
from ingestion.openmeteo import (
    FORECAST_TIMEZONE,
    MAX_HORIZON_DAYS,
    Location,
    fetch_forecast,
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
