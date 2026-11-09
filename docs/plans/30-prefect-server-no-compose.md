# 30 — Prefect server no compose, só em loopback e na tailnet, com a API autenticada

> Executa: agente. Depende de: 29 na `main` (padrão de UI em loopback + `tailscale serve`, passos do `compose-smoke`) e 28 (banco `prefect`). Branch: `feat/compose-prefect`.
> TDD: passo 0 (verificação, sem código) → test-writer (vermelho) → implementação mínima (verde) → refatorar com a suíte verde.
> Revisão 2026-11-08 (v2, com a revisão independente aceita pelo usuário). Em relação ao rascunho: imagem por `tag@sha256:` do índice (ADR 0006); passo 0 de verificação; não-root com `PREFECT_HOME` gravável; telemetria desligada; `cap_drop` e `no-new-privileges`; teto de `mem_limit`; checagens de `/ui-settings` e de consulta real no CI. Na v2: nomes atuais das settings (`PREFECT_SERVER_DATABASE_CONNECTION_URL`, `PREFECT_SERVER_UI_API_URL`, `PREFECT_SERVER_DATABASE_SQLALCHEMY_POOL_SIZE`/`_MAX_OVERFLOW`); healthcheck em `/api/ready`; imagem com versão completa `X.Y.Z-python3.12` e regex ancorada; pool 3 + 2; **autenticação da API** (`PREFECT_SERVER_API_AUTH_STRING` a partir de `PREFECT_API_AUTH` do `.env`) com allow-list de variáveis por serviço; migração automática na subida exige `pg_dump` antes de aplicar troca de imagem; flags de serviços internos como alavanca de memória; `curl` da UI no CI. Alinhamento entre planos (mesmo dia): os clientes da API entram no compose só no PR 34 (`jobs` e `prefect-worker`); o registro de deployments no deploy automático roda na VPS pelo `jobs`, com a credencial do `infra/.env`, sem GitHub Secret. Revisão final (mesmo dia): comportamento verificado no código-fonte do Prefect — o middleware de autenticação só cobre o app montado em `/api` e isenta `GET /api/health` e `GET /api/ready`; `/ui-settings` e `/` não são autenticados. O passo 0 confirma na versão fixada, e o CI não afirma autenticação em `/ui-settings`.

## 1. Objetivo

Subir o Prefect 3 server (API, UI e serviços internos de agendamento) no compose de produção, com backend no banco `prefect` (papel `prefect`) e a API protegida por autenticação básica, publicado só em `127.0.0.1:4200` e exposto na tailnet por `tailscale serve` (`https://<host>.<tailnet>.ts.net:4200`).
É onde as ingestões vão ser agendadas (PRs 32 a 36) e onde se veem histórico, logs e tracebacks.

## 2. Fora do escopo

- Worker e work pool (PR 34), flows (PR 32), deployments (PR 33); `prefect` no `pyproject.toml` (PR 32). Os clientes da API passam a precisar de `PREFECT_API_AUTH_STRING`: o PR 33 no registro local (variável de ambiente) e o PR 34 no compose (`jobs` e `prefect-worker`) (seção 9, "Dependências").
- Deploy na VPS, ACL e acesso da cientista (item 31).
- Automações e alertas do Prefect (PR 55).
- Separar os serviços internos em outro container (`--no-services`): só se a memória exigir (pergunta já respondida, seção 9).

## 3. Fase do roadmap

