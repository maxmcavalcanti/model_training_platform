# 25 — Tabela `raw.weather_observed`

> Executa: agente. Depende de: nada além da `main` atual (migrações `0001` a `0006` já mergeadas; head do Alembic = `0006`). Esta tabela é a migração `0007`, com `down_revision = "0006"`. Branch sugerida: `feat/raw-weather-observed`.
> Pré-requisito: ADR 0005 (`docs/adr/0005-data-contract-v1.md`), já mergeado; ele lista o PR 25 (`raw.weather_observed`) nas "Consequências". Nenhum ADR novo é necessário (seção 10).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-08: alinhado à `main` em `0f270bd` (Fase 1 concluída por decisão do usuário em 2026-11-08; Fase 2 começa agora). Segue o padrão de `migrations/versions/0004_raw_weather_forecast.py` (restrições nomeadas, chave estrangeira para `ref.locations`, mesmas variáveis) e de `migrations/versions/0006_raw_ons_daily_load.py` (`ingestor` mantém `UPDATE`), e o estilo de `tests/test_raw_weather_forecast.py` e `tests/test_raw_ons_daily_load.py`. Os PRs 24 (cliente) e 26 (job) dependem deste; este não depende deles.

## 1. Objetivo

Criar por migração Alembic (`0007`) a tabela `raw.weather_observed`: clima diário observado (reanálise ERA5 do Open-Meteo) por local e dia, chave (`location_id`, `date`), chave estrangeira para `ref.locations`, mesmas variáveis e unidades de `raw.weather_forecast` e `ingested_at` obrigatório.
O `ingestor` mantém `UPDATE`, porque o job do PR 26 reescreve os últimos 10 dias (o ERA5 recente pode mudar); é o "real" do modelo `rain_d1` e o clima de treino do `load_d1`.

## 2. Fora do escopo

