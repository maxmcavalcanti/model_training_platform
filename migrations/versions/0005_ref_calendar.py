"""ref_calendar

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08 13:00:00.000000

Creates ref.calendar: one row per day with the ISO weekday and Brazilian national holidays.
The table is loaded by the calendar job (python -m ingestion calendar), not by this migration.
Permissions come from the default privileges set by 0002; no explicit GRANT here.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE ref.calendar (
            "date" date PRIMARY KEY,
            weekday smallint NOT NULL
                CONSTRAINT calendar_weekday_isodow CHECK (weekday = EXTRACT(ISODOW FROM "date")),
            is_national_holiday boolean NOT NULL,
            holiday_name text,
            CONSTRAINT calendar_holiday_name_consistency CHECK (
                (is_national_holiday AND holiday_name IS NOT NULL AND holiday_name <> '')
                OR (NOT is_national_holiday AND holiday_name IS NULL)
            )
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE ref.calendar IS 'One row per day. National public holidays of Brazil "
        "from the holidays library pinned in uv.lock (no state or municipal holidays, no optional "
        "days such as Carnival). Loaded by python -m ingestion calendar.'"
    )
    op.execute(
        "COMMENT ON COLUMN ref.calendar.weekday IS "
        "'ISO 8601 day of week: 1 = Monday ... 7 = Sunday.'"
    )
    op.execute(
        "COMMENT ON COLUMN ref.calendar.holiday_name IS "
        "'Holiday name in Brazilian Portuguese (pt_BR); NULL when the day is not a national "
        "holiday.'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE ref.calendar")
