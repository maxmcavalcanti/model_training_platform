# 24 — Cliente do clima observado (arquivo ERA5 do Open-Meteo)

> Executa: agente. Depende de: 14 (na `main`, #26: `ingestion/http.py` e `ingestion/openmeteo.py`). O item 18 (atraso e revisões do ERA5) **ainda está em coleta** na VPS (cron em `/home/deploy/source-checks`); este plano usa valores provisórios (seção 9, D8). Branch sugerida: `feat/openmeteo-observed`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar com a suíte verde.
> Revisão 2026-11-08: alinhado à `main` em `0f270bd`. Decisão do usuário (2026-11-08): a Fase 1 é considerada concluída e a Fase 2 completa (PRs 24 a 27) começa agora. Correção de nomes: o mapa de variáveis se chama `DAILY_VARIABLES` (não `VARIAVEIS`, ADR 0001 e D9 do plano 14).

## 1. Objetivo

Buscar na API de arquivo do Open-Meteo (`archive-api.open-meteo.com/v1/archive`, reanálise ERA5) o clima diário observado de um local num intervalo de datas e devolver um DataFrame no formato de `raw.weather_observed`, com as mesmas variáveis, unidades e nomes de coluna da previsão.
Serve ao job diário (janela de releitura) e ao backfill desde 2015, ambos do PR 26; este PR não grava nada.

## 2. Fora do escopo

- Tabela `raw.weather_observed` e migração `0007` (PR 25). Por isso este PR **não tem teste `db`**: a tabela ainda não existe; a integração cliente → tabela é provada no PR 26.
- Job `ingest_weather_observed`, checagem pandera (`check_weather_observed`/continuidade), subcomando `weather-observed` da CLI, linha no crontab, cálculo de "hoje" com `ZoneInfo` e as constantes de janela e de atraso (todos do PR 26). Os valores provisórios ficam registrados na seção 9 (D8) para o PR 26 usar.
- Rodar o backfill em produção (item 27).
- Fixar o modelo da reanálise com o parâmetro `models=` da API (D6), dividir o backfill em pedaços (D7), dados horários, outras variáveis.
- Mudar o comportamento de `fetch_forecast` ou de `ingestion/http.py`. Renomear `FORECAST_TIMEZONE` ou outras constantes existentes.
- Editar `ingestion/jobs.py`, `ingestion/cli.py`, `ingestion/checks.py`, `ingestion/db.py`, `tests/conftest.py`, migrações, `infra/`, `.github/`, `AGENTS.md`, `.claude/`, `docs/plataforma-ml.md` (fechamento do item 18) ou outros planos (o ajuste do plano 26 aos valores provisórios é tarefa à parte, só `docs/**`).
- Qualquer item da Fase 3 em diante (Prefect, MLflow, score).

## 3. Fase do roadmap

Fase 2 — Clima, item "`raw.weather_observed` + backfill desde 2015" (`docs/plataforma-ml.md`, "Roadmap").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `ingestion/openmeteo.py` | Alterar: `ARCHIVE_URL` e `fetch_observed(...)`; extrair a validação comum da resposta numa função privada usada também por `fetch_forecast`, sem mudar o comportamento dele; docstring do módulo passa a citar as duas APIs |
| `tests/fixtures/openmeteo_archive_sao_paulo.json` | Novo: resposta real do arquivo gravada uma vez (test-writer) |
| `tests/test_openmeteo_observed.py` | Novo: testes do cliente (test-writer) |

Nenhuma dependência nova (`httpx`, `pandas` já estão em `pyproject.toml`).

### Fonte e regras

`docs/plataforma-ml.md`, "Fontes de dados": Open-Meteo histórico, clima observado (reanálise ERA5), `archive-api.open-meteo.com/v1/archive`, diário desde 1940, "serve para backfill e para o 'real' do modelo de clima". Gratuito para uso não comercial, limite justo de ~10 mil chamadas/dia.

`docs/plataforma-ml.md`, "Ingestão": `06:45 ingest_weather_observed` — "Upsert dos últimos 10 dias de clima observado (cobre atraso e correções da fonte)".

`docs/plataforma-ml.md`, item 18 (medição de 2026-11-08, ~11:50 BRT): a consulta ao `archive` para São Paulo (-23.55, -46.63, `timezone=America/Sao_Paulo`) de 2026-10-29 a 2026-11-08 devolveu as cinco variáveis não nulas nos 11 dias, **inclusive o dia corrente**: atraso observado 0. Ressalva registrada lá: o valor do dia corrente provavelmente não é dado final da reanálise (pode ser parcial ou preenchido por outro modelo); o `archive` não informa a origem. Pendente: se valores recentes mudam de um dia para o outro.

Modelo de dados (`docs/plataforma-ml.md`): `raw.weather_observed` — `location_id`, `date`, `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`, `ingested_at`; chave (`location_id`, `date`).

ADR 0005 (`docs/adr/0005-data-contract-v1.md`), trechos que valem aqui:

> `location_id` é texto em slug minúsculo [...] É a chave de `ref.locations` e a chave estrangeira em `raw.weather_observed` e `raw.weather_forecast` [...]
>
> `ref.locations` não tem coluna `timezone`: o dia dos dados de clima é `America/Sao_Paulo`, definido pelos jobs.
>
> `ingested_at` guarda o momento da **última escrita** da linha [...]

Consequência para o DataFrame: sem `ingested_at` (o `upsert` de `ingestion/db.py` carimba e recusa a coluna no DataFrame); `date` é o dia civil em `America/Sao_Paulo`.

`.claude/rules/migrations-e-dados.md`: "Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede." O retry vem de `fetch_json`; a checagem pandera é do PR 26.

### Código existente a reutilizar (na `main`, `0f270bd`)

`ingestion/http.py` (não alterar):

```python
class NetworkError(RuntimeError): ...  # todas as tentativas falharam por erro de rede

def fetch_json(client, url, params=None, *, attempts=3, base_delay=1.0, sleep=time.sleep) -> Any:
    """Return the decoded JSON body of a GET, retrying network errors."""
```

Política: repete `httpx.TransportError`, 429 e 5xx, esperando `base_delay * 2**n` (1 s, 2 s); outro status fora de 2xx levanta `httpx.HTTPStatusError` sem repetir; esgotado → `NetworkError`.

`ingestion/openmeteo.py` (trechos que importam):

```python
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_TIMEZONE = "America/Sao_Paulo"
MAX_HORIZON_DAYS = 7

# API variable -> raw.weather_forecast column (insertion order = output column order).
DAILY_VARIABLES = {
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "precipitation_sum": "precip_mm",
    "wind_speed_10m_max": "wind_speed_max",
    "relative_humidity_2m_mean": "humidity_mean",
}
DAILY_UNITS = {
    "temperature_2m_max": "°C",
    "temperature_2m_min": "°C",
    "precipitation_sum": "mm",
    "wind_speed_10m_max": "km/h",
    "relative_humidity_2m_mean": "%",
}

@dataclass(frozen=True)
class Location:
    location_id: str
    lat: float
    lon: float

def _validate(payload: object, location_id: str, issued_at: date, days: int) -> dict:
    """Return ``payload["daily"]`` after checking shape, units and first day."""
    # 1. payload["daily"] é dict, senão ValueError "<id>: response has no 'daily' section"
    # 2. "time" e as 5 variáveis presentes, senão "<id>: response is missing daily '<name>'"
    # 3. daily_units == DAILY_UNITS, senão "<id>: unexpected unit for <name>: got <x>, expected <y>"
    # 4. listas com o mesmo tamanho, senão "<id>: daily lists have different lengths: {...}"
    # 5. (só previsão) pelo menos days + 1 dias; daily.time[0] == issued_at

def fetch_forecast(client, location, issued_at, days=MAX_HORIZON_DAYS, *, base_delay=1.0,
                   sleep=time.sleep) -> pd.DataFrame:
    # params: latitude, longitude, daily=",".join(DAILY_VARIABLES), timezone=FORECAST_TIMEZONE,
    #         forecast_days=days + 1
    # colunas: location_id, issued_at, target_date + DAILY_VARIABLES.values(), variáveis float64
```

`ingestion/jobs.py` importa `FORECAST_TIMEZONE` e `MAX_HORIZON_DAYS` de `ingestion.openmeteo`; `tests/test_openmeteo_forecast.py` importa `DAILY_VARIABLES`, `FORECAST_URL`, `Location`, `fetch_forecast`. Nenhum desses nomes muda.

### Padrão de teste a espelhar (`tests/test_openmeteo_forecast.py`)

Fixture real carregada uma vez em `RECORDING`; variações em memória a partir de `copy.deepcopy(RECORDING)`; datas derivadas da fixture, nunca de `date.today()`; nenhum acesso à rede. Cliente falso:

```python
Step = Callable[[httpx.Request], httpx.Response]

class Harness:
    """Client whose n-th request is answered by the n-th step; records requests and sleeps."""

    def __init__(self, steps: list[Step]) -> None:
        self.steps = steps
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.steps[min(len(self.requests), len(self.steps)) - 1](request)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
```

Respostas: `_ok(payload)` devolve `httpx.Response(200, json=payload)`; `_unavailable` devolve `httpx.Response(503)`. Cada caso leva um comentário `# Case N` com o número da seção 8. O test-writer pode copiar `Harness` para o arquivo novo (não alterar `tests/conftest.py` nem o teste da previsão).

### Formato da resposta do arquivo (o que o cliente lê)

Igual ao da previsão (`daily_units` e `daily` com `time` e as 5 variáveis), com `daily.time` de `start_date` a `end_date`, inclusive. Ilustrativo:

```json
{"latitude": -23.5, "longitude": -46.75, "timezone": "America/Sao_Paulo",
 "daily_units": {"time": "iso8601", "temperature_2m_max": "°C", "temperature_2m_min": "°C",
                 "precipitation_sum": "mm", "wind_speed_10m_max": "km/h",
                 "relative_humidity_2m_mean": "%"},
 "daily": {"time": ["2026-10-29", "..."], "temperature_2m_max": [24.1, "..."], "...": []}}
```

A fonte da verdade é a fixture gravada no passo 1. A `latitude`/`longitude` ecoadas são as da célula da grade e diferem das pedidas; o cliente não as confere.

## 5. Passos

1. (test-writer) Na branch `feat/openmeteo-observed`, a partir da `main`, grave a fixture com **uma** chamada real, fora dos testes. Em PowerShell use `curl.exe` (não o alias `curl`). `<START>` = hoje (BRT) menos 10 dias, `<END>` = hoje (BRT), ambos `AAAA-MM-DD`:
   `curl.exe -s "https://archive-api.open-meteo.com/v1/archive?latitude=-23.55&longitude=-46.63&start_date=<START>&end_date=<END>&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean&timezone=America%2FSao_Paulo" -o tests/fixtures/openmeteo_archive_sao_paulo.json`
   Confira e, se qualquer item falhar, **pare e reporte** (a API mudou e o plano precisa ser revisto):
   - `daily` tem `time` e as 5 variáveis, cada uma com 11 valores;
   - `daily.time[0]` é `<START>` e `daily.time[-1]` é `<END>`, dias consecutivos;
   - `daily_units` é `°C`, `°C`, `mm`, `km/h`, `%` para as 5 variáveis, nesta ordem;
   - `timezone` é `America/Sao_Paulo`.
   Anote no corpo do PR quantos dias do fim vieram com nulos (a medição do item 18 achou zero). Não edite o JSON à mão: nulos e outras variações são feitos em memória nos testes.
2. (test-writer) Escreva `tests/test_openmeteo_observed.py` com os casos da seção 8. Regras: nenhum teste acessa a rede; `sleep=` falso que só anota; `START = date.fromisoformat(RECORDING["daily"]["time"][0])` e `END = ...["time"][-1]`; `LOCATION = Location("sao_paulo", -23.55, -46.63)`; nenhum teste `db`. Os casos que dependem de valores comparam com a fixture por posição ou por data, sem números fixos no teste. Rode `uv run pytest tests/test_openmeteo_observed.py` e confirme a falha por `ImportError: cannot import name 'ARCHIVE_URL'` (ou `'fetch_observed'`) `from 'ingestion.openmeteo'`. Rode `uv run ruff check .` e `uv run ruff format --check .`. Commit `test: add open-meteo archive client tests`.
3. (implementer) Partindo da branch com os testes, em `ingestion/openmeteo.py`:
   - `ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"`.
   - Extraia de `_validate` os passos 1 a 4 (seção 4) numa função privada, por exemplo `_daily_section(payload, location_id) -> dict`, mantendo as mesmas mensagens; `_validate` da previsão passa a chamá-la e continua com os passos próprios (mínimo de dias e primeiro dia). Rode `uv run pytest tests/test_openmeteo_forecast.py -m "not db"` e confirme verde antes de seguir.
   - `fetch_observed(client: httpx.Client, location: Location, start: date, end: date, *, base_delay: float = 1.0, sleep: Callable[[float], None] = time.sleep) -> pd.DataFrame`:
     1. `start > end` → `ValueError` (mensagem com as duas datas) antes de qualquer requisição. `start == end` é válido (um dia).
     2. `fetch_json(client, ARCHIVE_URL, params, base_delay=base_delay, sleep=sleep)` com `params` exatamente: `latitude`, `longitude` (da `location`), `start_date` e `end_date` (`date.isoformat()`), `daily` (chaves de `DAILY_VARIABLES` separadas por vírgula, nessa ordem), `timezone=FORECAST_TIMEZONE`. Sem `models` (D6) e sem parâmetros de unidade (unidades padrão, conferidas em `daily_units`).
     3. Valida com a função comum (forma, unidades, tamanhos) e depois exige `daily.time == [start, start+1, ..., end]` (todos os dias pedidos, em ordem, sem buraco nem sobra); senão `ValueError` com o `location_id`, citando a primeira divergência (data esperada e recebida, ou contagem esperada e recebida).
     4. Monta o DataFrame com colunas exatamente `location_id, date, temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean` (as variáveis na ordem de `DAILY_VARIABLES.values()`): `location_id` da `location` em todas as linhas; `date` como `datetime.date` (não `pd.Timestamp`); variáveis `float64`, `null` vira `NaN`.
     5. Descarta os dias em que **as 5 variáveis** são nulas (dia ainda não publicado, em qualquer posição); mantém dias com nulos parciais (D3). Ordena por `date` e refaz o índice `0..n-1`. Se todos os dias forem descartados, devolve DataFrame vazio com as mesmas colunas e dtypes (D4).
     6. Sem `ingested_at`.
   - Atualize a docstring do módulo para citar as APIs de previsão e de arquivo.
4. Rode os critérios de pronto, refatore com a suíte verde (por exemplo, a montagem das colunas de variáveis, comum às duas funções) e cole comandos e saídas no PR. No corpo do PR, declare as decisões D1 a D8 da seção 9 e marque D8 como provisória.

## 6. Critérios de pronto

O Postgres de teste é necessário só para a suíte completa: `docker compose -f infra/docker-compose.dev.yml up -d`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_openmeteo_observed.py` | Todos passam, sem rede e sem banco |
| `uv run pytest tests/test_openmeteo_forecast.py tests/test_job_weather_forecast.py` | Todos passam, sem edição desses arquivos (inclui o caso 22, `db`) |
| `uv run pytest` | Suíte verde, nenhum `skipped` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| `git diff --name-only main...HEAD` | Só `ingestion/openmeteo.py`, `tests/fixtures/openmeteo_archive_sao_paulo.json`, `tests/test_openmeteo_observed.py` |
| (manual, com rede) `uv run python -c "import httpx; from datetime import date; from ingestion.openmeteo import Location, fetch_observed; f = fetch_observed(httpx.Client(timeout=60), Location('sao_paulo', -23.55, -46.63), date(2015, 1, 1), date(2015, 12, 31)); print(f.shape, f['date'].min(), f['date'].max(), int(f.isna().sum().sum()))"` | `(365, 7) 2015-01-01 2015-12-31 0` |
| (manual, com rede) `uv run python -c "import httpx; from datetime import date; from ingestion.openmeteo import Location, fetch_observed; f = fetch_observed(httpx.Client(timeout=120), Location('sao_paulo', -23.55, -46.63), date(2015, 1, 1), date(2026, 11, 7)); print(f.shape)"` | `(4329, 7)` (uma chamada cobre o backfill inteiro de um local; se der timeout ou HTTP 4xx, anotar no PR, ver D7) |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a validação do intervalo devolvido, o descarte de dias ainda não publicados (sem perder dias parciais) e a fidelidade de nomes e unidades à previsão decidem o que entra em `raw.weather_observed`, que é o "real" dos modelos.

## 8. Casos de teste

`fetch_observed` (`tests/test_openmeteo_observed.py`; resposta = fixture salvo indicação; `START`/`END` = primeiro/último dia da fixture; `N` = número de dias da fixture; `Location('sao_paulo', -23.55, -46.63)`; `sleep` falso):

1. `start=START`, `end=END`, fixture sem dias inteiramente nulos (se a fixture tiver algum, o esperado exclui esses dias) → `N` linhas; `date` de `START` a `END` em ordem crescente, um por dia; `location_id = 'sao_paulo'` em todas; cada `date` é `datetime.date`; índice `0..N-1`.
2. Colunas exatamente `location_id, date, temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean`, nessa ordem, ou seja `["location_id", "date", *DAILY_VARIABLES.values()]` (mesmos nomes da previsão); não há `ingested_at`, `issued_at` nem `target_date`; as 5 variáveis são `float64`.
3. Para cada variável de `DAILY_VARIABLES`, a coluna do DataFrame é igual, dia a dia, à lista da fixture convertida para `float` (o primeiro e o último dia inclusive: nada é cortado, ao contrário da previsão).
4. A requisição vai para `https://archive-api.open-meteo.com/v1/archive` (`ARCHIVE_URL` tem esse valor) com `latitude=-23.55`, `longitude=-46.63`, `start_date=START.isoformat()`, `end_date=END.isoformat()`, `daily` igual a `",".join(DAILY_VARIABLES)`, `timezone=America/Sao_Paulo`; o conjunto de parâmetros é exatamente esses 6 (sem `models`, sem `forecast_days`); 1 requisição; nenhuma espera.
5. Os 3 últimos dias com as 5 variáveis `null` (em memória) → `N-3` linhas, última `date` = `END - 3`; as linhas restantes iguais às do caso 1.
6. Um dia do meio (posição 4) com as 5 variáveis `null` → `N-1` linhas, sem erro; a data desse dia não aparece; as demais linhas iguais às do caso 1 (a continuidade é checada no PR 26).
7. Um dia com só `relative_humidity_2m_mean` `null` → `N` linhas; `humidity_mean` desse dia é `NaN`; as outras 4 variáveis desse dia iguais às da fixture; dtype continua `float64`.
8. Um dia com 4 variáveis `null` e só `precipitation_sum` preenchido → a linha aparece, com `precip_mm` igual ao da fixture e o resto `NaN`.
9. Todos os dias com as 5 variáveis `null` → DataFrame vazio, sem erro, com as colunas do caso 2 e as 5 variáveis `float64`.
10. `start = end = START`, resposta = fixture recortada em memória para só o primeiro dia → 1 linha com `date = START`; a requisição tem `start_date` e `end_date` iguais a `START.isoformat()`.
11. `start = END`, `end = START` (com `START < END`) → `ValueError`; nenhuma requisição.
12. Validação da resposta, variações em memória, cada uma → `ValueError` cuja mensagem contém `sao_paulo`:
    a. sem a chave `daily` → `ValueError`;
    b. sem `relative_humidity_2m_mean` em `daily` → mensagem contém `relative_humidity_2m_mean`;
    c. `daily_units.wind_speed_10m_max = "m/s"` → mensagem contém `wind_speed_10m_max` e `m/s`;
    d. `temperature_2m_min` com um valor a menos que `time` → `ValueError`;
    e. pedido `start = START - 1 dia` com a fixture intacta (resposta começa um dia depois do pedido) → mensagem contém `(START - 1).isoformat()` e `START.isoformat()`;
    f. todas as listas de `daily` sem o último dia (resposta termina antes de `END`) → `ValueError`;
    g. todas as listas de `daily` sem o dia da posição 4 (buraco no meio de `time`) → `ValueError`.
13. Duas respostas 503 e depois a fixture → devolve as `N` linhas; 3 requisições; esperas `[1.0, 2.0]` (retry herdado de `fetch_json`).
14. Três respostas 503 → `NetworkError`; 3 requisições.
15. Resposta 400 com corpo `{"error": true, "reason": "Parameter 'start_date' is out of allowed range"}` (é como a API recusa datas fora da faixa) → `httpx.HTTPStatusError`, não `NetworkError`; 1 requisição; nenhuma espera.

Já existentes, que precisam continuar verdes **sem edição** (rede da refatoração de `_validate`): `tests/test_openmeteo_forecast.py` (casos 15 a 22, incluindo os de mensagem de erro 20b a 20f), `tests/test_job_weather_forecast.py`, `tests/test_http.py` e o resto da suíte.

## 9. Riscos e perguntas em aberto

Não há pergunta que bloqueie a implementação: as que tinham recomendação foram fechadas como decisões abaixo, por autorização do usuário para seguir as recomendações. O implementador as declara no corpo do PR.

### Decisões tomadas neste plano

- **D1. Mesmas variáveis, unidades e nomes de coluna da previsão.** `fetch_observed` reusa `DAILY_VARIABLES` e `DAILY_UNITS` (°C, mm, km/h, %) e confere `daily_units`, para a cientista comparar `raw.weather_observed` com `raw.weather_forecast` coluna a coluna. Mudança de unidade na fonte falha alto em vez de gravar valor errado.
- **D2. Fuso `America/Sao_Paulo` na requisição, reusando `FORECAST_TIMEZONE`.** O ADR 0005 diz que o dia dos dados de clima é `America/Sao_Paulo`, definido pelos jobs. Não renomear a constante agora (`ingestion/jobs.py` a importa); um nome neutro, se desejado, é refatoração à parte.
- **D3. Descartar só dias com as 5 variáveis nulas, em qualquer posição; manter nulos parciais.** Dia inteiramente nulo é "ainda não publicado" e não deve virar linha vazia que a checagem do PR 26 acusaria; um buraco no meio fica visível para a checagem de continuidade do PR 26, que é quem decide se falha.
- **D4. Resultado vazio não é erro no cliente.** Quem decide se "nenhum dia" é falha é o job (PR 26), como em `check_ons_daily_load` ("no rows between ..."). O DataFrame vazio mantém colunas e dtypes para o `upsert` e a checagem não quebrarem por formato.
- **D5. A resposta precisa cobrir exatamente `start..end`.** Dias faltando, sobrando ou fora de ordem em `daily.time` → `ValueError` para o local inteiro, como D7 do plano 14; nada parcial é devolvido. O job do PR 26 já trata falha por local.
- **D6. Sem o parâmetro `models`: usar o padrão da API.** É a consulta medida no item 18 (atraso 0). Fixar um modelo de reanálise pura provavelmente aumentaria o atraso em vários dias; a escolha fica para depois do item 18 (ver riscos). O caso 4 trava o conjunto de parâmetros, então mudar isso exige mudar o teste.
- **D7. Uma chamada por local para o intervalo inteiro, sem dividir em pedaços.** O backfill de 2015 até hoje são ~4330 dias por local, 4 chamadas no total; o limite justo conta chamadas ponderadas pelo volume, ainda longe de 10 mil/dia. Se o critério manual de backfill der timeout ou 4xx, o PR 26 divide por ano no job (não aqui). O PR 26 deve criar o cliente com timeout de 120 s para o backfill.
- **D8. Valores PROVISÓRIOS para o PR 26 (o cliente não os usa; ficam registrados para o plano 26).** Janela de releitura diária: **10 dias** (`start = end - 9`), valor do doc. Atraso máximo tolerado pela checagem: **7 dias** (`max_delay_days = 7`), folgado de propósito, para não alarmar todo dia se o Open-Meteo deixar de preencher os dias recentes e o atraso voltar ao da ERA5 pura. Fim padrão da janela: **ontem** (`end = hoje - 1`, BRT), porque o valor do dia corrente é possivelmente parcial (item 18); a releitura com `on_conflict="update"` corrige os dias recentes nas execuções seguintes. Os três valores são ajustáveis num PR posterior quando o item 18 fechar (cron em `/home/deploy/source-checks`).

### Riscos

- **Dias recentes podem não ser ERA5.** O atraso 0 medido sugere que o Open-Meteo completa os dias recentes com outro modelo e substitui depois; o `archive` não informa a origem (não verificado). Consequência: os últimos dias podem mudar. Mitigação: janela de 10 dias com upsert que atualiza (PR 26) e a medição de revisões do item 18. Se as revisões passarem de 10 dias, a janela do PR 26 cresce.
- **Grade da reanálise diferente da grade da previsão.** A célula ERA5 (~0,25°, ~25 km) não é a mesma célula da previsão nem uma estação: a fixture da previsão ecoou -23.51, -46.61 para o ponto pedido -23.55, -46.63; o arquivo ecoará outro ponto. Afeta a comparação previsão × observado; entra no aviso à cientista (abaixo).
- **Fixture envelhece e pode ter o dia corrente parcial.** Os testes derivam as datas da fixture e não usam `date.today()`; nulos são simulados em memória, então a fixture sem nulos (caso medido) basta.
- **A API pode mudar nomes, unidades ou a forma de recusar datas.** Mitigação: o passo 1 para e reporta; em produção, `ValueError` explícito. O corpo 400 do caso 15 é ilustrativo (o teste só depende do status).
- **Refatoração de `_validate`.** Mexe no caminho da previsão, que está em produção. Mitigação: os testes da previsão e do job da previsão rodam sem edição antes e depois (critério de pronto) e as mensagens de erro são preservadas.
- **Uso não comercial do Open-Meteo.** Projeto de estudo; se virar comercial, exige plano pago.

### Aviso à ciência de dados (quem envia é o usuário, junto com o item 27)

- `raw.weather_observed` usa as mesmas colunas e unidades de `raw.weather_forecast`: `temp_max`/`temp_min` em °C (2 m), `precip_mm` em mm (soma do dia), `wind_speed_max` em km/h (máxima a 10 m), `humidity_mean` em % (média a 2 m), dia em `America/Sao_Paulo`.
- Fonte: reanálise ERA5 via Open-Meteo, célula de grade (~25 km), não estação. Os dias mais recentes podem ser provisórios e mudar por até 10 dias (janela provisória).

## 10. Decisões que exigem ADR

- **Nenhuma.** O cliente não cria tabela nem altera `raw`/`ref`, não muda a assinatura de `build_features`, `predict` ou `evaluate` e não expõe serviço. As colunas seguem o modelo de dados de `docs/plataforma-ml.md`, coberto pelo ADR 0005 (que cita `raw.weather_observed`, PR 25).
- **Passaria a exigir ADR (ou emenda ao 0005), mergeado antes da implementação:** guardar a origem do dado (coluna `source`/`model` em `raw.weather_observed`), mudar unidades ou o significado das colunas, ou mudar o fuso que define `date`.
