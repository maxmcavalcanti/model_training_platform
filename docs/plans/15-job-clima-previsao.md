# 15 — Job `weather-forecast`: snapshot diário, checagem e CLI

> Executa: agente. Depende de: 11, 13, 14 (todos na `main` em `d75bdbe`). Branch sugerida: `feat/job-weather-forecast`.
> **Antecipado** (Fase 2 antes do fim da Fase 1; desvio de "uma fase por vez" aprovado pelo usuário em 2026-11-07, P5 resolvida).
> TDD: passo 0 (dependências) → test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-08: alinhado à `main` em `d75bdbe` (migração `0004` `raw.weather_forecast` sem `UPDATE` para o `ingestor`; `ingestion/openmeteo.py`, `ingestion/http.py`, `ingestion/db.py`, `ingestion/cli.py`; `ref.locations` com 4 capitais; ADR 0005). As perguntas que tinham recomendação foram fechadas como decisões D1 a D12 (seção 9), por autorização do usuário. Não há pergunta aberta que bloqueie; o único risco a conferir no passo 0 é a compatibilidade do `pandera` com `pandas>=3.1.1`.

## 1. Objetivo

Criar o job que tira o snapshot da previsão de hoje (dia em `America/Sao_Paulo`) para todos os locais de `ref.locations`, grava em `raw.weather_forecast` sem nunca sobrescrever snapshot existente e termina com checagem pandera.
Exposto como `python -m ingestion weather-forecast`; o agendamento é o PR 16.

## 2. Fora do escopo

- Agendamento (supercronic, PR 16) e ligar a coleta na VPS (item 17).
- Alertas no Telegram (PR 55); até lá, falha = código de saída 1 e log no stderr.
- Flow do Prefect (PR 32).
- Horizonte 0 e horizontes acima de 7 (ADR 0005: 1 a 7; a tabela recusa outros por `CHECK`).
- Backfill de previsões passadas pela API "Historical Forecast" (P10 no índice) e argumento `--date` (D8).
- Alterar `ingestion/openmeteo.py`, `ingestion/http.py`, `ingestion/db.py`, migrações, `tests/conftest.py`, `infra/`, `.github/workflows/ci.yml`, `.claude/` ou outros planos.
- Retry adicional no job: o retry de rede (3 tentativas, backoff) já está em `ingestion/http.py` e é chamado por `fetch_forecast`.

## 3. Fase do roadmap

Fase 2 — Clima, item "`raw.weather_forecast` coletando todo dia (prioridade)" (`docs/plataforma-ml.md`, "Roadmap"), antecipado pela P5.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Passo 0: dependências de produção `pandera` (checagem) e `tzdata` (base de fusos para `zoneinfo` no Windows; D7) |
| `ingestion/checks.py` | Novo: `CheckFailed`, `check(df, schema, expected_rows=None)` e `WEATHER_FORECAST_SCHEMA` |
| `ingestion/jobs.py` | Novo: `issue_date(now=None)`, `list_locations(conn)`, `PartialIngestionError`, `ingest_weather_forecast(engine, client, today, *, base_delay=1.0)` |
| `ingestion/cli.py` | Registrar o subcomando `weather-forecast` em `SUBCOMMANDS` |
| `AGENTS.md` | Seção "Comandos": acrescentar `uv run python -m ingestion weather-forecast` (cada PR registra os seus comandos, índice "Como usar") |
| `tests/test_checks_weather_forecast.py`, `tests/test_job_weather_forecast.py` | Testes (test-writer) |

### Código existente que este PR usa (estado em `d75bdbe`)

`ingestion/openmeteo.py`:

```python
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_TIMEZONE = "America/Sao_Paulo"
MAX_HORIZON_DAYS = 7
DAILY_VARIABLES = {  # API variable -> raw.weather_forecast column
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "precipitation_sum": "precip_mm",
    "wind_speed_10m_max": "wind_speed_max",
    "relative_humidity_2m_mean": "humidity_mean",
}

@dataclass(frozen=True)
class Location:
    location_id: str
    lat: float
    lon: float

def fetch_forecast(client: httpx.Client, location: Location, issued_at: date,
                   days: int = MAX_HORIZON_DAYS, *, base_delay: float = 1.0,
                   sleep: Callable[[float], None] = time.sleep) -> pd.DataFrame:
    """Fetch the daily forecast for horizons 1 to ``days`` as a frame ready for upsert."""
```

- Devolve 7 linhas com colunas, nesta ordem, `location_id`, `issued_at`, `target_date`, `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean` (variáveis em `float64`, `null` da API vira `NaN`). Não traz `horizon_days` (coluna gerada) nem `ingested_at` (carimbado pelo `upsert`).
- Levanta `ValueError` quando a resposta é inválida: sem `daily`, variável ausente, unidade inesperada, listas de tamanhos diferentes, menos de `days + 1` dias, ou primeiro dia da resposta diferente de `issued_at` (a mensagem cita as duas datas).
- Levanta `ingestion.http.NetworkError(RuntimeError)` quando as 3 tentativas falham por erro de transporte, 429 ou 5xx. Um 4xx que não seja 429 sai como `httpx.HTTPStatusError` na primeira tentativa, sem retry.

`ingestion/db.py`:

```python
def build_engine(url: str | None = None) -> sqlalchemy.Engine  # usa DATABASE_URL; levanta MissingConfiguration
def upsert(conn: sqlalchemy.Connection, table: str, rows: pd.DataFrame, keys: list[str], *,
           on_conflict: Literal["update", "ignore"] = "update",
           stamp_ingested_at: bool = True) -> int
```

- `upsert` devolve o número de linhas inseridas (no modo `"ignore"`, conflitos não contam). Quem chama é dono da transação: o `upsert` não faz commit. DataFrame vazio devolve 0.

`ingestion/cli.py` (registro de subcomandos e códigos de saída 0/1/2):

```python
@dataclass(frozen=True)
class Subcommand:
    help: str
    add_arguments: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], int]

SUBCOMMANDS: dict[str, Subcommand] = {}
# main(argv): exceção no run -> traceback no stderr, log "subcommand <name> failed", retorna 1
```

`migrations/versions/0004_raw_weather_forecast.py` (tabela que o job grava):

```sql
CREATE TABLE raw.weather_forecast (
    location_id text NOT NULL,
    issued_at date NOT NULL,
    target_date date NOT NULL,
    horizon_days smallint NOT NULL
        GENERATED ALWAYS AS ((target_date - issued_at)::smallint) STORED,
    temp_max double precision, temp_min double precision, precip_mm double precision,
    wind_speed_max double precision, humidity_mean double precision,
    ingested_at timestamptz NOT NULL,
    PRIMARY KEY (location_id, issued_at, target_date),
    FOREIGN KEY (location_id) REFERENCES ref.locations (location_id),
    CHECK ((target_date - issued_at) BETWEEN 1 AND 7)
);
REVOKE UPDATE ON raw.weather_forecast FROM ingestor;
```

O `ingestor` tem `SELECT` e `INSERT` na tabela, e **não** tem `UPDATE`, `DELETE` nem `TRUNCATE`. Logo o job só funciona com `on_conflict="ignore"`; com `"update"` o Postgres recusa (`42501`), mesmo sem conflito. Em produção o serviço `jobs` do `infra/docker-compose.yml` conecta como `ingestor` (`DATABASE_URL=postgresql+psycopg://ingestor:...@postgres:5432/ml`).

`migrations/versions/0003_ref_locations.py`: `ref.locations(location_id text PK, name, lat, lon, subsystem)` com 4 linhas: `belem`, `porto_alegre`, `recife`, `sao_paulo`. O `ingestor` lê `ref`.

