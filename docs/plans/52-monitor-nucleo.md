# 52 — Núcleo do monitoramento: juntar previsto com real, chamar `evaluate`, gravar métricas

> Executa: agente. Depende de: 51. Branch sugerida: `feat/monitor-nucleo`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar `avaliar_dia`, que para um modelo e uma data-alvo pega o último lote de previsões, obtém o real por uma função injetada, chama `evaluate(previsto, real)` do módulo dela e grava o dicionário em `monitoring.metricas`.
A origem do real fica fora deste PR (injeção), porque depende de uma decisão de contrato (PR 53).

## 2. Fora do escopo

- De onde vem o real (PR 53, com ADR). Flow e agenda (PR 54).

## 3. Fase do roadmap

Fase 5 — "Job de monitoramento + `monitoring.metricas`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/monitor.py` | `RealIndisponivel`, `MetricasInvalidas`, `ultimo_lote(conn, nome, data_alvo)`, `avaliar_dia(...)` |
| `tests/test_monitor_nucleo.py` | Testes com módulo falso e `obter_real` falso (test-writer) |

Contrato (`docs/plataforma-ml.md`):

```python
def evaluate(previsto: pd.DataFrame, real: pd.DataFrame) -> dict[str, float]: ...
    # ex.: {"mape": 3.1, "mae": 1520.0}
```

"O job de monitoramento cruza previsões com o real e grava o retorno de `evaluate` em `monitoring.metricas`." Horário: 08:00, "Junta previsões antigas com o real que chegou e grava métricas".

Tabelas: `predictions.previsoes(modelo, versao_modelo, chave, data_alvo, valor_previsto, gerado_em)`; `monitoring.metricas(modelo, versao_modelo, data, metrica, valor)`. Código existente: `ingestion/db.py` (`upsert`).

## 5. Passos

1. (test-writer) Testes da seção 8 com `banco_migrado`, previsões inseridas pelo admin no arranjo e um módulo falso cujo `evaluate` registra os argumentos. Confirme falha por `ModuleNotFoundError: flows.monitor`. Commit `test: add monitor core tests`.
2. (implementer) `flows/monitor.py`:
   - `ultimo_lote(conn, nome, data_alvo) -> pd.DataFrame` com colunas `chave, data_alvo, valor_previsto` e o `versao_modelo` do lote: as linhas do maior `gerado_em` entre as previsões daquele modelo e `data_alvo`. Sem previsão → DataFrame vazio.
   - `avaliar_dia(conn, *, nome, modulo, data_alvo, obter_real: Callable[[Connection, date], pd.DataFrame]) -> dict[str, float] | None`:
     1. `previsto = ultimo_lote(...)`; vazio → devolve `None` (nada a avaliar; não é erro).
     2. `real = obter_real(conn, data_alvo)` (colunas `chave, data_alvo, valor_real`); vazio → `RealIndisponivel` (o flow trata como "ainda não chegou").
     3. Chama `modulo.evaluate(previsto, real)`; exceção sobe sem embrulho.
     4. Valida: `dict` não vazio, chaves no padrão `^[a-z][a-z0-9_]*$`, valores `float` finitos; senão `MetricasInvalidas`.
     5. `upsert(conn, "monitoring.metricas", ..., chaves=["modelo","data","metrica"], ao_conflitar="atualizar", carimbar_ingerido_em=False)` com `versao_modelo` do lote.
     6. Devolve o dicionário.
3. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_monitor_nucleo.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: "último lote vence", real atrasado e métrica inválida são as regras que tornam o painel de erro confiável.

## 8. Casos de teste

1. Dois lotes para (`m`, D) e real de D → `evaluate` recebe só as linhas do lote mais recente; métricas gravadas com o `versao_modelo` desse lote.
2. `evaluate` devolve `{"mape": 3.1, "mae": 1520.0}` → duas linhas em `monitoring.metricas` para (`m`, D).
3. Rodar de novo com real revisado e `evaluate` devolvendo `{"mape": 2.9, "mae": 1400.0}` → as mesmas duas linhas, com valores novos.
4. Sem previsão para D → devolve `None`; `evaluate` não chamado; nada gravado.
5. Real vazio → `RealIndisponivel`; nada gravado.
6. `evaluate` devolve `{"MAPE": 3.1}` → `MetricasInvalidas`.
7. `evaluate` devolve `{"mape": float("nan")}` → `MetricasInvalidas`.
8. `evaluate` levanta `ValueError("x")` → a mesma exceção sobe.

## 9. Riscos e perguntas em aberto

- Formato do `real` (`chave, data_alvo, valor_real`) é proposta deste plano e entra no ADR "Fonte do real" (PR 53).

## 10. Decisões que exigem ADR

Depende do ADR "Fonte do real" (PR 53) para o formato do `real`.
