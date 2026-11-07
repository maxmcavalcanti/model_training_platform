"""Single entry point to open a Postgres connection."""

from __future__ import annotations

import os

import sqlalchemy

PLAIN_SCHEME = "postgresql://"
PSYCOPG_SCHEME = "postgresql+psycopg://"


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
