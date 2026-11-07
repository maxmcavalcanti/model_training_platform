# 01 — Bootstrap do ambiente de desenvolvimento

> Executa: agente (task-implementer). Depende de: nada. Branch sugerida: `chore/bootstrap-dev-env`.
> Índice e convenções gerais: `docs/plans/00-indice.md`.

## 1. Objetivo

Criar o ambiente Python do repositório (uv, pyproject, ruff, pytest) e um CI mínimo no GitHub Actions.
Preencher a seção "Comandos" do `AGENTS.md` com os comandos reais, para que todos os PRs seguintes possam usá-los.

## 2. Fora do escopo

- Postgres, Alembic, Docker, compose (PRs 03, 05, 06).
- Qualquer código de ingestão além de um pacote vazio importável.
- Pre-commit hooks, mypy, cobertura mínima, Dependabot (podem virar PR próprio depois, se o usuário quiser).
- Alterar `.claude/` ou `CLAUDE.md`.

## 3. Fase do roadmap

Pré-requisito da Fase 0 (`docs/plataforma-ml.md`, seção "Roadmap"). O roadmap não lista o bootstrap, mas sem ele nenhum PR seguinte tem comando de teste.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml` | Metadados do projeto, dependências, config do ruff e do pytest |
| `uv.lock` | Lockfile gerado por `uv lock` (commitar) |
| `.python-version` | Fixa Python 3.12 para o uv |
| `.gitignore` | `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.env`, `.env.*` (exceto `.env.example`) |
| `ingestion/__init__.py` | Pacote vazio (nome vem da árvore de `docs/plataforma-ml.md`) |
| `flows/__init__.py` | Pacote vazio (idem) |
| `tests/__init__.py` | Vazio |
| `tests/test_smoke.py` | Um teste que importa `ingestion` e `flows`. Exceção ao TDD justificada na seção 7 |
| `.github/workflows/ci.yml` | CI: ruff check, ruff format --check, pytest |
| `AGENTS.md` | Substituir o texto da seção "Comandos" pelos comandos reais |

## 5. Passos

1. Confirme que o `uv` está instalado: `uv --version`. Se não estiver, pare e reporte ao usuário (a toolchain foi aprovada em 2026-11-07, P1 resolvida; falta só a instalação).
2. Crie `.python-version` com o conteúdo `3.12`.
3. Crie `pyproject.toml`:
   - `[project]`: `name = "platform"`, `version = "0.1.0"`, `requires-python = ">=3.12,<3.13"`, `dependencies = []`.
   - `[dependency-groups]`: `dev = ["pytest", "ruff", "pyyaml"]` (pyyaml é usado pelos testes de compose do PR 03; incluir agora evita um commit só de dependência lá). Adicione com `uv add --dev pytest ruff pyyaml` para que as versões fiquem no lock.
   - `[build-system]`: `requires = ["hatchling"]`, `build-backend = "hatchling.build"`.
   - `[tool.hatch.build.targets.wheel]`: `packages = ["ingestion", "flows"]`.
   - `[tool.ruff]`: `line-length = 100`, `target-version = "py312"`.
   - `[tool.ruff.lint]`: `select = ["E", "F", "I", "B", "UP"]`.
   - `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `addopts = "-ra --strict-markers"`, `markers = ["db: precisa de Postgres (ver AGENTS.md, Comandos)"]`.
4. Crie os pacotes vazios `ingestion/__init__.py`, `flows/__init__.py`, `tests/__init__.py`.
5. Crie `tests/test_smoke.py` com um único teste: `import ingestion` e `import flows` não levantam erro.
6. Rode `uv sync` e confirme que gera `uv.lock` e `.venv/`.
7. Crie `.gitignore` com as entradas da tabela.
8. Crie `.github/workflows/ci.yml`:
   - Gatilhos: `pull_request` e `push` na `main`.
   - Um job `lint-and-test` em `ubuntu-latest`: `actions/checkout` (major atual), `astral-sh/setup-uv` (major atual, com `enable-cache: true`), `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`.
   - Fixe as actions por major (ex.: `@v4`) depois de conferir no GitHub Marketplace qual é a atual. Não invente versão.
9. Substitua a seção "Comandos" do `AGENTS.md` por (texto exato, em lista):
   - Instalar/atualizar ambiente: `uv sync`
   - Lint: `uv run ruff check .`
   - Formatação (checar): `uv run ruff format --check .` / aplicar: `uv run ruff format .`
   - Suíte de testes: `uv run pytest`
   - Um arquivo: `uv run pytest tests/test_smoke.py`
   - Um teste: `uv run pytest tests/test_smoke.py::<test_name>`
   - Adicionar dependência: `uv add <pacote>` (dev: `uv add --dev <pacote>`). Sempre commitar `uv.lock`.
   - Uma linha: "Migrações e Postgres de teste: ainda não existem (PRs 05 e 06)."
10. Rode os critérios de pronto e commite em conventional commits (`chore: bootstrap python env and ci`).

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv sync --locked` | Termina com código 0, sem "lockfile needs to be updated" |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `N files already formatted` e código 0 |
| `uv run pytest` | `1 passed` |
| `uv run python -c "import ingestion, flows; print('ok')"` | `ok` |
| `git ls-files uv.lock .python-version` | As duas linhas |
| No PR aberto, `gh pr checks` | Job `lint-and-test` com `pass` |
| `grep -n "uv run pytest" AGENTS.md` | Ao menos uma linha na seção Comandos |

## 7. Testes necessários

`não`, no sentido do fluxo TDD: o test-writer não pode rodar antes de existir comando de teste (regra do `.claude/agents/test-writer.md`). A verificação que substitui é a tabela de critérios acima. O `tests/test_smoke.py` existe só para o pytest não sair com código 5 ("no tests collected") no CI; o implementador o escreve neste PR, como exceção única.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

- Toolchain aprovada pelo usuário em 2026-11-07 (P1 resolvida): uv, ruff, pytest, hatchling, Python 3.12, CI no GitHub Actions. Se o `uv` não estiver instalado no Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`.
- Os repositórios são públicos (P2 resolvida): qualquer segredo commitado, mesmo apagado depois, fica no histórico público. Se acontecer, troque o segredo; reescrever o histórico não basta. O `.gitignore` da `main` já exclui `.env`; não o enfraqueça neste PR.
- Python 3.12 foi escolhido por ser a versão do guia da ciência de dados (`docs/guia-ciencia-de-dados.md`, "Ferramentas") e por ser suportada por Prefect 3 e MLflow. Mesma versão nos dois repos evita surpresa no job de score.
- Por que uv: um binário só, gerencia a versão do Python, lockfile multiplataforma, `uv run --with` (útil no PR 44), action oficial no GitHub. Alternativas consideradas: Poetry (mais lento, não gerencia Python), pip-tools (sem gestão de Python, dois arquivos de lock).
- Por que hatchling com `packages = ["ingestion", "flows"]`: mantém a árvore de pastas do doc (pastas na raiz, não `src/`) e deixa os pacotes importáveis no venv e na imagem Docker.
- Risco: line endings no Windows. O ruff format normaliza; se o CI acusar diferença, adicionar `.gitattributes` com `* text=auto eol=lf` neste mesmo PR.

## 10. Decisões que exigem ADR

- ADR "Toolchain Python: uv, ruff, pytest, hatchling e layout de pacotes na raiz". A escolha já foi aprovada pelo usuário em 2026-11-07 (P1 resolvida); o ADR só a registra e precisa estar mergeado antes deste PR.
