# 49 — Painel de previsões no Grafana

> Executa: agente. Depende de: 48. Branch sugerida: `feat/painel-previsoes`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Provisionar o painel "Previsões": último lote de previsões por modelo e chave, e previsto × real para modelos de carga (chave = subsistema).
Usa o teste genérico de SQL de painel criado no PR 48.

## 2. Fora do escopo

- Métricas de erro (MAPE etc.) e painel de erro (Fase 5, PR 58).
- Real do `chuva_d1` (depende do ADR "Fonte do real" (PR 53)).

## 3. Fase do roadmap

Fase 4 — "Grafana com dados brutos e previsões".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/grafana/dashboards/previsoes.json` | O painel |
| `tests/infra/test_paineis_sql.py` | Casos específicos deste painel (test-writer) |

Tabelas: `predictions.previsoes(modelo, versao_modelo, chave, data_alvo, valor_previsto, gerado_em)` (PK com `gerado_em`; reexecuções criam lotes), `raw.ons_carga_diaria(subsistema, data, carga_mwmed, ...)`.

## 5. Passos

1. (test-writer) Acrescente os casos da seção 8 (o teste genérico do PR 48 já executa o SQL do JSON novo). Para a variável `$modelo`, use `'teste'` no teste. Confirme falha porque o JSON não existe. Commit `test: add predictions panel tests`.
2. (implementer) `previsoes.json` (uid `previsoes`):
   - Variável `modelo` (query: `select distinct modelo from predictions.previsoes order by 1`).
   - "Último lote por data-alvo": para cada (`modelo`, `chave`, `data_alvo`), a linha de maior `gerado_em` (`distinct on (chave, data_alvo) ... order by chave, data_alvo, gerado_em desc`), filtrada por `modelo = '$modelo'`, como série temporal por `chave`.
   - "Previsto × real (carga)": junta o último lote com `raw.ons_carga_diaria` em `chave = subsistema and data_alvo = data`; duas séries por subsistema (`previsto`, `real`).
   - "Execuções do score": `select gerado_em as time, modelo, count(*) from predictions.previsoes where $__timeFilter(gerado_em) group by 1, 2`.
3. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_paineis_sql.py` | Todos passam |
| `python -m json.tool infra/grafana/dashboards/previsoes.json > /dev/null` | Código 0 |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a regra "último lote vence" é lógica de consulta e precisa de prova com dois lotes.

## 8. Casos de teste

1. Dois lotes do modelo `teste` para (`SE`, D+1) com valores 100 e 200 e `gerado_em` crescente → o painel "Último lote" devolve só 200.
2. Previsão de `SE` para D e carga real de `SE` em D → "Previsto × real" devolve as duas séries para D.
3. Previsão para D+1 sem real ainda → aparece só a série `previsto`, sem erro.
4. Previsões de outro modelo não aparecem com `$modelo = 'teste'`.

## 9. Riscos e perguntas em aberto

- O painel "Previsto × real" assume que a chave é subsistema e o real é a carga; para modelos de outro tipo ele fica vazio. Generalizar depende do ADR "Fonte do real" (PR 53).

## 10. Decisões que exigem ADR

Nenhuma.
