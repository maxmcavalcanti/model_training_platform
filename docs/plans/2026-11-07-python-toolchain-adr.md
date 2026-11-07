# ADR 0002: toolchain Python e layout de pacotes

> Executa: agente (`task-implementer`). Depende de: ADR 0001 (já na `main`). Branch sugerida: `docs/python-toolchain-adr`.
> Testes necessários: não. O PR toca só `docs/**`, então dispensa `code-reviewer` e `pr-reviewer` (`AGENTS.md`, "Fluxo de trabalho"); o usuário revisa se quiser.
> **Exceção registrada por instrução expressa do usuário (2026-11-07):** neste PR o `task-implementer` escreve o ADR `docs/adr/0002-python-toolchain-and-package-layout.md`, ao contrário da regra do `AGENTS.md` ("Nenhum agente escreve ADR"). A exceção vale só para este ADR.

## 1. Objetivo

Registrar em ADR a toolchain Python e o layout de pacotes já aprovados pelo usuário (P1 de `docs/plans/00-indice.md`), exatamente como o PR 01 (`docs/plans/01-bootstrap-ambiente-dev.md`) vai implementar.
O ADR não decide nada novo: só transcreve decisões existentes; o que não estiver decidido fica de fora e vai para a seção 9 deste plano.

## 2. Fora do escopo

- Implementar o bootstrap: `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`, pacotes, `ci.yml` e a seção "Comandos" do `AGENTS.md` são do PR 01.
- Alterar `AGENTS.md`, `CLAUDE.md`, `.claude/` ou qualquer arquivo fora de `docs/adr/`.
- Editar outros planos (`00-indice.md`, `01-…`, `05-…`, `06-…`, `11-…`, `44-…`), mesmo para apontar para o ADR novo (ver Q5).
- Decidir o que o PR 01 deixou para depois: pre-commit, mypy, cobertura mínima, Dependabot, `.gitattributes` (condicional no PR 01), versão exata das actions.
- Decisões de outros ADRs: imagem Docker dos jobs (PR 11), executor `uv run --with` e versão do pacote `models` (ADR de execução, P12/P13), layout do repo `models`.

## 3. Fase do roadmap

Pré-requisito da Fase 0 de `docs/plataforma-ml.md` ("Roadmap"): o índice exige este ADR mergeado antes do PR 01 (`docs/plans/00-indice.md`, "ADRs a escrever", item 1).

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `docs/adr/0002-python-toolchain-and-package-layout.md` | Criar o ADR (nome do arquivo em inglês, prosa em português, identificadores em inglês conforme ADR 0001) |

Nenhum outro arquivo. Não existe template nem skill `generate-adr` no repo; o formato segue o ADR 0001 (`docs/adr/0001-english-naming-convention.md`): título `# ADR NNNN: …`, linhas `Status:`, `Data:`, `Decisores:` e seções `##`.

### 4.1 Fonte das decisões (copiar para o ADR, sem acrescentar nada)

Do índice (`docs/plans/00-indice.md`, "Decisões resolvidas", P1): "uv, ruff, pytest, hatchling, Python 3.12, CI no GitHub Actions, pacotes na raiz."

Do plano 01 (`docs/plans/01-bootstrap-ambiente-dev.md`, passos 2, 3, 8 e 9, e seção 9):

- `.python-version` com `3.12`.
- `pyproject.toml`:
  - `[project]`: `name = "platform"`, `version = "0.1.0"`, `requires-python = ">=3.12,<3.13"`, `dependencies = []`.
  - `[dependency-groups]`: `dev = ["pytest", "ruff", "pyyaml"]`, adicionadas com `uv add --dev` para que as versões fiquem no lock.
  - `[build-system]`: `requires = ["hatchling"]`, `build-backend = "hatchling.build"`.
  - `[tool.hatch.build.targets.wheel]`: `packages = ["ingestion", "flows"]`.
  - `[tool.ruff]`: `line-length = 100`, `target-version = "py312"`.
  - `[tool.ruff.lint]`: `select = ["E", "F", "I", "B", "UP"]`.
  - `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `addopts = "-ra --strict-markers"`, `markers = ["db: ..."]` (marcador para testes que precisam de Postgres, usado a partir do PR 05).
- `uv.lock` gerado pelo uv e commitado; toda dependência nova entra por `uv add <pacote>` (dev: `uv add --dev <pacote>`), sempre commitando `uv.lock`.
- Layout: pacotes na raiz do repo, sem `src/`: `ingestion/` e `flows/` (árvore de `docs/plataforma-ml.md`, seção do repo `platform`), `tests/` na raiz. `migrations/` (Alembic, PR 06) e `infra/` ficam na raiz e não são pacotes do wheel.
- CI: `.github/workflows/ci.yml`, gatilhos `pull_request` e `push` na `main`, job `lint-and-test` em `ubuntu-latest`: `actions/checkout`, `astral-sh/setup-uv` com `enable-cache: true`, `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`. Actions fixadas por major, conferida no Marketplace na hora do PR 01.
- Comandos canônicos: `uv sync`; `uv run ruff check .`; `uv run ruff format --check .` (aplicar: `uv run ruff format .`); `uv run pytest`; um arquivo: `uv run pytest tests/<arquivo>.py`; um teste: `uv run pytest tests/<arquivo>.py::<test_name>`.
- Justificativas e alternativas (seção 9 do plano 01):
  - uv: um binário só, gerencia a versão do Python, lockfile multiplataforma, `uv run --with` (útil no PR 44), action oficial no GitHub. Alternativas: Poetry (mais lento, não gerencia Python) e pip-tools (sem gestão de Python, dois arquivos de lock).
  - hatchling com `packages = ["ingestion", "flows"]`: mantém a árvore do doc (pastas na raiz, não `src/`) e deixa os pacotes importáveis no venv e na imagem Docker.
  - Python 3.12: versão do guia da ciência de dados (`docs/guia-ciencia-de-dados.md`, "Ferramentas": "Python 3.12 + VS Code ou Jupyter"), suportada por Prefect 3 e MLflow; a mesma versão nos dois repos evita surpresa no job de score.
  - Risco de fim de linha no Windows: o ruff format normaliza; se o CI acusar diferença, o PR 01 adiciona `.gitattributes` com `* text=auto eol=lf`.

Usos já planejados que dependem desta toolchain (citar como consequência, sem decidir nada deles):

- PR 05: `uv add sqlalchemy "psycopg[binary]"` (passo 0) e `uv run pytest -m "not db"`.
- PR 06: `uv add alembic`; `uv run alembic upgrade head` também no CI.
- PR 11: imagem baseada em `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` (tag a conferir), `uv sync --locked --no-dev`, copiando `ingestion/`, `flows/`, `migrations/`, `alembic.ini`.
- PR 44: executor monta `uv run --frozen --with <pacote models> python -m <módulo>`; os detalhes são do ADR de execução (P12/P13).
- O repo `models` usa layout `src/models/` (`docs/plataforma-ml.md`), diferente deste repo; isso é decisão daquele repo.

## 5. Passos

1. Crie a branch `docs/python-toolchain-adr` a partir da `main` (que já tem o ADR 0001). Não edite este plano.
2. Crie `docs/adr/0002-python-toolchain-and-package-layout.md`, em português, com esta estrutura e nesta ordem:
   - `# ADR 0002: Toolchain Python e layout de pacotes`
   - `Status: Aceito`, `Data: 2026-11-07`, `Decisores: Maximiliano` (mesmo padrão do ADR 0001; ver Q1).
   - `## Contexto`: ainda não há código; todo PR seguinte precisa de lint, teste e CI reais; a decisão foi aprovada pelo usuário em 2026-11-07 (P1) e este ADR só a registra; escrito pelo `task-implementer` por instrução expressa do usuário, como exceção à regra do `AGENTS.md`, válida só para este ADR.
   - `## Decisão`, com subseções `###`: Gerenciador e lockfile (uv, `uv.lock` commitado, `uv sync --locked` no CI, `uv add`); Versão do Python (`.python-version` e `requires-python`); Backend de build e layout de pacotes (hatchling, `packages`, pacotes na raiz sem `src/`, `tests/`, `migrations/` e `infra/` fora do wheel); Lint e formatação (ruff check e ruff format, `line-length`, `target-version`, `select`); Testes (pytest e a config de `[tool.pytest.ini_options]`, marcador `db`); CI (GitHub Actions, job `lint-and-test`, passos). Use os valores da seção 4.1 literalmente, em blocos `toml` quando for config.
   - `## Comandos canônicos`: a lista da seção 4.1, dizendo que o PR 01 os grava na seção "Comandos" do `AGENTS.md`.
   - `## Consequências`: (a) todos os PRs seguintes usam os comandos canônicos, e nenhum plano usa comando que não exista no ponto em que roda; (b) dependência nova sempre por `uv add` com `uv.lock` no mesmo commit; (c) a toolchain é base dos usos já planejados nos PRs 05, 06, 11 e 44 (lista da seção 4.1), cujos detalhes continuam nos respectivos planos e ADRs; (d) mesma versão do Python (3.12) esperada no repo `models`; (e) o risco de fim de linha no Windows e a saída prevista (`.gitattributes` no PR 01, se necessário); (f) ficam fora desta decisão: pre-commit, mypy, cobertura mínima, Dependabot.
   - `## Alternativas consideradas`: Poetry e pip-tools, com os motivos da seção 4.1; layout `src/` rejeitado por divergir da árvore de `docs/plataforma-ml.md`. Não acrescente outras alternativas (ver Q3).
3. Identificadores em inglês (ADR 0001): use `platform`, `models`, `ingestion`, `flows`, `lint-and-test`, `build_engine` etc. Nada de `plataforma`/`modelos` como identificador; caminhos de `docs/` ficam como estão (`docs/plataforma-ml.md`).
4. Se durante a escrita surgir algo que não esteja na seção 4.1, não escreva no ADR: anote no corpo do PR como pergunta ao usuário.
5. Rode os critérios da seção 6 e cole comandos e saídas no corpo do PR.
6. Commit em inglês: `docs: add ADR 0002 python toolchain and package layout`. Título e corpo do PR em inglês. Abra o PR só se o usuário pedir; sem `code-reviewer` nem `pr-reviewer` (PR só de `docs/**`).

## 6. Critérios de pronto

Todos em PowerShell, na raiz do repo, na branch do PR. O repo ainda não tem comandos de lint ou teste (`AGENTS.md`, "Comandos"); só `git` é usado.

```powershell
# 1. Estrutura do ADR
git grep -n '^## ' -- docs/adr/0002-python-toolchain-and-package-layout.md

# 2. Valores do plano 01 presentes no ADR (nenhuma linha "MISSING")
$f = 'docs/adr/0002-python-toolchain-and-package-layout.md'
foreach ($s in @('hatchling.build', 'packages = [', 'ingestion', 'flows', '>=3.12,<3.13', '.python-version', 'uv.lock', 'line-length = 100', 'target-version = ', 'py312', '"E", "F", "I", "B", "UP"', 'testpaths', '-ra --strict-markers', 'lint-and-test', 'astral-sh/setup-uv', 'enable-cache', 'uv sync --locked', 'uv run ruff check .', 'uv run ruff format --check .', 'uv run ruff format .', 'uv run pytest', 'uv add --dev', 'Poetry', 'pip-tools', 'src/')) { git grep -qF -e $s -- $f; if ($LASTEXITCODE -ne 0) { "MISSING: $s" } }

# 3. Exceção registrada
git grep -n 'task-implementer' -- docs/adr/0002-python-toolchain-and-package-layout.md

# 4. Sem identificadores em português do ADR 0001
git grep -nwE 'plataforma|modelos|lint-e-testes|criar_engine' -- docs/adr/0002-python-toolchain-and-package-layout.md

# 5. Arquivos do PR
git diff --name-only main...HEAD
```

Saída esperada:

1. Exatamente, nesta ordem: `## Contexto`, `## Decisão`, `## Comandos canônicos`, `## Consequências`, `## Alternativas consideradas`.
2. Nada (nenhuma linha `MISSING:`). Se o PowerShell 5.1 corromper a string com aspas duplas `"E", "F", ...`, confira esse item à mão e registre no PR.
3. Ao menos uma linha.
4. Só linhas com o caminho `docs/plataforma-ml.md` (o `-w` casa `plataforma` dentro do nome do arquivo); nenhum uso como identificador.
5. Só `docs/adr/0002-python-toolchain-and-package-layout.md` (e este plano, se entrar no mesmo PR sem alteração).

## 7. Testes necessários

não: tarefa só de documentação (um ADR em Markdown), sem código nem mudança de comportamento; a verificação é feita pelos comandos `git grep` da seção 6.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

Riscos:

- **Divergência ADR × plano 01:** se um dos dois mudar depois, eles se contradizem. Mitigação: o critério 2 confere os valores literais; qualquer ajuste no plano 01 antes da implementação deve vir junto com ajuste no ADR.
- **ADR decidir algo novo sem querer** (versão de action, regra extra do ruff, mypy). Mitigação: passo 4.

Perguntas em aberto (o implementer não as resolve; sem resposta, segue o padrão indicado):

- **Q1.** Status `Aceito` já no PR (padrão do ADR 0001) ou `Proposto` até o merge? Padrão: `Aceito`.
- **Q2.** O nome de distribuição `platform` (`[project].name`) coincide com o módulo `platform` da stdlib. Como nenhum pacote importável se chama `platform` (o wheel tem só `ingestion` e `flows`), não há sombreamento, mas o ADR deve citar isso? Padrão: não citar, porque não está nos planos.
- **Q3.** Alternativas não documentadas nos planos (black + flake8 + isort em vez do ruff; setuptools em vez do hatchling; unittest em vez do pytest) devem entrar no ADR? Padrão: não, só Poetry, pip-tools e layout `src/`.
- **Q4.** Ajustes finos depois (trocar `select` do ruff, `line-length`, adicionar dependências de dev) exigem novo ADR ou PR normal? Os planos não dizem. Padrão: o ADR não fala disso.
- **Q5.** Atualizar `docs/plans/00-indice.md` ("ADRs a escrever", item 1) e `docs/plans/01-bootstrap-ambiente-dev.md` (seção 10) para citar o caminho do ADR 0002? Padrão: não neste PR.

## 10. Decisões que exigem ADR

- Esta tarefa **é** o ADR `docs/adr/0002-python-toolchain-and-package-layout.md`, escrito pelo `task-implementer` por instrução expressa do usuário (exceção à regra "Nenhum agente escreve ADR" do `AGENTS.md`, válida só para este ADR). Ele precisa estar mergeado antes do PR 01.
- Nenhum outro ADR é necessário.
