# 58 — Painel "Erro real × previsto" no Grafana

> Executa: agente. Depende de: 49, 51. Branch sugerida: `feat/painel-erro`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Provisionar o painel "Erro dos modelos": métricas diárias de `monitoring.metricas` por modelo, com médias móveis de 7 e 30 dias, e a versão do modelo ao longo do tempo.
É o critério de pronto da Fase 5 ("o painel mostra erro real × previsto atualizando sozinho").

## 2. Fora do escopo

- Painéis próprios da cientista (ela monta os dela; guia: "MAPE móvel de 7 e 30 dias").
- Alertas por limite de erro (regra de retreino é dela).

## 3. Fase do roadmap

Fase 5 — "Pronto quando: o painel mostra erro real × previsto atualizando sozinho".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/grafana/dashboards/erro-modelos.json` | O painel (uid `erro-modelos`) |
| `tests/infra/test_paineis_sql.py` | Casos deste painel (test-writer) |

Tabela: `monitoring.metricas(modelo, versao_modelo, data, metrica, valor)`, chave (`modelo`, `data`, `metrica`). O teste genérico do PR 48 já executa todo SQL de painel como `leitura`.

## 5. Passos

1. (test-writer) Casos da seção 8; variáveis `$modelo = 'teste'` e `$metrica = 'mape'`. Confirme falha porque o JSON não existe. Commit `test: add model error panel tests`.
2. (implementer) `erro-modelos.json`:
   - Variáveis `modelo` (`select distinct modelo from monitoring.metricas`) e `metrica` (`select distinct metrica from monitoring.metricas where modelo = '$modelo'`).
   - "Métrica diária e médias móveis": `valor` por `data`, mais `avg(valor) over (order by data rows between 6 preceding and current row)` e o mesmo com 29.
   - "Versão em produção por dia": `versao_modelo` por `data` (tabela ou state timeline).
   - "Previsto × real" do PR 49 referenciado por link (não duplicar).
3. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_paineis_sql.py` | Todos passam |
| `python -m json.tool infra/grafana/dashboards/erro-modelos.json > /dev/null` | Código 0 |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a janela das médias móveis é lógica de consulta e precisa de prova com valores conhecidos.

## 8. Casos de teste

1. 10 dias de `mape` = 1, 2, …, 10 para `teste` → no 10º dia, a média de 7 dias é 7.0 (média de 4..10) e a de 30 dias é 5.5.
2. Métrica de outro modelo não aparece com `$modelo = 'teste'`.
3. Troca de `versao_modelo` no 6º dia → o painel de versão mostra as duas versões nos dias certos.
4. Sem linhas → consultas executam sem erro e devolvem vazio.

## 9. Riscos e perguntas em aberto

- Média móvel por linhas (`rows between`) assume um registro por dia; dias sem métrica (real atrasado) encurtam a janela em dias corridos. Alternativa por intervalo de datas (`range between interval`). Aceitável para começar; anotar no painel.

## 10. Decisões que exigem ADR

Nenhuma.
