# 32 — Flows do Prefect para as três ingestões

> Executa: agente. Depende de: 15, 22, 26 (jobs na `main`) e 30 (serviço `prefect-server` no compose, imagem com versão completa `X.Y.Z` e digest). Branch sugerida: `feat/flows-ingest` (ADR 0001).
> TDD: passo 0 (dependência, implementer) → test-writer (vermelho) → refatoração com a suíte verde + implementação (verde) → refatorar.
> Revisão 2026-11-08: reescrito contra a `main` em `05c32c9` (jobs `ingest_weather_forecast`, `ingest_weather_observed` e `ingest_ons_load` em `ingestion/jobs.py`; janelas e timeouts calculados em `ingestion/cli.py`; `PartialIngestionError` e `CheckFailed`; `flows/__init__.py` vazio e já copiado pela imagem). Revisão 2 (mesmo dia): aplica a revisão independente aceita pelo usuário, com o nível INFO do logger `ingestion` (bloqueante), o regex ancorado da versão da imagem, a escolha da versão com cooldown de 7 dias e a exceção do estado como oráculo dos testes. Alinhamento entre planos (mesmo dia): o formato da imagem já está fixado no plano 30 (D1 e caso 4); este PR não mexe no compose nem na credencial da API (PR 34).

## 1. Objetivo

Expor os três jobs de ingestão como flows do Prefect (`ingest_weather_forecast`, `ingest_weather_observed`, `ingest_ons_load` em `flows/ingest.py`), com as mesmas janelas, timeouts e parâmetros de reprocessamento da CLI, e com os logs INFO dos jobs aparecendo no log do flow run.
O flow só orquestra: lógica, retry de rede e checagem continuam nos jobs; qualquer exceção do job (inclusive checagem falha) termina o flow run em `Failed`, com o traceback no log.

## 2. Fora do escopo

- Deployments, agendas e work pool (PR 33). Worker no compose e credencial da API (`PREFECT_API_AUTH_STRING`) nos serviços `jobs` e `prefect-worker` (PR 34). Cutover e remoção do supercronic (item 35 e PR 36).
- Alertas de falha (PR 55, Fase 5). Até lá, falha de flow só aparece na UI do Prefect.
- Flow do calendário (`calendar`): é carga manual, rara, e continua só na CLI.
- Backfill grande pelo Prefect: continua pela CLI (`docker compose ... run --rm jobs python -m ingestion ...`). Os parâmetros dos flows servem para reprocessar poucos dias (D7).
- Qualquer mudança em `raw`/`ref`, nos jobs, nas checagens ou nos horários.

## 3. Fase do roadmap

Fase 3 — "MLflow, Prefect e CI/CD", item "Ingestões migradas para flows do Prefect" (`docs/plataforma-ml.md`, "Roadmap").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Passo 0: `prefect==<X.Y.Z>`, a mesma versão completa da tag da imagem do `prefect-server` (PR 30) |
| `ingestion/runs.py` (novo) | Cálculo de janela, timeout HTTP e execução de cada job, compartilhado por CLI e flows (refatoração tirada de `ingestion/cli.py`) |
| `ingestion/cli.py` | `_run_weather_forecast`, `_run_ons_load` e `_run_weather_observed` passam a chamar `ingestion.runs`; argparse, códigos de saída e mensagens não mudam |
| `flows/ingest.py` (novo) | Os três flows e o nível INFO do logger `ingestion` |
| `tests/test_flows_ingest.py` (novo, test-writer) | Comportamento dos flows (nome do arquivo fixado no ADR 0001) |
| `tests/infra/test_prefect_version.py` (novo, test-writer) | Versão do `prefect` no `uv.lock` igual à da tag da imagem do `prefect-server` |
| `AGENTS.md` | Regra de Dependabot para o par `prefect` (uv) e imagem do `prefect-server` (compose), igual à do `postgres` |

### Código existente que o implementador precisa conhecer

`ingestion/jobs.py` (assinaturas, não mudam):

