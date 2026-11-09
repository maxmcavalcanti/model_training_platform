# 29 — MLflow no compose, só em loopback e na tailnet

> Executa: agente. Depende de: 28 (bancos, `create-databases`, passos do CI) na `main` e do checkpoint 28a feito. Não depende do ADR de execução de modelos (P13 bloqueia só o PR 42, como no índice). Usa os padrões dos PRs 03 e 10. Branch: `feat/compose-mlflow`.
> TDD: passo 0 (verificação, sem código) → test-writer (vermelho) → implementação mínima (verde) → refatorar com a suíte verde.
> Revisão 2026-11-08 (v2, com a revisão independente aceita pelo usuário). Em relação ao rascunho: imagem base por `tag@sha256:` do índice (ADR 0006); driver por `requirements.txt` com hashes; usuário não-root e `/artifacts` (ADR 0001); `/infra/mlflow` no Dependabot; URI do backend em variável de ambiente; pool abaixo do `CONNECTION LIMIT`; `cap_drop` e `no-new-privileges`; teto de `mem_limit`; Trivy sem HIGH/CRITICAL. Na v2: **`--allowed-hosts` e `--cors-allowed-origins` obrigatórios** (MLflow 3.5+ valida o `Host`, inclusive a porta, e bloqueia `POST /ajax-api` com `Origin` fora da lista; sem isso a UI pela tailnet não funciona) com três `curl` no CI, porque `/health` não passa pela checagem; MLflow não migra banco existente sozinho: Dependabot só com patch do MLflow e procedimento manual de `mlflow db upgrade`; telemetria e execução de jobs desligadas; a imagem oficial é Python 3.11 (`slim-trixie`), hashes com `uv pip compile --universal`; driver `psycopg[binary]` (v3) preferido; P13 deixa de bloquear este PR. Alinhamento entre planos (mesmo dia): a correção do índice (P13) foi aplicada; o plano 39 incorporou o procedimento de upgrade ao deploy automático (D12 de lá). Revisão final (mesmo dia): a URL do backend no argv do `mlflow db upgrade` dentro do container é risco residual aceito.

## 1. Objetivo

Subir o MLflow (tracking e model registry) no compose de produção, com backend no banco `mlflow` (papel `mlflow`) e artefatos num volume nomeado servidos pelo próprio servidor, publicado só em `127.0.0.1:5000` e exposto na tailnet por `tailscale serve` (`https://<host>.<tailnet>.ts.net:5000`), com a UI funcionando por esse endereço.
É o que libera a cientista para registrar experimentos e modelos (Fase 3).

## 2. Fora do escopo

- Prefect (PR 30) e deploy na VPS, ACL e acesso da cientista (item 31).
- MinIO ou S3 para artefatos; autenticação do próprio MLflow (`--app-name basic-auth`): a ACL do Tailscale é o controle (ADR 0003).
- Backup do volume e do banco (PR 57). Uso do MLflow pelo score (PR 43). Publicar `platform-mlflow` no GHCR (PR 37).
- O ADR de execução de modelos (P12/P13), anterior ao PR 42. Este PR só fixa a versão do servidor.
- Endurecer serviços antigos com `cap_drop`.
- Aplicar o procedimento de upgrade de versão do MLflow (seção 5, "Procedimento de upgrade"): só documentado aqui; o deploy automático do plano 39 o executa.

## 3. Fase do roadmap

