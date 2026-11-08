"""Security workflow tests (plan S3, cases 1 to 33; ADR 0006, items 3 and 6 to 10).

Static checks over ``.github/workflows/security.yml`` and the exception policy: top-level
``permissions: {}``, least privilege per job, stable job names, no ``paths:`` filter, no
secrets, SARIF upload skipped on forks, Trivy run from an image pinned by digest, and every
downgrade of a check recorded as a versioned exception. Each check function is also run on
embedded accepted and rejected examples, so a passing policy test cannot be an artifact of a
check that accepts everything.
"""

from __future__ import annotations

import re
import tomllib
from datetime import date

import pytest

from tests.infra.test_supply_chain_pins import (
    DIGEST,
    REPO_ROOT,
    SHA40,
    USES_LINE,
    WORKFLOWS_DIR,
    image_reference_problems,
    load_yaml,
    workflow_files,
)

SECURITY_WORKFLOW = WORKFLOWS_DIR / "security.yml"
CI_WORKFLOW = WORKFLOWS_DIR / "ci.yml"
TRIVYIGNORE = REPO_ROOT / ".trivyignore"

EXPECTED_JOBS = {"zizmor", "dependency-review", "trivy-config", "trivy-fs"}
TRIVY_JOBS = {"trivy-config", "trivy-fs"}
EXPECTED_CATEGORIES = {"zizmor", "trivy-config", "trivy-fs"}
UPLOAD_ACTION = "github/codeql-action/upload-sarif@"
FORK_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"
GOOD_UPLOAD_IF = (
    "${{ !cancelled() && (github.event_name != 'pull_request' || " + FORK_GUARD + ") }}"
)
GITHUB_CREDENTIAL_EXPRESSION = "${{ github.token }}"
TRIVY_IMAGE_REF = "$TRIVY_IMAGE"

EXCEPTION_LINE = re.compile(
    r"^\s*#\s*exception:\s*(?P<reason>\S[^;]*?)\s*;\s*(?P<url>https?://[^\s;]+)\s*;"
    r"\s*review\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$"
)
EXP_FIELD = re.compile(r"\bexp:(?P<date>\d{4}-\d{2}-\d{2})\b")
GHSA_ID = re.compile(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}")
CONTINUE_ON_ERROR = re.compile(r"^\s*continue-on-error\s*:")
SHA_AND_VERSION = re.compile(r"^(?P<action>[^@\s]+)@(?P<sha>[0-9a-f]{40})\s*#\s*(?P<version>v\S+)")
BANNED_TRIVY_ACTIONS = ("aquasecurity/trivy-action", "aquasecurity/setup-trivy")

GOOD_EXCEPTION = (
    "# exception: false positive on test fixture; "
    "https://github.com/o/r/security/code-scanning/1; review 2027-01-31"
)

TRIVY_CONFIG_RUN = (
    'docker run --rm -v "$GITHUB_WORKSPACE:/src:ro" -w /src "$TRIVY_IMAGE" config '
    "--misconfig-scanners dockerfile --severity HIGH,CRITICAL --exit-code 1 ."
)
TRIVY_FS_RUN = (
    'docker run --rm -v "$GITHUB_WORKSPACE:/src:ro" -w /src "$TRIVY_IMAGE" fs '
    "--scanners vuln,secret --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 ."
)


# --------------------------------------------------------------------------- loaders


def load_security() -> dict:
    """The parsed ``security.yml``, or ``{}`` while the file does not exist yet."""
    if not SECURITY_WORKFLOW.exists():
        return {}
    return load_yaml(SECURITY_WORKFLOW) or {}


def security_text() -> str:
    if not SECURITY_WORKFLOW.exists():
        return ""
    return SECURITY_WORKFLOW.read_text(encoding="utf-8")


def jobs_of(workflow: dict) -> dict[str, dict]:
    jobs = workflow.get("jobs") or {}
    return {name: job for name, job in jobs.items() if isinstance(job, dict)}


def steps_of(workflow: dict):
    """Yield ``(job_name, step)`` for every step of every job."""
    for name, job in jobs_of(workflow).items():
        for step in job.get("steps") or []:
            if isinstance(step, dict):
                yield name, step


def is_upload(step: dict) -> bool:
    return str(step.get("uses", "")).startswith(UPLOAD_ACTION)


def normalized(run: str) -> str:
    """Join shell line continuations and squeeze whitespace."""
    return " ".join(run.replace("\\\n", " ").split())


def trivy_runs(job: dict) -> list[str]:
    return [
        normalized(step["run"])
        for step in job.get("steps") or []
        if isinstance(step, dict) and TRIVY_IMAGE_REF in str(step.get("run", ""))
    ]


# --------------------------------------------------------------------------- check functions


def name_problems(workflow: dict) -> list[str]:
    """Case 2."""
    return [] if workflow.get("name") == "security" else [f"name is {workflow.get('name')!r}"]


