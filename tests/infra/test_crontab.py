"""Static policy tests for the interim scheduler crontab (plan 16, cases 1 to 8).

The check functions are exercised with embedded negative examples, so a passing policy test
cannot be an artifact of a check that accepts everything.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ingestion.cli import SUBCOMMANDS

REPO_ROOT = Path(__file__).resolve().parents[2]
CRONTAB = REPO_ROOT / "infra" / "cron" / "crontab"

COMMAND_FORM = re.compile(r"^python -m ingestion (?P<subcommand>\S+)(?: (?P<args>.*))?$")
FIXED_NUMBER = re.compile(r"^\d+$")
SCHEDULE_FIELD = re.compile(r"^[0-9*/,\-]+$")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=")
REDIRECT_MARKERS = (">", "|")
MIDNIGHT_HOURS = frozenset({23, 0})
FORECAST_LINE = "30 6 * * * python -m ingestion weather-forecast"


# --------------------------------------------------------------------------- check functions


def schedule_lines(text: str) -> list[str]:
    """Lines that are neither blank nor comments."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def split_line(line: str) -> tuple[list[str], str]:
    """Return (five schedule fields, command); the command is empty when absent."""
    parts = line.split(None, 5)
    fields = parts[:5]
    command = parts[5].strip() if len(parts) == 6 else ""
    return fields, command


def field_problems(line: str) -> list[str]:
    """Case 2: five schedule fields followed by a non-empty command."""
    fields, command = split_line(line)
    problems = []
    if len(fields) != 5:
        problems.append(f"{line!r}: expected 5 schedule fields, got {len(fields)}")
    for field in fields:
        if not SCHEDULE_FIELD.match(field):
            problems.append(f"{line!r}: {field!r} is not a schedule field")
    if not command:
        problems.append(f"{line!r}: empty command")
    return problems


def command_problems(line: str, known_subcommands: set[str]) -> list[str]:
    """Case 3: ``python -m ingestion <known subcommand> [args...]``."""
    _, command = split_line(line)
    match = COMMAND_FORM.match(command)
    if match is None:
        return [f"{line!r}: command is not 'python -m ingestion <subcommand>'"]
    if match.group("subcommand") not in known_subcommands:
        return [f"{line!r}: unknown subcommand {match.group('subcommand')!r}"]
    return []


def forecast_line_problems(lines: list[str]) -> list[str]:
    """Case 4: exactly one ``weather-forecast`` line, ``30 6 * * *``, no arguments."""
    matching = [
        line
        for line in lines
        if (m := COMMAND_FORM.match(split_line(line)[1]))
        and m.group("subcommand") == "weather-forecast"
    ]
    if len(matching) != 1:
        return [f"expected exactly one weather-forecast line, got {len(matching)}"]
    if " ".join(matching[0].split()) != FORECAST_LINE:
        return [f"{matching[0]!r} is not {FORECAST_LINE!r}"]
    return []


def fixed_time_problems(line: str) -> list[str]:
    """Case 5: minute and hour are plain numbers (one run per day)."""
    fields, _ = split_line(line)
    if len(fields) < 2:
        return [f"{line!r}: no minute and hour"]
    return [
        f"{line!r}: {name} {value!r} is not a fixed number"
        for name, value in (("minute", fields[0]), ("hour", fields[1]))
        if not FIXED_NUMBER.match(value)
    ]


def midnight_problems(line: str) -> list[str]:
    """Case 6: nothing runs in hours 23 and 0 (the snapshot day must not roll over)."""
    fields, _ = split_line(line)
    if len(fields) < 2 or not FIXED_NUMBER.match(fields[1]):
        return [f"{line!r}: hour is not a fixed number"]
    if int(fields[1]) in MIDNIGHT_HOURS:
        return [f"{line!r}: runs near midnight"]
    return []


def redirect_problems(line: str) -> list[str]:
    """Case 7: no output redirection or pipes (logs go to the container stdout)."""
    _, command = split_line(line)
    return [f"{line!r}: contains {marker!r}" for marker in REDIRECT_MARKERS if marker in command]


def environment_definition_problems(text: str) -> list[str]:
    """Case 8: no ``CRON_TZ=``, ``TZ=`` or ``NAME=value`` lines."""
    return [
        f"{line!r}: defines an environment variable"
        for line in schedule_lines(text)
        if ENV_ASSIGNMENT.match(line)
    ]


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def crontab_text() -> str:
    assert CRONTAB.is_file(), f"{CRONTAB} does not exist"
    return CRONTAB.read_text(encoding="utf-8")


@pytest.fixture
def lines(crontab_text: str) -> list[str]:
    return schedule_lines(crontab_text)


# --------------------------------------------------------------------------- policy tests


def test_crontab_exists_and_has_at_least_one_schedule_line(lines):
    assert lines != []


def test_every_schedule_line_has_five_fields_and_a_command(lines):
    assert lines != []
    for line in lines:
        assert field_problems(line) == []