Fase 3 — "MLflow e Prefect no compose, só na tailnet (`tailscale serve`)". Do doc, "Stack na VPS": "MLflow | Tracking de experimentos + model registry | Ela (principal) | Artefatos em volume local servidos pelo próprio MLflow (`--serve-artifacts`); MinIO só se crescer"; "MLflow e Prefect não têm autenticação própria: ficam em loopback, expostos só na tailnet; a ACL do Tailscale é o controle de acesso".

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/infra/test_mlflow_image.py` | test-writer | Casos 1 a 7 |
| `tests/infra/test_compose.py` | test-writer | Casos 8 a 22 (seção "plan 29"); `PORT_PUBLISHING_SERVICES` e a asserção de `test_general_rules_still_hold_with_the_scheduler` |
| `tests/infra/test_tailscale_serve.py` | test-writer | Caso 23 |
| `tests/infra/test_dependabot.py` | test-writer | Caso 24 |
| `infra/mlflow/Dockerfile` | implementer | Imagem oficial + driver do Postgres, não-root, `/artifacts` |
| `infra/mlflow/requirements.in` | implementer | Driver fixado com `==` |
| `infra/mlflow/requirements.txt` | implementer | Gerado com hashes |
| `infra/docker-compose.yml` | implementer | Serviço `mlflow` e volume `mlflow_artifacts` |
| `infra/scripts/tailscale-serve.sh` | implementer | Linha `--https=5000` |
| `.github/dependabot.yml` | implementer | `/infra/mlflow` no bloco `docker` e `ignore` de minor/major do MLflow |
| `.github/workflows/ci.yml` | implementer | Passos do MLflow no `compose-smoke` |
| `AGENTS.md` | implementer | Build da imagem e procedimento de upgrade |

### Contexto que o implementador precisa

`infra/scripts/tailscale-serve.sh` hoje:

```bash
#!/usr/bin/env bash
# Declares which loopback ports are exposed on the tailnet (ADR 0003): HTTPS per UI, raw TCP for Postgres (P15).
# Reset first, then reapply: the serve state on the VPS always matches git.
# One line per service, same port on loopback and on the tailnet.
set -euo pipefail

tailscale serve reset

tailscale serve --bg --https=8080 http://127.0.0.1:8080
tailscale serve --bg --tcp=5432 tcp://127.0.0.1:5432
```

Testes existentes que cobrem o serviço novo:

- `tests/infra/test_compose.py`: `restart: unless-stopped` sem `profiles`; `mem_limit` em todos; só `PORT_PUBLISHING_SERVICES` (hoje `{"health", "postgres"}`) publicam porta; porta só em `127.0.0.1` literal ou `${X_BIND_IP:-127.0.0.1}`; chave com `PASSWORD`/`TOKEN`/`SECRET` só com `${...}`; toda `${VAR}` obrigatória no `infra/.env.example`. `test_general_rules_still_hold_with_the_scheduler` afirma a igualdade `{"health", "postgres"}`: passa a afirmar só que o `scheduler` está fora. O plano 28 já pôs a allow-list `{"MLFLOW_DB_PASSWORD": {"jobs", "mlflow"}, "PREFECT_DB_PASSWORD": {"jobs", "prefect-server"}}`.
- `tests/infra/test_tailscale_serve.py`: `UI_SERVICES = ("health", "mlflow", "prefect-server", "grafana")`; correspondência compose ↔ script nos dois sentidos; sem `funnel`.
- `tests/infra/test_supply_chain_pins.py`: `FROM` por digest; imagem de terceiro no compose como `<nome>:<tag>@sha256:<64 hex>`; o `ci.yml` tem exatamente 3 `uses:` e 2 `actions/checkout`.
- `tests/infra/test_dependabot.py`: todo `Dockerfile` sob `infra/` num diretório do bloco `docker`; o bloco `docker` contém `/infra/jobs`.

Regras: `.claude/rules/infra.md` (restart, `mem_limit`, MLflow só em `127.0.0.1` + `tailscale serve`, nada em `0.0.0.0`, imagens por `tag@sha256:<índice multi-arch>`, nenhum `${{ }}` em `run:`, `uv run zizmor .github/workflows/` antes de commitar workflow). ADR 0003: "MLflow | `127.0.0.1:5000` | `https://<host>.ts.net:5000`". ADR 0001: serviço `mlflow`, imagem `platform-mlflow`, volume `mlflow_artifacts`, montagem `/artifacts`. ADR 0006, item 3: Trivy `config` sobre todos os Dockerfiles, HIGH/CRITICAL (imagem sem `USER` não-root é HIGH); item 2: quatro ecossistemas no Dependabot (sem `pip`).

