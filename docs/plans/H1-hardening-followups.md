# H1: endurecimento (follow-ups de revisões anteriores)

Nome do arquivo definido pelo usuário (`H1-hardening-followups.md`), no lugar do padrão `<AAAA-MM-DD>-<slug>.md`. Plano escrito em 2026-11-08 sobre `main` em `f8cca44`.

## 1. Objetivo

Fechar cinco follow-ups pequenos de revisões anteriores: `parse_load` rejeita carga não finita, `upsert` valida `keys` e `on_conflict` antes de tocar o banco, e as checagens de clima aceitam coluna toda NULL relida como `object`.
Também: `.dockerignore` exclui `*.pem`/`*.key` em qualquer profundidade, e o ignore `S105` de `tests/test_lint_config.py` some.

## 2. Fora do escopo

- Qualquer mudança em schema de `raw` ou `ref`, migração Alembic, ou na assinatura de `build_features`, `predict` e `evaluate` (por isso não há ADR).
- Mudar a assinatura pública de `upsert` (parâmetros, tipos e retorno ficam iguais; só entram validações novas).
- Coerção de dtype em `ONS_DAILY_LOAD_SCHEMA` (`load_avg_mw` é `NOT NULL` no banco: coluna toda NULL não ocorre) e em `CALENDAR_SCHEMA`; coerção de `horizon_days`.
- Mudar o tratamento de NaN em coluna float do ONS: NaN continua sendo "carga nula" e a linha continua descartada (caso 9 de `tests/test_ons_reader.py`).
- Validar outras formas de `keys` (string solta, chave repetida, `None`).
- Outros padrões no `.dockerignore` além de `*.pem` e `*.key`; mexer no `infra/jobs/Dockerfile`.
- Rever os demais ignores de `[tool.ruff.lint.per-file-ignores]` (`tests/**`, `tests/infra/test_compose.py`, `migrations/versions/0002_roles.py`).
- Editar `.claude/`, `docs/adr/`, `docs/plans/00-indice.md` (por instrução do usuário) ou `AGENTS.md`.

## 3. Fase do roadmap

Nenhum item novo de roadmap. É endurecimento de código já entregue: itens 1 a 3 tocam a ingestão das Fases 1 e 2 de `docs/plataforma-ml.md` (Fase 2, "Clima", ainda aberta); itens 4 e 5 fecham pendências da trilha "Segurança em CI (em paralelo à Fase 2)" de `docs/plans/00-indice.md` (S1 e S4). Nada de Fase 3 em diante.

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/test_ons_reader.py` | test-writer | Casos 1 e 2 (carga não finita). |
| `tests/test_upsert_arguments.py` (criar) | test-writer | Casos 3 a 6, sem banco (o `tests/test_upsert.py` tem `pytestmark = pytest.mark.db` no módulo inteiro; ver D7). |
| `tests/test_checks_weather_forecast.py` | test-writer | Casos 7 e 8. |
| `tests/test_checks_weather_observed.py` | test-writer | Casos 9 a 11. |
| `tests/test_job_weather_observed.py` | test-writer | Caso 12 (`db`), cenário real de releitura. |
| `tests/infra/test_jobs_image.py` | test-writer | Casos 13 a 15 (nova função de checagem e política do `.dockerignore`). |
| `tests/test_lint_config.py` | test-writer | Renomear `PASSWORD_SNIPPET` (D6) e caso 16. A renomeação é em arquivo de teste: cabe ao test-writer, não ao implementer. |
| `ingestion/ons.py` | implementer | Rejeitar valores não finitos em `_normalize_load`. |
| `ingestion/db.py` | implementer | Validar `keys` e `on_conflict` no início de `upsert`. |
| `ingestion/checks.py` | implementer | `coerce=True` nas cinco colunas de variáveis de clima. |
| `.dockerignore` | implementer | `**/*.pem` e `**/*.key` no lugar de `*.pem` e `*.key`. |
| `pyproject.toml` | implementer | Tirar `S105` do ignore de `tests/test_lint_config.py` e ajustar o comentário. |

## 5. Passos

Estado atual relevante (copiado do repo em `f8cca44`):

`ingestion/ons.py`, linhas 37 a 50:

```python
def _normalize_load(series: pd.Series) -> pd.Series:
    """Return the load as float64; blank text becomes null, other bad text raises."""
    if pd.api.types.is_numeric_dtype(series):
        return series.astype("float64")
    text = series.astype("object").map(
        lambda value: value.strip() if isinstance(value, str) else value
    )
    text = text.map(lambda value: None if value == "" else value)
    numbers = pd.to_numeric(text, errors="coerce")
    bad = numbers.isna() & text.notna()
    if bad.any():
        values = sorted(set(text[bad]))[:_MAX_REPORTED_VALUES]
        raise ValueError(f"non-numeric values in {_LOAD_COLUMN}: {values}")
    return numbers.astype("float64")
