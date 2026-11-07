# 32 — Flows do Prefect para as três ingestões

> Executa: agente. Depende de: 15, 22, 26, 30 (versão do Prefect fixada). Branch sugerida: `feat/flows-ingest`.
> TDD: passo 0 (dependência) → test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Expor os três jobs de ingestão como flows do Prefect (`ingest_weather_forecast`, `ingest_weather_observed`, `ingest_ons_load`) que chamam as funções já existentes em `ingestion/jobs.py`.
O flow só orquestra: a lógica, o retry e a checagem continuam onde estão; falha do job vira execução `Failed` no Prefect.

## 2. Fora do escopo

- Deployments e agenda (PR 33). Worker (PR 34). Desligar o supercronic (PR 36).
- Alertas (PR 55).

## 3. Fase do roadmap

Fase 3 — "Ingestões migradas para flows do Prefect".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | `prefect==<mesma versão do server do PR 30>` (passo 0) |
| `flows/ingest.py` | Os três flows |
| `ingestion/jobs.py` | Extrair `default_window(today, days)` se CLI e flows precisarem do mesmo cálculo (refatoração, sem mudar comportamento) |
| `tests/test_flows_ingest.py` | Testes (test-writer) |

Código existente (leia antes): `ingestion/jobs.py` com `ingest_weather_forecast(engine, client, today, *, base_delay)`, `ingest_ons_load(engine, client, start, end, *, max_delay_days, base_delay)`, `ingest_weather_observed(engine, client, start, end, *, max_delay_days, base_delay)`; `ingestion/cli.py` mostra como cada um é chamado com os padrões (janela de 30 dias para ONS, 10 para observado, hoje em `America/Sao_Paulo`).

Do doc: "Falha de checagem = execução falha no Prefect = alerta no Telegram". "Erro dentro do código dela aparece no Prefect com o traceback".

## 5. Passos

0. (implementer) `uv add prefect==<versão>`. Commit `build: add prefect`.
1. (test-writer) Escreva os testes da seção 8 com `prefect.testing.utilities.prefect_test_harness` (fixture de sessão) e `monkeypatch` das funções de `ingestion.jobs` para registrar chamadas. Confirme falha por `ModuleNotFoundError: flows.ingest`. Commit `test: add ingestion flow tests`.
2. (implementer) `flows/ingest.py`:
   - `@flow(name="ingest_weather_forecast", retries=0)` sem parâmetros: cria engine (`build_engine()`), `httpx.Client(timeout=30)`, `today` em `America/Sao_Paulo`, chama `jobs.ingest_weather_forecast`.
   - `@flow(name="ingest_ons_load", retries=0)` com parâmetros opcionais `start: date | None`, `end: date | None`, `days: int = 30` (backfill pela UI do Prefect).
   - `@flow(name="ingest_weather_observed", retries=0)` com os mesmos parâmetros, `days: int = 10`.
   - Sem `retries` no flow: o retry de rede já está em `ingestion/http.py`; repetir o flow inteiro duplicaria esperas e não ajuda em falha de checagem.
   - Usar `get_run_logger()` para registrar o intervalo processado.
   - Nenhuma regra nova aqui: se precisar decidir algo, é no job.
3. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_flows_ingest.py` | Todos passam |
| `uv run python -c "from flows.ingest import ingest_weather_forecast, ingest_ons_load, ingest_weather_observed; print('ok')"` | `ok` |
| `uv run pytest` | Suíte verde (inclui os testes da CLI, que não podem mudar) |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o mapeamento "exceção no job → estado `Failed`" e os padrões de janela precisam ser os mesmos da CLI.

## 8. Casos de teste

1. `ingest_weather_forecast()` com o job falso devolvendo `None` → estado final `Completed`; o job foi chamado uma vez com `today` igual à data atual em `America/Sao_Paulo`.
2. Job falso levantando `CheckFailed("x")` → estado `Failed` e a mensagem do estado contém `x`; o job foi chamado **uma** vez (sem retry do flow).
3. `ingest_ons_load()` sem parâmetros → job chamado com `end` = hoje e `start` = hoje − 29.
4. `ingest_ons_load(start=date(2015,1,1), end=date(2015,12,31))` → job chamado com esse intervalo.
5. `ingest_weather_observed()` sem parâmetros → `start` = hoje − 9.
6. `ingest_ons_load(start=date(2026,2,1), end=date(2026,1,1))` → `Failed` sem chamar o job.
7. Os nomes dos três flows são exatamente `ingest_weather_forecast`, `ingest_ons_load`, `ingest_weather_observed` (são os nomes do doc e viram nomes de deployment).

## 9. Riscos e perguntas em aberto

- A versão do `prefect` no `pyproject.toml` deve ser a mesma da imagem do server; senão o worker pode recusar a API.
- Dependências do Prefect são pesadas; o tempo de build da imagem `jobs` vai crescer.

## 10. Decisões que exigem ADR

Nenhuma.