def trigger_problems(workflow: dict) -> list[str]:
    """Cases 3 and 27: only pull_request and push (main), with no path or branch filters."""
    triggers = workflow.get("on", workflow.get(True))
    if not isinstance(triggers, dict):
        return [f"triggers are {triggers!r}"]
    problems = []
    if set(triggers) != {"pull_request", "push"}:
        problems.append(f"triggers are {sorted(map(str, triggers))}")
    for name, value in triggers.items():
        if not isinstance(value, dict):
            continue
        for key in ("paths", "paths-ignore"):
            if key in value:
                problems.append(f"trigger {name!r} has {key}")
    pull_request = triggers.get("pull_request")
    if isinstance(pull_request, dict) and ({"branches", "branches-ignore"} & set(pull_request)):
        problems.append("pull_request has a branch filter")
    push = triggers.get("push")
    if not isinstance(push, dict) or push.get("branches") != ["main"]:
        problems.append("push is not limited to branches [main]")
    return problems


def top_permissions_problems(workflow: dict) -> list[str]:
    """Cases 4 and 28: the top-level ``permissions`` is exactly the empty mapping."""
    if workflow.get("permissions") != {}:
        return [f"top-level permissions is {workflow.get('permissions', 'missing')!r}"]
    return []


def job_id_problems(workflow: dict) -> list[str]:
    """Case 5: exact job ids, and no ``name:`` that differs from the id."""
    jobs = jobs_of(workflow)
    problems = []
    if set(jobs) != EXPECTED_JOBS:
        problems.append(f"job ids are {sorted(jobs)}")
    for name, job in jobs.items():
        if "name" in job and job["name"] != name:
            problems.append(f"job {name!r} is named {job['name']!r}")
    return problems


def job_permission_shape_problems(workflow: dict) -> list[str]:
    """Cases 6 and 29: ``contents: read`` plus optional ``security-events: write``."""
    jobs = jobs_of(workflow)
    if not jobs:
        return ["no jobs"]
    problems = []
    for name, job in jobs.items():
        permissions = job.get("permissions")
        if not isinstance(permissions, dict) or not permissions:
            problems.append(f"job {name!r} does not declare permissions")
            continue
        if permissions.get("contents") != "read":
            problems.append(f"job {name!r}: contents is not read")
        extra = set(permissions) - {"contents", "security-events"}
        if extra:
            problems.append(f"job {name!r}: unexpected permissions {sorted(extra)}")
        if "security-events" in permissions and permissions["security-events"] != "write":
            problems.append(f"job {name!r}: security-events is not write")
    return problems


def job_upload_permission_problems(workflow: dict) -> list[str]:
    """Cases 7 and 29: ``security-events: write`` if and only if the job uploads SARIF."""
    jobs = jobs_of(workflow)
    if not jobs:
        return ["no jobs"]
    problems = []
    for name, job in jobs.items():
        permissions = job.get("permissions")
        writes = isinstance(permissions, dict) and permissions.get("security-events") == "write"
        uploads = any(is_upload(step) for step in job.get("steps") or [] if isinstance(step, dict))
        if writes != uploads:
            problems.append(f"job {name!r}: security-events write={writes}, upload={uploads}")
    return problems


def job_permission_problems(workflow: dict) -> list[str]:
    return job_permission_shape_problems(workflow) + job_upload_permission_problems(workflow)


def sarif_upload_problems(workflow: dict) -> list[str]:
    """Cases 8 and 30: guarded single-line ``if``, ``sarif_file`` and a distinct ``category``."""
    uploads = [(job, step) for job, step in steps_of(workflow) if is_upload(step)]
    if not uploads:
        return ["no SARIF upload steps"]
    problems = []
    categories: list[str] = []
    for job, step in uploads:
        condition = step.get("if")
        if not isinstance(condition, str) or "\n" in condition.strip():
            problems.append(f"job {job!r}: upload has no single-line if")
        else:
            if "!cancelled()" not in condition:
                problems.append(f"job {job!r}: upload if lacks !cancelled()")
            if FORK_GUARD not in condition:
                problems.append(f"job {job!r}: upload if lacks the fork guard")
        options = step.get("with") if isinstance(step.get("with"), dict) else {}
        if not options.get("sarif_file"):
            problems.append(f"job {job!r}: upload has no sarif_file")
        if not options.get("category"):
            problems.append(f"job {job!r}: upload has no category")
        else:
            categories.append(options["category"])
    if len(categories) != len(set(categories)):
        problems.append(f"duplicate categories {categories}")
    return problems


def secrets_problems(text: str) -> list[str]:
    """Cases 9 and 31: the workflow text never mentions ``secrets.``."""
    if not text.strip():
        return ["empty workflow text"]
    return ["references secrets."] if "secrets." in text else []


