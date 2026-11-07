# 30 — Prefect server no compose, acessível só pela tailnet

> Executa: agente. Depende de: 29 (padrão de serviço com UI em loopback + `tailscale serve`). Branch sugerida: `feat/compose-prefect`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Subir o Prefect 3 server (API + UI) com backend no banco `prefect`, publicado só em `127.0.0.1:4200` e exposto na tailnet por `tailscale serve` (`https://<host>.ts.net:4200`).
É onde os jobs vão ser agendados e onde os dois veem histórico, logs e tracebacks.

## 2. Fora do escopo

- Worker e work pool (PR 34). Flows e deployments (PRs 32 e 33).
- Alertas por automação do Prefect (PR 55).

## 3. Fase do roadmap

Fase 3 — "MLflow e Prefect no compose". O doc diz "atrás do Caddy"; pelo ADR de rede (PR 03, rede só Tailscale, desvio do doc), o acesso é pela tailnet.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/docker-compose.yml` | Serviço `prefect-server` |
| `infra/scripts/tailscale-serve.sh` | Linha `--https=4200 http://127.0.0.1:4200` |
| `tests/infra/test_compose.py` | Casos do `prefect-server` (test-writer) |
| `.github/workflows/ci.yml` | Smoke test de `/api/health` |

Do doc: "Prefect 3 (server + worker) — Agenda e executa os jobs; UI com histórico de execuções e logs". Regra: "MLflow e Prefect não têm autenticação própria: nunca expor sem proxy com auth ou sem Tailscale". Guia da cientista: "Prefect (só a interface) — Ver se o job do seu modelo rodou e ler o erro — Só leitura".

Os testes gerais do PR 03 (porta só em loopback ou IP do Tailscale, `mem_limit`, correspondência com o `tailscale-serve.sh`) já cobrem o serviço novo quando ele entra na lista de UIs.

## 5. Passos

1. (test-writer) Casos da seção 8 em `tests/infra/test_compose.py`; acrescente `prefect-server` à lista de serviços que podem publicar porta e à de UIs. Confirme falha. Commit `test: add prefect server compose tests`.
2. (implementer) Serviço `prefect-server`:
   - `image: prefecthq/prefect:3.<minor>-python3.12` (fixe a minor atual conferida no Docker Hub; a mesma versão de `prefect` que o PR 32 vai pôr no `pyproject.toml`).
   - `command: ["prefect", "server", "start", "--host", "0.0.0.0"]` (dentro do container), `restart: unless-stopped`, `ports: ["127.0.0.1:4200:4200"]`, `mem_limit: 640m` (estimativa server + worker de 500–800 MB; ajuste pelo 28a), `depends_on: postgres` saudável.
   - `environment`: `PREFECT_API_DATABASE_CONNECTION_URL: postgresql+asyncpg://prefect:${PREFECT_DB_SENHA}@postgres:5432/prefect`, `PREFECT_UI_API_URL: https://${TS_HOSTNAME}:4200/api`.
   - `healthcheck` em `http://localhost:4200/api/health`.
3. `infra/scripts/tailscale-serve.sh`: acrescente `tailscale serve --bg --https=4200 http://127.0.0.1:4200`.
4. `ci.yml`: no smoke, subir `prefect-server` com `--wait`.
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres prefect-server` (depois de `criar-bancos`) | `prefect-server ... Healthy` |
| `curl -s http://127.0.0.1:4200/api/health` | `true` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example ps --format '{{.Name}} {{.Ports}}'` | `prefect-server` com `127.0.0.1:4200->4200/tcp`; nenhuma linha com `0.0.0.0` |
| `shellcheck infra/scripts/tailscale-serve.sh` | Sem saída |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: mesma regra de exposição do MLflow.

## 8. Casos de teste

1. `prefect-server` publica só `127.0.0.1:4200:4200`, tem `restart: unless-stopped` e `mem_limit`.
2. A URL do banco usa o usuário `prefect` e o banco `prefect`, com senha via `${...}`.
3. `PREFECT_UI_API_URL` é `https://${TS_HOSTNAME}:4200/api` (a UI chama a API pelo navegador, pela tailnet).
4. A imagem do `prefect-server` tem tag com minor fixada (não `latest`, não só `3`).
5. `tailscale-serve.sh` tem a linha `--https=4200 http://127.0.0.1:4200`.

## 9. Riscos e perguntas em aberto

- "Só leitura" para a cientista não é garantido pelo Prefect OSS (não tem papéis de usuário). Sem proxy com autenticação, quem a ACL deixa chegar à porta 4200 consegue disparar e cancelar execuções. Aceitar ou dar a ela só acesso aos logs via outro caminho; perguntar ao usuário.
- Versões recentes do Prefect 3 têm autenticação básica embutida no server (`PREFECT_SERVER_API_AUTH_STRING`); se a versão fixada tiver, é uma camada opcional além da ACL do Tailscale. Fora deste PR; perguntar.
- Memória: Prefect server é o serviço mais pesado da Fase 3. A medição do item 31 decide se o 28b é necessário.

## 10. Decisões que exigem ADR

Nenhuma (coberto pelo ADR "Rede só Tailscale" do PR 03).