### Decisões (aceitas pelo usuário em 2026-11-08)

| Id | Decisão |
| --- | --- |
| D1 | `FROM ghcr.io/mlflow/mlflow:v<X.Y.Z>@sha256:<índice>` (base Python 3.11 `slim-trixie`, segundo a revisão) + driver por `requirements.txt` com `--require-hashes` |
| D2 | Última 3.x estável publicada há pelo menos 7 dias (`https://github.com/mlflow/mlflow/releases`); 3.5 ou mais nova (a proteção de host e CORS é dessa linha) |
| D3 | Porta `127.0.0.1:5000:5000` literal |
| D4 | Credencial do backend em `MLFLOW_BACKEND_STORE_URI` no `environment`, nunca no `command` |
| D5 | `mem_limit: 512m`, `--workers 1`, pool 2 + 2 (abaixo do `CONNECTION LIMIT 10` do PR 28) |
| D6 | `cap_drop: [ALL]`, `security_opt: ["no-new-privileges:true"]` |
| D7 | Driver `psycopg[binary]` (v3) com `postgresql+psycopg://`, se o passo 0 confirmar suporte na versão fixada; senão `psycopg2-binary` com `postgresql://` |
| D8 | Hosts permitidos `mlflow:5000,localhost:5000,127.0.0.1:5000,${TS_HOSTNAME}:5000` e origem CORS `https://${TS_HOSTNAME}:5000`, obrigatórios |
| D9 | `MLFLOW_DISABLE_TELEMETRY: "true"` e `MLFLOW_SERVER_ENABLE_JOB_EXECUTION: "false"` |
| D10 | Dependabot atualiza só patch do MLflow; minor e major são PR manual com o procedimento de upgrade |

## 5. Passos

0. **(implementer, sem commit; antes do test-writer)** Confira o que esta revisão não pôde executar e devolva a saída ao coordenador; divergência volta ao planner antes do test-writer.

   ```bash
   docker buildx imagetools inspect ghcr.io/mlflow/mlflow:v<X.Y.Z>
   IMG=ghcr.io/mlflow/mlflow:v<X.Y.Z>@sha256:<índice>
   docker run --rm $IMG sh -c 'python --version; id -u; head -2 /etc/os-release; command -v useradd'
   docker run --rm $IMG python -c "import psycopg2"
   docker run --rm $IMG python -c "import psycopg"
   docker run --rm $IMG mlflow server --help
   docker run --rm $IMG python -c "import mlflow.cli as c; print({p.name: p.envvar for p in c.server.params})"
   docker run --rm $IMG python -c "import mlflow.environment_variables as e; print([n for n in dir(e) if any(k in n for k in ('SQLALCHEMY', 'TELEMETRY', 'ALLOWED_HOSTS', 'CORS', 'JOB'))])"
   docker run --rm $IMG mlflow db upgrade --help
   docker compose up --help
   ```

   Anote: digest do índice e `linux/amd64` presente; Python (esperado 3.11); se roda como root e tem `useradd`; se o driver já vem na imagem (esperado: não); `--allowed-hosts`, `--cors-allowed-origins`, `--serve-artifacts`, `--artifacts-destination`, `--workers` e o formato dos valores; as variáveis `MLFLOW_BACKEND_STORE_URI`, `MLFLOW_SQLALCHEMYSTORE_POOL_SIZE`, `MLFLOW_SQLALCHEMYSTORE_MAX_OVERFLOW`, `MLFLOW_DISABLE_TELEMETRY`, `MLFLOW_SERVER_ENABLE_JOB_EXECUTION`, `MLFLOW_SERVER_ALLOWED_HOSTS` e `MLFLOW_SERVER_CORS_ALLOWED_ORIGINS`; que `mlflow db upgrade` recebe a URL como argumento posicional (esperado: só assim; ver risco "URL no argv do `db upgrade`"); se o compose aceita `--wait-timeout`. Depois, suba um container de teste com a imagem e o driver escolhido contra um Postgres descartável e confirme com `curl` os **códigos** das três chamadas do passo 7 (esperado: `200`, `403`, `403`) e que `postgresql+psycopg://` funciona (D7).
