# 33 — Deployments do Prefect com as agendas do doc

> Executa: agente. Depende de: 32. Branch sugerida: `feat/prefect-deployments`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Declarar em código os deployments dos três flows de ingestão, com agenda cron no fuso `America/Sao_Paulo` e o work pool `plataforma`, e um comando para registrá-los no servidor.
O registro é idempotente: rodar de novo atualiza, não duplica.

## 2. Fora do escopo

- Worker (PR 34). Registrar na VPS (item 35). Chamar o registro no deploy automático (PR 39).
- Deployments de score e monitoramento (PRs 46 e 54 acrescentam entradas aqui).

## 3. Fase do roadmap

Fase 3 — "Ingestões migradas para flows do Prefect".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/deployments.py` | `DEPLOYMENTS` (lista declarativa) e `registrar()`; `python -m flows.deployments` registra todos |
| `tests/test_deployments.py` | Testes (test-writer) |
| `AGENTS.md` | Comando para registrar deployments |

Agenda (`docs/plataforma-ml.md`, "Ingestão", BRT): 06:30 `ingest_clima_previsao`, 06:45 `ingest_clima_observado`, 07:00 `ingest_ons_carga`. Use os horários que estiverem em `infra/cron/crontab` (podem ter sido ajustados pelo item 18); os dois têm de bater até o PR 36.

## 5. Passos

1. (test-writer) Testes da seção 8: importam `DEPLOYMENTS` e inspecionam a declaração; o teste de registro usa `prefect_test_harness` e consulta o servidor de teste com `get_client()`. Confirme falha por `ModuleNotFoundError: flows.deployments`. Commit `test: add deployment definition tests`.
2. (implementer) `flows/deployments.py`:
   - `POOL = "plataforma"`, `FUSO = "America/Sao_Paulo"`.
   - `DEPLOYMENTS`: lista de registros (nome do deployment, flow, cron). Nome do deployment = nome do flow + `/producao` (ex.: `ingest_clima_previsao/producao`).
   - `registrar()`: garante que o work pool `POOL` existe (tipo `process`), e para cada item usa `flow.to_deployment(name="producao", cron=..., timezone=FUSO, work_pool_name=POOL)` e `prefect.deploy(..., build=False, push=False)` ou a API equivalente da versão instalada, sem imagem (o worker roda no container que já tem o código, PR 34).
   - `if __name__ == "__main__": registrar()`.
3. `AGENTS.md`, Comandos: "Registrar deployments do Prefect: `PREFECT_API_URL=<url> uv run python -m flows.deployments`".
4. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_deployments.py` | Todos passam |
| Com o compose de produção local (`postgres`, `prefect-server`) e `PREFECT_API_URL` apontando para ele: `uv run python -m flows.deployments` | Termina sem erro |
| Em seguida, `uv run prefect deployment ls` | Os três deployments `.../producao` |
| Rodar o registro de novo e listar | Continuam três |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: horário e fuso errados fazem o job rodar na hora errada sem nenhum erro visível; o teste compara com o crontab vigente.

## 8. Casos de teste

1. `DEPLOYMENTS` tem exatamente os flows `ingest_clima_previsao`, `ingest_clima_observado`, `ingest_ons_carga`.
2. Para cada um, o cron é igual ao da linha correspondente em `infra/cron/crontab` (enquanto o arquivo existir).
3. Todos usam `timezone = "America/Sao_Paulo"` e `work_pool_name = "plataforma"`.
4. (servidor de teste) Depois de `registrar()`, o servidor tem os três deployments com as agendas certas e o pool `plataforma`.
5. (servidor de teste) `registrar()` duas vezes → continuam três deployments, sem agenda duplicada.

## 9. Riscos e perguntas em aberto

- Durante a transição (itens 35 e PR 36), supercronic e Prefect podem rodar o mesmo job no mesmo dia. É seguro porque os jobs são idempotentes e a previsão usa `ignorar` no conflito.
- A API de deploy do Prefect 3 mudou entre minors; siga a documentação da versão fixada, mantendo o comportamento dos testes.

## 10. Decisões que exigem ADR

Nenhuma.
