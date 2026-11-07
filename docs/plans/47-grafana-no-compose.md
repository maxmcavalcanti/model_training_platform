# 47 — Grafana no compose, com datasource do Postgres (usuário `leitura`), acessível só pela tailnet

> Executa: agente. Depende de: 30 (padrão de UI em loopback + `tailscale serve`), 41. Branch sugerida: `feat/compose-grafana`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Subir o Grafana publicado só em `127.0.0.1:3000` e exposto na tailnet por `tailscale serve` (`https://<host>.ts.net:3000`), com o datasource do banco `ml` provisionado por arquivo usando o usuário somente leitura `leitura`.
Painéis vêm nos PRs 48, 49 e 58.

## 2. Fora do escopo

- Painéis (PRs 48, 49, 58). Alertas do Grafana (os alertas da plataforma são no Telegram via Prefect, PR 55).

## 3. Fase do roadmap

Fase 4 — "Grafana com dados brutos e previsões".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/docker-compose.yml` | Serviço `grafana`, volume `grafana_data` |
| `infra/grafana/provisioning/datasources/ml.yaml` | Datasource `ml` (PostgreSQL), usuário `leitura`, senha por variável de ambiente |
| `infra/scripts/tailscale-serve.sh` | Linha `--https=3000 http://127.0.0.1:3000` |
| `infra/.env.example` | `GRAFANA_ADMIN_SENHA`, `POSTGRES_LEITURA_SENHA` |
| `tests/infra/test_compose.py`, `tests/infra/test_grafana_provisioning.py` | Testes (test-writer) |
| `.github/workflows/ci.yml` | Smoke do `/api/health` |

Do doc: "Grafana — Painéis de dados, previsões e erro; alertas — Lê o Postgres com usuário somente leitura". Usuários do Postgres: "`leitura` (Grafana)". Regras gerais do PR 03: porta só em loopback ou IP do Tailscale, `mem_limit` em todo serviço, toda UI em loopback com linha no `tailscale-serve.sh`.

## 5. Passos

1. (test-writer) Testes da seção 8; acrescente `grafana` à lista de serviços que podem publicar porta e à de UIs. Confirme falha. Commit `test: add grafana compose and provisioning tests`.
2. (implementer) Serviço `grafana`: `image: grafana/grafana-oss:<versão>` (fixe a atual), `restart: unless-stopped`, `ports: ["127.0.0.1:3000:3000"]`, `mem_limit: 256m` (estimativa de 100–200 MB; ajuste pelo 28a), `volumes: [grafana_data:/var/lib/grafana, ./grafana/provisioning:/etc/grafana/provisioning:ro]`, `environment`: `GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_SENHA}`, `GF_SERVER_ROOT_URL: https://${TS_HOSTNAME}:3000`, `GF_USERS_ALLOW_SIGN_UP: "false"`, `POSTGRES_LEITURA_SENHA: ${POSTGRES_LEITURA_SENHA}`; `depends_on: postgres` saudável; healthcheck em `http://localhost:3000/api/health`.
3. `ml.yaml`: `apiVersion: 1`; datasource `name: ml`, `uid: ml`, `type: grafana-postgresql-datasource` (ou `postgres`, conforme a versão fixada), `url: postgres:5432`, `user: leitura`, `jsonData: {database: ml, sslmode: disable, postgresVersion: 1600}`, `secureJsonData: {password: $POSTGRES_LEITURA_SENHA}` (interpolação de variável de ambiente do Grafana), `editable: false`.
4. `infra/scripts/tailscale-serve.sh`: acrescente `tailscale serve --bg --https=3000 http://127.0.0.1:3000`.
5. CI: subir `grafana` no smoke e checar `/api/health` com `"database": "ok"`.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| Compose local com `.env.example`: `up -d --wait postgres grafana` | `grafana ... Healthy` |
| `docker compose ... exec grafana wget -qO- http://localhost:3000/api/health` | JSON com `"database": "ok"` |
| `docker compose ... ps --format '{{.Name}} {{.Ports}}'` | `grafana` com `127.0.0.1:3000->3000/tcp`; nenhuma linha com `0.0.0.0` |
| `shellcheck infra/scripts/tailscale-serve.sh` | Sem saída |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o datasource com o usuário errado daria ao Grafana permissão de escrita; o teste trava isso.

## 8. Casos de teste

1. `grafana` publica só `127.0.0.1:3000:3000`, com `restart: unless-stopped` e `mem_limit`.
2. Datasource `ml` usa `user: leitura`, banco `ml`, e a senha só como referência a variável de ambiente.
3. Nenhum arquivo em `infra/grafana/` contém senha literal.
4. `GF_USERS_ALLOW_SIGN_UP` é `"false"`.
5. `tailscale-serve.sh` tem a linha `--https=3000 http://127.0.0.1:3000` (regra geral do PR 03).

## 9. Riscos e perguntas em aberto

- Acesso: estar na tailnet (ACL do item 50) + login do próprio Grafana (admin e, se quiser, um usuário para a cientista). Não há proxy com autenticação na frente.
- Memória: o Grafana entra na Fase 4; a medição do item 50 decide se o 28b é necessário.
- Ela "monta 2 ou 3 gráficos" (guia): com `editable: false` só no datasource, ela consegue criar painéis próprios na UI; os provisionados por arquivo não são editáveis (mudança neles é por PR).

## 10. Decisões que exigem ADR

Nenhuma.