1. (test-writer) Casos da seção 8. Confirme a falha pelo motivo certo. Commit: `test: add mlflow compose and image tests`.
2. (implementer) `infra/mlflow/requirements.in` com uma linha (D7): `psycopg[binary]==<3.A.B>` (ou `psycopg2-binary==<2.9.C>` no fallback). Gere o `.txt` com hashes de todas as plataformas:

   ```bash
   uv pip compile infra/mlflow/requirements.in --universal --generate-hashes --python-version 3.11 -o infra/mlflow/requirements.txt
   ```

   (Alternativa equivalente: `--python-platform x86_64-manylinux_2_28` no lugar de `--universal`.) Use a versão de Python que o passo 0 mostrar.
3. (implementer) `infra/mlflow/Dockerfile`:

   ```dockerfile
   FROM ghcr.io/mlflow/mlflow:v<X.Y.Z>@sha256:<digest do índice>

   COPY requirements.txt /tmp/requirements.txt
   RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
       && rm /tmp/requirements.txt

   RUN useradd --create-home --uid 10001 mlflow \
       && mkdir /artifacts \
       && chown mlflow:mlflow /artifacts

   USER mlflow
   WORKDIR /home/mlflow
   ```

   O `/artifacts` do volume novo herda dono e permissões do diretório da imagem na primeira montagem.
4. (implementer) `infra/docker-compose.yml` (forma das opções conforme o passo 0; se só as variáveis de ambiente existirem para hosts e CORS, use-as no `environment` com os mesmos valores):

   ```yaml
     mlflow:
       build:
         context: ./mlflow
       restart: unless-stopped
       mem_limit: 512m
       cap_drop: [ALL]
       security_opt: ["no-new-privileges:true"]
       command:
         - mlflow
         - server
         - --host
         - 0.0.0.0
         - --port
         - "5000"
         - --workers
         - "1"
         - --serve-artifacts
         - --artifacts-destination
         - /artifacts
         - --allowed-hosts
         - "mlflow:5000,localhost:5000,127.0.0.1:5000,${TS_HOSTNAME:?TS_HOSTNAME is required}:5000"
         - --cors-allowed-origins
         - "https://${TS_HOSTNAME:?TS_HOSTNAME is required}:5000"
       environment:
         MLFLOW_BACKEND_STORE_URI: postgresql+psycopg://mlflow:${MLFLOW_DB_PASSWORD:?MLFLOW_DB_PASSWORD is required}@postgres:5432/mlflow
         MLFLOW_SQLALCHEMYSTORE_POOL_SIZE: "2"
         MLFLOW_SQLALCHEMYSTORE_MAX_OVERFLOW: "2"
         MLFLOW_DISABLE_TELEMETRY: "true"
         MLFLOW_SERVER_ENABLE_JOB_EXECUTION: "false"
       volumes:
         - "mlflow_artifacts:/artifacts"
       ports:
         - "127.0.0.1:5000:5000"
       healthcheck:
         test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=5)"]
         interval: 30s
         timeout: 10s
         retries: 5
         start_period: 180s
       depends_on:
         postgres:
           condition: service_healthy
   ```

   No topo: `volumes: {pgdata: {}, mlflow_artifacts: {}}` (em bloco, como está). Com o fallback `psycopg2-binary`, o esquema é `postgresql://`. O `--host 0.0.0.0` é dentro do container; no host só existe `127.0.0.1:5000`. **Nunca** ponha `mlflow db upgrade` no `command` (ver procedimento abaixo). O PR 37 troca o `build:` por `image: ghcr.io/${GHCR_OWNER}/platform-mlflow@${MLFLOW_IMAGE_DIGEST}`.
