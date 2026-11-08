# S4: regra `S` (flake8-bandit) do ruff

## 1. Objetivo

Ligar a regra `S` (flake8-bandit) do ruff em todo o repositório, como lint de segurança Python decidido no ADR 0006 no lugar do bandit.
Cada achado é corrigido no código ou ignorado em `[tool.ruff.lint.per-file-ignores]` do `pyproject.toml`, restrito a caminho e regra, com motivo; nunca por `noqa`.

## 2. Fora do escopo

- Pin por SHA das actions, `permissions` no `ci.yml`, digests de imagem (item S1).
- `dependabot.yml`, `SECURITY.md` (S2); workflow `security.yml` com zizmor, dependency-review e Trivy (S3); Settings do GitHub e checks required (S5).
- Instalar o bandit, Semgrep ou qualquer outro SAST (rejeitados no ADR 0006).
- Novo job ou passo no CI: a regra `S` entra pelo `uv run ruff check .`, que o `ci.yml` já roda (linha `- run: uv run ruff check .`).
- Ligar outras famílias do ruff (`BLE`, `TRY`, `PT` etc.) ou mudar `line-length`/`target-version`.
- Reescrever SQL de testes para parâmetros ligados só para agradar a `S608` (ver decisão D2).
- Editar migrações já aplicadas em produção (ver decisão D3).

## 3. Fase do roadmap

"Segurança em CI (pós-Fase 2)", item S4 de `docs/plans/00-indice.md` (fase própria decidida no ADR 0006; não existe em `docs/plataforma-ml.md`). Depende de S1. O ADR 0006, item 12 da Decisão, manda implementar "depois da Fase 2", em quatro PRs, sendo este o quarto: "(4) regra `S` do `ruff`". Ver pergunta em aberto P1 sobre a ordem.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `tests/test_lint_config.py` (criar, pelo `test-writer`) | Teste vermelho: prova pela configuração efetiva do ruff que a regra `S` vale no código de produção e que os ignores ficam restritos aos caminhos previstos. |
| `pyproject.toml` | Acrescentar `"S"` em `[tool.ruff.lint].select` e criar `[tool.ruff.lint.per-file-ignores]` com um comentário de motivo acima de cada entrada. |
| `AGENTS.md` | Uma linha em "Regras de código" registrando a política de ignores (decisão D5). Hoje a regra "sem `noqa`" não está escrita no `AGENTS.md`; só aparece em `docs/plans/06-alembic-e-schemas.md`, linha 147. |
| Código de produção em `ingestion/`, `flows/`, `migrations/` | Só se a medição do passo 2 achar algo que não esteja previsto aqui. A varredura por Grep não achou candidato em `ingestion/` nem em `flows/` (ver passo 2). |

