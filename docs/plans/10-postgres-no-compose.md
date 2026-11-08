# 10 — Postgres no compose de produção

> Executa: agente. Depende de: 03, 05 (ambos na `main`; `main` em `be56c94`, com 05, 06, 07 e 08 mergeados). Branch sugerida: `feat/compose-postgres`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisado em 2026-11-07 contra a `main` (ver "Notas da revisão" no fim).

## 1. Objetivo

Acrescentar o serviço `postgres` (16.15, banco `ml`) ao `infra/docker-compose.yml`, com volume nomeado, healthcheck, `mem_limit`, autenticação `scram-sha-256` para conexões TCP e porta publicada só em `127.0.0.1:5432`, exposta na tailnet por `tailscale serve --tcp=5432` (P15, ADR 0003), nunca em `0.0.0.0`.
Isso permite que a cientista de dados acesse o banco do notebook dela via Tailscale (critério da Fase 1; a subida real na VPS é o item 12).

## 2. Fora do escopo

- Imagem dos jobs, serviço `jobs` e execução de migração na VPS (PR 11 e item 12).
- Senhas dos papéis `ingestor`, `scientist`, `scorer`, `reader` (definidas à mão no item 12; a migração `0002` cria os papéis `LOGIN` sem senha, de propósito). Nenhuma variável `POSTGRES_<ROLE>_PASSWORD` entra neste PR.
- ACL do Tailscale e convite da cientista (item 12).
- Bancos `mlflow` e `prefect` (PR 28).
- Backups e restore (PR 57). Ajuste fino de memória do Postgres (`shared_buffers` etc.; checkpoint 28a).
- Montar `pg_hba.conf` ou `postgresql.conf` próprios por bind mount (ver passo 3: a autenticação é configurada por variáveis da imagem oficial).

## 3. Fase do roadmap

Fase 1 — "Postgres, migrações com Alembic, usuários e permissões" (parte "Postgres" em produção).

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/infra/test_compose.py` | test-writer | Casos 1 a 6 e 8 da seção 8 |
| `tests/infra/test_tailscale_serve.py` | test-writer | Caso 7 (mapeamento `--tcp` ↔ compose) e generalização do `header_problems` |
| `infra/docker-compose.yml` | implementer | Serviço `postgres` e volume `pgdata` |
| `infra/.env.example` | implementer (ver risco "deny de Read") | `POSTGRES_ADMIN_USER`, `POSTGRES_ADMIN_PASSWORD`, `POSTGRES_BIND_IP` com valores fictícios |
| `infra/scripts/tailscale-serve.sh` | implementer | Linha `tailscale serve --bg --tcp=5432 tcp://127.0.0.1:5432` e comentário do topo |
| `.github/workflows/ci.yml` | implementer | Job novo `compose-smoke`: sobe o `postgres` de produção, confere `healthy` e `scram-sha-256` |

### Regras e contexto que o implementador precisa

De `.claude/rules/infra.md`:

> - Todo serviço no compose tem `restart: unless-stopped`.
> - Firewall: nenhuma porta pública (ADR 0003). [...] Nenhuma porta do compose em `0.0.0.0` (o Docker passa por cima do ufw). [...] Não abrir porta para "testar".
> - `.env` da VPS fica fora do git, permissão 600. Segredos do CI vão em GitHub Secrets.

Do índice (`docs/plans/00-indice.md`): todo serviço tem `mem_limit` (VPS de 1 GB; estimativa do Postgres 100–250 MB, a medir no 28a). P15: "Loopback + `tailscale serve --tcp=5432`: `127.0.0.1:5432`, sem sidecar do Tailscale no compose e sem dependência da ordem de boot".

De `AGENTS.md`: nenhum segredo no git (repos públicos); agentes nunca leem arquivos `.env` com nenhuma ferramenta (o deny de `Read` cobre também `infra/.env.example`).

Estado atual na `main`:

`infra/docker-compose.yml`:

```yaml
name: platform

services:
  health:
    image: busybox:1.38.0
    command: ["httpd", "-f", "-p", "8080", "-h", "/www"]
    volumes:
      - "./health:/www:ro"
    restart: unless-stopped
    mem_limit: 16m
    ports:
      - "${HEALTH_BIND_IP:-127.0.0.1}:8080:8080"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8080/health"]
      interval: 10s
      timeout: 3s
      retries: 3
```

