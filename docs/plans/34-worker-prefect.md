# 34 — Worker do Prefect no compose

> Executa: agente. Depende de: 33 (deployments e `POOL` na `main`), 30 (serviço `prefect-server` com a API autenticada, D7 do plano 30) e do **ADR obrigatório** "Agendamento e execução pelo Prefect" (plano 33, seção 10), mergeado antes deste PR. Branch sugerida: `feat/compose-prefect-worker` (ADR 0001).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-08: reescrito contra a `main` em `05c32c9`: `infra/docker-compose.yml` com `health`, `postgres`, `scheduler` (supercronic, `mem_limit: 512m`, só o `DATABASE_URL` do `ingestor`) e `jobs` (profile `jobs`, também com `DATABASE_URL_ADMIN`); testes de política em `tests/infra/test_compose.py` (inclusive `admin_credential_problems`, reaproveitado aqui); `compose-smoke` no `.github/workflows/ci.yml`. Revisão 2 (mesmo dia): aplica a revisão independente aceita pelo usuário. Inclui o risco de API sem autenticação (com `PREFECT_API_AUTH_STRING` no worker, no `jobs` e no CI), a soma dos `mem_limit` contra a RAM real, `--watch-timeout` no CI, `PREFECT_WORKER_WEBSERVER_HOST=127.0.0.1`, o alinhamento com o digest do plano 37 e o comando que cria o banco `prefect`. Revisão 3 (alinhamento entre planos): a variável do `infra/.env` é `PREFECT_API_AUTH` (a mesma do plano 30); dentro dos containers clientes ela vira `PREFECT_API_AUTH_STRING`; posição dos passos no `compose-smoke` depois dos do PR 30. Revisão final (mesmo dia): os critérios que sobem o compose de produção são **somente CI** (`compose-smoke`); nada de `up` local sem autorização do usuário (colide com o Postgres de teste na 5432).

## 1. Objetivo

Subir no compose um serviço `prefect-worker` de longa duração (work pool `platform`, tipo `process`, uma execução por vez), na mesma imagem dos jobs e com o mínimo de privilégio: só o `DATABASE_URL` do `ingestor`, a URL interna da API e a credencial da API.
Dar ao serviço `jobs` a URL e a credencial da API, para registrar deployments na VPS, e provar no CI que o worker pega uma execução e que a falha do job vira `Failed`.

## 2. Fora do escopo

- Registrar deployments ou ligar o worker em produção (item 35). Remover o `scheduler` (PR 36).
- Imagem no GHCR (PR 37) e deploy automático (PR 39).
- Credencial `scorer`, MLflow e variáveis do Telegram no worker (PRs 46 e 55).
- Mudar o `prefect-server` (PR 30), inclusive a autenticação do lado do server, ou as regras de porta.

## 3. Fase do roadmap