Fase 3 — "MLflow e Prefect no compose, só na tailnet (`tailscale serve`)". Do doc: "Prefect 3 (server + worker) | Agenda e executa os jobs; UI com histórico de execuções e logs | Os dois". Do guia da cientista: "Prefect (só a interface) | Ver se o job do seu modelo rodou e ler o erro | Só leitura".

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/infra/test_compose.py` | test-writer | Casos 1 a 18 (seção "plan 30"); `PORT_PUBLISHING_SERVICES` ganha `prefect-server` |
| `tests/infra/test_tailscale_serve.py` | test-writer | Caso 19 |
| `tests/infra/test_dependabot.py` | test-writer | Caso 20 |
| `infra/docker-compose.yml` | implementer | Serviço `prefect-server` |
| `infra/.env.example` | implementer, anexando pelo Bash sem ler | `PREFECT_API_AUTH` fictício |
| `infra/scripts/tailscale-serve.sh` | implementer | Linha `--https=4200` |
| `.github/dependabot.yml` | implementer | `ignore` de major do Prefect no bloco `docker-compose` |
| `.github/workflows/ci.yml` | implementer | Passos do Prefect no `compose-smoke` |
| `AGENTS.md` | implementer | Verificação local da API |

Não há Dockerfile novo: a imagem oficial traz o `asyncpg` (o passo 0 confere).

### Contexto que o implementador precisa

- Depois do PR 29, o compose tem `mlflow` (com `cap_drop`, `no-new-privileges`, teto de `mem_limit`, `127.0.0.1:5000:5000`) e o `compose-smoke` tem os passos do `create-databases` (PR 28) e do MLflow. O `tailscale-serve.sh` tem 8080, 5000 e `--tcp=5432`.
- `tests/infra/test_compose.py` já tem a allow-list do plano 28: `{"MLFLOW_DB_PASSWORD": {"jobs", "mlflow"}, "PREFECT_DB_PASSWORD": {"jobs", "prefect-server"}}`. A checagem geral de segredo (`SECRET_KEY_MARKERS = ("PASSWORD", "SENHA", "TOKEN", "SECRET", "HASH")`) **não** pega a chave `PREFECT_SERVER_API_AUTH_STRING`; acrescentar `"AUTH"` à lista geral quebraria `POSTGRES_HOST_AUTH_METHOD: scram-sha-256` (literal legítimo do `postgres`). Por isso o caso 11 é específico.
- `tests/infra/test_tailscale_serve.py`: `UI_SERVICES = ("health", "mlflow", "prefect-server", "grafana")`.
- `tests/infra/test_supply_chain_pins.py`: imagem de terceiro como `<nome>:<tag>@sha256:<64 hex>`; `ci.yml` com exatamente 3 `uses:` e 2 `actions/checkout`.
- `.github/dependabot.yml`: o bloco `docker-compose` (diretório `/infra`) já atualiza imagens do compose, com `ignore` de major do `postgres`; `test_dependabot.py` exige esse `ignore`.
- Regras: `.claude/rules/infra.md` (restart, `mem_limit`, Prefect só em `127.0.0.1` + `tailscale serve`, imagens por digest do índice, nenhum `${{ }}` em `run:`, zizmor antes de commitar). ADR 0003: "Prefect | `127.0.0.1:4200` | `https://<host>.ts.net:4200`". ADR 0001: serviço `prefect-server`; variáveis `PREFECT_*` em inglês, sem mudança.
- `infra/.env.example` já declara `TS_HOSTNAME` (plano 03) e `PREFECT_DB_PASSWORD` (plano 28); este plano não leu o arquivo.
- **Comportamento da autenticação (verificado no código-fonte do Prefect 3 na revisão final; o passo 0 confirma na versão fixada):** com `PREFECT_SERVER_API_AUTH_STRING` definida, o middleware de autenticação básica só é aplicado ao app montado em `/api`, e isenta `GET /api/health` e `GET /api/ready`. Fora de `/api`, `GET /ui-settings` e a UI (`GET /`) não são autenticados (a UI pede a credencial no navegador e a manda nas chamadas à API). Toda outra rota de `/api` sem credencial responde `401`.

### Decisões (aceitas pelo usuário em 2026-11-08)