def run_expression_problems(workflow: dict) -> list[str]:
    """Cases 10 and 31: no ``${{`` inside a ``run:`` value."""
    if not jobs_of(workflow):
        return ["no jobs"]
    return [
        f"job {job!r}: run contains an expression"
        for job, step in steps_of(workflow)
        if "${{" in str(step.get("run", ""))
    ]


def multiline_if_problems(workflow: dict) -> list[str]:
    """Cases 11 and 31: no ``if:`` of a job or a step is a multi-line string."""
    if not jobs_of(workflow):
        return ["no jobs"]
    problems = []
    for name, job in jobs_of(workflow).items():
        conditions = [("job", job.get("if"))]
        conditions += [("step", step.get("if")) for _, step in steps_of({"jobs": {name: job}})]
        for kind, condition in conditions:
            if isinstance(condition, str) and "\n" in condition.strip():
                problems.append(f"job {name!r}: multi-line {kind} if")
    return problems


def dependency_review_problems(workflow: dict) -> list[str]:
    """Case 12."""
    job = jobs_of(workflow).get("dependency-review")
    if job is None:
        return ["no dependency-review job"]
    problems = []
    if "github.event_name == 'pull_request'" not in str(job.get("if", "")):
        problems.append("dependency-review is not limited to pull_request events")
    reviews = [
        step
        for step in job.get("steps") or []
        if str(step.get("uses", "")).startswith("actions/dependency-review-action@")
    ]
    if not reviews:
        problems.append("dependency-review does not use actions/dependency-review-action")
    for step in reviews:
        options = step.get("with") if isinstance(step.get("with"), dict) else {}
        if options.get("fail-on-severity") != "high":
            problems.append("fail-on-severity is not high")
    return problems


def trivy_image_problems(workflow: dict) -> list[str]:
    """Cases 13 and 32: ``env.TRIVY_IMAGE`` at the top, pinned by tag and digest."""
    env = workflow.get("env")
    image = env.get("TRIVY_IMAGE") if isinstance(env, dict) else None
    if not isinstance(image, str):
        return ["env.TRIVY_IMAGE is missing"]
    return image_reference_problems(image)


def calls_trivy(run: str) -> bool:
    return bool(re.search(r"TRIVY_IMAGE|aquasec|(?<![\w-])trivy(?![\w-])", run))


def trivy_run_problems(workflow: dict) -> list[str]:
    """Cases 14 and 32: ``docker run`` uses only ``"$TRIVY_IMAGE"``; Trivy stays in its jobs."""
    if not jobs_of(workflow):
        return ["no jobs"]
    problems = []
    for job, step in steps_of(workflow):
        run = normalized(str(step.get("run", "")))
        if not run:
            continue
        if "docker run" in run:
            if f'"{TRIVY_IMAGE_REF}"' not in run:
                problems.append(f'job {job!r}: docker run does not use "$TRIVY_IMAGE"')
            else:
                rest = run.replace(f'"{TRIVY_IMAGE_REF}"', "")
                if re.search(r"aquasec|ghcr\.io|[\w./-]+:[\w.-]+@sha256", rest):
                    problems.append(f"job {job!r}: docker run names a literal image")
        if calls_trivy(run) and job not in TRIVY_JOBS:
            problems.append(f"job {job!r}: calls Trivy outside the Trivy jobs")
    return problems


def banned_trivy_action_problems(workflow_text: str) -> list[str]:
    """Cases 15 and 32: no ``trivy-action`` and no ``setup-trivy`` (ADR 0006, incident)."""
    problems = []
    for number, line in enumerate(workflow_text.splitlines(), start=1):
        match = USES_LINE.match(line)
        if match and match["value"].strip("'\"").startswith(BANNED_TRIVY_ACTIONS):
            problems.append(f"line {number}: {match['value']}")
    return problems


def trivy_flag_problems(
    workflow: dict, job_name: str, subcommand: str, flags: tuple[str, ...]
) -> list[str]:
    """Cases 16, 17 and 32: subcommand and flags of every Trivy run of one job."""
    job = jobs_of(workflow).get(job_name)
    if job is None:
        return [f"no {job_name} job"]
    runs = trivy_runs(job)
    if not runs:
        return [f"{job_name} has no Trivy run"]
    problems = []
    for run in runs:
        tokens = run.split()
        index = tokens.index(f'"{TRIVY_IMAGE_REF}"') if f'"{TRIVY_IMAGE_REF}"' in tokens else -1
        if index < 0 or index + 1 >= len(tokens) or tokens[index + 1] != subcommand:
            problems.append(f"{job_name}: subcommand is not {subcommand}")
        for flag in flags:
            if not re.search(rf"(?<!\S){re.escape(flag)}(?!\S)", run):
                problems.append(f"{job_name}: missing {flag}")
    if not any(re.search(r"--exit-code 1(?!\S)", run) for run in runs):
        problems.append(f"{job_name}: no run with --exit-code 1")
    return problems


