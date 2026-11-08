"""Data quality checks run at the end of every ingestion job."""

from __future__ import annotations

import pandas as pd
import pandera.errors
import pandera.pandas as pa


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
