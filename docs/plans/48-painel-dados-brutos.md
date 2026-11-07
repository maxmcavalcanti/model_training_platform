# 48 — Painel de dados brutos no Grafana (provisionado por arquivo)

> Executa: agente. Depende de: 47. Branch sugerida: `feat/dashboard-raw-data`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Provisionar um painel "Dados brutos" com a carga do ONS por subsistema, o clima observado por local e a saúde da coleta de previsões (linhas por `issued_at`).
As consultas SQL são testadas contra o banco de teste com o usuário `reader`.

## 2. Fora do escopo

- Previsões (PR 49). Erro real × previsto (PR 58).

## 3. Fase do roadmap

Fase 4 — "Grafana com dados brutos e previsões".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/grafana/provisioning/dashboards/platform.yaml` | Provider que carrega JSONs de `/etc/grafana/dashboards` |
| `infra/grafana/dashboards/raw-data.json` | O painel |
| `infra/docker-compose.yml` | Montar `./grafana/dashboards:/etc/grafana/dashboards:ro` |
| `tests/infra/test_dashboards_sql.py` | Executa o SQL de cada painel (test-writer) |

Tabelas (já existem): `raw.ons_daily_load(subsystem, date, load_avg_mw, ingested_at)`, `raw.weather_observed(location_id, date, temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean, ingested_at)`, `raw.weather_forecast(location_id, issued_at, target_date, horizon_days, ..., ingested_at)`, `ref.locations(location_id, name, lat, lon, subsystem)`. Datasource `uid: ml` (PR 47).

## 5. Passos

1. (test-writer) `tests/infra/test_dashboards_sql.py`, genérico para todo JSON em `infra/grafana/dashboards/`: extrai cada `targets[].rawSql`, troca as macros do Grafana por SQL comum (`$__timeFilter(col)` → `col >= now() - interval '30 days'`; `$__timeFrom()` → `now() - interval '30 days'`; `$__timeTo()` → `now()`; variáveis `$var` → valor de teste definido no próprio teste), e executa como `reader` num banco migrado com algumas linhas inseridas pelo admin. Casos na seção 8. Confirme falha porque o JSON não existe. Commit `test: add grafana panel sql tests`.
2. (implementer) Provider `platform.yaml` (`apiVersion: 1`, `providers: [{name: platform, type: file, options: {path: /etc/grafana/dashboards}, allowUiUpdates: false}]`).
3. `raw-data.json` (uid `raw-data`), painéis, todos com datasource `uid: ml` e `format: time_series` ou `table`:
   - "Carga diária por subsistema (MWmed)": `select date::timestamp as time, subsystem as metric, load_avg_mw as value from raw.ons_daily_load where $__timeFilter(date::timestamp) order by 1`.
   - "Temperatura máxima observada por local": análogo com `raw.weather_observed`.
   - "Snapshots de previsão por dia (esperado: 4 × 7)": `select issued_at::timestamp as time, count(*) as value from raw.weather_forecast where $__timeFilter(issued_at::timestamp) group by 1 order by 1`.
   - "Última data por fonte" (tabela): `max(date)` do ONS, `max(date)` do observado, `max(issued_at)` da previsão, com a diferença em dias para hoje.
4. Compose: montar o diretório.
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_dashboards_sql.py` | Todos passam |
| `python -m json.tool infra/grafana/dashboards/raw-data.json > /dev/null` | Código 0 |
| Compose local: `up -d --wait postgres grafana` e `docker compose ... exec grafana wget -qO- --user admin:<senha do .env.example> http://localhost:3000/api/dashboards/uid/raw-data` | JSON do painel |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: SQL de painel quebra em silêncio (painel vazio); executar cada consulta como `reader` pega erro de sintaxe, de coluna e de permissão.

## 8. Casos de teste

1. Todo JSON em `infra/grafana/dashboards/` é JSON válido e tem `uid` único.
2. Todo `target` usa o datasource `uid: ml`.
3. Todo `rawSql`, com macros substituídas, executa como `reader` sem erro.
4. Painéis `time_series` devolvem uma coluna `time` do tipo timestamp.
5. Com 2 dias de carga para os 4 subsistemas inseridos no arranjo, o painel de carga devolve 8 linhas.
6. Com 28 linhas de previsão de hoje, o painel de snapshots devolve `28` para hoje.

## 9. Riscos e perguntas em aberto

- A substituição de macros no teste é uma aproximação do Grafana; um erro só na macro passaria. O smoke manual do item 50 cobre.

## 10. Decisões que exigem ADR

Nenhuma.