def trivy_config_problems(workflow: dict) -> list[str]:
    return trivy_flag_problems(
        workflow,
        "trivy-config",
        "config",
        ("--misconfig-scanners dockerfile", "--severity HIGH,CRITICAL"),
    )


def trivy_fs_problems(workflow: dict) -> list[str]:
    return trivy_flag_problems(
        workflow,
        "trivy-fs",
        "fs",
        ("--scanners vuln,secret", "--severity HIGH,CRITICAL", "--ignore-unfixed"),
    )


def trivy_mount_problems(workflow: dict) -> list[str]:
    """Cases 18 and 32: the checkout is mounted read-only in both Trivy jobs."""
    problems = []
    for job_name in sorted(TRIVY_JOBS):
        job = jobs_of(workflow).get(job_name)
        runs = trivy_runs(job) if job else []
        if not runs:
            problems.append(f"{job_name} has no Trivy run")
        for run in runs:
            if ":/src:ro" not in run or re.search(r":/src(?!:ro)", run):
                problems.append(f"{job_name}: checkout is not mounted read-only")
    return problems


def zizmor_job_problems(workflow: dict) -> list[str]:
    """Cases 19 and 31."""
    job = jobs_of(workflow).get("zizmor")
    if job is None:
        return ["no zizmor job"]
    steps = [step for step in job.get("steps") or [] if isinstance(step, dict)]
    runs = [normalized(str(step["run"])) for step in steps if "run" in step]
    problems = []
    if not any(re.search(r"\buv sync\b.*--locked\b", run) for run in runs):
        problems.append("zizmor job does not run 'uv sync --locked'")
    if not any(re.search(r"\buv run\b.*\bzizmor\b", run) for run in runs):
        problems.append("zizmor job does not call zizmor through 'uv run'")
    environments = [job.get("env"), *(step.get("env") for step in steps)]
    for env in environments:
        if isinstance(env, dict) and "GH_TOKEN" in env:
            if env["GH_TOKEN"] != GITHUB_CREDENTIAL_EXPRESSION:
                problems.append(f"GH_TOKEN is {env['GH_TOKEN']!r}")
    return problems


def action_consistency_problems(texts: dict[str, str]) -> list[str]:
    """Cases 21 and 33: the same action has one SHA and one version comment across workflows."""
    seen: dict[str, dict[str, set[tuple[str, str]]]] = {}
    for label, text in texts.items():
        for line in text.splitlines():
            match = USES_LINE.match(line)
            if not match:
                continue
            found = SHA_AND_VERSION.match(
                f"{match['value'].strip(chr(34) + chr(39))}{match['rest']}"
            )
            if found:
                pins = seen.setdefault(found["action"], {}).setdefault(label, set())
                pins.add((found["sha"], found["version"]))
    problems = []
    for action, by_workflow in seen.items():
        if len(by_workflow) < 2:
            continue
        if len(set().union(*by_workflow.values())) != 1:
            problems.append(f"{action} is pinned differently across workflows: {by_workflow}")
    return problems


def setup_uv_cache_problems(workflow: dict) -> list[str]:
    """Case 22."""
    if not jobs_of(workflow):
        return ["no jobs"]
    problems = []
    for job, step in steps_of(workflow):
        if not str(step.get("uses", "")).startswith("astral-sh/setup-uv@"):
            continue
        options = step.get("with") if isinstance(step.get("with"), dict) else {}
        if options.get("enable-cache") in (True, "true"):
            problems.append(f"job {job!r}: setup-uv enables the cache")
    return problems


def exception_problems(text: str, applies) -> list[str]:
    """Cases 24 to 26 and 33: each line selected by ``applies`` follows an exception line."""
    lines = text.splitlines()
    problems = []
    for index, line in enumerate(lines):
        if not applies(line):
            continue
        if index == 0 or not EXCEPTION_LINE.match(lines[index - 1]):
            problems.append(f"line {index + 1}: not preceded by an exception line")
    return problems


def is_zizmor_ignore(line: str) -> bool:
    return "zizmor: ignore[" in line and not EXCEPTION_LINE.match(line)


def is_ghsa_reference(line: str) -> bool:
    return bool(GHSA_ID.search(line)) and not line.lstrip().startswith("#")


def is_continue_on_error(line: str) -> bool:
    return bool(CONTINUE_ON_ERROR.match(line))


def trivyignore_problems(text: str) -> list[str]:
    """Cases 23 and 33: entries carry ``exp:`` equal to the review date of the exception above."""
    lines = text.splitlines()
    problems = []
    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        exp = EXP_FIELD.search(line)
        previous = EXCEPTION_LINE.match(lines[index - 1]) if index else None
        if not exp:
            problems.append(f"line {index + 1}: no exp:<date>")
        elif not previous:
            problems.append(f"line {index + 1}: not preceded by an exception line")
        elif previous["date"] != exp["date"]:
            problems.append(f"line {index + 1}: exp date differs from the review date")
        elif not _valid_date(exp["date"]):
            problems.append(f"line {index + 1}: invalid date")
    return problems


