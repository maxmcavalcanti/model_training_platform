"""Command line entry point: ``python -m ingestion <subcommand>``.

Exit codes: 0 success, 1 execution or quality-check failure, 2 incorrect usage.
"""

import argparse
import logging
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass

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