- Cliente do arquivo ERA5 (`fetch_observed`, PR 24, `docs/plans/24-cliente-observado-open-meteo.md`), job `weather-observed`, checagem pandera, CLI e crontab (PR 26, `docs/plans/26-job-clima-observado.md`), backfill desde 2015 e carga em produção (item 27).
- `CHECK` de faixa plausível nas variáveis (temperaturas −10 a 50 °C, `temp_min <= temp_max`, `precip_mm >= 0`, `wind_speed_max >= 0`, `humidity_mean` 0 a 100): fica na checagem pandera do PR 26, que roda depois de gravar (D4).
- `CHECK` de "pelo menos uma variável não nula": o PR 24 descarta antes os dias com todas as variáveis nulas (D5).
- `DEFAULT now()` em `ingested_at`: quem carimba é o `upsert` (`stamp_ingested_at=True`); faltar o carimbo deve falhar alto (`NOT NULL`), como na `0004` e na `0006`.
- Colunas além do modelo de dados (por exemplo `source`, `is_final`, `updated_at`, `first_ingested_at`): exigiriam ADR (ADR 0005, P9).
- Chave estrangeira de `date` para `ref.calendar` (mesma razão da D1 do plano 21: acoplaria jobs independentes e o calendário cobre só 2015–2030).
- Índices além da chave primária (4 linhas por dia).
- `GRANT` ou `REVOKE` explícitos: as permissões vêm só dos privilégios padrão da `0002` (D3).
- Acrescentar comentários de unidade em `raw.weather_forecast` (seria uma migração em outra tabela; ver seção 9, "Riscos").
- Alterar `migrations/versions/0001` a `0006`, `ingestion/` (inclusive `ingestion/db.py` e `ingestion/openmeteo.py`), `tests/conftest.py`, qualquer teste existente, `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `infra/`, `.claude/`, `AGENTS.md`, o ADR 0005, `docs/plataforma-ml.md` ou outros planos.
- Marcar o checkbox "`raw.weather_observed` + backfill desde 2015" do roadmap: fecha no item 27.

## 3. Fase do roadmap

Fase 2 — "Clima", item "`raw.weather_observed` + backfill desde 2015" (`docs/plataforma-ml.md`, "Roadmap"). Este PR entrega só a tabela.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `tests/test_raw_weather_observed.py` | Novo (test-writer): estrutura, restrições nomeadas, chave estrangeira, comentários, permissões (com `UPDATE` para o `ingestor`), `upsert` com `on_conflict="update"` e `downgrade`/`upgrade` |
| `migrations/versions/0007_raw_weather_observed.py` | Novo (implementer): cria `raw.weather_observed` com restrições de nome fixo e comentários; `downgrade` apaga a tabela |

Nada mais muda. Testes existentes que fazem `downgrade` a partir do `head` (`tests/test_migrations.py` até `base`, `tests/test_permissions.py` até `0001`, `tests/test_ref_locations.py` até `0002`, `tests/test_raw_weather_forecast.py` até `0003`, `tests/test_ref_calendar.py` até `0004`, `tests/test_raw_ons_daily_load.py` até `0005`) passam a reverter também a `0007` e continuam verdes sem edição: o `downgrade` da `0007` roda antes do da `0003` e apaga `raw.weather_observed`, que é a única tabela com chave estrangeira para `ref.locations` além de `raw.weather_forecast`; por isso o `DROP TABLE ref.locations` da `0003` continua funcionando. `tests/test_migrations.py` compara com o `head` dinamicamente e exige ids de 4 dígitos e head único.

### Contrato e modelo de dados

`docs/plataforma-ml.md`, "Modelo de dados":

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `raw.weather_observed` | `location_id`, `date`, `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`, `ingested_at` | (`location_id`, `date`) | Plataforma | Todos |
| `raw.weather_forecast` | `location_id`, `issued_at`, `target_date`, `horizon_days`, mesmas variáveis, `ingested_at` | (`location_id`, `issued_at`, `target_date`) | Plataforma | Todos |

`docs/plataforma-ml.md`, "Ingestão": "06:45 `ingest_weather_observed` — Upsert dos últimos 10 dias de clima observado (cobre atraso e correções da fonte)".

Fonte: `archive-api.open-meteo.com/v1/archive` (reanálise ERA5), diário desde 1940. Item 18 do mesmo doc (verificado em 2026-11-08): a consulta com `timezone=America/Sao_Paulo` devolveu as cinco variáveis não nulas inclusive no dia da consulta (atraso 0); ressalva: o valor do dia corrente provavelmente não é o dado final da reanálise; **pendente** verificar se os valores recentes mudam de um dia para o outro. Isso não muda o schema, mas é a razão de manter `UPDATE` (D3).

Mapeamento e unidades (as mesmas de `raw.weather_forecast`; o cliente valida as unidades em `ingestion/openmeteo.py`, `DAILY_UNITS`):

| Variável da API | Coluna | Unidade |
| --- | --- | --- |
| `temperature_2m_max` | `temp_max` | °C |
| `temperature_2m_min` | `temp_min` | °C |
| `precipitation_sum` | `precip_mm` | mm |
| `wind_speed_10m_max` | `wind_speed_max` | km/h |
| `relative_humidity_2m_mean` | `humidity_mean` | % |
| `time` (dia em `America/Sao_Paulo`) | `date` | — |
| (não existe) | `ingested_at` | `timestamptz` |

ADR 0005, trechos que se aplicam:

> `ingested_at` guarda o momento da **última escrita** da linha, carimbado pelo relógio do servidor no insert e, nos upserts que atualizam, também no `SET` do conflito. Não há coluna nova (nenhum `updated_at`): a "primeira entrada" não é registrada.
>
> `location_id` é texto em slug minúsculo [...] É a chave de `ref.locations` e a chave estrangeira em `raw.weather_observed` e `raw.weather_forecast` [...].
>
> O ADR cobre as tabelas dos PRs 09 (`ref.locations`), 13 (`raw.weather_forecast`), 19 (`ref.calendar`), 21 (`raw.ons_daily_load`) e 25 (`raw.weather_observed`), no que toca a estas três decisões. Os demais tipos e colunas dessas tabelas estão nos planos e em `docs/plataforma-ml.md`.
>
> `ref.locations` não tem coluna `timezone`: o dia dos dados de clima é `America/Sao_Paulo`, definido pelos jobs.

O modo "primeiro snapshot vence" (`on_conflict="ignore"`, `REVOKE UPDATE`) do ADR 0005 vale só para `raw.weather_forecast`. Esta tabela usa **`on_conflict="update"`** (D3), como `raw.ons_daily_load`.

`AGENTS.md`, "Fronteira": "Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados." Aqui: migração = `0007`; ADR = 0005 (seção 10); aviso = seção 9, "Aviso à ciência de dados", enviado pelo usuário.

`.claude/rules/migrations-e-dados.md`:

> - Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.
> - Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados. Mudança na assinatura do contrato exige ADR.
> - Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `scientist` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `reader` só lê. Toda tabela nova declara quem escreve e quem lê.
> - Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.
> - `raw.weather_forecast` guarda a previsão como emitida (`issued_at`). Nunca sobrescrever uma previsão antiga com uma nova.

A última regra **não** se aplica aqui: o observado não é previsão; é reescrito na janela recente.

### Quem escreve e quem lê

Resultado dos privilégios padrão de `migrations/versions/0002_roles.py` (válidos para tabelas criadas pelo admin que roda as migrações, `DATABASE_URL_ADMIN`), **sem** exceção nesta tabela:

| Papel | `raw.weather_observed` |
| --- | --- |
| admin (`DATABASE_URL_ADMIN`) | dono |
| `ingestor` | `SELECT`, `INSERT`, `UPDATE` (sem `DELETE`, sem `TRUNCATE`); é quem roda o job do PR 26 com `on_conflict="update"` |
| `scientist`, `scorer`, `reader` | só `SELECT` |

Trecho de `0002_roles.py`:

```python
ROLES = ("ingestor", "scientist", "scorer", "reader")
INGESTOR_SCHEMAS = "raw, ref"
...
op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {ALL_ROLES}")
...
op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schemas} GRANT INSERT, UPDATE ON TABLES TO {role}")
# (raw, ref) -> ingestor ; (predictions, monitoring) -> scorer
```

`INSERT ... ON CONFLICT DO UPDATE` exige `INSERT` e `UPDATE`. Diferença deliberada em relação à `0004`, que faz `REVOKE UPDATE ON raw.weather_forecast FROM ingestor`: aqui **não** há `REVOKE`, como na `0006`.

### Contrato do `upsert` (`ingestion/db.py`, não alterar)

```python
def upsert(
    conn: sqlalchemy.Connection,
    table: str,
    rows: pd.DataFrame,
    keys: list[str],
    *,
    on_conflict: Literal["update", "ignore"] = "update",
    stamp_ingested_at: bool = True,
) -> int:
    """Write ``rows`` into ``table`` ("schema.table") keyed by ``keys``.

    With ``on_conflict="update"`` existing rows are overwritten; with ``"ignore"`` they are
    kept untouched. When ``stamp_ingested_at`` is true, ``ingested_at`` is set to the server
    ``now()`` on insert and, in update mode, on conflict. Returns the number of rows inserted
    (plus updated, in update mode). The caller owns the transaction: nothing is committed here.
    """