5. (implementer) `infra/scripts/tailscale-serve.sh`: depois da linha da 8080, `tailscale serve --bg --https=5000 http://127.0.0.1:5000`.
6. (implementer) `.github/dependabot.yml`, bloco `docker`: `directories` passa a `"/infra/jobs"` e `"/infra/mlflow"`, e acrescente:

   ```yaml
       ignore:
         # MLflow does not migrate an existing database on start: minor and major upgrades are manual (plan 29)
         - dependency-name: "*mlflow/mlflow"
           update-types: ["version-update:semver-major", "version-update:semver-minor"]
   ```

   Valide: `uvx --from check-jsonschema==0.39.0 check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml`. O padrão com `*` cobre o nome com ou sem o registro (não verificado qual dos dois o Dependabot usa para o GHCR).
7. (implementer) `.github/workflows/ci.yml`, job `compose-smoke`, depois dos passos do PR 28 e antes do `if: always()` final; só `run:`:

   ```yaml
         - run: $COMPOSE build mlflow
         - run: $COMPOSE up -d --wait --wait-timeout 300 mlflow
         - name: Check MLflow answers on loopback
           run: test "$(curl -fsS http://127.0.0.1:5000/health)" = OK
         - name: Check MLflow accepts the tailnet host and origin and rejects others
           run: |
             ts_host="$(grep '^TS_HOSTNAME=' infra/.env.example | cut -d= -f2-)"
             url=http://127.0.0.1:5000/ajax-api/2.0/mlflow/experiments/search
             call() { curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -H "Host: $1" -H "Origin: $2" -d '{"max_results": 1}' "$url"; }
             ok="$(call "$ts_host:5000" "https://$ts_host:5000")"
             bad_host="$(call "evil.example:5000" "https://$ts_host:5000")"
             bad_origin="$(call "$ts_host:5000" "https://evil.example")"
             echo "allowed=$ok bad_host=$bad_host bad_origin=$bad_origin"
             test "$ok" = 200 && test "$bad_host" = 403 && test "$bad_origin" = 403
         - name: Check MLflow is published only on 127.0.0.1
           run: |
             ports="$($COMPOSE ps --format '{{.Ports}}' mlflow)"
             echo "$ports"
             echo "$ports" | grep -F '127.0.0.1:5000->5000/tcp'
             if echo "$ports" | grep -E '0\.0\.0\.0|\[::\]|:::'; then exit 1; fi
         - name: Check MLflow runs as a non-root user
           run: test "$($COMPOSE exec -T mlflow id -u)" != 0
         - name: Check a run logs a metric and an artifact through the server
           run: |
             $COMPOSE exec -T mlflow python -c "import mlflow; mlflow.set_tracking_uri('http://127.0.0.1:5000'); mlflow.set_experiment('ci-smoke'); run = mlflow.start_run(); mlflow.log_metric('x', 1.0); mlflow.log_text('ok', 'a.txt'); mlflow.end_run(); path = mlflow.artifacts.download_artifacts(run_id=run.info.run_id, artifact_path='a.txt'); raise SystemExit(open(path).read() != 'ok')"
             $COMPOSE exec -T mlflow sh -c 'find /artifacts -name a.txt | grep -q .'
         - name: Report MLflow image size, memory and connections (informational)
           run: |
             docker image ls platform-mlflow --format '{{.Repository}} {{.Size}}'
             docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'
             $COMPOSE exec -T postgres psql -U platform_admin -d ml -tAc "select usename, count(*) from pg_stat_activity where datname = 'mlflow' group by 1"
   ```

   Os códigos `200`/`403`/`403` são os que o passo 0 confirmar. Ler o `TS_HOSTNAME` do `.env.example` é do CI (o agente não abre o arquivo). Sem `--wait-timeout` no runner, tire a opção. O `down -v` com `if: always()` no fim do job continua: é o banco descartável do CI, nunca a VPS. Antes de commitar: `uv run zizmor .github/workflows/`.
8. (implementer) `AGENTS.md`, "Comandos": `- Imagem do MLflow: \`docker build -t platform-mlflow infra/mlflow\`` e, na VPS, `docker compose -f infra/docker-compose.yml build mlflow` (até o PR 37 a imagem é construída na VPS). UTF-8.
9. Rode os critérios da seção 6 e refatore com a suíte verde.

