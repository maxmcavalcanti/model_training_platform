"""Reader for the ONS daily load parquet files (public S3 bucket)."""

from __future__ import annotations

import io
import time
from collections.abc import Callable

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


def file_url(year: int) -> str:
    """URL of the yearly daily-load parquet file."""
    return f"{BUCKET_URL}/{LOAD_PREFIX}CARGA_ENERGIA_{year}.parquet"


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

    instants = pd.to_datetime(frame["din_instante"])
    if (instants != instants.dt.normalize()).any():
        raise ValueError("din_instante has timestamps that are not at midnight")
    frame["din_instante"] = instants

    frame = frame.dropna(subset=["val_cargaenergiamwmed"])

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