| Id | Decisão |
| --- | --- |
| D1 | Imagem `prefecthq/prefect:<X.Y.Z>-python3.12@sha256:<índice>`: a última 3.x estável publicada há pelo menos 7 dias (a revisão de 2026-11-08 indicou `3.9.1`; o passo 0 confirma). O PR 32 põe a mesma versão no `pyproject.toml` e o PR 34 usa a mesma versão no worker (pelo pacote `prefect` da imagem `jobs`) |
| D2 | Não-root (`user: "10001:10001"`) com `PREFECT_HOME: /tmp/prefect`; se o CI mostrar que não funciona, root registrado no PR |
| D3 | Porta `127.0.0.1:4200:4200` literal |
| D4 | `mem_limit: 640m` **só para o server** (o worker do PR 34 tem o seu, `768m`); pool 3 + 2 (abaixo do `CONNECTION LIMIT 20`); telemetria desligada |
| D5 | `cap_drop: [ALL]`, `security_opt: ["no-new-privileges:true"]` |
| D6 | URL da API na UI: `https://${TS_HOSTNAME}:4200/api` |
| D7 | API autenticada: variável `PREFECT_API_AUTH` no `infra/.env`, formato `admin:<senha>` com a senha de `openssl rand -hex 24`; no server vira `PREFECT_SERVER_API_AUTH_STRING`; nos clientes vira `PREFECT_API_AUTH_STRING` (`jobs` e `prefect-worker` no PR 34; registro local no PR 33). O deploy automático (PR 39) registra os deployments na VPS pelo `jobs`, com a mesma credencial do `infra/.env`. `/api/health` e `/api/ready` ficam fora da autenticação (comportamento do Prefect), o que permite checagens de saúde sem credencial |
| D8 | Dependabot: atualiza minor e patch do Prefect; major é manual (`ignore`) |

## 5. Passos

0. **(implementer, sem commit; antes do test-writer)** Confira e devolva a saída ao coordenador; divergência volta ao planner antes do test-writer.

   ```bash
   docker buildx imagetools inspect prefecthq/prefect:<X.Y.Z>-python3.12
   IMG=prefecthq/prefect:<X.Y.Z>-python3.12@sha256:<índice>
   docker run --rm $IMG prefect version
   docker run --rm $IMG sh -c 'id -u; python --version'
   docker run --rm $IMG python -c "import asyncpg; print(asyncpg.__version__)"
   docker run --rm $IMG prefect server start --help
   docker run --rm $IMG prefect config view --show-defaults
   ```

   Anote: digest do índice e `linux/amd64` presente; versão; usuário padrão; `asyncpg` importa; opções `--host`, `--port`, `--no-services`; e, no `config view` (sem variável definida, então sem segredo), os nomes exatos de: URL do banco (`PREFECT_SERVER_DATABASE_CONNECTION_URL`), URL da API na UI (`PREFECT_SERVER_UI_API_URL`), telemetria (`PREFECT_SERVER_ANALYTICS_ENABLED`), pool (`PREFECT_SERVER_DATABASE_SQLALCHEMY_POOL_SIZE`, `PREFECT_SERVER_DATABASE_SQLALCHEMY_MAX_OVERFLOW`), timeouts do banco (`PREFECT_SERVER_DATABASE_TIMEOUT`, `PREFECT_SERVER_DATABASE_CONNECTION_TIMEOUT`), `PREFECT_HOME`, autenticação (`PREFECT_SERVER_API_AUTH_STRING`), migração na subida (`PREFECT_SERVER_DATABASE_MIGRATE_ON_START`) e as flags de serviços internos (`PREFECT_SERVER_SERVICES_<NOME>_ENABLED`). Suba um container de teste contra um Postgres descartável, com a autenticação ligada, e confirme o comportamento descrito em "Comportamento da autenticação": `GET /api/health` e `GET /api/ready` **sem** credencial respondem `200`; `POST /api/flows/filter` sem credencial dá `401` e com credencial dá `200` e `[]`; `GET /ui-settings` sem credencial dá `200` com o campo `api_url`; `GET /` sem credencial devolve a UI (`200`, HTML); e como a UI pede a credencial (o valor inteiro `admin:<senha>` ou só a senha). Se a versão fixada se comportar diferente, registre no corpo do PR e ajuste o passo 6: os planos 28b, 31 e 39 usam esse comportamento.