### Procedimento de upgrade de versão do MLflow (documentado aqui; aplicado pelo deploy automático do plano 39)

O MLflow **não** migra um banco já existente na subida: com schema antigo, ele aborta com `Detected out-of-date database schema` e o `restart: unless-stopped` vira um laço de reinícios. Por isso:

1. PR que troca o `FROM` (patch pelo Dependabot; minor ou major à mão, porque o `ignore` do passo 6 bloqueia).
2. Na VPS, fora da janela 06:25–07:15: `dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d mlflow -Fc' > "$HOME/backups/mlflow-$(date +%F).dump"`.
3. `dc build mlflow` (a partir do PR 37: `dc pull mlflow`), `dc stop mlflow`.
4. `dc run --rm --no-deps mlflow sh -c 'exec mlflow db upgrade "$MLFLOW_BACKEND_STORE_URI"'`. O `run` substitui o `command`, e a URL é expandida dentro do container: nunca aparece no argv nem no histórico do host. Ela fica, sim, no argv do processo `mlflow db upgrade` dentro do container enquanto ele roda, porque o comando só aceita a URL como argumento posicional (risco residual aceito, seção 9).
5. `dc up -d --wait mlflow` e `curl -fsS http://127.0.0.1:5000/health`.

Nunca dentro do `command` do serviço. **Nota para o plano 39 (deploy via SSH), aplicada lá (D12):** a partir do PR 39, o `deploy.sh` executa este procedimento sempre que a linha `FROM` de `infra/mlflow/Dockerfile` muda entre o commit implantado e o anterior (`pg_dump` antes do `pull`, `stop` e `db upgrade` depois do `alembic`, então `up`), sem rollback de containers depois de um `db upgrade` bem-sucedido. Até o primeiro deploy automático, o procedimento é manual (exceção do ADR 0004).

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `uv run pytest` | Suíte verde (com o Postgres de teste no ar) |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem achados |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Sem saída, código 0 |
| `docker build -t platform-mlflow infra/mlflow` | Build sem erro |
| `docker run --rm platform-mlflow id -u` | `10001` |
| `docker run --rm platform-mlflow python -c "import psycopg; print('ok')"` (ou `psycopg2` no fallback) | `ok` |
| `docker run --rm -v "${PWD}:/src:ro" -w /src ghcr.io/aquasecurity/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c config --misconfig-scanners dockerfile --severity HIGH,CRITICAL --exit-code 1 infra/mlflow` | Código 0 |
| `uvx --from check-jsonschema==0.39.0 check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml` | `ok -- validation done` |
| `uv run zizmor .github/workflows/` | Sem achados |
| `gh pr checks` | `lint-and-test` e `compose-smoke` verdes; no log, `allowed=200 bad_host=403 bad_origin=403`, `127.0.0.1:5000->5000/tcp`, tamanho da imagem e memória do `platform-mlflow-1` (copie para a descrição do PR); `security.yml` sem achado novo |

Não suba o compose de produção localmente (colide com o Postgres de teste na 5432).

## 7. Testes necessários

`sim`: exposição (só loopback e tailnet), hosts e origens permitidos, credencial só do papel `mlflow`, pin da imagem e política de upgrade são regras verificáveis cuja regressão abriria o registry, quebraria a UI ou derrubaria o serviço.

## 8. Casos de teste

Dockerfile (`tests/infra/test_mlflow_image.py`; reaproveite `instructions`, `user_problems`, `copy_problems` e `secret_name_problems` de `tests/infra/test_jobs_image.py`):

