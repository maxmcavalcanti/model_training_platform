"""raw_weather_observed

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-08 14:00:00.000000

Creates raw.weather_observed: daily observed weather from the Open-Meteo ERA5 archive, one row
per location and day.
Permissions come from the default privileges set by 0002; no explicit GRANT or REVOKE here.
The ingestor keeps UPDATE on purpose: the job rewrites the recent window (recent ERA5 values may
be preliminary) with on_conflict="update" (ADR 0005: ingested_at is the last write). Unlike
raw.weather_forecast, observed values are not stored as issued.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE raw.weather_observed (
            location_id text NOT NULL,
            "date" date NOT NULL,
            temp_max double precision,
            temp_min double precision,
            precip_mm double precision,
            wind_speed_max double precision,
            humidity_mean double precision,
            ingested_at timestamptz NOT NULL,
            CONSTRAINT weather_observed_pkey PRIMARY KEY (location_id, "date"),
            CONSTRAINT weather_observed_location_id_fkey
                FOREIGN KEY (location_id) REFERENCES ref.locations (location_id)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE raw.weather_observed IS "
        "'Daily observed weather per location from the Open-Meteo archive (ERA5 reanalysis), "
        "one row per location and day. Rows are upserted. Recent days are rewritten by the "
        "daily job because recent ERA5 values may be preliminary (the ingestor role has "
        "UPDATE).'"
    )
    op.execute(
        'COMMENT ON COLUMN raw.weather_observed."date" IS '
        "'Calendar day in America/Sao_Paulo (timezone requested from the archive API).'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.weather_observed.temp_max IS "
        "'Daily maximum air temperature at 2 m, degrees Celsius (temperature_2m_max).'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.weather_observed.temp_min IS "
        "'Daily minimum air temperature at 2 m, degrees Celsius (temperature_2m_min).'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.weather_observed.precip_mm IS "
        "'Daily precipitation sum, mm (precipitation_sum).'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.weather_observed.wind_speed_max IS "
        "'Daily maximum wind speed at 10 m, km/h (wind_speed_10m_max).'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.weather_observed.humidity_mean IS "
        "'Daily mean relative humidity at 2 m, percent (relative_humidity_2m_mean).'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.weather_observed.ingested_at IS "
        "'Server time of the last write of the row (ADR 0005).'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE raw.weather_observed")
