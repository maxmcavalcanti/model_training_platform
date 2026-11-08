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

# Services allowed to publish ports (case 3). Later PRs extend this list.
PORT_PUBLISHING_SERVICES = frozenset({"health", "postgres"})

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


# =========================================================================== plan 10
# Production ``postgres`` service in infra/docker-compose.yml (cases 1 to 6 and 8).
# Case 7 (tailscale serve --tcp) lives in test_tailscale_serve.py.

DEV_COMPOSE = INFRA_DIR / "docker-compose.dev.yml"
POSTGRES_DATA_DIR = "/var/lib/postgresql/data"
POSTGRES_PORT = "${POSTGRES_BIND_IP:-127.0.0.1}:5432:5432"
SCRAM = "scram-sha-256"
FIXED_MINOR_TAG = re.compile(r"^\d+\.\d+(\.\d+)?$")
# ``${NAME}`` / ``${NAME:?msg}`` / ``${NAME:-default}``; ``$${NAME}`` is an escape (removed first).
COMPOSE_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)([^}]*)\}")


def postgres_port_problems(service: dict) -> list[str]:
    """Case 1: exactly one port, 5432 -> 5432, host IP ``${POSTGRES_BIND_IP:-127.0.0.1}``."""
    ports = service.get("ports") or []
    if ports != [POSTGRES_PORT]:
        return [f"expected exactly {[POSTGRES_PORT]}, got {ports}"]
    return []


def named_volume_problems(service: dict, top_level_volumes: object, target: str) -> list[str]:
    """Case 2: ``target`` is backed by a named volume declared at the top level."""
    sources = []
    for volume in service.get("volumes") or []:
        if isinstance(volume, dict):
            if volume.get("target") == target:
                sources.append(volume.get("source"))
            continue
        parts = str(volume).split(":")
        if len(parts) >= 2 and parts[1] == target:
            sources.append(parts[0])
    if len(sources) != 1:
        return [f"expected one mount at {target}, got {sources}"]
    source = sources[0]
    if not isinstance(source, str) or source.startswith(("./", "../", "/")):
        return [f"{source!r} is a bind mount, not a named volume"]
    declared = top_level_volumes if isinstance(top_level_volumes, dict) else {}
    if source not in declared:
        return [f"volume {source!r} is not declared at the top level"]
    return []


def healthcheck_problems(service: dict) -> list[str]:
    """Case 3: a healthcheck with a non-empty ``test``."""
    healthcheck = service.get("healthcheck")
    if not isinstance(healthcheck, dict) or not healthcheck.get("test"):
        return ["missing healthcheck.test"]
    return []


def image_tag(service: dict) -> str | None:
    image = service.get("image")
    if not isinstance(image, str) or ":" not in image:
        return None
    return image.rsplit(":", 1)[1]


def image_tag_problems(prod: dict, dev: dict) -> list[str]:
    """Case 5: same tag in prod and dev, and a fixed ``major.minor`` tag."""
    problems = []
    prod_tag, dev_tag = image_tag(prod), image_tag(dev)
    if prod_tag != dev_tag:
        problems.append(f"prod tag {prod_tag!r} differs from dev tag {dev_tag!r}")
    if prod_tag is None or not FIXED_MINOR_TAG.match(prod_tag):
        problems.append(f"tag {prod_tag!r} is not a fixed major.minor tag")
    return problems


def required_variables(compose_text: str) -> set[str]:
    """Variables referenced without a ``:-`` default (``$${X}`` escapes do not count)."""
    unescaped = compose_text.replace("$$", "")
    return {
        name
        for name, rest in COMPOSE_REFERENCE.findall(unescaped)
        if not rest.startswith((":-", "-"))
    }


def undeclared_variables(compose_text: str, env_text: str) -> list[str]:
    """Case 6: required variables missing from ``.env.example``."""
    declared = set(parse_env_file(env_text))
    return sorted(required_variables(compose_text) - declared)