1. Exatamente um `FROM`, casando com `^ghcr\.io/mlflow/mlflow:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$`. Negativos: sem digest, `latest`, `v3`, outra imagem.
2. O último `USER` existe e não é `root` nem `0`.
3. Nenhum `ADD` e nenhum `COPY` do contexto inteiro.
4. Nenhum `ENV`/`ARG` com nome de segredo nem `MLFLOW_BACKEND_STORE_URI`.
5. Todo `pip install` usa `--require-hashes` e `-r`. Negativos: `RUN pip install psycopg2-binary`, `-r` sem `--require-hashes`.
6. `requirements.in` tem exatamente uma dependência, `psycopg[binary]` ou `psycopg2-binary`, fixada com `==X.Y.Z`. Negativos: `>=`, sem versão, outro pacote.
7. `requirements.txt` fixa a mesma versão e tem pelo menos uma linha `--hash=sha256:<64 hex>`.

Compose (`tests/infra/test_compose.py`, seção "plan 29"):

8. `mlflow` sem `profiles`, com `restart: unless-stopped`.
9. `mem_limit` presente e no máximo 512 MiB (rejeita `1g`, `600m`, ausente).
10. `ports` exatamente `["127.0.0.1:5000:5000"]`. Negativos: `"5000:5000"`, `"0.0.0.0:5000:5000"`, `"${MLFLOW_BIND_IP}:5000:5000"`, porta extra.
11. `build.context` é `./mlflow` e não há `image:`.
12. `MLFLOW_BACKEND_STORE_URI` casa com `^postgresql(\+psycopg)?://mlflow:\$\{MLFLOW_DB_PASSWORD(:\?[^}]*)?\}@postgres:5432/mlflow$`, e o esquema bate com o driver do `requirements.in` (`psycopg` → `postgresql+psycopg://`; `psycopg2-binary` → `postgresql://`). Negativos: usuário admin, senha literal, `localhost`, banco `ml`, senha `${POSTGRES_ADMIN_PASSWORD}`, esquema que não bate com o driver.
13. O serviço não referencia `ADMIN`, `POSTGRES_INGESTOR_PASSWORD` nem `PREFECT_DB_PASSWORD` (allow-list do plano 28 inclusive).
14. `command` é lista e contém `--serve-artifacts`, `--artifacts-destination` + `/artifacts`, `--workers` + `"1"`, `--port` + `"5000"`; sem `--backend-store-uri` e sem item com `PASSWORD`. Negativo: `--backend-store-uri postgresql://mlflow:${MLFLOW_DB_PASSWORD}@...` no `command`.
15. `command` (ou o `environment`, na forma que o passo 0 confirmar) tem a lista de hosts permitidos com `mlflow:5000`, `localhost:5000`, `127.0.0.1:5000` e `${TS_HOSTNAME...}:5000`, e a origem CORS exatamente `https://${TS_HOSTNAME...}:5000`. Negativos: hosts sem o `TS_HOSTNAME`, `TS_HOSTNAME` sem a porta, `*` como host, origem `http://`, origem `*`.
16. `command` não contém `db upgrade` nem `mlflow db` (upgrade nunca automático no serviço).
17. `MLFLOW_DISABLE_TELEMETRY` é `"true"` e `MLFLOW_SERVER_ENABLE_JOB_EXECUTION` é `"false"`.
18. Volume `mlflow_artifacts` em `/artifacts`, declarado no topo (`named_volume_problems`).
19. `healthcheck.test` aponta para `/health` na 5000 (só prova que o processo responde; host e CORS são cobertos pelos `curl` do CI, passo 7); `depends_on.postgres.condition` é `service_healthy`.
20. `cap_drop` contém `ALL` e `security_opt` contém `no-new-privileges:true`.
21. `PORT_PUBLISHING_SERVICES` passa a `{"health", "postgres", "mlflow"}`; `scheduler` fora.
22. Regras gerais verdes: `MLFLOW_DB_PASSWORD` e `TS_HOSTNAME` declaradas no `.env.example`; `FROM` por digest (`test_supply_chain_pins.py`).

Script (`tests/infra/test_tailscale_serve.py`):

23. Exatamente uma linha `--https=5000 http://127.0.0.1:5000`; a correspondência compose ↔ script inclui a 5000.

Dependabot (`tests/infra/test_dependabot.py`):

