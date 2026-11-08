"""Supply-chain pin policy tests (plan S1, cases 1 to 19; ADR 0006, items 4 to 7).

Static checks over the workflows, the compose files and the Dockerfiles: actions pinned by
commit SHA with a version comment, minimal ``permissions``, ``persist-credentials: false``,
no dangerous triggers, no secrets in ``ci.yml`` and third-party images pinned by digest.
The check functions are exercised with embedded negative examples, so a passing policy test
cannot be an artifact of a check that accepts everything.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
INFRA_DIR = REPO_ROOT / "infra"
CI_WORKFLOW = WORKFLOWS_DIR / "ci.yml"
MAIN_COMPOSE = INFRA_DIR / "docker-compose.yml"
DEV_COMPOSE = INFRA_DIR / "docker-compose.dev.yml"

SHA40 = "a" * 40
DIGEST = "sha256:" + "b" * 64

# Own images (built by this repo, published to GHCR in plan 37) are not third-party and are
# the only images allowed without a digest. Plan 37 extends this list.
OWN_IMAGE_PREFIXES = ("ghcr.io/${GHCR_OWNER}/platform-",)

USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<value>\S+)(?P<rest>.*)$")
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^\s+# v\d+\.\d+\.\d+\s*$")
DOCKER_DIGEST_REF = re.compile(r"^docker://\S+@sha256:[0-9a-f]{64}$")
# <name>:<tag>@sha256:<64 hex>; the name may contain a registry with a port.
PINNED_IMAGE = re.compile(r"^(?P<name>[^@\s]+):(?P<tag>[^:@/\s]+)@sha256:[0-9a-f]{64}$")
DIGEST_SUFFIX = re.compile(r"@sha256:[0-9a-f]{64}$")
FORBIDDEN_TRIGGERS = frozenset({"pull_request_target", "workflow_run"})
BROAD_PERMISSIONS = frozenset({"write-all", "read-all"})


# --------------------------------------------------------------------------- check functions


def uses_problems(workflow_text: str) -> list[str]:
    """Cases 1, 10 to 12: every ``uses:`` is a full commit SHA plus a ``# vX.Y.Z`` comment."""
    problems = []
    for number, line in enumerate(workflow_text.splitlines(), start=1):
        match = USES_LINE.match(line)
        if not match:
            continue
        value, rest = match["value"].strip("'\""), match["rest"]
        if value.startswith("./"):
            continue
        if value.startswith("docker://"):
            if not DOCKER_DIGEST_REF.match(value):
                problems.append(f"line {number}: {value} is not pinned by digest")
            continue
        if not PINNED_ACTION.match(value):
            problems.append(f"line {number}: {value} is not pinned by a 40-hex commit SHA")
        elif not VERSION_COMMENT.match(rest):
            problems.append(f"line {number}: {value} lacks a '# vX.Y.Z' comment")
    return problems


def top_permissions_problems(workflow: dict) -> list[str]:
    """Cases 2 and 13: ``permissions`` at the top, neither ``write-all`` nor ``read-all``."""
    if "permissions" not in workflow:
        return ["missing top-level permissions"]
    value = workflow["permissions"]
    if isinstance(value, str) and value in BROAD_PERMISSIONS:
        return [f"top-level permissions is {value!r}"]
    return []


def minimal_permissions_problems(workflow: dict) -> list[str]:
    """Cases 3, 13 and 14: top is exactly ``{contents: read}``; every job has no ``write``."""
    problems = []
    if workflow.get("permissions") != {"contents": "read"}:
        problems.append(f"top-level permissions is {workflow.get('permissions')!r}")
    for name, job in (workflow.get("jobs") or {}).items():
        permissions = job.get("permissions") if isinstance(job, dict) else None
        if not isinstance(permissions, dict) or not permissions:
            problems.append(f"job {name!r} does not declare permissions")
        elif "write" in permissions.values():
            problems.append(f"job {name!r} grants write permissions")
    return problems


def checkout_problems(workflow: dict) -> list[str]:
    """Cases 4 and 15: every checkout step has ``persist-credentials`` set to boolean false."""
    problems = []
    for name, job in (workflow.get("jobs") or {}).items():
        for index, step in enumerate(job.get("steps") or []):
            if not str(step.get("uses", "")).startswith("actions/checkout@"):
                continue
            options = step.get("with")
            if not isinstance(options, dict) or options.get("persist-credentials") is not False:
                problems.append(f"job {name!r} step {index}: persist-credentials is not false")
    return problems