def _valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- policy on real files


def test_security_workflow_exists_and_is_a_non_empty_mapping():
    assert SECURITY_WORKFLOW.exists(), ".github/workflows/security.yml does not exist"
    assert isinstance(load_security(), dict) and load_security() != {}


def test_workflow_name_is_security():
    assert name_problems(load_security()) == []


def test_triggers_are_pull_request_and_push_to_main_without_filters():
    assert trigger_problems(load_security()) == []


def test_top_level_permissions_are_empty():
    assert top_permissions_problems(load_security()) == []


def test_job_ids_are_stable_and_unrenamed():
    assert job_id_problems(load_security()) == []


def test_every_job_declares_minimal_permissions():
    assert job_permission_shape_problems(load_security()) == []


def test_security_events_write_only_where_sarif_is_uploaded():
    assert job_upload_permission_problems(load_security()) == []


def test_sarif_uploads_are_guarded_against_forks_with_distinct_categories():
    workflow = load_security()
    assert sarif_upload_problems(workflow) == []
    categories = {step["with"]["category"] for _, step in steps_of(workflow) if is_upload(step)}
    assert categories == EXPECTED_CATEGORIES


def test_security_workflow_does_not_reference_secrets():
    assert secrets_problems(security_text()) == []


def test_no_run_value_contains_an_expression():
    assert run_expression_problems(load_security()) == []


def test_no_if_is_a_multi_line_block():
    assert multiline_if_problems(load_security()) == []


def test_dependency_review_job_is_pull_request_only_and_fails_on_high():
    assert dependency_review_problems(load_security()) == []


def test_trivy_image_is_pinned_by_tag_and_digest():
    assert trivy_image_problems(load_security()) == []


def test_docker_run_uses_only_the_pinned_trivy_image_in_the_trivy_jobs():
    assert trivy_run_problems(load_security()) == []


@pytest.mark.parametrize("path", workflow_files(), ids=lambda path: path.name)
def test_no_workflow_uses_trivy_action_or_setup_trivy(path):
    assert banned_trivy_action_problems(path.read_text(encoding="utf-8")) == []


def test_trivy_config_job_flags():
    assert trivy_config_problems(load_security()) == []


def test_trivy_fs_job_flags():
    assert trivy_fs_problems(load_security()) == []


def test_trivy_jobs_mount_the_checkout_read_only():
    assert trivy_mount_problems(load_security()) == []


def test_zizmor_job_installs_locked_and_runs_through_uv():
    assert zizmor_job_problems(load_security()) == []


def test_zizmor_is_a_locked_dev_dependency():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = pyproject["dependency-groups"]["dev"]
    assert any(re.match(r"zizmor\b", requirement) for requirement in dev)
    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert re.search(r'^name = "zizmor"$', lock, re.MULTILINE)


def test_shared_actions_have_the_same_sha_and_version_comment_in_every_workflow():
    texts = {path.name: path.read_text(encoding="utf-8") for path in workflow_files()}
    assert action_consistency_problems(texts) == []
    shared = {"actions/checkout", "astral-sh/setup-uv"}
    in_security = {
        found["action"]
        for line in security_text().splitlines()
        if (match := USES_LINE.match(line))
        and (found := SHA_AND_VERSION.match(match["value"] + match["rest"]))
    }
    assert shared <= in_security


def test_setup_uv_does_not_enable_the_cache():
    assert setup_uv_cache_problems(load_security()) == []


def test_trivyignore_entries_follow_the_exception_format():
    text = TRIVYIGNORE.read_text(encoding="utf-8") if TRIVYIGNORE.exists() else ""
    assert trivyignore_problems(text) == []


def test_zizmor_ignores_are_documented_in_every_workflow():
    for path in workflow_files():
        text = path.read_text(encoding="utf-8")
        assert exception_problems(text, is_zizmor_ignore) == [], path.name


def test_ghsa_ids_in_security_workflow_are_documented():
    text = security_text()
    assert text != ""
    assert exception_problems(text, is_ghsa_reference) == []


def test_continue_on_error_in_security_workflow_is_documented():
    text = security_text()
    assert text != ""
    assert exception_problems(text, is_continue_on_error) == []


# --------------------------------------------------------------------------- negative examples


def _upload(category="zizmor", condition=GOOD_UPLOAD_IF, with_category=True):
    step: dict = {
        "uses": f"{UPLOAD_ACTION}{SHA40}",
        "with": {"sarif_file": "out.sarif"},
    }
    if condition is not None:
        step["if"] = condition
    if with_category:
        step["with"]["category"] = category
    return step


def _job(permissions, steps=None, **extra):
    job: dict = {"steps": steps if steps is not None else []}
    if permissions is not None:
        job["permissions"] = permissions
    return {**job, **extra}


# case 27