24. O bloco `docker` lista `/infra/mlflow` (cobertura reversa existente fica verde) e tem um `ignore` cujo `dependency-name` cobre `mlflow/mlflow` com `version-update:semver-major` e `version-update:semver-minor`. Negativo embutido: `ignore` só com major.

## 9. Riscos e perguntas em aberto

Riscos:

- **Memória:** o MLflow é um dos dois serviços mais pesados; o item 31 mede e só segue se a folga permitir (o 28b de 2 GB é o padrão antes dele).
- **Sem autenticação:** quem a ACL deixar chegar à 5000 lê e escreve no registry, inclusive o alias `champion` (deploy de modelo). O item 31 libera a 5000 só para o dono e a cientista.
- **Host e CORS:** sem `--allowed-hosts` e `--cors-allowed-origins` certos, a UI pela tailnet carrega mas não lista nada (o `POST /ajax-api` volta `403`), enquanto o `/health` fica verde. Os `curl` do CI travam isso.
- **Upgrade de schema:** subir versão sem `mlflow db upgrade` derruba o serviço em laço. Mitigação: `ignore` no Dependabot e procedimento da seção 5; executado pelo deploy automático a partir do PR 39 (D12 de lá).
- **URL no argv do `db upgrade` (risco residual aceito):** o `mlflow db upgrade` só recebe a URL do banco (com a senha do papel `mlflow`) como argumento posicional. O procedimento garante que ela nunca vai para o argv nem para o histórico do host, mas, durante os segundos em que o upgrade roda, ela é legível no `/proc/<pid>/cmdline` do processo dentro do container. Aceito: processo curto, VPS de um único usuário, e quem consegue ler processos de container já está no grupo `docker` (equivalente a root).
- **Driver fora do Dependabot:** sem ecossistema `pip` (ADR 0006); vulnerabilidade aparece no Trivy `fs` e nos alertas do GitHub; atualização manual.
- **Imagem construída na VPS** até o PR 37; o PR 37 publica também `platform-mlflow` (`MLFLOW_IMAGE_DIGEST`).
- **Não verificado por execução nesta revisão** (os fatos vieram da revisão independente com acesso à web; o passo 0 confere localmente): digest e plataformas da imagem, Python 3.11 da base, ausência do driver, usuário padrão, nomes e formatos de `--allowed-hosts`, `--cors-allowed-origins`, das variáveis `MLFLOW_*` citadas, códigos `200`/`403`, `mlflow db upgrade <url>`, suporte a `postgresql+psycopg://`, nome do dependency no Dependabot para o GHCR, `--wait-timeout`.

Correção do índice: **aplicada** em 2026-11-08. A linha "P13" de "Pontos de decisão em aberto" bloqueia só o 42; o PR 29 fixa a versão do servidor e o item 31 a informa à cientista.

Perguntas ao usuário:

1. **P13 (ADR de execução de modelos): decidir agora ou antes do PR 42?** Inclui tipo de `conn` em `build_features`, objeto `model` em `predict`, saída estrita e versão do MLflow igual nos três lugares; precisa da concordância da cientista. **Recomendação (aceita):** antes do PR 42, como no índice; até lá, a regra prática é "cliente na mesma versão do servidor", comunicada no item 31.

Recomendações já aceitas pelo usuário (registradas): D1 a D10; não ligar a autenticação embutida do MLflow; não limitar tamanho de artefato no servidor (o item 31 pede à cientista que não registre dados brutos; o vigia de disco, PR 56, avisa acima de 80%); URL no argv do `db upgrade` dentro do container como risco residual.

## 10. Decisões que exigem ADR

**Nenhuma.** Exposição pelo ADR 0003 (5000 já na tabela dele) e pin pelo ADR 0006.

Exigiriam ADR (sinalizar, não escrever): porta fora de `127.0.0.1` ou `tailscale funnel`; ecossistema `pip` no Dependabot (item 2 do ADR 0006); artefatos em S3/MinIO ou backend fora da VPS. O ADR de execução de modelos (P13) já está na lista do índice, para antes do PR 42.
