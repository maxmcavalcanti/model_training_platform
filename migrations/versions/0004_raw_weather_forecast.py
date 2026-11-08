"""raw_weather_forecast

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08 12:00:00.000000

Creates raw.weather_forecast: daily weather forecast snapshots, stored as issued (ADR 0005).
Permissions come from the default privileges set by 0002; no explicit GRANT here.
As an exception to those defaults, UPDATE is revoked from the ingestor on this table only, so
the database enforces "the first snapshot wins": the ingestor can only insert with
on_conflict="ignore". Corrections are done by the admin.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE raw.weather_forecast (
            location_id text NOT NULL,
            issued_at date NOT NULL,
            target_date date NOT NULL,
            horizon_days smallint NOT NULL
                GENERATED ALWAYS AS ((target_date - issued_at)::smallint) STORED,
            temp_max double precision,
            temp_min double precision,
            precip_mm double precision,
            wind_speed_max double precision,
            humidity_mean double precision,
            ingested_at timestamptz NOT NULL,
            CONSTRAINT weather_forecast_pkey
                PRIMARY KEY (location_id, issued_at, target_date),
            CONSTRAINT weather_forecast_location_id_fkey
                FOREIGN KEY (location_id) REFERENCES ref.locations (location_id),
            CONSTRAINT weather_forecast_horizon_days_range
                CHECK ((target_date - issued_at) BETWEEN 1 AND 7)
        )
        """
    )
    op.execute("REVOKE UPDATE ON raw.weather_forecast FROM ingestor")
    op.execute(
        "COMMENT ON TABLE raw.weather_forecast IS "
        "'Daily weather forecast snapshots, stored as issued. One row per location, issue date "
        "and target date; the first snapshot of the day wins and is never overwritten "
        "(ADR 0005). The ingestor role has no UPDATE on this table.'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.weather_forecast.issued_at IS "
        "'Calendar day in America/Sao_Paulo on which the snapshot was taken.'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.weather_forecast.horizon_days IS "
        "'Generated: target_date - issued_at, from 1 to 7.'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.weather_forecast.ingested_at IS "
        "'Server time of the last write of the row (ADR 0005).'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE raw.weather_forecast")
