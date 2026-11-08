"""Tests for ``ingestion.ons`` (plan 20, cases 1 to 18).

Parquet files are built in memory with the schema of the real ONS file. The network is simulated
with ``httpx.MockTransport``. No test touches the network or the database.
"""

from __future__ import annotations

import datetime as dt
import io
from collections.abc import Callable

import httpx
import pandas as pd
import pytest

from ingestion.http import NetworkError
from ingestion.ons import fetch_load, file_url, parse_load

SUBSYSTEM_NAMES = {
    "N": "Norte",
    "NE": "Nordeste",
    "S": "Sul",
    "SE": "Sudeste/Centro-Oeste",
}
OUTPUT_COLUMNS = ["subsystem", "date", "load_avg_mw"]
DAYS = [dt.datetime(2026, 11, 5), dt.datetime(2026, 11, 6)]
Step = Callable[[httpx.Request], httpx.Response]


def _frame(rows: list[tuple[str, dt.datetime, float | None]]) -> pd.DataFrame:
    """Frame with the four columns and dtypes of the ONS file."""
    return pd.DataFrame(
        {
            "id_subsistema": pd.Series([r[0] for r in rows], dtype="object"),
            "nom_subsistema": pd.Series([SUBSYSTEM_NAMES.get(r[0], r[0]) for r in rows]),
            "din_instante": pd.Series([r[1] for r in rows], dtype="datetime64[ns]"),
            "val_cargaenergiamwmed": pd.Series([r[2] for r in rows], dtype="float64"),
        }
    )


def _grid() -> list[tuple[str, dt.datetime, float | None]]:
    """2 days x 4 subsystems, in the file's natural order."""
    return [
        (code, day, 1000.0 + index * 10 + number)
        for number, day in enumerate(DAYS)
        for index, code in enumerate(["SE", "S", "NE", "N"])
    ]


def _to_parquet(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer)
    return buffer.getvalue()


def _grid_bytes() -> bytes:
    return _to_parquet(_frame(_grid()))


class Harness:
    """Client whose n-th request is answered by the n-th step; records requests and sleeps."""

    def __init__(self, steps: list[Step]) -> None:
        self.steps = steps
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.steps[min(len(self.requests), len(self.steps)) - 1](request)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _ok(content: bytes) -> Step:
    return lambda request: httpx.Response(200, content=content)


def _status(code: int) -> Step:
    return lambda request: httpx.Response(code)


# Case 1
def test_parse_load_returns_normalized_columns_and_index():
    frame = parse_load(_grid_bytes())

    assert len(frame) == 8
    assert list(frame.columns) == OUTPUT_COLUMNS
    assert list(frame.index) == list(range(8))
    assert "nom_subsistema" not in frame.columns
    assert "ingested_at" not in frame.columns


# Case 2
def test_parse_load_date_is_python_date():
    frame = parse_load(_grid_bytes())

    assert all(type(value) is dt.date for value in frame["date"])
    assert set(frame["date"]) == {dt.date(2026, 11, 5), dt.date(2026, 11, 6)}


# Case 3
def test_parse_load_keeps_load_value_as_float64():
    rows = [("SE", dt.datetime(2026, 11, 5), 41234.5)]
    frame = parse_load(_to_parquet(_frame(rows)))

    assert frame.loc[0, "load_avg_mw"] == 41234.5
    assert frame["load_avg_mw"].dtype == "float64"


# Case 4
def test_parse_load_sorts_by_date_then_subsystem():
    rows = list(reversed(_grid()))
    rows = rows[3:] + rows[:3]
    frame = parse_load(_to_parquet(_frame(rows)))

    pairs = list(zip(frame["date"], frame["subsystem"], strict=True))
    assert pairs == sorted(pairs)
    assert [code for _, code in pairs[:4]] == ["N", "NE", "S", "SE"]
    assert list(frame.index) == list(range(8))