```

Hoje `"nan"` em texto já é rejeitado (vira NaN com texto não nulo; caso 23). Mas `pd.to_numeric("inf")` devolve `inf`, que passa; e coluna float64 com `inf`/`-inf` passa direto. O valor chega ao `upsert`, o Postgres (`double precision`) aceita `Infinity`, e só a checagem pandera depois da gravação (`in_range(0, 100000)`) falha: a linha ruim já ficou em `raw.ons_daily_load`.

`ingestion/db.py`, início de `upsert` (linhas 50 a 56):

```python
    schema, separator, name = table.partition(".")
    if not separator or not schema or not name or "." in name:
        raise ValueError(f"table must be 'schema.table', got {table!r}")
    if rows.empty:
        return 0

    reflected = sqlalchemy.Table(name, sqlalchemy.MetaData(schema=schema), autoload_with=conn)
```

Hoje `on_conflict` inválido (ex.: `"replace"`) cai silenciosamente no `else` e vira `ON CONFLICT DO NOTHING` (linhas 85 a 88). `keys=[]` não é validado; a reflexão (que toca o banco) acontece antes de qualquer checagem de `keys`.

`ingestion/checks.py`, linhas 41 a 56:

```python
def _temperature() -> pa.Column:
    return pa.Column(float, pa.Check.in_range(-10, 50), nullable=True)

def _weather_variable_columns() -> dict[str, pa.Column]:
    return {
        "temp_max": _temperature(),
        "temp_min": _temperature(),
        "precip_mm": pa.Column(float, pa.Check.ge(0), nullable=True),
        "wind_speed_max": pa.Column(float, pa.Check.ge(0), nullable=True),
        "humidity_mean": pa.Column(float, pa.Check.in_range(0, 100), nullable=True),
    }