```python
class PartialIngestionError(RuntimeError): ...          # algum local falhou; o resto foi gravado
def issue_date(now: datetime | None = None) -> date      # "hoje" em America/Sao_Paulo
def ingest_weather_forecast(engine, client, today: date, *, base_delay=1.0) -> int
def ingest_ons_load(engine, client, start: date, end: date, *, max_delay_days=ONS_MAX_DELAY_DAYS, base_delay=1.0) -> int
def ingest_weather_observed(engine, client, start: date, end: date, *, max_delay_days=OBSERVED_MAX_DELAY_DAYS, base_delay=1.0) -> int
ONS_WINDOW_DAYS = 30; ONS_MAX_DELAY_DAYS = 5
OBSERVED_WINDOW_DAYS = 10; OBSERVED_MAX_DELAY_DAYS = 7; OBSERVED_END_LAG_DAYS = 1
```

`ingest_ons_load` e `ingest_weather_observed` levantam `ValueError(f"start {start} is after end {end}")` antes de tocar rede ou banco. Os três jobs levantam `CheckFailed` (`ingestion/checks.py`) quando a checagem pandera falha, e os de clima levantam `PartialIngestionError` quando algum local falhou. O retry de rede (3 tentativas, só transporte, 429 e 5xx) está em `ingestion/http.py`. `ingestion/db.py`: `build_engine()` lê `DATABASE_URL` e levanta `MissingConfiguration("DATABASE_URL is not set")`. Os jobs registram sucesso com `logging.getLogger(__name__)` (logger `ingestion.jobs`) em nível INFO, por exemplo `weather-forecast ok: 4 locations, 28 rows inserted, 0 already existed`.

`ingestion/cli.py` hoje (o comportamento que `ingestion/runs.py` herda):

```python
# weather-forecast
engine = build_engine()
try:
    with httpx.Client(timeout=30) as client:
        jobs.ingest_weather_forecast(engine, client, today=jobs.issue_date())
finally:
    engine.dispose()

# ons-load: --end (padrão hoje), --start | --days (mutuamente exclusivos, days >= 1, padrão ONS_WINDOW_DAYS)
end = args.end or jobs.issue_date()
start = args.start or end - timedelta(days=args.days - 1)
# httpx.Client(timeout=60)

# weather-observed: --end (padrão ontem), --start | --days (padrão OBSERVED_WINDOW_DAYS)
end = args.end or jobs.issue_date() - timedelta(days=jobs.OBSERVED_END_LAG_DAYS)
start = args.start or end - timedelta(days=args.days - 1)
timeout = 120 if (end - start).days + 1 > jobs.OBSERVED_WINDOW_DAYS else 30
```

Os testes de caracterização da CLI fazem `monkeypatch.setattr("ingestion.jobs.ingest_ons_load", ...)` e `monkeypatch.setattr("ingestion.jobs.issue_date", ...)`. Por isso `ingestion/runs.py` precisa buscar `jobs.issue_date` e `jobs.ingest_*` pelo módulo na hora da chamada (`from ingestion import jobs` e depois `jobs.ingest_ons_load(...)`), nunca com `from ingestion.jobs import ingest_ons_load` no topo. O mesmo vale para `build_engine`: precisa ser chamado dentro da função, para `DATABASE_URL` ausente virar erro na execução.

Do doc (`docs/plataforma-ml.md`): "Falha de checagem = execução falha no Prefect = alerta no Telegram"; "Erro dentro do código dela aparece no Prefect com o traceback". Regra (`.claude/rules/migrations-e-dados.md`): "As regras de job (idempotência, reprocessamento por data, retry com backoff só para erro de rede) valem também para flows do Prefect."

### Por que o nível do logger `ingestion` precisa ser fixado (bloqueante)