# Case 5
@pytest.mark.parametrize("column", ["val_cargaenergiamwmed", "id_subsistema", "din_instante"])
def test_parse_load_rejects_missing_required_column(column):
    content = _to_parquet(_frame(_grid()).drop(columns=[column]))

    with pytest.raises(ValueError, match=column):
        parse_load(content)


# Case 6
def test_parse_load_rejects_se_co_code():
    rows = _grid()
    rows[0] = ("SE/CO", rows[0][1], rows[0][2])

    with pytest.raises(ValueError, match="SE/CO"):
        parse_load(_to_parquet(_frame(rows)))


# Case 7
def test_parse_load_rejects_sin_rows():
    rows = _grid() + [("SIN", DAYS[0], 70000.0)]

    with pytest.raises(ValueError, match="SIN"):
        parse_load(_to_parquet(_frame(rows)))


# Case 8
def test_parse_load_rejects_non_midnight_timestamp():
    rows = [("SE", dt.datetime(2026, 11, 5, 12, 0, 0), 100.0)]

    with pytest.raises(ValueError):
        parse_load(_to_parquet(_frame(rows)))


# Case 9
def test_parse_load_drops_rows_with_null_load():
    rows = _grid()
    rows[2] = (rows[2][0], rows[2][1], None)
    frame = parse_load(_to_parquet(_frame(rows)))

    assert len(frame) == 7
    assert list(frame.index) == list(range(7))
    assert not frame["load_avg_mw"].isna().any()
    assert (rows[2][0], dt.date(2026, 11, 5)) not in set(
        zip(frame["subsystem"], frame["date"], strict=True)
    )


# Case 10
def test_parse_load_rejects_duplicate_key():
    rows = _grid() + [("SE", DAYS[0], 999.0)]

    with pytest.raises(ValueError):
        parse_load(_to_parquet(_frame(rows)))


# Case 11
def test_parse_load_rejects_bytes_that_are_not_parquet():
    with pytest.raises(ValueError):
        parse_load(b"not a parquet")


# Case 12
def test_parse_load_accepts_empty_file():
    frame = parse_load(_to_parquet(_frame([])))

    assert frame.empty
    assert list(frame.columns) == OUTPUT_COLUMNS


# Case 13
def test_parse_load_does_not_judge_staleness():
    rows = [
        ("SE", dt.datetime(2015, 1, 30), 100.0),
        ("SE", dt.datetime(2015, 1, 31), 101.0),
    ]
    frame = parse_load(_to_parquet(_frame(rows)))

    assert len(frame) == 2
    assert frame["date"].max() == dt.date(2015, 1, 31)


# Case 14
def test_file_url_follows_bucket_pattern():
    assert file_url(2015) == (
        "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/carga_energia_di/"
        "CARGA_ENERGIA_2015.parquet"
    )


# Case 15
def test_fetch_load_requests_year_file_and_parses_it():
    content = _grid_bytes()
    harness = Harness([_ok(content)])

    frame = fetch_load(harness.client, 2026, sleep=harness.sleep)

    assert len(harness.requests) == 1
    assert harness.requests[0].method == "GET"
    assert str(harness.requests[0].url) == file_url(2026)
    pd.testing.assert_frame_equal(frame, parse_load(content))
    assert harness.sleeps == []


# Case 16
def test_fetch_load_retries_after_503():
    harness = Harness([_status(503), _ok(_grid_bytes())])

    frame = fetch_load(harness.client, 2026, base_delay=0.5, sleep=harness.sleep)

    assert len(frame) == 8
    assert len(harness.requests) == 2
    assert harness.sleeps == [0.5]


# Case 17
def test_fetch_load_raises_network_error_after_three_503():
    harness = Harness([_status(503)])

    with pytest.raises(NetworkError):
        fetch_load(harness.client, 2026, sleep=harness.sleep)

    assert len(harness.requests) == 3