`tests/conftest.py`: `fresh_database` (banco vazio por teste, URL de admin) e `migrated_database` (sessão, só leitura). `tests/test_raw_weather_forecast.py` e `tests/test_openmeteo_forecast.py` já definem um fixture local `forecast_database` (um `fresh_database` com `alembic upgrade head`, via `monkeypatch.setenv("DATABASE_URL_ADMIN", ...)` e `command.upgrade(alembic_config(), "head")`) e escrevem como `ingestor` com `SET ROLE ingestor`. O test-writer deve repetir esse padrão no arquivo novo (não mexer no `conftest.py`).

`tests/fixtures/openmeteo_forecast_sao_paulo.json`: resposta real com `daily.time` de `2026-11-08` a `2026-11-15` (8 dias), unidades corretas, `temperature_2m_max` entre 15.6 e 28.7, `temperature_2m_min` entre 11.8 e 16.6, umidade entre 72 e 89. Serve para os 4 locais (o local vem do parâmetro, não da resposta).

`infra/jobs/Dockerfile`: já instala o `tzdata` do Debian e define `TZ=America/Sao_Paulo`; o pacote `tzdata` do PyPI é para Windows e não muda nada na imagem.

### Regras que valem aqui

`.claude/rules/migrations-e-dados.md`:

> Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.
> `raw.weather_forecast` guarda a previsão como emitida (`issued_at`). Nunca sobrescrever uma previsão antiga com uma nova.

`AGENTS.md`: "Todo job termina com checagem de qualidade (pandera). Checagem falha = execução falha." Mensagens de log e de erro em inglês (ADR 0001).

`docs/plataforma-ml.md`, "Checagem": "linhas esperadas por dia, sem nulos nas colunas-chave, valores dentro de faixas plausíveis (… temperatura entre −10 e 50 °C)". Job das 06:30: "Snapshot da previsão para os próximos 7 dias, um registro por local e data-alvo, com `issued_at` = hoje".

ADR 0005: `issued_at` é `date`, o dia do snapshot em `America/Sao_Paulo`; o primeiro snapshot do dia vence; horizontes 1 a 7.

## 5. Passos

0. (implementer, primeiro commit da branch) `uv add pandera tzdata`. Confira que a versão resolvida do `pandera` aceita o `pandas` do `uv.lock` (3.x): `uv run python -c "import pandera.pandas as pa, pandas as pd; print(pa.__version__, pd.__version__)"` deve imprimir as duas versões sem erro. Se a resolução falhar ou o import quebrar com pandas 3, **pare** e reporte ao usuário (seção 9, R1). Rode `uv run pytest -m "not db"` (verde). Commit `build: add pandera and tzdata dependencies`.
1. (test-writer) Escreva os testes da seção 8 em `tests/test_checks_weather_forecast.py` e `tests/test_job_weather_forecast.py`. Detalhes:
   - Os testes do job usam `@pytest.mark.db`, um fixture local `forecast_database` como nos arquivos existentes, e um `httpx.Client(transport=httpx.MockTransport(handler))` cujo handler escolhe a resposta pelo parâmetro `latitude` da requisição (para fazer um local falhar) e devolve a fixture gravada.
   - `today` fixo = primeiro dia da fixture (`2026-11-08`). Para o caso "dia seguinte", o handler devolve uma cópia da fixture com cada data de `daily.time` deslocada em +1 dia (o cliente exige que o primeiro dia seja `issued_at`).
   - O job roda como `ingestor`: o teste passa um engine criado com `sqlalchemy.create_engine(url, connect_args={"options": "-c role=ingestor"})` (o usuário `postgres` do banco de teste é superusuário e pode assumir o papel). Isso prova que o job funciona sem `UPDATE` (D2).
   - Passe `base_delay=0` ao job para o retry não dormir.
   - Confirme a falha por `ModuleNotFoundError: No module named 'ingestion.checks'` / `'ingestion.jobs'` e, no teste de CLI, por `invalid choice: 'weather-forecast'`. Commit `test: add weather-forecast job tests`.