def trigger_problems(workflow: dict) -> list[str]:
    """Cases 5 and 16: no ``pull_request_target`` and no ``workflow_run`` trigger."""
    triggers = workflow.get("on", workflow.get(True))
    if isinstance(triggers, str):
        names = {triggers}
    elif isinstance(triggers, (list, dict)):
        names = set(triggers)
    else:
        names = set()
    return [f"forbidden trigger {name!r}" for name in sorted(names & FORBIDDEN_TRIGGERS)]


def image_reference_problems(image: str) -> list[str]:
    """Cases 7 and 17: ``<name>:<tag>@sha256:<64 hex>``, tag present and not ``latest``."""
    match = PINNED_IMAGE.match(image)
    if not match:
        return [f"{image!r} is not '<name>:<tag>@sha256:<64 hex>'"]
    if match["tag"] == "latest":
        return [f"{image!r} uses the latest tag"]
    return []


def compose_image_problems(compose: dict) -> list[str]:
    problems = []
    for name, service in (compose.get("services") or {}).items():
        image = service.get("image") if isinstance(service, dict) else None
        if image is None or image.startswith(OWN_IMAGE_PREFIXES):
            continue
        problems += [f"service {name!r}: {p}" for p in image_reference_problems(image)]
    return problems


def workflow_images(workflow: dict) -> dict[str, str]:
    """Return ``{label: image}`` for every job service and job container image."""
    images = {}
    for job_name, job in (workflow.get("jobs") or {}).items():
        containers = {"container": job.get("container")}
        for service_name, service in (job.get("services") or {}).items():
            containers[f"services.{service_name}"] = service
        for label, value in containers.items():
            image = value.get("image") if isinstance(value, dict) else value
            if isinstance(image, str):
                images[f"{job_name}.{label}"] = image
    return images


def workflow_image_problems(workflow: dict) -> list[str]:
    problems = []
    for label, image in workflow_images(workflow).items():
        problems += [f"{label}: {p}" for p in image_reference_problems(image)]
    return problems


def dockerfile_from_problems(dockerfile_text: str) -> list[str]:
    """Cases 8 and 18: every ``FROM`` is digest-pinned, ``scratch`` or an earlier stage."""
    problems = []
    stages: set[str] = set()
    for line in dockerfile_text.splitlines():
        tokens = line.split()
        if not tokens or tokens[0].upper() != "FROM":
            continue
        arguments = [token for token in tokens[1:] if not token.startswith("--")]
        reference = arguments[0]
        if reference != "scratch" and reference not in stages:
            if not DIGEST_SUFFIX.search(reference):
                problems.append(f"FROM {reference} is not pinned by digest")
        if len(arguments) >= 3 and arguments[1].upper() == "AS":
            stages.add(arguments[2])
    return problems


def same_postgres_reference_problems(references: dict[str, str | None]) -> list[str]:
    """Case 9: one full ``tag@digest`` reference across prod, dev and the CI service."""
    tails = {label: (ref.split(":", 1)[-1] if ref else None) for label, ref in references.items()}
    if None in tails.values() or len(set(tails.values())) != 1:
        return [f"postgres references differ: {references}"]
    return []


# --------------------------------------------------------------------------- loaders


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOWS_DIR.glob("*.yml"), *WORKFLOWS_DIR.glob("*.yaml")])


def compose_files() -> list[Path]:
    return sorted(INFRA_DIR.glob("docker-compose*.yml"))


def dockerfiles() -> list[Path]:
    return sorted(INFRA_DIR.glob("**/Dockerfile"))


def ids(paths: list[Path]) -> list[str]:
    return [path.relative_to(REPO_ROOT).as_posix() for path in paths]


# --------------------------------------------------------------------------- policy on real files


def test_there_are_workflows_to_check():
    assert workflow_files() != []


@pytest.mark.parametrize("path", workflow_files(), ids=ids(workflow_files()))
def test_every_action_is_pinned_by_sha_with_a_version_comment(path):
    assert uses_problems(path.read_text(encoding="utf-8")) == []


def test_ci_workflow_has_uses_lines_to_check():
    lines = CI_WORKFLOW.read_text(encoding="utf-8").splitlines()
    assert len([line for line in lines if USES_LINE.match(line)]) == 3


@pytest.mark.parametrize("path", workflow_files(), ids=ids(workflow_files()))
def test_every_workflow_declares_top_level_permissions(path):
    assert top_permissions_problems(load_yaml(path)) == []


def test_ci_permissions_are_read_only_at_the_top_and_in_every_job():
    assert minimal_permissions_problems(load_yaml(CI_WORKFLOW)) == []


@pytest.mark.parametrize("path", workflow_files(), ids=ids(workflow_files()))
def test_checkout_does_not_persist_credentials(path):
    assert checkout_problems(load_yaml(path)) == []


