"""Infra policy tests for every ``infra/docker-compose*.yml`` (plan 03, cases 1 to 8).

The check functions are defined here and exercised with embedded negative examples, so a
passing policy test cannot be an artifact of a check that accepts everything.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_DIR = REPO_ROOT / "infra"
ENV_EXAMPLE = INFRA_DIR / ".env.example"
MAIN_COMPOSE = INFRA_DIR / "docker-compose.yml"

# Services allowed to publish ports in this PR (case 3). Later PRs extend this list.
PORT_PUBLISHING_SERVICES = frozenset({"health"})

LOOPBACK = "127.0.0.1"
TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")

SECRET_KEY_MARKERS = ("PASSWORD", "SENHA", "TOKEN", "SECRET", "HASH")
ENV_REFERENCE = re.compile(r"^\$\{[^}]+\}$")

# "127.0.0.1:8080:8080" or "${X_BIND_IP:-<default>}:8080:8080" (the default is validated by
# is_acceptable_port), optionally followed by a protocol such as "/tcp". A bare "${X_BIND_IP}"
# still matches here (default is None) so that is_acceptable_port can reject it explicitly.
SHORT_PORT = re.compile(
    r"^(?P<ip>127\.0\.0\.1|\$\{(?P<var>[A-Z][A-Z0-9_]*_BIND_IP)(?::-(?P<default>[^}]*))?\})"
    r":(?P<host>\d+):(?P<container>\d+)(?:/[a-z]+)?$"
)


# --------------------------------------------------------------------------- check functions


def load_compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def services_of(compose: dict) -> dict:
    return compose.get("services") or {}


def services_missing_restart(services: dict) -> list[str]:
    """Case 1: services without ``profiles`` must use ``restart: unless-stopped``."""
    return [
        name
        for name, spec in services.items()
        if not spec.get("profiles") and spec.get("restart") != "unless-stopped"
    ]


def services_missing_mem_limit(services: dict) -> list[str]:
    """Case 2: every service, profiles or not, must set ``mem_limit``."""
    return [name for name, spec in services.items() if not spec.get("mem_limit")]


def services_with_forbidden_ports(services: dict, allowed: frozenset[str]) -> list[str]:
    """Case 3: only allow-listed services may declare ``ports``."""
    return [name for name, spec in services.items() if spec.get("ports") and name not in allowed]


def is_acceptable_port(port: object) -> bool:
    """Case 4: the published port has an explicit loopback host IP.

    Accepted: a literal ``127.0.0.1`` or ``${X_BIND_IP:-127.0.0.1}``. A bare ``${X_BIND_IP}``
    is rejected: when the variable is missing it becomes ``:8080:8080`` and Docker publishes
    on 0.0.0.0, bypassing ufw.
    """
    if isinstance(port, dict):
        # Long syntax: only a literal 127.0.0.1 host_ip is accepted.
        return port.get("host_ip") == LOOPBACK and port.get("published") is not None
    if not isinstance(port, str):
        return False
    match = SHORT_PORT.match(port)
    if match is None:
        return False
    if match.group("var") is None:
        return True  # literal 127.0.0.1
    # The variable form requires a default, and it must be exactly 127.0.0.1.
    return match.group("default") == LOOPBACK


def bad_ports(services: dict) -> list[tuple[str, object]]:
    return [
        (name, port)
        for name, spec in services.items()
        for port in spec.get("ports") or []
        if not is_acceptable_port(port)
    ]


def parse_env_file(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        values[key] = value
    return values


def is_acceptable_bind_ip(value: str) -> bool:
    """Case 5: loopback or an address in the Tailscale range 100.64.0.0/10."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return str(address) == LOOPBACK or address in TAILSCALE_NETWORK


def bad_bind_ips(env_text: str) -> list[str]:
    return [
        key
        for key, value in parse_env_file(env_text).items()
        if key.endswith("_BIND_IP") and not is_acceptable_bind_ip(value)
    ]


def environment_items(environment: object) -> list[tuple[str, str | None]]:
    """Normalize the compose ``environment`` (mapping or ``KEY=VALUE`` list)."""
    if not environment:
        return []
    if isinstance(environment, dict):
        return [(str(k), None if v is None else str(v)) for k, v in environment.items()]
    items = []
    for entry in environment:
        key, sep, value = str(entry).partition("=")
        items.append((key, value if sep else None))
    return items


def literal_secret_keys(environment: object) -> list[str]:
    """Case 6: secret-looking keys may only hold ``${...}`` references."""
    offenders = []
    for key, value in environment_items(environment):
        looks_secret = any(marker in key.upper() for marker in SECRET_KEY_MARKERS)
        if looks_secret and value is not None and not ENV_REFERENCE.match(value):
            offenders.append(key)
    return offenders