```

Reflete a tabela, recusa coluna inexistente, recusa `ingested_at` no DataFrame quando carimba, converte `NaN`/`None` em `NULL`. O DataFrame do job (PR 24/26) tem `location_id, date, temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean`, sem `ingested_at`.

### Migrações de referência

`migrations/versions/0004_raw_weather_forecast.py` (trecho):

```python
CREATE TABLE raw.weather_forecast (
    location_id text NOT NULL,
    issued_at date NOT NULL,
    target_date date NOT NULL,
    horizon_days smallint NOT NULL
        GENERATED ALWAYS AS ((target_date - issued_at)::smallint) STORED,
    temp_max double precision,
    temp_min double precision,
    precip_mm double precision,
    wind_speed_max double precision,
    humidity_mean double precision,
    ingested_at timestamptz NOT NULL,
    CONSTRAINT weather_forecast_pkey
        PRIMARY KEY (location_id, issued_at, target_date),
    CONSTRAINT weather_forecast_location_id_fkey
        FOREIGN KEY (location_id) REFERENCES ref.locations (location_id),
    CONSTRAINT weather_forecast_horizon_days_range
        CHECK ((target_date - issued_at) BETWEEN 1 AND 7)
)
...
op.execute("REVOKE UPDATE ON raw.weather_forecast FROM ingestor")   # NÃO copiar
op.execute(
    "COMMENT ON COLUMN raw.weather_forecast.ingested_at IS "
    "'Server time of the last write of the row (ADR 0005).'"
)
```

`migrations/versions/0006_raw_ons_daily_load.py` (cabeçalho e estilo a espelhar):

```python
"""raw_ons_daily_load

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-08 13:00:00.000000

Creates raw.ons_daily_load: daily load from ONS, one row per subsystem and day.
Permissions come from the default privileges set by 0002; no explicit GRANT or REVOKE here.
The ingestor keeps UPDATE on purpose: ONS revises published days and the job upserts with
on_conflict="update" (ADR 0005: ingested_at is the last write).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""CREATE TABLE raw.ons_daily_load ( ... "date" date NOT NULL, ... )""")
    op.execute("COMMENT ON TABLE raw.ons_daily_load IS '...'")
    ...


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE raw.ons_daily_load")
```

Regras de estilo: só `from alembic import op` (não importar `sqlalchemy`: `F401` no ruff); apagar o comentário `# Add "from alembic import op" ...` do template `migrations/script.py.mako`; SQL em `op.execute`; toda restrição com nome fixo e prefixo da tabela; um `op.execute` por `COMMENT ON`; `"date"` entre aspas no DDL e nos `COMMENT ON COLUMN`, como na `0006`; docstring, comentários e textos de `COMMENT` em inglês (ADR 0001). `alembic revision` sem `--autogenerate` não precisa de banco; o arquivo sai `0007_raw_weather_observed.py` pelo template `%(rev)s_%(slug)s`.

