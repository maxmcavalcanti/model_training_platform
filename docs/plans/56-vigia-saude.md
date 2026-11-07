# 56 — Vigia de saúde: disco acima de 80% e serviço fora do ar

> Executa: agente. Depende de: 55. Branch sugerida: `feat/health-watchdog`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar um flow `watch_health`, a cada 15 minutos, que checa uso de disco da VPS e a saúde de `health`, MLflow, Prefect, Grafana e Postgres, e manda alerta no Telegram quando algo passa do limite.
Avisa uma vez por problema (não a cada 15 minutos) e avisa quando volta ao normal.

## 2. Fora do escopo

- Falha de flow (PR 55). Backups (PR 57).
- Monitorar a própria VPS por fora (ver riscos).

## 3. Fase do roadmap

Fase 5 — "Alertas no Telegram".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/watchdog.py` | `check_disk(path, threshold)`, `check_services(client, targets)`, `@flow watch_health` |
| `flows/deployments.py` | `watch_health` com `*/15 * * * *` |
| `infra/docker-compose.yml` | Montar o disco do host somente leitura no worker (ex.: `/:/host:ro`) para medir uso |
| `tests/test_watchdog.py`, `tests/test_deployments.py` | Testes (test-writer) |

Do doc: "Alertas: … disco acima de 80%, serviço fora do ar → Telegram".

Código existente: `flows/alerts.py` (`send_telegram`, `notify_failure`), `flows/deployments.py`.

Alvos de saúde (rede interna do compose): `http://mlflow:5000/health` (corpo `OK`), `http://prefect-server:4200/api/health` (`true`), `http://grafana:3000/api/health` (`"database": "ok"`), `http://health:8080/health` (`ok`), Postgres com `SELECT 1` usando `DATABASE_URL`.

## 5. Passos

1. (test-writer) Testes da seção 8 com `httpx.MockTransport`, `shutil.disk_usage` falso via `monkeypatch` e `send_telegram` falso. Confirme falha. Commit `test: add health watcher tests`.
2. (implementer) `flows/watchdog.py`:
   - `check_disk(path="/host", threshold=0.80) -> Problema | None`.
   - `check_services(client, targets) -> list[Problema]` com timeout de 5 s por alvo.
   - Estado entre execuções: um `Variable` do Prefect (`prefect.variables.Variable`) com o conjunto de problemas abertos. Problema novo → alerta "ALERTA"; problema que sumiu → alerta "RESOLVIDO"; problema que continua → nada.
   - O flow termina `Completed` mesmo com problemas (o alerta já foi enviado; `Failed` dispararia `notify_failure` e duplicaria a mensagem). Não use `on_failure` neste flow além do padrão.
3. Deployment `*/15 * * * *` e montagem do disco.
4. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_watchdog.py tests/test_deployments.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a deduplicação de alertas (abrir, manter, resolver) é lógica com estado e fácil de errar.

## 8. Casos de teste

1. Disco em 85% e nenhum problema aberto → um alerta com `disk` e `85%`.
2. Execução seguinte, ainda 85% → nenhum alerta novo.
3. Execução seguinte, 60% → um alerta `RESOLVIDO` de disco.
4. MLflow respondendo 502 → alerta citando `mlflow`; Prefect, Grafana e `health` saudáveis não geram alerta.
5. Alvo que estoura o timeout → tratado como fora do ar.
6. Postgres recusando conexão → alerta citando `postgres`.
7. Tudo saudável → nenhum alerta; flow `Completed`.
8. Deployment `watch_health` com `*/15 * * * *`.

## 9. Riscos e perguntas em aberto

- Se o Prefect (server ou worker) cair, o vigia não roda e ninguém é avisado. Com rede só Tailscale, um monitor externo não alcança a VPS; a opção compatível é um heartbeat de saída: o vigia faz um `GET` numa URL de um serviço tipo healthchecks.io a cada execução, e o serviço avisa quando o ping para de chegar. Decisão do usuário (P17); se aprovada, a URL do ping é segredo e vai no `.env`.
- Memória: o vigia também pode checar `MemAvailable` de `/proc/meminfo` do host contra os gatilhos do 28b. Fora deste PR; perguntar.
- Montar `/` do host no worker, mesmo somente leitura, expõe arquivos do host ao container. Alternativa: montar só a partição de dados do Docker. Confirmar.

## 10. Decisões que exigem ADR

Nenhuma.