# Case 18
def test_fetch_load_propagates_404_without_retry():
    harness = Harness([_status(404)])

    with pytest.raises(httpx.HTTPStatusError):
        fetch_load(harness.client, 2026, sleep=harness.sleep)

    assert len(harness.requests) == 1
    assert harness.sleeps == []


# ---------------------------------------------------------------------------
# ONS source-gaps plan (2026-11-08), cases 19 to 27: load stored as text, as in files up to 2021
# ---------------------------------------------------------------------------

SUBSYSTEM_CODES = ["SE", "S", "NE", "N"]

TextRow = tuple[str, dt.datetime, str | None]


@pytest.fixture(params=["object", "str"])
def text_dtype(request) -> str:
    """Pandas dtype of the text load column (``str`` is the pandas 3 default for strings)."""
    return request.param


def _text_frame(rows: list[TextRow], dtype: str) -> pd.DataFrame:
    """Like ``_frame`` but with ``val_cargaenergiamwmed`` as text."""
    frame = _frame([(r[0], r[1], None) for r in rows])
    frame["val_cargaenergiamwmed"] = pd.Series([r[2] for r in rows], dtype=dtype)
    return frame


def _text_grid(first: dt.datetime, last: dt.datetime) -> list[TextRow]:
    """Every day from ``first`` to ``last`` times the four subsystems, load as text."""
    rows: list[TextRow] = []
    day = first
    while day <= last:
        for index, code in enumerate(SUBSYSTEM_CODES):
            rows.append((code, day, str(1000.0 + index * 10 + day.day)))
        day += dt.timedelta(days=1)
    return rows


def _text_two_days() -> list[TextRow]:
    return [
        (code, day, f"{1000.0 + index * 10 + number}")
        for number, day in enumerate(DAYS)
        for index, code in enumerate(SUBSYSTEM_CODES)
    ]


def _keys(frame: pd.DataFrame) -> set[tuple[str, dt.date]]:
    return set(zip(frame["subsystem"], frame["date"], strict=True))


# Case 19 (characterization: already passes before the fix)
def test_parse_load_converts_text_load_to_float64(text_dtype):
    rows = _text_two_days()
    rows[0] = ("SE", DAYS[0], "41234.5")

    frame = parse_load(_to_parquet(_text_frame(rows, text_dtype)))

    assert len(frame) == 8
    assert frame["load_avg_mw"].dtype == "float64"
    se = frame[(frame["subsystem"] == "SE") & (frame["date"] == dt.date(2026, 11, 5))]
    assert se["load_avg_mw"].iloc[0] == 41234.5


# Case 20
def test_parse_load_drops_row_with_empty_text_load(text_dtype):
    rows = _text_two_days()
    rows[2] = (rows[2][0], rows[2][1], "")

    frame = parse_load(_to_parquet(_text_frame(rows, text_dtype)))

    assert len(frame) == 7
    assert list(frame.index) == list(range(7))
    assert not frame["load_avg_mw"].isna().any()
    assert (rows[2][0], dt.date(2026, 11, 5)) not in _keys(frame)


# Case 21
@pytest.mark.parametrize("blank", ["   ", "\t", " \n ", None])
def test_parse_load_drops_row_with_blank_or_null_text_load(text_dtype, blank):
    rows = _text_two_days()
    rows[2] = (rows[2][0], rows[2][1], blank)

    frame = parse_load(_to_parquet(_text_frame(rows, text_dtype)))

    assert len(frame) == 7
    assert (rows[2][0], dt.date(2026, 11, 5)) not in _keys(frame)


# Case 22
def test_parse_load_strips_spaces_around_text_load(text_dtype):
    rows = _text_two_days()
    rows[0] = ("SE", DAYS[0], " 41234.5 ")

    frame = parse_load(_to_parquet(_text_frame(rows, text_dtype)))

    assert len(frame) == 8
    se = frame[(frame["subsystem"] == "SE") & (frame["date"] == dt.date(2026, 11, 5))]
    assert se["load_avg_mw"].iloc[0] == 41234.5


