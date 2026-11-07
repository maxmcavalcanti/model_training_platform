# 55 — Alerta no Telegram quando um flow falha

> Executa: agente. Depende de: 54 (todos os flows existem). Branch sugerida: `feat/telegram-alerts`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Enviar uma mensagem no Telegram sempre que um flow da plataforma terminar `Failed` ou `Crashed`, com nome do flow, motivo e link para a execução no Prefect.
Fecha a regra "Falha de checagem = execução falha no Prefect = alerta no Telegram".

## 2. Fora do escopo

- Disco cheio e serviço fora do ar (PR 56). Criar o bot (item 59).

## 3. Fase do roadmap

Fase 5 — "Alertas no Telegram, backups com restore testado".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/alerts.py` | `send_telegram(texto, *, cliente=None) -> bool` e hook `notify_failure(flow, flow_run, state)` |
| `flows/ingest.py`, `flows/score_flow.py`, `flows/monitor_flow.py` | `on_failure=[notify_failure]` e `on_crashed=[notify_failure]` em todos os `@flow` |
| `infra/docker-compose.yml` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `PREFECT_UI_URL=https://${TS_HOSTNAME}:4200` (o link da mensagem só abre para quem está na tailnet) no `prefect-worker` |
| `infra/.env.example` | As duas variáveis do Telegram (vazias) |
| `tests/test_alerts.py` | Testes (test-writer) |

Do doc: "Alertas: falha de flow no Prefect, disco acima de 80%, serviço fora do ar → Telegram". "Falha de checagem = execução falha no Prefect = alerta no Telegram".

API do Telegram: `POST https://api.telegram.org/bot<token>/sendMessage` com JSON `{"chat_id": ..., "text": ...}`.

## 5. Passos

1. (test-writer) Testes da seção 8 com `httpx.MockTransport` e `prefect_test_harness` (um flow de teste com `on_failure=[notify_failure]` que levanta erro). Confirme falha por `ModuleNotFoundError: flows.alertas`. Commit `test: add telegram alert tests`.
2. (implementer) `flows/alerts.py`:
   - `send_telegram(texto, *, cliente=None) -> bool`: sem `TELEGRAM_BOT_TOKEN` ou `TELEGRAM_CHAT_ID` → log de aviso e `False` (não levanta: alerta ausente não pode mascarar o erro original). Não usa o retry de `ingestion.http`: o envio tem no máximo 1 tentativa extra e timeout de 10 s, para não atrasar o término do flow. Erro de envio → log e `False`. Sucesso → `True`.
   - O token nunca aparece em log nem em exceção (substituir por `***`).
   - Texto limitado a 4000 caracteres (limite do Telegram é 4096).
   - `notify_failure(flow, flow_run, state)`: monta `"[plataforma] <flow.name> <state.name>: <state.message>\n<PREFECT_UI_URL>/runs/flow-run/<flow_run.id>"` e chama `send_telegram`. Qualquer exceção dentro do hook é capturada e registrada.
3. Acrescente os hooks a todos os flows e as variáveis ao compose.
4. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_alerts.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| Com `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` reais exportados (manual): `uv run python -c "from flows.alertas import send_telegram; print(send_telegram('teste'))"` | `True` e a mensagem chega |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o alerta é o que transforma falha silenciosa em ação; precisa provar que dispara, que não vaza o token e que não mascara o erro.

## 8. Casos de teste

1. Com token e chat: `send_telegram("oi")` faz um `POST` para `/bot<token>/sendMessage` com `chat_id` e `text="oi"`; devolve `True`.
2. Sem token → nenhuma requisição; `False`; log de aviso.
3. Telegram responde 500 duas vezes → `False`, sem exceção.
4. Texto de 5000 caracteres → enviado com no máximo 4000.
5. Erro do Telegram cuja mensagem contém o token → o log não contém o token.
6. Flow de teste com `on_failure=[notify_failure]` que levanta `CheckFailed("faltou dia")` → estado `Failed` e uma mensagem enviada contendo o nome do flow e `faltou dia`.
7. Mesmo flow, com o Telegram fora → o estado final continua `Failed` com a mensagem original (o hook não troca o erro).
8. Todos os flows de `flows/ingest.py`, `flows/score_flow.py` e `flows/monitor_flow.py` têm `notify_failure` em `on_failure` e `on_crashed` (inspecionar os objetos `Flow`).

## 9. Riscos e perguntas em aberto

- Se o worker inteiro cair, nenhum flow roda e nenhum hook dispara. Isso é coberto pelo PR 56 (serviço fora do ar), mas não se o Prefect estiver fora; ver risco lá.

## 10. Decisões que exigem ADR

Nenhuma.