O PR 34 põe `PREFECT_LOGGING_EXTRA_LOGGERS=ingestion` no worker. Essa configuração liga os handlers do Prefect ao logger `ingestion`, mas não define o nível dele. Sem nível próprio, o logger herda o nível efetivo do root, que no `logging.yml` padrão do Prefect é `WARNING`. Assim as linhas INFO dos jobs (`weather-forecast ok: ...`, `ons-load ok: ...`) não chegariam ao log do flow run nem à UI, e o item 35 depende delas. A correção fica em `flows/ingest.py`: no import do módulo, `logging.getLogger("ingestion").setLevel(logging.INFO)`. A CLI não é afetada, porque já faz `logging.basicConfig(level=logging.INFO)`.

### O que o PR 30 entrega (na `main` antes deste PR)

Serviço `prefect-server` em `infra/docker-compose.yml` com imagem `prefecthq/prefect:<X.Y.Z>-python3.12@sha256:<64 hex>`, isto é, **versão completa `X.Y.Z` e digest** (nunca só `3`, `3.9` ou `latest`; ADR 0006), travada pelo caso 4 do plano 30. API interna em `http://prefect-server:4200/api`, autenticada (plano 30, D7), e UI publicada só em loopback, exposta por `tailscale serve`. Os testes deste PR usam `prefect_test_harness` (server temporário, sem autenticação) e não precisam da credencial; o caso 25 lê a tag da imagem.

## 5. Passos

0. (implementer, primeiro commit da branch) Escolha da versão: a **última versão estável do Prefect 3 publicada há pelo menos 7 dias** (mesmo cooldown do Dependabot, ADR 0006). Em 2026-11-08 é a `3.9.1`, porque a `3.9.2` saiu em 2026-11-06. A versão tem de ser **a mesma da tag da imagem do `prefect-server`** em `infra/docker-compose.yml` (PR 30). Se forem diferentes, pare e devolva para o planejamento, em vez de escolher um lado. Rode `uv add "prefect==<X.Y.Z>"` e confira que `uv run prefect version` mostra `Version: <X.Y.Z>`. Commit `build: add prefect`. Sem isso, os testes falhariam por import quebrado, não por comportamento ausente.
1. (implementer, ainda no passo 0) Confira localmente a API que os testes e o código vão usar:

   ```bash
   uv run python -c "import prefect; print(prefect.__version__)"
   uv run python -c "from prefect import flow, get_run_logger; print('ok')"
   uv run python -c "from prefect.testing.utilities import prefect_test_harness; print('ok')"
   uv run python -c "import inspect; from prefect import flow; print(inspect.signature(flow))"
   uv run python -c "import inspect; from prefect.states import State; print(inspect.signature(State.result))"
   ```

   → a versão do passo 0; `ok`; `ok`; a assinatura com `name`, `retries` e `log_prints`; `State.result` aceita `raise_on_failure`. Se algum falhar, pare e devolva para o planejamento.
2. (test-writer) Escreva os casos da seção 8 em `tests/test_flows_ingest.py` e `tests/infra/test_prefect_version.py`:
   - Fixture de módulo (ou de sessão) com `prefect_test_harness()`, que sobe um server temporário com SQLite, sem tocar no Postgres. Os testes não levam o marcador `db`.
   - Mesmo padrão dos testes de CLI: `monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:secret@127.0.0.1:1/none")`, `monkeypatch.setattr("ingestion.jobs.issue_date", lambda *a, **k: date(2026, 11, 8))` e jobs falsos em `ingestion.jobs.ingest_*`, que registram `(start, end, client.timeout.read)` e o tipo dos argumentos.
   - Oráculo de falha: chame o flow com `return_state=True`. Confira `state.is_failed()` e use **`state.result(raise_on_failure=False)` como oráculo principal**: ele devolve a exceção do job, então confira o tipo (`isinstance(exc, CheckFailed)` etc.) e `str(exc)`. `str(state.message)` é só verificação secundária, porque o formato da mensagem do estado é do Prefect e pode mudar entre versões. Sem `return_state`, a chamada direta relança a exceção do job (casos 2 e 3).
   - Log do flow run (caso 26): depois da execução, leia os logs do flow run pelo client do server de teste (`get_client(sync_client=True).read_logs(...)` filtrando pelo id do flow run, ou o equivalente da versão, conferido com `inspect`).
   - Confirme que falham pelo motivo certo: `ModuleNotFoundError: No module named 'flows.ingest'` e, no teste de versão, a ausência de `prefect` no `uv.lock` ou do serviço `prefect-server` (se o PR 30 ainda não estiver na `main`, este plano não começa). Commit `test: add ingestion flow tests`.
