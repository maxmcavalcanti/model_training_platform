"""Single entry point to open a Postgres connection."""

from __future__ import annotations

import os
from typing import Literal

import pandas as pd
import sqlalchemy
from sqlalchemy.dialects import postgresql

PLAIN_SCHEME = "postgresql://"
PSYCOPG_SCHEME = "postgresql+psycopg://"

_MAX_BATCH_ROWS = 5000
_MAX_STATEMENT_PARAMETERS = 65_535
_INGESTED_AT = "ingested_at"


class MissingConfiguration(RuntimeError):
    """Raised when a required configuration value is not set."""


def build_engine(url: str | None = None) -> sqlalchemy.Engine:
    """Build an engine from ``url`` or the ``DATABASE_URL`` environment variable."""
    resolved_url = url or os.environ.get("DATABASE_URL")
    if not resolved_url:
        raise MissingConfiguration("DATABASE_URL is not set")
    if resolved_url.startswith(PLAIN_SCHEME):
        resolved_url = PSYCOPG_SCHEME + resolved_url[len(PLAIN_SCHEME) :]
    return sqlalchemy.create_engine(resolved_url, pool_pre_ping=True)


def upsert(
    conn: sqlalchemy.Connection,
    table: str,
    rows: pd.DataFrame,
    keys: list[str],
    *,
    on_conflict: Literal["update", "ignore"] = "update",
    stamp_ingested_at: bool = True,
) -> int:
    """Write ``rows`` into ``table`` ("schema.table") keyed by ``keys``.

    With ``on_conflict="update"`` existing rows are overwritten; with ``"ignore"`` they are
    kept untouched. When ``stamp_ingested_at`` is true, ``ingested_at`` is set to the server
    ``now()`` on insert and, in update mode, on conflict. Returns the number of rows inserted
    (plus updated, in update mode). The caller owns the transaction: nothing is committed here.
    """
    schema, separator, name = table.partition(".")
    if not separator or not schema or not name or "." in name:
        raise ValueError(f"table must be 'schema.table', got {table!r}")
    if not keys:
        raise ValueError("keys must name at least one column")
    if on_conflict not in ("update", "ignore"):
        raise ValueError(f"on_conflict must be 'update' or 'ignore', got {on_conflict!r}")
    if rows.empty:
        return 0

    reflected = sqlalchemy.Table(name, sqlalchemy.MetaData(schema=schema), autoload_with=conn)
    columns = [str(column) for column in rows.columns]
    for column in columns:
        if column not in reflected.c:
            raise ValueError(f"column {column!r} does not exist in table {table}")
    for key in keys:
        if key not in columns:
            raise ValueError(f"key column {key!r} is missing from the DataFrame")
    if stamp_ingested_at:
        if _INGESTED_AT not in reflected.c:
            raise ValueError(f"table {table} has no {_INGESTED_AT} column to stamp")
        if _INGESTED_AT in columns:
            raise ValueError(f"DataFrame must not contain {_INGESTED_AT} when stamping it")
    if rows.duplicated(subset=keys).any():
        raise ValueError(f"duplicate keys {keys} inside the DataFrame")

    records = rows.astype(object).where(rows.notna(), None).to_dict("records")
    batch_size = min(_MAX_BATCH_ROWS, _MAX_STATEMENT_PARAMETERS // len(columns))
    update_columns = [column for column in columns if column not in keys]

    total = 0
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        if stamp_ingested_at:
            batch = [{**record, _INGESTED_AT: sqlalchemy.func.now()} for record in batch]
        statement = postgresql.insert(reflected).values(batch)
        set_ = {column: statement.excluded[column] for column in update_columns}
        if stamp_ingested_at:
            set_[_INGESTED_AT] = sqlalchemy.func.now()
        if on_conflict == "update" and set_:
            statement = statement.on_conflict_do_update(index_elements=keys, set_=set_)
        else:
            statement = statement.on_conflict_do_nothing(index_elements=keys)
        total += conn.execute(statement, execution_options={"preserve_rowcount": True}).rowcount
    return total
