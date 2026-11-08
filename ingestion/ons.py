"""Reader for the ONS daily load parquet files (public S3 bucket)."""

from __future__ import annotations

import io
import time
from collections.abc import Callable
from datetime import date

import httpx
import pandas as pd
import pyarrow as pa

from ingestion.http import fetch_bytes

BUCKET_URL = "https://ons-aws-prod-opendata.s3.amazonaws.com"
LOAD_PREFIX = "dataset/carga_energia_di/"
# Source column -> output column; the order is the output order.
COLUMN_MAP = {
    "id_subsistema": "subsystem",
    "din_instante": "date",
    "val_cargaenergiamwmed": "load_avg_mw",
}
SUBSYSTEMS = ("SE", "S", "NE", "N")
# Days with no load for any subsystem in the ONS source itself (survey of 2000-2026 files,
# 2026-11-08). check_ons_daily_load tolerates them only as whole-day gaps.
ONS_KNOWN_GAPS = frozenset({date(2013, 12, 1), date(2014, 2, 1), date(2015, 4, 9)})
_LOAD_COLUMN = "val_cargaenergiamwmed"
_MAX_REPORTED_VALUES = 5


def file_url(year: int) -> str:
    """URL of the yearly daily-load parquet file."""
    return f"{BUCKET_URL}/{LOAD_PREFIX}CARGA_ENERGIA_{year}.parquet"


def _normalize_load(series: pd.Series) -> pd.Series:
    """Return the load as float64; blank text becomes null, other bad text raises."""
    if pd.api.types.is_numeric_dtype(series):
        return series.astype("float64")
    text = series.astype("object").map(
        lambda value: value.strip() if isinstance(value, str) else value
    )
    text = text.map(lambda value: None if value == "" else value)
    numbers = pd.to_numeric(text, errors="coerce")
    bad = numbers.isna() & text.notna()
    if bad.any():
        values = sorted(set(text[bad]))[:_MAX_REPORTED_VALUES]
        raise ValueError(f"non-numeric values in {_LOAD_COLUMN}: {values}")
    return numbers.astype("float64")


def parse_load(content: bytes) -> pd.DataFrame:
    """Validate and normalize a daily-load parquet into ``subsystem, date, load_avg_mw``."""
    try:
        raw = pd.read_parquet(io.BytesIO(content))
    except (pa.ArrowException, OSError, ValueError) as error:
        raise ValueError(f"content is not a readable parquet file: {error}") from error

    for column in COLUMN_MAP:
        if column not in raw.columns:
            raise ValueError(f"missing column in ONS load file: {column}")

    frame = raw[list(COLUMN_MAP)].copy()
    for column in ("id_subsistema", "din_instante"):
        if frame[column].isna().any():
            raise ValueError(f"null values in key column: {column}")

    unknown = sorted(set(frame["id_subsistema"]) - set(SUBSYSTEMS))
    if unknown:
        raise ValueError(f"unknown subsystem codes: {unknown}")

    frame[_LOAD_COLUMN] = _normalize_load(frame[_LOAD_COLUMN])
    frame = frame.dropna(subset=[_LOAD_COLUMN])

    instants = pd.to_datetime(frame["din_instante"])
    if (instants != instants.dt.normalize()).any():
        raise ValueError("din_instante has timestamps that are not at midnight")
    frame["din_instante"] = instants

    duplicated = frame.duplicated(subset=["id_subsistema", "din_instante"], keep=False)
    if duplicated.any():
        keys = sorted(
            {
                (code, instant.date().isoformat())
                for code, instant in zip(
                    frame.loc[duplicated, "id_subsistema"],
                    frame.loc[duplicated, "din_instante"],
                    strict=True,
                )
            }
        )
        raise ValueError(f"duplicate (subsystem, date) keys: {keys}")

    result = frame.rename(columns=COLUMN_MAP)
    result["date"] = result["date"].dt.date
    result["load_avg_mw"] = result["load_avg_mw"].astype("float64")
    return result.sort_values(["date", "subsystem"]).reset_index(drop=True)


def fetch_load(
    client: httpx.Client,
    year: int,
    *,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> pd.DataFrame:
    """Download the parquet of ``year`` and return it normalized."""
    content = fetch_bytes(client, file_url(year), base_delay=base_delay, sleep=sleep)
    return parse_load(content)