3. (implementer, refatoração com a suíte verde) Crie `ingestion/runs.py` e faça a CLI usá-lo, **antes** de escrever os flows:
   - `run_weather_forecast() -> int`: engine, `httpx.Client(timeout=30)`, `jobs.ingest_weather_forecast(engine, client, today=jobs.issue_date())`, `engine.dispose()` em `finally`; devolve o que o job devolveu.
   - `run_ons_load(start: date | None = None, end: date | None = None, days: int | None = None) -> int`: `end` padrão `jobs.issue_date()`; `start` e `days` juntos → `ValueError("start and days are mutually exclusive")`; `days` padrão `jobs.ONS_WINDOW_DAYS`; `days < 1` → `ValueError("days must be at least 1")`; `start` padrão `end - (days - 1)`; timeout 60; o resto como hoje.
   - `run_weather_observed(start=None, end=None, days=None) -> int`: `end` padrão `jobs.issue_date() - jobs.OBSERVED_END_LAG_DAYS`; mesmas regras de `start`/`days`, padrão `jobs.OBSERVED_WINDOW_DAYS`; timeout 120 quando o intervalo passa de `OBSERVED_WINDOW_DAYS` dias, senão 30.
   - Cada `run_*` registra a janela no logger `ingestion.runs` em INFO antes de chamar o job (ex.: `ons-load window 2026-10-10 to 2026-11-08`) e não captura exceção nenhuma.
   - `ingestion/cli.py`: o argparse continua impondo a exclusão mútua e `days >= 1` (erro de uso, código 2). `_run_ons_load` e `_run_weather_observed` passam `days=None` quando `args.start` foi dado (o argparse preenche `days` com o padrão mesmo nesse caso) e devolvem `0`.
   - Rode `uv run pytest -m "not db" tests/test_cli.py tests/test_job_weather_forecast.py tests/test_job_ons_load.py tests/test_job_weather_observed.py`: tudo verde, sem editar teste. Commit `refactor: share run windows between cli and flows`.
4. (implementer) `flows/ingest.py`:
   - No topo do módulo, depois dos imports: `logging.getLogger("ingestion").setLevel(logging.INFO)` (seção 4, "Por que o nível...").
   - `@flow(name="ingest_weather_forecast", retries=0)` → `def ingest_weather_forecast() -> int`, chama `runs.run_weather_forecast()`.
   - `@flow(name="ingest_weather_observed", retries=0)` → `def ingest_weather_observed(start: date | None = None, end: date | None = None, days: int | None = None) -> int`, chama `runs.run_weather_observed(start, end, days)`.
   - `@flow(name="ingest_ons_load", retries=0)` → mesma forma, chama `runs.run_ons_load(start, end, days)`.
   - Cada flow registra o resultado com `get_run_logger()` (ex.: `ingest_ons_load wrote 120 rows`) e devolve o inteiro. Sem `try/except`, sem tasks, sem `retries` no flow (D2) e sem `timeout_seconds` (D4).
   - Importe `runs` pelo módulo (`from ingestion import runs`), pelo mesmo motivo do passo 3.