Cuidado com o texto dos `COMMENT`: `op.execute` com string passa por `sqlalchemy.text()`, que interpreta `:nome` (inclusive `:45`) como parâmetro. **Não use dois-pontos** nos comentários (por exemplo, nada de "06:45"). Também use só ASCII e escreva `degrees Celsius` e `percent` em vez de `°C` e `%`, como a `0006` escreveu `Diaria` sem acento (D8).

### Padrões de teste a seguir (`tests/test_raw_weather_forecast.py`, `tests/test_raw_ons_daily_load.py`, `tests/conftest.py`)

- Fixtures de `tests/conftest.py` (não alterar): `migrated_database` (sessão, em `head`, **só leitura**: `SELECT` e catálogo, inclusive `has_table_privilege`); `fresh_database` (por teste, vazio, apagado no teardown). `alembic_config()` é função, importada de `tests.conftest`. Todo teste que escreve, faz `upsert` ou `downgrade` usa um fixture próprio:

```python
@pytest.fixture
def observed_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database
```

- Helpers locais ao módulo, replicados dos arquivos de referência: `_query(url, statement, role=None)`, `_execute(url, statement, params=None, role=None)` (com commit), `_insert_expecting_error(url, row, statement=INSERT, error_type=IntegrityError)`, `_assert_denied(url, role, statement, params=None)` (confere `42501`), `_table_exists(url)` via `to_regclass('raw.weather_observed')`, `_has_privilege(url, role, privilege, table=TABLE)` via `has_table_privilege`, `_frame(...)` (DataFrame no formato do job, sem `ingested_at`), `_upsert_as(url, role, frame, on_conflict)` (`SET ROLE` + `upsert` + commit). Todos usam `build_engine(url)` de `ingestion.db` e `engine.dispose()` no `finally`.
- `pytestmark = pytest.mark.db` no módulo. Docstring do módulo: `"""Tests for table ``raw.weather_observed`` (plan 25, migration 0007). ..."""`, mencionando que, diferente de `raw.weather_forecast`, o `ingestor` mantém `UPDATE`.
- Constantes: `TABLE = "raw.weather_observed"`, `KEYS = ["location_id", "date"]`, `WEATHER_COLUMNS = ["temp_max", "temp_min", "precip_mm", "wind_speed_max", "humidity_mean"]`.
- Erros: `error.orig.sqlstate` e `error.orig.diag.constraint_name`. SQLSTATEs: `42501` permissão, `23502` `NOT NULL`, `23503` chave estrangeira, `23505` chave duplicada.
- `INSERT` direto nos testes passa `now()` para `ingested_at` (a coluna não tem `DEFAULT`). Sugestão: `INSERT = 'INSERT INTO raw.weather_observed (location_id, "date", temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean, ingested_at) VALUES (:location_id, :date, :temp_max, :temp_min, :precip_mm, :wind_speed_max, :humidity_mean, now())'`.
- Comentários lidos com `obj_description(to_regclass('raw.weather_observed'), 'pg_class')` e `col_description(a.attrelid, a.attnum)` sobre `pg_attribute`, como no caso 4 de `tests/test_raw_ons_daily_load.py`.
- Os 4 locais de `ref.locations` (semeados pela `0003`): `sao_paulo`, `porto_alegre`, `recife`, `belem`.

## 5. Passos

