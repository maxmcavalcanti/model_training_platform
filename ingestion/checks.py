"""Data quality checks run at the end of every ingestion job."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pandera.errors
import pandera.pandas as pa

from ingestion.ons import ONS_KNOWN_GAPS


class CheckFailed(RuntimeError):
    """Raised when a quality check fails; the job execution must fail."""


def check(df: pd.DataFrame, schema: pa.DataFrameSchema, expected_rows: int | None = None) -> None:
    """Validate ``df`` against ``schema`` and, when given, its row count.

    All problems are reported together in a single :class:`CheckFailed`.
    """
    problems: list[str] = []
    try:
        schema.validate(df, lazy=True)
    except pandera.errors.SchemaErrors as error:
        problems.append(_describe(error))
    if expected_rows is not None and expected_rows != len(df):
        problems.append(f"expected {expected_rows} rows, got {len(df)}")
    if problems:
        raise CheckFailed("; ".join(problems))


def _describe(error: pandera.errors.SchemaErrors) -> str:
    cases = error.failure_cases
    details = sorted({f"{case['column']}: {case['check']}" for _, case in cases.iterrows()})
    return f"schema validation failed ({len(cases)} failure cases): " + ", ".join(details)


def _temperature() -> pa.Column:
    return pa.Column(float, pa.Check.in_range(-10, 50), nullable=True)


def _min_not_above_max(df: pd.DataFrame) -> pd.Series:
    return df["temp_min"].isna() | df["temp_max"].isna() | (df["temp_min"] <= df["temp_max"])


WEATHER_FORECAST_SCHEMA = pa.DataFrameSchema(
    {
        "location_id": pa.Column(nullable=False),
        "issued_at": pa.Column(nullable=False),
        "target_date": pa.Column(nullable=False),
        "horizon_days": pa.Column(int, pa.Check.in_range(1, 7), nullable=False),
        "temp_max": _temperature(),
        "temp_min": _temperature(),
        "precip_mm": pa.Column(float, pa.Check.ge(0), nullable=True),
        "wind_speed_max": pa.Column(float, pa.Check.ge(0), nullable=True),
        "humidity_mean": pa.Column(float, pa.Check.in_range(0, 100), nullable=True),
    },
    checks=pa.Check(_min_not_above_max, error="temp_min must not exceed temp_max"),
    unique=["location_id", "issued_at", "target_date"],
    strict=False,
)


def _weekday_matches_date(df: pd.DataFrame) -> pd.Series:
    return df["weekday"] == df["date"].map(lambda day: day.isoweekday())


def _holiday_flag_matches_name(df: pd.DataFrame) -> pd.Series:
    has_name = df["holiday_name"].notna() & (df["holiday_name"] != "")
    return df["is_national_holiday"] == has_name


CALENDAR_SCHEMA = pa.DataFrameSchema(
    {
        "date": pa.Column(nullable=False, unique=True),
        "weekday": pa.Column(int, pa.Check.in_range(1, 7), nullable=False),
        "is_national_holiday": pa.Column(bool, nullable=False),
        "holiday_name": pa.Column(nullable=True),
    },
    checks=[
        pa.Check(_weekday_matches_date, error="weekday must match the ISO weekday of date"),
        pa.Check(
            _holiday_flag_matches_name,
            error="is_national_holiday must be true if and only if holiday_name is set",
        ),
    ],
    strict=False,
)


ONS_DAILY_LOAD_SCHEMA = pa.DataFrameSchema(
    {
        "subsystem": pa.Column(nullable=False, checks=pa.Check.isin(["SE", "S", "NE", "N"])),
        "date": pa.Column(nullable=False),
        "load_avg_mw": pa.Column(
            float,
            pa.Check.in_range(0, 100000, include_min=False, include_max=False),
            nullable=False,
        ),
    },
    unique=["subsystem", "date"],
    strict=False,
)

_ONS_SUBSYSTEM_COUNT = 4


def check_ons_daily_load(
    df: pd.DataFrame,
    start: date,
    end: date,
    max_delay_days: int,
    *,
    known_gaps: frozenset[date] = ONS_KNOWN_GAPS,
) -> None:
    """Check stored ONS daily load: schema, 4 subsystems per day, continuity and freshness.

    Dates in ``known_gaps`` may be absent altogether (whole-day source gaps); a partial day fails.

    All problems are reported together in a single :class:`CheckFailed`.
    """
    problems: list[str] = []
    try:
        ONS_DAILY_LOAD_SCHEMA.validate(df, lazy=True)
    except pandera.errors.SchemaErrors as error:
        problems.append(_describe(error))

    if df.empty:
        problems.append(f"no rows between {start} and {end}")
    else:
        counts = df.groupby("date").size()
        for day, count in counts.items():
            if count != _ONS_SUBSYSTEM_COUNT:
                problems.append(f"{day} has {count} rows, expected {_ONS_SUBSYSTEM_COUNT}")
        present = set(counts.index)
        last = max(present)
        missing = [
            day.isoformat()
            for day in (start + timedelta(days=n) for n in range((last - start).days + 1))
            if day not in present and day not in known_gaps
        ]
        if missing:
            problems.append(f"missing dates: {', '.join(missing)}")
        limit = end - timedelta(days=max_delay_days)
        if last < limit:
            problems.append(f"stale: last date {last} is older than {limit}")
    if problems:
        raise CheckFailed("; ".join(problems))