```

Usado por `WEATHER_FORECAST_SCHEMA` e `WEATHER_OBSERVED_SCHEMA`. Os jobs (`ingestion/jobs.py`) releem com `pd.read_sql_query(...)`; uma coluna `double precision` toda NULL no intervalo volta como `object` (só `None`) e o pandera reprova o dtype, embora os dados sejam válidos.

`.dockerignore` (completo hoje): `.git`, `.venv`, `**/.env`, `**/.env.*`, `**/__pycache__`, `**/*.pyc`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.claude`, `docs`, `tests`, `node_modules`, `*.pem`, `*.key`. No `.dockerignore`, `*.pem` só casa na raiz do contexto; `**/*.pem` casa na raiz e em qualquer subpasta (mesma lógica já usada em `**/.env`).

`pyproject.toml`, trecho:

```toml
# the test deliberately feeds a fake password literal to ruff to prove S105 still fires
# in tests, and runs ruff through subprocess with a fixed argv
"tests/test_lint_config.py" = ["S105", "S603"]
```

O `S105` só dispara em `tests/test_lint_config.py`, linha 18, `PASSWORD_SNIPPET = 'password = "hunter2"\n'`: a regra olha o nome do alvo da atribuição (`PASSWORD_...`), não o conteúdo da string. Renomeando a constante para um nome sem `password`/`pass`/`pwd`/`token`/`secret`, o ignore deixa de ser necessário. O `S603` continua (o `subprocess.run` com argv não literal).

Passos:

1. (test-writer) Criar branch a partir de `main`. Escrever os casos 1 a 16 da seção 8 nos arquivos da seção 4. Em `tests/test_lint_config.py`, renomear `PASSWORD_SNIPPET` para `CREDENTIAL_SNIPPET` (todas as ocorrências: definição e `test_hardcoded_password_is_reported_in_flows`/`_in_tests`) e acrescentar o caso 16.
2. (test-writer) Rodar `uv run pytest -m "not db"` e o caso 12 com Postgres de teste (`docker compose -f infra/docker-compose.dev.yml up -d`, depois `uv run pytest tests/test_job_weather_observed.py`). Confirmar vermelho nos casos que dependem de produção (lista na seção 9, R1) e registrar quais parametrizações já passam (caracterização). Rodar `uv run ruff check .` e `uv run ruff format --check .` (devem passar; o ignore de `S105` ainda existe nesta etapa).
3. (implementer) `ingestion/ons.py`: em `_normalize_load`, depois de obter os floats (nos dois caminhos: numérico e texto), rejeitar qualquer valor infinito (`inf`/`-inf`) com `ValueError` cuja mensagem contém `val_cargaenergiamwmed` e até `_MAX_REPORTED_VALUES` valores ofensores, ex. `non-finite values in val_cargaenergiamwmed: ['inf']`. NaN em coluna numérica continua sendo nulo (descartado depois por `dropna`). No caminho de texto, reportar o texto original.
4. (implementer) `ingestion/db.py`: logo depois da validação de `table` e antes de `if rows.empty: return 0`, levantar `ValueError` se `keys` estiver vazio (mensagem contém `keys`, ex. `keys must name at least one column`) e se `on_conflict not in ("update", "ignore")` (mensagem contém `on_conflict` e o valor recebido em `repr`, ex. `on_conflict must be 'update' or 'ignore', got 'replace'`). Nada disso pode usar `conn`. Não mudar a assinatura.
5. (implementer) `ingestion/checks.py`: acrescentar `coerce=True` às cinco colunas de `_temperature()`/`_weather_variable_columns()`. Manter `float`, os `Check` e `nullable=True` como estão. Não ligar `coerce` no nível do `DataFrameSchema`.
6. (implementer) `.dockerignore`: trocar `*.pem` por `**/*.pem` e `*.key` por `**/*.key` (D5).
7. (implementer) `pyproject.toml`: `"tests/test_lint_config.py" = ["S603"]`, com comentário só sobre o subprocess, ex. `# runs ruff through subprocess with a fixed argv`.
8. (implementer) Rodar `uv run ruff format .`, `uv run ruff check .`, `uv run pytest -m "not db"` e, com o Postgres de teste, `uv run pytest`. Tudo verde.
9. `code-reviewer`, depois o PR (toca código e `pyproject.toml`: passa por `code-reviewer` e `pr-reviewer`).

## 6. Critérios de pronto

- `uv run ruff check .` → `All checks passed!`
- `uv run ruff format --check .` → termina com código 0 (`... files already formatted`).
- `uv run pytest -m "not db"` → todos passam, nenhum `failed`.
- `uv run pytest` (com `docker compose -f infra/docker-compose.dev.yml up -d`) → todos passam, nenhum `failed`.
- `uv run pytest tests/test_upsert_arguments.py` sem Postgres no ar → passa (prova que a validação não toca o banco).
- `uv run pytest tests/infra/test_jobs_image.py tests/test_lint_config.py` → passa.
- `Select-String -Path .dockerignore -Pattern '^\*\*/\*\.(pem|key)$'` (PowerShell) → duas linhas: `**/*.pem` e `**/*.key`.
- `Select-String -Path pyproject.toml -Pattern 'test_lint_config.py'` → `"tests/test_lint_config.py" = ["S603"]`.
- `git diff --stat main` → só os arquivos da seção 4 (nenhum em `migrations/`, `docs/adr/`, `.claude/`).

## 7. Testes necessários

sim: os itens 1 a 3 mudam lógica de produção; os itens 4 e 5 mudam config guardada por testes de política já existentes (`tests/infra/test_jobs_image.py`, `tests/test_lint_config.py`).

## 8. Casos de teste

Rede de caracterização existente (deve continuar verde): `tests/test_ons_reader.py` casos 9 (NaN float descartado) e 23 (`"nan"`, `"abc"`, `"12,5"` em texto rejeitados); `tests/test_upsert.py` inteiro (`db`); `tests/test_checks_weather_forecast.py` e `tests/test_checks_weather_observed.py` inteiros (faixas, nulos parciais, `temp_min <= temp_max`); `tests/infra/test_jobs_image.py::test_dockerignore_*`; `tests/test_lint_config.py::test_hardcoded_password_is_reported_in_tests` e `::test_repository_passes_ruff_check_with_project_configuration`.