0. (test-writer e implementer, antes de tudo) Confirme a base: `uv run alembic heads` mostra `0006 (head)` e `migrations/versions/` não tem arquivo `0007_*`. Se o head for outro, **parar** e avisar o usuário (não renumerar por conta própria).
1. (test-writer) Partindo da `main` atualizada, na branch `feat/raw-weather-observed`, escreva `tests/test_raw_weather_observed.py` com os casos da seção 8, seguindo os padrões da seção 4. Rode `uv run pytest tests/test_raw_weather_observed.py` e confirme que falham porque `raw.weather_observed` não existe (`UndefinedTable` / `to_regclass` nulo). `uv run ruff check .` e `uv run ruff format --check .` limpos. Commit `test: add raw.weather_observed tests`.
2. (implementer) Partindo da branch com os testes: `uv run alembic revision -m "raw_weather_observed" --rev-id 0007`. Confira `down_revision = "0006"`. Ajuste os imports (só `from alembic import op`; apague o comentário do template).
3. Docstring do módulo, em inglês, no formato da `0006`: cria `raw.weather_observed` (daily observed weather from the Open-Meteo ERA5 archive, one row per location and day); permissions come from the default privileges set by 0002, no explicit GRANT or REVOKE; the ingestor keeps UPDATE on purpose because the job rewrites the recent window (recent ERA5 values may be preliminary) with `on_conflict="update"` (ADR 0005: `ingested_at` is the last write); unlike `raw.weather_forecast`, observed values are not stored as issued.
4. `upgrade`, primeiro `op.execute`, a tabela, com estes nomes e tipos exatos (os testes conferem):

   ```sql
   CREATE TABLE raw.weather_observed (
       location_id text NOT NULL,
       "date" date NOT NULL,
       temp_max double precision,
       temp_min double precision,
       precip_mm double precision,
       wind_speed_max double precision,
       humidity_mean double precision,
       ingested_at timestamptz NOT NULL,
       CONSTRAINT weather_observed_pkey PRIMARY KEY (location_id, "date"),
       CONSTRAINT weather_observed_location_id_fkey
           FOREIGN KEY (location_id) REFERENCES ref.locations (location_id)
   )
   ```

   Sem `ON DELETE`/`ON UPDATE` (padrão `NO ACTION`, como na `0004`). Sem `CHECK`.
5. `upgrade`, um `op.execute` por comentário, com estes textos (ASCII, sem dois-pontos; o caso 4 confere trechos):
   - `COMMENT ON TABLE raw.weather_observed IS 'Daily observed weather per location from the Open-Meteo archive (ERA5 reanalysis), one row per location and day. Rows are upserted. Recent days are rewritten by the daily job because recent ERA5 values may be preliminary (the ingestor role has UPDATE).'`
   - `COMMENT ON COLUMN raw.weather_observed."date" IS 'Calendar day in America/Sao_Paulo (timezone requested from the archive API).'`
   - `COMMENT ON COLUMN raw.weather_observed.temp_max IS 'Daily maximum air temperature at 2 m, degrees Celsius (temperature_2m_max).'`
   - `COMMENT ON COLUMN raw.weather_observed.temp_min IS 'Daily minimum air temperature at 2 m, degrees Celsius (temperature_2m_min).'`
   - `COMMENT ON COLUMN raw.weather_observed.precip_mm IS 'Daily precipitation sum, mm (precipitation_sum).'`
   - `COMMENT ON COLUMN raw.weather_observed.wind_speed_max IS 'Daily maximum wind speed at 10 m, km/h (wind_speed_10m_max).'`
   - `COMMENT ON COLUMN raw.weather_observed.humidity_mean IS 'Daily mean relative humidity at 2 m, percent (relative_humidity_2m_mean).'`
   - `COMMENT ON COLUMN raw.weather_observed.ingested_at IS 'Server time of the last write of the row (ADR 0005).'`
6. Não escreva `GRANT` nem `REVOKE` (D3).
7. `downgrade`: `op.execute("DROP TABLE raw.weather_observed")` (sem `CASCADE`).
8. Rode os critérios de pronto e cole comando e saída no PR. No corpo do PR, declare as decisões D1 a D10 da seção 9, em especial D3 (`ingestor` com `UPDATE`, `on_conflict="update"`, diferente da `0004`).
9. (usuário, depois que a `0007` estiver em produção, de preferência junto do backfill do item 27) Enviar à cientista o aviso da seção 9.

## 6. Critérios de pronto