1. (test-writer) Casos da seção 8 com os nomes confirmados. Confirme a falha. Commit: `test: add prefect server compose tests`.
2. (implementer) `infra/docker-compose.yml`:

   ```yaml
     prefect-server:
       image: prefecthq/prefect:<X.Y.Z>-python3.12@sha256:<digest do índice>
       command: ["prefect", "server", "start", "--host", "0.0.0.0", "--port", "4200"]
       restart: unless-stopped
       mem_limit: 640m
       user: "10001:10001"
       cap_drop: [ALL]
       security_opt: ["no-new-privileges:true"]
       environment:
         PREFECT_SERVER_DATABASE_CONNECTION_URL: postgresql+asyncpg://prefect:${PREFECT_DB_PASSWORD:?PREFECT_DB_PASSWORD is required}@postgres:5432/prefect
         PREFECT_SERVER_DATABASE_SQLALCHEMY_POOL_SIZE: "3"
         PREFECT_SERVER_DATABASE_SQLALCHEMY_MAX_OVERFLOW: "2"
         PREFECT_SERVER_UI_API_URL: https://${TS_HOSTNAME:?TS_HOSTNAME is required}:4200/api
         PREFECT_SERVER_API_AUTH_STRING: ${PREFECT_API_AUTH:?PREFECT_API_AUTH is required}
         PREFECT_SERVER_ANALYTICS_ENABLED: "false"
         PREFECT_HOME: /tmp/prefect
       ports:
         - "127.0.0.1:4200:4200"
       healthcheck:
         test: ["CMD", "python", "-c", "import base64, os, sys, urllib.request; token = base64.b64encode(os.environ['PREFECT_SERVER_API_AUTH_STRING'].encode()).decode(); request = urllib.request.Request('http://127.0.0.1:4200/api/ready', headers={'Authorization': 'Basic ' + token}); sys.exit(urllib.request.urlopen(request, timeout=5).status != 200)"]
         interval: 30s
         timeout: 10s
         retries: 5
         start_period: 180s
       depends_on:
         postgres:
           condition: service_healthy
   ```

   O healthcheck manda a credencial mesmo com `/api/ready` isento (continua funcionando se uma versão futura deixar de isentá-lo) e a lê do ambiente do container, sem `$` no compose. O `--host 0.0.0.0` é dentro do container. A migração do banco na subida é o padrão do Prefect (ver risco "Troca de imagem").
3. (implementer) `infra/.env.example`, sem abrir o arquivo:

   ```bash
   printf '%s\n' '' '# Prefect API basic auth, user:password (plan 30). Fake value.' '# Real value: printf "admin:%s" "$(openssl rand -hex 24)"' 'PREFECT_API_AUTH=admin:change-me-prefect-auth' >> infra/.env.example
   ```

   O valor fictício `admin:change-me-prefect-auth` é o que os planos 33 e 34 usam nos comandos locais.
4. (implementer) `infra/scripts/tailscale-serve.sh`: depois da linha da 5000, `tailscale serve --bg --https=4200 http://127.0.0.1:4200`.
5. (implementer) `.github/dependabot.yml`, bloco `docker-compose`, acrescente ao `ignore` existente:

   ```yaml
         # A Prefect major changes the API and the database; upgrade by hand with plan 30's procedure
         - dependency-name: prefecthq/prefect
           update-types: ["version-update:semver-major"]
   ```

   Se o Dependabot propuser tags que não são de release (pré-release, variantes como `-kubernetes`), acrescente um `ignore` por `versions` para elas e registre no PR. Valide com `uvx --from check-jsonschema==0.39.0 check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml`.
