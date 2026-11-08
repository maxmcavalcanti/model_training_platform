"""Tests for table ``ref.locations`` and its four seeded capitals (plan 09).

Reads use the shared ``migrated_database`` (read-only). Writes and the downgrade run on a
``fresh_database`` migrated to ``head`` by the ``locations_database`` fixture.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from ingestion.db import build_engine
from tests.conftest import alembic_config

pytestmark = pytest.mark.db

INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
UNIQUE_VIOLATION = "23505"

SEEDED_ROWS = [
    ("belem", "Belém", -1.46, -48.49, "N"),
    ("porto_alegre", "Porto Alegre", -30.03, -51.23, "S"),
    ("recife", "Recife", -8.05, -34.88, "NE"),
    ("sao_paulo", "São Paulo", -23.55, -46.63, "SE"),
]
SELECT_ALL = "SELECT location_id, name, lat, lon, subsystem FROM ref.locations ORDER BY location_id"
INSERT = (
    "INSERT INTO ref.locations (location_id, name, lat, lon, subsystem) "
    "VALUES (:location_id, :name, :lat, :lon, :subsystem)"
)
VALID_ROW = {
    "location_id": "curitiba",
    "name": "Curitiba",
    "lat": -25.43,
    "lon": -49.27,
    "subsystem": "S",
}


def _query(url: str, statement: str, role: str | None = None) -> list[tuple]:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            if role is not None:
                connection.execute(text(f"SET ROLE {role}"))
            return [tuple(row) for row in connection.execute(text(statement))]
    finally:
        engine.dispose()


def _execute(url: str, statement: str, params: dict | None = None, role: str | None = None) -> None:
    """Run ``statement`` (optionally as ``role``) on its own connection and commit."""
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            if role is not None:
                connection.execute(text(f"SET ROLE {role}"))
            connection.execute(text(statement), params or {})
            connection.commit()
    finally:
        engine.dispose()


def _insert_expecting_integrity_error(url: str, row: dict) -> IntegrityError:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            with pytest.raises(IntegrityError) as error_info:
                connection.execute(text(INSERT), row)
            return error_info.value
    finally:
        engine.dispose()


def _assert_denied(url: str, role: str, statement: str, params: dict | None = None) -> None:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text(f"SET ROLE {role}"))
            with pytest.raises(ProgrammingError) as error_info:
                connection.execute(text(statement), params or {})
            assert error_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE
    finally:
        engine.dispose()


def _table_exists(url: str) -> bool:
    return _query(url, "SELECT to_regclass('ref.locations') IS NOT NULL") == [(True,)]


@pytest.fixture
def locations_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database


# Case 1
def test_seeded_rows_are_the_four_capitals(migrated_database):
    assert _query(migrated_database, SELECT_ALL) == SEEDED_ROWS


# Case 2
def test_each_subsystem_appears_exactly_once_in_seeded_data(migrated_database):
    rows = _query(
        migrated_database,
        "SELECT subsystem, count(*) FROM ref.locations GROUP BY subsystem ORDER BY subsystem",
    )

    assert rows == [("N", 1), ("NE", 1), ("S", 1), ("SE", 1)]


# Case 3
def test_columns_types_and_primary_key(migrated_database):
    columns = _query(
        migrated_database,
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'ref' AND table_name = 'locations' ORDER BY column_name",
    )
    primary_key = _query(
        migrated_database,
        "SELECT a.attname FROM pg_index i "
        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = to_regclass('ref.locations') AND i.indisprimary",
    )

    assert columns == [
        ("lat", "double precision", "NO"),
        ("location_id", "text", "NO"),
        ("lon", "double precision", "NO"),
        ("name", "text", "NO"),
        ("subsystem", "text", "NO"),
    ]
    assert primary_key == [("location_id",)]


# Case 4
@pytest.mark.parametrize("subsystem", ["CO", "SE/CO", "se"])
def test_invalid_subsystem_is_rejected(locations_database, subsystem):
    error = _insert_expecting_integrity_error(
        locations_database, {**VALID_ROW, "subsystem": subsystem}
    )

    assert error.orig.sqlstate == CHECK_VIOLATION
    assert error.orig.diag.constraint_name == "locations_subsystem_code"


# Case 5
@pytest.mark.parametrize(
    "location_id",
    [
        "São Paulo",
        "belém",
        "SAO_PAULO",
        "sao paulo",
        "sao-paulo",
        "",
        "_recife",
        "recife_",
        "sao__paulo",
        "1recife",
    ],
)
def test_location_id_outside_slug_format_is_rejected(locations_database, location_id):
    error = _insert_expecting_integrity_error(
        locations_database, {**VALID_ROW, "location_id": location_id}
    )

    assert error.orig.sqlstate == CHECK_VIOLATION
    assert error.orig.diag.constraint_name == "locations_location_id_slug"


# Case 6
@pytest.mark.parametrize("location_id", ["curitiba", "rio_de_janeiro", "zona2"])
def test_location_id_in_slug_format_is_accepted(locations_database, location_id):
    _execute(locations_database, INSERT, {**VALID_ROW, "location_id": location_id})

    assert (location_id,) in _query(locations_database, "SELECT location_id FROM ref.locations")


# Case 7
@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("lat", 91, "locations_lat_range"),
        ("lat", -91, "locations_lat_range"),
        ("lon", 181, "locations_lon_range"),
        ("lon", -181, "locations_lon_range"),
    ],
)
def test_coordinates_out_of_range_are_rejected(locations_database, column, value, constraint):
    error = _insert_expecting_integrity_error(locations_database, {**VALID_ROW, column: value})

    assert error.orig.sqlstate == CHECK_VIOLATION
    assert error.orig.diag.constraint_name == constraint


def test_coordinates_at_the_limits_are_accepted(locations_database):
    _execute(locations_database, INSERT, {**VALID_ROW, "lat": 90, "lon": -180})

    rows = _query(
        locations_database,
        "SELECT lat, lon FROM ref.locations WHERE location_id = 'curitiba'",
    )
    assert rows == [(90.0, -180.0)]


# Case 8
@pytest.mark.parametrize("column", ["name", "lat", "lon", "subsystem"])
def test_null_in_required_column_is_rejected(locations_database, column):
    error = _insert_expecting_integrity_error(locations_database, {**VALID_ROW, column: None})

    assert error.orig.sqlstate == NOT_NULL_VIOLATION


# Case 9
def test_duplicate_location_id_is_rejected(locations_database):
    error = _insert_expecting_integrity_error(
        locations_database, {**VALID_ROW, "location_id": "recife"}
    )

    assert error.orig.sqlstate == UNIQUE_VIOLATION


# Case 10
def test_ingestor_inserts_and_updates_but_cannot_delete(locations_database):
    _execute(locations_database, INSERT, VALID_ROW, role="ingestor")
    assert _query(locations_database, "SELECT count(*) FROM ref.locations") == [(5,)]

    _execute(
        locations_database,
        "UPDATE ref.locations SET name = 'Curitiba PR' WHERE location_id = 'curitiba'",
        role="ingestor",
    )
    assert _query(
        locations_database, "SELECT name FROM ref.locations WHERE location_id = 'curitiba'"
    ) == [("Curitiba PR",)]

    _assert_denied(
        locations_database, "ingestor", "DELETE FROM ref.locations WHERE location_id = 'curitiba'"
    )


# Case 11
@pytest.mark.parametrize("role", ["reader", "scientist", "scorer"])
def test_read_only_roles_select_but_cannot_insert(locations_database, role):
    assert _query(locations_database, "SELECT count(*) FROM ref.locations", role=role) == [(4,)]

    _assert_denied(locations_database, role, INSERT, VALID_ROW)


# Case 12
def test_downgrade_to_0002_drops_the_table_and_upgrade_recreates_it(locations_database):
    config = alembic_config()
    assert _table_exists(locations_database)

    command.downgrade(config, "0002")

    assert not _table_exists(locations_database)
    assert _query(
        locations_database, "SELECT count(*) FROM pg_namespace WHERE nspname = 'ref'"
    ) == [(1,)]

    command.upgrade(config, "head")

    assert _query(locations_database, SELECT_ALL) == SEEDED_ROWS