def auth_problems(environment: object) -> list[str]:
    """Case 8: scram-sha-256 for host auth, and no ``trust`` or ``md5`` anywhere."""
    values = dict(environment_items(environment))
    problems = []
    if values.get("POSTGRES_HOST_AUTH_METHOD") != SCRAM:
        problems.append("POSTGRES_HOST_AUTH_METHOD is not scram-sha-256")
    if f"--auth-host={SCRAM}" not in (values.get("POSTGRES_INITDB_ARGS") or ""):
        problems.append("POSTGRES_INITDB_ARGS lacks --auth-host=scram-sha-256")
    for key, value in values.items():
        lowered = (value or "").lower()
        if "trust" in lowered or "md5" in lowered:
            problems.append(f"{key} mentions trust or md5")
    return problems


@pytest.fixture
def main_compose() -> dict:
    return load_compose(MAIN_COMPOSE)


@pytest.fixture
def postgres_service(main_compose: dict) -> dict:
    service = services_of(main_compose).get("postgres")
    assert service is not None, "infra/docker-compose.yml has no 'postgres' service"
    return service


# --------------------------------------------------------------------------- plan 10 policy


def test_postgres_publishes_only_5432_on_loopback_default(postgres_service):
    assert postgres_port_problems(postgres_service) == []


def test_postgres_data_dir_is_a_declared_named_volume(postgres_service, main_compose):
    problems = named_volume_problems(
        postgres_service, main_compose.get("volumes"), POSTGRES_DATA_DIR
    )
    assert problems == []


def test_postgres_has_a_healthcheck(postgres_service):
    assert healthcheck_problems(postgres_service) == []


def test_postgres_password_comes_from_an_env_reference(postgres_service):
    environment = postgres_service.get("environment")
    assert "POSTGRES_PASSWORD" in dict(environment_items(environment))
    assert literal_secret_keys(environment) == []


def test_postgres_image_tag_matches_dev_and_is_fixed(postgres_service):
    dev_service = services_of(load_compose(DEV_COMPOSE))["postgres"]
    assert image_tag_problems(postgres_service, dev_service) == []


def test_every_required_compose_variable_is_declared_in_env_example():
    compose_text = MAIN_COMPOSE.read_text(encoding="utf-8")
    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert undeclared_variables(compose_text, env_text) == []


def test_postgres_requires_its_admin_variables_in_env_example(postgres_service):
    # Guards against dropping the ``:?`` / reference form: the vars must be required and declared.
    compose_text = MAIN_COMPOSE.read_text(encoding="utf-8")
    env_keys = set(parse_env_file(ENV_EXAMPLE.read_text(encoding="utf-8")))
    required = required_variables(compose_text)
    for name in ("POSTGRES_ADMIN_USER", "POSTGRES_ADMIN_PASSWORD"):
        assert name in required, f"{name} is not a required variable of the compose file"
        assert name in env_keys, f"{name} is missing from infra/.env.example"


def test_postgres_authentication_is_scram_sha_256(postgres_service):
    assert auth_problems(postgres_service.get("environment")) == []


# --------------------------------------------------------------------------- plan 10 negatives


def test_postgres_port_check_accepts_the_expected_port():
    assert postgres_port_problems({"ports": [POSTGRES_PORT]}) == []


@pytest.mark.parametrize(
    "ports",
    [
        ["${POSTGRES_BIND_IP}:5432:5432"],
        ["5432:5432"],
        ["0.0.0.0:5432:5432"],
        ["127.0.0.1:15432:5432"],
        [POSTGRES_PORT, "127.0.0.1:5433:5432"],
        [],
    ],
)
def test_postgres_port_check_rejects_everything_else(ports):
    assert postgres_port_problems({"ports": ports}) != []


def test_postgres_port_check_rejects_missing_ports_key():
    assert postgres_port_problems({}) != []


def test_named_volume_check_accepts_declared_named_volume():
    service = {"volumes": [f"pgdata:{POSTGRES_DATA_DIR}"]}
    assert named_volume_problems(service, {"pgdata": {}}, POSTGRES_DATA_DIR) == []