5. (implementer) `AGENTS.md`, "Fluxo de trabalho": acrescente, ao lado da regra do `postgres`, "PR do Dependabot que troca a versão do `prefect` no `uv.lock` ou a imagem do `prefect-server` no `infra/docker-compose.yml`: levar o outro lado à mesma versão completa (`X.Y.Z`) por commit na própria branch; o teste `tests/infra/test_prefect_version.py` fica vermelho até isso."
6. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run prefect version` | Primeira linha `Version: <X.Y.Z>`, igual à tag do `prefect-server` |
| `uv run pytest tests/test_flows_ingest.py tests/infra/test_prefect_version.py` | Todos passam |
| `uv run pytest -m "not db" tests/test_cli.py tests/test_job_weather_forecast.py tests/test_job_ons_load.py tests/test_job_weather_observed.py` | Todos passam, sem nenhum teste editado (`git diff --stat main -- tests/test_cli.py tests/test_job_*.py` vazio) |
| `uv run python -c "from flows.ingest import ingest_weather_forecast as f, ingest_weather_observed as o, ingest_ons_load as l; print(f.name, o.name, l.name)"` | `ingest_weather_forecast ingest_weather_observed ingest_ons_load` |
| `uv run python -c "import logging, flows.ingest; print(logging.getLevelName(logging.getLogger('ingestion').level))"` | `INFO` |
| `uv run python -m ingestion --help` | Lista `weather-forecast`, `calendar`, `ons-load`, `weather-observed`, `create-databases` |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem achados |
| `docker compose -f infra/docker-compose.dev.yml up -d` e `uv run pytest` | Suíte inteira verde |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` | Termina sem erro |
| `docker run --rm platform-jobs python -c "import flows.ingest; print('ok')"` | `ok` |
| `docker run --rm platform-jobs prefect version` | `Version: <X.Y.Z>` |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: lógica nova (flows, mapeamento de exceção para `Failed`, nível de log) e refatoração da CLI; a refatoração usa como rede os testes de CLI existentes (listados no caso 23).

## 8. Casos de teste

Salvo indicação: `DATABASE_URL` fictícia (`postgresql+psycopg://user:secret@127.0.0.1:1/none`), `issue_date` fixa em 2026-11-08 e job falso que devolve um inteiro e registra o que recebeu. Nos casos de falha, o oráculo é a exceção de `state.result(raise_on_failure=False)` (tipo e texto); a mensagem do estado é conferida só de forma secundária.

`tests/test_flows_ingest.py`:

1. `ingest_weather_forecast()` com job falso devolvendo `28` → devolve `28`; o estado (`return_state=True`) é `Completed`; o job foi chamado uma vez, com `today = 2026-11-08` e cliente com timeout de leitura `30`.
2. Job da previsão levantando `CheckFailed("expected 28 rows, got 21")` → a chamada direta levanta `CheckFailed`; com `return_state=True`, `state.is_failed()` e `state.result(raise_on_failure=False)` é um `CheckFailed` cujo texto contém `expected 28 rows, got 21`; o job foi chamado **uma** vez (sem retry do flow).
3. Job da previsão levantando `PartialIngestionError("forecast failed for locations: recife")` → `Failed`; a exceção do estado é `PartialIngestionError` e contém `recife`; job chamado uma vez.
4. `ingest_ons_load()` → job recebe `(2026-10-10, 2026-11-08)`, timeout `60`.
5. `ingest_ons_load(days=10)` → `(2026-10-30, 2026-11-08)`.
6. `ingest_ons_load(start=date(2015, 1, 1), end=date(2015, 12, 31))` → `(2015-01-01, 2015-12-31)`.
7. `ingest_ons_load(end=date(2026, 1, 31))` → `(2026-01-02, 2026-01-31)`.
8. `ingest_ons_load(start=date(2026, 11, 1))` → `(2026-11-01, 2026-11-08)`.
9. `ingest_ons_load(start="2015-01-01", end="2015-12-31")` (strings ISO, como chegam da UI e de `--param`) → o job recebe `(2015-01-01, 2015-12-31)` e o job falso confere `type(start) is date` e `type(end) is date` (nem `str`, nem `datetime`).
10. `ingest_ons_load(start=date(2026, 11, 1), days=5)` → `Failed`; a exceção do estado é `ValueError` com `mutually exclusive`; job não chamado.
11. `ingest_ons_load(days=0)` → `Failed`; `ValueError` com `at least 1`; job não chamado.
12. Job **real** (sem monkeypatch do job), `ingest_ons_load(start=date(2026, 2, 1), end=date(2026, 1, 1))` → `Failed`; `ValueError` com `is after end`, sem tentativa de rede.
13. Job do ONS levantando `CheckFailed("stale: last date 2026-10-01 is older than 2026-11-03")` → `Failed`; `CheckFailed` com `stale`; job chamado uma vez.
14. `ingest_weather_observed()` → `(2026-10-29, 2026-11-07)`, timeout `30`.
15. `ingest_weather_observed(days=3)` → `(2026-11-05, 2026-11-07)`, timeout `30`.
16. `ingest_weather_observed(start=date(2015, 1, 1), end=date(2015, 12, 31))` → mesmo intervalo, timeout `120`.
17. `ingest_weather_observed(start=date(2015, 1, 1))` → `(2015-01-01, 2026-11-07)`, timeout `120`.
18. `ingest_weather_observed(end=date(2026, 1, 31))` → `(2026-01-22, 2026-01-31)`, timeout `30`.
19. `ingest_weather_observed(days=10)` → timeout `30`; `ingest_weather_observed(days=11)` → timeout `120`.
20. `ingest_weather_observed(start=date(2026, 11, 1), days=5)` e `ingest_weather_observed(days=0)` → `Failed` com `ValueError`; job não chamado.
21. Job do observado levantando `PartialIngestionError("observed weather failed for locations: belem")` → `Failed`; `PartialIngestionError` com `belem`; job chamado uma vez.
22. Sem `DATABASE_URL` no ambiente, qualquer um dos três flows → `Failed`; a exceção do estado é `MissingConfiguration` e contém `DATABASE_URL`; job não chamado. Com a `DATABASE_URL` fictícia e um job falso que levanta `RuntimeError("boom")`, nem o texto da exceção nem `str(state.message)` contêm `secret` (a senha da URL nunca vaza para o estado).
23. Caracterização (já existem, não mudam): `tests/test_cli.py` inteiro; `tests/test_job_weather_forecast.py` casos 25 a 28; `tests/test_job_ons_load.py` casos 25 a 34; `tests/test_job_weather_observed.py` casos 34 a 40 e os seguintes de CLI. Todos verdes depois da refatoração.
24. Importar `flows.ingest` deixa `logging.getLogger("ingestion").level == logging.INFO`.
25. *(ver `tests/infra/test_prefect_version.py`, abaixo.)*
26. Com `prefect_test_harness`, um job falso da previsão que faz `logging.getLogger("ingestion.jobs").info("weather-forecast ok: x")` e devolve `28` → o flow termina `Completed`, e os logs do flow run lidos pelo client do server de teste contêm uma linha com `weather-forecast ok: x`. Se o teste precisar ligar `PREFECT_LOGGING_EXTRA_LOGGERS=ingestion` (como o worker do PR 34), use `prefect.settings.temporary_settings` ou o equivalente da versão, sem mudar o nível do logger no teste: o nível tem de vir de `flows/ingest.py`.

`tests/infra/test_prefect_version.py`:

25. A versão do pacote `prefect` no `uv.lock` (lido com `tomllib`) é igual ao grupo capturado da imagem do serviço `prefect-server` em `infra/docker-compose.yml`, pela regex ancorada `^prefecthq/prefect:(\d+\.\d+\.\d+)-python3\.12@sha256:[0-9a-f]{64}$`. Exemplos: `prefecthq/prefect:3.9.1-python3.12@sha256:<64 hex>` dá `3.9.1`. São rejeitados: `prefecthq/prefect:3.9.2.dev6-python3.12@sha256:<64 hex>`, `prefecthq/prefect:3.9-python3.12@sha256:<64 hex>`, `prefecthq/prefect:sha-802fc94-python3.12@sha256:<64 hex>`, `prefecthq/prefect:3.9.1-python3.12-conda@sha256:<64 hex>`, `prefecthq/prefect:3.9.1-python3.12-kubernetes@sha256:<64 hex>`, `prefecthq/prefect:3.9.1-python3.11@sha256:<64 hex>`, `prefecthq/prefect:3.9.1-python3.12` (sem digest), `prefecthq/prefect:latest` e `prefecthq/prefect:3-python3.12`. Versões diferentes entre lock e imagem são reportadas.