2. (implementer) `ingestion/checks.py`:
   - `class CheckFailed(RuntimeError)`.
   - `check(df: pd.DataFrame, schema, expected_rows: int | None = None) -> None`: valida com `schema.validate(df, lazy=True)`; converte `pandera.errors.SchemaErrors` em `CheckFailed` com mensagem legível que cita as colunas e as checagens que falharam (por exemplo a partir de `error.failure_cases`). Se `expected_rows` for dado e diferente de `len(df)`, levanta `CheckFailed` com mensagem que cita os dois números (ex.: `expected 28 rows, got 21`). Se as duas coisas falharem, uma única `CheckFailed` com as duas mensagens.
   - `WEATHER_FORECAST_SCHEMA` (`import pandera.pandas as pa`, `DataFrameSchema`, `strict=False`):
     - `location_id`, `issued_at`, `target_date`: não nulos.
     - `horizon_days`: não nulo, entre 1 e 7.
     - `temp_max`, `temp_min`: entre −10 e 50, nulos permitidos.
     - `precip_mm` ≥ 0, `wind_speed_max` ≥ 0, `humidity_mean` entre 0 e 100; nulos permitidos.
     - Checagem de DataFrame: `temp_min <= temp_max` nas linhas em que ambos existem.
     - Unicidade de (`location_id`, `issued_at`, `target_date`).
3. `ingestion/jobs.py`:
   - `issue_date(now: datetime | None = None) -> date`: dia de `now` em `ZoneInfo(FORECAST_TIMEZONE)` (importe a constante de `ingestion.openmeteo`); `now=None` usa `datetime.now(UTC)`; `datetime` sem fuso levanta `ValueError`.
   - `list_locations(conn) -> list[Location]`: `SELECT location_id, lat, lon FROM ref.locations ORDER BY location_id`.
   - `class PartialIngestionError(RuntimeError)`.
   - `ingest_weather_forecast(engine, client, today: date, *, base_delay: float = 1.0) -> int` (devolve as linhas inseridas nesta execução):
     1. Lê os locais numa conexão.
     2. Para cada local, chama `fetch_forecast(client, location, today, base_delay=base_delay)`. Se levantar `NetworkError`, `ValueError` ou `httpx.HTTPError`, registra `logger.error` com o `location_id` e o erro e **continua** com os outros (D3). Outras exceções (bug) propagam.
     3. Concatena os frames que deram certo e grava numa transação (`with engine.begin() as conn`) com `upsert(conn, "raw.weather_forecast", frame, keys=["location_id", "issued_at", "target_date"], on_conflict="ignore")`. Sem frames, não chama o `upsert`.
     4. Numa nova conexão, relê `SELECT location_id, issued_at, target_date, horizon_days, temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean FROM raw.weather_forecast WHERE issued_at = :today` e roda `check(df, WEATHER_FORECAST_SCHEMA, expected_rows=len(locations) * MAX_HORIZON_DAYS)`.
     5. Se algum local falhou no passo 2, levanta `PartialIngestionError` cuja mensagem lista os locais que falharam (e, se a checagem do passo 4 também falhou, inclui a mensagem dela). Sem falha de local, a `CheckFailed` do passo 4 propaga como está.
     6. Sucesso: `logger.info` com número de locais, linhas inseridas e linhas já existentes; devolve as inseridas.
4. `ingestion/cli.py`: registre `SUBCOMMANDS["weather-forecast"]` com `help="Snapshot today's weather forecast for every location into raw.weather_forecast"`, sem argumentos. O `run`:
   - Importa o módulo (`from ingestion import jobs`) e chama `jobs.ingest_weather_forecast(...)` e `jobs.issue_date()` pelo atributo do módulo, para o teste poder trocar a função com `monkeypatch.setattr("ingestion.jobs.ingest_weather_forecast", ...)` (D10).
   - `engine = build_engine()`; `with httpx.Client(timeout=30) as client`; chama o job com `today=jobs.issue_date()`; `engine.dispose()` no `finally`; devolve 0.
   - Exceções não são tratadas aqui: o `main` já converte em código 1 com traceback.