def test_trigger_check_accepts_pull_request_and_push_to_main():
    workflow = {True: {"pull_request": None, "push": {"branches": ["main"]}}}
    assert trigger_problems(workflow) == []
    assert trigger_problems({"on": workflow[True]}) == []


@pytest.mark.parametrize(
    "triggers",
    [
        {"pull_request": None, "push": {"branches": ["main"], "paths": ["src/**"]}},
        {"pull_request": {"paths-ignore": ["docs/**"]}, "push": {"branches": ["main"]}},
        {"pull_request": None, "push": {"branches": ["main", "dev"]}},
        {"pull_request": None, "push": {"branches": ["main"]}, "schedule": [{"cron": "0 0 * * *"}]},
        {"pull_request": {"branches": ["main"]}, "push": {"branches": ["main"]}},
    ],
)
def test_trigger_check_rejects_filters_and_extra_triggers(triggers):
    assert trigger_problems({True: triggers}) != []


# case 28


def test_top_permissions_check_accepts_the_empty_mapping():
    assert top_permissions_problems({"permissions": {}}) == []


@pytest.mark.parametrize(
    "workflow", [{"permissions": {"contents": "read"}}, {}, {"permissions": "read-all"}]
)
def test_top_permissions_check_rejects_anything_but_the_empty_mapping(workflow):
    assert top_permissions_problems(workflow) != []


# case 29


@pytest.mark.parametrize(
    "permissions, steps",
    [
        ({"contents": "read"}, []),
        ({"contents": "read", "security-events": "write"}, [_upload()]),
    ],
)
def test_job_permission_check_accepts_least_privilege(permissions, steps):
    assert job_permission_problems({"jobs": {"a": _job(permissions, steps)}}) == []


@pytest.mark.parametrize(
    "permissions, steps",
    [
        ({"contents": "read", "security-events": "write"}, []),
        ({"contents": "read"}, [_upload()]),
        (None, []),
        ({}, []),
        ({"contents": "write"}, []),
        ({"contents": "read", "pull-requests": "write"}, []),
        ({"contents": "read", "id-token": "write"}, []),
    ],
)
def test_job_permission_check_rejects_excess_or_missing_permissions(permissions, steps):
    assert job_permission_problems({"jobs": {"a": _job(permissions, steps)}}) != []


# case 30


def test_upload_check_accepts_guarded_uploads_with_distinct_categories():
    jobs = {"a": _job({}, [_upload("zizmor")]), "b": _job({}, [_upload("trivy-fs")])}
    assert sarif_upload_problems({"jobs": jobs}) == []


@pytest.mark.parametrize(
    "steps",
    [
        [_upload(condition=None)],
        [_upload(condition="${{ always() }}")],
        [_upload(condition="${{ !cancelled() }}")],
        [_upload(condition="${{ always() && " + FORK_GUARD + " }}")],
        [_upload("same"), _upload("same")],
        [_upload(with_category=False)],
        [],
    ],
)
def test_upload_check_rejects_unguarded_or_ambiguous_uploads(steps):
    assert sarif_upload_problems({"jobs": {"a": _job({}, steps)}}) != []


# case 31


def _run_workflow(run=None, condition=None, job_condition=None):
    step: dict = {}
    if run is not None:
        step["run"] = run
    if condition is not None:
        step["if"] = condition
    extra = {"if": job_condition} if job_condition is not None else {}
    return {"jobs": {"a": _job({}, [step], **extra)}}


def test_run_check_accepts_shell_variables():
    assert run_expression_problems(_run_workflow(run='echo "$TRIVY_IMAGE"')) == []


def test_run_check_rejects_template_expressions():
    assert run_expression_problems(_run_workflow(run="echo ${{ github.head_ref }}")) != []


def test_if_check_accepts_single_line_conditions():
    workflow = _run_workflow(
        run="true", condition="github.event_name == 'pull_request'", job_condition="always()"
    )
    assert multiline_if_problems(workflow) == []


@pytest.mark.parametrize(
    "workflow",
    [
        _run_workflow(run="true", condition="${{ a }}\n${{ b }}\n"),
        _run_workflow(run="true", job_condition="${{ a }}\n${{ b }}\n"),
    ],
)
def test_if_check_rejects_multi_line_blocks(workflow):
    assert multiline_if_problems(workflow) != []


def test_secrets_check_rejects_secret_references_and_accepts_the_job_token():
    assert secrets_problems("env:\n  X: ${{ secrets.X }}\n") != []
    assert secrets_problems("env:\n  GH_TOKEN: ${{ github.token }}\n") == []


# dependency-review (case 12)


def _review_job(condition="github.event_name == 'pull_request'", severity="high"):
    job = _job(
        {"contents": "read"},
        [
            {
                "uses": f"actions/dependency-review-action@{SHA40}",
                "with": {"fail-on-severity": severity},
            }
        ],
    )
    if condition is not None:
        job["if"] = condition
    return {"jobs": {"dependency-review": job}}


