# 14 — Cliente da previsão do Open-Meteo (com retry)

> Executa: agente. Depende de: 08 (na `main`; `ingestion/db.py` com `upsert`). Também usa a tabela do 13 (na `main` em `b8bc1d7`, #24) num teste de integração. Branch sugerida: `feat/openmeteo-forecast`.
> **Antecipado** (Fase 2 antes do fim da Fase 1; desvio de "uma fase por vez" aprovado pelo usuário em 2026-11-07, P5 resolvida).
> TDD: passo 0 (dependência) → test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-08: alinhado à `main` em `b8bc1d7` (migração `0004` `raw.weather_forecast`, head `0004`; ADR 0005; contrato do `upsert` em `ingestion/db.py`; fixtures de `tests/conftest.py`; `ref.locations` com as 4 capitais). As perguntas que tinham recomendação foram fechadas como decisões D1 a D9 (seção 9), por autorização do usuário. Não há pergunta aberta que bloqueie.

## 1. Objetivo

Buscar na API de previsão do Open-Meteo a previsão diária de um local e devolver um DataFrame pronto para `upsert` em `raw.weather_forecast` (horizontes 1 a 7, `issued_at` = dia em `America/Sao_Paulo`), com retry e backoff só para erro de rede.
Não grava nada em produção: quem grava é o job do PR 15.

## 2. Fora do escopo

- Gravar no banco pelo job, checagem pandera, subcomando de CLI, leitura de `ref.locations` (`list_locations`) e o cálculo de `today` com `ZoneInfo` (todos do PR 15).
- API de histórico/arquivo `archive-api.open-meteo.com` e `fetch_observed` (PR 24).
- Leitura do parquet do ONS (PR 20); aqui só nasce o `fetch_bytes` que ele vai usar.
- Horizonte 0 e horizontes acima de 7 (ADR 0005 e decisão D2 do plano 13: 1 a 7).
- Respeitar o cabeçalho `Retry-After` do 429 (D5).
- Backfill de previsões passadas, API "Historical Forecast" (P10 no índice).
- Alterar `ingestion/db.py`, `ingestion/cli.py`, `tests/conftest.py`, migrações, `infra/`, `.github/workflows/ci.yml`, `AGENTS.md`, `.claude/` ou outros planos (o ajuste de nomes no plano 24 é tarefa à parte, seção 9).

## 3. Fase do roadmap

Fase 2 — Clima, item "`raw.weather_forecast` coletando todo dia (prioridade)" (`docs/plataforma-ml.md`, "Roadmap"), antecipado pela P5.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Dependência de produção `httpx` (passo 0). Sem `tenacity` (D4) |
| `ingestion/http.py` | Novo: `NetworkError`, `fetch_json` e `fetch_bytes` com retry e backoff só para erro de rede |
| `ingestion/openmeteo.py` | Novo: `Location`, `FORECAST_URL`, `FORECAST_TIMEZONE`, `DAILY_VARIABLES`, `DAILY_UNITS`, `fetch_forecast` |
| `tests/fixtures/openmeteo_forecast_sao_paulo.json` | Novo: resposta real gravada uma vez (test-writer). O PR 15 reusa |
| `tests/test_http.py` | Novo: testes do retry (test-writer) |
| `tests/test_openmeteo_forecast.py` | Novo: testes do cliente, incluindo um teste `db` de integração com `raw.weather_forecast` (test-writer) |

### Fonte, job e regras

`docs/plataforma-ml.md`, "Fontes de dados": Open-Meteo previsão, `api.open-meteo.com/v1/forecast`, sem chave, previsão diária de temperatura máx/mín, chuva, vento, umidade, até 16 dias; gratuito para uso não comercial, ~10 mil chamadas/dia.
`docs/plataforma-ml.md`, "Ingestão": `06:30 ingest_weather_forecast` — "Snapshot da previsão para os próximos 7 dias, um registro por local e data-alvo, com `issued_at` = hoje". Regra de todos os jobs: "Retry com backoff para erro de rede (3 tentativas)".

`.claude/rules/migrations-e-dados.md`:

> - Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.
> - `raw.weather_forecast` guarda a previsão como emitida (`issued_at`). Nunca sobrescrever uma previsão antiga com uma nova.

ADR 0005 (`docs/adr/0005-data-contract-v1.md`), trechos que este cliente precisa respeitar:

> Em `raw.weather_forecast`, `issued_at` é do tipo `date`: o dia em que o snapshot da previsão foi tirado, não um instante. [...] quando o job roda de novo no mesmo dia **o primeiro snapshot vence** (insert que ignora o conflito, nunca sobrescreve).
>
> `horizon_days` é a distância em dias entre `target_date` e `issued_at`, e o job grava os horizontes de **1 a 7**.
>
> `location_id` é texto em slug minúsculo [...] por exemplo `sao_paulo`, `porto_alegre`, `recife`, `belem`. [...] `ref.locations` não tem coluna `timezone`: o dia dos dados de clima é `America/Sao_Paulo`, definido pelos jobs.

Nomes (ADR 0001, `docs/adr/0001-english-naming-convention.md`): `fetch_json`, `fetch_bytes`, `attempts`, `base_delay`, `NetworkError`, `Location`, `fetch_forecast`, `FORECAST_URL`, fixture `openmeteo_forecast_sao_paulo.json`, teste `test_openmeteo_forecast`, branch `feat/openmeteo-forecast`. Todo identificador, mensagem de erro e comentário em inglês; o mapa antigo `VARIAVEIS` deste plano passa a se chamar `DAILY_VARIABLES` (D9).

### Tabela de destino (`migrations/versions/0004_raw_weather_forecast.py`, na `main`, não alterar)

```sql
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
-- e: REVOKE UPDATE ON raw.weather_forecast FROM ingestor
```

Consequências para o DataFrame do cliente: **não** traz `horizon_days` (coluna gerada; informá-la falha com `428C9`) nem `ingested_at` (o `upsert` carimba e recusa a coluna no DataFrame); `location_id` precisa existir em `ref.locations`; `target_date - issued_at` precisa estar entre 1 e 7, ou o banco recusa com `23514`.

### `ref.locations` (`migrations/versions/0003_ref_locations.py`, na `main`)

| `location_id` | `name` | `lat` | `lon` | `subsystem` |
| --- | --- | --- | --- | --- |
| `sao_paulo` | São Paulo | -23.55 | -46.63 | SE |
| `porto_alegre` | Porto Alegre | -30.03 | -51.23 | S |
| `recife` | Recife | -8.05 | -34.88 | NE |
| `belem` | Belém | -1.46 | -48.49 | N |

As 4 estão em UTC-3, sem horário de verão. A `Location` deste PR só carrega `location_id`, `lat` e `lon`; o PR 15 monta a lista a partir dessa tabela.

### Contrato do `upsert` (`ingestion/db.py`, na `main`, não alterar)

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

Ele reflete a tabela, recusa coluna do DataFrame que não exista nela, recusa `ingested_at` no DataFrame quando carimba, recusa chaves duplicadas no DataFrame e converte `NaN` em `NULL` (`rows.astype(object).where(rows.notna(), None)`). O PR 15 chamará `upsert(conn, "raw.weather_forecast", df, keys=["location_id", "issued_at", "target_date"], on_conflict="ignore")`; o caso 22 da seção 8 prova que a saída de `fetch_forecast` entra assim, como `ingestor`.

### Fixtures e padrões de teste existentes (não alterar)

`tests/conftest.py`:

- `migrated_database` (sessão): banco em `head`, compartilhado e **só leitura**.
- `fresh_database` (por teste): banco vazio, apagado no teardown. Teste que escreve usa um fixture próprio sobre ele, como em `tests/test_raw_weather_forecast.py`:

```python
@pytest.fixture
def forecast_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database
```

- `alembic_config()` é função importada de `tests.conftest`. Para agir como papel: `SET ROLE ingestor` na mesma conexão, como `_upsert_as` em `tests/test_raw_weather_forecast.py`:

```python
def _upsert_as(url: str, role: str, frame: pd.DataFrame, on_conflict: str) -> int:
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text(f"SET ROLE {role}"))
            written = upsert(connection, TABLE, frame, keys=KEYS, on_conflict=on_conflict)
            connection.commit()
            return written
    finally:
        engine.dispose()
```

- Sem Postgres de teste (`docker compose -f infra/docker-compose.dev.yml up -d`), testes `db` **falham**, não pulam. Por isso só o caso 22 é `db`: marcar só ele com `@pytest.mark.db` (não usar `pytestmark` no módulo), para `uv run pytest -m "not db"` rodar o resto sem banco.

### Formato da resposta do Open-Meteo (o que o cliente lê)

```json
{
  "latitude": -23.5, "longitude": -46.625, "timezone": "America/Sao_Paulo",
  "daily_units": {"time": "iso8601", "temperature_2m_max": "°C", "temperature_2m_min": "°C",
                  "precipitation_sum": "mm", "wind_speed_10m_max": "km/h",
                  "relative_humidity_2m_mean": "%"},
  "daily": {"time": ["2026-11-08", "..."], "temperature_2m_max": [31.2, "..."], "...": []}
}
```

Ilustrativo: a fonte da verdade é a fixture gravada no passo 1. Com `timezone=America/Sao_Paulo`, `daily.time[0]` é o dia corrente no fuso de São Paulo.

## 5. Passos

0. (implementer) Na branch `feat/openmeteo-forecast`, a partir da `main`: `uv add httpx`. Confira que `pyproject.toml` ganhou `httpx` em `dependencies` e que `uv.lock` mudou. `uv run pytest` continua verde. Commit `build: add httpx`. (Os testes importam `httpx`; sem este commit eles quebrariam por import, não por comportamento ausente.)
1. (test-writer) Grave a fixture com **uma** chamada real, fora dos testes (em PowerShell use `curl.exe`, não o alias `curl`):
   `curl.exe -s "https://api.open-meteo.com/v1/forecast?latitude=-23.55&longitude=-46.63&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean&timezone=America%2FSao_Paulo&forecast_days=8" -o tests/fixtures/openmeteo_forecast_sao_paulo.json`
   Confira e, se qualquer item falhar, **pare e reporte** (a API mudou e o plano precisa ser revisto):
   - `daily` tem `time` e as 5 variáveis, cada uma com 8 valores;
   - `daily_units` é `°C`, `°C`, `mm`, `km/h`, `%` para as 5 variáveis, nesta ordem;
   - `timezone` é `America/Sao_Paulo`;
   - `daily.time[0]` é a data de hoje em São Paulo.
   Não edite o JSON à mão; variações (nulo, unidade errada, dia faltando) são feitas em memória nos testes, a partir de uma cópia do conteúdo carregado.
2. (test-writer) Escreva `tests/test_http.py` e `tests/test_openmeteo_forecast.py` com os casos da seção 8. Regras:
   - Nenhum teste acessa a rede: `httpx.Client(transport=httpx.MockTransport(handler))`, com o `handler` registrando cada `httpx.Request` recebido.
   - Erros de transporte são simulados levantando a exceção do `httpx` dentro do `handler` (ex.: `raise httpx.ConnectError("boom", request=request)`).
   - Esperas: passe `sleep=` com uma função que só anota o argumento (D4); nenhum teste dorme de verdade.
   - Derive `D` (o `issued_at` dos casos) de `daily.time[0]` da fixture, não de `date.today()`.
   - Só o caso 22 leva `@pytest.mark.db`, com um fixture `forecast_database` igual ao da seção 4.
   Rode `uv run pytest tests/test_http.py tests/test_openmeteo_forecast.py` e confirme a falha por `ModuleNotFoundError: No module named 'ingestion.http'` / `'ingestion.openmeteo'`. Rode `uv run ruff check .` e `uv run ruff format --check .`. Commit `test: add open-meteo forecast client tests`.
3. (implementer) `ingestion/http.py`, partindo da branch com os testes:
   - `class NetworkError(RuntimeError)`: mensagem com a URL e o número de tentativas; `__cause__` é a última exceção (`raise ... from last_error`).
   - Função interna `_get_with_retry(client, url, params, *, attempts, base_delay, sleep) -> httpx.Response`: faz `client.get(url, params=params)` até `attempts` vezes.
     - Repete em `httpx.TransportError` (conexão, timeout, protocolo) e em resposta HTTP 429 ou 500–599.
     - Entre tentativas espera `base_delay * 2**n`, com `n = 0, 1, ...` (padrão: 1 s e depois 2 s); não espera depois da última.
     - Qualquer outro status fora de 2xx: `response.raise_for_status()` na primeira vez, sem repetir (`httpx.HTTPStatusError`).
     - Esgotadas as tentativas: `NetworkError`. Para 429/5xx a causa é o `httpx.HTTPStatusError` da última resposta.
     - `attempts < 1` → `ValueError`.
   - `fetch_json(client, url, params=None, *, attempts=3, base_delay=1.0, sleep=time.sleep) -> Any`: devolve `response.json()`. JSON inválido numa resposta 200 não é erro de rede: a exceção sobe sem retry.
   - `fetch_bytes(client, url, params=None, *, attempts=3, base_delay=1.0, sleep=time.sleep) -> bytes`: mesma política, devolve `response.content` (o PR 20 usa para o parquet do ONS; assinatura compatível com `docs/plans/20-leitura-ons.md`).
   - O timeout é do `client` (o PR 15 cria `httpx.Client(timeout=30)`); `ingestion/http.py` não cria cliente.
4. `ingestion/openmeteo.py`:
   - `@dataclass(frozen=True) class Location: location_id: str; lat: float; lon: float`.
   - `FORECAST_URL = "https://api.open-meteo.com/v1/forecast"`.
   - `FORECAST_TIMEZONE = "America/Sao_Paulo"`.
   - `DAILY_VARIABLES = {"temperature_2m_max": "temp_max", "temperature_2m_min": "temp_min", "precipitation_sum": "precip_mm", "wind_speed_10m_max": "wind_speed_max", "relative_humidity_2m_mean": "humidity_mean"}` (ordem de inserção = ordem das colunas de saída).
   - `DAILY_UNITS = {"temperature_2m_max": "°C", "temperature_2m_min": "°C", "precipitation_sum": "mm", "wind_speed_10m_max": "km/h", "relative_humidity_2m_mean": "%"}`.
   - `MAX_HORIZON_DAYS = 7`.
   - `fetch_forecast(client, location, issued_at: date, days: int = 7, *, base_delay=1.0, sleep=time.sleep) -> pd.DataFrame`:
     1. `days` fora de 1 a 7 → `ValueError` antes de qualquer requisição (D2).
     2. Chama `fetch_json(client, FORECAST_URL, params, base_delay=base_delay, sleep=sleep)` (3 tentativas) com `params` exatamente: `latitude`, `longitude` (da `location`), `daily` (chaves de `DAILY_VARIABLES` separadas por vírgula, nessa ordem), `timezone=America/Sao_Paulo`, `forecast_days=days + 1`. Nenhum parâmetro de unidade: as unidades padrão da API são as esperadas (D6).
     3. Valida a resposta; qualquer falha → `ValueError` com mensagem que nomeia o problema e o `location_id`:
        - falta `daily`, `daily.time` ou alguma das 5 variáveis (mensagem cita o nome que falta);
        - `daily_units` de alguma variável diferente de `DAILY_UNITS` (mensagem cita a variável e a unidade recebida) (D6);
        - listas de `daily` com tamanhos diferentes entre si, ou com menos de `days + 1` dias;
        - `daily.time[0]` diferente de `issued_at` (fuso errado ou execução fora do dia) (D3).
     4. Devolve só `target_date` de `issued_at + 1` a `issued_at + days` (horizontes 1 a `days`), ordenado por `target_date`, índice `0..days-1`, colunas exatamente `location_id, issued_at, target_date, temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean`:
        - `location_id`: o da `location`, em todas as linhas;
        - `issued_at` e `target_date`: valores `datetime.date` (não `pd.Timestamp`);
        - variáveis: `float64`; `null` da API vira `NaN` (o `upsert` grava `NULL`).
        - Sem `horizon_days` e sem `ingested_at` (seção 4).
5. Rode os critérios de pronto, refatore com a suíte verde e cole comando e saída no PR. No corpo do PR, declare as decisões D1 a D9 da seção 9.

## 6. Critérios de pronto

Precisa do Postgres de teste para o caso 22 e para a suíte completa: `docker compose -f infra/docker-compose.dev.yml up -d`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_http.py tests/test_openmeteo_forecast.py -m "not db"` | Todos passam, sem rede e sem banco |
| `uv run pytest tests/test_http.py tests/test_openmeteo_forecast.py` | Todos passam, nenhum `skipped` (inclui o caso 22) |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| `git diff --name-only main...HEAD` | Só `pyproject.toml`, `uv.lock`, `ingestion/http.py`, `ingestion/openmeteo.py`, `tests/fixtures/openmeteo_forecast_sao_paulo.json`, `tests/test_http.py`, `tests/test_openmeteo_forecast.py` |
| `uv run python -c "import httpx; from datetime import date; from ingestion.openmeteo import Location, fetch_forecast; print(fetch_forecast(httpx.Client(timeout=30), Location('sao_paulo', -23.55, -46.63), date.today()).shape)"` (manual, com rede, numa máquina com relógio em horário de Brasília; ver seção 9) | `(7, 8)` |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` | Build termina sem erro (o `uv sync --locked --no-dev` instala o `httpx`) |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o retry precisa repetir só erro de rede, e o recorte de horizontes, a validação do dia de emissão e das unidades decidem se o snapshot que entra numa tabela sem backfill é válido.

## 8. Casos de teste

`fetch_json` e `fetch_bytes` (`tests/test_http.py`; `sleep` falso que anota as esperas, `base_delay=1.0` salvo indicação):

1. Resposta 200 com JSON na primeira → devolve o JSON; 1 requisição; nenhuma espera.
2. `httpx.ConnectError`, `httpx.ConnectError`, depois 200 → devolve o JSON; 3 requisições; esperas `[1.0, 2.0]`.
3. `httpx.ReadTimeout` e depois 200 → devolve o JSON; 2 requisições.
4. Três respostas 503 → `NetworkError`; 3 requisições; esperas `[1.0, 2.0]` (nenhuma depois da última); a mensagem contém a URL; `__cause__` é `httpx.HTTPStatusError`.
5. Três `httpx.ConnectError` → `NetworkError` com `__cause__` `httpx.ConnectError`; 3 requisições.
6. 429 e depois 200 → devolve o JSON; 2 requisições.
7. 500, 502 e depois 200 → devolve o JSON; 3 requisições.
8. Resposta 400 → `httpx.HTTPStatusError` (não `NetworkError`); 1 requisição; nenhuma espera.
9. Resposta 404 → `httpx.HTTPStatusError`; 1 requisição.
10. Resposta 200 com corpo que não é JSON → levanta erro de decodificação (não `NetworkError`); 1 requisição.
11. `attempts=5`, `base_delay=0.5` e só 503 → 5 requisições; esperas `[0.5, 1.0, 2.0, 4.0]`.
12. `attempts=0` → `ValueError`; nenhuma requisição.
13. `params={"a": "1"}` → a requisição enviada tem `a=1` na query string.
14. `fetch_bytes` com 503 e depois 200 com corpo `b"\x00\x01"` → devolve `b"\x00\x01"`; 2 requisições.

`fetch_forecast` (`tests/test_openmeteo_forecast.py`; resposta = fixture, `D = daily.time[0]` da fixture, `Location('sao_paulo', -23.55, -46.63)`):

15. `issued_at = D` → 7 linhas; `target_date` de D+1 a D+7 em ordem crescente; todas com `location_id = 'sao_paulo'` e `issued_at = D`; valores de `issued_at` e `target_date` são `datetime.date`.
16. Colunas exatamente `location_id, issued_at, target_date, temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean`, nessa ordem; não há `horizon_days` nem `ingested_at`; as 5 variáveis têm dtype `float64`.
17. Para cada variável, o valor de D+1 e o de D+7 no DataFrame são iguais aos da fixture nas posições 1 e 7 (o valor de D, posição 0, não aparece).
18. A requisição enviada vai para `https://api.open-meteo.com/v1/forecast` com `latitude=-23.55`, `longitude=-46.63`, `timezone=America/Sao_Paulo`, `forecast_days=8` e `daily` com as 5 variáveis na ordem de `DAILY_VARIABLES`; 1 requisição.
19. `days=3` → 3 linhas (D+1 a D+3) e `forecast_days=4` na requisição. `days=0` e `days=8` → `ValueError`, nenhuma requisição.
20. Variações da fixture, feitas em memória:
    a. `null` em `precipitation_sum` no dia D+2 → `NaN` em `precip_mm` dessa linha; as demais linhas e colunas inalteradas.
    b. `issued_at = D + 1` (ou `D - 1`) → `ValueError` mencionando a data esperada e a recebida.
    c. Sem a chave `relative_humidity_2m_mean` em `daily` → `ValueError` mencionando `relative_humidity_2m_mean`.
    d. `daily_units.wind_speed_10m_max = "m/s"` → `ValueError` mencionando `wind_speed_10m_max`.
    e. Todas as listas de `daily` cortadas para 7 dias (D a D+6) com `days=7` → `ValueError`.
    f. Uma variável com um valor a menos que `time` → `ValueError`.
21. Duas respostas 503 e depois a fixture (com `sleep` falso) → devolve as 7 linhas; 3 requisições (o retry vem de `fetch_json`). Três 503 → `NetworkError`.
22. (`@pytest.mark.db`, banco novo em `head` via `forecast_database`) O DataFrame do caso 15, gravado como `ingestor` com `upsert(conn, "raw.weather_forecast", df, keys=["location_id", "issued_at", "target_date"], on_conflict="ignore")` e commit → devolve 7; lida de volta como admin, a tabela tem 7 linhas com `issued_at = D` e `horizon_days` de 1 a 7. Um segundo `upsert` igual (outra transação) → devolve 0 e a tabela continua com 7 linhas.

Já existentes, que precisam continuar verdes sem edição: toda a suíte (`tests/test_upsert.py`, `tests/test_raw_weather_forecast.py`, `tests/test_ref_locations.py`, `tests/test_cli.py`, `tests/infra/`, entre outros).

## 9. Riscos e perguntas em aberto

Não há perguntas abertas que bloqueiem: as que tinham recomendação foram fechadas abaixo, por autorização do usuário para seguir as recomendações.

### Decisões tomadas neste plano (o implementador declara no corpo do PR)

- **D1. Fuso e dia de emissão: `timezone=America/Sao_Paulo` na requisição.** É o que a coluna `issued_at` documenta na `0004` ("Calendar day in America/Sao_Paulo") e o que o ADR 0005 manda ("o dia dos dados de clima é `America/Sao_Paulo`, definido pelos jobs"). O cliente recebe `issued_at` do chamador e não calcula "hoje": quem calcula é o PR 15, com `ZoneInfo("America/Sao_Paulo")`.
- **D2. Horizontes 1 a 7, sem horizonte 0; `days` restrito a 1 a 7.** Decisão do usuário registrada no plano 13 (D2) e no `CHECK weather_forecast_horizon_days_range` da `0004`. Pedir `forecast_days = days + 1` e descartar o dia 0 é o jeito de obter D+1 a D+7. `days > 7` falha cedo no cliente porque o banco recusaria as linhas (`23514`); `days < 1` não tem sentido.
- **D3. Validar que `daily.time[0] == issued_at`, senão `ValueError`.** Protege contra fuso errado ou execução que vira o dia, que gravariam horizontes deslocados numa tabela onde o primeiro snapshot vence e nada é reescrito.
- **D4. Retry escrito à mão em `ingestion/http.py`, sem `tenacity`; espera injetável (`sleep=`).** São ~15 linhas, a política fica explícita, os testes verificam as esperas exatas sem dormir e a imagem de jobs (VPS de 1 GB) ganha uma dependência a menos. A versão anterior deste plano usava `tenacity`; nenhum outro plano depende dela.
- **D5. 429 é tratado como erro de rede, com o mesmo backoff; `Retry-After` é ignorado.** São 4 chamadas por dia, longe do limite de ~10 mil; respeitar o cabeçalho só aumentaria a complexidade. Se o Open-Meteo passar a limitar de verdade, revisitar.
- **D6. Unidades: as padrão da API (°C, mm, km/h, %), conferidas em `daily_units`.** O plano 13 deixou a unidade para este PR. Não mandar parâmetro de unidade mantém a requisição simples; checar `daily_units` faz uma mudança de unidade na fonte falhar alto em vez de gravar valores errados. As unidades entram no aviso à cientista (abaixo).
- **D7. Resposta incompleta ou malformada → `ValueError` para o local inteiro**, sem gravar parcial. O PR 15 já trata erro por local (registra, segue com os outros e falha no fim), e a checagem dele espera exatamente 7 linhas por local.
- **D8. Fixture real gravada uma vez, variações em memória; um teste `db` de integração (caso 22).** A fixture real prova o formato da API; o caso 22 prova, contra a `0004` e o `upsert` reais, que o DataFrame do cliente entra na tabela como `ingestor` com `on_conflict="ignore"` (sem `horizon_days`, sem `ingested_at`, `location_id` válido, horizontes no `CHECK`). Só esse caso é `db`, para o resto rodar com `-m "not db"`.
- **D9. Nomes em inglês: `DAILY_VARIABLES` no lugar de `VARIAVEIS`**, mais `FORECAST_TIMEZONE`, `DAILY_UNITS` e `MAX_HORIZON_DAYS`, conforme ADR 0001 (identificadores em inglês). O ADR 0001 não listava `VARIAVEIS`; o nome antigo violava a regra.

### Riscos

- **Plano 24 cita `VARIAVEIS`.** `docs/plans/24-cliente-observado-open-meteo.md` manda reutilizar `VARIAVEIS`; com D9 o nome é `DAILY_VARIABLES`. Atualizar o plano 24 antes de executá-lo (tarefa à parte, só `docs/**`).
- **Comando manual e fuso da máquina.** O critério manual usa `date.today()`, que segue o relógio local; fora de UTC-3, perto da meia-noite, a validação D3 falha com `ValueError` (comportamento correto). `ZoneInfo("America/Sao_Paulo")` no Windows exige o pacote `tzdata` (o Windows não traz a base de fusos); este PR não usa `ZoneInfo`, mas o **PR 15 deve adicionar `tzdata`** como dependência para o `today` funcionar nos testes locais no Windows (a imagem já tem `tzdata` do apt e `TZ=America/Sao_Paulo`).
- **A API pode mudar nomes de variáveis ou unidades.** Mitigação: passo 1 para e reporta; em produção, `ValueError` explícito (D6, D7) em vez de dado errado.
- **Dado da fixture envelhece.** A fixture fica com a data do dia em que foi gravada; os testes derivam `D` dela, então não dependem do dia em que rodam. O PR 15 reutiliza a fixture com `today = D`.
- **Retry duplo.** Quando a ingestão virar flow do Prefect (PR 32), o retry de rede fica só aqui; o flow não deve ter `retries` próprio (o plano 32 já prevê `retries=0`).
- **Tempo total de uma falha.** Com 3 tentativas, 1 s + 2 s de espera mais o timeout do cliente (30 s no PR 15) por tentativa, um local inacessível custa até ~93 s; 4 locais, até ~6 min, bem antes do próximo job (06:45).
- **Uso não comercial do Open-Meteo.** O projeto é de estudo; se virar comercial, exige plano pago.
- **Postgres de teste.** Sem o container de `infra/docker-compose.dev.yml`, o caso 22 falha (não pula), por desenho do `tests/conftest.py`.

### Aviso à ciência de dados (complementa o aviso do plano 13; quem envia é o usuário, junto com o item 17)

- Unidades das variáveis em `raw.weather_forecast`: `temp_max`/`temp_min` em °C, `precip_mm` em mm (soma do dia), `wind_speed_max` em km/h (máxima a 10 m), `humidity_mean` em % (média a 2 m). Variáveis da API: `temperature_2m_max`, `temperature_2m_min`, `precipitation_sum`, `wind_speed_10m_max`, `relative_humidity_2m_mean`, dia no fuso `America/Sao_Paulo`.
- As coordenadas são as de `ref.locations` (ponto da capital, não média da região).

## 10. Decisões que exigem ADR

- **Nenhuma.** O cliente materializa decisões já tomadas: ADR 0005 (`issued_at` como dia em `America/Sao_Paulo`, horizontes 1 a 7, primeiro snapshot vence) e ADR 0001 (nomes). D1 a D9 são detalhes de implementação que não mudam `raw`, `ref`, a assinatura do contrato nem a rede.
- **Passaria a exigir emenda ao ADR 0005 (ou ADR novo), mergeada antes da implementação,** guardar o horizonte 0 ou ir além de 7, ou mudar unidades de forma que altere o significado das colunas de `raw.weather_forecast`.