Precisa do Postgres de teste: `docker compose -f infra/docker-compose.dev.yml up -d`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_raw_weather_observed.py tests/test_migrations.py tests/test_permissions.py tests/test_ref_locations.py tests/test_raw_weather_forecast.py tests/test_ref_calendar.py tests/test_raw_ons_daily_load.py tests/test_upsert.py` | Todos passam, nenhum `skipped` |
| `uv run alembic heads` | `0007 (head)` |
| `uv run alembic history` | Primeira linha `0006 -> 0007 (head), raw_weather_observed` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| `git diff --name-only main...HEAD` | Só `tests/test_raw_weather_observed.py` e `migrations/versions/0007_raw_weather_observed.py` |
| `gh pr checks` | Verde (o CI roda `alembic upgrade head` e a suíte com Postgres) |

## 7. Testes necessários

`sim`: chave, chave estrangeira, nulidade, comentários de unidade e permissões (o `ingestor` precisa de `UPDATE` para reescrever a janela recente do ERA5) são o contrato que a cientista consulta e que o job do PR 26 usa.

## 8. Casos de teste

Leitura e catálogo, no banco compartilhado em `head` (`migrated_database`):

1. Schema: colunas pelo `information_schema.columns` (ordenadas por nome) exatamente: `date date NO`, `humidity_mean double precision YES`, `ingested_at timestamp with time zone NO`, `location_id text NO`, `precip_mm double precision YES`, `temp_max double precision YES`, `temp_min double precision YES`, `wind_speed_max double precision YES`. Nenhuma coluna gerada (`is_generated = NEVER` em todas).
2. Paridade com a previsão: para cada uma das 5 variáveis, `data_type` e `is_nullable` em `raw.weather_observed` são iguais aos de `raw.weather_forecast`.
3. Restrições: o conjunto de restrições da tabela (`pg_constraint`, `conname` e `contype`) é exatamente `weather_observed_pkey` (`p`) e `weather_observed_location_id_fkey` (`f`); a chave primária é formada exatamente por `location_id` e `date`; a chave estrangeira liga `location_id` a `ref.locations (location_id)`. Nenhum `CHECK` (D4).
4. Comentários: o da tabela não é nulo e contém `ERA5` e `UPDATE`; o de `date` contém `America/Sao_Paulo`; `temp_max` e `temp_min` contêm `degrees Celsius`; `precip_mm` contém `mm`; `wind_speed_max` contém `km/h`; `humidity_mean` contém `percent`; `ingested_at` contém `last write`.
5. A tabela nasce vazia (`count(*)` = 0).
6. Privilégios do `ingestor` em `raw.weather_observed` por `has_table_privilege`: `SELECT` = true, `INSERT` = true, `UPDATE` = true, `DELETE` = false, `TRUNCATE` = false.
7. `scientist`, `scorer`, `reader`: `SELECT` = true; `INSERT` = false; `UPDATE` = false.

Escrita, cada teste num banco novo em `head` (`observed_database`), como admin salvo indicação. Linha de base: `location_id = 'recife'`, `date = 2026-11-05`, `temp_max = 30.5`, `temp_min = 24.0`, `precip_mm = 3.2`, `wind_speed_max = 22.0`, `humidity_mean = 78.0`, `ingested_at = now()`.

8. Inserir a linha de base → aceita; relida com os mesmos valores e `ingested_at` não nulo.
9. Os 4 locais na mesma data, e o mesmo local em duas datas → todas as linhas coexistem (5 linhas).
10. Mesma (`location_id`, `date`) duas vezes sem `ON CONFLICT` → a segunda falha com `23505`.
11. `location_id = 'does_not_exist'` → falha com `23503` na restrição `weather_observed_location_id_fkey`.
12. `NULL` em `location_id`, `date` ou `ingested_at` → falha com `23502`.
13. As 5 variáveis nulas na mesma linha → aceita; só `humidity_mean` nulo → aceita (nulo parcial, como o PR 24 entrega).
14. Valores fora da faixa plausível (`temp_min = 35.0` com `temp_max = 20.0`, `humidity_mean = 120.0`, `precip_mm = -1.0`) → aceitos pelo banco (a faixa é da checagem pandera do PR 26, D4).
15. Com a linha de base gravada, o admin apaga `recife` de `ref.locations` → falha com `23503` (a chave estrangeira protege o histórico) e as duas tabelas ficam como estavam.
16. Como `ingestor`, `upsert(conn, "raw.weather_observed", df, keys=["location_id", "date"], on_conflict="update")` com 2 linhas (`recife` 2026-11-05 e 2026-11-06, sem `ingested_at`), seguido de commit → devolve 2; `ingested_at` não nulo nas duas.
17. Reescrita do ERA5: com as linhas do caso 16 gravadas, um segundo `upsert` como `ingestor`, `on_conflict="update"`, em outra transação, com `precip_mm` de 2026-11-06 mudado (por exemplo 3.2 → 5.0) e 2026-11-05 igual → sem erro de permissão; 2026-11-06 passa a 5.0, 2026-11-05 continua igual, total continua 2 linhas, e o `ingested_at` das duas é estritamente maior que o da primeira escrita (ADR 0005: última escrita).
18. Mesmo `upsert` do caso 16 repetido idêntico → continua com 2 linhas e os mesmos valores (idempotente).
19. `upsert` com `NaN` em `humidity_mean` → a linha é gravada com `humidity_mean` `NULL`.
20. Como `ingestor`: `INSERT` da linha de base funciona; `UPDATE raw.weather_observed SET precip_mm = 0.0` funciona; `DELETE FROM raw.weather_observed` e `TRUNCATE raw.weather_observed` falham com `42501` e a linha continua.
21. Como `scientist`, `scorer` e `reader`: `SELECT count(*)` devolve 1 depois que o admin inseriu a linha de base; `INSERT` de outra linha e `UPDATE` da existente falham com `42501`.
22. Migração, `downgrade` até `0006`: antes, `raw.weather_observed` existe; depois, não existe, e `raw.ons_daily_load`, `ref.calendar`, `raw.weather_forecast` e `ref.locations` (4 linhas) continuam; um novo `upgrade head` recria a tabela vazia, com `UPDATE` para o `ingestor` e `SELECT` sem `INSERT` para o `reader` (`has_table_privilege`), e com a chave estrangeira `weather_observed_location_id_fkey` presente.
23. Migração, `downgrade` até `0002` a partir do `head` com uma linha em `raw.weather_observed` → termina sem erro (a `0007` sai antes da `0003`, então `ref.locations` pode ser apagada) e `raw.weather_observed` e `ref.locations` não existem.

Já existentes que continuam verdes sem edição: `tests/test_migrations.py` (round trip `head` → `base` → `head`, `upgrade head` duas vezes, ids de 4 dígitos, head único), `tests/test_permissions.py`, `tests/test_ref_locations.py`, `tests/test_raw_weather_forecast.py` (inclusive o caso 22, `downgrade` até `0003`), `tests/test_ref_calendar.py`, `tests/test_raw_ons_daily_load.py` (inclusive o caso 19, `downgrade` até `0005`) e `tests/test_upsert.py`.

## 9. Riscos e perguntas em aberto

Nenhuma pergunta em aberto bloqueia. Decisões (adotadas pelas recomendações, com a autorização do usuário de aceitar recomendações; o usuário pode revertê-las na revisão do plano):

- **D1. Colunas, tipos e nulidade iguais aos de `raw.weather_forecast`.** Mesmas 5 variáveis, `double precision`, aceitando nulo; mesmas unidades (°C, mm, km/h, %), que o cliente já valida em `DAILY_UNITS`. Assim a cientista compara previsão e observado coluna a coluna.
- **D2. Chave (`location_id`, `date`) e chave estrangeira para `ref.locations`, com nomes fixos** (`weather_observed_pkey`, `weather_observed_location_id_fkey`), no padrão `weather_forecast_*` da `0004`. O formato do slug já é garantido pelo `CHECK` de `ref.locations` (ADR 0005, P18); não precisa repetir aqui.
- **D3. O `ingestor` mantém `UPDATE` e o job usa `on_conflict="update"`.** O doc define a janela diária de 10 dias "para cobrir atraso e correções da fonte" e o item 18 registra que o valor do dia corrente provavelmente não é final; regravar essa janela exige sobrescrever. É coerente com a `0006` (ONS) e com "última escrita" do ADR 0005. Logo **não** há `REVOKE UPDATE` (diferente da `0004`). `DELETE` e `TRUNCATE` continuam negados. Sem exceção ao modelo de papéis da `0002`.
- **D4. Sem `CHECK` de faixa nas variáveis.** A faixa fica na checagem pandera do PR 26, que roda depois de gravar, para o job acusar com diagnóstico ("checagem falha = execução falha") em vez de a transação ser recusada. Igual a `raw.weather_forecast` e à D4 do plano 21.
- **D5. Sem `CHECK` de "pelo menos uma variável não nula".** O PR 24 já descarta dias com todas as variáveis nulas; manter a mesma liberdade de `raw.weather_forecast`. Se a cientista pedir, vira mudança de contrato futura.
- **D6. `date` é o dia em `America/Sao_Paulo`**, o fuso pedido à API pelo cliente (ADR 0005: "o dia dos dados de clima é `America/Sao_Paulo`, definido pelos jobs"). Documentado no comentário da coluna. O nome `date` vem do modelo de dados e vai entre aspas no DDL, como na `0006`.
- **D7. `ingested_at timestamptz NOT NULL`, sem `DEFAULT`**, carimbado pelo `upsert` no insert e no `SET` do conflito.
- **D8. Unidade e origem nos comentários, em ASCII e sem dois-pontos.** A cientista lê o catálogo; a `0004` não tem comentários de unidade, a `0006` tem. ASCII (`degrees Celsius`, `percent`) segue a `0006` (`Diaria`) e evita depender da codificação do banco; sem dois-pontos porque `op.execute` passa por `text()`.
- **D9. Revisão `0007`, `down_revision = "0006"`.** Se o head mudar antes de começar, o passo 0 para.
- **D10. Testes num arquivo só** (`tests/test_raw_weather_observed.py`): não há lógica de Python neste PR.

Riscos:

- **ERA5 pode mudar valores mais antigos que a janela de 10 dias.** O item 18 ainda não mediu revisões; não muda o schema, só a janela do PR 26.
- **Linha que a fonte deixa de publicar.** O `upsert` não apaga (o `ingestor` não tem `DELETE`); correção manual pelo admin. Registrar no PR, não tratar aqui.
- **`downgrade` em produção apaga o histórico.** O observado pode ser recarregado do arquivo ERA5 (backfill), mas `alembic downgrade` abaixo de `0007` não deve rodar em produção sem combinar.
- **Comentários de unidade só nesta tabela.** `raw.weather_forecast` continua sem eles; acrescentá-los é uma migração própria (só `COMMENT`, sem mudança de colunas), fora deste PR.
- **Privilégios padrão dependem do admin.** As migrações rodam com o mesmo admin (`DATABASE_URL_ADMIN`); na VPS, pelo procedimento interino do ADR 0004 (`docker compose -f infra/docker-compose.yml run --rm jobs alembic upgrade head`).
- **Postgres de teste.** Sem o container de `infra/docker-compose.dev.yml`, os testes `db` falham (não pulam), por desenho de `tests/conftest.py`.

### Aviso à ciência de dados

A regra exige aviso para mudança em `raw`. Quem envia é o usuário (passo 9). Conteúdo mínimo:

- Existe `raw.weather_observed` (`location_id`, `date`, `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`, `ingested_at`), chave (`location_id`, `date`), uma linha por local por dia, com histórico desde 2015 depois do backfill (item 27).
- Fonte: arquivo do Open-Meteo (reanálise ERA5). Mesmas variáveis e unidades de `raw.weather_forecast`: temperaturas em °C, chuva em mm, vento máximo em km/h, umidade média em %. `date` é o dia em `America/Sao_Paulo`.
- Para comparar previsão e observado: `JOIN raw.weather_forecast f ON f.location_id = o.location_id AND f.target_date = o."date"`.
- Os valores recentes podem mudar: o job reescreve os últimos 10 dias toda manhã, e o valor do dia corrente provavelmente não é o final da reanálise. `ingested_at` é a última escrita, não a primeira. Para reprodutibilidade, congele o recorte em `features` ou registre a data da extração.
- Uma variável pode vir nula num dia (nulo parcial); dias sem nenhuma variável não têm linha.
- `scientist` só lê esta tabela.

## 10. Decisões que exigem ADR

- **Nenhum ADR novo.** A exigência do `AGENTS.md` (migração + ADR + aviso para mudança em `raw`) é cumprida por: migração `0007`; ADR 0005 (mergeado), que cita `raw.weather_observed` duas vezes — como tabela com chave estrangeira para `ref.locations` (P18) e na lista de tabelas cobertas, PR 25 —, fixa `ingested_at` como última escrita (a semântica do modo `update`) e o dia dos dados de clima em `America/Sao_Paulo`, e delega "os demais tipos e colunas" aos planos e a `docs/plataforma-ml.md`, cujo modelo de dados já prevê esta tabela com estas colunas e esta chave; e o aviso da seção 9.
- **D3 (`UPDATE` mantido) não exige ADR:** é o padrão da `0002` para `raw`, sem exceção (a exceção é a da `0004`), e o modo `update` é o padrão do `upsert` (PR 08). Não há exceção a sinalizar.
- **Contrato das funções** (`build_features`, `predict`, `evaluate`): não muda. **Rede/portas:** nada exposto (ADR 0003). **Dependências:** nenhuma.
- Exigiriam ADR no futuro (novo ou emenda ao 0005), com migração e aviso: nova coluna (por exemplo `source`, `is_final`, `first_ingested_at`), mudar a chave, mudar unidades, guardar versões das revisões do ERA5 em vez de sobrescrever, ou passar a guardar o observado "como publicado" (`REVOKE UPDATE`).
