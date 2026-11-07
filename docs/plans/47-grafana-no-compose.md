# 47 — Grafana no compose, com datasource do Postgres (usuário `leitura`)

> Executa: agente. Depende de: 30 (Caddyfile e testes de proxy), 41. Branch sugerida: `feat/compose-grafana`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Subir o Grafana atrás do Caddy, com o datasource do banco `ml` provisionado por arquivo usando o usuário somente leitura `leitura`.
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
| `infra/caddy/Caddyfile` | Site `grafana.{$DOMINIO}` com `basic_auth` e `reverse_proxy grafana:3000` |
| `infra/.env.example` | `GRAFANA_ADMIN_SENHA`, `POSTGRES_LEITURA_SENHA` |
| `tests/infra/test_compose.py`, `tests/infra/test_grafana_provisioning.py` | Testes (test-writer) |
| `.github/workflows/ci.yml` | Smoke do `/api/health` |

Do doc: "Grafana — Painéis de dados, previsões e erro; alertas — Lê o Postgres com usuário somente leitura". Usuários do Postgres: "`leitura` (Grafana)". Regra geral do Caddyfile (PR 29): todo `reverse_proxy` com `basic_auth`.

## 5. Passos

1. (test-writer) Testes da seção 8. Confirme falha. Commit `test: add grafana compose and provisioning tests`.
2. (implementer) Serviço `grafana`: `image: grafana/grafana-oss:<versão>` (fixe a atual), `restart: unless-stopped`, sem `ports`, `volumes: [grafana_data:/var/lib/grafana, ./grafana/provisioning:/etc/grafana/provisioning:ro]`, `environment`: `GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_SENHA}`, `GF_SERVER_ROOT_URL: https://grafana.${DOMINIO}`, `GF_USERS_ALLOW_SIGN_UP: "false"`, `POSTGRES_LEITURA_SENHA: ${POSTGRES_LEITURA_SENHA}`; `depends_on: postgres` saudável; healthcheck em `http://localhost:3000/api/health`.
3. `ml.yaml`: `apiVersion: 1`; datasource `name: ml`, `uid: ml`, `type: grafana-postgresql-datasource` (ou `postgres`, conforme a versão fixada), `url: postgres:5432`, `user: leitura`, `jsonData: {database: ml, sslmode: disable, postgresVersion: 1600}`, `secureJsonData: {password: $POSTGRES_LEITURA_SENHA}` (interpolação de variável de ambiente do Grafana), `editable: false`.
4. `Caddyfile`: site `grafana.{$DOMINIO}` com os dois usuários de `basic_auth` e `reverse_proxy grafana:3000`.
5. CI: subir `grafana` no smoke e checar `/api/health` com `"database": "ok"`.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| Compose local com `.env.example`: `up -d --wait postgres grafana` | `grafana ... Healthy` |
| `docker compose ... exec grafana wget -qO- http://localhost:3000/api/health` | JSON com `"database": "ok"` |
| `caddy validate` | `Valid configuration` |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o datasource com o usuário errado daria ao Grafana permissão de escrita; o teste trava isso.

## 8. Casos de teste

1. `grafana` sem `ports`, com `restart: unless-stopped`.
2. Datasource `ml` usa `user: leitura`, banco `ml`, e a senha só como referência a variável de ambiente.
3. Nenhum arquivo em `infra/grafana/` contém senha literal.
4. `GF_USERS_ALLOW_SIGN_UP` é `"false"`.
5. Caddyfile: o site do Grafana tem `basic_auth` (regra geral já existente).

## 9. Riscos e perguntas em aberto

- Dupla autenticação (Caddy + login do Grafana). Alternativa: Grafana com `auth.proxy` confiando no usuário do Caddy. Fica a dupla por simplicidade; perguntar se incomoda.
- Ela "monta 2 ou 3 gráficos" (guia): com `editable: false` só no datasource, ela consegue criar painéis próprios na UI; os provisionados por arquivo não são editáveis (mudança neles é por PR).

## 10. Decisões que exigem ADR

Nenhuma.
