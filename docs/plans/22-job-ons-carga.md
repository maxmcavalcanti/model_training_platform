# 22 — Job `ons-load`: janela móvel, backfill por intervalo, checagem pandera e agenda 07:00

> Executa: agente. Depende de: **21 mergeado** (`raw.ons_daily_load`, migração `0006`), 20 (`ingestion/ons.py`), 19 (`ref.calendar`, migração `0005`), 16 (crontab do supercronic), 15 (padrão de job). Branch sugerida: `feat/job-ons-load`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-08: alinhado à `main` em `c6a9ba6` (PRs 15, 16, 19 e 20 mergeados) e ao plano 21 (`docs/plans/21-tabela-ons-carga.md`, em revisão), assumido na `main` antes de começar (passo 0). As perguntas com recomendação viraram decisões D1 a D12 (seção 9), por autorização do usuário. O horário 07:00, a janela de 30 dias e o atraso máximo são **provisórios** até o item 18 fechar.

## 1. Objetivo

Criar o subcomando `ons-load`: baixa o(s) parquet(s) anual(is) do ONS, faz upsert em `raw.ons_daily_load` dos últimos 30 dias (ou de `--start`/`--end`, para backfill), relê o intervalo e termina com checagem pandera (faixa em MWmed, 4 subsistemas por dia, continuidade, atraso).
Agendar a execução diária às 07:00 (America/Sao_Paulo) no crontab do supercronic, com horário e janela marcados como provisórios.

## 2. Fora do escopo

- Rodar o backfill desde 2015 em produção e fechar o checkbox do roadmap (item 23, que usa `--start`/`--end` deste PR).
- Fechar o item 18 (atraso e profundidade de revisão) e ajustar os valores provisórios: PR pequeno posterior (D10).
- Flow do Prefect (PR 32) e alertas no Telegram (PR 55).
- Mudar `raw.ons_daily_load` (migração `0006`), `ingestion/ons.py`, `ingestion/http.py`, `ingestion/db.py`, migrações, `tests/conftest.py`, `pyproject.toml`/`uv.lock` (nenhuma dependência nova), `infra/jobs/Dockerfile`, `infra/docker-compose.yml`, `.claude/`, `AGENTS.md`, ADRs e outros planos.
- Apagar linhas que o ONS removeu (o `ingestor` não tem `DELETE`; ver riscos).
- Clima observado (`raw.weather_observed`, PR 25) e o horário 06:45.
- Corrigir `SE/CO` na tabela de fontes de `docs/plataforma-ml.md`.

## 3. Fase do roadmap

Fase 1 — "Banco e carga do ONS", item "Ingestão do ONS + backfill desde 2015 + checagens" (`docs/plataforma-ml.md`, "Roadmap"). Este PR entrega o job e a checagem; o backfill em produção é o item 23.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `tests/test_checks_ons_load.py` | Novo (test-writer): checagem pura, sem banco nem rede |
| `tests/test_job_ons_load.py` | Novo (test-writer): job com banco (`db`) e CLI sem banco |
| `tests/infra/test_crontab.py` | Alterar (test-writer): exatamente uma linha `ons-load` com `0 7 * * *`, sem argumentos, com exemplos negativos |
| `ingestion/checks.py` | `ONS_DAILY_LOAD_SCHEMA` e `check_ons_daily_load(df, start, end, max_delay_days)` |
| `ingestion/jobs.py` | Constantes provisórias e `ingest_ons_load(engine, client, start, end, *, max_delay_days, base_delay)` |
| `ingestion/cli.py` | Subcomando `ons-load [--start] [--end] [--days]` |
| `infra/cron/crontab` | Linha `0 7 * * * python -m ingestion ons-load` com comentário de provisório |

### Fatos da fonte (`docs/plataforma-ml.md`, "Para verificar antes da Fase 1", item 18)

- Um arquivo por ano: `CARGA_ENERGIA_<ANO>.parquet`, de 2000 a 2026, no bucket público `ons-aws-prod-opendata`, prefixo `dataset/carga_energia_di/`.
- `CARGA_ENERGIA_2026.parquet` tinha `LastModified` 2026-11-07T22:00:35Z (19:00 BRT de sábado). Anos fechados não mudam há meses (2025: 2026-01-31), o que sugere que o ONS reescreve o ano inteiro de tempos em tempos.
- No domingo 2026-11-08, ~11:50 BRT, a última data no arquivo de 2026 era 2026-11-05 (D−3, fim de semana), com os 4 subsistemas.
- **Pendente:** atraso em dias úteis às ~07:00 e profundidade das revisões (comparação 2026-11-08 × 2026-11-15). Por isso D2, D3 e D4.
- Doc, "Ingestão": "07:00 `ingest_ons_load` — Lê o parquet do ano corrente no S3 e faz upsert dos últimos 30 dias (cobre revisões do ONS)". "Os horários são um ponto de partida; ajustar depois de verificar quando o ONS publica." "um backfill é só o mesmo job com um intervalo maior." Checagem: "linhas esperadas por dia, sem nulos nas colunas-chave, valores dentro de faixas plausíveis (carga positiva…)".

### Regras que se aplicam (`.claude/rules/migrations-e-dados.md`, `AGENTS.md`)

> Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.

`AGENTS.md`: "Todo job termina com checagem de qualidade (pandera). Checagem falha = execução falha." Identificadores, logs e mensagens de erro em inglês (ADR 0001).

`.claude/rules/infra.md`: deploy só por merge na `main`; até o PR 39 o usuário atualiza a VPS à mão (ADR 0004). Nenhum agente aplica deploy.

### Código existente a usar (não alterar)

`ingestion/ons.py` (PR 20):

```python
SUBSYSTEMS = ("SE", "S", "NE", "N")

def file_url(year: int) -> str: ...  # .../dataset/carga_energia_di/CARGA_ENERGIA_{year}.parquet

def parse_load(content: bytes) -> pd.DataFrame:
    """Validate and normalize a daily-load parquet into ``subsystem, date, load_avg_mw``."""
    # ValueError: not parquet, missing column, null key, unknown subsystem (SE/CO, SIN...),
    # non-midnight timestamp, duplicate (subsystem, date). Rows with null load are dropped.
    # "date" is datetime.date; load_avg_mw float64; sorted by date, subsystem. Empty file -> empty frame.

def fetch_load(client, year, *, base_delay=1.0, sleep=time.sleep) -> pd.DataFrame:
    """Download the parquet of ``year`` and return it normalized."""
```

`ingestion/http.py`: `fetch_bytes` repete 3 vezes erro de transporte, 429 e 5xx e então levanta `NetworkError`; um 404 sai na hora como `httpx.HTTPStatusError` (sem retry; caso 18 de `tests/test_ons_reader.py`). Para detectar 404: `error.response.status_code == 404`.

`ingestion/db.py`: `upsert(conn, table, rows, keys, *, on_conflict="update", stamp_ingested_at=True) -> int` (devolve inseridas + atualizadas; não faz commit; recusa `ingested_at` no DataFrame quando carimba). `build_engine(url=None)` lê `DATABASE_URL`; sem ela, `MissingConfiguration`. Criar o engine não conecta.

`ingestion/checks.py`: `check(df, schema, expected_rows=None)` valida com `schema.validate(df, lazy=True)` e levanta um único `CheckFailed` com todos os problemas juntos (`"; ".join(problems)`). Esquemas existentes se chamam `WEATHER_FORECAST_SCHEMA` e `CALENDAR_SCHEMA` (módulo usa `import pandera.pandas as pa`).

`ingestion/jobs.py`: `issue_date(now=None) -> date` devolve a data de `now` em `America/Sao_Paulo` (reusar para "hoje", D7). Padrão de `load_calendar` (upsert em `engine.begin()`, releitura com `pd.read_sql_query`, `check`, `logger.info(...)`, devolve o número escrito):

```python
def load_calendar(engine: sqlalchemy.Engine, start: date, end: date) -> int:
    rows = build_calendar(start, end)          # ValueError if start > end
    with engine.begin() as conn:
        written = upsert(conn, "ref.calendar", rows, keys=["date"], on_conflict="update",
                         stamp_ingested_at=False)
        stored = pd.read_sql_query(_CALENDAR_REREAD_STATEMENT, conn, params={"start": start, "end": end})
    check(stored, CALENDAR_SCHEMA, expected_rows=(end - start).days + 1)
    logger.info("calendar ok: ...")
    return written
```

`ingestion/cli.py`: códigos 0 sucesso, 1 falha de execução ou de checagem (qualquer exceção do `run`, com traceback em stderr), 2 uso incorreto (argparse). Registro por `SUBCOMMANDS["nome"] = Subcommand(help=..., add_arguments=..., run=...)`; `run` importa `ingestion.jobs` e `build_engine` dentro da função (os testes fazem `monkeypatch.setattr("ingestion.jobs.<função>", ...)`), cria `httpx.Client(timeout=30)` e faz `engine.dispose()` no `finally`. O `calendar` usa `type=date.fromisoformat` e, com `--start` depois de `--end`, devolve **1** com `ValueError` no stderr (o job valida).

`infra/cron/crontab` hoje:

```
# Interim schedule until Prefect (ADR 0004). Times are America/Sao_Paulo (TZ from the image).
# The forecast job snapshots "today" in America/Sao_Paulo: keep it far from midnight.
30 6 * * * python -m ingestion weather-forecast
```

`tests/infra/test_crontab.py` (PR 16) já exige, para toda linha: 5 campos + comando; `python -m ingestion <subcomando conhecido em SUBCOMMANDS>`; minuto e hora fixos; nada nas horas 23 e 0; sem `>` ou `|`; nenhuma linha `NOME=valor`. Tem `forecast_line_problems(lines)` com `FORECAST_LINE` e exemplos negativos: o novo `ons_load_line_problems` segue o mesmo molde.

### Padrões de teste (`tests/test_job_weather_forecast.py`, `tests/test_ons_reader.py`, `tests/conftest.py`)

- Fixture de escrita por teste (não usar `migrated_database`, que é só leitura):

```python
@pytest.fixture
def load_database(fresh_database, monkeypatch) -> Iterator[str]:
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database
```

- Job como `ingestor`: `create_engine(url, connect_args={"options": "-c role=ingestor"})`, `base_delay=0`, `engine.dispose()` no `finally`.
- Parquet em memória com as 4 colunas e dtypes do ONS (`id_subsistema` object, `nom_subsistema`, `din_instante` `datetime64[ns]`, `val_cargaenergiamwmed` float64) e `frame.to_parquet(buffer)`, como `_frame`/`_to_parquet` de `tests/test_ons_reader.py`.
- Rede por `httpx.MockTransport` que responde pelo ano no caminho da URL (`CARGA_ENERGIA_<ano>.parquet`) e registra as requisições; nenhum teste toca a rede real.
- CLI sem banco: `monkeypatch.setenv("DATABASE_URL", <url fictícia>)`, `monkeypatch.setattr("ingestion.jobs.ingest_ons_load", fake)` e `monkeypatch.setattr("ingestion.jobs.issue_date", lambda *a, **k: dt.date(2026, 11, 8))`; código efetivo = retorno de `main(argv)` ou `SystemExit.code`.
- `pytestmark`/`@pytest.mark.db` nos testes com banco.

## 5. Passos

0. (test-writer e implementer, antes de tudo) Confirme que o PR 21 está na `main`: `git log --oneline -1 -- migrations/versions/0006_raw_ons_daily_load.py` mostra um commit e `uv run alembic heads` mostra `0006 (head)`. Confirme também que o `ingestor` tem `UPDATE` (o plano 21, D3, não faz `REVOKE`). Se não, **parar**.
1. (test-writer) Na branch `feat/job-ons-load`, a partir da `main` atualizada, escreva `tests/test_checks_ons_load.py`, `tests/test_job_ons_load.py` e as adições em `tests/infra/test_crontab.py` (seção 8). Rode `uv run pytest tests/test_checks_ons_load.py tests/test_job_ons_load.py tests/infra/test_crontab.py` e confirme que falham por `ImportError` de `ONS_DAILY_LOAD_SCHEMA`/`check_ons_daily_load`/`ingest_ons_load`, por subcomando `ons-load` inexistente ou pela linha ausente no crontab. `uv run ruff check .` e `uv run ruff format --check .` limpos. Commit `test: add ons-load job tests`.
2. (implementer) `ingestion/checks.py`:
   - `ONS_DAILY_LOAD_SCHEMA` (pandera): `subsystem` não nulo e em `SE`, `S`, `NE`, `N`; `date` não nulo; `load_avg_mw` float, não nulo, `0 < valor < 100000` (D5); unicidade (`subsystem`, `date`); `strict=False`.
   - `check_ons_daily_load(df, start, end, max_delay_days) -> None`: junta num único `CheckFailed` (mensagem com todos os problemas separados por `"; "`, como `check`) os problemas do esquema e estes, calculados sobre as datas presentes:
     - nenhuma linha no intervalo → problema `no rows between <start> and <end>`;
     - data com número de linhas diferente de 4 → problema citando a data ISO;
     - data faltando entre `start` e a maior data presente (inclusive) → problema citando as datas ISO que faltam (D6);
     - maior data < `end - max_delay_days` → problema `stale: last date <maior> is older than <end - max_delay_days>`.
3. `ingestion/jobs.py`, constantes no topo da seção do ONS, com comentário em inglês dizendo que são provisórias até o item 18:
   - `ONS_WINDOW_DAYS = 30` (D3), `ONS_MAX_DELAY_DAYS = 5` (D4). Tabela `"raw.ons_daily_load"`, chaves `["subsystem", "date"]`.
4. `ingest_ons_load(engine, client, start, end, *, max_delay_days=ONS_MAX_DELAY_DAYS, base_delay=1.0) -> int`:
   1. `start > end` → `ValueError` nomeando as duas datas, antes de qualquer requisição ou conexão.
   2. Para cada ano de `start.year` a `end.year`, em ordem, `fetch_load(client, year, base_delay=base_delay)`. `httpx.HTTPStatusError` com 404 **no ano de `end`** → `logger.warning("ONS load file for %d not published yet (404)", year)` e segue; 404 em qualquer outro ano, outro status ou `NetworkError`/`ValueError` → propaga (D8). Todo download e parse acontece antes de escrever: falha aqui não grava nada.
   3. Concatena e filtra `start <= date <= end`.
   4. Se houver linhas, numa transação (`engine.begin()`): `upsert(conn, "raw.ons_daily_load", frame, keys=["subsystem", "date"], on_conflict="update")`. Commit antes da checagem (D9).
   5. Relê `SELECT subsystem, "date", load_avg_mw FROM raw.ons_daily_load WHERE "date" BETWEEN :start AND :end ORDER BY "date", subsystem` e chama `check_ons_daily_load(stored, start, end, max_delay_days)`.
   6. `logger.info("ons-load ok: %d rows written from %s to %s, last date %s", ...)` e devolve o número do `upsert` (0 se nada foi escrito).
5. `ingestion/cli.py`, subcomando `ons-load` (help: `Upsert ONS daily load into raw.ons_daily_load (rolling window or --start/--end backfill)`):
   - `--start` e `--end` com `type=date.fromisoformat`; `--days` inteiro ≥ 1 (valor < 1 → erro de argparse, código 2), padrão `ONS_WINDOW_DAYS`.
   - `--days` e `--start` são mutuamente exclusivos (grupo do argparse → código 2).
   - `end = args.end or jobs.issue_date()`; `start = args.start or end - timedelta(days=days - 1)`.
   - `--start` depois de `--end` → o job levanta `ValueError` → código **1**, como o `calendar` (D11).
   - Chama `jobs.ingest_ons_load(engine, client, start, end)` com `httpx.Client(timeout=60)` (arquivo anual maior que o JSON do Open-Meteo).
6. `infra/cron/crontab`: acrescente, depois da linha do forecast, um comentário em inglês (`# ons-load time and window are provisional until the ONS publication delay is measured (plan 22).`) e a linha `0 7 * * * python -m ingestion ons-load`.
7. Rode os critérios de pronto e cole comando e saída no PR. No corpo do PR, liste D1 a D12 e destaque que D2, D3 e D4 são provisórios.

## 6. Critérios de pronto

Precisa do Postgres de teste: `docker compose -f infra/docker-compose.dev.yml up -d`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_checks_ons_load.py tests/test_job_ons_load.py tests/infra/test_crontab.py` | Todos passam, nenhum `skipped` |
| `uv run python -m ingestion ons-load --help` | Lista `--start`, `--end` e `--days`; código 0 |
| `uv run python -m ingestion ons-load --days 0; echo $?` | Erro de uso; `2` |
| Banco local migrado (`uv run alembic upgrade head`), `DATABASE_URL` apontando para ele, com rede: `uv run python -m ingestion ons-load; echo $?` | `0` (se der `1` por `stale`, é o atraso real do ONS: colar a mensagem no PR e não mexer em `ONS_MAX_DELAY_DAYS` sem combinar) |
| Em seguida: `select count(*), count(distinct "date"), min("date"), max("date") from raw.ons_daily_load` | `count = 4 × count(distinct date)`; `min` = hoje − 29 dias; `max` a no máximo 5 dias de hoje |
| Rodar o job de novo e repetir a consulta | Mesmos números |
| Backfill curto com rede: `uv run python -m ingestion ons-load --start 2015-01-01 --end 2015-12-31; echo $?` | `0`; `select count(*) from raw.ons_daily_load where "date" between '2015-01-01' and '2015-12-31'` = `1460` |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` e `docker run --rm platform-jobs supercronic -test /app/infra/cron/crontab; echo $?` | `0` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| `git diff --name-only main...HEAD` | Só os 7 arquivos da seção 4 |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: janela, virada de ano, 404 do ano novo, revisão de valor, idempotência e checagem de continuidade e atraso são lógica nova que garante "dado do dia todo dia, sem duplicata, revisões absorvidas".

## 8. Casos de teste

Parquets gerados no teste; "grade" = todos os dias do intervalo × `SE`, `S`, `NE`, `N`, com cargas plausíveis (ex.: `SE` 40000, `S` 12000, `NE` 11000, `N` 7000).

Checagem pura (`tests/test_checks_ons_load.py`, sem banco). `start = 2026-10-10`, `end = 2026-11-08`, `max_delay_days = 5` salvo indicação:

1. Grade de 2026-10-10 a 2026-11-05 → passa.
2. Um dia com só 3 subsistemas → `CheckFailed` citando essa data.
3. 2026-10-20 ausente nos 4 subsistemas → `CheckFailed` citando `2026-10-20`.
4. Grade começando em 2026-10-12 (faltam 10 e 11) → `CheckFailed` citando `2026-10-10` e `2026-10-11`.
5. Grade até 2026-11-02 (6 dias antes de `end`) → `CheckFailed` com `stale`; até 2026-11-03 (5 dias) → passa.
6. `load_avg_mw` = `0.0`, `-1.0` ou `150000.0` em uma linha → `CheckFailed` mencionando `load_avg_mw`.
7. `subsystem` = `SIN` em uma linha → `CheckFailed`.
8. Linha duplicada (`SE`, 2026-10-15) → `CheckFailed`.
9. DataFrame vazio → `CheckFailed` com `no rows`.
10. Dois problemas ao mesmo tempo (uma carga 0 e um dia faltando) → um único `CheckFailed` que cita os dois.

Job com banco (`tests/test_job_ons_load.py`, `db`, como `ingestor`, `base_delay=0`):

11. Parquet de 2026 com grade de 2026-09-01 a 2026-11-05; `start = 2026-10-10`, `end = 2026-11-08` → devolve 108; 108 linhas na tabela (27 dias × 4), nenhuma antes de 2026-10-10; `ingested_at` não nulo; uma única requisição, para `CARGA_ENERGIA_2026.parquet`.
12. Repetir o caso 11 com o mesmo parquet → continua 108 linhas, mesmos valores.
13. Segunda execução com `SE` 2026-10-15 alterado de 40000 para 40500 no parquet (revisão do ONS) → banco com 40500; outras linhas iguais; total 108; `ingested_at` dessa linha maior que o da primeira escrita.
14. Revisão fora da janela: valor de 2026-09-15 alterado no parquet e mesma janela do caso 11 → linha de 2026-09-15 não existe no banco (a janela não grava fora de `start`).
15. Virada de ano: `start = 2026-12-20`, `end = 2027-01-05`, parquets de 2026 (grade até 2026-12-31) e 2027 (grade 2027-01-01 a 2027-01-03) → requisições para 2026 e 2027; 60 linhas (15 dias × 4); passa.
16. Ano novo não publicado: `start = 2026-12-04`, `end = 2027-01-02`, 2027 responde 404, 2026 tem grade até 2026-12-31 → sem exceção; 112 linhas (28 dias × 4) de 2026; devolve 112.
17. Mesmo 404 de 2027, mas 2026 com grade só até 2026-12-26 e `end = 2027-01-02` → grava as linhas de 2026 e levanta `CheckFailed` com `stale` (não `HTTPStatusError`).
18. Backfill `start = 2015-01-01`, `end = 2016-12-31`, 2015 responde 404 e 2016 tem grade → `httpx.HTTPStatusError` (404 fora do ano de `end` é erro) e tabela vazia.
19. Backfill `start = 2015-01-01`, `end = 2015-12-31` com grade completa de 2015 → 1460 linhas; passa (o atraso conta a partir de `end`, não de hoje).
20. Um dia com só 3 subsistemas no parquet dentro da janela → `CheckFailed`; as linhas recebidas continuam gravadas.
21. `load_avg_mw = 0.0` num dia → `CheckFailed`; as 108 linhas ficaram gravadas (inclusive a com 0).
22. Parquet com `id_subsistema = "SE/CO"` → `ValueError`; tabela vazia.
23. Arquivo de 2026 responde 503 três vezes → `NetworkError`; tabela vazia.
24. `start = 2026-11-08`, `end = 2026-11-01` → `ValueError` com as duas datas; nenhuma requisição feita.

CLI (`tests/test_job_ons_load.py`, sem banco, job e `issue_date` substituídos; hoje = 2026-11-08):

25. `ons-load` → código 0; o job recebe `start = 2026-10-10`, `end = 2026-11-08`.
26. `ons-load --days 10` → `start = 2026-10-30`, `end = 2026-11-08`.
27. `ons-load --start 2015-01-01 --end 2015-12-31` → recebe exatamente essas datas.
28. `ons-load --end 2026-01-31` → `start = 2026-01-02`, `end = 2026-01-31`.
29. `ons-load --start 2026-11-01` → `start = 2026-11-01`, `end = 2026-11-08`.
30. `ons-load --start 2026-11-01 --days 5` → código 2.
31. `ons-load --days 0` → código 2; `ons-load --start 2026-13-01` → código 2.
32. Job levanta `CheckFailed` → código 1.
33. `ons-load --start 2026-02-01 --end 2026-01-01`, com `DATABASE_URL` fictícia e o job real (a validação vem antes de conectar e de qualquer requisição) → código 1 e `ValueError` no stderr.
34. Sem `DATABASE_URL` → código 1 e `DATABASE_URL` no stderr.

Crontab (`tests/infra/test_crontab.py`):

35. Existe exatamente uma linha `ons-load`, igual a `0 7 * * * python -m ingestion ons-load` (espaços normalizados), sem argumentos; a linha do forecast continua `30 6 * * * python -m ingestion weather-forecast`.
36. Exemplos negativos de `ons_load_line_problems`: lista vazia; linha duplicada; `5 7 * * *`; `0 8 * * *`; `0 7 * * 1-5`; com `--days 30` → todos com problema.
37. As regras existentes (subcomando conhecido, hora fixa, longe da meia-noite, sem redirecionamento, sem variável) passam com a linha nova.

Já existentes que continuam verdes sem edição: `tests/test_ons_reader.py`, `tests/test_raw_ons_daily_load.py` (PR 21), `tests/test_job_weather_forecast.py`, `tests/test_calendar.py`, `tests/test_cli.py`, `tests/infra/test_jobs_image.py`, `tests/infra/test_compose.py`.

## 9. Riscos e perguntas em aberto

Nenhuma pergunta em aberto bloqueia. Decisões (recomendações adotadas, com autorização do usuário):