`infra/docker-compose.dev.yml` usa `image: postgres:16.15`, `mem_limit: 512m`, porta `"${DEV_BIND_IP:-127.0.0.1}:5432:5432"`.

`infra/scripts/tailscale-serve.sh`:

```bash
#!/usr/bin/env bash
# Declares which loopback ports are exposed as HTTPS on the tailnet (ADR 0003).
# Reset first, then reapply: the serve state on the VPS always matches git.
# One line per UI, same port on loopback and on the tailnet.
set -euo pipefail

tailscale serve reset

tailscale serve --bg --https=8080 http://127.0.0.1:8080
```

`infra/.env.example` (conteúdo segundo o plano 03; o planner não o leu por causa do deny): comentário no topo, `HEALTH_BIND_IP=127.0.0.1`, `TS_HOSTNAME=platform.example.ts.net`.

Pontos dos testes existentes que condicionam este PR:

- `tests/infra/test_compose.py`: `PORT_PUBLISHING_SERVICES = frozenset({"health", "postgres"})` (o `postgres` **já** está na allow-list). `is_acceptable_port` só aceita `127.0.0.1` literal ou `${X_BIND_IP:-127.0.0.1}`; **um `${POSTGRES_BIND_IP}` sem default é reprovado** (vira `:5432:5432` = `0.0.0.0` se a variável faltar). `literal_secret_keys` exige `${...}` em chaves com `PASSWORD`. `bad_bind_ips` exige todo `*_BIND_IP` do `.env.example` em loopback ou `100.64.0.0/10`.
- `tests/infra/test_tailscale_serve.py`: a regex `MAPPING` só reconhece `--https=<p> http://127.0.0.1:<p>`; `UI_SERVICES = ("health", "mlflow", "prefect-server", "grafana")`; a fixture `ui_loopback_ports` varre **todos** os `docker-compose*.yml` (inclusive o de dev). Hoje uma linha `--tcp` seria ignorada pelas checagens: não é validada nem conta para "reset antes do mapeamento".
- CI (`.github/workflows/ci.yml`, job `lint-and-test`): service container `postgres:16` publicado em `5432:5432` (todas as interfaces do runner), depois `uv run pytest`, `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` e `shellcheck infra/scripts/*.sh`.

## 5. Passos

1. (test-writer) Em `tests/infra/test_compose.py`, escreva os casos 1 a 6 e 8 da seção 8. Em `tests/infra/test_tailscale_serve.py`, escreva o caso 7, com exemplos negativos embutidos (padrão do arquivo: toda função de checagem tem exemplo que reprova). Confirme que falham porque o serviço `postgres` não existe em `infra/docker-compose.yml` e o script não tem linha `--tcp` (não por erro de import). Os testes existentes que já passam devem continuar passando. Commit `test: add prod postgres compose tests`.
2. (implementer) Em `infra/docker-compose.yml`, acrescente o serviço `postgres`:
   - `image: postgres:16.15` (a mesma tag do compose de dev)
   - `restart: unless-stopped`
   - `mem_limit: 256m`
   - `environment`:
     - `POSTGRES_USER: ${POSTGRES_ADMIN_USER:?POSTGRES_ADMIN_USER is required}`
     - `POSTGRES_PASSWORD: ${POSTGRES_ADMIN_PASSWORD:?POSTGRES_ADMIN_PASSWORD is required}`
     - `POSTGRES_DB: ml`
     - `POSTGRES_HOST_AUTH_METHOD: scram-sha-256`
     - `POSTGRES_INITDB_ARGS: "--auth-host=scram-sha-256"`
   - `volumes: ["pgdata:/var/lib/postgresql/data"]`
   - `ports: ["${POSTGRES_BIND_IP:-127.0.0.1}:5432:5432"]` (o default `127.0.0.1` é obrigatório: o teste reprova a forma sem default)
   - `healthcheck`: `test: ["CMD-SHELL", "pg_isready -U \"$${POSTGRES_USER}\" -d ml"]`, `interval: 10s`, `timeout: 5s`, `retries: 5`, `start_period: 30s` (o `$$` faz a variável ser lida dentro do container, não interpolada pelo compose)
   - No nível de topo: `volumes: { pgdata: {} }`.
   - Não defina `listen_addresses`: dentro do container o Postgres precisa escutar na interface da rede do Docker para a publicação de porta funcionar. "Só loopback" é garantido no host pelo `ports` em `127.0.0.1`.
