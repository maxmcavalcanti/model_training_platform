# 22 — Job `ons-load`: janela de 30 dias, backfill por intervalo, checagem e agenda 07:00

> Executa: agente. Depende de: 16 (crontab), 20, 21. Branch sugerida: `feat/job-ons-load`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar o job que lê o(s) parquet(s) do ONS, faz upsert em `raw.ons_daily_load` dos últimos 30 dias (ou de um intervalo dado, para backfill) e termina com checagem pandera.
Acrescentar a execução diária às 07:00 BRT ao crontab do agendador.

## 2. Fora do escopo

- Rodar o backfill em produção (item 23).
- Flow do Prefect (PR 32), alertas (PR 55).

## 3. Fase do roadmap

Fase 1 — "Ingestão do ONS + backfill desde 2015 + checagens".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `ingestion/checks.py` | `SCHEMA_ONS_LOAD` e `check_ons_continuity(df, fim, max_delay_days)` |
| `ingestion/jobs.py` | `ingest_ons_load(engine, cliente, inicio, fim, *, max_delay_days, base_delay)` |
| `ingestion/cli.py` | Subcomando `ons-load [--start AAAA-MM-DD] [--end AAAA-MM-DD] [--days N]` |
| `infra/cron/crontab` | Linha `0 7 * * * python -m ingestion ons-load` |
| `tests/test_job_ons_load.py`, `tests/infra/test_crontab.py` | Testes (test-writer) |

Código existente: `ingestion/ons.py` (`download_load(cliente, ano)`), `ingestion/db.py` (`upsert`), `ingestion/checks.py` (`checar`, `CheckFailed`), `ingestion/cli.py` (`SUBCOMMANDS`).

Do doc (`docs/plataforma-ml.md`, "Ingestão"): "07:00 `ingest_ons_load` — Lê o parquet do ano corrente no S3 e faz upsert dos últimos 30 dias (cobre revisões do ONS)". "Backfill inicial: carga do ONS … desde 2015". "um backfill é só o mesmo job com um intervalo maior". Checagem: "linhas esperadas por dia, sem nulos nas colunas-chave, valores dentro de faixas plausíveis (carga positiva…)".

Use os resultados do item 18 (atraso de publicação e profundidade das revisões). Se não estiverem em `docs/plataforma-ml.md`, use os padrões abaixo e anote no PR.

## 5. Passos

1. (test-writer) Escreva os testes da seção 8 com `migrated_database` e `httpx.MockTransport` servindo parquets gerados no teste (um por ano, colunas do PR 20). Acrescente em `tests/infra/test_crontab.py`: existe exatamente uma linha `ons-load` com agenda `0 7 * * *`. Confirme falha. Commit `test: add ons-load job tests`.
2. (implementer) `checks.py`:
   - `SCHEMA_ONS_LOAD`: `subsistema` em `SE, S, NE, N`; `data` não nula; `load_avg_mw` > 0; unicidade (`subsistema`, `data`).
   - `check_ons_continuity(df, fim, max_delay_days)`: cada data presente tem exatamente 4 linhas; não há data faltando entre a menor e a maior; a maior data é ≥ `fim - max_delay_days`. Falha → `CheckFailed`.
3. `jobs.py`, `ingest_ons_load(engine, cliente, inicio, fim, *, max_delay_days=2, base_delay=1.0)`:
   1. Para cada ano entre `inicio.year` e `fim.year`, `download_load`. 404 no ano de `fim` quando `fim` está nos primeiros dias de janeiro → registra aviso e segue (o arquivo do ano novo ainda não existe); 404 em outro ano → erro.
   2. Filtra `inicio <= data <= fim`.
   3. `upsert(..., "raw.ons_daily_load", chaves=["subsistema", "data"], on_conflict="atualizar")` numa transação.
   4. Relê o intervalo do banco e roda `checar(df, SCHEMA_ONS_LOAD)` e `check_ons_continuity(df, fim, max_delay_days)`.
4. CLI `ons-load`: sem argumentos → `fim` = hoje (BRT) e `inicio = fim - 29 dias`. `--days N` muda a janela. `--start`/`--end` explícitos (backfill) têm precedência; `--start` depois de `--end` → código 2.
5. Acrescente a linha ao `infra/cron/crontab`.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_job_ons_load.py tests/infra/test_crontab.py` | Todos passam |
| Banco local migrado, com rede: `uv run python -m ingestion ons-load; echo $?` | `0` |
| Em seguida: `select count(*), min(data), max(data) from raw.ons_daily_load` | ~120 linhas (30 dias × 4), `max(data)` a no máximo 2 dias de hoje |
| Rodar de novo e contar | Mesmo número |
| `docker run --rm platform-jobs supercronic -test /app/infra/cron/crontab` (após `docker build`) | Código 0 |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: janela que cruza o ano, revisão de valor e checagem de continuidade são as regras que garantem "dado do dia chega todo dia, sem duplicata".

## 8. Casos de teste

1. Parquet do ano com 60 dias × 4 subsistemas, `fim` = último dia, janela padrão → 120 linhas gravadas (só 30 dias).
2. Rodar de novo → 120 linhas (sem duplicata).
3. Segunda execução com o valor de um dia já gravado alterado no parquet (revisão do ONS) → valor novo no banco.
4. Janela de 2026-12-20 a 2027-01-05 → busca os arquivos de 2026 e 2027 e grava os dias dos dois anos.
5. `fim` = 2027-01-02 e o arquivo de 2027 devolve 404 → grava os dias de 2026 da janela, sem exceção pelo 404. (A checagem de atraso pode falhar; isso é esperado e deve ser a causa da falha, não o 404.)
6. 404 no arquivo de 2025 num backfill 2015–2026 → erro.
7. Um dia com só 3 subsistemas → `CheckFailed`.
8. Um dia faltando no meio da janela → `CheckFailed` citando a data.
9. Última data 5 dias antes de `fim` com `max_delay_days=2` → `CheckFailed` (dado atrasado).
10. `load_avg_mw = 0` num dia → `CheckFailed` (e as linhas ficaram gravadas).
11. Backfill: `--start 2015-01-01 --end 2015-12-31` com parquet de 2015 → 1460 linhas.
12. CLI `ons-load --start 2026-02-01 --end 2026-01-01` → código 2.

## 9. Riscos e perguntas em aberto

- `max_delay_days=2` e o horário 07:00 são palpites até o item 18. Se o ONS publica D−1 só à tarde, mudar o horário na linha do crontab neste PR.
- Backfill de 12 arquivos anuais de uma vez: cabe em memória (poucas dezenas de milhares de linhas).

## 10. Decisões que exigem ADR

Nenhuma.