def test_dependency_review_check_accepts_a_pull_request_only_high_gate():
    assert dependency_review_problems(_review_job()) == []


@pytest.mark.parametrize(
    "workflow",
    [_review_job(condition=None), _review_job(severity="critical"), {"jobs": {}}],
)
def test_dependency_review_check_rejects_missing_gate_or_scope(workflow):
    assert dependency_review_problems(workflow) != []


# case 32


def test_trivy_image_check_accepts_a_digest_pinned_image():
    image = f"ghcr.io/aquasecurity/trivy:0.1.0@{DIGEST}"
    assert trivy_image_problems({"env": {"TRIVY_IMAGE": image}}) == []


@pytest.mark.parametrize(
    "workflow",
    [
        {"env": {"TRIVY_IMAGE": "aquasec/trivy:latest"}},
        {"env": {"TRIVY_IMAGE": "aquasec/trivy:0.1.0"}},
        {"env": {}},
        {},
    ],
)
def test_trivy_image_check_rejects_unpinned_or_missing_images(workflow):
    assert trivy_image_problems(workflow) != []


def _trivy_workflow(config_run=TRIVY_CONFIG_RUN, fs_run=TRIVY_FS_RUN):
    return {
        "jobs": {
            "trivy-config": _job({"contents": "read"}, [{"run": config_run}]),
            "trivy-fs": _job({"contents": "read"}, [{"run": fs_run}]),
        }
    }


def test_trivy_checks_accept_the_expected_runs():
    workflow = _trivy_workflow()
    assert trivy_run_problems(workflow) == []
    assert trivy_config_problems(workflow) == []
    assert trivy_fs_problems(workflow) == []
    assert trivy_mount_problems(workflow) == []


def test_trivy_checks_accept_continuations_and_a_non_failing_first_run():
    run = TRIVY_FS_RUN.replace(" --scanners", " \\\n  --scanners")
    quiet = run.replace("--exit-code 1", "--exit-code 0")
    workflow = {
        "jobs": {
            "trivy-config": _trivy_workflow()["jobs"]["trivy-config"],
            "trivy-fs": _job({"contents": "read"}, [{"run": quiet}, {"run": run}]),
        }
    }
    assert trivy_fs_problems(workflow) == []


@pytest.mark.parametrize(
    "run",
    [
        "docker run --rm aquasec/trivy:0.1.0 fs .",
        'docker run --rm "$TRIVY_IMAGE" fs . && docker run --rm aquasec/trivy:0.1.0 fs .',
        "docker run --rm alpine:3.20 true",
    ],
)
def test_trivy_run_check_rejects_literal_images(run):
    assert trivy_run_problems(_trivy_workflow(fs_run=run)) != []


def test_trivy_run_check_rejects_trivy_outside_the_trivy_jobs():
    workflow = {"jobs": {"zizmor": _job({"contents": "read"}, [{"run": TRIVY_FS_RUN}])}}
    assert trivy_run_problems(workflow) != []


def test_banned_action_check_rejects_trivy_action():
    line = f"      - uses: aquasecurity/trivy-action@{SHA40} # v0.1.0"
    assert banned_trivy_action_problems(line) != []
    setup = f"      - uses: aquasecurity/setup-trivy@{SHA40} # v0.1.0"
    assert banned_trivy_action_problems(setup) != []
    assert banned_trivy_action_problems(f"      - uses: actions/checkout@{SHA40} # v7.0.1") == []


@pytest.mark.parametrize(
    "fs_run",
    [
        TRIVY_FS_RUN.replace(" --ignore-unfixed", ""),
        TRIVY_FS_RUN.replace("--severity HIGH,CRITICAL", "--severity MEDIUM,HIGH,CRITICAL"),
        TRIVY_FS_RUN.replace("--scanners vuln,secret", "--scanners vuln"),
        TRIVY_FS_RUN.replace("--exit-code 1", "--exit-code 0"),
        TRIVY_CONFIG_RUN,
    ],
)
def test_trivy_fs_check_rejects_missing_or_wrong_flags(fs_run):
    assert trivy_fs_problems(_trivy_workflow(fs_run=fs_run)) != []


@pytest.mark.parametrize(
    "config_run",
    [
        TRIVY_CONFIG_RUN.replace("--misconfig-scanners dockerfile ", ""),
        TRIVY_CONFIG_RUN.replace("--severity HIGH,CRITICAL", "--severity MEDIUM,HIGH,CRITICAL"),
        TRIVY_CONFIG_RUN.replace("--exit-code 1", "--exit-code 0"),
        TRIVY_FS_RUN,
    ],
)
def test_trivy_config_check_rejects_missing_or_wrong_flags(config_run):
    assert trivy_config_problems(_trivy_workflow(config_run=config_run)) != []


def test_trivy_mount_check_rejects_a_writable_checkout():
    run = TRIVY_FS_RUN.replace(":/src:ro", ":/src")
    assert trivy_mount_problems(_trivy_workflow(fs_run=run)) != []
    assert trivy_mount_problems(_trivy_workflow(config_run=run)) != []