def test_every_command_runs_a_known_ingestion_subcommand(lines):
    assert lines != []
    for line in lines:
        assert command_problems(line, set(SUBCOMMANDS)) == []


def test_weather_forecast_runs_once_at_0630_without_arguments(lines):
    assert forecast_line_problems(lines) == []


def test_every_line_runs_once_a_day_at_a_fixed_time(lines):
    assert lines != []
    for line in lines:
        assert fixed_time_problems(line) == []


def test_no_line_is_scheduled_near_midnight(lines):
    assert lines != []
    for line in lines:
        assert midnight_problems(line) == []


def test_no_line_redirects_output(lines):
    assert lines != []
    for line in lines:
        assert redirect_problems(line) == []


def test_crontab_defines_no_timezone_or_environment_variable(crontab_text):
    assert schedule_lines(crontab_text) != []
    assert environment_definition_problems(crontab_text) == []


# --------------------------------------------------------------------------- negative examples


def test_schedule_lines_skips_blank_and_comment_lines():
    text = "# comment\n\n  # indented comment\n30 6 * * * python -m ingestion weather-forecast\n"
    assert schedule_lines(text) == [FORECAST_LINE]


def test_field_check_accepts_a_complete_line():
    assert field_problems(FORECAST_LINE) == []


@pytest.mark.parametrize(
    "line",
    ["30 6 * * python -m ingestion weather-forecast", "30 6 * * *", "30 6 * *", ""],
)
def test_field_check_rejects_missing_fields_or_command(line):
    assert field_problems(line) != []


def test_command_check_accepts_known_subcommand_with_or_without_arguments():
    known = {"weather-forecast"}
    assert command_problems(FORECAST_LINE, known) == []
    assert command_problems(FORECAST_LINE + " --flag", known) == []


@pytest.mark.parametrize(
    "line",
    [
        "30 6 * * * python -m ingestion weather_forecast",
        "30 6 * * * python -m ingestion",
        "30 6 * * * uv run python -m ingestion weather-forecast",
        '30 6 * * * /bin/sh -c "python -m ingestion weather-forecast"',
        "30 6 * * * python -m ingestion nope",
    ],
)
def test_command_check_rejects_other_forms_and_unknown_subcommands(line):
    assert command_problems(line, {"weather-forecast"}) != []


def test_forecast_check_accepts_the_expected_line():
    assert forecast_line_problems([FORECAST_LINE]) == []


@pytest.mark.parametrize(
    "lines_",
    [
        [],
        [FORECAST_LINE, FORECAST_LINE],
        ["31 6 * * * python -m ingestion weather-forecast"],
        ["30 7 * * * python -m ingestion weather-forecast"],
        ["30 6 * * 1 python -m ingestion weather-forecast"],
        [FORECAST_LINE + " --extra"],
    ],
)
def test_forecast_check_rejects_missing_duplicate_or_deviating_lines(lines_):
    assert forecast_line_problems(lines_) != []


def test_fixed_time_check_accepts_numbers():
    assert fixed_time_problems(FORECAST_LINE) == []


@pytest.mark.parametrize(
    "line",
    [
        "*/5 6 * * * python -m ingestion weather-forecast",
        "30 * * * * python -m ingestion weather-forecast",
        "30 6,7 * * * python -m ingestion weather-forecast",
        "30 6-8 * * * python -m ingestion weather-forecast",
    ],
)
def test_fixed_time_check_rejects_ranges_lists_and_wildcards(line):
    assert fixed_time_problems(line) != []


def test_midnight_check_accepts_morning_hours():
    assert midnight_problems(FORECAST_LINE) == []


@pytest.mark.parametrize(
    "line",
    [
        "55 23 * * * python -m ingestion weather-forecast",
        "5 0 * * * python -m ingestion weather-forecast",
        "5 * * * * python -m ingestion weather-forecast",
    ],
)
def test_midnight_check_rejects_hours_23_and_0(line):
    assert midnight_problems(line) != []


def test_redirect_check_accepts_a_plain_command():
    assert redirect_problems(FORECAST_LINE) == []


@pytest.mark.parametrize(
    "suffix",
    [" >> /tmp/log", " > /tmp/log", " 2> /tmp/err", " | tee /tmp/log", " 2>&1"],
)
def test_redirect_check_rejects_redirection_and_pipes(suffix):
    assert redirect_problems(FORECAST_LINE + suffix) != []


def test_environment_check_accepts_comments_and_schedule_lines():
    assert environment_definition_problems(f"# TZ=UTC in a comment\n{FORECAST_LINE}\n") == []


@pytest.mark.parametrize(
    "text",
    [
        f"CRON_TZ=America/Sao_Paulo\n{FORECAST_LINE}\n",
        f"TZ=UTC\n{FORECAST_LINE}\n",
        f"MAILTO=me\n{FORECAST_LINE}\n",
        f"{FORECAST_LINE}\nPATH=/usr/bin\n",
    ],
)
def test_environment_check_rejects_variable_definitions(text):
    assert environment_definition_problems(text) != []
