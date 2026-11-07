# 15 — Job `weather-forecast`: snapshot diário, checagem e CLI

> Executa: agente. Depende de: 11, 13, 14. Branch sugerida: `feat/job-weather-forecast`.
> **Antecipado** (Fase 2 antes do fim da Fase 1; desvio de "uma fase por vez" aprovado pelo usuário em 2026-11-07, P5 resolvida).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar o job que tira o snapshot da previsão de hoje para todos os locais de `ref.locations`, grava em `raw.weather_forecast` sem sobrescrever snapshot existente e termina com checagem pandera.
Exposto como `python -m ingestion weather-forecast`; o agendamento é o PR 16.

## 2. Fora do escopo

- Agendamento (PR 16) e deploy (item 17).
- Alertas no Telegram (PR 55); até lá, falha = código de saída 1 e log.
- Flow do Prefect (PR 32).

## 3. Fase do roadmap

Fase 2 — "`raw.weather_forecast` coletando todo dia (prioridade)".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | `pandera` |
| `ingestion/checks.py` | `CheckFailed`, `checar(df, schema, expected_rows=None)` e `SCHEMA_WEATHER_FORECAST` |
| `ingestion/jobs.py` | `list_locations(conn)` e `ingest_weather_forecast(engine, cliente, hoje)` |
| `ingestion/cli.py` | Subcomando `weather-forecast` |
| `tests/test_checks_weather_forecast.py`, `tests/test_job_weather_forecast.py` | Testes (test-writer) |

Código existente que este PR usa (leia antes):

- `ingestion/db.py`: `build_engine()`, `upsert(conn, tabela, linhas, chaves, *, on_conflict, stamp_ingested_at)` (PR 08).
- `ingestion/openmeteo.py`: `Local`, `fetch_forecast(cliente, local, issued_at, dias=7, *, base_delay)` (PR 14).
- `ingestion/cli.py`: registro `SUBCOMMANDS` e códigos de saída 0/1/2 (PR 11).

Regras (`.claude/rules/migrations-e-dados.md`):

> Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.
> `raw.weather_forecast` guarda a previsão como emitida (`issued_at`). Nunca sobrescrever uma previsão antiga com uma nova.

Checagem (`docs/plataforma-ml.md`): "linhas esperadas por dia, sem nulos nas colunas-chave, valores dentro de faixas plausíveis (… temperatura entre −10 e 50 °C)".

## 5. Passos

1. (test-writer) Escreva os testes da seção 8. Os do job usam `migrated_database` (`@pytest.mark.db`), `httpx.MockTransport` que responde com a fixture `tests/fixtures/openmeteo_forecast_sao_paulo.json` (ajustando `latitude`/`longitude` não é preciso: o local vem do parâmetro) e `hoje` fixo igual ao primeiro dia da fixture. Confirme falha por `ModuleNotFoundError: ingestion.checks`. Commit `test: add weather-forecast job tests`.
2. (implementer) `uv add pandera`. Use o caminho de import recomendado pela versão instalada (nas versões recentes, `import pandera.pandas as pa`).
3. `ingestion/checks.py`:
   - `class CheckFailed(RuntimeError)`.
   - `checar(df, schema, expected_rows: int | None = None) -> None`: valida com `schema.validate(df, lazy=True)`; se `expected_rows` for dado e diferente de `len(df)`, falha. Toda falha vira `CheckFailed` com mensagem legível (quais colunas/linhas).
   - `SCHEMA_WEATHER_FORECAST`: `location_id`, `issued_at`, `target_date` não nulos; `horizon_days` entre 1 e 7; `temp_max` e `temp_min` entre −10 e 50 (nulos permitidos); `precip_mm` ≥ 0; `wind_speed_max` ≥ 0; `humidity_mean` entre 0 e 100; checagem de DataFrame `temp_min <= temp_max` onde ambos existem; unicidade de (`location_id`, `issued_at`, `target_date`).
