"""Tests for the ``python -m ingestion`` CLI (plan 11, cases 1 to 8).

"Effective code" of ``main(argv)`` is the returned value or, if ``main`` raises ``SystemExit``,
its ``code``. Usage errors may use either form.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def effective_code(argv: list[str]) -> int:
    from ingestion.cli import main

    try:
        code = main(argv)
    except SystemExit as exit_info:
        code = exit_info.code
    return 0 if code is None else code


def register(monkeypatch: pytest.MonkeyPatch, name: str, run, add_arguments=None) -> None:
    from ingestion import cli

    subcommand = cli.Subcommand(
        help=f"test subcommand {name}",
        add_arguments=add_arguments or (lambda parser: None),
        run=run,
    )
    monkeypatch.setitem(cli.SUBCOMMANDS, name, subcommand)


def test_help_exits_zero_and_prints_usage(capsys):
    assert effective_code(["--help"]) == 0
    out = capsys.readouterr().out
    assert "usage" in out
    assert "python -m ingestion" in out


def test_missing_subcommand_exits_two_with_usage_on_stderr(capsys):
    assert effective_code([]) == 2
    assert "usage" in capsys.readouterr().err


def test_unknown_subcommand_exits_two_with_invalid_choice(capsys):
    assert effective_code(["does-not-exist"]) == 2
    assert "invalid choice" in capsys.readouterr().err


def test_registered_subcommand_returning_zero_makes_main_return_zero(monkeypatch):
    from ingestion.cli import main

    register(monkeypatch, "ok", lambda args: 0)
    assert main(["ok"]) == 0


def test_arguments_reach_the_subcommand_run(monkeypatch):
    from ingestion.cli import main

    def add_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--day")

    register(
        monkeypatch,
        "echo",
        lambda args: 0 if args.day == "2026-11-07" else 1,
        add_arguments,
    )
    assert main(["echo", "--day", "2026-11-07"]) == 0


def test_subcommand_returning_one_makes_main_return_one(monkeypatch):
    from ingestion.cli import main

    register(monkeypatch, "fails", lambda args: 1)
    assert main(["fails"]) == 1


def test_unhandled_exception_returns_one_and_prints_traceback_to_stderr(monkeypatch, capsys):
    from ingestion.cli import main

    def explode(args: argparse.Namespace) -> int:
        raise RuntimeError("boom")

    register(monkeypatch, "explodes", explode)
    assert main(["explodes"]) == 1
    err = capsys.readouterr().err
    assert "Traceback" in err
    assert "boom" in err


def test_module_entry_point_propagates_help_exit_code():
    result = subprocess.run(
        [sys.executable, "-m", "ingestion", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout
