FROM ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    TZ=America/Sao_Paulo

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY ingestion/ ingestion/
COPY flows/ flows/
COPY migrations/ migrations/
COPY alembic.ini ./
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 10001 app
USER app

ENTRYPOINT []
CMD ["python", "-m", "ingestion", "--help"]