6. (implementer) `.github/workflows/ci.yml`, job `compose-smoke`, depois dos passos do MLflow e antes do `if: always()` final; só `run:`:

   ```yaml
         - run: $COMPOSE pull prefect-server
         - run: $COMPOSE up -d --wait --wait-timeout 300 prefect-server
         - name: Check the Prefect API requires credentials
           run: |
             code="$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:4200/api/flows/filter)"
             echo "without credentials: $code"
             test "$code" = 401
         - name: Check Prefect is ready, serves the UI and reads its database
           run: |
             curl -fsS http://127.0.0.1:4200/api/ready
             curl -fsS http://127.0.0.1:4200/ui-settings | grep -E '"api_url": ?"https://[^"]+\.ts\.net:4200/api"'
             curl -fsS http://127.0.0.1:4200/ | grep -qi '<html'
             auth="$(grep '^PREFECT_API_AUTH=' infra/.env.example | cut -d= -f2-)"
             test "$(curl -fsS -u "$auth" -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:4200/api/flows/filter)" = "[]"
         - name: Check Prefect is published only on 127.0.0.1
           run: |
             ports="$($COMPOSE ps --format '{{.Ports}}' prefect-server)"
             echo "$ports"
             echo "$ports" | grep -F '127.0.0.1:4200->4200/tcp'
             if echo "$ports" | grep -E '0\.0\.0\.0|\[::\]|:::'; then exit 1; fi
         - name: Check Prefect runs as a non-root user
           run: test "$($COMPOSE exec -T prefect-server id -u)" != 0
         - name: Check Prefect logs have no connection-limit errors
           run: |
             if $COMPOSE logs prefect-server | grep -iE 'too many connections|connection limit exceeded'; then exit 1; fi
         - name: Report Prefect image size, memory and connections (informational)
           run: |
             docker image ls prefecthq/prefect --format '{{.Repository}}:{{.Tag}} {{.Size}}'
             docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'
             $COMPOSE exec -T postgres psql -U platform_admin -d ml -tAc "select datname, usename, count(*) from pg_stat_activity where datname in ('mlflow', 'prefect') group by 1, 2 order by 1, 2"
   ```

   `/api/ready`, `/ui-settings` e `/` vão sem credencial (comportamento descrito no contexto; o passo 0 confirma). A credencial do CI é o valor **fictício** do `.env.example`, usado só na consulta autenticada (o `ci.yml` continua sem `secrets.`). Antes de commitar: `uv run zizmor .github/workflows/`.
7. (implementer) `AGENTS.md`, "Comandos": `- Prefect (na VPS): \`curl -fsS http://127.0.0.1:4200/api/ready\` (sem credencial; o resto da API pede a \`PREFECT_API_AUTH\`)`. UTF-8.
8. Rode os critérios da seção 6 e refatore com a suíte verde.

### Troca de imagem do Prefect (documentado aqui; aplicado em PR futuro)

O Prefect migra o banco sozinho na subida (padrão). Uma migração que falha no meio deixa o banco num estado intermediário. Por isso, antes de aplicar na VPS qualquer PR (inclusive do Dependabot) que troque a imagem do `prefect-server`, fora da janela 06:25–07:15:

1. `dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d prefect -Fc' > "$HOME/backups/prefect-$(date +%F).dump"`.
2. `dc pull prefect-server` e `dc up -d --wait prefect-server`.
3. `dc logs --since 10m prefect-server | grep -iE 'migrat|error'` e `curl -fsS http://127.0.0.1:4200/api/ready`.

**Nota para o plano 39 (deploy via SSH):** o deploy automático faz o `pg_dump` do banco `prefect` antes de trocar a imagem do server (aplicado no plano 39, D13).

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `uv run pytest` | Suíte verde (com o Postgres de teste no ar) |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem achados |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Sem saída, código 0 |
| `uvx --from check-jsonschema==0.39.0 check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml` | `ok -- validation done` |
| `uv run zizmor .github/workflows/` | Sem achados |
| `gh pr checks` | `lint-and-test` e `compose-smoke` verdes; no log: `without credentials: 401`, a linha `api_url` com `.ts.net:4200/api`, `127.0.0.1:4200->4200/tcp`, tamanho da imagem, memória do `platform-prefect-server-1` e conexões por banco (copie para a descrição do PR); `security.yml` sem achado novo |

Não suba o compose de produção localmente (colide com o Postgres de teste na 5432).

## 7. Testes necessários

`sim`: exposição, autenticação da API, credencial só do papel `prefect`, pin da imagem e política de atualização; regressão é cara e silenciosa (sem autenticação, qualquer acesso dispara e cancela execuções).

## 8. Casos de teste

Compose (`tests/infra/test_compose.py`, seção "plan 30"):

