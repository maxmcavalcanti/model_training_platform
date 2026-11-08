# 26 — Job `weather-observed`: janela de 10 dias até ontem, backfill por intervalo, checagem pandera e agenda 06:45

> Executa: agente. Depende de: 24 (na `main`, #40: `fetch_observed` e `ARCHIVE_URL` em `ingestion/openmeteo.py`), 25 (na `main`, #41: `raw.weather_observed`, migração `0007`), 16 (crontab do supercronic), 15 e 22 (padrões de job). Branch sugerida: `feat/job-weather-observed`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar com a suíte verde.
> Revisão 2026-11-08: alinhado à `main` em `fa7ba1b`. Substitui a versão anterior deste plano (nomes fora do padrão, janela terminando hoje, sem tratamento de timeout nem de erro malformado). Os valores de janela (10 dias), atraso máximo (7 dias) e fim da janela (ontem, BRT) vêm da D8 do plano 24 e são **provisórios** até o item 18 fechar (coleta em `/home/deploy/source-checks` na VPS). As perguntas com recomendação viraram decisões D1 a D14 (seção 9), por autorização do usuário para aceitar recomendações; o usuário pode revertê-las na revisão do plano.

## 1. Objetivo

Criar o subcomando `weather-observed`: para cada local de `ref.locations`, busca o clima observado (ERA5 via Open-Meteo) da janela dos últimos 10 dias terminando ontem (ou de `--start`/`--end`, para backfill), faz upsert em `raw.weather_observed`, relê o intervalo e termina com checagem pandera (faixas, continuidade por local, atraso).
Agendar a execução diária às 06:45 (America/Sao_Paulo) no crontab do supercronic, com janela, atraso e horário marcados como provisórios.

## 2. Fora do escopo

- Rodar o backfill desde 2015 em produção, mandar o aviso à cientista e marcar o checkbox "`raw.weather_observed` + backfill desde 2015" do roadmap (item 27, `docs/plans/27-backfill-observado-e-pronto-fase-2-manual.md`).
- Fechar o item 18 e ajustar os valores provisórios (janela, atraso, fim da janela, horário): PR pequeno posterior (D12).
- Mudar `raw.weather_observed` ou qualquer migração; mudar `ingestion/db.py`, `ingestion/http.py`, `ingestion/ons.py`, `ingestion/calendar_ref.py`.
- Mudar `fetch_forecast` ou `_validate` (previsão em produção), inclusive o mesmo envolvimento de erro malformado da D9: fica como follow-up (seção 9, riscos).
- Fixar o modelo da reanálise (`models=`), dividir o backfill em pedaços por ano (só se o critério manual de backfill falhar, ver D8 do plano 24 / D7 aqui), dados horários, outras variáveis, coluna de origem do dado.
- Lista de lacunas conhecidas da fonte (`known_gaps`, como no ONS): não há lacuna conhecida no ERA5; se o backfill achar alguma, vira plano à parte.
- Flow do Prefect (PR 32), alertas no Telegram (PR 55), qualquer item da Fase 3 em diante.
- Editar `tests/conftest.py`, testes existentes além dos dois listados na seção 4 (`tests/test_openmeteo_observed.py` e `tests/infra/test_crontab.py`, só acréscimos), `pyproject.toml`/`uv.lock` (nenhuma dependência nova), `infra/jobs/Dockerfile`, `infra/docker-compose.yml`, `.github/`, `.claude/`, `AGENTS.md` (a linha de comando nova em "Comandos" entra junto com o item 27, ver seção 9), ADRs, `docs/plataforma-ml.md` e outros planos.

## 3. Fase do roadmap

Fase 2 — "Clima", item "`raw.weather_observed` + backfill desde 2015" (`docs/plataforma-ml.md`, "Roadmap"). Este PR entrega o job, a checagem e a agenda; o backfill em produção é o item 27.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `tests/test_checks_weather_observed.py` | Novo (test-writer): checagem pura, sem banco nem rede (casos 1 a 12) |
| `tests/test_openmeteo_observed.py` | Alterar (test-writer, só acréscimo): erros malformados com `location_id` na mensagem (casos 13 a 16) |
| `tests/test_job_weather_observed.py` | Novo (test-writer): job com banco (`db`) e CLI sem banco (casos 17 a 43) |
| `tests/infra/test_crontab.py` | Alterar (test-writer, só acréscimo): linha `weather-observed` e espaçamento mínimo entre linhas (casos 44 a 48) |
| `ingestion/checks.py` | `WEATHER_OBSERVED_SCHEMA`, colunas de variáveis comuns com `WEATHER_FORECAST_SCHEMA` e `check_weather_observed(...)` |
| `ingestion/openmeteo.py` | `fetch_observed`: envolver `time` malformado e valor não numérico em `ValueError` com o `location_id` (D9) |
| `ingestion/jobs.py` | Constantes provisórias e `ingest_weather_observed(...)` |
| `ingestion/cli.py` | Subcomando `weather-observed [--start] [--end] [--days]` com timeout por tamanho do intervalo |
| `infra/cron/crontab` | Linha `45 6 * * * python -m ingestion weather-observed` com comentário de provisório |

Nenhum outro arquivo muda. `git diff --name-only main...HEAD` deve mostrar exatamente esses 9.

### Fonte e regras

`docs/plataforma-ml.md`, "Ingestão":

> | 06:45 | `ingest_weather_observed` | Upsert dos últimos 10 dias de clima observado (cobre atraso e correções da fonte) |
>
> Cada job é idempotente e reprocessável por data: rodar duas vezes o mesmo dia dá o mesmo resultado, e um backfill é só o mesmo job com um intervalo maior.
>
> Checagem depois de gravar: linhas esperadas por dia, sem nulos nas colunas-chave, valores dentro de faixas plausíveis (carga positiva, temperatura entre −10 e 50 °C)
>
> **Backfill inicial:** carga do ONS e clima observado desde 2015.

Item 18 (medição de 2026-11-08, ~11:50 BRT): o `archive` devolveu as 5 variáveis não nulas inclusive no dia corrente (atraso 0); o valor do dia corrente provavelmente não é final; **pendente** saber se valores recentes mudam de um dia para o outro.

Plano 24, D8 (valores **provisórios** para este PR): janela diária de **10 dias** (`start = end - 9`); atraso máximo tolerado **7 dias**; fim padrão da janela **ontem** (`end = hoje - 1`, BRT), porque o dia corrente é possivelmente parcial; a releitura com `on_conflict="update"` corrige os dias recentes nas execuções seguintes. Plano 24, D7: uma chamada por local para o intervalo inteiro (backfill de 2015 até ontem ≈ 4330 dias por local, 4 chamadas); cliente com timeout de 120 s no backfill.

Plano 25 (tabela na `main`): chave (`location_id`, `"date"`), chave estrangeira para `ref.locations`, variáveis `double precision` anuláveis, `ingested_at timestamptz NOT NULL` sem `DEFAULT` (quem carimba é o `upsert`), **sem `CHECK` de faixa** (a faixa é desta checagem), o `ingestor` tem `SELECT`, `INSERT`, `UPDATE` (sem `DELETE`/`TRUNCATE`). `"date"` vai entre aspas no SQL.

`.claude/rules/migrations-e-dados.md`:

> Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.

`AGENTS.md`: "Todo job termina com checagem de qualidade (pandera). Checagem falha = execução falha." Identificadores, logs, mensagens de erro e comentários de código em inglês (ADR 0001).

ADR 0004 (`docs/adr/0004-interim-operation-before-prefect.md`), trecho que pesa no horário:

> O build da imagem na VPS (1 vCPU, 1 GB de RAM, 2 GB de swap) é lento e pode usar swap. Não construir imagem com um job agendado em execução. Dois jobs ao mesmo tempo (por exemplo, backfill manual durante o job agendado) podem passar do `mem_limit`; a medição do checkpoint 28a confirma.

O serviço `scheduler` (`infra/docker-compose.yml`) tem `mem_limit: 512m`, compartilhado pelo supercronic e pelos jobs que ele dispara.

`.claude/rules/infra.md`: deploy só por merge na `main`; até o PR 39 o usuário atualiza a VPS à mão (ADR 0004). Nenhum agente aplica deploy.

### Código existente a usar (na `main`, `fa7ba1b`)

`ingestion/openmeteo.py` (o que existe; só `fetch_observed` muda, D9):

```python
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_TIMEZONE = "America/Sao_Paulo"
DAILY_VARIABLES = {"temperature_2m_max": "temp_max", "temperature_2m_min": "temp_min",
                   "precipitation_sum": "precip_mm", "wind_speed_10m_max": "wind_speed_max",
                   "relative_humidity_2m_mean": "humidity_mean"}
DAILY_UNITS = {...}  # °C, °C, mm, km/h, %

@dataclass(frozen=True)
class Location:
    location_id: str
    lat: float
    lon: float

def _daily_section(payload, location_id) -> dict: ...  # ValueError "<id>: ..." for shape, units, lengths

def fetch_observed(client, location, start, end, *, base_delay=1.0, sleep=time.sleep) -> pd.DataFrame:
    """Fetch observed daily weather for ``start..end`` as a frame ready for upsert.

    Days whose five variables are all null (not yet published) are dropped.
    """
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    params = {...}  # latitude, longitude, start_date, end_date, daily, timezone
    payload = fetch_json(client, ARCHIVE_URL, params, base_delay=base_delay, sleep=sleep)
    daily = _daily_section(payload, location.location_id)

    expected = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    received = [date.fromisoformat(day) for day in daily["time"]]          # <- D9
    for want, got in zip(expected, received, strict=False):
        if want != got:
            raise ValueError(f"{location.location_id}: expected day {want}, got {got}")
    if len(received) != len(expected):
        raise ValueError(f"{location.location_id}: expected {len(expected)} days "
                         f"from {start} to {end}, got {len(received)}")

    columns: dict[str, object] = {"location_id": [location.location_id] * len(expected),
                                  "date": expected}
    for name, column in DAILY_VARIABLES.items():
        columns[column] = pd.Series(daily[name], dtype="float64")         # <- D9
    frame = pd.DataFrame(columns)
    return frame.dropna(how="all", subset=list(DAILY_VARIABLES.values())).reset_index(drop=True)
```

Problema que a D9 resolve (follow-up do code-reviewer do PR 24): `date.fromisoformat("2026-13-01")` levanta `ValueError` sem o `location_id`; `date.fromisoformat(None)` levanta **`TypeError`**, que o `except (NetworkError, ValueError, httpx.HTTPError)` do job não pega, derrubando a execução inteira em vez de só o local; `pd.Series(["abc"], dtype="float64")` levanta `ValueError` sem `location_id`, e um valor como `{}` pode levantar `TypeError`.

`ingestion/http.py` (não alterar): `fetch_json(client, url, params=None, *, attempts=3, base_delay=1.0, sleep=time.sleep)` repete `httpx.TransportError`, 429 e 5xx esperando `base_delay * 2**n` (1 s, 2 s); outro status fora de 2xx levanta `httpx.HTTPStatusError` sem repetir; esgotado → `NetworkError`.

`ingestion/db.py` (não alterar): `upsert(conn, table, rows, keys, *, on_conflict="update", stamp_ingested_at=True) -> int` (inseridas + atualizadas; não faz commit; recusa `ingested_at` no DataFrame quando carimba; `NaN` vira `NULL`). `build_engine(url=None)` lê `DATABASE_URL`; sem ela, `MissingConfiguration`; criar o engine não conecta.

`ingestion/jobs.py` (trechos a espelhar; não mudar o que existe):

```python
class PartialIngestionError(RuntimeError):
    """Raised when the job saved what it could but some locations failed."""

def issue_date(now: datetime | None = None) -> date: ...  # date of now in America/Sao_Paulo

def list_locations(conn) -> list[Location]: ...  # ORDER BY location_id

def ingest_weather_forecast(engine, client, today, *, base_delay=1.0) -> int:
    with engine.connect() as conn:
        locations = list_locations(conn)
    frames, failed = [], []
    for location in locations:
        try:
            frames.append(fetch_forecast(client, location, today, base_delay=base_delay))
        except (NetworkError, ValueError, httpx.HTTPError) as error:
            logger.error("forecast failed for %s: %s", location.location_id, error)
            failed.append(location.location_id)
    inserted = 0
    if frames:
        with engine.begin() as conn:
            inserted = upsert(conn, _FORECAST_TABLE, pd.concat(frames, ignore_index=True),
                              keys=_FORECAST_KEYS, on_conflict="ignore")
    with engine.connect() as conn:
        stored = pd.read_sql_query(_REREAD_STATEMENT, conn, params={"today": today})
    check_error = None
    try:
        check(stored, WEATHER_FORECAST_SCHEMA, expected_rows=...)
    except CheckFailed as error:
        check_error = error
    if failed:
        message = f"forecast failed for locations: {', '.join(failed)}"
        if check_error is not None:
            message += f"; {check_error}"
        raise PartialIngestionError(message)
    if check_error is not None:
        raise check_error
    logger.info(...)
    return inserted

# Provisional until roadmap item 18 measures the ONS publication delay and revision depth.
ONS_WINDOW_DAYS = 30
ONS_MAX_DELAY_DAYS = 5

def ingest_ons_load(engine, client, start, end, *, max_delay_days=ONS_MAX_DELAY_DAYS, base_delay=1.0) -> int:
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    ...
```

`ingestion/checks.py` (trechos):

```python
class CheckFailed(RuntimeError): ...

def check(df, schema, expected_rows=None) -> None: ...   # one CheckFailed, "; ".join(problems)
def _describe(error: pandera.errors.SchemaErrors) -> str: ...  # "schema validation failed (N failure cases): col: check, ..."

def _temperature() -> pa.Column:
    return pa.Column(float, pa.Check.in_range(-10, 50), nullable=True)

def _min_not_above_max(df) -> pd.Series:
    return df["temp_min"].isna() | df["temp_max"].isna() | (df["temp_min"] <= df["temp_max"])

WEATHER_FORECAST_SCHEMA = pa.DataFrameSchema(
    {
        "location_id": pa.Column(nullable=False),
        "issued_at": pa.Column(nullable=False),
        "target_date": pa.Column(nullable=False),
        "horizon_days": pa.Column(int, pa.Check.in_range(1, 7), nullable=False),
        "temp_max": _temperature(),
        "temp_min": _temperature(),
        "precip_mm": pa.Column(float, pa.Check.ge(0), nullable=True),
        "wind_speed_max": pa.Column(float, pa.Check.ge(0), nullable=True),
        "humidity_mean": pa.Column(float, pa.Check.in_range(0, 100), nullable=True),
    },
    checks=pa.Check(_min_not_above_max, error="temp_min must not exceed temp_max"),
    unique=["location_id", "issued_at", "target_date"],
    strict=False,
)

def check_ons_daily_load(df, start, end, max_delay_days, *, known_gaps=ONS_KNOWN_GAPS) -> None:
    # schema problems + "no rows between <start> and <end>" + per-day count
    # + "missing dates: <iso>, ..." (from start to the last present date)
    # + "stale: last date <last> is older than <end - max_delay_days>"
    # all in a single CheckFailed("; ".join(problems))
```

`ingestion/cli.py` (padrão do `ons-load`, a espelhar):

```python
def _positive_int(value: str) -> int: ...  # < 1 -> argparse.ArgumentTypeError (exit 2)

def _add_ons_load_arguments(parser):
    from ingestion.jobs import ONS_WINDOW_DAYS
    parser.add_argument("--end", type=date.fromisoformat, help="last day (ISO), default today")
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--start", type=date.fromisoformat, help="first day (ISO)")
    window.add_argument("--days", type=_positive_int, default=ONS_WINDOW_DAYS,
                        help=f"window length in days ending at --end (default {ONS_WINDOW_DAYS})")

def _run_ons_load(args) -> int:
    from ingestion import jobs
    from ingestion.db import build_engine
    end = args.end or jobs.issue_date()
    start = args.start or end - timedelta(days=args.days - 1)
    engine = build_engine()
    try:
        with httpx.Client(timeout=60) as client:
            jobs.ingest_ons_load(engine, client, start, end)
    finally:
        engine.dispose()
    return 0

SUBCOMMANDS["ons-load"] = Subcommand(help=..., add_arguments=..., run=...)
```

Códigos: 0 sucesso; 1 qualquer exceção do `run` (traceback em stderr); 2 uso incorreto (argparse). Os testes substituem `ingestion.jobs.<função>` e `ingestion.jobs.issue_date` por `monkeypatch.setattr`, por isso o `run` importa `ingestion.jobs` dentro da função e chama `jobs.<nome>`.

`infra/cron/crontab` hoje:

```
# Interim schedule until Prefect (ADR 0004). Times are America/Sao_Paulo (TZ from the image).
# The forecast job snapshots "today" in America/Sao_Paulo: keep it far from midnight.
30 6 * * * python -m ingestion weather-forecast
# ons-load time and window are provisional until the ONS publication delay is measured (plan 22).
0 7 * * * python -m ingestion ons-load
```

`tests/infra/test_crontab.py` já tem `schedule_lines`, `split_line`, `COMMAND_FORM`, `FIXED_NUMBER`, `FORECAST_LINE`, `ONS_LOAD_LINE`, `forecast_line_problems`, `ons_load_line_problems` (molde a copiar) e as regras gerais (5 campos, subcomando conhecido em `SUBCOMMANDS`, minuto e hora fixos, nada nas horas 23 e 0, sem `>`/`|`, sem `NOME=valor`), cada uma com exemplos negativos.

### Padrões de teste a espelhar

- `tests/test_job_weather_forecast.py`: `_client(url, default, per_location)` que responde pelo local mais próximo de `latitude`/`longitude` da requisição (coordenadas lidas de `ref.locations` com `_coordinates(url)`); `_run_as_ingestor` com `create_engine(url, connect_args={"options": "-c role=ingestor"})`, `base_delay=0` e `engine.dispose()` no `finally`; fixture de escrita por teste:

```python
@pytest.fixture
def observed_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database
```

  `migrated_database` é só leitura: não usar para escrever. `alembic_config` vem de `tests.conftest`.
- `tests/test_job_ons_load.py`: classe de fonte falsa que registra as requisições; caso de `start > end` com engine fictício (`postgresql+psycopg://user:secret@127.0.0.1:1/none`) provando que nada conecta; CLI com `_fake_job(monkeypatch)` que substitui o job e `issue_date` e registra `(start, end)`; `_effective_code(argv)` = retorno de `main(argv)` ou `SystemExit.code`.
- `tests/test_openmeteo_observed.py`: `RECORDING`, `START`/`END`/`N` da fixture `tests/fixtures/openmeteo_archive_sao_paulo.json` (11 dias, 2026-10-29 a 2026-11-08), `LOCATION = Location("sao_paulo", -23.55, -46.63)`, `Harness`, `_payload()` (deep copy), `_expect_value_error(payload)`.
- Os 4 locais de `ref.locations`: `belem`, `porto_alegre`, `recife`, `sao_paulo` (ordem de `list_locations`).
- Resposta do arquivo nos testes do job: montada em memória para o intervalo pedido (`start_date`/`end_date` da requisição), no formato da fixture: `{"latitude": ..., "longitude": ..., "timezone": "America/Sao_Paulo", "daily_units": RECORDING["daily_units"], "daily": {"time": [...], "<variável>": [...]}}`, com valores plausíveis fixos (sugestão: `temperature_2m_max` 30.0, `temperature_2m_min` 20.0, `precipitation_sum` 1.0, `wind_speed_10m_max` 10.0, `relative_humidity_2m_mean` 70.0) e variações por local (status HTTP, dias nulos, valor alterado numa data, unidade errada, `time` malformado). Cada caso leva `# Case N` com o número da seção 8 (nos arquivos existentes, `# Plan 26, case N`).

## 5. Passos

0. (test-writer e implementer, antes de tudo) Confirme a base: `uv run alembic heads` mostra `0007 (head)`; `git log --oneline -1 -- migrations/versions/0007_raw_weather_observed.py` mostra um commit; `uv run python -c "from ingestion.openmeteo import fetch_observed, ARCHIVE_URL"` termina sem erro. Se algo falhar, **parar** e avisar o usuário.
1. (test-writer) Na branch `feat/job-weather-observed`, a partir da `main` atualizada, escreva `tests/test_checks_weather_observed.py`, `tests/test_job_weather_observed.py` e os acréscimos em `tests/test_openmeteo_observed.py` e `tests/infra/test_crontab.py` (seção 8). Rode `uv run pytest tests/test_checks_weather_observed.py tests/test_job_weather_observed.py tests/test_openmeteo_observed.py tests/infra/test_crontab.py` e confirme que falham por `ImportError` de `WEATHER_OBSERVED_SCHEMA`/`check_weather_observed`/`ingest_weather_observed`/`OBSERVED_WINDOW_DAYS`, por subcomando `weather-observed` inexistente, pela linha ausente no crontab e, nos casos 13 a 16, por mensagem sem `sao_paulo` ou por `TypeError`. Os casos 1 a 15 do plano 24 em `tests/test_openmeteo_observed.py` continuam verdes. `uv run ruff check .` e `uv run ruff format --check .` limpos. Commit `test: add weather-observed job tests`.
2. (implementer) Partindo da branch com os testes, `ingestion/checks.py`:
   1. Extraia as 5 colunas de variáveis de `WEATHER_FORECAST_SCHEMA` numa função privada (por exemplo `_weather_variable_columns() -> dict[str, pa.Column]`, devolvendo um dict novo a cada chamada) e use-a nos dois esquemas, junto com o mesmo `pa.Check(_min_not_above_max, error="temp_min must not exceed temp_max")`. Rode `uv run pytest tests/test_checks_weather_forecast.py tests/test_job_weather_forecast.py` e confirme verde antes de seguir (refatoração sem mudança de comportamento).
   2. `WEATHER_OBSERVED_SCHEMA`: `location_id` não nulo, `date` não nulo, as 5 variáveis (faixas iguais às da previsão: temperaturas −10 a 50, `precip_mm >= 0`, `wind_speed_max >= 0`, `humidity_mean` 0 a 100, todas anuláveis), `temp_min <= temp_max`, `unique=["location_id", "date"]`, `strict=False`.
   3. `check_weather_observed(df, location_ids, start, end, max_delay_days) -> None` (`location_ids: Sequence[str]`, os locais esperados): junta num único `CheckFailed` (`"; ".join(problems)`) os problemas do esquema (via `_describe`) e, para cada `location_id` de `location_ids`, na ordem recebida, calculados sobre as linhas desse local:
      - nenhuma linha → `<id>: no rows between <start> and <end>`;
      - datas faltando entre `start` e a maior data presente do local (inclusive) → `<id>: missing dates: <iso>, <iso>` (D4);
      - maior data do local < `end - max_delay_days` → `<id>: stale: last date <maior> is older than <end - max_delay_days>` (D3).
      Linhas de `location_id` fora de `location_ids` são ignoradas por essas regras (o esquema ainda vale para elas).
3. `ingestion/openmeteo.py`, só dentro de `fetch_observed` (D9): envolva a conversão de `daily["time"]` em `try/except (TypeError, ValueError)` → `raise ValueError(f"{location.location_id}: malformed daily 'time': {error}") from error`; envolva a conversão de cada variável (`pd.Series(..., dtype="float64")`) do mesmo jeito → `ValueError(f"{location.location_id}: non-numeric value in daily '{name}': {error}")`. Mantenha as mensagens e a ordem das validações existentes. Rode `uv run pytest tests/test_openmeteo_observed.py tests/test_openmeteo_forecast.py -m "not db"` e confirme verde.
4. `ingestion/jobs.py`, nova seção depois do ONS, com comentário em inglês dizendo que os valores são provisórios até o item 18 (plano 24, D8):
   - `OBSERVED_WINDOW_DAYS = 10`, `OBSERVED_MAX_DELAY_DAYS = 7`, `OBSERVED_END_LAG_DAYS = 1` (a janela padrão termina ontem). Tabela `"raw.weather_observed"`, chaves `["location_id", "date"]`.
   - Releitura: `SELECT location_id, "date", temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean FROM raw.weather_observed WHERE "date" BETWEEN :start AND :end ORDER BY location_id, "date"`.
   - Importe `fetch_observed` de `ingestion.openmeteo` e `WEATHER_OBSERVED_SCHEMA` não é necessário no job (a checagem o usa); importe `check_weather_observed` de `ingestion.checks`.
5. `ingest_weather_observed(engine, client, start, end, *, max_delay_days=OBSERVED_MAX_DELAY_DAYS, base_delay=1.0) -> int`, docstring em inglês:
   1. `start > end` → `ValueError(f"start {start} is after end {end}")` antes de qualquer conexão ou requisição.
   2. `list_locations` numa conexão; para cada local, `fetch_observed(client, location, start, end, base_delay=base_delay)`; `except (NetworkError, ValueError, httpx.HTTPError)` → `logger.error("observed weather failed for %s: %s", location_id, error)` e anota o local (D5). Uma requisição por local para o intervalo inteiro (D7).
   3. Concatena os frames; se houver linhas, numa transação (`engine.begin()`): `upsert(conn, "raw.weather_observed", frame, keys=["location_id", "date"], on_conflict="update")`. Commit antes da checagem (grava e depois checa, como os outros jobs).
   4. Relê `start..end` numa conexão nova e chama `check_weather_observed(stored, [l.location_id for l in locations], start, end, max_delay_days)`, capturando `CheckFailed`.
   5. Se algum local falhou → `PartialIngestionError(f"observed weather failed for locations: {', '.join(failed)}" + (f"; {check_error}" se houver))`; senão, se a checagem falhou, relança o `CheckFailed`.
   6. `logger.info("weather-observed ok: %d locations, %d rows written from %s to %s", ...)` e devolve o número do `upsert` (0 se nada foi escrito).
6. `ingestion/cli.py`, subcomando `weather-observed` (help: `Upsert observed weather (ERA5 archive) into raw.weather_observed (rolling window ending yesterday or --start/--end backfill)`):
   - `--end` (`type=date.fromisoformat`, help `last day (ISO), default yesterday`); grupo mutuamente exclusivo `--start` (`type=date.fromisoformat`) e `--days` (`type=_positive_int`, padrão `OBSERVED_WINDOW_DAYS`).
   - `end = args.end or jobs.issue_date() - timedelta(days=jobs.OBSERVED_END_LAG_DAYS)`; `start = args.start or end - timedelta(days=args.days - 1)`.
   - Timeout (D8): `(end - start).days + 1 > jobs.OBSERVED_WINDOW_DAYS` → `httpx.Client(timeout=120)`; senão `httpx.Client(timeout=30)`. Se `start > end`, use 30 (o job vai levantar `ValueError` antes de qualquer requisição). Constantes privadas no módulo da CLI, por exemplo `_OBSERVED_TIMEOUT_SECONDS = 30` e `_OBSERVED_BACKFILL_TIMEOUT_SECONDS = 120`.
   - Chama `jobs.ingest_weather_observed(engine, client, start, end)`; `engine.dispose()` no `finally`; devolve 0.
   - `--start` depois de `--end` → `ValueError` do job → código 1 (D10).
7. `infra/cron/crontab`: entre a linha do forecast e o comentário do ONS, acrescente `# weather-observed window, delay and time are provisional until the ERA5 delay and revisions are measured (plan 26).` e `45 6 * * * python -m ingestion weather-observed`.
8. Rode os critérios de pronto, refatore com a suíte verde e cole comandos e saídas no PR. No corpo do PR, liste D1 a D14 e destaque que D2, D3 e D11 são provisórios.

## 6. Critérios de pronto

Precisa do Postgres de teste: `docker compose -f infra/docker-compose.dev.yml up -d`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_checks_weather_observed.py tests/test_job_weather_observed.py tests/test_openmeteo_observed.py tests/infra/test_crontab.py` | Todos passam, nenhum `skipped` |
| `uv run pytest tests/test_checks_weather_forecast.py tests/test_job_weather_forecast.py tests/test_openmeteo_forecast.py tests/test_job_ons_load.py tests/test_checks_ons_load.py tests/test_cli.py` | Todos passam, sem edição desses arquivos |
| `uv run python -m ingestion weather-observed --help` | Lista `--start`, `--end` e `--days`; código 0 |
| `uv run python -m ingestion weather-observed --days 0; echo $?` | Erro de uso; `2` |
| Banco local migrado (`uv run alembic upgrade head`), `DATABASE_URL` apontando para ele, com rede: `uv run python -m ingestion weather-observed; echo $?` | `0` (se der `1`, colar a mensagem no PR; não mexer nas constantes provisórias sem combinar) |
| Em seguida: `uv run python -c "import sqlalchemy as sa; from ingestion.db import build_engine; e = build_engine(); print(e.connect().execute(sa.text('select location_id, count(*), min(\"date\"), max(\"date\") from raw.weather_observed group by 1 order by 1')).all())"` | 4 locais; `min` = ontem − 9 dias; `max` = ontem (ou até 7 dias antes, se a fonte atrasar); `count` = `max - min + 1` em cada local |
| Rodar o job de novo e repetir a consulta | Mesmos números |
| Backfill curto com rede: `uv run python -m ingestion weather-observed --start 2015-01-01 --end 2015-12-31; echo $?` e `select count(*) from raw.weather_observed where "date" between '2015-01-01' and '2015-12-31'` (mesmo comando `python -c` acima) | `0`; `1460` |
| (manual, com rede, opcional mas recomendado) `uv run python -m ingestion weather-observed --start 2015-01-01; echo $?` | `0` em poucos minutos; anotar no PR o tempo; se houver timeout ou 4xx, anotar no PR e não dividir por ano sem combinar (D7) |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` e `docker run --rm platform-jobs supercronic -test /app/infra/cron/crontab; echo $?` | `0` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| `git diff --name-only main...HEAD` | Só os 9 arquivos da seção 4 |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: janela até ontem, reescrita de valores corrigidos pela fonte, falha parcial por local, continuidade e atraso por local, timeout por tamanho do intervalo e o envolvimento dos erros malformados são lógica nova que decide o que entra no "real" dos modelos.

## 8. Casos de teste

Datas padrão: hoje (BRT) = 2026-11-08; `END` = 2026-11-07 (ontem); `START` = 2026-10-29 (`END` − 9); `max_delay_days = 7` (limite de atraso = 2026-10-31) salvo indicação. "Grade" = todos os dias de um intervalo × os 4 locais, com valores plausíveis.

Checagem pura (`tests/test_checks_weather_observed.py`, sem banco; `location_ids = ["belem", "porto_alegre", "recife", "sao_paulo"]`):

1. Grade de `START` a `END` (40 linhas) → passa.
2. `sao_paulo` sem 2026-11-02 (os outros completos) → `CheckFailed` cuja mensagem contém `sao_paulo` e `2026-11-02`.
3. `recife` começando em 2026-10-31 (faltam 10-29 e 10-30) → `CheckFailed` contendo `recife`, `2026-10-29` e `2026-10-30`.
4. Atraso: todos os locais até 2026-10-31 → passa; `belem` até 2026-10-30 e os outros completos → `CheckFailed` contendo `stale` e `belem`.
5. `porto_alegre` sem nenhuma linha → `CheckFailed` contendo `porto_alegre` e `no rows`.
6. DataFrame vazio (com as colunas) → `CheckFailed` que cita os 4 locais com `no rows`.
7. Faixas, cada uma numa linha só (parametrizado) → `CheckFailed` cuja mensagem contém a coluna: `temp_max = 51.0` → `temp_max`; `temp_min = -11.0` → `temp_min`; `precip_mm = -0.1` → `precip_mm`; `wind_speed_max = -1.0` → `wind_speed_max`; `humidity_mean = 101.0` → `humidity_mean`.
8. `temp_min = 25.0` com `temp_max = 20.0` num dia → `CheckFailed` contendo `temp_min must not exceed temp_max`.
9. Nulos parciais: `humidity_mean` `NaN` num dia e `temp_max` `NaN` em outro → passa.
10. Linha duplicada (`sao_paulo`, 2026-11-01) → `CheckFailed`; `location_id` nulo numa linha → `CheckFailed`.
11. Dois problemas ao mesmo tempo (`recife` sem 2026-11-02 e `temp_max = 80.0` em `belem`) → um único `CheckFailed` que cita `2026-11-02` e `temp_max`.
12. Backfill: grade de 2015-01-01 a 2015-12-31, `start`/`end` iguais a esses → passa (o atraso conta a partir de `end`, não de hoje).

Cliente (`tests/test_openmeteo_observed.py`, acréscimos; fixture, `START`/`END` e `LOCATION` do arquivo; sem rede):

13. `daily.time[3]` trocado por `"2026-13-01"` → `ValueError` cuja mensagem contém `sao_paulo`.
14. `daily.time[3]` trocado por `None` → `ValueError` (não `TypeError`) cuja mensagem contém `sao_paulo`.
15. `daily.temperature_2m_max[2]` trocado por `"abc"` → `ValueError` cuja mensagem contém `sao_paulo` e `temperature_2m_max`.
16. `daily.precipitation_sum[2]` trocado por `{}` → `ValueError` (não `TypeError`) cuja mensagem contém `sao_paulo` e `precipitation_sum`.

Job com banco (`tests/test_job_weather_observed.py`, `db`, como `ingestor`, `base_delay=0`, `start = START`, `end = END` salvo indicação):

17. Todos os locais respondem a grade → devolve 40; 40 linhas, 10 por local, de 2026-10-29 a 2026-11-07; `ingested_at` não nulo; 4 requisições, uma por local, todas com `start_date=2026-10-29` e `end_date=2026-11-07`.
18. Repetir o caso 17 com as mesmas respostas → continua 40 linhas, mesmos valores.
19. Segunda execução com `precipitation_sum` de `recife` em 2026-11-05 mudado de 1.0 para 7.5 → banco com 7.5 nessa linha; `ingested_at` dela maior que o da primeira escrita; as outras 39 linhas com os mesmos valores; total 40.
20. Atraso da fonte: os 5 últimos dias (2026-11-03 a 2026-11-07) com as 5 variáveis nulas em todos os locais → devolve 20; 20 linhas; sem erro (última data 2026-11-02 ≥ 2026-10-31).
21. Mesmo cenário do caso 20 com `max_delay_days=3` → `CheckFailed` contendo `stale`; as 20 linhas ficam gravadas.
22. Releitura limitada ao intervalo: antes do job, o admin insere em `raw.weather_observed` uma linha de `sao_paulo` em 2026-10-20 com `temp_max = 80.0` (`ingested_at = now()`); o job do caso 17 → passa, devolve 40, e a linha de 2026-10-20 continua igual.
23. `belem` responde 503 três vezes → `PartialIngestionError` contendo `belem`; 30 linhas (os outros 3 locais, 10 cada); nenhuma linha de `belem`; 3 requisições para `belem`.
24. Depois do caso 23, nova execução com todos respondendo → 40 linhas; as 30 de antes com os mesmos valores.
25. `recife` responde 400 (`{"error": true, "reason": "..."}`) → `PartialIngestionError` contendo `recife`; 30 linhas; 1 requisição para `recife` (sem retry).
26. `recife` com `daily_units.wind_speed_10m_max = "m/s"` → `PartialIngestionError` contendo `recife`; 30 linhas.
27. `porto_alegre` com `None` numa posição de `daily.time` e `sao_paulo` com `"abc"` numa variável → `PartialIngestionError` (não `TypeError`) contendo `porto_alegre` e `sao_paulo`; 20 linhas (`belem` e `recife`).
28. `sao_paulo` com as 5 variáveis nulas em 2026-11-02 (dia do meio) → `CheckFailed` contendo `sao_paulo` e `2026-11-02`; 39 linhas gravadas.
29. `temperature_2m_min = 25.0` e `temperature_2m_max = 20.0` em 2026-11-01 para `belem` → `CheckFailed` contendo `temp_min must not exceed temp_max`; 40 linhas gravadas, inclusive a ruim.
30. Falha de local e de checagem juntas: `belem` 503 três vezes e `sao_paulo` com `temperature_2m_max = 80.0` num dia → `PartialIngestionError` cuja mensagem contém `belem` e `temp_max`; 30 linhas.
31. Todos os locais respondem 503 sobre uma tabela que já tem as 40 linhas do caso 17 → `PartialIngestionError` contendo os 4 locais; as 40 linhas continuam com os mesmos valores e o mesmo `ingested_at`.
32. Backfill `start = 2015-01-01`, `end = 2015-12-31` → devolve 1460; 1460 linhas; 4 requisições, uma por local, cada uma com `start_date=2015-01-01` e `end_date=2015-12-31`.
33. (sem banco) `start = 2026-11-08`, `end = 2026-11-01`, engine fictício → `ValueError` cuja mensagem contém `2026-11-08` e `2026-11-01`; nenhuma requisição.

CLI (`tests/test_job_weather_observed.py`, sem banco; job e `issue_date` substituídos, `issue_date` = 2026-11-08; o job falso registra `(start, end)` e `client.timeout.read`):

34. `weather-observed` → código 0; o job recebe `(2026-10-29, 2026-11-07)`; timeout 30.
35. `weather-observed --days 3` → `(2026-11-05, 2026-11-07)`; timeout 30.
36. `weather-observed --start 2015-01-01 --end 2015-12-31` → exatamente essas datas; timeout 120.
37. `weather-observed --start 2015-01-01` → `(2015-01-01, 2026-11-07)`; timeout 120.
38. `weather-observed --end 2026-01-31` → `(2026-01-22, 2026-01-31)`.
39. Timeout no limite: `--days 10` → 30; `--days 11` → 120.
40. `--start 2026-11-01 --days 5` → código 2; `--days 0` → código 2; `--start 2026-13-01` → código 2; em todos, o job não é chamado.
41. Job levanta `CheckFailed` → código 1; job levanta `PartialIngestionError` → código 1.
42. `weather-observed --start 2026-02-01 --end 2026-01-01`, com `DATABASE_URL` fictícia e o job real → código 1 e `ValueError` no stderr.
43. Sem `DATABASE_URL` → código 1 e `DATABASE_URL` no stderr.

Crontab (`tests/infra/test_crontab.py`, acréscimos):

44. Existe exatamente uma linha `weather-observed`, igual a `45 6 * * * python -m ingestion weather-observed` (espaços normalizados), sem argumentos; as linhas do forecast (`30 6 * * *`) e do `ons-load` (`0 7 * * *`) continuam iguais.
45. Exemplos negativos de `weather_observed_line_problems`: lista vazia; só `FORECAST_LINE`; linha duplicada; `30 6 * * *`; `0 7 * * *`; `45 7 * * *`; `45 6 * * 1-5`; com `--days 10` → todos com problema; a linha esperada sozinha e junto das outras duas → sem problema.
46. As regras gerais (5 campos, subcomando conhecido, hora fixa, longe da meia-noite, sem redirecionamento) passam para a linha nova.
47. Espaçamento (D11): no crontab real, quaisquer duas linhas estão a pelo menos 15 minutos uma da outra (minuto do dia = hora × 60 + minuto).
48. Exemplos de `spacing_problems(lines, min_minutes=15)`: as três linhas reais → sem problema; `30 6` e `40 6` → problema; duas linhas no mesmo horário → problema; `30 6` e `45 6` → sem problema.

Já existentes que continuam verdes sem edição: `tests/test_checks_weather_forecast.py` (rede da refatoração do esquema), `tests/test_job_weather_forecast.py`, `tests/test_openmeteo_forecast.py`, casos 1 a 15 de `tests/test_openmeteo_observed.py`, `tests/test_raw_weather_observed.py`, `tests/test_job_ons_load.py`, `tests/test_checks_ons_load.py`, `tests/test_cli.py`, `tests/infra/test_jobs_image.py`, `tests/infra/test_compose.py` e os testes existentes de `tests/infra/test_crontab.py`.

## 9. Riscos e perguntas em aberto

Nenhuma pergunta em aberto bloqueia. Decisões (recomendações adotadas, com autorização do usuário; o implementador as declara no corpo do PR):

- **D1. Um subcomando para o diário e o backfill.** O doc diz "um backfill é só o mesmo job com um intervalo maior"; o item 27 roda `weather-observed --start 2015-01-01`.
- **D2. Janela padrão de 10 dias terminando ontem (BRT), provisória.** `end = issue_date() - OBSERVED_END_LAG_DAYS` (1), `start = end - 9`. O dia corrente é possivelmente parcial (item 18); a reescrita diária corrige os dias recentes. "Hoje" vem de `jobs.issue_date()` (mesmo fuso do crontab e do dia de `date`, ADR 0005).
- **D3. Atraso máximo de 7 dias, provisório, contado a partir de `end` e por local.** Folgado de propósito (plano 24, D8): não alarma se o Open-Meteo deixar de preencher os dias recentes. Contar a partir de `end` faz o backfill de 2015 passar (caso 12), como no ONS.
- **D4. Continuidade por local, de `start` até a maior data do local.** Buraco no início ou no meio falha (o cliente descarta dias inteiramente nulos, plano 24 D3, e é aqui que o buraco aparece); o fim aberto é coberto pelo atraso. Local sem nenhuma linha no intervalo falha com `no rows`.
- **D5. Falha por local como no job de previsão.** Erro de rede, de validação ou HTTP num local não impede os outros; grava o que veio, checa, e termina com `PartialIngestionError` citando os locais (e o resultado da checagem, se também falhou). Diferente do ONS, que propaga na hora, porque aqui há 4 fontes independentes.
- **D6. `on_conflict="update"` e grava antes de checar.** O observado é reescrito na janela (plano 25, D3); o dado recebido fica gravado para diagnóstico mesmo se a checagem falhar (a tabela não tem `CHECK`, plano 25 D4).
- **D7. Uma requisição por local para o intervalo inteiro, sem dividir em pedaços.** Plano 24, D7: 4 chamadas no backfill. Se o critério manual (`--start 2015-01-01`) der timeout ou 4xx, a divisão por ano vira PR à parte.
- **D8. Timeout por tamanho do intervalo: 30 s até 10 dias, 120 s acima.** O plano 24 pede 120 s no backfill. Usar 120 s também no diário faria o pior caso (4 locais × 3 tentativas × 120 s + esperas ≈ 24 min) passar das 07:00 e coincidir com o `ons-load`, que é o que o ADR 0004 manda evitar. Com 30 s o pior caso diário fica em ≈ 6 min (4 × (3 × 30 + 1 + 2) s).
- **D9. Erros malformados do cliente viram `ValueError` com o `location_id`, só em `fetch_observed`.** Follow-up do code-reviewer do PR 24. Além da mensagem, corrige um defeito: `TypeError` (por `None` em `time` ou valor não numérico de tipo estranho) escaparia do `except` do job e derrubaria todos os locais. O mesmo ajuste em `fetch_forecast` fica fora (previsão em produção; ver riscos).
- **D10. `--start` depois de `--end` → código 1 (`ValueError` do job), não 2.** Mesmo comportamento do `calendar` e do `ons-load`.
- **D11. 06:45, provisório, com espaçamento mínimo de 15 minutos testado.** É o horário do doc, a 15 min do forecast (06:30) e do `ons-load` (07:00). Execuções normais levam segundos (4 respostas JSON pequenas); o pior caso com timeout de 30 s (≈ 6 min, D8) termina antes do próximo job, então o `mem_limit` de 512 MB do `scheduler` não é disputado por dois jobs. O teste de espaçamento (casos 47 e 48) impede que um ajuste futuro de horário encoste dois jobs. Alternativa avaliada e descartada: mover para 06:50 (encurta a folga antes do `ons-load`) ou 07:15 (adia o "real" sem ganho). Se o checkpoint 28a mostrar que algum job demora mais, o horário muda num PR pequeno.
- **D12. Ajuste pós-item 18 é PR separado.** Muda só as constantes `OBSERVED_*`, a linha do crontab e os testes que as fixam.
- **D13. Faixas iguais às da previsão (refatoradas para uma função comum).** A cientista compara previsão e observado coluna a coluna (plano 24, D1). Sem teto de chuva nem de vento: não há limite no doc; um valor absurdo de chuva passa (ver riscos).
- **D14. Testes em quatro arquivos.** Checagem pura separada (como `tests/test_checks_ons_load.py`), job e CLI juntos (como `tests/test_job_ons_load.py`), acréscimos no teste do cliente e no do crontab.

Riscos:

- **Valores provisórios.** Se o ERA5 do Open-Meteo revisar além de 10 dias, a janela não absorve; mitigação até o item 18: `weather-observed --days N` ou `--start`. Se o atraso real passar de 7 dias, o job falha todo dia até o ajuste; sem alertas (PR 55), a falha só aparece no log do `scheduler`.
- **Dias recentes podem não ser ERA5** (plano 24, riscos): podem mudar dentro da janela; é o motivo do `update`.
- **Mensagem de continuidade grande** num backfill com muitos dias faltando (lista todas as datas). Aceito: só acontece em falha real e ajuda o diagnóstico.
- **`fetch_forecast` tem o mesmo defeito da D9** (`TypeError` com `time` malformado derruba todos os locais). Follow-up recomendado: PR pequeno no cliente da previsão, com testes, depois deste.
- **Valor booleano numa variável** (`true`) vira 1.0 sem erro na conversão para `float64`; improvável na API e coberto pela checagem só se sair da faixa.
- **Backfill manual concorrendo com o agendado** pode passar do `mem_limit` (ADR 0004): o item 27 deve rodá-lo fora de 06:25–07:15 (ver abaixo).
- **Linha que a fonte deixa de publicar** não é apagada (`ingestor` sem `DELETE`); correção manual pelo admin.
- **Postgres de teste:** sem o container, os testes `db` falham (não pulam), por desenho de `tests/conftest.py`.

### Ajustes necessários no plano 27 (tarefa à parte, só `docs/**`; não editados aqui)

`docs/plans/27-backfill-observado-e-pronto-fase-2-manual.md` precisa de ajuste:

1. Backfill: trocar `--start 2015-01-01 --end $(date +%F)` por `--start 2015-01-01` (o fim padrão é ontem em BRT, D2). `$(date +%F)` usa o fuso do host da VPS (provavelmente UTC) e incluiria o dia corrente, possivelmente parcial.
2. Rodar o backfill fora da janela 06:25–07:15 BRT e nunca durante `docker compose build` (ADR 0004, memória); registrar o tempo da execução (4 requisições, timeout de 120 s).
3. Verificação: além de `min = 2015-01-01` e contagens iguais, exigir `max("date")` = ontem (ou dentro de 7 dias) e `count(*) = max - min + 1` por local (continuidade).
4. Logs: conferir uma linha `weather-observed ok` por dia no `scheduler` (`docker compose -f infra/docker-compose.yml logs --since 168h scheduler | grep "weather-observed ok"`), além do grep de erros.
5. Enviar à cientista o aviso das seções 9 dos planos 24 e 25 (colunas, unidades, célula de grade ERA5, últimos 10 dias podem mudar).
6. Fechar o checkbox "`raw.weather_observed` + backfill desde 2015" em `docs/plataforma-ml.md` (com data e números, como o item do ONS) e acrescentar a linha `weather-observed` em "Comandos" do `AGENTS.md` (esta última não é só `docs/**`: passa pelos dois revisores).

## 10. Decisões que exigem ADR

- **Nenhum ADR novo.** A tabela e o modo `update` estão cobertos pelo ADR 0005 e pelo plano 25; o agendamento pelo supercronic, pelo ADR 0004 (o espaçamento da D11 segue a restrição de memória dele); nada é exposto na rede (ADR 0003); nomes seguem o ADR 0001; nenhuma dependência nova (ADR 0002). Não muda schema de `raw`/`ref` nem o contrato `build_features`/`predict`/`evaluate`.
- Passariam a exigir ADR (ou emenda ao 0005), mergeado antes da implementação: guardar a origem ou a versão das revisões do ERA5 (coluna nova), mudar o fuso que define `date` ou passar a guardar o observado "como publicado" (sem `UPDATE`).
