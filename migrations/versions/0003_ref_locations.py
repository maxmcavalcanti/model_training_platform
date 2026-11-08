"""ref_locations

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07 22:22:18.015071

Creates ref.locations and loads the four capitals (one per subsystem) in the same transaction.
Permissions come from the default privileges set by 0002; no explicit GRANT here.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE ref.locations (
            location_id text PRIMARY KEY
                CONSTRAINT locations_location_id_slug
                CHECK (location_id ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'),
            name text NOT NULL,
            lat double precision NOT NULL
                CONSTRAINT locations_lat_range CHECK (lat BETWEEN -90 AND 90),
            lon double precision NOT NULL
                CONSTRAINT locations_lon_range CHECK (lon BETWEEN -180 AND 180),
            subsystem text NOT NULL
                CONSTRAINT locations_subsystem_code CHECK (subsystem IN ('SE', 'S', 'NE', 'N'))
        )
        """
    )
    op.execute(
        """
        INSERT INTO ref.locations (location_id, name, lat, lon, subsystem) VALUES
            ('sao_paulo', 'São Paulo', -23.55, -46.63, 'SE'),
            ('porto_alegre', 'Porto Alegre', -30.03, -51.23, 'S'),
            ('recife', 'Recife', -8.05, -34.88, 'NE'),
            ('belem', 'Belém', -1.46, -48.49, 'N')
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE ref.locations")
