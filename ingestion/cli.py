"""Command line entry point: ``python -m ingestion <subcommand>``.

Exit codes: 0 success, 1 execution or quality-check failure, 2 incorrect usage.
"""

import argparse
import logging
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Subcommand:
    help: str
    add_arguments: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], int]


SUBCOMMANDS: dict[str, Subcommand] = {}


def _add_weather_forecast_arguments(parser: argparse.ArgumentParser) -> None:
    """The subcommand takes no arguments."""


def _run_weather_forecast(args: argparse.Namespace) -> int:
    from ingestion import jobs
    from ingestion.db import build_engine

    engine = build_engine()
    try:
        with httpx.Client(timeout=30) as client:
            jobs.ingest_weather_forecast(engine, client, today=jobs.issue_date())
    finally:
        engine.dispose()
    return 0


SUBCOMMANDS["weather-forecast"] = Subcommand(
    help="Snapshot today's weather forecast for every location into raw.weather_forecast",
    add_arguments=_add_weather_forecast_arguments,
    run=_run_weather_forecast,
)


def _add_calendar_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="first day (ISO)")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="last day (ISO)")


def _run_calendar(args: argparse.Namespace) -> int:
    from ingestion import jobs
    from ingestion.db import build_engine

    engine = build_engine()
    try:
        jobs.load_calendar(engine, args.start, args.end)
    finally:
        engine.dispose()
    return 0


SUBCOMMANDS["calendar"] = Subcommand(
    help="Load ref.calendar (one row per day, national holidays) for a date range",
    add_arguments=_add_calendar_arguments,
    run=_run_calendar,
)


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _add_ons_load_arguments(parser: argparse.ArgumentParser) -> None:
    from ingestion.jobs import ONS_WINDOW_DAYS

    parser.add_argument("--end", type=date.fromisoformat, help="last day (ISO), default today")
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--start", type=date.fromisoformat, help="first day (ISO)")
    window.add_argument(
        "--days",
        type=_positive_int,
        default=ONS_WINDOW_DAYS,
        help=f"window length in days ending at --end (default {ONS_WINDOW_DAYS})",
    )


def _run_ons_load(args: argparse.Namespace) -> int:
    from ingestion import jobs
    from ingestion.db import build_engine

    end = args.end or jobs.issue_date()
    start = args.start or end - timedelta(days=args.days - 1)
    engine = build_engine()
    try:
        with httpx.Client(timeout=60) as client:
            jobs.ingest_ons_load(engine, client, start, end)
    finally:
        engine.dispose()
    return 0


SUBCOMMANDS["ons-load"] = Subcommand(
    help="Upsert ONS daily load into raw.ons_daily_load (rolling window or --start/--end backfill)",
    add_arguments=_add_ons_load_arguments,
    run=_run_ons_load,
)


_OBSERVED_TIMEOUT_SECONDS = 30
_OBSERVED_BACKFILL_TIMEOUT_SECONDS = 120


def _add_weather_observed_arguments(parser: argparse.ArgumentParser) -> None:
    from ingestion.jobs import OBSERVED_WINDOW_DAYS

    parser.add_argument("--end", type=date.fromisoformat, help="last day (ISO), default yesterday")
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--start", type=date.fromisoformat, help="first day (ISO)")
    window.add_argument(
        "--days",
        type=_positive_int,
        default=OBSERVED_WINDOW_DAYS,
        help=f"window length in days ending at --end (default {OBSERVED_WINDOW_DAYS})",
    )


def _run_weather_observed(args: argparse.Namespace) -> int:
    from ingestion import jobs
    from ingestion.db import build_engine

    end = args.end or jobs.issue_date() - timedelta(days=jobs.OBSERVED_END_LAG_DAYS)
    start = args.start or end - timedelta(days=args.days - 1)
    if (end - start).days + 1 > jobs.OBSERVED_WINDOW_DAYS:
        timeout = _OBSERVED_BACKFILL_TIMEOUT_SECONDS
    else:
        timeout = _OBSERVED_TIMEOUT_SECONDS
    engine = build_engine()
    try:
        with httpx.Client(timeout=timeout) as client:
            jobs.ingest_weather_observed(engine, client, start, end)
    finally:
        engine.dispose()
    return 0


SUBCOMMANDS["weather-observed"] = Subcommand(
    help=(
        "Upsert observed weather (ERA5 archive) into raw.weather_observed "
        "(rolling window ending yesterday or --start/--end backfill)"
    ),
    add_arguments=_add_weather_observed_arguments,
    run=_run_weather_observed,
)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(prog="python -m ingestion")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, subcommand in SUBCOMMANDS.items():
        subparser = subparsers.add_parser(name, help=subcommand.help)
        subcommand.add_arguments(subparser)

    args = parser.parse_args(argv)
    name = args.command
    try:
        return SUBCOMMANDS[name].run(args)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        logger.error("subcommand %s failed", name)
        return 1
