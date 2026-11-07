# 30 — Prefect server no compose, atrás do Caddy com autenticação

> Executa: agente. Depende de: 29 (Caddyfile e testes de proxy). Branch sugerida: `feat/compose-prefect`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Subir o Prefect 3 server (API + UI) com backend no banco `prefect`, acessível de fora só pelo Caddy com `basic_auth`.
É onde os jobs vão ser agendados e onde os dois veem histórico, logs e tracebacks.

## 2. Fora do escopo

- Worker e work pool (PR 34). Flows e deployments (PRs 32 e 33).
- Alertas por automação do Prefect (PR 55).

## 3. Fase do roadmap

Fase 3 — "MLflow e Prefect no compose, atrás do Caddy".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/docker-compose.yml` | Serviço `prefect-server` |
| `infra/caddy/Caddyfile` | Site `prefect.{$DOMINIO}` com `basic_auth` e `reverse_proxy prefect-server:4200` |
| `tests/infra/test_compose.py` | Casos do `prefect-server` (test-writer) |
| `.github/workflows/ci.yml` | Smoke test de `/api/health` |

Do doc: "Prefect 3 (server + worker) — Agenda e executa os jobs; UI com histórico de execuções e logs". "MLflow e Prefect não têm autenticação própria: nunca expor sem proxy com auth". Guia da cientista: "Prefect (só a interface) — Ver se o job do seu modelo rodou e ler o erro — Só leitura".

Os testes gerais de Caddyfile do PR 29 (todo `reverse_proxy` com `basic_auth`) já cobrem o site novo.

## 5. Passos

1. (test-writer) Casos da seção 8 em `tests/infra/test_compose.py`. Confirme falha. Commit `test: add prefect server compose tests`.
2. (implementer) Serviço `prefect-server`:
   - `image: prefecthq/prefect:3.<minor>-python3.12` (fixe a minor atual conferida no Docker Hub; a mesma versão de `prefect` que o PR 32 vai pôr no `pyproject.toml`).
   - `command: ["prefect", "server", "start", "--host", "0.0.0.0"]`, `restart: unless-stopped`, sem `ports`, `depends_on: postgres` saudável.
   - `environment`: `PREFECT_API_DATABASE_CONNECTION_URL: postgresql+asyncpg://prefect:${PREFECT_DB_SENHA}@postgres:5432/prefect`, `PREFECT_UI_API_URL: https://prefect.${DOMINIO}/api`.
   - `healthcheck` em `http://localhost:4200/api/health`.
3. `Caddyfile`: site `prefect.{$DOMINIO}` com os dois usuários de `basic_auth` (como o do MLflow) e `reverse_proxy prefect-server:4200`.
4. `ci.yml`: no smoke, subir `prefect-server` com `--wait`.
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres prefect-server` (depois de `criar-bancos`) | `prefect-server ... Healthy` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example exec prefect-server python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:4200/api/health').read())"` | `b'true'` |
| `caddy validate` | `Valid configuration` |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: mesma regra de exposição do MLflow.

## 8. Casos de teste

1. `prefect-server` não publica porta e tem `restart: unless-stopped`.
2. A URL do banco usa o usuário `prefect` e o banco `prefect`, com senha via `${...}`.
3. `PREFECT_UI_API_URL` aponta para o domínio público com `https://` (a UI chama a API pelo navegador, passando pelo Caddy).
4. A imagem do `prefect-server` tem tag com minor fixada (não `latest`, não só `3`).

## 9. Riscos e perguntas em aberto

- "Só leitura" para a cientista não é garantido pelo Prefect OSS (não tem papéis de usuário). Com `basic_auth` ela consegue também disparar e cancelar execuções. Aceitar ou dar a ela só acesso aos logs via outro caminho; perguntar ao usuário.
- Versões recentes do Prefect 3 têm autenticação básica embutida no server (`PREFECT_SERVER_API_AUTH_STRING`); se a versão fixada tiver, pode ser camada extra. Opcional, não substitui o Caddy.

## 10. Decisões que exigem ADR

Nenhuma.