@pytest.mark.parametrize(
    ("service", "top_level"),
    [
        ({"volumes": [f"./pgdata:{POSTGRES_DATA_DIR}"]}, {"pgdata": {}}),
        ({"volumes": [f"../pgdata:{POSTGRES_DATA_DIR}"]}, {"pgdata": {}}),
        ({"volumes": [f"/srv/pg:{POSTGRES_DATA_DIR}"]}, {"pgdata": {}}),
        ({"volumes": [f"pgdata:{POSTGRES_DATA_DIR}"]}, {}),
        ({"volumes": [f"pgdata:{POSTGRES_DATA_DIR}"]}, None),
        ({"volumes": [f"other:{POSTGRES_DATA_DIR}"]}, {"pgdata": {}}),
        ({"volumes": ["pgdata:/somewhere/else"]}, {"pgdata": {}}),
        ({}, {"pgdata": {}}),
    ],
)
def test_named_volume_check_rejects_bind_mounts_and_undeclared_volumes(service, top_level):
    assert named_volume_problems(service, top_level, POSTGRES_DATA_DIR) != []


@pytest.mark.parametrize("service", [{}, {"healthcheck": {}}, {"healthcheck": {"test": []}}])
def test_healthcheck_check_rejects_missing_or_empty_test(service):
    assert healthcheck_problems(service) != []


def test_healthcheck_check_accepts_a_test():
    assert healthcheck_problems({"healthcheck": {"test": ["CMD", "true"]}}) == []


def test_image_tag_check_accepts_same_fixed_minor_tag():
    service = {"image": "postgres:16.15"}
    assert image_tag_problems(service, {"image": "postgres:16.15"}) == []


@pytest.mark.parametrize(
    ("prod", "dev"),
    [
        ("postgres:16", "postgres:16"),
        ("postgres:latest", "postgres:latest"),
        ("postgres", "postgres"),
        ("postgres:16.15", "postgres:16.14"),
        ("postgres:16.15", "postgres:16"),
    ],
)
def test_image_tag_check_rejects_floating_or_diverging_tags(prod, dev):
    assert image_tag_problems({"image": prod}, {"image": dev}) != []


def test_undeclared_variables_reports_required_ones_only():
    compose_text = "a: ${A}\nb: ${B:?x}\nc: ${C:-y}\nd: $${POSTGRES_USER}\n"
    assert undeclared_variables(compose_text, "A=1\n") == ["B"]


def test_undeclared_variables_is_empty_when_all_required_are_declared():
    compose_text = "a: ${A}\nb: ${B:?x}\nc: ${C:-y}\n"
    assert undeclared_variables(compose_text, "A=1\nB=2\n") == []


def test_undeclared_variables_ignores_commented_env_entries():
    assert undeclared_variables("a: ${A}\n", "# A=1\n") == ["A"]


GOOD_AUTH = {
    "POSTGRES_USER": "${POSTGRES_ADMIN_USER:?required}",
    "POSTGRES_PASSWORD": "${POSTGRES_ADMIN_PASSWORD:?required}",
    "POSTGRES_DB": "ml",
    "POSTGRES_HOST_AUTH_METHOD": SCRAM,
    "POSTGRES_INITDB_ARGS": f"--auth-host={SCRAM}",
}


def test_auth_check_accepts_scram_configuration():
    assert auth_problems(GOOD_AUTH) == []


@pytest.mark.parametrize(
    "environment",
    [
        {k: v for k, v in GOOD_AUTH.items() if k != "POSTGRES_HOST_AUTH_METHOD"},
        {**GOOD_AUTH, "POSTGRES_HOST_AUTH_METHOD": "trust"},
        {**GOOD_AUTH, "POSTGRES_HOST_AUTH_METHOD": "md5"},
        {k: v for k, v in GOOD_AUTH.items() if k != "POSTGRES_INITDB_ARGS"},
        {**GOOD_AUTH, "POSTGRES_INITDB_ARGS": "--auth-host=md5"},
        {**GOOD_AUTH, "POSTGRES_INITDB_ARGS": f"--auth-host={SCRAM} --auth-local=trust"},
        None,
    ],
)
def test_auth_check_rejects_missing_trust_and_md5(environment):
    assert auth_problems(environment) != []