Novos (16):

ONS, `tests/test_ons_reader.py` (sem banco; usar os helpers `_text_two_days`, `_text_frame`, `_frame`, `_grid`, `_to_parquet` e a fixture `text_dtype` que já existem):

1. Parquet com a carga em texto (`object` e `str`) onde uma linha tem `"inf"`, `"-inf"`, `"+inf"` ou `"Infinity"` → `parse_load` levanta `ValueError` cuja mensagem contém `val_cargaenergiamwmed`. Para `"inf"`, a mensagem também contém `inf`.
2. Parquet com a carga em float64 onde uma linha tem `float("inf")` ou `float("-inf")` → `ValueError` com `val_cargaenergiamwmed` na mensagem.

`upsert`, `tests/test_upsert_arguments.py` (sem marcador `db`; `conn` é um dublê que registra qualquer acesso de atributo e falha se for usado; as linhas são um DataFrame `k1, k2, value` como em `tests/test_upsert.py`, tabela `"raw.upsert_test"`):

3. `keys=[]` com DataFrame não vazio → `ValueError` com `keys` na mensagem; o dublê não registrou nenhum acesso.
4. `keys=[]` com DataFrame vazio → `ValueError` (não devolve `0`); dublê intocado.
5. `on_conflict` em `"replace"`, `"UPDATE"`, `""` e `None` com DataFrame não vazio e `keys` válidas → `ValueError` com `on_conflict` e o valor recebido na mensagem; dublê intocado.
6. `on_conflict="replace"` com DataFrame vazio → `ValueError`; dublê intocado.

Checagens, sem banco:

7. `tests/test_checks_weather_forecast.py`: frame válido de 28 linhas com `humidity_mean` (e, em outra parametrização, `temp_max` e `temp_min` juntas) trocada por coluna `object` só com `None` → `check(frame, WEATHER_FORECAST_SCHEMA, expected_rows=28)` não levanta.
8. `tests/test_checks_weather_forecast.py`: `temp_max` como coluna `object` com `None` em todas as linhas menos uma, que vale `51.0` → `CheckFailed` com `temp_max` na mensagem (a coerção não afrouxa a faixa).
9. `tests/test_checks_weather_observed.py`: frame válido (`_valid_frame()`) com cada uma das cinco variáveis, uma por vez, trocada por coluna `object` só com `None` → `check_weather_observed` não levanta.
10. `tests/test_checks_weather_observed.py`: `humidity_mean` como coluna `object` com `None` e um único `101.0` → `CheckFailed` com `humidity_mean` na mensagem.
11. `tests/test_checks_weather_observed.py`: `precip_mm` como coluna `object` com um valor `"abc"` e o resto `None` → `CheckFailed` (não `TypeError` nem outra exceção) com `precip_mm` na mensagem.

Job, `tests/test_job_weather_observed.py` (marcador `db`):

12. Fonte simulada (`Source` com `_answer(...)`) que devolve `relative_humidity_2m_mean` nulo em todos os dias do intervalo para todas as localidades, demais variáveis normais → `ingest_weather_observed` devolve `40`, não levanta, e as 40 linhas gravadas têm `humidity_mean` NULL. Usar uma mutação nova, ex. "zera uma variável em todos os dias", no estilo de `_null_last_days`.

`.dockerignore`, `tests/infra/test_jobs_image.py` (nova função de checagem separada de `dockerignore_problems`, ver D5, ex. `key_material_problems(text) -> list[str]`):

13. Política: o `.dockerignore` real passa na nova checagem (contém `**/*.pem` e `**/*.key`).
14. A checagem aceita `"**/*.pem\n**/*.key\n"` e `"# keys\n**/*.key\n**/*.pem\n"`.
15. A checagem rejeita `"*.pem\n*.key\n"` (só raiz), `"**/*.pem\n"` (falta `.key`) e `"**/*.key\n"` (falta `.pem`).

Lint, `tests/test_lint_config.py`:

