"""Guards the ruff `S` (flake8-bandit) configuration of the project (plan S4, ADR 0006).

Each probe feeds a snippet to ruff through stdin with the project configuration (no
`--select`, no `--isolated`) and a fictitious path, then reads the reported `S` codes.
"""

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ASSERT_SNIPPET = "def f(x):\n    assert x\n"
SQL_FSTRING_SNIPPET = 'def q(table):\n    return f"SELECT a FROM {table}"\n'
PASSWORD_SNIPPET = 'password = "hunter2"\n'
BIND_ALL_SNIPPET = 'HOST = "0.0.0.0"\n'
# The argv is not a literal on purpose: recent ruff versions skip S603 for all-literal argv.
SUBPROCESS_SNIPPET = (
    "import subprocess\n\n\ndef run(args):\n    subprocess.run(args, check=False)\n"
)

PRODUCTION_PATH = "ingestion/lint_probe.py"
FLOWS_PATH = "flows/lint_probe.py"
MIGRATION_PATH = "migrations/versions/9999_lint_probe.py"
TEST_PATH = "tests/test_lint_probe.py"
INFRA_TEST_PATH = "tests/infra/test_lint_probe.py"

WHOLE_REPO_GLOBS = {"*", "**", "**/*.py", "*.py"}


def reported_security_codes(snippet: str, path: str) -> set[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--output-format",
            "json",
            "--stdin-filename",
            path,
            "-",
        ],
        input=snippet,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    return {item["code"] for item in json.loads(result.stdout) if item["code"].startswith("S")}


def load_ruff_lint_config() -> dict:
    with (REPO_ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)["tool"]["ruff"]["lint"]


def test_assert_is_reported_in_production_code():
    assert "S101" in reported_security_codes(ASSERT_SNIPPET, PRODUCTION_PATH)


def test_assert_is_allowed_in_tests():
    assert "S101" not in reported_security_codes(ASSERT_SNIPPET, TEST_PATH)


def test_string_built_sql_is_reported_in_production_code():
    assert "S608" in reported_security_codes(SQL_FSTRING_SNIPPET, PRODUCTION_PATH)


def test_string_built_sql_is_allowed_in_tests():
    assert "S608" not in reported_security_codes(SQL_FSTRING_SNIPPET, TEST_PATH)


def test_string_built_sql_is_still_reported_in_a_new_migration():
    assert "S608" in reported_security_codes(SQL_FSTRING_SNIPPET, MIGRATION_PATH)


def test_hardcoded_password_is_reported_in_flows():
    assert "S105" in reported_security_codes(PASSWORD_SNIPPET, FLOWS_PATH)


def test_hardcoded_password_is_reported_in_tests():
    assert "S105" in reported_security_codes(PASSWORD_SNIPPET, TEST_PATH)


def test_bind_to_all_interfaces_is_reported_in_production_code():
    assert "S104" in reported_security_codes(BIND_ALL_SNIPPET, PRODUCTION_PATH)


def test_bind_to_all_interfaces_is_reported_in_tests_outside_test_compose():
    assert "S104" in reported_security_codes(BIND_ALL_SNIPPET, INFRA_TEST_PATH)


def test_subprocess_is_reported_in_a_generic_test():
    assert "S603" in reported_security_codes(SUBPROCESS_SNIPPET, TEST_PATH)


def test_subprocess_is_reported_in_production_code():
    assert "S603" in reported_security_codes(SUBPROCESS_SNIPPET, PRODUCTION_PATH)


def test_security_rule_family_is_selected():
    assert "S" in load_ruff_lint_config()["select"]


def test_per_file_ignores_never_ignore_the_whole_security_family_or_other_families():
    per_file_ignores = load_ruff_lint_config().get("per-file-ignores", {})
    offenders = {
        (glob, code)
        for glob, codes in per_file_ignores.items()
        for code in codes
        if not re.fullmatch(r"S\d+", code)
    }
    assert offenders == set()


def test_per_file_ignores_never_cover_the_repo_or_production_packages():
    per_file_ignores = load_ruff_lint_config().get("per-file-ignores", {})
    offenders = {
        glob
        for glob in per_file_ignores
        if glob in WHOLE_REPO_GLOBS or glob.startswith(("ingestion/", "flows/"))
    }
    assert offenders == set()


def test_per_file_ignores_table_exists_for_the_documented_findings():
    assert load_ruff_lint_config().get("per-file-ignores")


def test_repository_passes_ruff_check_with_project_configuration():
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