4. `ingestion/jobs.py`:
   - `list_locations(conn) -> list[Local]` lendo `ref.locations` ordenado por `location_id`.
   - `ingest_weather_forecast(engine, cliente, hoje: date, *, base_delay=1.0) -> None`:
     1. Lê os locais.
     2. Para cada local, chama `fetch_forecast`. Se um local falhar, registra o erro e **continua** com os outros (cada local que falha é histórico perdido; os outros não devem pagar por ele).
     3. Grava o que deu certo com `upsert(..., "raw.weather_forecast", chaves=["location_id", "issued_at", "target_date"], on_conflict="ignorar")`, numa transação.
     4. Relê `raw.weather_forecast` com `issued_at = hoje` e roda `checar(df, SCHEMA_WEATHER_FORECAST, expected_rows=len(locais) * 7)`.
     5. Se algum local falhou no passo 2, levanta `RuntimeError` listando os locais, **depois** de gravar os demais.
   - Não há parâmetro de data: a API só devolve a previsão atual, então não existe reprocessar um dia passado. Reexecutar no mesmo dia completa locais que faltaram e não muda os que já existem.
5. `ingestion/cli.py`: subcomando `weather-forecast`, sem argumentos; usa `build_engine()`, `httpx.Client(timeout=30)` e `hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()`. `CheckFailed` ou qualquer exceção → código 1.
6. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_checks_weather_forecast.py tests/test_job_weather_forecast.py` | Todos passam |
| `uv run python -m ingestion --help` | Lista `weather-forecast` |
| Com o compose de dev rodando e o banco migrado: `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/<banco> uv run python -m ingestion weather-forecast; echo $?` (manual, com rede) | Log com 4 locais e `0` |
| Em seguida: `psql ... -c "select count(*) from raw.weather_forecast"` | `28` |
| Rodar o mesmo comando de novo e contar | Continua `28` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: é o job de maior prioridade e as regras "nunca sobrescrever", "falha parcial grava os outros" e "checagem falha = execução falha" precisam de prova.

## 8. Casos de teste

Checagem:
1. DataFrame válido de 28 linhas com `expected_rows=28` → não levanta.
2. `expected_rows=28` e 27 linhas → `CheckFailed` mencionando `28` e `27`.
3. `temp_max = 51` → `CheckFailed` mencionando `temp_max`.
4. `temp_min > temp_max` numa linha → `CheckFailed`.
5. `precip_mm = -0.1` → `CheckFailed`.
6. `location_id` nulo → `CheckFailed`.
7. `temp_max` nulo (valor ausente na fonte) → não levanta.

Job (banco com os 4 locais do PR 09):
8. Primeira execução → 28 linhas com `issued_at = hoje`, horizontes 1 a 7 para cada local; sem exceção.
9. Segunda execução no mesmo dia, com a API devolvendo temperaturas diferentes → continua 28 linhas e os valores são os da **primeira** execução.
10. Execução no dia seguinte → 56 linhas; os snapshots do dia anterior intactos.
11. API falha (503 nas 3 tentativas) só para `recife` → 21 linhas gravadas e o job levanta erro que menciona `recife`. (A checagem de linhas também acusaria; o erro deve citar o local.)
12. Execução seguinte no mesmo dia com `recife` funcionando → 28 linhas; as 21 anteriores inalteradas.
13. API devolve `temperature_2m_max = 80` para um dia → linhas gravadas e o job levanta `CheckFailed`.
14. CLI: `main(["weather-forecast"])` com o job levantando `CheckFailed` (via `monkeypatch`) devolve 1.

## 9. Riscos e perguntas em aberto

- Caso 13 grava o dado ruim antes de falhar (a checagem é "depois de gravar", como manda a regra). Como a previsão é snapshot e não se repete, guardar o dado e alertar é melhor que perder o dia. Confirmar com o usuário.
- P8 (horizonte 0 e semântica de `issued_at`) muda `expected_rows` e a faixa de `horizon_days`.

## 10. Decisões que exigem ADR

Nenhuma além do ADR "Contrato de dados v1".
