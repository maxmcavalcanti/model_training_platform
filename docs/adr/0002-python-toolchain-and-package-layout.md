# ADR 0002: Toolchain Python e layout de pacotes

Status: Aceito
Data: 2026-11-07
Decisores: Maximiliano

## Contexto

Ainda não há código no repo. Todo PR seguinte precisa de lint, teste e CI reais. A toolchain e o layout abaixo foram aprovados pelo usuário em 2026-11-07 (P1 de `docs/plans/00-indice.md`: "uv, ruff, pytest, hatchling, Python 3.12, CI no GitHub Actions, pacotes na raiz") e serão implementados pelo PR 01 (`docs/plans/01-bootstrap-ambiente-dev.md`). Este ADR só registra a decisão.

Este ADR foi escrito pelo `task-implementer` por instrução expressa do usuário, como exceção à regra do `AGENTS.md` ("Nenhum agente escreve ADR"). A exceção vale só para este ADR.

## Decisão

### Gerenciador e lockfile

uv gerencia dependências e a versão do Python. O `uv.lock` é gerado pelo uv e commitado. Toda dependência nova entra por `uv add <pacote>` (dev: `uv add --dev <pacote>`), sempre commitando `uv.lock`. O CI instala com `uv sync --locked`.

### Versão do Python

Python 3.12, nos dois lugares:

- `.python-version` com `3.12`.
- `requires-python = ">=3.12,<3.13"` no `pyproject.toml`.

É a versão do guia da ciência de dados (`docs/guia-ciencia-de-dados.md`, "Ferramentas") e é suportada por Prefect 3 e MLflow. A mesma versão nos dois repos evita surpresa no job de score.

### Backend de build e layout de pacotes

```toml
[project]
name = "platform"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = []

[dependency-groups]
dev = ["pytest", "ruff", "pyyaml"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["ingestion", "flows"]
```

O grupo `dev` é preenchido com `uv add --dev` para que as versões fiquem no lock.

O nome de distribuição `platform` não conflita com o módulo `platform` da stdlib: só um diretório ou pacote importável com esse nome conflitaria, e não haverá.

Os pacotes ficam na raiz do repo, sem `src/`: `ingestion/` e `flows/` (árvore de `docs/plataforma-ml.md`, seção do repo `platform`). O hatchling com `packages = ["ingestion", "flows"]` mantém essa árvore e deixa os pacotes importáveis no venv e na imagem Docker. `tests/` fica na raiz. `migrations/` (Alembic, PR 06) e `infra/` ficam na raiz e não são pacotes do wheel.

### Lint e formatação

ruff para lint (`ruff check`) e formatação (`ruff format`):

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

### Testes

pytest, configurado assim:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = ["db: ..."]
```

O marcador `db` é para testes que precisam de Postgres, usado a partir do PR 05.

### CI

`.github/workflows/ci.yml`, gatilhos `pull_request` e `push` na `main`, job `lint-and-test` em `ubuntu-latest`, com os passos:

1. `actions/checkout`
2. `astral-sh/setup-uv` com `enable-cache: true`
3. `uv sync --locked`
4. `uv run ruff check .`
5. `uv run ruff format --check .`
6. `uv run pytest`

As actions são fixadas por major, conferida no Marketplace na hora do PR 01.

## Comandos canônicos

O PR 01 grava estes comandos na seção "Comandos" do `AGENTS.md`:

- Instalar: `uv sync`
- Lint: `uv run ruff check .`
- Formatação (checar): `uv run ruff format --check .`
- Formatação (aplicar): `uv run ruff format .`
- Suíte: `uv run pytest`
- Um arquivo: `uv run pytest tests/<arquivo>.py`
- Um teste: `uv run pytest tests/<arquivo>.py::<test_name>`

## Consequências

- Todos os PRs seguintes usam os comandos canônicos, e nenhum plano usa comando que não exista no ponto em que roda.
- Dependência nova sempre por `uv add`, com `uv.lock` no mesmo commit.
- A toolchain é base dos usos já planejados, cujos detalhes continuam nos respectivos planos e ADRs:
  - PR 05: `uv add sqlalchemy "psycopg[binary]"` e `uv run pytest -m "not db"`.
  - PR 06: `uv add alembic`; `uv run alembic upgrade head` também no CI.
  - PR 11: imagem baseada em `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` (tag a conferir), `uv sync --locked --no-dev`, copiando `ingestion/`, `flows/`, `migrations/` e `alembic.ini`.
  - PR 44: o executor monta `uv run --frozen --with <pacote models> python -m <módulo>`; os detalhes são do ADR de execução (P12/P13).
- A mesma versão do Python (3.12) é esperada no repo `models`. O layout daquele repo (`src/models/`, em `docs/plataforma-ml.md`) difere deste e é decisão dele.
- Risco de fim de linha no Windows: o `ruff format` normaliza; se o CI acusar diferença, o PR 01 adiciona `.gitattributes` com `* text=auto eol=lf`.
- Ficam fora desta decisão: pre-commit, mypy, cobertura mínima e Dependabot.

## Alternativas consideradas

- Poetry: mais lento e não gerencia a versão do Python.
- pip-tools: não gerencia a versão do Python e exige dois arquivos de lock.
- Layout `src/`: rejeitado por divergir da árvore de `docs/plataforma-ml.md`.

Motivo de escolher o uv: um binário só, gerencia a versão do Python, lockfile multiplataforma, `uv run --with` (útil no PR 44) e action oficial no GitHub.