def test_ci_has_checkout_steps_to_check():
    steps = [
        step
        for job in load_yaml(CI_WORKFLOW)["jobs"].values()
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert len(steps) == 2


@pytest.mark.parametrize("path", workflow_files(), ids=ids(workflow_files()))
def test_no_workflow_uses_dangerous_triggers(path):
    assert trigger_problems(load_yaml(path)) == []


def test_ci_workflow_does_not_reference_secrets():
    assert "secrets." not in CI_WORKFLOW.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", compose_files(), ids=ids(compose_files()))
def test_compose_images_are_pinned_by_digest(path):
    assert compose_image_problems(load_yaml(path)) == []


@pytest.mark.parametrize("path", workflow_files(), ids=ids(workflow_files()))
def test_workflow_service_and_container_images_are_pinned_by_digest(path):
    assert workflow_image_problems(load_yaml(path)) == []


def test_ci_has_a_postgres_service_image():
    assert "lint-and-test.services.postgres" in workflow_images(load_yaml(CI_WORKFLOW))


@pytest.mark.parametrize("path", dockerfiles(), ids=ids(dockerfiles()))
def test_dockerfile_base_images_are_pinned_by_digest(path):
    assert dockerfile_from_problems(path.read_text(encoding="utf-8")) == []


def test_postgres_reference_is_identical_in_prod_dev_and_ci():
    references = {
        "prod": load_yaml(MAIN_COMPOSE)["services"]["postgres"].get("image"),
        "dev": load_yaml(DEV_COMPOSE)["services"]["postgres"].get("image"),
        "ci": workflow_images(load_yaml(CI_WORKFLOW)).get("lint-and-test.services.postgres"),
    }
    assert same_postgres_reference_problems(references) == []
    assert all(DIGEST_SUFFIX.search(ref) for ref in references.values() if ref)


# --------------------------------------------------------------------------- negative examples


@pytest.mark.parametrize(
    "line",
    [
        f"      - uses: actions/checkout@{SHA40} # v7.0.1",
        f"        uses: org/repo/.github/workflows/x.yml@{SHA40} # v1.2.3",
        "      - uses: ./.github/actions/local",
        f"      - uses: docker://alpine:3.20@{DIGEST}",
    ],
)
def test_uses_check_accepts_pinned_references(line):
    assert uses_problems(line) == []


@pytest.mark.parametrize(
    "line",
    [
        "      - uses: actions/checkout@v7",
        "      - uses: astral-sh/setup-uv@v10.3.3",
        "      - uses: actions/checkout@main",
        f"      - uses: actions/checkout@{'a' * 39} # v7.0.1",
        f"      - uses: actions/checkout@{'a' * 41} # v7.0.1",
        f"      - uses: actions/checkout@{'A' * 40} # v7.0.1",
        f"      - uses: actions/checkout@{SHA40}",
        f"      - uses: actions/checkout@{SHA40} # v7",
        f"      - uses: actions/checkout@{SHA40} # latest",
        "      - uses: docker://alpine:3.20",
    ],
)
def test_uses_check_rejects_unpinned_or_uncommented_references(line):
    assert uses_problems(line) != []


@pytest.mark.parametrize("permissions", [{"contents": "read"}, {}])
def test_top_permissions_check_accepts_explicit_permissions(permissions):
    assert top_permissions_problems({"permissions": permissions}) == []


@pytest.mark.parametrize(
    "workflow", [{}, {"permissions": "write-all"}, {"permissions": "read-all"}]
)
def test_top_permissions_check_rejects_missing_or_broad_permissions(workflow):
    assert top_permissions_problems(workflow) != []


def test_minimal_permissions_check_accepts_read_only_top_and_jobs():
    workflow = {
        "permissions": {"contents": "read"},
        "jobs": {"build": {"permissions": {"contents": "read"}}},
    }
    assert minimal_permissions_problems(workflow) == []


@pytest.mark.parametrize(
    "workflow",
    [
        {"permissions": {"contents": "read"}, "jobs": {"build": {}}},
        {
            "permissions": {"contents": "read"},
            "jobs": {"build": {"permissions": {"contents": "write"}}},
        },
        {"permissions": {}, "jobs": {"build": {"permissions": {"contents": "read"}}}},
        {"jobs": {"build": {"permissions": {"contents": "read"}}}},
    ],
)
def test_minimal_permissions_check_rejects_missing_or_write_permissions(workflow):
    assert minimal_permissions_problems(workflow) != []


def _checkout_workflow(step: dict) -> dict:
    return {"jobs": {"build": {"steps": [step]}}}


def test_checkout_check_accepts_persist_credentials_false():
    step = {"uses": f"actions/checkout@{SHA40}", "with": {"persist-credentials": False}}
    assert checkout_problems(_checkout_workflow(step)) == []


def test_checkout_check_ignores_other_steps():
    assert checkout_problems(_checkout_workflow({"run": "echo hi"})) == []


@pytest.mark.parametrize(
    "step",
    [
        {"uses": f"actions/checkout@{SHA40}"},
        {"uses": f"actions/checkout@{SHA40}", "with": {"persist-credentials": True}},
        {"uses": f"actions/checkout@{SHA40}", "with": {"persist-credentials": "false"}},
    ],
)
def test_checkout_check_rejects_missing_or_truthy_persist_credentials(step):
    assert checkout_problems(_checkout_workflow(step)) != []


@pytest.mark.parametrize(
    "triggers",
    [{"pull_request": None, "push": {"branches": ["main"]}}, ["push", "pull_request"], "push"],
)
def test_trigger_check_accepts_safe_triggers(triggers):
    assert trigger_problems({True: triggers}) == []
    assert trigger_problems({"on": triggers}) == []


@pytest.mark.parametrize(
    "triggers",
    [
        {"pull_request": None, "pull_request_target": None},
        {"push": None, "workflow_run": {"workflows": ["ci"]}},
        ["push", "pull_request_target"],
        "workflow_run",
    ],
)
def test_trigger_check_rejects_dangerous_triggers(triggers):
    assert trigger_problems({True: triggers}) != []


@pytest.mark.parametrize(
    "image",
    [
        f"postgres:16.15@{DIGEST}",
        f"ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim@{DIGEST}",
        f"localhost:5000/x:1.0@{DIGEST}",
    ],
)
def test_image_check_accepts_tag_with_digest(image):
    assert image_reference_problems(image) == []


@pytest.mark.parametrize(
    "image",
    [
        "postgres:16.15",
        f"postgres@{DIGEST}",
        f"postgres:latest@{DIGEST}",
        "postgres:16.15@sha256:" + "b" * 63,
        "postgres:16.15@sha512:" + "b" * 64,
        "postgres:16.15@sha256:" + "B" * 64,
    ],
)
def test_image_check_rejects_unpinned_or_malformed_references(image):
    assert image_reference_problems(image) != []


def test_compose_check_skips_build_only_services_and_flags_unpinned_images():
    pinned = {"services": {"a": {"build": "."}, "b": {"image": f"busybox:1.38.0@{DIGEST}"}}}
    unpinned = {"services": {"b": {"image": "busybox:1.38.0"}}}
    assert compose_image_problems(pinned) == []
    assert compose_image_problems(unpinned) != []


def test_compose_check_allows_own_images_without_digest():
    compose = {"services": {"jobs": {"image": "ghcr.io/${GHCR_OWNER}/platform-jobs:${IMAGE_TAG}"}}}
    assert compose_image_problems(compose) == []


def test_workflow_image_check_covers_services_and_containers():
    workflow = {
        "jobs": {
            "a": {"services": {"db": {"image": "postgres:16"}}},
            "b": {"container": "python:3.12"},
            "c": {"container": {"image": "python:3.12"}},
        }
    }
    assert len(workflow_image_problems(workflow)) == 3
    pinned = {"jobs": {"a": {"services": {"db": {"image": f"postgres:16.15@{DIGEST}"}}}}}
    assert workflow_image_problems(pinned) == []


@pytest.mark.parametrize(
    "text",
    [
        f"FROM python:3.12@{DIGEST}\n",
        f"FROM --platform=linux/amd64 python:3.12@{DIGEST}\n",
        f"FROM x:1@{DIGEST} AS build\nFROM build\n",
        "FROM scratch\n",
    ],
)
def test_dockerfile_check_accepts_pinned_scratch_and_stage_references(text):
    assert dockerfile_from_problems(text) == []


@pytest.mark.parametrize("text", ["FROM python:3.12\n", "FROM build\n"])
def test_dockerfile_check_rejects_unpinned_or_unknown_stage_references(text):
    assert dockerfile_from_problems(text) != []


def test_same_reference_check_accepts_identical_and_rejects_diverging():
    same = {"prod": f"postgres:16.15@{DIGEST}", "dev": f"postgres:16.15@{DIGEST}"}
    other = {"prod": f"postgres:16.15@{DIGEST}", "dev": "postgres:16.15@sha256:" + "c" * 64}
    assert same_postgres_reference_problems(same) == []
    assert same_postgres_reference_problems(other) != []
    assert same_postgres_reference_problems({"prod": "postgres:16.15", "dev": None}) != []
