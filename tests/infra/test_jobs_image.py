"""Static policy tests for the jobs Dockerfile and `.dockerignore` (plan 11, cases 14 to 19).

The check functions are exercised with embedded negative examples, so a passing policy test
cannot be an artifact of a check that accepts everything.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "infra" / "jobs" / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"

BASE_IMAGE = re.compile(
    r"^ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+-python3\.12-bookworm-slim(@sha256:[0-9a-f]{64})?$"
)
SECRET_NAME_MARKERS = ("PASSWORD", "TOKEN", "SECRET", "DATABASE_URL")
ROOT_USERS = frozenset({"root", "0"})


# --------------------------------------------------------------------------- check functions


def instructions(dockerfile_text: str) -> list[tuple[str, str]]:
    """Return (INSTRUCTION, arguments) pairs: joins line continuations, skips comments."""
    logical_lines: list[str] = []
    buffer = ""
    for raw_line in dockerfile_text.splitlines():
        stripped = raw_line.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if buffer and stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1].strip() + " "
            continue
        logical_lines.append((buffer + stripped).strip())
        buffer = ""
    if buffer:
        logical_lines.append(buffer.strip())
    result = []
    for line in logical_lines:
        keyword, _, arguments = line.partition(" ")
        result.append((keyword.upper(), arguments.strip()))
    return result


def base_image_problems(dockerfile_text: str) -> list[str]:
    """Case 14: every ``FROM`` is the version-pinned uv image for Python 3.12 bookworm-slim."""
    froms = [args for keyword, args in instructions(dockerfile_text) if keyword == "FROM"]
    if not froms:
        return ["no FROM instruction"]
    problems = []
    for args in froms:
        tokens = [token for token in args.split() if not token.startswith("--")]
        image = tokens[0] if tokens else ""
        if not BASE_IMAGE.match(image):
            problems.append(f"unacceptable base image {image!r}")
    return problems


def user_problems(dockerfile_text: str) -> list[str]:
    """Case 15: the last ``USER`` exists and is not root."""
    users = [args for keyword, args in instructions(dockerfile_text) if keyword == "USER"]
    if not users:
        return ["no USER instruction"]
    if users[-1].split(":")[0].strip() in ROOT_USERS:
        return [f"last USER is {users[-1]!r}"]
    return []


def copy_problems(dockerfile_text: str) -> list[str]:
    """Case 16: no ``ADD`` and no ``COPY`` of the whole build context."""
    problems = []
    for keyword, args in instructions(dockerfile_text):
        if keyword == "ADD":
            problems.append(f"ADD {args}")
        elif keyword == "COPY":
            tokens = [token for token in args.split() if not token.startswith("--")]
            if any(source in (".", "./") for source in tokens[:-1]):
                problems.append(f"COPY {args}")
    return problems


def secret_name_problems(dockerfile_text: str) -> list[str]:
    """Case 17: no ``ENV`` or ``ARG`` whose name looks like a secret or a database URL."""
    problems = []
    for keyword, args in instructions(dockerfile_text):
        if keyword not in ("ENV", "ARG"):
            continue
        names = re.findall(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=", args)
        if not names and args:
            names = [args.split()[0].split("=")[0]]
        for name in names:
            if any(marker in name.upper() for marker in SECRET_NAME_MARKERS):
                problems.append(f"{keyword} {name}")
    return problems


def uv_sync_problems(dockerfile_text: str) -> list[str]:
    """Case 18: every ``RUN`` with ``uv sync`` passes ``--locked`` and ``--no-dev``."""
    problems = []
    for keyword, args in instructions(dockerfile_text):
        if keyword == "RUN" and "uv sync" in args:
            for flag in ("--locked", "--no-dev"):
                if flag not in args.split():
                    problems.append(f"RUN {args} lacks {flag}")
    return problems


def dockerignore_problems(text: str) -> list[str]:
    """Case 19: patterns exclude ``.env`` files at any depth, ``.git`` and ``.venv``."""
    patterns = {
        line.strip().rstrip("/")
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    problems = []
    if not ({"**/.env", "**/.env*"} & patterns):
        problems.append("missing **/.env")
    if not ({"**/.env.*", "**/.env*"} & patterns):
        problems.append("missing **/.env.*")
    for required in (".git", ".venv"):
        if required not in patterns:
            problems.append(f"missing {required}")
    return problems


def key_material_problems(text: str) -> list[str]:
    """H1 cases 13 to 15: ``.pem`` and ``.key`` files are excluded at any depth."""
    patterns = {
        line.strip().rstrip("/")
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return [f"missing {pattern}" for pattern in ("**/*.pem", "**/*.key") if pattern not in patterns]


# --------------------------------------------------------------------------- policy tests


@pytest.fixture
def dockerfile_text() -> str:
    assert DOCKERFILE.is_file(), f"{DOCKERFILE} does not exist"
    return DOCKERFILE.read_text(encoding="utf-8")


def test_base_image_is_pinned_uv_python312_bookworm_slim(dockerfile_text):
    assert base_image_problems(dockerfile_text) == []


def test_image_ends_as_a_non_root_user(dockerfile_text):
    assert user_problems(dockerfile_text) == []


def test_image_never_copies_the_whole_context_or_uses_add(dockerfile_text):
    assert copy_problems(dockerfile_text) == []


def test_image_has_no_secret_or_database_url_env_or_arg(dockerfile_text):
    assert secret_name_problems(dockerfile_text) == []


def test_uv_sync_is_locked_and_without_dev(dockerfile_text):
    assert uv_sync_problems(dockerfile_text) == []


def test_dockerignore_excludes_secrets_and_vcs_at_any_depth():
    assert DOCKERIGNORE.is_file(), f"{DOCKERIGNORE} does not exist"
    assert dockerignore_problems(DOCKERIGNORE.read_text(encoding="utf-8")) == []


# --------------------------------------------------------------------------- negative examples


@pytest.mark.parametrize(
    "image",
    [
        "ghcr.io/astral-sh/uv:0.9.5-python3.12-bookworm-slim",
        f"ghcr.io/astral-sh/uv:0.9.5-python3.12-bookworm-slim@sha256:{'a' * 64}",
    ],
)
def test_base_image_check_accepts_pinned_tags(image):
    assert base_image_problems(f"FROM {image}\n") == []


@pytest.mark.parametrize(
    "image",
    [
        "ghcr.io/astral-sh/uv:python3.12-bookworm-slim",
        "ghcr.io/astral-sh/uv:latest",
        "ghcr.io/astral-sh/uv",
        "python:3.12-slim",
        "ghcr.io/astral-sh/uv:0.9.5-python3.11-bookworm-slim",
    ],
)
def test_base_image_check_rejects_floating_or_other_images(image):
    assert base_image_problems(f"FROM {image}\n") != []


def test_base_image_check_rejects_a_dockerfile_without_from():
    assert base_image_problems("RUN true\n") != []


def test_user_check_accepts_non_root_user():
    assert user_problems("USER app\n") == []


@pytest.mark.parametrize(
    "text",
    ["RUN true\n", "USER app\nUSER root\n", "USER 0\n", "USER root:root\n"],
)
def test_user_check_rejects_missing_or_root_user(text):
    assert user_problems(text) != []


def test_copy_check_accepts_explicit_sources():
    assert copy_problems("COPY ingestion/ ingestion/\n") == []


@pytest.mark.parametrize(
    "text",
    ["COPY . .\n", "COPY ./ /app/\n", "ADD ingestion/ ingestion/\n", "COPY --chown=app . /app\n"],
)
def test_copy_check_rejects_whole_context_and_add(text):
    assert copy_problems(text) != []


def test_secret_name_check_accepts_harmless_env():
    assert secret_name_problems("ENV UV_LINK_MODE=copy TZ=America/Sao_Paulo\n") == []


@pytest.mark.parametrize(
    "text",
    [
        "ENV DATABASE_URL=postgresql://x\n",
        "ARG POSTGRES_ADMIN_PASSWORD\n",
        "ENV A=1 API_TOKEN=x\n",
        "ENV APP_SECRET x\n",
    ],
)
def test_secret_name_check_rejects_secret_like_names(text):
    assert secret_name_problems(text) != []


def test_uv_sync_check_accepts_locked_no_dev_including_continuations():
    text = (
        "RUN uv sync --locked --no-dev --no-install-project\nRUN uv sync \\\n --locked --no-dev\n"
    )
    assert uv_sync_problems(text) == []


@pytest.mark.parametrize(
    "text", ["RUN uv sync\n", "RUN uv sync --locked\n", "RUN uv sync --no-dev\n"]
)
def test_uv_sync_check_rejects_missing_flags(text):
    assert uv_sync_problems(text) != []


@pytest.mark.parametrize(
    "text",
    [".git\n.venv\n**/.env\n**/.env.*\n", ".git/\n.venv\n**/.env*\n"],
)
def test_dockerignore_check_accepts_deep_env_patterns(text):
    assert dockerignore_problems(text) == []


@pytest.mark.parametrize(
    "text",
    [".env*\n.git\n.venv\n", "**/.env\n.git\n.venv\n", "**/.env*\n.venv\n", "**/.env*\n.git\n"],
)
def test_dockerignore_check_rejects_root_only_or_incomplete_patterns(text):
    assert dockerignore_problems(text) != []


# H1 case 13
def test_dockerignore_excludes_key_material_at_any_depth():
    assert DOCKERIGNORE.is_file(), f"{DOCKERIGNORE} does not exist"
    assert key_material_problems(DOCKERIGNORE.read_text(encoding="utf-8")) == []


# H1 case 14
@pytest.mark.parametrize("text", ["**/*.pem\n**/*.key\n", "# keys\n**/*.key\n**/*.pem\n"])
def test_key_material_check_accepts_deep_patterns(text):
    assert key_material_problems(text) == []


# H1 case 15
@pytest.mark.parametrize("text", ["*.pem\n*.key\n", "**/*.pem\n", "**/*.key\n"])
def test_key_material_check_rejects_root_only_or_incomplete_patterns(text):
    assert key_material_problems(text) != []


# =========================================================================== plan 16
# Pinned supercronic in the jobs image (cases 17 to 22).

SUPERCRONIC_VERSION_FORMAT = re.compile(r"^v\d+\.\d+\.\d+$")
SHA256_FORMAT = re.compile(r"^[0-9a-f]{64}$")
SUPERCRONIC_URL = (
    "https://github.com/aptible/supercronic/releases/download/"
    "${SUPERCRONIC_VERSION}/supercronic-linux-amd64"
)
SHA256_CHECK = re.compile(r"\bsha256sum\s+-c\b")
CRON_DIRECTORY = {"infra/cron", "infra/cron/"}
EXPECTED_TIMEZONE = "America/Sao_Paulo"


def arg_values(dockerfile_text: str, name: str) -> list[str | None]:
    """Default values of every ``ARG <name>`` (``None`` when declared without a default)."""
    values: list[str | None] = []
    for keyword, args in instructions(dockerfile_text):
        if keyword != "ARG":
            continue
        arg_name, sep, value = args.partition("=")
        if arg_name.strip() == name:
            values.append(value.strip() if sep else None)
    return values


def arg_format_problems(dockerfile_text: str, name: str, pattern: re.Pattern[str]) -> list[str]:
    values = arg_values(dockerfile_text, name)
    if len(values) != 1:
        return [f"expected exactly one ARG {name}, got {len(values)}"]
    value = values[0]
    if value is None or not pattern.match(value):
        return [f"ARG {name} has unacceptable value {value!r}"]
    return []


def supercronic_version_problems(dockerfile_text: str) -> list[str]:
    """Case 17: ``ARG SUPERCRONIC_VERSION=v<n>.<n>.<n>``."""
    return arg_format_problems(dockerfile_text, "SUPERCRONIC_VERSION", SUPERCRONIC_VERSION_FORMAT)


def supercronic_checksum_problems(dockerfile_text: str) -> list[str]:
    """Case 18: ``ARG SUPERCRONIC_SHA256`` is 64 lowercase hex characters."""
    return arg_format_problems(dockerfile_text, "SUPERCRONIC_SHA256", SHA256_FORMAT)


def supercronic_download_problems(dockerfile_text: str) -> list[str]:
    """Case 19: one ``RUN`` downloads the pinned amd64 asset and verifies it with sha256sum."""
    for keyword, args in instructions(dockerfile_text):
        if (
            keyword == "RUN"
            and SUPERCRONIC_URL in args
            and SHA256_CHECK.search(args)
            and "${SUPERCRONIC_SHA256}" in args
        ):
            return []
    return ["no RUN downloads the pinned supercronic and verifies it with sha256sum -c"]


def cron_copy_problems(dockerfile_text: str) -> list[str]:
    """Case 20: ``COPY infra/cron/ infra/cron/`` (relative to ``WORKDIR /app``)."""
    workdirs = [args for keyword, args in instructions(dockerfile_text) if keyword == "WORKDIR"]
    if "/app" not in workdirs:
        return ["no WORKDIR /app"]
    for keyword, args in instructions(dockerfile_text):
        if keyword != "COPY":
            continue
        tokens = [token for token in args.split() if not token.startswith("--")]
        if len(tokens) == 2 and tokens[0] in CRON_DIRECTORY and tokens[1] in CRON_DIRECTORY:
            return []
    return ["no COPY infra/cron/ infra/cron/"]


def timezone_problems(dockerfile_text: str) -> list[str]:
    """Case 21: the last ``TZ`` set by an ``ENV`` is America/Sao_Paulo."""
    values = [
        match.group(1)
        for keyword, args in instructions(dockerfile_text)
        if keyword == "ENV"
        for match in re.finditer(r"(?:^|\s)TZ=(\S+)", args)
    ]
    if not values:
        return ["no ENV TZ"]
    if values[-1] != EXPECTED_TIMEZONE:
        return [f"TZ is {values[-1]!r}, expected {EXPECTED_TIMEZONE!r}"]
    return []


# --------------------------------------------------------------------------- plan 16 policy


def test_supercronic_version_is_pinned_to_a_release_tag(dockerfile_text):
    assert supercronic_version_problems(dockerfile_text) == []


def test_supercronic_checksum_is_a_sha256(dockerfile_text):
    assert supercronic_checksum_problems(dockerfile_text) == []


def test_supercronic_is_downloaded_from_the_pinned_release_and_verified(dockerfile_text):
    assert supercronic_download_problems(dockerfile_text) == []


def test_crontab_directory_is_copied_into_the_image_without_add(dockerfile_text):
    assert cron_copy_problems(dockerfile_text) == []
    assert not [keyword for keyword, _ in instructions(dockerfile_text) if keyword == "ADD"]


def test_image_keeps_the_sao_paulo_timezone(dockerfile_text):
    assert timezone_problems(dockerfile_text) == []


def test_existing_rules_hold_with_the_supercronic_args(dockerfile_text):
    # The new ARGs must exist for this guard to mean anything.
    assert arg_values(dockerfile_text, "SUPERCRONIC_VERSION") != []
    assert arg_values(dockerfile_text, "SUPERCRONIC_SHA256") != []
    assert secret_name_problems(dockerfile_text) == []
    assert user_problems(dockerfile_text) == []
    users = [args for keyword, args in instructions(dockerfile_text) if keyword == "USER"]
    assert users[-1] == "app"


# --------------------------------------------------------------------------- plan 16 negatives

GOOD_DOWNLOAD = (
    "RUN curl -fsSLo /tmp/supercronic \\\n"
    f'    "{SUPERCRONIC_URL}" \\\n'
    '    && echo "${SUPERCRONIC_SHA256}  /tmp/supercronic" | sha256sum -c -\n'
)


@pytest.mark.parametrize("value", ["v0.2.33", "v1.10.0"])
def test_version_check_accepts_release_tags(value):
    assert supercronic_version_problems(f"ARG SUPERCRONIC_VERSION={value}\n") == []


@pytest.mark.parametrize(
    "text",
    [
        "ARG SUPERCRONIC_VERSION\n",
        "ARG SUPERCRONIC_VERSION=latest\n",
        "ARG SUPERCRONIC_VERSION=0.2.33\n",
        "ARG SUPERCRONIC_VERSION=v0.2\n",
        "ARG SUPERCRONIC_VERSION=\n",
        "RUN true\n",
    ],
)
def test_version_check_rejects_floating_or_malformed_values(text):
    assert supercronic_version_problems(text) != []


def test_checksum_check_accepts_64_lowercase_hex():
    assert supercronic_checksum_problems(f"ARG SUPERCRONIC_SHA256={'a1' * 32}\n") == []


@pytest.mark.parametrize(
    "value",
    ["a" * 40, "a" * 63, "", f"sha256:{'a' * 64}", "A" * 64, "g" * 64],
)
def test_checksum_check_rejects_other_values(value):
    assert supercronic_checksum_problems(f"ARG SUPERCRONIC_SHA256={value}\n") != []


def test_checksum_check_rejects_a_missing_arg():
    assert supercronic_checksum_problems("RUN true\n") != []


def test_download_check_accepts_the_pinned_download_with_sha256sum():
    assert supercronic_download_problems(GOOD_DOWNLOAD) == []


@pytest.mark.parametrize(
    "text",
    [
        GOOD_DOWNLOAD.replace("/download/${SUPERCRONIC_VERSION}/", "/latest/"),
        GOOD_DOWNLOAD.replace("linux-amd64", "linux-arm64"),
        GOOD_DOWNLOAD.replace("sha256sum -c -", "true"),
        GOOD_DOWNLOAD.replace("sha256sum", "sha1sum"),
        GOOD_DOWNLOAD.replace("${SUPERCRONIC_SHA256}", "deadbeef"),
        "RUN true\n",
    ],
)
def test_download_check_rejects_unpinned_or_unverified_downloads(text):
    assert supercronic_download_problems(text) != []


def test_download_check_requires_the_verification_in_the_same_run():
    text = (
        f'RUN curl -fsSLo /tmp/supercronic "{SUPERCRONIC_URL}"\n'
        "RUN sha256sum -c ${SUPERCRONIC_SHA256}\n"
    )
    assert supercronic_download_problems(text) != []


def test_cron_copy_check_accepts_the_crontab_directory():
    assert cron_copy_problems("WORKDIR /app\nCOPY infra/cron/ infra/cron/\n") == []


@pytest.mark.parametrize(
    "text",
    [
        "WORKDIR /app\nCOPY infra/cron/ /etc/cron/\n",
        "WORKDIR /app\nCOPY infra/ infra/\n",
        "WORKDIR /app\nCOPY cron/ infra/cron/\n",
        "WORKDIR /app\nADD infra/cron/ infra/cron/\n",
        "COPY infra/cron/ infra/cron/\n",
        "WORKDIR /app\n",
    ],
)
def test_cron_copy_check_rejects_other_copies(text):
    assert cron_copy_problems(text) != []


@pytest.mark.parametrize(
    "text",
    [
        "ENV TZ=America/Sao_Paulo\n",
        "ENV A=1 TZ=America/Sao_Paulo\n",
        "ENV TZ=UTC\nENV TZ=America/Sao_Paulo\n",
    ],
)
def test_timezone_check_accepts_sao_paulo(text):
    assert timezone_problems(text) == []


@pytest.mark.parametrize(
    "text",
    ["ENV TZ=UTC\n", "ENV A=1\n", "RUN true\n", "ENV TZ=America/Sao_Paulo\nENV TZ=UTC\n"],
)
def test_timezone_check_rejects_other_or_missing_values(text):
    assert timezone_problems(text) != []
