# 29 — MLflow no compose, acessível só pela tailnet

> Executa: agente. Depende de: 03, 10, 28 e do checkpoint de memória 28a feito (o upgrade 28b só se um gatilho tiver disparado). Branch sugerida: `feat/compose-mlflow`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Subir o MLflow (tracking + model registry) com backend no banco `mlflow` e artefatos num volume local servidos pelo próprio MLflow, publicado só em `127.0.0.1:5000` e exposto na tailnet por `tailscale serve` (`https://<host>.ts.net:5000`).
É o que libera a cientista para registrar experimentos e modelos.

## 2. Fora do escopo

- Prefect (PR 30). MinIO (o doc diz "MinIO só se crescer").
- Backup do volume de artefatos (PR 57).
- Uso do MLflow pelo job de score (PR 43).
- ACL do Tailscale para a cientista (item 31).

## 3. Fase do roadmap

Fase 3 — "MLflow e Prefect no compose". O doc diz "atrás do Caddy"; pelo ADR de rede (PR 03, rede só Tailscale, desvio do doc), o acesso é pela tailnet, sem proxy com autenticação.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/mlflow/Dockerfile` | Imagem oficial do MLflow + driver Postgres (`psycopg2-binary`), que a oficial não traz |
| `infra/docker-compose.yml` | Serviço `mlflow` e volume `mlflow_artifacts` |
| `infra/scripts/tailscale-serve.sh` | Linha `--https=5000 http://127.0.0.1:5000` |
| `tests/infra/test_compose.py`, `tests/infra/test_tailscale_serve.py` | Casos do `mlflow` (test-writer) |
| `.github/workflows/ci.yml` | Build da imagem e smoke test do `/health` |

Do doc (`docs/plataforma-ml.md`): "MLflow — Tracking de experimentos + model registry — Artefatos em volume local servidos pelo próprio MLflow (`--serve-artifacts`)". "Onde ela trabalha: localmente, no notebook dela, conectada via Tailscale ao Postgres (usuário próprio) e ao MLflow da VPS." Regra (`.claude/rules/infra.md`): "MLflow e Prefect não têm autenticação própria: nunca expor sem proxy com auth ou sem Tailscale".

Regras gerais já cobertas pelos testes do PR 03 (devem continuar passando): nenhuma porta em `0.0.0.0`; `mem_limit` em todo serviço; toda porta de UI em loopback tem linha no `tailscale-serve.sh` e vice-versa; sem `funnel`.

## 5. Passos

1. (test-writer) Casos da seção 8; acrescente `mlflow` à lista de serviços que podem publicar porta e à lista de UIs do caso 9 do PR 03. Confirme falha. Commit `test: add mlflow compose tests`.
2. (implementer) `infra/mlflow/Dockerfile`: `FROM ghcr.io/mlflow/mlflow:v<versão>` (fixe a versão estável atual, conferida no GHCR do MLflow; a mesma versão do cliente que a cientista usa, ver P13), `RUN pip install --no-cache-dir psycopg2-binary==<versão>`.
3. Serviço `mlflow`:
   - `build: {context: ./mlflow}`, `restart: unless-stopped`, `depends_on: postgres` saudável.
   - `ports: ["127.0.0.1:5000:5000"]` (só loopback; nunca `0.0.0.0`).
   - `mem_limit: 512m` (estimativa de 300–500 MB; ajuste pelo número medido no 28a, se houver).
   - `command`: `mlflow server --host 0.0.0.0 --port 5000 --workers 1 --backend-store-uri postgresql://mlflow:${MLFLOW_DB_PASSWORD}@postgres:5432/mlflow --artifacts-destination /mlartifacts --serve-artifacts`. O `--host 0.0.0.0` é dentro do container (rede do compose); o que vai para o host é só o `127.0.0.1:5000` do `ports`. `--workers 1` economiza memória na VPS de 1 GB (confira se a versão fixada aceita a opção; em versões com servidor uvicorn o nome pode mudar). Se a versão fixada exigir lista de hosts permitidos (opção `--allowed-hosts` nas versões recentes), inclua `mlflow`, `localhost`, `127.0.0.1:5000` e `${TS_HOSTNAME}:5000`.
   - `volumes: [mlflow_artifacts:/mlartifacts]`.
   - `healthcheck` em `http://localhost:5000/health` (use `python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"`; a imagem pode não ter `curl`).
4. `infra/scripts/tailscale-serve.sh`: acrescente `tailscale serve --bg --https=5000 http://127.0.0.1:5000`.
5. `ci.yml`: `docker compose -f infra/docker-compose.yml --env-file infra/.env.example build mlflow`; smoke: subir `postgres`, rodar `jobs python -m ingestion create-databases`, subir `mlflow` com `--wait` e `docker compose ... exec mlflow python -c "<urllib /health>"`. Derrubar com `down -v`. (Pode ser o mesmo job de smoke do PR 10.)
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres mlflow` (depois de `create-databases`) | `mlflow ... Healthy` |
| `curl -s http://127.0.0.1:5000/health` | `OK` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example ps --format '{{.Name}} {{.Ports}}'` | `mlflow` com `127.0.0.1:5000->5000/tcp`; nenhuma linha com `0.0.0.0` |
| `shellcheck infra/scripts/tailscale-serve.sh` | Sem saída |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a regra "nunca expor MLflow fora da tailnet" é verificável no compose e no script e protege contra regressão.

## 8. Casos de teste

1. Compose: `mlflow` publica só `127.0.0.1:5000:5000`, tem `restart: unless-stopped` e `mem_limit`.
2. Compose: o `command` do `mlflow` contém `--serve-artifacts` e usa o usuário `mlflow` no backend, nunca o admin; a senha vem de `${MLFLOW_DB_PASSWORD}`.
3. Compose: artefatos em volume nomeado.
4. `tailscale-serve.sh` tem a linha `--https=5000 http://127.0.0.1:5000` (caso geral do PR 03, agora com o `mlflow` na lista de UIs).
5. Exemplo negativo do caso geral: um compose de teste com `mlflow` em `"5000:5000"` (sem IP) reprova.

## 9. Riscos e perguntas em aberto

- Memória: o MLflow é um dos dois serviços mais pesados. Depois do merge, a medição do item 31 decide se o 28b é necessário.
- Sem autenticação no MLflow: qualquer dispositivo da tailnet que a ACL deixe chegar à porta 5000 lê e escreve no registry. A ACL do item 31 libera para a cientista só as portas dela.
- P13: versão do MLflow igual no servidor, no notebook dela e no job de score, senão o registry pode recusar ou carregar errado.
- Cliente do MLflow: ela define só `MLFLOW_TRACKING_URI=https://<host>.ts.net:5000` (sem usuário e senha). O job de score acessa por dentro da rede do compose (`http://mlflow:5000`).

## 10. Decisões que exigem ADR

Coberto pelo ADR "Rede só Tailscale" (PR 03).