Estado atual de `pyproject.toml` (trecho relevante, completo):

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
# docs/ holds Portuguese prose with illustrative code blocks, not code to format
extend-exclude = ["docs"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

O ruff está em `[dependency-groups].dev` (`"ruff>=0.17.4"`), travado no `uv.lock`; o pacote expõe `python -m ruff` (há `ruff/__main__.py` no `.venv`).

## 5. Passos

1. Partir da `main` atualizada. Rodar `uv sync` para garantir o ruff do `uv.lock`.
2. **Medir os achados reais**, sem mudar nada ainda:
   - `uv run ruff check --select S --statistics .` (contagem por código).
   - `uv run ruff check --select S --output-format concise .` (arquivo e linha de cada achado).
   - Guardar as duas saídas para o corpo do PR (evidência).
   - O `--select S` na linha de comando substitui o `select` do projeto; é só para medir.
   Previsão feita por Grep nos fontes (o implementador confirma ou corrige com a medição):

   | Código | Onde é provável | Por quê |
   | --- | --- | --- |
   | `S101` (assert) | `tests/**` (praticamente todo arquivo) | pytest usa `assert` nu. Nenhum `assert` em `ingestion/`, `flows/` ou `migrations/`. |
   | `S608` (SQL montado por string) | `tests/test_upsert.py`, `tests/test_permissions.py`, `tests/test_raw_*.py`, `tests/test_ref_*.py`, `tests/test_calendar.py` (`select_day.format(...)`), `tests/test_job_weather_forecast.py` (linha 118), `tests/test_job_ons_load.py` | f-strings `f"SELECT ... FROM {TABLE}"`, `f"INSERT INTO {schema}.x ..."`, `f"UPDATE {schema}.x SET ..."` com constantes do próprio teste. |
   | `S608` | `migrations/versions/0002_roles.py`, linhas 42 a 45 | `"DO $$ BEGIN " f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN " ...`, com `role` vindo da constante `ROLES`. Os demais `op.execute(f"GRANT/REVOKE/ALTER ...")` e o `0001_schemas.py` (`CREATE/DROP SCHEMA`) provavelmente não casam com o padrão da `S608` (que procura `SELECT ... FROM`, `INSERT ... VALUES`, `UPDATE ... SET`, `DELETE FROM`). |
   | `S603` (subprocess) | `tests/test_cli.py` linha 100 (`[sys.executable, "-m", "ingestion", "--help"]`), `tests/infra/test_compose.py` linha 249 (`["git", "ls-files", "infra/.env"]`) | Chamada a `subprocess.run` com argv fixo. |
   | `S607` (executável por caminho parcial) | `tests/infra/test_compose.py` linha 249 | `"git"` resolvido pelo `PATH`. |
   | `S104` (bind em todas as interfaces) | `tests/infra/test_compose.py` (linhas 291, 309, 310, 353, 585 e vizinhas) | Literais `"0.0.0.0"` e `"::"` usados como entrada que os checadores de compose devem rejeitar. Strings como `"tcp://0.0.0.0:5432"` em `tests/infra/test_tailscale_serve.py` provavelmente não disparam (a regra olha o literal inteiro). |
   | `S108` (arquivo temporário fixo) | provavelmente nenhum | `/tmp` só aparece no meio de strings de Dockerfile/crontab em `tests/infra/test_jobs_image.py` e `tests/infra/test_crontab.py`. |
   | `S105`/`S106`/`S107` (senha fixa) | provavelmente nenhum | Grep por nomes `password/token/secret/pwd` atribuídos a literal não achou nada; `SECRET_NAME_MARKERS` e `SECRET_KEY_MARKERS` são tuplas; `hide_password=False` é booleano. |
   | `S113`, `S311`, `S324`, `S301`, `S506`, `S110` | nenhum | Sem `random`, `hashlib`, `pickle`, `yaml.load`, `try/except/pass`. `httpx.Client` em `ingestion/cli.py` já passa `timeout=30`/`timeout=60`. |

3. **Classificar cada achado medido** com esta regra, nesta ordem:
   1. Em `ingestion/` ou `flows/` (código de produção): **corrigir o código**. Nunca ignorar por arquivo em produção sem aprovar com o usuário (pergunta em aberto). Rodar os testes que cobrem o arquivo antes e depois da correção (ver seção 7).
   2. Em `migrations/versions/` já aplicada: ignorar só aquele arquivo e só aquele código (decisão D3).
   3. Em `tests/`: ignorar, com o glob mais estreito que cubra os achados reais. `S101` e `S608` em `tests/**` (difusos); `S603`, `S607` e `S104` só nos arquivos onde aparecem.
   4. Achado não previsto na tabela do passo 2: parar e registrar no PR, com a proposta de correção ou de ignore, antes de seguir.
4. Rodar o `test-writer` (antes da implementação): ele cria `tests/test_lint_config.py` com os casos da seção 8 e mostra que falham pelo motivo certo (os casos 1, 3, 5, 6, 7 e 9 falham porque a regra `S` não está ligada; os de "não reporta" passam já no vermelho, e isso é esperado). O próprio teste chama `subprocess`, então o seu arquivo entra no ignore de `S603` (passo 5).
5. Editar `pyproject.toml`:
   - `select = ["E", "F", "I", "B", "UP", "S"]`.
   - Criar `[tool.ruff.lint.per-file-ignores]` logo abaixo de `[tool.ruff.lint]`, um comentário em inglês acima de cada entrada. Forma esperada (ajustar à medição do passo 2: remover a entrada cujo achado não existir, nunca alargar um glob sem achado que justifique):

   ```toml
   [tool.ruff.lint.per-file-ignores]
   # pytest relies on bare assert; SQL in tests is built from test constants, never external input
   "tests/**" = ["S101", "S608"]
   # fixed argv built by the test itself (sys.executable, git, ruff)
   "tests/test_cli.py" = ["S603"]
   "tests/test_lint_config.py" = ["S603"]
   # git is looked up on PATH on purpose: the test must run on any developer machine and on CI
   "tests/infra/test_compose.py" = ["S603", "S607", "S104"]
   # applied migration; role names come from the ROLES constant, and rewriting an applied
   # migration is riskier than the finding
   "migrations/versions/0002_roles.py" = ["S608"]
   ```

   - Se o mesmo arquivo casar com mais de um glob, o ruff soma os ignores; não repetir `S101`/`S608` nas entradas por arquivo.
6. Se a medição achou algo em `ingestion/` ou `flows/`, corrigir o código conforme o passo 3.1.
7. Acrescentar ao `AGENTS.md`, seção "Regras de código", uma linha (decisão D5), por exemplo: "Lint de segurança pela regra `S` do ruff (ADR 0006). Achado se corrige no código; ignore só em `[tool.ruff.lint.per-file-ignores]` do `pyproject.toml`, restrito a caminho e regra, com comentário de motivo. Nunca `noqa`."
8. Rodar `uv run ruff format .` e depois todos os comandos da seção 6.
9. No corpo do PR (em inglês): a saída do passo 2, a tabela final "código, caminho, corrigido ou ignorado, motivo" e a saída dos comandos da seção 6.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `N files already formatted`, sem `Would reformat` |
| `uv run ruff check --isolated --select I --config "lint.isort.known-first-party=['ingestion','tests']" .` | `All checks passed!` |
| `uv run pytest tests/test_lint_config.py` | todos `passed`, nenhum `failed` nem `skipped` |
| `uv run pytest -m "not db"` | nenhum `failed` |
| `docker compose -f infra/docker-compose.dev.yml up -d` seguido de `uv run pytest` | nenhum `failed` (os testes `db` falham, não pulam, sem Postgres: ver `tests/conftest.py`) |
| `git grep -n "noqa" -- "*.py"` | nenhuma linha (código de saída 1) |
| `git diff main --stat` | só `pyproject.toml`, `AGENTS.md`, `tests/test_lint_config.py` e, se a medição exigiu, arquivos de produção listados no PR |

No CI, o passo `uv run ruff check .` do job `lint-and-test` passa a aplicar a regra `S` sem mudança no `ci.yml`.

## 7. Testes necessários

sim: a configuração de lint muda o que é aceito no repositório, e o comportamento "a regra `S` vale em produção e os ignores não vazam" precisa de um teste vermelho que o prenda.

Se o passo 6 mudar código de produção, a rede são os testes existentes do arquivo tocado: `ingestion/db.py` em `tests/test_upsert.py` e `tests/test_db.py`; `ingestion/http.py` em `tests/test_http.py`; `ingestion/cli.py` em `tests/test_cli.py`; `ingestion/jobs.py` em `tests/test_job_weather_forecast.py` e `tests/test_job_ons_load.py`; `ingestion/openmeteo.py` em `tests/test_openmeteo_forecast.py` e `tests/test_openmeteo_observed.py`; `ingestion/ons.py` em `tests/test_ons_reader.py`; `ingestion/checks.py` em `tests/test_checks_weather_forecast.py` e `tests/test_checks_ons_load.py`; `ingestion/calendar_ref.py` em `tests/test_calendar.py`; migrações em `tests/test_migrations.py` e `tests/test_permissions.py`. Rodar antes (verde) e depois (verde).

## 8. Casos de teste

Recomendação de forma (o `test-writer` decide os detalhes): cada caso passa um trecho de código ao ruff com a configuração do projeto, pela entrada padrão, informando um caminho fictício, e lê os códigos reportados. Comando sugerido, com `cwd` na raiz do repositório: `[sys.executable, "-m", "ruff", "check", "--output-format", "json", "--stdin-filename", "<caminho>", "-"]`, `check=False` (o ruff sai com 1 quando há achado), lendo `code` de cada item do JSON. Não passar `--select` nem `--isolated`, senão o teste deixa de medir a configuração do projeto. Considerar só os códigos que começam com `S`. O caminho fictício não precisa existir. Antes de fixar cada trecho, o `test-writer` confirma com `--select S` que ele dispara o código esperado na versão travada do ruff; se não disparar, troca o trecho, não o caso.

Caminhos fictícios sugeridos: `ingestion/lint_probe.py`, `flows/lint_probe.py`, `migrations/versions/9999_lint_probe.py`, `tests/test_lint_probe.py`, `tests/infra/test_lint_probe.py`.

1. Código de produção com `assert`: trecho `def f(x):\n    assert x\n` em `ingestion/lint_probe.py` → reporta `S101`.
2. Teste com `assert`: o mesmo trecho em `tests/test_lint_probe.py` → não reporta `S101`.
3. SQL por f-string em produção: `def q(table):\n    return f"SELECT a FROM {table}"\n` em `ingestion/lint_probe.py` → reporta `S608`.
4. SQL por f-string em teste: o mesmo trecho em `tests/test_lint_probe.py` → não reporta `S608`.
5. O ignore da migração não vaza: o trecho do caso 3 em `migrations/versions/9999_lint_probe.py` → reporta `S608`.
6. Senha fixa vale também em teste: `password = "hunter2"\n` em `flows/lint_probe.py` → reporta `S105`; o mesmo em `tests/test_lint_probe.py` → reporta `S105` (prova que os testes não ignoram a família `S` inteira).
7. Bind em todas as interfaces: `HOST = "0.0.0.0"\n` em `ingestion/lint_probe.py` → reporta `S104`; o mesmo em `tests/infra/test_lint_probe.py` → reporta `S104` (o ignore de `S104` é só de `tests/infra/test_compose.py`).
8. Subprocess em teste qualquer: `import subprocess\nimport sys\n\nsubprocess.run([sys.executable, "-V"], check=False)\n` em `tests/test_lint_probe.py` → reporta `S603` (o ignore é por arquivo, não de `tests/**`).
9. Subprocess em produção: o trecho do caso 8 em `ingestion/lint_probe.py` → reporta `S603`.
10. Guarda da configuração (lê `pyproject.toml` com `tomllib`):
    - `"S"` está em `tool.ruff.lint.select` → verdadeiro.
    - Nenhum valor em `tool.ruff.lint.per-file-ignores` é a família inteira (`"S"`) nem um código fora de `S` seguido de dígitos → verdadeiro.
    - Nenhuma chave de `per-file-ignores` cobre o repositório inteiro (`"*"`, `"**"`, `"**/*.py"`, `"*.py"`) nem começa com `ingestion/` ou `flows/` → verdadeiro.
11. Repositório limpo: `ruff check .` com a configuração do projeto, a partir da raiz → código de saída 0. (Opcional: duplica o CI; o `test-writer` pode omitir se preferir não rodar o lint inteiro dentro do pytest.)

No vermelho (antes do passo 5) os casos 1, 3, 5, 6, 7, 9 e o primeiro item do 10 falham; os casos 2, 4 e 8 passam por vacuidade, o que é esperado e não invalida o vermelho.

## 9. Riscos e perguntas em aberto

- **P1, ordem (pergunta ao usuário).** O ADR 0006 manda implementar depois da Fase 2 e o índice põe S4 dependendo de S1. Hoje a Fase 2 está em andamento (plano 26 aberto) e o `ci.yml` ainda usa tags (`actions/checkout@v7`, `astral-sh/setup-uv@v10.3.3`), ou seja, S1 não entrou. Recomendação: não iniciar a implementação antes de a Fase 2 fechar e S1 estar na `main`; a dependência de S1 é só de ordem (S4 não toca o `ci.yml`), então se o usuário quiser antecipar, basta registrar a exceção no índice.
- **P2, achado em produção não previsto.** Se a medição achar algo em `ingestion/` ou `flows/` que não se corrige sem mudar comportamento, o implementador para e pergunta; não cria ignore em produção por conta própria.
- **Risco: semântica de regra por versão do ruff.** O que dispara `S603`, `S608` e `S104` varia entre versões (por exemplo, versões recentes do ruff deixam de reportar `S603` quando o argv é todo literal). Mitigação: a medição do passo 2 manda, e os trechos dos casos de teste são conferidos na versão travada. Um bump do ruff pelo Dependabot (S2) pode fazer surgir achados novos; aí o CI fica vermelho e o ajuste é um PR próprio.
- **Risco: ignores por arquivo ficam velhos.** Se um arquivo listado for renomeado, a entrada morre em silêncio e o achado volta como erro (falha segura). O ruff não avisa ignore sem uso por arquivo; não há como travar isso sem `RUF100`, que trata de `noqa`, não de `per-file-ignores`.
- **Risco: `S608` difuso em `tests/**`.** Esconde SQL montado por string em teste futuro. Aceito porque os testes só usam constantes próprias; o caso 4 documenta a escolha e o caso 3 garante que produção continua coberta.
- **Risco: o teste novo roda o ruff por subprocess.** Depende do ruff do grupo `dev`, que o CI instala com `uv sync --locked`. Não roda na imagem `jobs` (que não executa testes).

## 10. Decisões que exigem ADR

Nenhuma. A decisão de usar a regra `S` com ignores justificados já está no ADR 0006 (Alternativas, "bandit", e Decisão, item 12).

Decisões deste plano, com recomendação (o usuário aprova junto com o plano):

- **D1, forma do teste:** usar o ruff pela entrada padrão com a configuração do projeto (casos 1 a 9) mais a guarda por `tomllib` (caso 10). Recomendado: os casos 1 a 9 testam o efeito real da configuração, não a forma do TOML; a guarda cobre o que o efeito não pega (família inteira ignorada, glob que cobre tudo).
- **D2, `S608` nos testes:** ignorar em `tests/**`, sem reescrever o SQL dos testes. Recomendado: o SQL dos testes usa nomes de tabela, papel e schema do próprio teste, e identificadores não podem ir como parâmetro ligado; reescrever dezenas de consultas não reduz risco.
- **D3, `S608` em `migrations/versions/0002_roles.py`:** ignorar só esse arquivo, sem editar a migração. Recomendado: ela já está aplicada em produção, o valor interpolado vem da constante `ROLES` e mexer numa migração aplicada é mais arriscado que o achado. Migrações futuras ficam sob a regra.
- **D4, `S603`/`S607`/`S104` nos testes:** ignore por arquivo, só onde a medição achar. Recomendado em vez de `tests/**`, para que um `subprocess` novo num teste seja uma decisão explícita.
- **D5, registrar a política no `AGENTS.md`:** uma linha em "Regras de código". Recomendado: a regra "sem `noqa`" hoje só existe num plano antigo; sem a linha, o implementador de um PR futuro não a encontra. Como o PR toca `AGENTS.md` e `pyproject.toml`, passa pelo `code-reviewer` e pelo `pr-reviewer`, o que já é o caso por tocar código.