# Case 23
@pytest.mark.parametrize("value", ["abc", "12,5", "nan"])
def test_parse_load_rejects_non_numeric_text_load(text_dtype, value):
    rows = _text_two_days()
    rows[2] = (rows[2][0], rows[2][1], value)

    with pytest.raises(ValueError, match="val_cargaenergiamwmed"):
        parse_load(_to_parquet(_text_frame(rows, text_dtype)))


# Case 24
def test_parse_load_drops_a_whole_empty_day(text_dtype):
    rows = [
        (code, day, "" if day == dt.datetime(2015, 4, 9) else load)
        for code, day, load in _text_grid(dt.datetime(2015, 4, 8), dt.datetime(2015, 4, 10))
    ]

    frame = parse_load(_to_parquet(_text_frame(rows, text_dtype)))

    assert len(frame) == 8
    assert dt.date(2015, 4, 9) not in set(frame["date"])
    for day in (dt.date(2015, 4, 8), dt.date(2015, 4, 10)):
        assert set(frame.loc[frame["date"] == day, "subsystem"]) == set(SUBSYSTEM_CODES)


# Case 25
def test_parse_load_ignores_orphan_row_with_empty_load(text_dtype):
    rows = _text_grid(dt.datetime(2013, 2, 1), dt.datetime(2013, 2, 3))
    expected = next(r[2] for r in rows if r[0] == "S" and r[1] == dt.datetime(2013, 2, 2))
    rows.append(("S", dt.datetime(2013, 2, 2, 0, 0, 1), ""))

    frame = parse_load(_to_parquet(_text_frame(rows, text_dtype)))

    assert len(frame) == 12
    orphaned = frame[(frame["subsystem"] == "S") & (frame["date"] == dt.date(2013, 2, 2))]
    assert len(orphaned) == 1
    assert orphaned["load_avg_mw"].iloc[0] == float(expected)


# Case 26
def test_parse_load_rejects_non_midnight_row_with_text_load(text_dtype):
    rows = _text_grid(dt.datetime(2013, 2, 1), dt.datetime(2013, 2, 3))
    rows.append(("S", dt.datetime(2013, 2, 2, 0, 0, 1), "123.0"))

    with pytest.raises(ValueError, match="midnight"):
        parse_load(_to_parquet(_text_frame(rows, text_dtype)))


# Case 27
def test_parse_load_ignores_orphan_row_with_null_float_load():
    rows = _grid()
    rows.append(("S", dt.datetime(2026, 11, 5, 0, 0, 1), None))

    frame = parse_load(_to_parquet(_frame(rows)))

    assert len(frame) == 8
    assert list(frame["date"]).count(dt.date(2026, 11, 5)) == 4


# ---------------------------------------------------------------------------
# Hardening follow-ups plan H1, cases 1 and 2: non-finite load is rejected
# ---------------------------------------------------------------------------


# H1 case 1
@pytest.mark.parametrize("value", ["inf", "-inf", "+inf", "Infinity"])
def test_parse_load_rejects_non_finite_text_load(text_dtype, value):
    rows = _text_two_days()
    rows[2] = (rows[2][0], rows[2][1], value)

    with pytest.raises(ValueError, match="val_cargaenergiamwmed") as error_info:
        parse_load(_to_parquet(_text_frame(rows, text_dtype)))

    if value == "inf":
        assert "inf" in str(error_info.value)


# H1 case 2
@pytest.mark.parametrize("value", [float("inf"), float("-inf")])
def test_parse_load_rejects_non_finite_float_load(value):
    rows = _grid()
    rows[2] = (rows[2][0], rows[2][1], value)

    with pytest.raises(ValueError, match="val_cargaenergiamwmed"):
        parse_load(_to_parquet(_frame(rows)))
