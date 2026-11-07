# 29 — MLflow no compose, atrás do Caddy com autenticação

> Executa: agente. Depende de: 03, 10, 28. Branch sugerida: `feat/compose-mlflow`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Subir o MLflow (tracking + model registry) com backend no banco `mlflow` e artefatos num volume local servidos pelo próprio MLflow, acessível de fora só pelo Caddy com `basic_auth`.
É o que libera a cientista para registrar experimentos e modelos.

## 2. Fora do escopo

- Prefect (PR 30). MinIO (o doc diz "MinIO só se crescer").
- Backup do volume de artefatos (PR 57).
- Uso do MLflow pelo job de score (PR 43).

## 3. Fase do roadmap

Fase 3 — "MLflow e Prefect no compose, atrás do Caddy".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/mlflow/Dockerfile` | Imagem oficial do MLflow + driver Postgres (`psycopg2-binary`), que a oficial não traz |
| `infra/docker-compose.yml` | Serviço `mlflow` e volume `mlflow_artifacts` |
| `infra/caddy/Caddyfile` | Site `mlflow.{$DOMINIO}` com `basic_auth` e `reverse_proxy mlflow:5000` |
| `infra/.env.example` | `CADDY_CIENTISTA_USUARIO`, `CADDY_CIENTISTA_SENHA_HASH` (fictícios) |
| `tests/infra/test_compose.py`, `tests/infra/test_caddyfile.py` | Testes (test-writer) |
| `.github/workflows/ci.yml` | Build da imagem e smoke test do `/health` |

Do doc (`docs/plataforma-ml.md`): "MLflow — Tracking de experimentos + model registry — Artefatos em volume local servidos pelo próprio MLflow (`--serve-artifacts`)". "MLflow e Prefect não têm autenticação própria: nunca expor sem proxy com auth". "Onde ela trabalha: localmente, no notebook dela, conectada via Tailscale ao Postgres (usuário próprio) e ao MLflow da VPS."

## 5. Passos

1. (test-writer) Testes da seção 8. `tests/infra/test_caddyfile.py` lê o `Caddyfile` como texto e verifica cada bloco de site. Confirme falha. Commit `test: add mlflow compose and proxy tests`.
2. (implementer) `infra/mlflow/Dockerfile`: `FROM ghcr.io/mlflow/mlflow:v<versão>` (fixe a versão estável atual, conferida no GHCR do MLflow; a mesma versão do cliente que a cientista usa, ver P13), `RUN pip install --no-cache-dir psycopg2-binary==<versão>`.
3. Serviço `mlflow`:
   - `build: {context: ./mlflow}`, `restart: unless-stopped`, `depends_on: postgres` saudável, sem `ports`.
   - `command`: `mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri postgresql://mlflow:${MLFLOW_DB_SENHA}@postgres:5432/mlflow --artifacts-destination /mlartifacts --serve-artifacts`. Se a versão fixada exigir lista de hosts permitidos (opção `--allowed-hosts` nas versões recentes), inclua `mlflow`, `localhost` e `mlflow.${DOMINIO}`.
   - `volumes: [mlflow_artifacts:/mlartifacts]`.
   - `healthcheck` em `http://localhost:5000/health` (use `python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"`; a imagem pode não ter `curl`).
4. `Caddyfile`, novo site:
   ```
   mlflow.{$DOMINIO} {
       basic_auth {
           {$CADDY_USUARIO} {$CADDY_SENHA_HASH}
           {$CADDY_CIENTISTA_USUARIO} {$CADDY_CIENTISTA_SENHA_HASH}
       }
       reverse_proxy mlflow:5000
   }
   ```
5. `ci.yml`: `docker compose -f infra/docker-compose.yml --env-file infra/.env.example build mlflow`; smoke: subir `postgres`, rodar `jobs python -m ingestion criar-bancos`, subir `mlflow` com `--wait` e `docker compose ... exec mlflow python -c "<urllib /health>"`. Derrubar com `down -v`. (Pode ser o mesmo job de smoke do PR 10.)
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres mlflow` (depois de `criar-bancos`) | `mlflow ... Healthy` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example exec mlflow python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5000/health').read())"` | `b'OK'` |
| `caddy validate` do PR 03 | `Valid configuration` |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a regra "nunca expor MLflow sem auth" é verificável no compose e no Caddyfile e protege contra regressão.

## 8. Casos de teste

1. Compose: `mlflow` não publica porta e tem `restart: unless-stopped`.
2. Compose: o `command` do `mlflow` contém `--serve-artifacts` e usa o usuário `mlflow` no backend, nunca o admin.
3. Compose: artefatos em volume nomeado.
4. Caddyfile: todo bloco de site que contém `reverse_proxy` também contém `basic_auth` (regra geral; vale para Prefect e Grafana depois).
5. Caddyfile: o único `handle` sem `basic_auth` é `/saude` do site principal.
6. Caddyfile: hashes de senha só aparecem como `{$...}`.

## 9. Riscos e perguntas em aberto

- P4: subdomínio `mlflow.<dominio>` exige registro DNS (item 31). Na opção "só Tailscale", o nome `*.ts.net` não aceita subdomínio; aí o Caddy precisa de uma porta por serviço no IP do Tailscale. Ajustar conforme o ADR de rede.
- P13: versão do MLflow igual no servidor, no notebook dela e no job de score, senão o registry pode recusar ou carregar errado.
- Cliente do MLflow com `basic_auth`: ela define `MLFLOW_TRACKING_URI=https://mlflow.<dominio>`, `MLFLOW_TRACKING_USERNAME` e `MLFLOW_TRACKING_PASSWORD`. O job de score acessa por dentro da rede do compose (`http://mlflow:5000`), sem passar pelo Caddy.

## 10. Decisões que exigem ADR

Coberto pelo ADR de rede (PR 03), se ele precisar mudar por causa de subdomínios.