3. (implementer) Autenticação, para registrar no PR: com `POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256`, as linhas `host` que o `initdb` gera (127.0.0.1/::1 e replicação) usam `scram-sha-256`; o entrypoint da imagem acrescenta `host all all all scram-sha-256` por causa do `POSTGRES_HOST_AUTH_METHOD`. `password_encryption` já é `scram-sha-256` por padrão no Postgres 16. O socket local (`local`) fica `trust`, padrão da imagem: só alcançável por `docker compose exec`, que já exige acesso de root ao host (ver pergunta em aberto 1). Papéis `LOGIN` sem senha não conseguem autenticar por TCP com `scram-sha-256`, que é o comportamento desejado até o item 12. Essas variáveis só valem na criação do volume; um volume `pgdata` já existente mantém o `pg_hba.conf` antigo.
4. (implementer) Em `infra/.env.example`, acrescente sem apagar o que existe:
   ```
   # Postgres (plan 10). Fictitious values: the real ones live only in infra/.env on the VPS.
   # Postgres stays on 127.0.0.1 and is exposed on the tailnet by `tailscale serve --tcp=5432`
   # (ADR 0003). Never 0.0.0.0.
   POSTGRES_ADMIN_USER=platform_admin
   POSTGRES_ADMIN_PASSWORD=change-me
   POSTGRES_BIND_IP=127.0.0.1
   ```
   O implementador não pode ler esse arquivo (deny de `Read`, regra do `AGENTS.md`), então Edit/Write não funcionam nele. Siga a decisão do usuário na pergunta em aberto 2; o padrão recomendado é anexar sem ler: `printf '%s\n' '...' >> infra/.env.example` pelo Bash, e conferir com `uv run pytest tests/infra` (os testes leem o arquivo em Python).
5. (implementer) Em `infra/scripts/tailscale-serve.sh`, depois da linha `--https=8080`, acrescente `tailscale serve --bg --tcp=5432 tcp://127.0.0.1:5432`. Atualize o comentário do topo: "Declares which loopback ports are exposed on the tailnet (ADR 0003): HTTPS per UI, raw TCP for Postgres (P15)." e "One line per service, same port on loopback and on the tailnet." A sintaxe vale para o CLI atual do Tailscale (`--tcp=<porta> tcp://<host>:<porta>`); confira contra `tailscale serve --help` da versão da VPS (item 12). Se divergir, ajuste o script e o regex do teste num PR de correção, registrando no PR. Rode `shellcheck infra/scripts/tailscale-serve.sh` se o shellcheck existir localmente; no CI ele já roda.
6. (implementer) Em `.github/workflows/ci.yml`, crie um job novo `compose-smoke` (sem `services:`, para não disputar a porta 5432 com o service container do `lint-and-test`: bindar `127.0.0.2:5432` falha enquanto `0.0.0.0:5432` está ocupado). Passos do job:
   1. `actions/checkout@v7`
   2. `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres`
   3. `docker compose -f infra/docker-compose.yml --env-file infra/.env.example exec -T postgres psql -U platform_admin -d ml -tAc "select count(*) from pg_hba_file_rules where type like 'host%' and auth_method <> 'scram-sha-256'"` e falhar se a saída não for `0` (por exemplo, `test "$(...)" = 0`).
   4. `docker compose -f infra/docker-compose.yml --env-file infra/.env.example ps --format '{{.Ports}}' postgres | grep -v '0\.0\.0\.0'` (falha se publicar em `0.0.0.0`; `grep -v` sem linhas restantes também falha, o que pega serviço sem porta).
   5. Com `if: always()`: `docker compose -f infra/docker-compose.yml --env-file infra/.env.example down -v`.
   `down -v` apaga o volume: é só para o CI e para teste local; nunca na VPS.
7. (implementer) Rode os critérios de pronto e cole comando e saída no PR.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra` | Todos passam |
| `uv run pytest` | Suíte verde (precisa do Postgres de dev, como hoje) |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erros |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Sem saída, código 0 |
| `docker compose -f infra/docker-compose.yml config -q` (sem `--env-file`, sem `infra/.env`) | Falha com `POSTGRES_ADMIN_USER is required` (ou a mensagem da senha) |
| `docker compose -f infra/docker-compose.dev.yml down` e depois `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres` | `Container platform-postgres-1  Healthy` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example ps --format '{{.Ports}}' postgres` | `127.0.0.1:5432->5432/tcp`, sem `0.0.0.0` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example exec -T postgres psql -U platform_admin -d ml -tAc "select 1"` | `1` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example exec -T postgres psql -U platform_admin -d ml -tAc "show password_encryption"` | `scram-sha-256` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example exec -T postgres psql -U platform_admin -d ml -tAc "select count(*) from pg_hba_file_rules where type like 'host%' and auth_method <> 'scram-sha-256'"` | `0` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example down -v` | Container e volume `platform_pgdata` removidos |
| `shellcheck infra/scripts/tailscale-serve.sh` (se instalado localmente; senão, o passo do CI) | Sem saída |
| `gh pr checks` | Verde, incluindo o job `compose-smoke` |