- **D1. Um subcomando para o diário e o backfill.** O doc diz "um backfill é só o mesmo job com um intervalo maior"; o item 23 roda `ons-load --start 2015-01-01 --end <ontem>`.
- **D2. 07:00 provisório.** É o horário do roadmap e fica fora da faixa 23:00–00:59 que o teste do crontab proíbe. Como o arquivo foi reescrito às 19:00 BRT de sábado, pode ser que o ONS publique à noite; se o item 18 mostrar isso, o ajuste é só mudar a linha do crontab e o caso 35.
- **D3. Janela de 30 dias provisória (`ONS_WINDOW_DAYS`).** É o valor do doc; a profundidade das revisões só sai em 2026-11-15. `--days` permite rodar janela maior sem mudar código.
- **D4. Atraso máximo de 5 dias provisório (`ONS_MAX_DELAY_DAYS`).** A única medição deu D−3 num domingo às 11:50; numa segunda às 07:00 o esperado é D−4 se o ONS não publicar no fim de semana, e um feriado colado soma um dia. 5 evita alarme falso enquanto não há medição em dia útil; fica mais apertado depois do item 18.
- **D5. "Unidade MWmed" verificada por faixa: `0 < load_avg_mw < 100000`.** Pandera não vê unidade; a faixa pega carga não positiva (regra do doc) e erro de unidade (MWh do dia seria ~24 vezes maior: o `SE`, ~40000 MWmed, viraria ~960000). 100000 fica acima de qualquer subsistema (o SIN inteiro é ~80000).
- **D6. Continuidade medida de `start` até a maior data presente.** Buracos no início (inclusive no backfill) e no meio falham; o fim aberto é coberto pela regra de atraso, contada a partir de `end` (por isso o backfill de 2015 passa).
- **D7. "Hoje" em `America/Sao_Paulo`, reusando `jobs.issue_date()`.** Mesmo fuso do crontab; não cria função nova.
- **D8. Virada de ano e 404.** O job baixa todos os anos entre `start.year` e `end.year` (no início de janeiro, a janela de 30 dias já inclui o ano anterior). Um 404 só é tolerado no ano de `end`, que é o arquivo que o ONS pode ainda não ter criado; quem decide se isso é falha é a checagem de atraso (caso 17). 404 em outro ano é arquivo que deveria existir → erro.
- **D9. Grava e depois checa, em transações separadas.** Igual ao forecast: "checagem falha = execução falha", mas o dado recebido fica gravado para diagnóstico (a tabela aceita carga 0, plano 21 D4). Download e parse vêm antes de qualquer escrita: erro de fonte não grava nada.
- **D10. Ajuste pós-item 18 é PR separado.** Muda só as constantes, a linha do crontab e os testes que as fixam; não bloqueia este PR.
- **D11. `--start` depois de `--end` → código 1 (`ValueError` do job), não 2.** Mesmo comportamento do `calendar` mergeado; o job valida também quando chamado sem CLI. Muda a decisão da versão anterior deste plano (código 2).
- **D12. Sem dependência nova e sem mudar `ingestion/ons.py`.** O 404 é tratado no job pelo `httpx.HTTPStatusError` que `fetch_load` já propaga.

Riscos:

- **S3 pode responder 403 em vez de 404** para objeto inexistente em bucket sem listagem pública. A listagem do prefixo funcionou no item 18, então a expectativa é 404; se em janeiro vier 403, o job falha com código 1 (falha alta, não silenciosa) e o ajuste é incluir 403 na regra do D8.
- **Revisões além de 30 dias** não são absorvidas pela rodada diária. Mitigação até o item 18: rodar `ons-load --days N` ou um backfill do ano.
- **Linha removida pelo ONS** não é apagada (sem `DELETE` para o `ingestor`); correção manual pelo admin.
- **Atraso real maior que 5 dias** faz o job falhar todo dia até o ajuste; sem alertas (PR 55), a falha só aparece no log do container `scheduler`.
- **Memória do backfill:** 12 arquivos anuais de ~1460 linhas: irrelevante.
- **Postgres de teste:** sem o container, os testes `db` falham (não pulam), por desenho de `tests/conftest.py`.

## 10. Decisões que exigem ADR

- **Nenhum ADR novo.** A tabela e o modo `on_conflict="update"` estão cobertos pelo ADR 0005 e pelo plano 21; o agendamento pelo supercronic, pelo ADR 0004; nada é exposto na rede (ADR 0003); nomes seguem o ADR 0001; nenhuma dependência nova (ADR 0002). Não muda schema de `raw`/`ref` nem o contrato `build_features`/`predict`/`evaluate`.
