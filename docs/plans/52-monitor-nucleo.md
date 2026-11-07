# 52 — Núcleo do monitoramento: juntar previsto com real, chamar `evaluate`, gravar métricas

> Executa: agente. Depende de: 51. Branch sugerida: `feat/monitor-core`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar `evaluate_day`, que para um modelo e uma data-alvo pega o último lote de previsões, obtém o real por uma função injetada, chama `evaluate(predicted, actual)` do módulo dela e grava o dicionário em `monitoring.model_metrics`.
A origem do real fica fora deste PR (injeção), porque depende de uma decisão de contrato (PR 53).

## 2. Fora do escopo

- De onde vem o real (PR 53, com ADR). Flow e agenda (PR 54).

## 3. Fase do roadmap

Fase 5 — "Job de monitoramento + `monitoring.model_metrics`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/monitor.py` | `ActualsUnavailable`, `InvalidMetrics`, `latest_batch(conn, name, target_date)`, `evaluate_day(...)` |
| `tests/test_monitor_core.py` | Testes com módulo falso e `get_actuals` falso (test-writer) |

Contrato (`docs/plataforma-ml.md`):

```python
def evaluate(previsto: pd.DataFrame, real: pd.DataFrame) -> dict[str, float]: ...
    # ex.: {"mape": 3.1, "mae": 1520.0}
```

"O job de monitoramento cruza previsões com o real e grava o retorno de `evaluate` em `monitoring.model_metrics`." Horário: 08:00, "Junta previsões antigas com o real que chegou e grava métricas".

Tabelas: `predictions.model_predictions(model_name, model_version, key, target_date, predicted_value, generated_at)`; `monitoring.model_metrics(model_name, model_version, date, metric, value)`. Código existente: `ingestion/db.py` (`upsert`).

## 5. Passos

1. (test-writer) Testes da seção 8 com `migrated_database`, previsões inseridas pelo admin no arranjo e um módulo falso cujo `evaluate` registra os argumentos. Confirme falha por `ModuleNotFoundError: flows.monitor`. Commit `test: add monitor core tests`.
2. (implementer) `flows/monitor.py`:
   - `latest_batch(conn, name, target_date) -> pd.DataFrame` com colunas `key, target_date, predicted_value` e o `model_version` do lote: as linhas do maior `generated_at` entre as previsões daquele modelo e `target_date`. Sem previsão → DataFrame vazio.
   - `evaluate_day(conn, *, name, module, target_date, get_actuals: Callable[[Connection, date], pd.DataFrame]) -> dict[str, float] | None`:
     1. `predicted = latest_batch(...)`; vazio → devolve `None` (nada a avaliar; não é erro).
     2. `actual = get_actuals(conn, target_date)` (colunas `key, target_date, actual_value`); vazio → `ActualsUnavailable` (o flow trata como "ainda não chegou").
     3. Chama `module.evaluate(predicted, actual)`; exceção sobe sem embrulho.
     4. Valida: `dict` não vazio, chaves no padrão `^[a-z][a-z0-9_]*$`, valores `float` finitos; senão `InvalidMetrics`.
     5. `upsert(conn, "monitoring.model_metrics", ..., keys=["model_name","date","metric"], on_conflict="update", stamp_ingested_at=False)` com `model_version` do lote.
     6. Devolve o dicionário.
3. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_monitor_core.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: "último lote vence", real atrasado e métrica inválida são as regras que tornam o painel de erro confiável.

## 8. Casos de teste

1. Dois lotes para (`m`, D) e real de D → `evaluate` recebe só as linhas do lote mais recente; métricas gravadas com o `model_version` desse lote.
2. `evaluate` devolve `{"mape": 3.1, "mae": 1520.0}` → duas linhas em `monitoring.model_metrics` para (`m`, D).
3. Rodar de novo com real revisado e `evaluate` devolvendo `{"mape": 2.9, "mae": 1400.0}` → as mesmas duas linhas, com valores novos.
4. Sem previsão para D → devolve `None`; `evaluate` não chamado; nada gravado.
5. Real vazio → `ActualsUnavailable`; nada gravado.
6. `evaluate` devolve `{"MAPE": 3.1}` → `InvalidMetrics`.
7. `evaluate` devolve `{"mape": float("nan")}` → `InvalidMetrics`.
8. `evaluate` levanta `ValueError("x")` → a mesma exceção sobe.

## 9. Riscos e perguntas em aberto

- Formato do `actual` (`key, target_date, actual_value`) é proposta deste plano e entra no ADR "Fonte do real" (PR 53).

## 10. Decisões que exigem ADR

Depende do ADR "Fonte do real" (PR 53) para o formato do `actual`.
