"""Security policy tests (plan S2, cases 15 to 22; ADR 0006, item 1).

Static checks over ``SECURITY.md``: it points reporters to GitHub private vulnerability
reporting, has the expected sections, and never leaks an e-mail address, an IPv4 literal or a
``*.ts.net`` host in a public repository. The detectors are exercised with positive and
negative examples so a passing policy test cannot be an artifact of a detector that finds
nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SECURITY_FILE = REPO_ROOT / "SECURITY.md"

ADVISORY_LINK = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/security/advisories/new")
EMAIL = re.compile(r"(?<![\w/])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.]*\d)")
TS_NET_HOST = re.compile(r"\.ts\.net\b", re.IGNORECASE)
REQUIRED_SECTIONS = ("Reporting a vulnerability", "What to expect", "Scope")


# --------------------------------------------------------------------------- check functions


def email_findings(text: str) -> list[str]:
    """Case 18 and 21: e-mail addresses (git@host:path counts; ``owner/repo@sha`` does not)."""
    return EMAIL.findall(text)


def ipv4_findings(text: str) -> list[str]:
    """Case 19 and 22: dotted-quad IPv4 literals."""
    return IPV4.findall(text)


def ts_net_findings(text: str) -> list[str]:
    """Case 20 and 22: hostnames under ``ts.net``, any letter case."""
    return TS_NET_HOST.findall(text)


def structure_problems(text: str) -> list[str]:
    """Cases 16 and 17: advisory link, the button text, sections and the out-of-scope list."""
    problems = []
    if not ADVISORY_LINK.search(text):
        problems.append("no https://github.com/<owner>/<repo>/security/advisories/new link")
    if "Report a vulnerability" not in text:
        problems.append("missing text 'Report a vulnerability'")
    for section in REQUIRED_SECTIONS:
        if not re.search(rf"^#+\s+{re.escape(section)}\s*$", text, re.MULTILINE):
            problems.append(f"missing section '{section}'")
    if "Out of scope" not in text:
        problems.append("missing text 'Out of scope'")
    return problems


# ----------------------------------------------------------- policy on the real file


@pytest.fixture(scope="module")
def security_text() -> str:
    assert SECURITY_FILE.is_file(), f"{SECURITY_FILE} does not exist"
    return SECURITY_FILE.read_text(encoding="utf-8")


def test_security_file_exists_at_repository_root():
    assert SECURITY_FILE.is_file()


def test_security_file_has_link_sections_and_scope(security_text):
    assert structure_problems(security_text) == []


def test_security_file_has_no_email(security_text):
    assert email_findings(security_text) == []


def test_security_file_has_no_ipv4(security_text):
    assert ipv4_findings(security_text) == []


def test_security_file_has_no_ts_net_host(security_text):
    assert ts_net_findings(security_text) == []


# --------------------------------------------------------------------------- examples (21, 22)


@pytest.mark.parametrize(
    "text",
    ["contact me at a@b.co", "user.name+x@example.com.br", "git@github.com:owner/repo"],
)
def test_email_is_detected(text):
    assert email_findings(text) != []


@pytest.mark.parametrize(
    "text",
    [
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "@dependabot rebase",
    ],
)
def test_non_email_is_not_detected(text):
    assert email_findings(text) == []


@pytest.mark.parametrize("text", ["100.64.0.1", "192.0.2.10:5432"])
def test_ipv4_is_detected(text):
    assert ipv4_findings(text) != []


@pytest.mark.parametrize("text", ["v7.0.1", "16.15"])
def test_non_ipv4_is_not_detected(text):
    assert ipv4_findings(text) == []


@pytest.mark.parametrize("text", ["vps.tail1234.ts.net", "VPS.TAIL1234.TS.NET"])
def test_ts_net_host_is_detected(text):
    assert ts_net_findings(text) != []


def test_tailscale_word_is_not_a_ts_net_host():
    assert ts_net_findings("Tailscale") == []


GOOD_POLICY = """# Security policy

## Reporting a vulnerability

Click **Report a vulnerability** or open
https://github.com/owner/repo/security/advisories/new

## What to expect

Best effort.

## Scope

Out of scope: upstream projects.
"""


def test_good_policy_structure_is_accepted():
    assert structure_problems(GOOD_POLICY) == []


@pytest.mark.parametrize(
    "broken",
    [
        GOOD_POLICY.replace("security/advisories/new", "security"),
        GOOD_POLICY.replace("Report a vulnerability", "Report it"),
        GOOD_POLICY.replace("## What to expect", "## Timing"),
        GOOD_POLICY.replace("Out of scope", "Excluded"),
    ],
)
def test_broken_policy_structure_is_rejected(broken):
    assert structure_problems(broken) != []
