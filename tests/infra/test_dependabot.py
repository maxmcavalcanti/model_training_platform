"""Dependabot configuration policy tests (plan S2, cases 1 to 14; ADR 0006, items 2, 4 and 5).

Static checks over ``.github/dependabot.yml``: four ecosystems, ``directories`` that exist and
hold the ecosystem manifest, weekly schedule, cooldown, one catch-all group per ecosystem, the
Postgres major ignore and the commit prefix. The check functions are exercised with embedded
negative examples, so a passing policy test cannot be an artifact of a check that accepts
everything. Functions that look at the disk take the repository root, so examples use tmp_path.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPENDABOT_FILE = REPO_ROOT / ".github" / "dependabot.yml"

EXPECTED_ECOSYSTEMS = frozenset({"github-actions", "docker", "docker-compose", "uv"})
REQUIRED_DIRECTORIES = {
    "github-actions": ["/"],
    "uv": ["/"],
}
REQUIRED_CONTAINED = {
    "docker": "/infra/jobs",
    "docker-compose": "/infra",
}
COMPOSE_GLOBS = ("docker-compose*.yml", "docker-compose*.yaml", "compose*.yml", "compose*.yaml")


# --------------------------------------------------------------------------- check functions


def _blocks(config: dict) -> list[dict]:
    updates = config.get("updates") if isinstance(config, dict) else None
    return [block for block in updates or [] if isinstance(block, dict)]


def _name(block: dict) -> str:
    return str(block.get("package-ecosystem"))


def _resolve(root: Path, directory: str) -> Path:
    return root / directory.lstrip("/")


def version_problems(config: dict) -> list[str]:
    """Case 1: ``version`` is the integer 2."""
    version = config.get("version") if isinstance(config, dict) else None
    if type(version) is not int or version != 2:
        return [f"version is {version!r}, expected the integer 2"]
    return []


def ecosystem_problems(config: dict) -> list[str]:
    """Case 2: exactly the four ecosystems, each once."""
    names = [_name(block) for block in _blocks(config)]
    problems = []
    for name in sorted(EXPECTED_ECOSYSTEMS - set(names)):
        problems.append(f"missing ecosystem {name}")
    for name in sorted(set(names) - EXPECTED_ECOSYSTEMS):
        problems.append(f"unexpected ecosystem {name}")
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f"ecosystem {name} appears more than once")
    return problems


def directories_shape_problems(config: dict) -> list[str]:
    """Case 3: ``directories`` is a non-empty list of ``/`` paths; no ``directory``."""
    problems = []
    for block in _blocks(config):
        name = _name(block)
        if "directory" in block:
            problems.append(f"{name}: uses 'directory' instead of 'directories'")
        directories = block.get("directories")
        if not isinstance(directories, list) or not directories:
            problems.append(f"{name}: 'directories' must be a non-empty list")
            continue
        for directory in directories:
            if not isinstance(directory, str) or not directory.startswith("/"):
                problems.append(f"{name}: directory {directory!r} must start with '/'")
    return problems


def expected_directories_problems(config: dict) -> list[str]:
    """Case 4: github-actions and uv at ``/``; docker has /infra/jobs; compose has /infra."""
    by_name = {_name(block): block.get("directories") or [] for block in _blocks(config)}
    problems = []
    for name, expected in REQUIRED_DIRECTORIES.items():
        if name in by_name and by_name[name] != expected:
            problems.append(f"{name}: directories {by_name[name]!r}, expected {expected!r}")
    for name, required in REQUIRED_CONTAINED.items():
        if name in by_name and required not in by_name[name]:
            problems.append(f"{name}: directories {by_name[name]!r} lack {required!r}")
    return problems


def existing_directories_problems(config: dict, root: Path) -> list[str]:
    """Case 5: every listed directory exists."""
    problems = []
    for block in _blocks(config):
        for directory in block.get("directories") or []:
            if isinstance(directory, str) and not _resolve(root, directory).is_dir():
                problems.append(f"{_name(block)}: directory {directory} does not exist")
    return problems


def _has_manifest(ecosystem: str, folder: Path) -> list[str]:
    """Return what is missing in ``folder`` for ``ecosystem`` (empty list when complete)."""
    if ecosystem == "github-actions":
        workflows = folder / ".github" / "workflows"
        found = list(workflows.glob("*.yml")) + list(workflows.glob("*.yaml"))
        return [] if found else [".github/workflows/*.yml"]
    if ecosystem == "uv":
        return [name for name in ("pyproject.toml", "uv.lock") if not (folder / name).is_file()]
    if ecosystem == "docker":
        return [] if (folder / "Dockerfile").is_file() else ["Dockerfile"]
    if ecosystem == "docker-compose":
        found = [path for pattern in COMPOSE_GLOBS for path in folder.glob(pattern)]
        return [] if found else ["docker-compose*.yml"]
    return []


def manifest_problems(config: dict, root: Path) -> list[str]:
    """Case 6: every directory holds the manifest of its ecosystem."""
    problems = []
    for block in _blocks(config):
        for directory in block.get("directories") or []:
            if not isinstance(directory, str):
                continue
            folder = _resolve(root, directory)
            if not folder.is_dir():
                continue
            for missing in _has_manifest(_name(block), folder):
                problems.append(f"{_name(block)}: {directory} lacks {missing}")
    return problems


def reverse_coverage_problems(config: dict, root: Path) -> list[str]:
    """Case 7: every Dockerfile / compose file under ``infra/`` sits in a listed directory."""
    listed = {
        _name(block): {d.rstrip("/") or "/" for d in block.get("directories") or []}
        for block in _blocks(config)
    }
    infra = root / "infra"
    problems = []
    if not infra.is_dir():
        return problems
    for dockerfile in sorted(infra.rglob("Dockerfile")):
        directory = "/" + dockerfile.parent.relative_to(root).as_posix()
        if directory not in listed.get("docker", set()):
            problems.append(f"{directory}/Dockerfile is not covered by the docker ecosystem")
    compose_dirs = {
        path.parent for pattern in COMPOSE_GLOBS for path in infra.rglob(pattern) if path.is_file()
    }
    for folder in sorted(compose_dirs):
        directory = "/" + folder.relative_to(root).as_posix()
        if directory not in listed.get("docker-compose", set()):
            problems.append(f"{directory} has compose files not covered by docker-compose")
    return problems


def schedule_problems(config: dict) -> list[str]:
    """Case 8: ``schedule.interval`` is weekly in every block."""
    problems = []
    for block in _blocks(config):
        schedule = block.get("schedule")
        interval = schedule.get("interval") if isinstance(schedule, dict) else None
        if interval != "weekly":
            problems.append(f"{_name(block)}: schedule.interval is {interval!r}, expected weekly")
    return problems


def cooldown_problems(config: dict) -> list[str]:
    """Case 9: ``cooldown`` is a map with integer ``default-days`` >= 1."""
    problems = []
    for block in _blocks(config):
        cooldown = block.get("cooldown")
        if not isinstance(cooldown, dict):
            problems.append(f"{_name(block)}: missing cooldown")
            continue
        days = cooldown.get("default-days")
        if type(days) is not int or days < 1:
            problems.append(f"{_name(block)}: cooldown.default-days is {days!r}, expected >= 1")
    return problems


def groups_problems(config: dict) -> list[str]:
    """Case 10: exactly one group per block, whose patterns contain ``*``."""
    problems = []
    for block in _blocks(config):
        groups = block.get("groups")
        if not isinstance(groups, dict) or len(groups) != 1:
            count = len(groups) if isinstance(groups, dict) else 0
            problems.append(f"{_name(block)}: expected exactly one group, found {count}")
            continue
        (group,) = groups.values()
        patterns = group.get("patterns") if isinstance(group, dict) else None
        if not isinstance(patterns, list) or "*" not in patterns:
            problems.append(f"{_name(block)}: group patterns {patterns!r} lack '*'")
    return problems


def postgres_ignore_problems(config: dict) -> list[str]:
    """Case 11: docker-compose ignores Postgres major updates."""
    for block in _blocks(config):
        if _name(block) != "docker-compose":
            continue
        for entry in block.get("ignore") or []:
            if not isinstance(entry, dict) or entry.get("dependency-name") != "postgres":
                continue
            if "version-update:semver-major" in (entry.get("update-types") or []):
                return []
        return ["docker-compose: no ignore of postgres version-update:semver-major"]
    return ["docker-compose: block not found"]


def commit_message_problems(config: dict) -> list[str]:
    """Case 12: ``commit-message.prefix`` is ``chore`` in every block."""
    problems = []
    for block in _blocks(config):
        message = block.get("commit-message")
        prefix = message.get("prefix") if isinstance(message, dict) else None
        if prefix != "chore":
            problems.append(f"{_name(block)}: commit-message.prefix is {prefix!r}, expected chore")
    return problems


# --------------------------------------------------------------------------- examples


def _block(ecosystem: str, directories: list[str], **extra: object) -> dict:
    block: dict = {
        "package-ecosystem": ecosystem,
        "directories": directories,
        "schedule": {"interval": "weekly", "day": "monday", "time": "06:00"},
        "cooldown": {"default-days": 7, "semver-major-days": 30},
        "groups": {ecosystem: {"patterns": ["*"]}},
        "commit-message": {"prefix": "chore", "include": "scope"},
    }
    if ecosystem == "docker-compose":
        block["ignore"] = [
            {"dependency-name": "postgres", "update-types": ["version-update:semver-major"]}
        ]
    block.update(extra)
    return block


def good_config() -> dict:
    return {
        "version": 2,
        "updates": [
            _block("github-actions", ["/"]),
            _block("docker", ["/infra/jobs"]),
            _block("docker-compose", ["/infra"]),
            _block("uv", ["/"]),
        ],
    }


def _mutated(mutate) -> dict:
    config = copy.deepcopy(good_config())
    mutate(config)
    return config


def _find(config: dict, ecosystem: str) -> dict:
    return next(block for block in config["updates"] if block["package-ecosystem"] == ecosystem)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (tmp_path / "uv.lock").write_text("version = 1\n")
    (tmp_path / "infra" / "jobs").mkdir(parents=True)
    (tmp_path / "infra" / "jobs" / "Dockerfile").write_text("FROM scratch\n")
    (tmp_path / "infra" / "docker-compose.yml").write_text("services: {}\n")
    return tmp_path


def all_problems(config: dict, root: Path) -> list[str]:
    return [
        *version_problems(config),
        *ecosystem_problems(config),
        *directories_shape_problems(config),
        *expected_directories_problems(config),
        *existing_directories_problems(config, root),
        *manifest_problems(config, root),
        *reverse_coverage_problems(config, root),
        *schedule_problems(config),
        *cooldown_problems(config),
        *groups_problems(config),
        *postgres_ignore_problems(config),
        *commit_message_problems(config),
    ]


# ----------------------------------------------------------- policy on the real file


@pytest.fixture(scope="module")
def real_config() -> dict:
    assert DEPENDABOT_FILE.is_file(), f"{DEPENDABOT_FILE} does not exist"
    config = yaml.safe_load(DEPENDABOT_FILE.read_text(encoding="utf-8"))
    assert isinstance(config, dict), "dependabot.yml must be a mapping"
    return config


def test_dependabot_file_exists_and_is_a_mapping(real_config):
    assert isinstance(real_config, dict)


def test_real_version_is_2(real_config):
    assert version_problems(real_config) == []


def test_real_ecosystems_are_exactly_the_four(real_config):
    assert ecosystem_problems(real_config) == []


def test_real_blocks_use_directories_not_directory(real_config):
    assert directories_shape_problems(real_config) == []


def test_real_expected_directories(real_config):
    assert expected_directories_problems(real_config) == []


def test_real_directories_exist(real_config):
    assert existing_directories_problems(real_config, REPO_ROOT) == []


def test_real_directories_hold_the_ecosystem_manifest(real_config):
    assert manifest_problems(real_config, REPO_ROOT) == []


def test_real_infra_dockerfiles_and_compose_files_are_covered(real_config):
    assert reverse_coverage_problems(real_config, REPO_ROOT) == []


def test_real_schedule_is_weekly(real_config):
    assert schedule_problems(real_config) == []


def test_real_cooldown_is_set(real_config):
    assert cooldown_problems(real_config) == []


def test_real_one_catch_all_group_per_block(real_config):
    assert groups_problems(real_config) == []


def test_real_compose_block_ignores_postgres_major(real_config):
    assert postgres_ignore_problems(real_config) == []


def test_real_commit_prefix_is_chore(real_config):
    assert commit_message_problems(real_config) == []


# --------------------------------------------------------------------------- examples (13, 14)


def test_minimal_good_config_is_accepted(tree):
    assert all_problems(good_config(), tree) == []


def _drop_uv(config):
    config["updates"] = [b for b in config["updates"] if b["package-ecosystem"] != "uv"]


def _duplicate_docker(config):
    config["updates"].append(_block("docker", ["/infra/jobs"]))


def _extra_pip(config):
    config["updates"].append(_block("pip", ["/"]))


def _use_directory(config):
    block = _find(config, "github-actions")
    del block["directories"]
    block["directory"] = "/"


def _set(ecosystem, key, value):
    def mutate(config):
        _find(config, ecosystem)[key] = value

    return mutate


def _delete(ecosystem, key):
    def mutate(config):
        del _find(config, ecosystem)[key]

    return mutate


NEGATIVE_EXAMPLES = {
    "version 1": (lambda c: c.update(version=1), version_problems),
    "version as string": (lambda c: c.update(version="2"), version_problems),
    "missing uv": (_drop_uv, ecosystem_problems),
    "docker twice": (_duplicate_docker, ecosystem_problems),
    "extra pip": (_extra_pip, ecosystem_problems),
    "directory instead of directories": (_use_directory, directories_shape_problems),
    "empty directories": (_set("uv", "directories", []), directories_shape_problems),
    "directory without slash": (
        _set("docker", "directories", ["infra"]),
        directories_shape_problems,
    ),
    "interval daily": (
        _set("uv", "schedule", {"interval": "daily"}),
        schedule_problems,
    ),
    "no cooldown": (_delete("docker", "cooldown"), cooldown_problems),
    "cooldown zero": (_set("docker", "cooldown", {"default-days": 0}), cooldown_problems),
    "cooldown empty": (_set("docker", "cooldown", {}), cooldown_problems),
    "no groups": (_delete("uv", "groups"), groups_problems),
    "narrow pattern": (
        _set("github-actions", "groups", {"actions": {"patterns": ["actions/*"]}}),
        groups_problems,
    ),
    "two groups": (
        _set(
            "uv",
            "groups",
            {"a": {"patterns": ["*"]}, "b": {"patterns": ["*"]}},
        ),
        groups_problems,
    ),
    "no postgres ignore": (_delete("docker-compose", "ignore"), postgres_ignore_problems),
    "postgres ignore only minor": (
        _set(
            "docker-compose",
            "ignore",
            [{"dependency-name": "postgres", "update-types": ["version-update:semver-minor"]}],
        ),
        postgres_ignore_problems,
    ),
    "no commit-message": (_delete("uv", "commit-message"), commit_message_problems),
}


@pytest.mark.parametrize("name", sorted(NEGATIVE_EXAMPLES))
def test_negative_example_is_rejected(name):
    mutate, check = NEGATIVE_EXAMPLES[name]
    assert check(_mutated(mutate)) != []


def test_wrong_expected_directories_are_rejected():
    config = _mutated(_set("github-actions", "directories", ["/infra"]))
    assert expected_directories_problems(config) != []
    config = _mutated(_set("docker", "directories", ["/infra"]))
    assert expected_directories_problems(config) != []


def test_nonexistent_directory_is_rejected(tree):
    config = _mutated(_set("docker", "directories", ["/infra/jobs", "/infra/nope"]))
    assert existing_directories_problems(config, tree) != []


def test_docker_directory_without_dockerfile_is_rejected(tree):
    (tree / "infra" / "jobs" / "Dockerfile").unlink()
    assert manifest_problems(good_config(), tree) != []


def test_uv_directory_without_lock_is_rejected(tree):
    (tree / "uv.lock").unlink()
    assert manifest_problems(good_config(), tree) != []


def test_compose_directory_without_compose_file_is_rejected(tree):
    (tree / "infra" / "docker-compose.yml").unlink()
    assert manifest_problems(good_config(), tree) != []


def test_actions_directory_without_workflows_is_rejected(tree):
    (tree / ".github" / "workflows" / "ci.yml").unlink()
    assert manifest_problems(good_config(), tree) != []


def test_dockerfile_in_unlisted_directory_is_rejected(tree):
    (tree / "infra" / "mlflow").mkdir()
    (tree / "infra" / "mlflow" / "Dockerfile").write_text("FROM scratch\n")
    assert reverse_coverage_problems(good_config(), tree) != []


def test_compose_file_in_unlisted_directory_is_rejected(tree):
    (tree / "infra" / "extra").mkdir()
    (tree / "infra" / "extra" / "docker-compose.yml").write_text("services: {}\n")
    assert reverse_coverage_problems(good_config(), tree) != []