def relative_bind_sources(volumes: list | None) -> list[str]:
    """Host-side sources of volumes that use a relative (``./``) path."""
    sources = []
    for volume in volumes or []:
        if isinstance(volume, dict):
            source = volume.get("source")
        else:
            source = str(volume).split(":", 1)[0]
        if isinstance(source, str) and source.startswith("./"):
            sources.append(source)
    return sources


def missing_relative_mounts(volumes: list | None, base_dir: Path) -> list[str]:
    """Case 8: relative mount sources (relative to the compose file) must exist."""
    return [s for s in relative_bind_sources(volumes) if not (base_dir / s).exists()]


def loopback_published_ports(service: dict, env: dict[str, str]) -> set[int]:
    """Host ports of ``service`` that are published on loopback (used by case 9)."""
    ports: set[int] = set()
    for port in service.get("ports") or []:
        if not is_acceptable_port(port):
            continue
        if isinstance(port, dict):
            ports.add(int(port["published"]))
            continue
        match = SHORT_PORT.match(port)
        assert match is not None
        # An acceptable short port is always loopback: a literal 127.0.0.1 or a
        # "${X_BIND_IP:-127.0.0.1}" default, so ``env`` is not needed to resolve it.
        ports.add(int(match.group("host")))
    return ports


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def compose_files() -> list[Path]:
    assert MAIN_COMPOSE.is_file(), f"{MAIN_COMPOSE} does not exist"
    return sorted(INFRA_DIR.glob("docker-compose*.yml"))


@pytest.fixture
def all_services(compose_files: list[Path]) -> list[tuple[Path, dict]]:
    return [(path, services_of(load_compose(path))) for path in compose_files]


# --------------------------------------------------------------------------- policy tests


def test_main_compose_file_exists_and_has_services(all_services):
    assert MAIN_COMPOSE in [path for path, _ in all_services]
    for path, services in all_services:
        assert services, f"{path.name} defines no services"


def test_every_service_without_profiles_restarts_unless_stopped(all_services):
    for path, services in all_services:
        assert services_missing_restart(services) == [], path.name


def test_every_service_has_mem_limit(all_services):
    for path, services in all_services:
        assert services_missing_mem_limit(services) == [], path.name


def test_only_allow_listed_services_publish_ports(all_services):
    for path, services in all_services:
        offenders = services_with_forbidden_ports(services, PORT_PUBLISHING_SERVICES)
        assert offenders == [], path.name


def test_every_published_port_has_explicit_safe_host_ip(all_services):
    for path, services in all_services:
        assert bad_ports(services) == [], path.name


def test_env_example_exists_and_bind_ips_are_loopback_or_tailscale():
    assert ENV_EXAMPLE.is_file(), f"{ENV_EXAMPLE} does not exist"
    assert bad_bind_ips(ENV_EXAMPLE.read_text(encoding="utf-8")) == []


def test_no_literal_secrets_in_environment(all_services):
    for path, services in all_services:
        for name, spec in services.items():
            assert literal_secret_keys(spec.get("environment")) == [], f"{path.name}:{name}"


