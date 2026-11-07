# 26 — Job `clima-observado`: janela de 10 dias, backfill, checagem e agenda 06:45

> Executa: agente. Depende de: 16, 24, 25. Branch sugerida: `feat/job-clima-observado`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar o job que faz upsert do clima observado dos últimos 10 dias (ou de um intervalo, para backfill) para todos os locais de `ref.locais`, com checagem pandera.
Acrescentar a execução diária às 06:45 BRT ao crontab.

## 2. Fora do escopo

- Rodar o backfill em produção (item 27). Prefect (PR 32). Alertas (PR 55).

## 3. Fase do roadmap

Fase 2 — "`raw.clima_observado` + backfill desde 2015".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `ingestion/checks.py` | `SCHEMA_CLIMA_OBSERVADO` e `checar_continuidade_clima(df, fim, atraso_max_dias)` |
| `ingestion/jobs.py` | `ingest_clima_observado(engine, cliente, inicio, fim, *, atraso_max_dias, espera_base)` |
| `ingestion/cli.py` | Subcomando `clima-observado [--inicio] [--fim] [--dias N]` |
| `infra/cron/crontab` | Linha `45 6 * * * python -m ingestion clima-observado` |
| `tests/test_job_clima_observado.py`, `tests/infra/test_crontab.py` | Testes (test-writer) |

Código existente: `ingestion/openmeteo.py` (`buscar_observado`), `ingestion/jobs.py` (`listar_locais`, `ingest_clima_previsao` e `ingest_ons_carga` como referência de estilo), `ingestion/checks.py`, `ingestion/db.py` (`upsert`).

Do doc: "06:45 `ingest_clima_observado` — Upsert dos últimos 10 dias de clima observado (cobre atraso e correções da fonte)". Backfill desde 2015. Faixa plausível de temperatura: −10 a 50 °C.

## 5. Passos

1. (test-writer) Escreva os testes da seção 8 com `banco_migrado` e `httpx.MockTransport` (respostas montadas no teste no formato da fixture `tests/fixtures/openmeteo_arquivo_sao_paulo.json`). Em `tests/infra/test_crontab.py`: exatamente uma linha `clima-observado` com `45 6 * * *`. Confirme falha. Commit `test: add clima-observado job tests`.
2. (implementer) `checks.py`:
   - `SCHEMA_CLIMA_OBSERVADO`: chaves não nulas; mesmas faixas de `SCHEMA_CLIMA_PREVISAO` (temperaturas −10 a 50, `temp_min <= temp_max`, `precip_mm` ≥ 0, `vento_max` ≥ 0, `umidade_media` 0 a 100); unicidade (`local_id`, `data`). Extraia as faixas comuns para não duplicar.
   - `checar_continuidade_clima(df, locais, fim, atraso_max_dias)`: para cada local, sem dia faltando entre a menor e a maior data, e maior data ≥ `fim - atraso_max_dias`.
3. `jobs.py`, `ingest_clima_observado(engine, cliente, inicio, fim, *, atraso_max_dias=7, espera_base=1.0)`: mesmo padrão de `ingest_clima_previsao` (busca por local, continua se um local falhar, grava os que deram certo, falha no fim citando os locais), mas com `ao_conflitar="atualizar"` (o observado pode ser corrigido pela fonte) e chaves `["local_id", "data"]`. Depois de gravar, relê o intervalo e checa.
4. CLI `clima-observado`: sem argumentos, `fim` = hoje (BRT) e `inicio = fim - 9`; `--dias`, `--inicio`, `--fim` como no `ons-carga`.
5. Acrescente a linha ao crontab.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_job_clima_observado.py tests/infra/test_crontab.py` | Todos passam |
| Banco local migrado, com rede: `uv run python -m ingestion clima-observado; echo $?` | `0` |
| `select local_id, count(*), max(data) from raw.clima_observado group by 1` | 4 locais; `max(data)` dentro do atraso do ERA5 |
| Rodar de novo e contar | Mesmo número |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: mesma justificativa do ONS (janela, correção da fonte, continuidade), mais a falha parcial por local.

## 8. Casos de teste

1. 4 locais, API devolve 10 dias completos → 40 linhas.
2. Rodar de novo → 40 linhas.
3. Segunda execução com `precip_mm` corrigido num dia → valor novo no banco (diferente da previsão, aqui atualiza).
4. ERA5 sem os 5 dias mais recentes (todas as variáveis nulas) e `atraso_max_dias=7` → 20 linhas, sem erro.
5. Mesmo cenário com `atraso_max_dias=3` → `ChecagemFalhou` (dado atrasado demais).
6. API falha só para `belem` → 30 linhas gravadas e erro citando `belem`.
7. Buraco de um dia no meio para um local → `ChecagemFalhou` citando local e data.
8. `temp_min > temp_max` num dia → `ChecagemFalhou`.
9. Backfill `--inicio 2015-01-01 --fim 2015-12-31` → 1460 linhas (365 × 4).
10. CLI `--inicio` depois de `--fim` → código 2.

## 9. Riscos e perguntas em aberto

- `atraso_max_dias=7` é palpite até o item 18.

## 10. Decisões que exigem ADR

Nenhuma.