Fase 3 — "MLflow, Prefect e CI/CD", itens "MLflow e Prefect no compose, só na tailnet" e "Ingestões migradas para flows do Prefect".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/docker-compose.yml` | Serviço `prefect-worker`; `PREFECT_API_URL` e `PREFECT_API_AUTH_STRING` no `jobs` |
| `tests/infra/test_compose.py` (test-writer) | Seção "plan 34" com os casos da seção 8; allow-list de variáveis do plano 30 (caso 12 de lá) estendida |
| `.github/workflows/ci.yml` | Passos novos no job `compose-smoke` |
| `AGENTS.md` | Comandos do worker e do registro na VPS |

`infra/.env.example` não muda: `PREFECT_API_AUTH` já foi declarada pelo PR 30, com o valor fictício `admin:change-me-prefect-auth` (plano 30, passo 3), que é o que o `compose-smoke` usa.

### Contexto do repositório

Regras de `.claude/rules/infra.md` que valem aqui:

> Todo serviço do compose sem `profiles` tem `restart: unless-stopped`. [...] Todo serviço, com ou sem `profiles`, tem `mem_limit`.
> MLflow, Prefect e Grafana não têm autenticação adequada: só em `127.0.0.1`, expostos na tailnet por `tailscale serve`; a ACL do Tailscale é o controle de acesso (ADR 0003).
> Workflows (`.github/workflows/**`, ADR 0006): [...] nenhum `secrets.` no `ci.yml` [...]; nenhum `${{ }}` dentro de `run:` [...]; `if:` em uma linha só [...]. Antes de commitar mudança em workflow, rode `uv run zizmor .github/workflows/` e corrija os achados.

Serviço `scheduler` atual (modelo de serviço de longa duração com a imagem dos jobs):

```yaml
  scheduler:
    build:
      context: ..
      dockerfile: infra/jobs/Dockerfile
    command: ["supercronic", "/app/infra/cron/crontab"]
    restart: unless-stopped
    mem_limit: 512m
    environment:
      DATABASE_URL: postgresql+psycopg://ingestor:${POSTGRES_INGESTOR_PASSWORD:?POSTGRES_INGESTOR_PASSWORD is required}@postgres:5432/ml
    depends_on:
      postgres:
        condition: service_healthy
```

Funções de `tests/infra/test_compose.py` que o test-writer reaproveita: `ingestor_url_problems`, `database_url_credential_problems`, `admin_credential_problems` (nenhum `DATABASE_URL_ADMIN` e nenhuma ocorrência de `ADMIN` no serviço), `depends_on_postgres_problems`, `jobs_build_problems`, `scheduler_timezone_problems` (`TZ` ausente ou `America/Sao_Paulo`), `services_with_forbidden_ports`, `required_variables`, `undeclared_variables` e `ENV_REFERENCE`. `PORT_PUBLISHING_SERVICES` não ganha o worker. Atenção: `literal_secret_keys` só olha chaves com `PASSWORD`, `SENHA`, `TOKEN`, `SECRET` ou `HASH`, e `PREFECT_API_AUTH_STRING` não tem nenhum desses marcadores; o caso 11 do plano 30 (toda chave terminada em `AUTH_STRING` é uma única referência `${...}`) já cobre isso em qualquer serviço, e o caso 6 daqui reforça.

`flows/deployments.py` (PR 33): `POOL = "platform"`, `POOL_TYPE = "process"`, `POOL_CONCURRENCY_LIMIT = 1`, `WORKING_DIR = "/app"`. Na imagem (`infra/jobs/Dockerfile`), o usuário é `app` (uid 10001, com home), `WORKDIR /app` e `PATH` com `/app/.venv/bin`; não há `curl` (é removido no build).

`flows/ingest.py` (PR 32) fixa `logging.getLogger("ingestion").setLevel(logging.INFO)` no import. Sem isso, o `PREFECT_LOGGING_EXTRA_LOGGERS=ingestion` deste plano ligaria os handlers, mas o logger herdaria `WARNING` do root (`logging.yml` do Prefect), e os logs INFO dos jobs sumiriam (D6).

### O que o PR 30 entrega (na `main` antes deste PR)

- Serviço `prefect-server` com `healthcheck` em `/api/ready` (para `depends_on: service_healthy`), imagem `prefecthq/prefect:<X.Y.Z>-python3.12@sha256:<digest>`, `mem_limit: 640m` (só do server) e API interna em `http://prefect-server:4200/api`.
- Autenticação da API (plano 30, D7): variável `PREFECT_API_AUTH` no `infra/.env`, formato `admin:<senha>`; no server, `PREFECT_SERVER_API_AUTH_STRING: ${PREFECT_API_AUTH:?PREFECT_API_AUTH is required}`. Nos clientes (este PR: `prefect-worker` e `jobs`), a mesma variável do `.env` entra como `PREFECT_API_AUTH_STRING: ${PREFECT_API_AUTH:?PREFECT_API_AUTH is required}`.
- Allow-list de variáveis por serviço em `tests/infra/test_compose.py` (plano 30, caso 12): `PREFECT_API_AUTH` → `{"prefect-server"}`, com a nota "os clientes do PR 34 entram aqui". Este PR a estende (caso 6).
- Banco `prefect` criado pelo subcomando do PR 28: `docker compose ... --profile jobs run --rm -T jobs python -m ingestion create-databases` (já roda no `compose-smoke` desde o PR 28).

## 5. Passos

1. (implementer, antes de tudo) Confira as flags na versão fixada:

   ```bash
   uv run prefect worker start --help
   uv run prefect deployment run --help
   uv run prefect config view --show-defaults | grep -E 'EXTRA_LOGGERS|WORKER_WEBSERVER|API_AUTH_STRING'
   ```

   → `worker start` lista `--pool`, `--type`, `--limit` e `--with-healthcheck`; `deployment run` lista `--param`, `--watch` e `--watch-timeout`; aparecem `PREFECT_LOGGING_EXTRA_LOGGERS`, `PREFECT_WORKER_WEBSERVER_HOST`, `PREFECT_WORKER_WEBSERVER_PORT` (padrão `8080`) e `PREFECT_API_AUTH_STRING`. Se faltar alguma, pare e devolva para o planejamento com a saída.
2. (test-writer) Casos da seção 8 numa seção `# === plan 34` de `tests/infra/test_compose.py`, com funções de checagem novas e exemplos negativos, no estilo do arquivo. O caso 3 importa `flows.deployments.POOL`. Confirme a falha por `infra/docker-compose.yml has no 'prefect-worker' service` (e pelo `jobs` sem `PREFECT_API_URL`). Commit `test: add prefect worker compose tests`.
3. (implementer) `infra/docker-compose.yml`, serviço novo (depois do `scheduler`, que fica intocado até o PR 36):

   ```yaml
     prefect-worker:
       build:
         context: ..
         dockerfile: infra/jobs/Dockerfile
       command: ["prefect", "worker", "start", "--pool", "platform", "--type", "process", "--limit", "1", "--with-healthcheck"]
       restart: unless-stopped
       mem_limit: 768m
       environment:
         DATABASE_URL: postgresql+psycopg://ingestor:${POSTGRES_INGESTOR_PASSWORD:?POSTGRES_INGESTOR_PASSWORD is required}@postgres:5432/ml
         PREFECT_API_URL: http://prefect-server:4200/api
         PREFECT_API_AUTH_STRING: ${PREFECT_API_AUTH:?PREFECT_API_AUTH is required}
         PREFECT_LOGGING_EXTRA_LOGGERS: ingestion
         PREFECT_WORKER_WEBSERVER_HOST: 127.0.0.1
       healthcheck:
         test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]
         interval: 30s
         timeout: 5s
         retries: 3
         start_period: 60s
       depends_on:
         postgres:
           condition: service_healthy
         prefect-server:
           condition: service_healthy
   ```

   Sem `ports`, `volumes`, `user`, `privileged` nem `profiles`. O servidor de saúde do worker escuta só em `127.0.0.1` dentro do container e não é publicado.
4. (implementer) No serviço `jobs`, acrescente `PREFECT_API_URL: http://prefect-server:4200/api` e `PREFECT_API_AUTH_STRING: ${PREFECT_API_AUTH:?PREFECT_API_AUTH is required}`. O `jobs` não ganha `depends_on: prefect-server`: ele também roda migrações e a CLI sem o Prefect.
5. (implementer) `.github/workflows/ci.yml`, job `compose-smoke`, **depois dos passos do Prefect server (PR 30)** e antes do `if: always()` final (o banco `prefect` e o `prefect-server` já estão no ar pelos passos dos PRs 28 e 30; hoje os passos do `scheduler` vêm antes deles e continuam onde estão até o PR 36):

   ```yaml
         - run: $COMPOSE build prefect-worker
         - run: $COMPOSE up -d --wait prefect-worker
         - name: Check the worker runs as a non-root user
           run: test "$($COMPOSE exec -T prefect-worker whoami)" = app
         - name: Check the worker has no admin database URL
           run: |
             if $COMPOSE exec -T prefect-worker printenv DATABASE_URL_ADMIN; then exit 1; fi
         - run: $COMPOSE run --rm -T jobs python -m flows.deployments
         - name: Check the deployments use the Sao Paulo schedules
           run: |
             for name in ingest_weather_forecast ingest_weather_observed ingest_ons_load; do
               $COMPOSE run --rm -T jobs prefect deployment inspect "$name/production" | grep -F America/Sao_Paulo
             done
         - name: Check a failing flow run ends Failed through the worker
           run: |
             if $COMPOSE run --rm -T jobs prefect deployment run ingest_ons_load/production --param start=2026-02-01 --param end=2026-01-01 --watch --watch-timeout 300; then exit 1; fi
             $COMPOSE logs prefect-worker | grep -F 'is after end'
         - name: Report worker memory (informational)
           run: docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'
   ```

   O penúltimo passo dispara `ingest_ons_load` com `start > end`. O job levanta `ValueError` antes de tocar rede ou banco, o que prova o caminho worker → subprocesso → código de `/app` → `Failed` sem chamar ONS nem Open-Meteo do CI. O `--watch-timeout 300` impede que um worker travado prenda o job do CI. Os valores de `PREFECT_API_AUTH` e das senhas vêm do `infra/.env.example` (`$COMPOSE` já usa `--env-file infra/.env.example`), sem `secrets.`. Não acrescente `uses:` (o teste `test_ci_workflow_has_uses_lines_to_check` espera 3). Rode `uv run zizmor .github/workflows/` e corrija os achados.
6. (implementer) `AGENTS.md`, "Comandos":
   - "Worker do Prefect: `docker compose -f infra/docker-compose.yml build jobs prefect-worker` (imagens separadas do mesmo Dockerfile: construa as duas juntas), `docker compose -f infra/docker-compose.yml up -d prefect-worker` e `docker compose -f infra/docker-compose.yml logs prefect-worker` (na VPS; localmente o compose de produção colide com o Postgres de teste)."
   - "Registrar deployments na VPS: `docker compose -f infra/docker-compose.yml run --rm jobs python -m flows.deployments`."
   - Na linha "Na VPS (até o PR 37...)": `build jobs prefect-worker` no lugar de `build jobs`.
7. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

Locais (sem subir o compose de produção):

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam (inclusive os do `scheduler` e do crontab, intocados) |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q; echo "exit=$?"` | Nada impresso antes de `exit=0` |
| `uv run zizmor .github/workflows/` | Sem achados |
| `uv run ruff check .` e `uv run pytest` | Sem achados; suíte verde |

**Somente CI (`compose-smoke`)**, conferidos no log do PR por `gh pr checks` e `gh run view <id> --log`. Não rode localmente sem autorização explícita do usuário (o compose de produção colide com o Postgres de teste na 5432); se autorizado, pare o dev antes (`docker compose -f infra/docker-compose.dev.yml stop`), termine com `docker compose -f infra/docker-compose.yml --env-file infra/.env.example down` (**nunca `-v`**) e religue o dev (`... -f infra/docker-compose.dev.yml start`).

| Passo do `compose-smoke` | Saída esperada no log |
| --- | --- |
| `create-databases` (PR 28) e `up -d --wait prefect-server` (PR 30) | `exit 0`; `prefect-server` `Healthy` |
| `$COMPOSE up -d --wait prefect-worker` | `prefect-worker` `Healthy` |
| `Check the worker runs as a non-root user` | Verde (`app`) |
| `Check the worker has no admin database URL` | Verde |
| `$COMPOSE run --rm -T jobs python -m flows.deployments` | Três linhas de log, código 0 |
| `Check the deployments use the Sao Paulo schedules` | Três linhas com `America/Sao_Paulo` |
| `Check a failing flow run ends Failed through the worker` | O `--watch` sai com código diferente de 0 em menos de 300 s e o log do worker contém `is after end` |
| `Report worker memory (informational)` | Linha do `prefect-worker` em repouso; copie o número para a descrição do PR (insumo do item 35) |
| `gh pr checks` | Verde, com os passos novos do `compose-smoke` |

## 7. Testes necessários

`sim`: o worker roda os jobs em produção. Credencial errada, pool errado ou concorrência sem limite fazem os flows rodarem com privilégio demais, não rodarem ou estourarem a memória.

## 8. Casos de teste

`tests/infra/test_compose.py`, seção "plan 34":

1. `prefect-worker` existe, não tem `profiles`, tem `restart: unless-stopped` e `mem_limit` no máximo 768 MiB (rejeita `1g`, `800m`, ausente), e não declara `ports`.
2. `prefect-worker` constrói como o `jobs`: `build.context == ".."` e `build.dockerfile == "infra/jobs/Dockerfile"` (mesmo código e mesmas dependências). O PR 37 troca isso por `image:` por digest comum aos dois.
3. `command` é exatamente `["prefect", "worker", "start", "--pool", <POOL>, "--type", "process", "--limit", "1", "--with-healthcheck"]`, com `<POOL>` igual a `flows.deployments.POOL`. Exemplos negativos: forma string, outro pool, `--type docker`, sem `--limit` ou com `--limit 2` são rejeitados.
4. `DATABASE_URL` do worker é a URL do `ingestor` com senha por referência (`ingestor_url_problems` e `database_url_credential_problems` vazios).
5. O worker não tem credencial de admin (`admin_credential_problems` vazio).
6. Mínimo privilégio:
   - As variáveis `${...}` referenciadas no serviço `prefect-worker` são um subconjunto de `{"POSTGRES_INGESTOR_PASSWORD", "PREFECT_API_AUTH"}`.
   - A allow-list do plano 30 (caso 12 de lá) passa a `PREFECT_API_AUTH` → `{"prefect-server", "jobs", "prefect-worker"}`; `PREFECT_DB_PASSWORD` → `{"jobs", "prefect-server"}` e `MLFLOW_DB_PASSWORD` → `{"jobs", "mlflow"}` não mudam.
   - Se o `prefect-server` tem `PREFECT_SERVER_API_AUTH_STRING`, o worker e o `jobs` têm `PREFECT_API_AUTH_STRING`, cujo valor é exatamente uma referência `${PREFECT_API_AUTH...}` (`ENV_REFERENCE`), nunca literal nem outra variável.
   - Exemplos negativos: um serviço que referencia `POSTGRES_ADMIN_PASSWORD`, a senha do banco `prefect` ou a do `mlflow` é rejeitado; `PREFECT_API_AUTH_STRING: admin:hunter2` (literal) é rejeitado; `PREFECT_API_AUTH_STRING: ${PREFECT_API_AUTH_STRING}` (variável do `.env` com outro nome) é rejeitado; `mlflow` com `PREFECT_API_AUTH` é rejeitado.
7. Nada de acesso ao host: o worker não tem `volumes` (em particular nenhum `/var/run/docker.sock`), `privileged: true`, `user` `root`/`0`, `network_mode: host` nem `pid: host`. Exemplos negativos para cada um.
8. `environment` do worker:
   - `PREFECT_API_URL == "http://prefect-server:4200/api"` (rede interna do compose, nunca a URL da tailnet nem `127.0.0.1`);
   - `PREFECT_LOGGING_EXTRA_LOGGERS == "ingestion"`;
   - `PREFECT_WORKER_WEBSERVER_HOST == "127.0.0.1"`;
   - `TZ` ausente ou `America/Sao_Paulo`.
9. `healthcheck.test` do worker não é vazio e aponta para `127.0.0.1`.
10. `depends_on` do worker: `postgres` e `prefect-server`, os dois com `condition: service_healthy`.
11. O `jobs` tem `PREFECT_API_URL == "http://prefect-server:4200/api"` e continua passando nos casos do plano 11 (profile `jobs`, `restart: "no"`, `ingestor`).
12. `PORT_PUBLISHING_SERVICES` não contém `prefect-worker`, e toda variável obrigatória do compose continua declarada no `infra/.env.example` (`undeclared_variables` vazio; `PREFECT_API_AUTH` já declarada pelo PR 30).

## 9. Riscos e perguntas em aberto

### Riscos

1. **API do Prefect sem autenticação = execução remota com a credencial `ingestor`.** Com o worker `process`, quem consegue chamar a API do server pode criar ou alterar um deployment com um entrypoint qualquer, ou disparar execuções, e o worker roda esse código com `DATABASE_URL` do `ingestor` e acesso à rede. A ACL do Tailscale limita quem chega à porta 4200 (no item 31, só o dono; a cientista só no item 50). **Recomendação (aceita): `PREFECT_SERVER_API_AUTH_STRING` no server (PR 30, D7) e `PREFECT_API_AUTH_STRING` no worker, no `jobs` e no CI** (valor fictício do `.env.example`, sem `secrets.`), registrado no ADR "Agendamento e execução pelo Prefect". Isso não substitui a ACL; é uma segunda camada. Quando a 4200 for liberada à cientista (item 50), ela precisa da credencial, e quem tem a credencial pode tudo no Prefect OSS (ponto a combinar com ela no item 50).
2. **Memória.** A soma dos `mem_limit` depois deste PR passa de 2 GB: `health` 16m, `postgres` 256m, `scheduler` 512m, `mlflow` 512m (PR 29), `prefect-server` 640m (o limite do plano 30 é só do server) e `prefect-worker` 768m, contra 2 GB de RAM (28b, padrão antes do item 31; 1 GB só se o usuário registrou dispensa) e 2 GB de swap. `mem_limit` é teto por container, não reserva, e uma soma maior que a RAM é normal. **Só a coluna `available` medida no item 35 decide** (gatilhos G1 a G5 do 28a, seção 5.6, e a segunda projeção de lá, "folga do item 35"), junto com o uso real de cada container no `docker stats`. O worker em repouso adiciona cerca de 120 a 200 MB fixos, contra ~10 MB do supercronic.
3. **API e CLI do Prefect.** Os pontos vieram de memória e de revisão independente com acesso à web, e o passo 1 os confere: `prefect worker start --pool --type --limit --with-healthcheck`; o servidor de saúde em `/health` com `PREFECT_WORKER_WEBSERVER_HOST`/`PORT`; `PREFECT_LOGGING_EXTRA_LOGGERS`; `PREFECT_API_AUTH_STRING`; `prefect deployment run --param --watch --watch-timeout` saindo com código diferente de 0 quando a execução falha; a saída de `prefect deployment inspect` com o timezone.
4. **SIGTERM durante um flow.** Recriar o worker (deploy, `up -d`) com um flow rodando mata o subprocesso, e o run fica `Crashed`. Não recrie o worker entre 06:25 e 07:15 BRT; o PR 39 recusa deploy entre 06:00 e 08:00 BRT.
5. **`depends_on: prefect-server`** faz o worker esperar o server saudável no boot. Se o server cair depois, o worker tenta reconectar sozinho (comportamento a observar no reboot do item 35).
6. **CI mais lento** pelo build de mais uma imagem com Prefect. Aceitável.
7. **Fase 4.** Um worker com `ingestor` e `scorer`, ou um segundo worker (com RAM a mais), é decisão do PR 46.
8. **Prova só no CI.** O caminho worker → subprocesso → `Failed` não é exercitado localmente (o compose de produção não sobe na máquina do desenvolvedor sem autorização); o `compose-smoke` é a prova, e o item 35 prova o sucesso real na VPS.

### Decisões (com recomendação; aceitas pelo usuário)

- **D1. Tipo de work pool: `process`, `docker` ou `serve()`.** **`process`.** Na VPS de 1 vCPU, o `process` roda cada flow run como subprocesso dentro do container do worker: o worker em repouso (estimativa de 120–200 MB) mais um subprocesso por vez (estimativa de 250–450 MB com Prefect, pandas e pyarrow), tudo sob um único `mem_limit` e com o código já na imagem.
  - `docker` não economiza RAM: o worker continua no ar e cada execução sobe um container novo, com o mesmo pico do flow mais a partida do container. Exige montar `/var/run/docker.sock`, o que equivale a root no host e quebra o mínimo privilégio, e uma imagem endereçável, que só existe a partir do PR 37.
  - `serve()` gasta RAM parecida, mas não tem work pool: sem limite de concorrência declarado, sem a fila da Fase 4 e fora do "server + worker" do doc.

  As estimativas são do índice (`docs/plans/00-indice.md`) e são confirmadas no item 35.
- **D2. `mem_limit` do worker: `768m`.** O limite cobre o worker mais um flow (`--limit 1`). Reduzir em PR próprio se o pico medido no item 35 ficar bem abaixo.
- **D3. Uma execução por vez: `--limit 1` no worker**, além do limite 1 do pool (PR 33).
- **D4. Healthcheck: `--with-healthcheck`, com `PREFECT_WORKER_WEBSERVER_HOST=127.0.0.1`**, conferido em Python (a imagem não tem `curl`). O servidor de saúde não fica exposto nem na rede interna do compose.
- **D5. Imagem do worker.** Até o PR 37: `build` igual ao do `jobs`, sem `image:` comum; consequência, `build jobs prefect-worker` sempre junto. No PR 37: `jobs` e `prefect-worker` passam a usar a **mesma referência por digest**, `ghcr.io/${GHCR_OWNER:?GHCR_OWNER is required}/platform-jobs@${JOBS_IMAGE_DIGEST:?JOBS_IMAGE_DIGEST is required}`, para que o código do worker e o do `jobs` (que registra os deployments) sejam sempre idênticos. O plano 37 lista o `prefect-worker` com essa referência (passo 5 e caso 18 de lá).
- **D6. Logs dos jobs na UI: `PREFECT_LOGGING_EXTRA_LOGGERS=ingestion`.** Só funciona junto com o nível INFO fixado em `flows/ingest.py` pelo PR 32 (correção bloqueante de lá). Sem as duas coisas, a UI mostra só o traceback, e os greps de `weather-forecast ok` do item 35 falham.
- **D7. Prova no CI.** Registrar deployments e disparar só a execução de falha proposital (`start > end`), com `--watch-timeout 300`. O sucesso real, que chama ONS e Open-Meteo, é provado no item 35.
- **D8. Nome da variável da credencial.** No `infra/.env`, uma só: `PREFECT_API_AUTH` (plano 30, D7), referenciada pelo server como `PREFECT_SERVER_API_AUTH_STRING` e pelos clientes como `PREFECT_API_AUTH_STRING`. Trocar a senha = trocar uma linha do `.env` e recriar server, worker e `jobs` juntos.

### Perguntas em aberto

- Nenhuma bloqueante.

## 10. Decisões que exigem ADR

**Sim, o ADR obrigatório do plano 33, seção 10** ("Agendamento e execução pelo Prefect"), que precisa estar mergeado antes deste PR. Ele registra o tipo `process` em vez de `docker` (não montar o socket do Docker), a fronteira de credenciais do worker e a autenticação da API como segunda camada além da ACL. Nenhuma porta é publicada (o healthcheck é interno, em loopback), então o ADR 0003 não muda.
