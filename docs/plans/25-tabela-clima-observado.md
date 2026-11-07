# 25 — Tabela `raw.weather_observed`

> Executa: agente. Depende de: 21 (próxima revisão Alembic). Branch sugerida: `feat/raw-weather-observed`.
> Pré-requisito: ADR "Contrato de dados v1" (PR 09).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar por migração a tabela de clima observado diário por local.
É o "real" do modelo `rain_d1` e a fonte de clima para treino do `load_d1`.

## 2. Fora do escopo

- Cliente (PR 24), job, checagem e backfill (PR 26 e item 27).

## 3. Fase do roadmap

Fase 2 — "`raw.weather_observed` + backfill desde 2015".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0007_raw_weather_observed.py` | Tabela; `downgrade` a remove |
| `tests/test_raw_weather_observed.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`): `raw.weather_observed` — `location_id`, `date`, `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`, `ingested_at`; chave (`location_id`, `date`); escreve Plataforma; lê Todos.

## 5. Passos

1. (test-writer) Escreva os testes da seção 8 (`@pytest.mark.db`, banco migrado). Confirme falha porque a tabela não existe. Commit `test: add raw.weather_observed tests`.
2. (implementer) `uv run alembic revision -m "raw_weather_observed" --rev-id 0007` (ou o próximo número livre).
3. `upgrade`: `raw.weather_observed (location_id text not null references ref.locations(location_id), date date not null, temp_max double precision, temp_min double precision, precip_mm double precision, wind_speed_max double precision, humidity_mean double precision, ingested_at timestamptz not null, primary key (location_id, date))`. Variáveis aceitam nulo, como em `raw.weather_forecast` (PR 13).
4. `downgrade`: `DROP TABLE raw.weather_observed`.
5. Permissões pelos privilégios padrão (PR 07).
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_raw_weather_observed.py tests/test_migrations.py` | Todos passam |
| `uv run alembic heads` | `0007 (head)` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: chave e chave estrangeira fazem parte do contrato.

## 8. Casos de teste

1. Inserir (`recife`, 2026-11-05, valores, now()) funciona.
2. Mesma (`location_id`, `date`) duas vezes sem `ON CONFLICT` → violação de chave primária.
3. `location_id` inexistente em `ref.locations` → violação de chave estrangeira.
4. Variáveis nulas são aceitas.
5. Como `ingestor`, `INSERT` funciona; como `scientist` e `reader`, só `SELECT`.
6. `downgrade` de um passo remove só esta tabela.

## 9. Riscos e perguntas em aberto

- Nenhum além do ADR de contrato.

## 10. Decisões que exigem ADR

Coberto pelo ADR "Contrato de dados v1".
