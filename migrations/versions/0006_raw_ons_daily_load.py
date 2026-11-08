"""raw_ons_daily_load

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-08 13:00:00.000000

Creates raw.ons_daily_load: daily load from ONS, one row per subsystem and day.
Permissions come from the default privileges set by 0002; no explicit GRANT or REVOKE here.
The ingestor keeps UPDATE on purpose: ONS revises published days and the job upserts with
on_conflict="update" (ADR 0005: ingested_at is the last write).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE raw.ons_daily_load (
            subsystem text NOT NULL
                CONSTRAINT ons_daily_load_subsystem_code
                CHECK (subsystem IN ('SE', 'S', 'NE', 'N')),
            "date" date NOT NULL,
            load_avg_mw double precision NOT NULL,
            ingested_at timestamptz NOT NULL,
            CONSTRAINT ons_daily_load_pkey PRIMARY KEY (subsystem, "date")
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE raw.ons_daily_load IS "
        "'Daily energy load published by ONS (Carga de Energia Diaria), one row per subsystem "
        "and day. Rows are upserted: ONS revises published days and the latest published value "
        "overwrites the stored one (the ingestor role has UPDATE).'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.ons_daily_load.subsystem IS "
        "'ONS subsystem code (id_subsistema): SE = Sudeste/Centro-Oeste, S = Sul, "
        "NE = Nordeste, N = Norte.'"
    )
    op.execute(
        'COMMENT ON COLUMN raw.ons_daily_load."date" IS '
        "'Calendar day as published by ONS (din_instante, date only).'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.ons_daily_load.load_avg_mw IS "
        "'Average load over the day in MWmed (average MW), from ONS val_cargaenergiamwmed.'"
    )
    op.execute(
        "COMMENT ON COLUMN raw.ons_daily_load.ingested_at IS "
        "'Server time of the last write of the row (ADR 0005).'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE raw.ons_daily_load")
