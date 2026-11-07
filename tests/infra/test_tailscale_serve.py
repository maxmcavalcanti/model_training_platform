"""Policy tests for ``infra/scripts/tailscale-serve.sh`` (plan 03, cases 9 to 11)."""

from __future__ import annotations

import re

import pytest

from tests.infra.test_compose import (
    ENV_EXAMPLE,
    INFRA_DIR,
    MAIN_COMPOSE,
    load_compose,
    loopback_published_ports,
    parse_env_file,
    services_of,
)

SERVE_SCRIPT = INFRA_DIR / "scripts" / "tailscale-serve.sh"

UI_SERVICES = ("health", "mlflow", "prefect-server", "grafana")

MAPPING = re.compile(r"tailscale\s+serve\b.*--https=(\d+)\s+http://127\.0\.0\.1:(\d+)\s*$")
RESET = re.compile(r"^\s*tailscale\s+serve\s+reset\s*$")
STRICT_MODE = "set -euo pipefail"


# --------------------------------------------------------------------------- check functions


def code_lines(script_text: str) -> list[str]:
    """Non-blank, non-comment lines (the shebang counts as a comment)."""
    return [
        line.strip()
        for line in script_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def serve_mappings(script_text: str) -> list[tuple[int, int]]:
    """(tailnet https port, loopback target port) per mapping line."""
    mappings = []
    for line in code_lines(script_text):
        match = MAPPING.search(line)
        if match:
            mappings.append((int(match.group(1)), int(match.group(2))))
    return mappings


def mapping_problems(script_text: str, loopback_ports: set[int]) -> list[str]:
    """Case 9: script and compose must agree in both directions."""
    problems = []
    mappings = serve_mappings(script_text)
    for https_port, target_port in mappings:
        if https_port != target_port:
            problems.append(f"https {https_port} does not match target {target_port}")
        if target_port not in loopback_ports:
            problems.append(f"orphan script entry for port {target_port}")
    targets = {target for _, target in mappings}
    for port in sorted(loopback_ports - targets):
        problems.append(f"compose port {port} is not served")
    return problems


def mentions_funnel(script_text: str) -> bool:
    """Case 10."""
    return "funnel" in script_text.lower()


def header_problems(script_text: str) -> list[str]:
    """Case 11: strict mode first, then ``tailscale serve reset`` before any mapping."""
    problems = []
    lines = code_lines(script_text)
    if not lines or lines[0] != STRICT_MODE:
        problems.append("script does not start with 'set -euo pipefail'")
    reset_index = next((i for i, line in enumerate(lines) if RESET.match(line)), None)
    mapping_indexes = [i for i, line in enumerate(lines) if MAPPING.search(line)]
    if reset_index is None:
        problems.append("no 'tailscale serve reset'")
    elif mapping_indexes and reset_index > min(mapping_indexes):
        problems.append("'tailscale serve reset' comes after a mapping line")
    return problems


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def script_text() -> str:
    assert SERVE_SCRIPT.is_file(), f"{SERVE_SCRIPT} does not exist"
    return SERVE_SCRIPT.read_text(encoding="utf-8")


@pytest.fixture
def ui_loopback_ports() -> set[int]:
    assert MAIN_COMPOSE.is_file(), f"{MAIN_COMPOSE} does not exist"
    env = parse_env_file(ENV_EXAMPLE.read_text(encoding="utf-8")) if ENV_EXAMPLE.is_file() else {}
    ports: set[int] = set()
    for path in sorted(INFRA_DIR.glob("docker-compose*.yml")):
        services = services_of(load_compose(path))
        for name in UI_SERVICES:
            if name in services:
                ports |= loopback_published_ports(services[name], env)
    return ports


# --------------------------------------------------------------------------- policy tests


def test_script_and_compose_loopback_ports_match_both_ways(script_text, ui_loopback_ports):
    assert ui_loopback_ports, "no UI service publishes a loopback port"
    assert mapping_problems(script_text, ui_loopback_ports) == []


def test_script_never_mentions_funnel(script_text):
    assert not mentions_funnel(script_text)


def test_script_header_is_strict_and_resets_before_mappings(script_text):
    assert header_problems(script_text) == []
    assert serve_mappings(script_text), "script has no mapping lines"


# --------------------------------------------------------------------------- negative examples

GOOD_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail

tailscale serve reset
tailscale serve --bg --https=8080 http://127.0.0.1:8080
"""

SERVE_8080 = "tailscale serve --bg --https=8080 http://127.0.0.1:8080\n"


def test_good_script_passes_every_check():
    assert serve_mappings(GOOD_SCRIPT) == [(8080, 8080)]
    assert mapping_problems(GOOD_SCRIPT, {8080}) == []
    assert not mentions_funnel(GOOD_SCRIPT)
    assert header_problems(GOOD_SCRIPT) == []


def test_mapping_check_rejects_orphan_script_entry():
    script = GOOD_SCRIPT + "tailscale serve --bg --https=5000 http://127.0.0.1:5000\n"
    assert mapping_problems(script, {8080}) == ["orphan script entry for port 5000"]


def test_mapping_check_rejects_compose_port_missing_from_script():
    assert mapping_problems(GOOD_SCRIPT, {8080, 5000}) == ["compose port 5000 is not served"]


def test_mapping_check_rejects_mismatched_https_and_target_ports():
    script = "tailscale serve --bg --https=15000 http://127.0.0.1:5000\n"
    assert mapping_problems(script, {5000}) == ["https 15000 does not match target 5000"]


def test_mapping_check_ignores_commented_lines():
    script = "# tailscale serve --bg --https=9999 http://127.0.0.1:9999\n" + GOOD_SCRIPT
    assert serve_mappings(script) == [(8080, 8080)]


def test_mapping_check_does_not_pass_on_empty_script():
    assert mapping_problems("", {8080}) == ["compose port 8080 is not served"]


@pytest.mark.parametrize(
    "script",
    [
        "tailscale funnel --bg 8080\n",
        "tailscale serve --bg --funnel --https=8080 http://127.0.0.1:8080\n",
        "tailscale serve --bg --https=8080 http://127.0.0.1:8080  # also FUNNEL it\n",
    ],
)
def test_funnel_check_rejects_funnel_usage(script):
    assert mentions_funnel(script)


@pytest.mark.parametrize(
    ("script", "expected_problems"),
    [
        ("tailscale serve reset\n" + SERVE_8080, 1),
        ("#!/usr/bin/env bash\nset -e\ntailscale serve reset\n", 1),
        ("#!/usr/bin/env bash\nset -euo pipefail\n" + SERVE_8080, 1),
        ("set -euo pipefail\n" + SERVE_8080 + "tailscale serve reset\n", 1),
        ("", 2),
    ],
)
def test_header_check_rejects_bad_scripts(script, expected_problems):
    assert len(header_problems(script)) == expected_problems
