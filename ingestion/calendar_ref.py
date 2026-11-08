"""Build the ref.calendar rows: one per day, with Brazilian national holidays."""

from __future__ import annotations

from datetime import date, timedelta

import holidays
import pandas as pd

COLUMNS = ["date", "weekday", "is_national_holiday", "holiday_name"]


def build_calendar(start: date, end: date) -> pd.DataFrame:
    """Return one row per day from ``start`` to ``end``, both inclusive.

    Pure function: no database, no network, no clock. Holidays are the national public holidays
    of Brazil from the ``holidays`` library, with names in Brazilian Portuguese.
    """
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    national = holidays.country_holidays(
        "BR",
        years=range(start.year, end.year + 1),
        language="pt_BR",
        categories=(holidays.PUBLIC,),
    )
    rows = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        name = national.get(day)
        rows.append(
            {
                "date": day,
                "weekday": day.isoweekday(),
                "is_national_holiday": name is not None,
                "holiday_name": name,
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)
