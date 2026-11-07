# 13 — Tabela `raw.weather_forecast`

> Executa: agente. Depende de: 09. Branch sugerida: `feat/raw-weather-forecast`.
> Pré-requisitos: ADR "Contrato de dados v1" (PR 09) aprovado, com a decisão P8 (semântica de `issued_at`) registrada.
> **Antecipado**: item da Fase 2 feito antes do fim da Fase 1, porque cada dia sem coleta é histórico perdido (desvio de "uma fase por vez" aprovado pelo usuário em 2026-11-07, P5 resolvida).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar por migração a tabela de snapshots de previsão do tempo, um registro por local, data de emissão e data-alvo.
É a tabela mais urgente da plataforma: o histórico dela só começa no dia em que a coleta ligar.

## 2. Fora do escopo

- Cliente HTTP (PR 14) e job (PR 15).
- `raw.weather_observed` (PR 25).
- Backfill de previsões passadas (o doc exclui; ver P10 no índice).

## 3. Fase do roadmap

Fase 2 — Clima: "`raw.weather_forecast` coletando todo dia (prioridade)".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0004_raw_weather_forecast.py` | Cria a tabela; `downgrade` a remove |
| `tests/test_raw_weather_forecast.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`):

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `raw.weather_forecast` | `location_id`, `issued_at`, `target_date`, `horizon_days`, mesmas variáveis (`temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`), `ingested_at` | (`location_id`, `issued_at`, `target_date`) | Plataforma | Todos |

Por que existe (do doc): "O modelo de carga só pode usar, no dia D, a previsão disponível em D — usar o clima observado de D+1 seria vazamento de dados."

## 5. Passos

1. (test-writer) Escreva `tests/test_raw_weather_forecast.py` (`@pytest.mark.db`, banco migrado) com os casos da seção 8. Confirme falha porque a tabela não existe. Commit `test: add raw.weather_forecast tests`.
2. (implementer) `uv run alembic revision -m "raw_weather_forecast" --rev-id 0004`.
3. `upgrade`, tabela `raw.weather_forecast`:
   - `location_id text not null references ref.locations(location_id)`
   - `issued_at date not null` (dia, no fuso `America/Sao_Paulo`, em que o snapshot foi tirado; ver P8)
   - `target_date date not null`
   - `horizon_days smallint generated always as (target_date - issued_at) stored`, com `check (horizon_days between 0 and 16)`
   - `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`: `double precision`, aceitam nulo (a fonte pode não ter a variável; a checagem do PR 15 decide)
   - `ingested_at timestamptz not null`
   - `primary key (location_id, issued_at, target_date)`
   - Comentário na tabela (`COMMENT ON TABLE`): "Previsão como emitida. Nunca sobrescrever um snapshot antigo."
4. `downgrade`: `DROP TABLE raw.weather_forecast`.
5. Permissões vêm dos privilégios padrão (PR 07). Não repetir `GRANT`.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_raw_weather_forecast.py tests/test_migrations.py` | Todos passam |
| `uv run alembic heads` | `0004 (head)` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: chave, coluna gerada e restrições definem o contrato que a cientista vai consultar; erro aqui é caro de corrigir depois que o histórico começa.

## 8. Casos de teste

1. Inserir (`sao_paulo`, emitida `2026-11-07`, alvo `2026-11-10`) → `horizon_days` = 3.
2. Inserir a mesma chave duas vezes (sem `ON CONFLICT`) → violação de chave primária.
3. Mesmo `location_id` e `target_date` com `issued_at` diferentes → duas linhas coexistem (snapshots distintos).
4. `location_id = 'does_not_exist'` → violação de chave estrangeira.
5. `target_date` anterior a `issued_at` → violação de `CHECK`.
6. `target_date` 17 dias depois de `issued_at` → violação de `CHECK`.
7. Tentar informar `horizon_days` no `INSERT` → erro (coluna gerada).
8. Como `ingestor`, `INSERT` funciona; como `reader` e `scientist`, só `SELECT`.
9. `downgrade` até `0003` remove a tabela; `ref.locations` continua.

## 9. Riscos e perguntas em aberto

- P8: `issued_at` como `date` segue o doc ("`issued_at` = hoje"). Alternativa: `timestamptz` com a hora da coleta, que permitiria mais de um snapshot por dia. Com `date`, uma segunda execução no mesmo dia não cria snapshot novo (o PR 15 usa `ignore` no conflito e preserva o primeiro). Decidir antes do merge; mudar depois exige migração de contrato.
- Coluna gerada é proposta deste plano: garante que `horizon_days` nunca fique inconsistente. O job do PR 15 não envia essa coluna.

## 10. Decisões que exigem ADR

Coberto pelo ADR "Contrato de dados v1" (PR 09), que deve registrar P8.