## 9. Riscos e perguntas em aberto

### Decisões (com recomendação; aceitas pelo usuário)

- **D1. Onde mora o cálculo de janela e timeout.** (a) módulo novo `ingestion/runs.py`, usado por CLI e flows; (b) flows duplicando o cálculo; (c) flows chamando `ingestion.cli.main([...])`. **Recomendação: (a).** A (b) cria duas fontes de verdade; a (c) perde o traceback no Prefect, porque a CLI captura a exceção e devolve `1`.
- **D2. `retries` no flow.** **Recomendação: `0`.** O retry de rede já acontece dentro do job (3 tentativas), e retry de flow repetiria também falha de checagem, o que contraria "retry só para erro de rede".
- **D3. Parâmetros nos flows.** **Recomendação: `start`, `end` e `days` opcionais, com a semântica da CLI.** A regra de reprocessar por data vale para flows. Os deployments do PR 33 não fixam parâmetros, então a execução agendada usa a janela diária.
- **D4. `timeout_seconds` no flow.** **Recomendação: não pôr agora.** Reavaliar no item 35 com as durações medidas.
- **D5. Tasks dentro do flow.** **Recomendação: nenhuma.**
- **D6. Pin do `prefect`.** **Recomendação: `==` no `pyproject.toml`** com versão completa, escolhida com o cooldown de 7 dias, e o teste de alinhamento com a imagem (caso 25).
- **D7. Backfill pelo flow.** **Recomendação:** backfill de anos continua pela CLI no serviço `jobs`. Pelo flow, só janelas curtas: o worker tem limite de 1 execução (PR 34).
- **D8. Onde fixar o nível do logger.** **Recomendação: no import de `flows/ingest.py`**, e não no compose nem num `logging.yml` próprio. Fica junto do código que depende dele, vale em qualquer processo que rode os flows (worker, harness, `serve`) e não muda a CLI.

### Riscos

- **API do Prefect.** Os pontos vieram de memória e de revisão independente com acesso à web, e são conferidos no passo 1: `flow(name=, retries=)`, `get_run_logger`, `prefect_test_harness`, `return_state=True`, `State.result(raise_on_failure=False)` devolvendo a exceção, coerção de string ISO para `date` (caso 9), leitura de logs pelo client (caso 26) e o efeito de `PREFECT_LOGGING_EXTRA_LOGGERS`. Se algum não valer na versão fixada, pare e devolva para o planejamento.
- **`prefect_test_harness` lento.** Sobe um server temporário em subprocesso, mais lento no Windows. Use fixture de módulo ou de sessão.
- **Imagem maior e build mais lento na VPS (1 vCPU).** `prefect-client`, mais leve, foi descartado: não traz o CLI do worker nem o harness.
- **Conflito de dependências.** Se o `uv add` não resolver junto com `sqlalchemy>=2.1.8`, `pandas>=3.1.1` e `httpx`, pare e devolva com a saída.
- **Achados de segurança novos** no `dependency-review` e no Trivy `fs` (ADR 0006, ainda só avisa): corrigir ou registrar exceção versionada, nunca `noqa`.
- **Dependabot.** Ecossistemas separados: o caso 25 fica vermelho até os dois lados se alinharem, e a regra do passo 5 diz o que fazer. O cooldown de 7 dias vale para os dois.

### Perguntas em aberto

- Nenhuma bloqueante. O formato da imagem (`X.Y.Z` completo + digest) está garantido pelo plano 30 (D1 e caso 4).

## 10. Decisões que exigem ADR

**Nenhuma.** O Prefect 3 já é a escolha do doc (`docs/plataforma-ml.md`, "Stack na VPS"). Este PR não mexe em `raw`/`ref` nem no contrato, não publica porta e não agenda nada. A forma de execução (work pool, worker, registro) é do ADR obrigatório "Agendamento e execução pelo Prefect" sinalizado no plano 33, que precisa estar mergeado antes do 33, não deste.