## 7. Testes necessários

`sim`: a exposição de porta do banco e o método de autenticação são o maior risco de segurança da fase; os testes de YAML e do script impedem regressão em todo PR futuro.

## 8. Casos de teste

Todos leem `infra/docker-compose.yml` (não o de dev), salvo onde dito.

1. O serviço `postgres` existe e publica exatamente uma porta, com porta de host 5432, porta de container 5432 e IP de host `${POSTGRES_BIND_IP:-127.0.0.1}`. Entrada que deve reprovar (exemplo embutido): `${POSTGRES_BIND_IP}:5432:5432`, `5432:5432`, `0.0.0.0:5432:5432`, `127.0.0.1:15432:5432`. (A allow-list `PORT_PUBLISHING_SERVICES` já contém `postgres`; não precisa mexer nela.)
2. `postgres` monta um volume nomeado (não bind mount, isto é, a origem não começa com `./`, `../` nem `/`) em `/var/lib/postgresql/data`, e esse nome está declarado no `volumes:` de topo. Reprova: `./pgdata:/var/lib/postgresql/data`, `/srv/pg:/var/lib/postgresql/data`, volume nomeado não declarado no topo.
3. `postgres` tem `healthcheck` com `test` não vazio.
4. `POSTGRES_PASSWORD` do `postgres` vem de `${...}` (regra geral de segredos, já existente; deve continuar passando).
5. A tag da imagem de `postgres` é igual em `infra/docker-compose.yml` e `infra/docker-compose.dev.yml`, e é uma tag fixa com minor (`16.15`, não `16` nem `latest`).
6. Toda referência `${VAR}` ou `${VAR:?...}` (sem default `:-`) em `infra/docker-compose.yml` tem `VAR` declarada em `infra/.env.example` (caso geral: vale para serviços futuros). Exemplo embutido: compose com `${A}`, `${B:?x}` e `${C:-y}` e `.env.example` só com `A` → falta `B`; `C` não é exigida. `$${POSTGRES_USER}` (escape) não conta como referência.
7. Script do `tailscale serve` (`tests/infra/test_tailscale_serve.py`):
   - Toda linha `tailscale serve ... --tcp=<p> tcp://127.0.0.1:<q>` tem `p == q`, e o conjunto dessas portas é igual ao conjunto de portas publicadas em loopback pelo `postgres` de `infra/docker-compose.yml` **apenas** (o compose de dev também publica 5432 e não pode fazer o teste passar sozinho). Hoje o resultado esperado é `{5432}` nos dois lados.
   - Reprova (exemplos embutidos): linha `--tcp=15432 tcp://127.0.0.1:5432`; linha `--tcp=5432 tcp://0.0.0.0:5432`; script sem linha `--tcp` com compose publicando 5432; linha `--tcp=6000` sem serviço correspondente; linha `--tcp` comentada não conta.
   - `tailscale serve reset` vem antes de qualquer linha de mapeamento, seja `--https` ou `--tcp` (reprova: reset depois de uma linha `--tcp`).
   - O mapeamento `--https` existente continua só com as UIs (saúde hoje); uma linha `--tcp` não é contada como UI.
   - `POSTGRES_BIND_IP` em `infra/.env.example` vale exatamente `127.0.0.1` (a regra geral aceita a faixa do Tailscale; a P15 exige loopback para o Postgres).
8. Autenticação: no `environment` do `postgres`, `POSTGRES_HOST_AUTH_METHOD` vale `scram-sha-256` e `POSTGRES_INITDB_ARGS` contém `--auth-host=scram-sha-256`; nenhum valor do `environment` contém `trust` nem `md5`. Reprova: `POSTGRES_HOST_AUTH_METHOD` ausente, `trust` ou `md5`; `POSTGRES_INITDB_ARGS` ausente.

## 9. Riscos e perguntas em aberto

Perguntas para o usuário (decidir antes do passo 2):