def test_env_file_is_not_versioned():
    result = subprocess.run(
        ["git", "ls-files", "infra/.env"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == ""


def test_env_example_exists():
    assert ENV_EXAMPLE.is_file(), f"{ENV_EXAMPLE} does not exist"


def test_relative_volume_sources_exist(all_services):
    for path, services in all_services:
        for name, spec in services.items():
            missing = missing_relative_mounts(spec.get("volumes"), path.parent)
            assert missing == [], f"{path.name}:{name}"


# --------------------------------------------------------------------------- negative examples


@pytest.mark.parametrize(
    "port",
    [
        "127.0.0.1:8080:8080",
        "127.0.0.1:8080:8080/tcp",
        "${HEALTH_BIND_IP:-127.0.0.1}:8080:8080",
        "${X_BIND_IP:-127.0.0.1}:8080:8080",
        "${X_BIND_IP:-127.0.0.1}:8080:8080/tcp",
        {"target": 8080, "published": 8080, "host_ip": "127.0.0.1"},
    ],
)
def test_port_check_accepts_safe_ports(port):
    assert is_acceptable_port(port)


@pytest.mark.parametrize(
    "port",
    [
        "0.0.0.0:8080:8080",
        "8080:8080",
        "8080",
        8080,
        "::8080:8080",
        "[::]:8080:8080",
        "::1:8080:8080",
        "192.168.1.10:8080:8080",
        "100.64.0.1:8080:8080",
        "localhost:8080:8080",
        "${HEALTH_PORT}:8080:8080",
        "${HEALTH_BIND_IP:-0.0.0.0}:8080:8080",
        "${X_BIND_IP}:8080:8080",
        "${X_BIND_IP}:8080:8080/tcp",
        "${X_BIND_IP:-0.0.0.0}:8080:8080",
        "${X_BIND_IP:-}:8080:8080",
        "${X_BIND_IP:-100.64.0.1}:8080:8080",
        {"target": 8080, "published": 8080},
        {"target": 8080, "published": 8080, "host_ip": "0.0.0.0"},
        {"target": 8080, "published": 8080, "host_ip": "::"},
        {"target": 8080, "published": 8080, "host_ip": "100.64.0.1"},
    ],
)
def test_port_check_rejects_unsafe_ports(port):
    assert not is_acceptable_port(port)


def test_bad_ports_reports_the_offending_service():
    services = {
        "good": {"ports": ["127.0.0.1:1:1"]},
        "bad": {"ports": ["127.0.0.1:2:2", "0.0.0.0:3:3"]},
    }
    assert bad_ports(services) == [("bad", "0.0.0.0:3:3")]


def test_restart_check_rejects_missing_or_wrong_policy_but_skips_profiles():
    services = {
        "ok": {"restart": "unless-stopped"},
        "missing": {},
        "always": {"restart": "always"},
        "optional": {"profiles": ["dev"]},
    }
    assert services_missing_restart(services) == ["missing", "always"]


def test_mem_limit_check_applies_even_with_profiles():
    services = {"ok": {"mem_limit": "16m"}, "bare": {}, "optional": {"profiles": ["dev"]}}
    assert services_missing_mem_limit(services) == ["bare", "optional"]


def test_port_allow_list_check_rejects_unlisted_services():
    services = {"health": {"ports": ["x"]}, "postgres": {"ports": ["y"]}, "worker": {}}
    assert services_with_forbidden_ports(services, frozenset({"health"})) == ["postgres"]


@pytest.mark.parametrize("value", ["127.0.0.1", "100.64.0.0", "100.100.100.100", "100.127.255.255"])
def test_bind_ip_check_accepts_loopback_and_tailscale_range(value):
    assert is_acceptable_bind_ip(value)


@pytest.mark.parametrize(
    "value",
    ["0.0.0.0", "", "::", "192.168.0.1", "100.63.255.255", "100.128.0.0", "${OTHER}", "localhost"],
)
def test_bind_ip_check_rejects_everything_else(value):
    assert not is_acceptable_bind_ip(value)


def test_bad_bind_ips_only_inspects_bind_ip_keys():
    text = (
        "# comment\n"
        "HEALTH_BIND_IP=0.0.0.0\n"
        "POSTGRES_BIND_IP='127.0.0.1'\n"
        "TS_HOSTNAME=x\n"
        "OK_BIND_IP=100.64.0.9\n"
    )
    assert bad_bind_ips(text) == ["HEALTH_BIND_IP"]


@pytest.mark.parametrize(
    "environment",
    [
        {"POSTGRES_PASSWORD": "hunter2"},
        {"DB_SENHA": "x"},
        {"API_TOKEN": "abc"},
        {"APP_SECRET": "${A}suffix"},
        {"PASSWORD_HASH": "$2b$12$abcdef"},
        {"db_password": "x"},
        ["API_TOKEN=abc"],
    ],
)
def test_secret_check_rejects_literal_values(environment):
    assert literal_secret_keys(environment) != []


@pytest.mark.parametrize(
    "environment",
    [
        {"POSTGRES_PASSWORD": "${POSTGRES_PASSWORD}"},
        {"API_TOKEN": "${API_TOKEN:?required}"},
        ["API_TOKEN=${API_TOKEN}"],
        {"TZ": "UTC", "MODE": "production"},
        {"API_TOKEN": None},
        None,
    ],
)
def test_secret_check_accepts_references_and_non_secret_keys(environment):
    assert literal_secret_keys(environment) == []


def test_mount_check_rejects_missing_relative_sources(tmp_path):
    (tmp_path / "present").mkdir()
    volumes = ["./present:/a:ro", "./absent:/b", "named_volume:/c", "/abs/path:/d"]
    assert missing_relative_mounts(volumes, tmp_path) == ["./absent"]


def test_mount_check_handles_long_syntax(tmp_path):
    volumes = [{"type": "bind", "source": "./absent", "target": "/x"}]
    assert missing_relative_mounts(volumes, tmp_path) == ["./absent"]