# case 19


def _zizmor_job(
    sync="uv sync --locked --only-dev", call="uv run --no-sync zizmor .", credential=None
):
    steps: list[dict] = [{"run": sync}]
    step: dict = {"run": call}
    if credential is not None:
        step["env"] = {"GH_TOKEN": credential}
    steps.append(step)
    return {"jobs": {"zizmor": _job({"contents": "read"}, steps)}}


def test_zizmor_check_accepts_locked_sync_uv_run_and_the_job_token():
    assert zizmor_job_problems(_zizmor_job(credential=GITHUB_CREDENTIAL_EXPRESSION)) == []
    assert zizmor_job_problems(_zizmor_job()) == []


@pytest.mark.parametrize(
    "workflow",
    [
        _zizmor_job(sync="uv sync --only-dev"),
        _zizmor_job(call="zizmor ."),
        _zizmor_job(credential="${{ github.event.pull_request.title }}"),
        {"jobs": {}},
    ],
)
def test_zizmor_check_rejects_unlocked_sync_bare_call_or_foreign_token(workflow):
    assert zizmor_job_problems(workflow) != []


# case 22


def test_setup_uv_cache_check_rejects_enable_cache():
    cached = {"uses": f"astral-sh/setup-uv@{SHA40}", "with": {"enable-cache": True}}
    plain = {"uses": f"astral-sh/setup-uv@{SHA40}"}
    assert setup_uv_cache_problems({"jobs": {"a": _job({}, [cached])}}) != []
    assert setup_uv_cache_problems({"jobs": {"a": _job({}, [plain])}}) == []


# case 33: exceptions


def _entry(reason="false positive on test fixture", url=None, review="2027-01-31"):
    url = url or "https://github.com/o/r/security/code-scanning/1"
    return f"# exception: {reason}; {url}; review {review}"


def test_trivyignore_check_accepts_a_documented_entry():
    assert trivyignore_problems(f"{GOOD_EXCEPTION}\nCVE-2026-0001 exp:2027-01-31\n") == []


@pytest.mark.parametrize(
    "text",
    [
        "CVE-2026-0001 exp:2027-01-31\n",
        f"{GOOD_EXCEPTION}\nCVE-2026-0001\n",
        f"{_entry(review='2027-01-31')}\nCVE-2026-0001 exp:2027-03-31\n",
        f"{_entry(url='no link here')}\nCVE-2026-0001 exp:2027-01-31\n",
        f"{_entry(reason='')}\nCVE-2026-0001 exp:2027-01-31\n",
        f"{GOOD_EXCEPTION}\n\nCVE-2026-0001 exp:2027-01-31\n",
    ],
)
def test_trivyignore_check_rejects_undocumented_entries(text):
    assert trivyignore_problems(text) != []


def test_zizmor_ignore_check_requires_an_exception_line_above():
    ignore = "        uses: x/y@abc  # zizmor: ignore[template-injection]"
    assert exception_problems(f"{GOOD_EXCEPTION}\n{ignore}\n", is_zizmor_ignore) == []
    assert exception_problems(f"{ignore}\n", is_zizmor_ignore) != []
    assert exception_problems(f"run: true\n{ignore}\n", is_zizmor_ignore) != []


def test_ghsa_check_requires_an_exception_line_above():
    entry = "          allow-ghsas: GHSA-abcd-efgh-ijkl"
    assert exception_problems(f"{GOOD_EXCEPTION}\n{entry}\n", is_ghsa_reference) == []
    assert exception_problems(f"with:\n{entry}\n", is_ghsa_reference) != []


def test_continue_on_error_check_requires_an_exception_line_above():
    line = "    continue-on-error: true"
    assert exception_problems(f"{GOOD_EXCEPTION}\n{line}\n", is_continue_on_error) == []
    assert exception_problems(f"job:\n{line}\n", is_continue_on_error) != []


# case 33: same action, same pin


def _pinned(action, sha, version):
    return f"      - uses: {action}@{sha} # {version}\n"


def test_action_consistency_check_accepts_identical_pins():
    text = _pinned("actions/checkout", SHA40, "v7.0.1")
    assert action_consistency_problems({"ci.yml": text, "security.yml": text}) == []


def test_action_consistency_check_rejects_different_shas():
    texts = {
        "ci.yml": _pinned("actions/checkout", "a" * 40, "v7.0.1"),
        "security.yml": _pinned("actions/checkout", "b" * 40, "v7.0.1"),
    }
    assert action_consistency_problems(texts) != []


def test_action_consistency_check_rejects_different_version_comments():
    texts = {
        "ci.yml": _pinned("actions/checkout", SHA40, "v7.0.1"),
        "security.yml": _pinned("actions/checkout", SHA40, "v7.0.2"),
    }
    assert action_consistency_problems(texts) != []