1. **Socket local `trust` ou senha?** Recomendação: manter `local` em `trust` (padrão da imagem), porque só quem já tem `docker exec` no host chega nele, e os critérios de pronto e o item 12 (`exec postgres psql -U <admin>`) dependem disso. A alternativa (`--auth-local=scram-sha-256`) exige `PGPASSWORD` em todo `exec` e muda o checklist do item 12. O revisor pediu `scram-sha-256`; confirme se isso vale só para conexões TCP (este plano) ou também para o socket.
2. **Como editar `infra/.env.example`.** O deny de `Read` bloqueia Edit/Write nesse arquivo para o agente. Opções: (a) o implementador anexa as linhas pelo Bash sem ler o arquivo (recomendado, passo 4); (b) o usuário cola o conteúdo atual e o implementador reescreve; (c) o usuário edita à mão e commita na branch. Diga qual.
3. **Nome do admin.** `platform_admin` é o valor fictício do `.env.example`; o real fica no `infra/.env` da VPS (item 12). Confirme que o admin não é `postgres` (a imagem cria `POSTGRES_USER` como superusuário e não cria `postgres` quando ele é diferente).

Riscos:

- Com `tailscale serve --tcp`, toda conexão da tailnet chega ao container vinda do gateway da rede do Docker (o `tailscaled` repassa para `127.0.0.1` do host, e o Docker repassa ao container). O `pg_hba.conf` não distingue clientes; o controle de rede é só a ACL do Tailscale (item 12), e o controle por pessoa é a senha de cada papel.
- `POSTGRES_INITDB_ARGS` e `POSTGRES_HOST_AUTH_METHOD` só valem quando o volume está vazio. Se alguém subir o `postgres` antes deste PR com outro `pg_hba`, o volume precisa ser recriado (na VPS ainda não há volume: o item 12 é o primeiro `up`). O critério com `pg_hba_file_rules` pega isso.
- `docker compose ... down -v` apaga `platform_pgdata`. Só no CI e em teste local. Não há backup até o PR 57: até lá, perder o volume na VPS é perder os dados (os jobs de ingestão são reprocessáveis, mas o histórico de previsões do item 17 não é).
- `mem_limit: 256m` com `shared_buffers` padrão (128 MB): cabe pela estimativa de 100–250 MB, mas é estimativa. Se o container for morto por OOM no item 12 ou 17, aumentar o limite é a primeira resposta; a medição oficial é o 28a. `shm_size` padrão (64 MB) basta para consultas pequenas.
- Sintaxe do `tailscale serve --tcp` pode variar entre versões do CLI; confirmação real só no item 12. Se o reboot do item 12 exigir rodar o script de novo, devolva para o planejamento.
- Local (Windows, Docker Desktop): o compose de dev usa a mesma porta 5432; pare-o antes dos critérios com `up`, e suba-o de novo depois para a suíte completa.

## 10. Decisões que exigem ADR

Nenhum ADR novo. A exposição do Postgres em `127.0.0.1:5432` com `tailscale serve --tcp=5432` está coberta explicitamente pelo ADR 0003 (`docs/adr/0003-tailscale-only-network.md`: linha "Postgres" da tabela de mapeamento e seção "Postgres (P15)"). Os nomes seguem o ADR 0001. A escolha de `scram-sha-256` é configuração dentro dessa decisão, não mudança estrutural.

## Notas da revisão (2026-11-07)

Mudanças em relação à versão anterior deste plano, para conferir contra a `main` em `be56c94`:

- Porta: `${POSTGRES_BIND_IP}` sem default seria reprovada por `is_acceptable_port`; passa a `${POSTGRES_BIND_IP:-127.0.0.1}`.
- Allow-list: `postgres` já está em `PORT_PUBLISHING_SERVICES`; o caso 1 não pede mais para acrescentá-lo.
- Script: a regex do teste só via `--https`; o caso 7 agora define a checagem `--tcp` ↔ compose (só o compose de produção) e o reset antes de linhas `--tcp`.
- Autenticação `scram-sha-256` (pedido do revisor) e caso 8 novos; esclarecido que "só loopback" é no host, não no `listen_addresses`.
- Imagem fixada em `postgres:16.15`; `:?` nas variáveis obrigatórias; healthcheck com `$$`.
- CI: a opção `127.0.0.2` não funciona com o service container em `0.0.0.0:5432`; fica só o job separado `compose-smoke`.
- Senhas dos papéis e backups explicitamente fora do escopo.
