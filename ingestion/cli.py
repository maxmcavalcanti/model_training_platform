"""Command line entry point: ``python -m ingestion <subcommand>``.

Exit codes: 0 success, 1 execution or quality-check failure, 2 incorrect usage.
"""

import argparse
import logging
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Subcommand:
    help: str
    add_arguments: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], int]


SUBCOMMANDS: dict[str, Subcommand] = {}


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
