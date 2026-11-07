# 49 — Painel de previsões no Grafana

> Executa: agente. Depende de: 48. Branch sugerida: `feat/dashboard-predictions`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Provisionar o painel "Previsões": último lote de previsões por modelo e chave, e previsto × real para modelos de carga (chave = subsistema).
Usa o teste genérico de SQL de painel criado no PR 48.

## 2. Fora do escopo

- Métricas de erro (MAPE etc.) e painel de erro (Fase 5, PR 58).
- Real do `rain_d1` (depende do ADR "Fonte do real" (PR 53)).

## 3. Fase do roadmap

Fase 4 — "Grafana com dados brutos e previsões".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/grafana/dashboards/predictions.json` | O painel |
| `tests/infra/test_dashboards_sql.py` | Casos específicos deste painel (test-writer) |

Tabelas: `predictions.model_predictions(model_name, model_version, key, target_date, predicted_value, generated_at)` (PK com `generated_at`; reexecuções criam lotes), `raw.ons_daily_load(subsystem, date, load_avg_mw, ...)`.

## 5. Passos

1. (test-writer) Acrescente os casos da seção 8 (o teste genérico do PR 48 já executa o SQL do JSON novo). Para a variável `$model_name`, use `'test'` no teste. Confirme falha porque o JSON não existe. Commit `test: add predictions panel tests`.
2. (implementer) `predictions.json` (uid `predictions`):
   - Variável `model_name` (query: `select distinct model_name from predictions.model_predictions order by 1`).
   - "Último lote por data-alvo": para cada (`model_name`, `key`, `target_date`), a linha de maior `generated_at` (`distinct on (key, target_date) ... order by key, target_date, generated_at desc`), filtrada por `model_name = '$model_name'`, como série temporal por `key`.
   - "Previsto × real (carga)": junta o último lote com `raw.ons_daily_load` em `key = subsystem and target_date = date`; duas séries por subsistema (`predicted`, `actual`).
   - "Execuções do score": `select generated_at as time, model_name, count(*) from predictions.model_predictions where $__timeFilter(generated_at) group by 1, 2`.
3. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_dashboards_sql.py` | Todos passam |
| `python -m json.tool infra/grafana/dashboards/predictions.json > /dev/null` | Código 0 |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a regra "último lote vence" é lógica de consulta e precisa de prova com dois lotes.

## 8. Casos de teste

1. Dois lotes do modelo `test` para (`SE`, D+1) com valores 100 e 200 e `generated_at` crescente → o painel "Último lote" devolve só 200.
2. Previsão de `SE` para D e carga real de `SE` em D → "Previsto × real" devolve as duas séries para D.
3. Previsão para D+1 sem real ainda → aparece só a série `predicted`, sem erro.
4. Previsões de outro modelo não aparecem com `$model_name = 'test'`.

## 9. Riscos e perguntas em aberto

- O painel "Previsto × real" assume que a chave é subsistema e o real é a carga; para modelos de outro tipo ele fica vazio. Generalizar depende do ADR "Fonte do real" (PR 53).

## 10. Decisões que exigem ADR

Nenhuma.