16. A entrada `per-file-ignores` de `tests/test_lint_config.py` em `pyproject.toml` não contém `S105` (lida por `load_ruff_lint_config()`, que já existe).

## 9. Riscos e perguntas em aberto

- R1. Quais casos devem nascer vermelhos: 1 (ao menos `"inf"`), 2, 3, 5 (ao menos `"replace"`, que hoje vira `DO NOTHING`), 4, 6, 7, 9, 10, 11, 12, 13 e 16. O caso 8 pode já ficar vermelho por dtype em vez de faixa; ele vale como guarda depois da coerção. Algumas parametrizações do caso 1 (ex. `"Infinity"`, se o `pd.to_numeric` não o reconhecer) já passam hoje como "não numérico": tudo bem, o teste afirma só `ValueError` com o nome da coluna. Os casos 14 e 15 testam a função nova e nascem vermelhos por ela não existir.
- R2. Caso 12 supõe que `pd.read_sql_query` (pandas 3, psycopg 3) devolve `object` para `double precision` toda NULL. Se o test-writer vir o caso verde antes da implementação, registrar isso no PR: o caso fica como guarda e o vermelho do item 3 é dado pelos casos 7, 9, 10 e 11.
- R3. Com `coerce=True`, um valor não conversível vira falha de coerção reportada pelo pandera (`coerce_dtype('float64')`) dentro do mesmo `CheckFailed`, com o nome da coluna. O `_describe` atual já monta a mensagem a partir de `failure_cases`; o caso 11 confirma.
- R4. Validar `keys`/`on_conflict` antes de `rows.empty` muda um comportamento: chamada com DataFrame vazio e argumento inválido passa a levantar. Nenhum chamador atual (`ingestion/jobs.py`) passa `keys=[]` ou `on_conflict` fora de `"update"`/`"ignore"`.
- R5. O índice `docs/plans/00-indice.md` não ganha a linha H1, por instrução do usuário. Fica para o usuário decidir se registra depois.
- P1. Nenhuma pergunta bloqueante.

Decisões tomadas, com recomendação (o usuário pode trocar antes do test-writer):

- D1. Carga não finita no ONS: **recomendado** rejeitar o arquivo inteiro com `ValueError`, como já acontece com texto não numérico. Alternativa: descartar a linha como nula (rejeitada: esconderia erro da fonte e abriria lacuna sem aviso).
- D2. NaN em coluna float do ONS continua significando "nulo, descartar" (comportamento atual, caso 9); só `±inf` passa a ser rejeitado. **Recomendado** manter.
- D3. Validação de `keys` e `on_conflict` antes do atalho `rows.empty`: **recomendado**, porque é erro de programação e não depende dos dados.
- D4. Coerção no schema (`coerce=True` nas cinco colunas) em vez de `dtype=` no `pd.read_sql_query` dos jobs: **recomendado** no schema, porque protege qualquer chamador da checagem e mantém os jobs como estão. Coerção só nas colunas de variáveis, não no `DataFrameSchema` inteiro.
- D5. `.dockerignore`: **recomendado** substituir `*.pem`/`*.key` por `**/*.pem`/`**/*.key` (o `**/` também casa na raiz), e testar com função nova (`key_material_problems`) em vez de ampliar `dockerignore_problems`, para não editar os exemplos positivos existentes de `test_dockerignore_check_accepts_deep_env_patterns`.
- D6. `S105`: **recomendado** renomear `PASSWORD_SNIPPET` para `CREDENTIAL_SNIPPET` e remover `S105` do ignore. O conteúdo da string (`'password = "hunter2"\n'`) não muda, então `test_hardcoded_password_is_reported_in_tests` continua provando que `S105` dispara em testes.
- D7. Testes de argumentos do `upsert` em arquivo novo sem `db` (`tests/test_upsert_arguments.py`): **recomendado**, porque `tests/test_upsert.py` marca o módulo todo com `db` e o objetivo é justamente provar que nada toca o banco.

## 10. Decisões que exigem ADR

Nenhuma. Não muda schema de `raw`/`ref`, não muda a assinatura de `build_features`, `predict` ou `evaluate`, não publica porta nem expõe serviço. A assinatura de `upsert` fica igual; o `.dockerignore` e os ignores do ruff seguem as políticas já registradas (plano 11 e ADR 0006).
