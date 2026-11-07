# 48 — Painel de dados brutos no Grafana (provisionado por arquivo)

> Executa: agente. Depende de: 47. Branch sugerida: `feat/painel-dados-brutos`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Provisionar um painel "Dados brutos" com a carga do ONS por subsistema, o clima observado por local e a saúde da coleta de previsões (linhas por `emitida_em`).
As consultas SQL são testadas contra o banco de teste com o usuário `leitura`.

## 2. Fora do escopo

- Previsões (PR 49). Erro real × previsto (PR 58).

## 3. Fase do roadmap

Fase 4 — "Grafana com dados brutos e previsões".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/grafana/provisioning/dashboards/plataforma.yaml` | Provider que carrega JSONs de `/etc/grafana/dashboards` |
| `infra/grafana/dashboards/dados-brutos.json` | O painel |
| `infra/docker-compose.yml` | Montar `./grafana/dashboards:/etc/grafana/dashboards:ro` |
| `tests/infra/test_paineis_sql.py` | Executa o SQL de cada painel (test-writer) |

Tabelas (já existem): `raw.ons_carga_diaria(subsistema, data, carga_mwmed, ingerido_em)`, `raw.clima_observado(local_id, data, temp_max, temp_min, precip_mm, vento_max, umidade_media, ingerido_em)`, `raw.clima_previsao(local_id, emitida_em, data_alvo, horizonte_dias, ..., ingerido_em)`, `ref.locais(local_id, nome, lat, lon, subsistema)`. Datasource `uid: ml` (PR 47).

## 5. Passos

1. (test-writer) `tests/infra/test_paineis_sql.py`, genérico para todo JSON em `infra/grafana/dashboards/`: extrai cada `targets[].rawSql`, troca as macros do Grafana por SQL comum (`$__timeFilter(col)` → `col >= now() - interval '30 days'`; `$__timeFrom()` → `now() - interval '30 days'`; `$__timeTo()` → `now()`; variáveis `$var` → valor de teste definido no próprio teste), e executa como `leitura` num banco migrado com algumas linhas inseridas pelo admin. Casos na seção 8. Confirme falha porque o JSON não existe. Commit `test: add grafana panel sql tests`.
2. (implementer) Provider `plataforma.yaml` (`apiVersion: 1`, `providers: [{name: plataforma, type: file, options: {path: /etc/grafana/dashboards}, allowUiUpdates: false}]`).
3. `dados-brutos.json` (uid `dados-brutos`), painéis, todos com datasource `uid: ml` e `format: time_series` ou `table`:
   - "Carga diária por subsistema (MWmed)": `select data::timestamp as time, subsistema as metric, carga_mwmed as value from raw.ons_carga_diaria where $__timeFilter(data::timestamp) order by 1`.
   - "Temperatura máxima observada por local": análogo com `raw.clima_observado`.
   - "Snapshots de previsão por dia (esperado: 4 × 7)": `select emitida_em::timestamp as time, count(*) as value from raw.clima_previsao where $__timeFilter(emitida_em::timestamp) group by 1 order by 1`.
   - "Última data por fonte" (tabela): `max(data)` do ONS, `max(data)` do observado, `max(emitida_em)` da previsão, com a diferença em dias para hoje.
4. Compose: montar o diretório.
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_paineis_sql.py` | Todos passam |
| `python -m json.tool infra/grafana/dashboards/dados-brutos.json > /dev/null` | Código 0 |
| Compose local: `up -d --wait postgres grafana` e `docker compose ... exec grafana wget -qO- --user admin:<senha do .env.example> http://localhost:3000/api/dashboards/uid/dados-brutos` | JSON do painel |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: SQL de painel quebra em silêncio (painel vazio); executar cada consulta como `leitura` pega erro de sintaxe, de coluna e de permissão.

## 8. Casos de teste

1. Todo JSON em `infra/grafana/dashboards/` é JSON válido e tem `uid` único.
2. Todo `target` usa o datasource `uid: ml`.
3. Todo `rawSql`, com macros substituídas, executa como `leitura` sem erro.
4. Painéis `time_series` devolvem uma coluna `time` do tipo timestamp.
5. Com 2 dias de carga para os 4 subsistemas inseridos no arranjo, o painel de carga devolve 8 linhas.
6. Com 28 linhas de previsão de hoje, o painel de snapshots devolve `28` para hoje.

## 9. Riscos e perguntas em aberto

- A substituição de macros no teste é uma aproximação do Grafana; um erro só na macro passaria. O smoke manual do item 50 cobre.

## 10. Decisões que exigem ADR

Nenhuma.