5. `AGENTS.md`, seção "Comandos": acrescente `- Snapshot da previsão: uv run python -m ingestion weather-forecast (usa DATABASE_URL; na VPS: docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion weather-forecast)`.
6. Rode os critérios de pronto, `uv run ruff check .` e `uv run ruff format --check .`, e refatore com a suíte verde.

## 6. Critérios de pronto

Comandos em PowerShell (ambiente do usuário). Os manuais precisam do compose de dev e de rede.

| Comando | Saída esperada |
| --- | --- |
| `uv run python -c "import pandera.pandas, tzdata, zoneinfo; print(zoneinfo.ZoneInfo('America/Sao_Paulo'))"` | `America/Sao_Paulo` |
| `uv run pytest tests/test_checks_weather_forecast.py tests/test_job_weather_forecast.py` (com `docker compose -f infra/docker-compose.dev.yml up -d`) | Todos passam |
| `uv run python -m ingestion --help` | Lista `weather-forecast` |
| Manual: `docker compose -f infra/docker-compose.dev.yml exec postgres createdb -U postgres ml_manual` e `$env:DATABASE_URL_ADMIN="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ml_manual"; uv run alembic upgrade head` | Migra até `0004` |
| Manual: `$env:DATABASE_URL=$env:DATABASE_URL_ADMIN; uv run python -m ingestion weather-forecast; echo $LASTEXITCODE` | Log com 4 locais e `0` |
| Manual: `docker compose -f infra/docker-compose.dev.yml exec postgres psql -U postgres -d ml_manual -tAc "select count(*) from raw.weather_forecast"` | `28` |
| Manual: rodar o job de novo e contar | `0` de saída e continua `28` |
| Manual (limpeza): `docker compose -f infra/docker-compose.dev.yml exec postgres dropdb -U postgres ml_manual` | Sem erro |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` e `docker run --rm platform-jobs python -m ingestion --help` | Lista `weather-forecast` |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erros |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: é o job de maior prioridade e as regras "nunca sobrescrever", "falha parcial grava os outros", "checagem falha = execução falha" e "dia em `America/Sao_Paulo`" precisam de prova.

## 8. Casos de teste

Checagem (`tests/test_checks_weather_forecast.py`, sem banco; DataFrame válido = 4 locais × horizontes 1 a 7, com as colunas relidas no passo 3.4):

1. DataFrame válido de 28 linhas com `expected_rows=28` → não levanta.
2. `expected_rows=28` e 27 linhas → `CheckFailed` cuja mensagem contém `28` e `27`.
3. `temp_max = 51` numa linha → `CheckFailed` mencionando `temp_max`.
4. `temp_min = -10.5` numa linha → `CheckFailed` mencionando `temp_min`.
5. `temp_min > temp_max` numa linha (ambos dentro da faixa) → `CheckFailed`.
6. `precip_mm = -0.1` → `CheckFailed` mencionando `precip_mm`.
7. `humidity_mean = 101` → `CheckFailed` mencionando `humidity_mean`.
8. `location_id` nulo → `CheckFailed`.
9. `horizon_days = 0` → `CheckFailed`.
10. Duas linhas com a mesma (`location_id`, `issued_at`, `target_date`) → `CheckFailed`.
11. `temp_max` e `temp_min` nulos numa linha (valor ausente na fonte) → não levanta.
12. Duas falhas ao mesmo tempo (`temp_max = 51` em uma linha e `precip_mm = -1` em outra) → uma única `CheckFailed` que menciona as duas colunas.

Data de emissão (`tests/test_job_weather_forecast.py`, sem banco):

13. `issue_date(datetime(2026, 11, 8, 2, 30, tzinfo=UTC))` → `date(2026, 11, 7)` (23:30 em São Paulo).
14. `issue_date(datetime(2026, 11, 8, 3, 0, tzinfo=UTC))` → `date(2026, 11, 8)`.
15. `issue_date(datetime(2026, 11, 8, 12, 0))` (sem fuso) → `ValueError`.

Job (`@pytest.mark.db`, banco migrado com os 4 locais, job rodando como `ingestor`, `today = 2026-11-08`):

16. `list_locations` → 4 `Location`, em ordem `belem`, `porto_alegre`, `recife`, `sao_paulo`, com as coordenadas de `ref.locations`.
17. Primeira execução → devolve 28; a tabela tem 28 linhas com `issued_at = 2026-11-08`, 7 por local, `horizon_days` de 1 a 7 e `target_date` de `2026-11-09` a `2026-11-15`; `ingested_at` preenchido; sem exceção.
18. Segunda execução no mesmo dia, com a API devolvendo temperaturas diferentes → sem exceção, devolve 0, continua 28 linhas e `temp_max` e `ingested_at` são os da **primeira** execução.
19. Execução com `today = 2026-11-09` (fixture com datas deslocadas em +1) → 56 linhas no total; as 28 de `2026-11-08` intactas (mesmos valores e `ingested_at`).
20. API responde 503 em todas as tentativas só para `recife` → 21 linhas gravadas (nenhuma de `recife`) e o job levanta `PartialIngestionError` cuja mensagem contém `recife`; os outros 3 locais aparecem completos.
21. Logo depois de 20, nova execução no mesmo dia com `recife` funcionando → sem exceção; 28 linhas; as 21 anteriores com os mesmos valores e `ingested_at`.
22. API responde com resposta inválida (unidade `m/s` em `wind_speed_10m_max`) só para `belem` → 21 linhas gravadas e `PartialIngestionError` mencionando `belem`.
23. API devolve `temperature_2m_max = 80` num dia de um local → as 28 linhas são gravadas (inclusive a de 80) e o job levanta `CheckFailed` mencionando `temp_max`.
24. Banco com um snapshot já gravado para `today` em que falta um local (simula execução anterior parcial) e API falhando para todos → `PartialIngestionError` citando os 4 locais e nenhuma linha alterada.

CLI (`tests/test_job_weather_forecast.py`, sem banco):

25. `main(["weather-forecast"])` com `DATABASE_URL` definida para uma URL qualquer e `ingestion.jobs.ingest_weather_forecast` trocada (via `monkeypatch`) por uma função que levanta `CheckFailed` → devolve 1.
26. Mesmo arranjo, com a função trocada devolvendo 28 → devolve 0, e ela recebeu `today` igual a `ingestion.jobs.issue_date()` trocada por uma que devolve `date(2026, 11, 8)`.
27. `main(["weather-forecast"])` sem `DATABASE_URL` no ambiente (`monkeypatch.delenv`) → devolve 1 e o stderr cita `DATABASE_URL`.
28. `main(["weather-forecast", "--date", "2026-11-08"])` → código 2 (o subcomando não aceita argumentos).

## 9. Riscos e perguntas em aberto

Decisões tomadas nesta revisão (recomendações adotadas por autorização do usuário):

- **D1. `on_conflict="ignore"`.** A migração 0004 revoga `UPDATE` do `ingestor`; com `"update"` o insert falha por privilégio. É também a regra "o primeiro snapshot vence" (ADR 0005).
- **D2. Testes do job rodam como `ingestor`.** Em produção o job conecta como `ingestor`; testar como admin esconderia um `UPDATE` acidental.
- **D3. Falha de um local não derruba os outros.** Cada local que falha é um dia de histórico perdido e não se recupera; os outros não devem pagar por ele. O job grava os que deram certo e termina com erro (código 1), citando os locais. Reexecutar no mesmo dia completa os que faltaram. Só erros esperados (`NetworkError`, `ValueError` de resposta inválida, `httpx.HTTPError`) são isolados; bug propaga.
- **D4. Dado fora de faixa é gravado antes de falhar.** A regra manda checar "depois de gravar" e a previsão é um snapshot que não se repete: guardar o dado e falhar a execução é melhor que perder o dia. A correção, se preciso, é feita pelo admin (o `ingestor` não tem `UPDATE` nem `DELETE`).
- **D5. A checagem relê o banco** (todas as linhas de `issued_at = today`), não o DataFrame em memória. Assim ela vale também quando a execução não inseriu nada (reexecução) e cobre `horizon_days`, que é gerado pelo Postgres.
- **D6. `expected_rows = len(ref.locations) * 7`.** Segue ADR 0005 (horizontes 1 a 7) e acompanha locais novos em `ref.locations` sem mudar código.
- **D7. `tzdata` como dependência de produção.** No Windows o `zoneinfo` não tem base de fusos sem o pacote; na imagem já existe o `tzdata` do Debian, então o pacote não muda nada lá. O fuso é o `FORECAST_TIMEZONE` de `ingestion/openmeteo.py`, para não haver duas fontes.
- **D8. Sem argumento `--date`.** A API de previsão só devolve a previsão atual, e o cliente exige que o primeiro dia da resposta seja `issued_at`; reprocessar um dia passado não é possível. "Reprocessável por data" aqui significa: reexecutar no mesmo dia completa o que faltou e não muda o que existe. A função do job aceita `today` para os testes.
- **D9. Faixas da checagem:** temperatura −10 a 50 °C (doc), precipitação e vento ≥ 0, umidade 0 a 100 %, `horizon_days` 1 a 7, nulos permitidos nas variáveis (a tabela aceita e a fonte às vezes omite).
- **D10. A CLI chama o job pelo atributo do módulo `ingestion.jobs`,** para o teste trocar a função com `monkeypatch` sem rede nem banco.
- **D11. Nomes:** `WEATHER_FORECAST_SCHEMA` (substantivo no fim, como `DAILY_VARIABLES`) e `PartialIngestionError`; mensagens e logs em inglês (ADR 0001).
- **D12. Comando registrado no `AGENTS.md`** neste PR, como os PRs anteriores fizeram.

Riscos:

- **R1. `pandera` e `pandas` 3.x.** O projeto fixa `pandas>=3.1.1`. Se a versão do `pandera` resolvida pelo `uv` não suportar pandas 3, o passo 0 falha. Nesse caso o implementador para e reporta; as saídas possíveis (versão do `pandera`, fixar `pandas`, ou trocar a biblioteca de checagem) mudam uma regra do `AGENTS.md` e são decisão do usuário.
- **R2. Memória:** pandas + pandera no job de 512 MB (`mem_limit` do serviço `jobs`). 28 linhas é trivial; o custo é o import. Medir no item 17 com `docker stats`.
- **R3. Horário da coleta e a virada do dia:** se o job rodar perto da meia-noite, o `issue_date` e o primeiro dia da API (também em `America/Sao_Paulo`) podem divergir por segundos; o cliente levanta `ValueError` e o local falha. Às 06:30 (PR 16) o risco é nulo.
- **R4. Bug que propaga (D3)** perde a execução inteira; aceitável, porque reexecutar no mesmo dia recupera.

Perguntas em aberto (não bloqueiam este PR):

- Horizonte 0 (ADR 0005, "em aberto"): se a cientista quiser, muda `expected_rows`, a faixa de `horizon_days`, o cliente e a tabela, e exige novo ADR ou emenda ao 0005.
- Aviso à ciência de dados de que a coleta vai começar: fica para o item 17, quando a tabela passa a ter dados em produção.

## 10. Decisões que exigem ADR

Nenhuma. O PR não muda `raw`/`ref` (usa a tabela da migração 0004 como está), não toca o contrato `build_features`/`predict`/`evaluate` e não publica porta. As regras que ele aplica já estão no ADR 0005 (`issued_at`, primeiro snapshot vence, horizontes 1 a 7) e no `AGENTS.md` (pandera). Só exigiria ADR se o R1 levar a trocar o pandera por outra biblioteca de checagem.
