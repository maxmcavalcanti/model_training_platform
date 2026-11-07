# 54 — Flow `monitorar_modelos` e deployment às 08:00

> Executa: agente. Depende de: 53, 46. Branch sugerida: `feat/flow-monitor`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar o flow diário que, para cada modelo com `champion`, roda `flows.monitor_um` no ambiente isolado da versão do pacote do champion, e agendá-lo às 08:00 BRT.
Mesmo padrão do `score_modelos`: falha de um modelo não impede os outros.

## 2. Fora do escopo

- Alertas (PR 55). Painel (PR 58).

## 3. Fase do roadmap

Fase 5 — "Job de monitoramento + `monitoring.metricas`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/monitor_flow.py` | `@flow(name="monitorar_modelos")` e `@task avaliar_modelo` |
| `flows/deployments.py` | Entrada `monitorar_modelos` com `0 8 * * *` |
| `tests/test_flow_monitor.py`, `tests/test_deployments.py` | Testes (test-writer) |

Do doc: "08:00 `monitorar_modelos` — Junta previsões antigas com o real que chegou e grava métricas".

Código existente: `flows/score_flow.py` (padrão a seguir: listar champions, uma task por modelo, falha agregada no fim), `flows/registro.py`, `flows/executor.py`, `flows/deployments.py`. Se o padrão de "uma task por champion com falha agregada" estiver duplicado entre `score_flow.py` e o novo arquivo, extraia uma função comum (refatoração com a suíte verde; os testes do PR 46 não mudam).

## 5. Passos

1. (test-writer) Testes da seção 8 com `prefect_test_harness` e `monkeypatch` de `listar_champions` e `executar`. Em `tests/test_deployments.py`: `monitorar_modelos` com `0 8 * * *`. Confirme falha. Commit `test: add monitor flow tests`.
2. (implementer) `monitorar_modelos(hoje: date | None = None, dias: int = 14)`: para cada champion com `pacote_versao`, `executar(montar_comando(pacote_versao, "flows.monitor_um", ["--modelo", nome, "--hoje", hoje.isoformat(), "--dias", str(dias)]))`.
3. Deployment às `0 8 * * *`.
4. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_flow_monitor.py tests/test_deployments.py tests/test_flow_score.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: mesma justificativa do flow de score.

## 8. Casos de teste

1. Dois champions → dois comandos `flows.monitor_um` com a versão de cada um; `Completed`.
2. Um falha → os dois rodam; `Failed` citando o que falhou.
3. Nenhum champion → `Completed` sem chamadas.
4. `hoje` padrão = data atual em `America/Sao_Paulo`; `dias` padrão 14.
5. Deployment `monitorar_modelos` com `0 8 * * *`, fuso e pool corretos.

## 9. Riscos e perguntas em aberto

- Nenhum novo.

## 10. Decisões que exigem ADR

Nenhuma além do ADR "Fonte do real".
