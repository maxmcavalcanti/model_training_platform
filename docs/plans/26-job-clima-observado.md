# 26 — Job `weather-observed`: janela de 10 dias, backfill, checagem e agenda 06:45

> Executa: agente. Depende de: 16, 24, 25. Branch sugerida: `feat/job-weather-observed`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar o job que faz upsert do clima observado dos últimos 10 dias (ou de um intervalo, para backfill) para todos os locais de `ref.locations`, com checagem pandera.
Acrescentar a execução diária às 06:45 BRT ao crontab.

## 2. Fora do escopo

- Rodar o backfill em produção (item 27). Prefect (PR 32). Alertas (PR 55).

## 3. Fase do roadmap

Fase 2 — "`raw.weather_observed` + backfill desde 2015".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `ingestion/checks.py` | `SCHEMA_WEATHER_OBSERVED` e `check_weather_continuity(df, fim, max_delay_days)` |
| `ingestion/jobs.py` | `ingest_weather_observed(engine, cliente, inicio, fim, *, max_delay_days, base_delay)` |
| `ingestion/cli.py` | Subcomando `weather-observed [--start] [--end] [--days N]` |
| `infra/cron/crontab` | Linha `45 6 * * * python -m ingestion weather-observed` |
| `tests/test_job_weather_observed.py`, `tests/infra/test_crontab.py` | Testes (test-writer) |

Código existente: `ingestion/openmeteo.py` (`fetch_observed`), `ingestion/jobs.py` (`list_locations`, `ingest_weather_forecast` e `ingest_ons_load` como referência de estilo), `ingestion/checks.py`, `ingestion/db.py` (`upsert`).

Do doc: "06:45 `ingest_weather_observed` — Upsert dos últimos 10 dias de clima observado (cobre atraso e correções da fonte)". Backfill desde 2015. Faixa plausível de temperatura: −10 a 50 °C.

## 5. Passos

1. (test-writer) Escreva os testes da seção 8 com `migrated_database` e `httpx.MockTransport` (respostas montadas no teste no formato da fixture `tests/fixtures/openmeteo_archive_sao_paulo.json`). Em `tests/infra/test_crontab.py`: exatamente uma linha `weather-observed` com `45 6 * * *`. Confirme falha. Commit `test: add weather-observed job tests`.
2. (implementer) `checks.py`:
   - `SCHEMA_WEATHER_OBSERVED`: chaves não nulas; mesmas faixas de `SCHEMA_WEATHER_FORECAST` (temperaturas −10 a 50, `temp_min <= temp_max`, `precip_mm` ≥ 0, `wind_speed_max` ≥ 0, `humidity_mean` 0 a 100); unicidade (`location_id`, `data`). Extraia as faixas comuns para não duplicar.
   - `check_weather_continuity(df, locais, fim, max_delay_days)`: para cada local, sem dia faltando entre a menor e a maior data, e maior data ≥ `fim - max_delay_days`.
3. `jobs.py`, `ingest_weather_observed(engine, cliente, inicio, fim, *, max_delay_days=7, base_delay=1.0)`: mesmo padrão de `ingest_weather_forecast` (busca por local, continua se um local falhar, grava os que deram certo, falha no fim citando os locais), mas com `on_conflict="atualizar"` (o observado pode ser corrigido pela fonte) e chaves `["location_id", "data"]`. Depois de gravar, relê o intervalo e checa.
4. CLI `weather-observed`: sem argumentos, `fim` = hoje (BRT) e `inicio = fim - 9`; `--days`, `--start`, `--end` como no `ons-load`.
5. Acrescente a linha ao crontab.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_job_weather_observed.py tests/infra/test_crontab.py` | Todos passam |
| Banco local migrado, com rede: `uv run python -m ingestion weather-observed; echo $?` | `0` |
| `select location_id, count(*), max(data) from raw.weather_observed group by 1` | 4 locais; `max(data)` dentro do atraso do ERA5 |
| Rodar de novo e contar | Mesmo número |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: mesma justificativa do ONS (janela, correção da fonte, continuidade), mais a falha parcial por local.

## 8. Casos de teste

1. 4 locais, API devolve 10 dias completos → 40 linhas.
2. Rodar de novo → 40 linhas.
3. Segunda execução com `precip_mm` corrigido num dia → valor novo no banco (diferente da previsão, aqui atualiza).
4. ERA5 sem os 5 dias mais recentes (todas as variáveis nulas) e `max_delay_days=7` → 20 linhas, sem erro.
5. Mesmo cenário com `max_delay_days=3` → `CheckFailed` (dado atrasado demais).
6. API falha só para `belem` → 30 linhas gravadas e erro citando `belem`.
7. Buraco de um dia no meio para um local → `CheckFailed` citando local e data.
8. `temp_min > temp_max` num dia → `CheckFailed`.
9. Backfill `--start 2015-01-01 --end 2015-12-31` → 1460 linhas (365 × 4).
10. CLI `--start` depois de `--end` → código 2.

## 9. Riscos e perguntas em aberto

- `max_delay_days=7` é palpite até o item 18.

## 10. Decisões que exigem ADR

Nenhuma.
