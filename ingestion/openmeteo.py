"""Client for the Open-Meteo daily forecast and archive (ERA5 reanalysis) APIs."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import httpx
import pandas as pd

from ingestion.http import fetch_json

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_TIMEZONE = "America/Sao_Paulo"
MAX_HORIZON_DAYS = 7

# API variable -> raw.weather_forecast column (insertion order = output column order).
DAILY_VARIABLES = {
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "precipitation_sum": "precip_mm",
    "wind_speed_10m_max": "wind_speed_max",
    "relative_humidity_2m_mean": "humidity_mean",
}
DAILY_UNITS = {
    "temperature_2m_max": "°C",
    "temperature_2m_min": "°C",
    "precipitation_sum": "mm",
    "wind_speed_10m_max": "km/h",
    "relative_humidity_2m_mean": "%",
}


@dataclass(frozen=True)
class Location:
    location_id: str
    lat: float
    lon: float


def _daily_section(payload: object, location_id: str) -> dict:
    """Return ``payload["daily"]`` after checking shape, units and list lengths."""
    daily = payload.get("daily") if isinstance(payload, dict) else None
    if not isinstance(daily, dict):
        raise ValueError(f"{location_id}: response has no 'daily' section")
    names = ("time", *DAILY_VARIABLES)
    for name in names:
        if name not in daily:
            raise ValueError(f"{location_id}: response is missing daily '{name}'")
    units = payload.get("daily_units") or {}
    for name, expected in DAILY_UNITS.items():
        if units.get(name) != expected:
            raise ValueError(
                f"{location_id}: unexpected unit for {name}: "
                f"got {units.get(name)!r}, expected {expected!r}"
            )
    lengths = {name: len(daily[name]) for name in names}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"{location_id}: daily lists have different lengths: {lengths}")
    return daily


def _validate(payload: object, location_id: str, issued_at: date, days: int) -> dict:
    """Return ``payload["daily"]`` after checking the common shape and the first day."""
    daily = _daily_section(payload, location_id)
    if len(daily["time"]) < days + 1:
        raise ValueError(
            f"{location_id}: expected at least {days + 1} days, got {len(daily['time'])}"
        )
    first_day = date.fromisoformat(daily["time"][0])
    if first_day != issued_at:
        raise ValueError(f"{location_id}: first forecast day is {first_day}, expected {issued_at}")
    return daily


def fetch_forecast(
    client: httpx.Client,
    location: Location,
    issued_at: date,
    days: int = MAX_HORIZON_DAYS,
    *,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> pd.DataFrame:
    """Fetch the daily forecast for horizons 1 to ``days`` as a frame ready for upsert."""
    if not 1 <= days <= MAX_HORIZON_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_HORIZON_DAYS}, got {days}")
    params = {
        "latitude": location.lat,
        "longitude": location.lon,
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": FORECAST_TIMEZONE,
        "forecast_days": days + 1,
    }
    payload = fetch_json(client, FORECAST_URL, params, base_delay=base_delay, sleep=sleep)
    daily = _validate(payload, location.location_id, issued_at, days)

    columns: dict[str, object] = {
        "location_id": [location.location_id] * days,
        "issued_at": [issued_at] * days,
        "target_date": [issued_at + timedelta(days=h) for h in range(1, days + 1)],
    }
    for name, column in DAILY_VARIABLES.items():
        columns[column] = pd.Series(daily[name][1 : days + 1], dtype="float64")
    return pd.DataFrame(columns)


def fetch_observed(
    client: httpx.Client,
    location: Location,
    start: date,
    end: date,
    *,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> pd.DataFrame:
    """Fetch observed daily weather for ``start..end`` as a frame ready for upsert.

    Days whose five variables are all null (not yet published) are dropped.
    """
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    params = {
        "latitude": location.lat,
        "longitude": location.lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": FORECAST_TIMEZONE,
    }
    payload = fetch_json(client, ARCHIVE_URL, params, base_delay=base_delay, sleep=sleep)
    daily = _daily_section(payload, location.location_id)

    expected = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    received = [date.fromisoformat(day) for day in daily["time"]]
    for want, got in zip(expected, received, strict=False):
        if want != got:
            raise ValueError(f"{location.location_id}: expected day {want}, got {got}")
    if len(received) != len(expected):
        raise ValueError(
            f"{location.location_id}: expected {len(expected)} days "
            f"from {start} to {end}, got {len(received)}"
        )

    columns: dict[str, object] = {
        "location_id": [location.location_id] * len(expected),
        "date": expected,
    }
    for name, column in DAILY_VARIABLES.items():
        columns[column] = pd.Series(daily[name], dtype="float64")
    frame = pd.DataFrame(columns)
    return frame.dropna(how="all", subset=list(DAILY_VARIABLES.values())).reset_index(drop=True)