1. `prefect-server` sem `profiles`, com `restart: unless-stopped`.
2. `mem_limit` presente e no máximo 640 MiB (rejeita `1g`, `700m`, ausente).
3. `ports` exatamente `["127.0.0.1:4200:4200"]`. Negativos: `"4200:4200"`, `"0.0.0.0:4200:4200"`, `"${PREFECT_BIND_IP}:4200:4200"`.
4. `image` casa com `^prefecthq/prefect:3\.\d+\.\d+-python3\.12@sha256:[0-9a-f]{64}$`. Negativos: `prefecthq/prefect:3-latest`, `prefecthq/prefect:3.9-python3.12@sha256:...` (versão incompleta), `prefecthq/prefect:3.9.1-python3.12` (sem digest), `-python3.11`, `2.20.0-python3.12@sha256:...`, `3.9.1-python3.12-kubernetes@sha256:...`.
5. `PREFECT_SERVER_DATABASE_CONNECTION_URL` casa com `^postgresql\+asyncpg://prefect:\$\{PREFECT_DB_PASSWORD(:\?[^}]*)?\}@postgres:5432/prefect$`. Negativos: usuário admin, senha literal, banco `ml`, sem `+asyncpg`.
6. Pool `PREFECT_SERVER_DATABASE_SQLALCHEMY_POOL_SIZE` e `..._MAX_OVERFLOW` definidos, com soma no máximo 5.
7. `PREFECT_SERVER_UI_API_URL` é `https://${TS_HOSTNAME...}:4200/api`. Negativos: `http://`, `localhost`, porta diferente, sem `/api`.
8. `PREFECT_SERVER_ANALYTICS_ENABLED` é `"false"`.
9. `command` é `prefect server start --host 0.0.0.0 --port 4200` (sem `--no-services`).
10. `PREFECT_SERVER_API_AUTH_STRING` presente e igual a uma única referência `${PREFECT_API_AUTH...}`.
11. Em **qualquer** serviço, toda chave de ambiente que termine em `AUTH_STRING` tem valor que é uma única referência `${...}`. Negativos embutidos: `{"PREFECT_SERVER_API_AUTH_STRING": "admin:hunter2"}`, `{"PREFECT_API_AUTH_STRING": "${A}x"}`, a forma em lista `["PREFECT_API_AUTH_STRING=admin:x"]`. Positivo embutido: `POSTGRES_HOST_AUTH_METHOD: scram-sha-256` não é afetado.
12. Allow-list de variáveis por serviço, estendida: `PREFECT_DB_PASSWORD` → `{"jobs", "prefect-server"}`; `PREFECT_API_AUTH` → `{"prefect-server"}` (o PR 34 acrescenta `jobs` e `prefect-worker`); `MLFLOW_DB_PASSWORD` → `{"jobs", "mlflow"}`. Negativos: `mlflow` com `PREFECT_API_AUTH`; `scheduler` com `PREFECT_API_AUTH`.
13. `PREFECT_API_AUTH` é obrigatória (`required_variables`) e declarada no `infra/.env.example`, com valor no formato `<usuário>:<senha>` (contém exatamente um `:`, usuário e senha não vazios).
14. O serviço não referencia `ADMIN` (variáveis do Postgres), `POSTGRES_INGESTOR_PASSWORD` nem `MLFLOW_DB_PASSWORD`.
15. `user` não é root (`0`, `root`, ausente reprovam).
16. `healthcheck.test` aponta para `/api/ready` na 4200 e manda `Authorization`; `depends_on.postgres.condition` é `service_healthy`.
17. `cap_drop` contém `ALL` e `security_opt` contém `no-new-privileges:true`.
18. `PORT_PUBLISHING_SERVICES` passa a `{"health", "postgres", "mlflow", "prefect-server"}`; `scheduler` fora; regras gerais verdes (variáveis declaradas; imagem por digest em `test_supply_chain_pins.py`).

Script (`tests/infra/test_tailscale_serve.py`):

19. Exatamente uma linha `--https=4200 http://127.0.0.1:4200`; a correspondência compose ↔ script inclui 8080, 5000 e 4200.

Dependabot (`tests/infra/test_dependabot.py`):

20. O bloco `docker-compose` tem `ignore` de `prefecthq/prefect` com `version-update:semver-major`, além do `ignore` do `postgres` (o teste existente segue verde).

## 9. Riscos e perguntas em aberto

Riscos:

- **Sem papéis de usuário no Prefect OSS:** com a autenticação básica, quem tem a credencial pode tudo (disparar, cancelar, apagar). "Só leitura" para a cientista não existe; por isso a 4200 não é liberada a ela no item 31.
- **Endpoints fora da autenticação:** `GET /api/health`, `GET /api/ready`, `GET /ui-settings` e a UI estática respondem sem credencial a quem a ACL deixar chegar à 4200. Expõem só saúde, a URL da API e o HTML da UI; nenhum dado de flow. Aceito; a ACL continua sendo a primeira barreira.
- **Credencial no navegador e nos clientes:** a UI pede a credencial; worker e `jobs` (que registra os deployments) precisam dela. Trocar a senha exige atualizar o `.env` e recriar server e clientes juntos.
- **WebSocket pelo `tailscale serve`:** a UI usa WebSocket para eventos; o item 31 confere no navegador. Se falhar, a UI funciona sem atualização ao vivo; correção é PR.
- **Memória:** API, UI e serviços internos no mesmo processo. Alavancas, se o item 31 apertar: desligar serviços internos não usados com `PREFECT_SERVER_SERVICES_<NOME>_ENABLED=false` (ex.: `PREFECT_SERVER_SERVICES_TRIGGERS_ENABLED`, se não houver automações; as automações do PR 55 precisam dele), baixar o pool, separar serviços com `--no-services`. Os timeouts do banco (`PREFECT_SERVER_DATABASE_TIMEOUT`, `..._CONNECTION_TIMEOUT`) são o ajuste se a VPS lenta gerar erros de timeout.
- **Troca de imagem migra o banco na subida:** procedimento da seção 5 (`pg_dump` antes); aplicado no deploy automático pelo plano 39.
- **Primeira subida lenta:** `start_period: 180s` e `--wait-timeout 300` no CI.
- **Fuso horário:** o Prefect guarda UTC; as agendas do PR 33 declaram `America/Sao_Paulo`.
- **Não verificado por execução nesta revisão** (os nomes vieram da revisão independente com acesso à web e do código-fonte; o passo 0 confere localmente): digest e plataformas, versão `3.9.1`, `asyncpg` na imagem, usuário padrão, nomes das settings, a isenção de `/api/health` e `/api/ready` e a ausência de autenticação em `/ui-settings` e `/` na versão fixada, `POST /api/flows/filter`, formato da credencial na UI, `pg_trgm`.

Dependências que este PR cria (já registradas nos planos seguintes):

- **Plano 33 (deployments):** o registro local precisa de `PREFECT_API_AUTH_STRING` no ambiente, com o valor de `PREFECT_API_AUTH` do `.env.example` (`admin:change-me-prefect-auth`).
- **Plano 34 (worker):** `PREFECT_API_AUTH_STRING: ${PREFECT_API_AUTH:?...}` no `prefect-worker` e no `jobs`, que entram na allow-list do caso 12.
- **Plano 39 (deploy via SSH):** o registro de deployments roda na VPS pelo `jobs` (credencial do `infra/.env`, sem GitHub Secret); o `pg_dump` do banco `prefect` vem antes de trocar a imagem; a checagem de saúde do Prefect manda a credencial mesmo com `/api/health` isento (D14 de lá).
- **Planos 28b e 31:** as checagens de saúde do Prefect usam `/api/ready` sem credencial.
- **Plano 55 (alertas):** não desligar `PREFECT_SERVER_SERVICES_TRIGGERS_ENABLED`.

Recomendações aceitas pelo usuário (registradas): D1 a D8; não liberar a 4200 à cientista no item 31 (só na Fase 4, item 50); autenticação da API já neste PR; separar serviços só se a memória exigir.

## 10. Decisões que exigem ADR

**Nenhuma.** Exposição pelo ADR 0003 (4200 já na tabela dele) e pin pelo ADR 0006; a autenticação básica acrescenta uma camada sem mudar a rede (e é registrada no ADR "Agendamento e execução pelo Prefect", do plano 33).

Exigiriam ADR (sinalizar, não escrever): 4200 fora de `127.0.0.1` ou `tailscale funnel`; trocar o Prefect por outro orquestrador; Prefect Cloud no lugar do server.
