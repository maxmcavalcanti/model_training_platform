# 10 — Postgres no compose de produção

> Executa: agente. Depende de: 03, 05. Branch sugerida: `feat/compose-postgres`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Acrescentar o serviço `postgres` (16, banco `ml`) ao `infra/docker-compose.yml`, com volume persistente, healthcheck, `mem_limit` e porta publicada só em loopback (`127.0.0.1:5432`) e exposta na tailnet por `tailscale serve --tcp=5432` (P15, ADR 0003), nunca em `0.0.0.0`.
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
| `infra/.env.example` | `POSTGRES_ADMIN_USER`, `POSTGRES_ADMIN_PASSWORD`, `POSTGRES_BIND_IP` (valores fictícios) |
| `tests/infra/test_compose.py` | Casos novos para o serviço `postgres` de produção (test-writer) |
| `.github/workflows/ci.yml` | Smoke test: subir o `postgres` do compose de produção e esperar `healthy` |
| `infra/scripts/tailscale-serve.sh` | Linha `tailscale serve --bg --tcp=5432 tcp://127.0.0.1:5432` (P15) |
| `tests/infra/test_tailscale_serve.py` | Caso novo para a linha do Postgres (test-writer) |

Regras de infra (de `.claude/rules/infra.md`): todo serviço com `restart: unless-stopped`; nenhuma porta pública (rede só Tailscale, decisão de 2026-11-07, ADR 0003); `.env` fora do git. Do PR 03: todo serviço tem `mem_limit` (VPS de 1 GB).

Atenção (está no item 02): porta publicada pelo Docker passa por cima do ufw. Publicar em `0.0.0.0` exporia o Postgres à internet; os testes do PR 03 reprovam isso.

## 5. Passos

1. (test-writer) Em `tests/infra/test_compose.py`, acrescente os casos da seção 8 para `infra/docker-compose.yml`. Escreva também o caso 7 em `tests/infra/test_tailscale_serve.py`. Confirme falha porque o serviço `postgres` não existe no compose de produção. Commit `test: add prod postgres compose tests`.
2. (implementer) No `infra/docker-compose.yml`, serviço `postgres`:
   - `image: postgres:16.<minor>` (mesma minor do compose de dev, PR 05)
   - `restart: unless-stopped`
   - `mem_limit: 256m` (estimativa de 100–250 MB, a medir no checkpoint 28a)
   - `environment`: `POSTGRES_USER: ${POSTGRES_ADMIN_USER}`, `POSTGRES_PASSWORD: ${POSTGRES_ADMIN_PASSWORD}`, `POSTGRES_DB: ml`
   - `volumes: [pgdata:/var/lib/postgresql/data]`
   - `ports: ["${POSTGRES_BIND_IP}:5432:5432"]`
   - `healthcheck`: `pg_isready -U ${POSTGRES_ADMIN_USER} -d ml`, intervalo 10s, 5 tentativas
   - Volume nomeado `pgdata`.
3. Em `infra/.env.example`: `POSTGRES_ADMIN_USER=platform_admin`, `POSTGRES_ADMIN_PASSWORD=troque-me`, `POSTGRES_BIND_IP=127.0.0.1`, com comentário: "o Postgres fica em 127.0.0.1 e é exposto na tailnet por `tailscale serve --tcp=5432` (ADR 0003); nunca 0.0.0.0".
4. Em `infra/scripts/tailscale-serve.sh`, acrescente `tailscale serve --bg --tcp=5432 tcp://127.0.0.1:5432` depois das linhas `--https`. Confira a sintaxe contra `tailscale serve --help` da versão instalada (mesma regra do PR 03); se divergir, ajuste e registre no PR.
5. No `ci.yml`, novo passo depois dos testes: `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres` e depois `docker compose -f infra/docker-compose.yml --env-file infra/.env.example down -v`. Atenção à porta 5432 já usada pelo service container do CI: no passo, sobrescreva com `POSTGRES_BIND_IP=127.0.0.2` (o loopback inteiro responde no Linux) ou rode o smoke num job separado sem service container. Escolha a segunda se a primeira conflitar.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_compose.py` | Todos passam |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Sem saída, código 0 |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres` (localmente, com o compose de dev parado) | `Container platform-postgres-1  Healthy` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example exec postgres psql -U platform_admin -d ml -c "select 1"` | Uma linha com `1` |
| `uv run pytest` | Suíte verde |
| `shellcheck infra/scripts/tailscale-serve.sh` | Sem saída |
| `gh pr checks` | Verde, com o passo de smoke do compose |

## 7. Testes necessários

`sim`: a exposição de porta do banco é o maior risco de segurança da fase; o teste de YAML impede regressão em todo PR futuro.

## 8. Casos de teste

1. Em `infra/docker-compose.yml`, `postgres` publica só a porta de container 5432, com IP de host `${POSTGRES_BIND_IP}`; acrescente `postgres` à lista de serviços que podem publicar porta. O caso geral do PR 03 garante que `POSTGRES_BIND_IP` no `.env.example` é loopback ou da faixa do Tailscale.
2. `postgres` usa volume nomeado (não bind mount) para `/var/lib/postgresql/data`.
3. `postgres` tem `healthcheck`.
4. `POSTGRES_PASSWORD` vem de `${...}` (já coberto pela regra geral de segredos; deve continuar passando).
5. A imagem de `postgres` no compose de produção e no de dev é a mesma tag.
6. `infra/.env.example` declara todas as variáveis `${VAR}` sem valor padrão usadas em `infra/docker-compose.yml` (caso geral: vale para todos os serviços futuros).
7. `infra/scripts/tailscale-serve.sh` tem uma linha `--tcp=5432 tcp://127.0.0.1:5432`, e `POSTGRES_BIND_IP` em `infra/.env.example` vale `127.0.0.1`.

## 9. Riscos e perguntas em aberto

- Com `tailscale serve --tcp`, o Postgres vê as conexões da tailnet vindas de 127.0.0.1. Se o teste de reboot do item 12 falhar, devolva para o planejamento.
- Ajustes de memória do Postgres (`shared_buffers` etc.): o padrão da imagem (128 MB) cabe no `mem_limit: 256m`. Ajuste fino só depois da medição do checkpoint 28a.

## 10. Decisões que exigem ADR

Coberto pelo ADR 0003 (`docs/adr/0003-tailscale-only-network.md`).
