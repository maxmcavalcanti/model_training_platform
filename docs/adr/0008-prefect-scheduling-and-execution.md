# ADR-0008: Agendamento e execução pelo Prefect

**Status:** Aceito **Data:** 2026-11-09

## Contexto

- O ADR 0004 mantém o supercronic como agendador interino e prevê a troca pelo Prefect na Fase 3.
- A API do Prefect não tem autenticação por padrão. Um worker `process` com a credencial do `ingestor` deixaria qualquer nó do tailnet com acesso à porta 4200 executar comando como o `ingestor`.
- A VPS tem 1 GB de RAM; o orçamento de memória da Fase 3 (Postgres, MLflow, Prefect server e worker) não cabe nela.
- Este ADR foi escrito pela skill `generate-adr` a pedido do usuário (2026-11-09).

## Decisão

1. **Prefect 3 server** no compose, só no tailnet (`tailscale serve`), com imagem `X.Y.Z-python3.12@sha256` (a última estável com pelo menos 7 dias, alinhada ao `prefect` do `uv.lock`), banco `prefect` próprio e papel `prefect` com limite de conexões.
2. **API autenticada.** `PREFECT_SERVER_API_AUTH_STRING` no server e `PREFECT_API_AUTH_STRING` no worker, nos jobs e no CI, ambas derivadas de `PREFECT_API_AUTH` no `.env`, nunca literais no compose. `/api/health` e `/api/ready` são isentos.
3. **Flows de ingestão** reaproveitam a lógica da CLI por `ingestion/runs.py`. Qualquer exceção do job (`CheckFailed`, `PartialIngestionError` e outras) falha o flow, sem retry; o logger `ingestion` é fixado em INFO para os logs dos jobs chegarem ao Prefect.
4. **Deployments em código** (`flows/deployments.py`, entrypoint `MODULE_PATH`), com agendas às 06:30, 06:45 e 07:00 em `America/Sao_Paulo`, via `Cron` com timezone.
5. **Pool `platform` do tipo `process`, limite 1.** O worker tem `mem_limit: 768m` e recebe só o `DATABASE_URL` do `ingestor` (nunca o admin). Não tem `docker.sock`, volumes nem portas.
6. **Cutover do supercronic** idempotente: nenhum dia é ingerido duas vezes nem fica sem agenda. O `scheduler` sai no PR 36, e as regras do crontab migram para testes.
7. **Memória.** O upgrade da VPS para 2 GB (item 28b) é o caminho padrão antes do item 35, dispensável só com uma medição que mostre folga.
8. O status do ADR 0004 muda em PR só de `docs/**`, junto com o do ADR 0007.

## Consequências

**Positivo:**

- Uma única fonte de horários, com UI e histórico de execuções, e base para a Fase 4.
- Privilégio mínimo no worker e API autenticada.
- Falha de check falha o flow, como exige a regra do projeto.

**Negativo:**

- Mais memória e mais uma peça a operar (servidor, banco, worker).
- O segredo da API precisa de rotação manual, e a UI não tem autenticação individual.
- Runs atrasados executam em fila depois de uma queda longa; é inofensivo por idempotência.
- A versão do `prefect` no `uv.lock` e a imagem do server precisam andar juntas (guardadas por teste).

## Alternativas consideradas

**Pool `docker`:** um container por execução. Rejeitado porque exige montar o `docker.sock` (equivale a root no host), precisa de imagem no registro e não economiza RAM.

**Manter o supercronic:** já funciona. Rejeitado porque não dá observabilidade nem base para a Fase 4 e a orquestração de modelos.

**API do Prefect sem autenticação, protegida só pela ACL do tailnet:** menos configuração. Rejeitado porque qualquer nó com acesso à porta executaria comando no worker.
