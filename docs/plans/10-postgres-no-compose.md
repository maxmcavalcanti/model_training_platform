# 10 — Postgres no compose de produção

> Executa: agente. Depende de: 03, 05. Branch sugerida: `feat/compose-postgres`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Acrescentar o serviço `postgres` (16, banco `ml`) ao `infra/docker-compose.yml`, com volume persistente, healthcheck e porta publicada só no IP do Tailscale.
Isso permite que a cientista de dados acesse o banco do notebook dela via Tailscale (critério da Fase 1).

## 2. Fora do escopo

- Imagem dos jobs e execução de migração na VPS (PR 11 e item 12).
- Bancos `mlflow` e `prefect` (PR 28).
- Backups (PR 57).

## 3. Fase do roadmap

Fase 1 — "Postgres, migrações com Alembic, usuários e permissões" (parte "Postgres" em produção).

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/docker-compose.yml` | Serviço `postgres` e volume `pgdata` |
| `infra/.env.example` | `POSTGRES_ADMIN_USUARIO`, `POSTGRES_ADMIN_SENHA`, `POSTGRES_BIND_IP` (valores fictícios) |
| `tests/infra/test_compose.py` | Casos novos para o serviço `postgres` de produção (test-writer) |
| `.github/workflows/ci.yml` | Smoke test: subir o `postgres` do compose de produção e esperar `healthy` |

Regras de infra (de `.claude/rules/infra.md`): todo serviço com `restart: unless-stopped`; só 22 e 443 abertas ou nenhuma porta pública; `.env` fora do git.

Atenção (está no item 02): porta publicada pelo Docker passa por cima do ufw. Publicar em `0.0.0.0` exporia o Postgres à internet.

## 5. Passos

1. (test-writer) Em `tests/infra/test_compose.py`, acrescente os casos da seção 8 para `infra/docker-compose.yml`. Confirme falha porque o serviço `postgres` não existe no compose de produção. Commit `test: add prod postgres compose tests`.
2. (implementer) No `infra/docker-compose.yml`, serviço `postgres`:
   - `image: postgres:16.<minor>` (mesma minor do compose de dev, PR 05)
   - `restart: unless-stopped`
   - `environment`: `POSTGRES_USER: ${POSTGRES_ADMIN_USUARIO}`, `POSTGRES_PASSWORD: ${POSTGRES_ADMIN_SENHA}`, `POSTGRES_DB: ml`
   - `volumes: [pgdata:/var/lib/postgresql/data]`
   - `ports: ["${POSTGRES_BIND_IP}:5432:5432"]`
   - `healthcheck`: `pg_isready -U ${POSTGRES_ADMIN_USUARIO} -d ml`, intervalo 10s, 5 tentativas
   - Volume nomeado `pgdata`.
3. Em `infra/.env.example`: `POSTGRES_ADMIN_USUARIO=plataforma_admin`, `POSTGRES_ADMIN_SENHA=troque-me`, `POSTGRES_BIND_IP=127.0.0.1`, com comentário: "na VPS, use o IP do Tailscale (`tailscale ip -4`)".
4. No `ci.yml`, novo passo depois dos testes: `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres` e depois `docker compose -f infra/docker-compose.yml --env-file infra/.env.example down -v`. Atenção à porta 5432 já usada pelo service container do CI: no passo, sobrescreva com `POSTGRES_BIND_IP=127.0.0.2` (o loopback inteiro responde no Linux) ou rode o smoke num job separado sem service container. Escolha a segunda se a primeira conflitar.
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_compose.py` | Todos passam |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Sem saída, código 0 |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres` (localmente, com o compose de dev parado) | `Container plataforma-postgres-1  Healthy` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example exec postgres psql -U plataforma_admin -d ml -c "select 1"` | Uma linha com `1` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde, com o passo de smoke do compose |

## 7. Testes necessários

`sim`: a exposição de porta do banco é o maior risco de segurança da fase; o teste de YAML impede regressão em todo PR futuro.

## 8. Casos de teste

1. Em `infra/docker-compose.yml`, `postgres` publica só a porta de container 5432, com IP de host `${POSTGRES_BIND_IP}`.
2. `postgres` usa volume nomeado (não bind mount) para `/var/lib/postgresql/data`.
3. `postgres` tem `healthcheck`.
4. `POSTGRES_PASSWORD` vem de `${...}` (já coberto pela regra geral de segredos; deve continuar passando).
5. A imagem de `postgres` no compose de produção e no de dev é a mesma tag.
6. `infra/.env.example` declara todas as variáveis `${VAR}` sem valor padrão usadas em `infra/docker-compose.yml` (caso geral: vale para todos os serviços futuros).

## 9. Riscos e perguntas em aberto

- P15: bind no IP do Tailscale exige que o Docker suba depois do tailscaled (configurado no item 02). Se o IP não existir no boot, o container não sobe e o reboot quebra. Alternativa: sidecar do Tailscale no compose. Decidir se o teste de reboot do item 12 falhar.
- Ajustes de memória do Postgres (`shared_buffers` etc.) ficam para depois do `docker stats` da Fase 3, como diz o doc.

## 10. Decisões que exigem ADR

Coberto pelo ADR de rede do PR 03.
