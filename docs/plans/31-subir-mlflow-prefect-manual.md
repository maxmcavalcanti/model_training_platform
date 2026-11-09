# 31 — Subir MLflow e Prefect na VPS, liberar o MLflow para a cientista e medir a memória (manual)

> Executa: **usuário** (VPS e painel do Tailscale; agentes não têm acesso). Depende de: 28, 29 e 30 na `main`; checkpoint 28a feito; item 27 fechado (D+7, não antes de 2026-11-15), porque este item recria o `scheduler`.
> **Pré-condição de memória (decisão aceita pelo usuário em 2026-11-08): padrão, 28b feito (VPS com 2 GB); ou dispensa registrada pelo usuário com a medição do 28a de D+7 ou depois (`available` mediano em repouso de 700 MB ou mais e nenhum gatilho G1 a G5).** Sem uma das duas, não comece.
> Revisão 2026-11-08 (v2, com a revisão independente aceita pelo usuário). Em relação ao rascunho: senhas em hex; `.env` atualizado logo depois do `git pull`; `0008` antes do `create-databases`; prova de isolamento dos papéis; subida de um serviço por vez com medição; ACL com `tests`; 4200 não liberada à cientista; prova ponta a ponta do notebook; reboot; gatilhos; bloco inicial de sessão; janela proibida; nada de `down -v`. Na v2: pré-condição de memória; parada **obrigatória** depois do MLflow se a folga acabar; filtro do `ss` com loopback, `100.` e o IPv6 do Tailscale (`fd7a:115c:a1e0:`); recuperação do `TS_HOSTNAME`; variável `PREFECT_API_AUTH` e chamadas autenticadas ao Prefect; G1 com três medições; procedimento de `Detected out-of-date database schema`; diagnóstico de CORS (UI vazia e `403` em `/ajax-api`); uma senha por vez na tela; cliente `mlflow-skinny` opcional e limpeza da variável no notebook. Revisão final (mesmo dia): `/api/ready` e `/ui-settings` sem credencial (isentos no Prefect, plano 30); gatilho daqui leva ao 28b antes do item 35; URL do MLflow no argv do `db upgrade` dentro do container como risco residual aceito.

## 1. Objetivo

Levar MLflow e Prefect server à VPS (bancos e papéis criados, serviços `healthy` em `127.0.0.1`, expostos na tailnet por `tailscale serve`, API do Prefect autenticada), liberar o MLflow para a cientista pela ACL e provar o registro de um experimento do notebook.
Medir a memória com a stack nova e decidir, pelos gatilhos do 28a, se é preciso outro upgrade antes do item 35 (que acrescenta o worker).

## 2. Fora do escopo

- Qualquer mudança de código, compose, crontab ou `mem_limit` na VPS (correção é PR).
- Worker, flows, deployments e o cutover do agendador (PRs 32 a 36, item 35).
- Acesso da cientista à UI do Prefect (4200): Fase 4, item 50.
- Grafana (PR 47), backup (PR 57), alertas (PR 55).
- Atualizar `docs/acesso-cientista.md`, `docs/plataforma-ml.md` e o índice: PR só de `docs/**` depois (5.14).
- Upgrade de versão do MLflow ou troca de imagem do Prefect (procedimentos nos planos 29 e 30).

## 3. Fase do roadmap

Fase 3 — "MLflow, Prefect e CI/CD" → "libera o treino com registro": entrega o primeiro checkbox, "MLflow e Prefect no compose, só na tailnet (`tailscale serve`)". Rede só Tailscale (ADR 0003); deploy manual pela exceção do ADR 0004 (válida até o primeiro deploy automático do PR 39).

## 4. Arquivos a criar ou alterar

**Nenhum arquivo do repositório.** Na VPS (`/opt/platform`, usuário `deploy`) mudam: `infra/.env` (três variáveis novas e, se faltar, `TS_HOSTNAME`), imagens `platform-jobs`, `platform-scheduler`, `platform-mlflow` e `prefecthq/prefect`, schema do `ml` (`0007 → 0008`), bancos e papéis `mlflow` e `prefect`, volume `platform_mlflow_artifacts`, containers `mlflow` e `prefect-server`, `scheduler` recriado, estado do `tailscale serve`. No painel do Tailscale: a ACL.

### O que está na `main` e este item usa

- **PR 28:** `python -m ingestion create-databases` (idempotente; `DATABASE_URL_ADMIN`, `MLFLOW_DB_PASSWORD`, `PREFECT_DB_PASSWORD`; senha só `[A-Za-z0-9._~-]`, 16+). Papéis `mlflow` (`CONNECTION LIMIT 10`) e `prefect` (`20`), sem atributos elevados, donos dos bancos de mesmo nome, bancos fechados para `PUBLIC`. Logs: `service database ready: <nome>` e `create-databases ok: mlflow, prefect`. Migração `0008_ml_database_connect`: `CONNECT` no `ml` só para `ingestor`, `scientist`, `scorer` e `reader`.
- **PR 29:** `mlflow` (imagem `platform-mlflow`), `127.0.0.1:5000`, `mem_limit: 512m`, `--workers 1`, artefatos no volume `mlflow_artifacts` em `/artifacts`, hosts permitidos `mlflow:5000,localhost:5000,127.0.0.1:5000,${TS_HOSTNAME}:5000`, CORS `https://${TS_HOSTNAME}:5000`, healthcheck `/health` (`OK`), não-root. O MLflow não migra banco existente na subida.
- **PR 30:** `prefect-server` (`prefecthq/prefect:<X.Y.Z>-python3.12@sha256:...`), `127.0.0.1:4200`, `mem_limit: 640m`, `PREFECT_SERVER_UI_API_URL=https://${TS_HOSTNAME}:4200/api`, API autenticada por `PREFECT_SERVER_API_AUTH_STRING=${PREFECT_API_AUTH}` (formato `admin:<senha>`), healthcheck `/api/ready`. `GET /api/health`, `GET /api/ready`, `GET /ui-settings` e a UI respondem sem credencial; o resto de `/api` exige a credencial (plano 30, "Comportamento da autenticação"). Migra o próprio banco na subida.
- **`infra/scripts/tailscale-serve.sh`:** `reset`, `--https=8080`, `--https=5000`, `--https=4200`, `--tcp=5432`.

## 5. Passos

### Regras deste item

- Nada pesado entre **06:25 e 07:15** (horário de Brasília): build, pull, migração, `create-databases`, `dc up`, `tailscale-serve.sh`, reboot. Confira com `TZ=America/Sao_Paulo date '+%F %H:%M'`.
- Um comando pesado por vez. Nunca build durante um job.
- Nunca `dc down -v`, `docker volume rm`, `docker volume prune`, `docker image prune -a` nem `docker system prune -a`. Nunca `alembic downgrade` em produção. Nunca `dc config` sem `-q`. Não imprimir o `infra/.env` inteiro; senhas aparecem na tela uma por vez, só no 5.2.
- Nunca `tailscale funnel`, nunca porta em `0.0.0.0`: exposição fora da tailnet ou do loopback exige ADR (`AGENTS.md`, "Fronteira").
- Não editar código, compose ou crontab na VPS.
- **Parada obrigatória:** se depois do MLflow (5.7) a folga acabar, o Prefect não sobe.

### Bloco inicial de toda sessão SSH

Na VPS, como `deploy` (`ssh deploy@<host>.<tailnet>.ts.net`). **Toda sessão SSH nova** começa com este bloco:

```bash
cd /opt/platform
dc() { docker compose -f /opt/platform/infra/docker-compose.yml "$@"; }
q() { dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -A -t -F "|" -v ON_ERROR_STOP=1'; }
pcurl() { printf 'user = "%s"\n' "$(grep '^PREFECT_API_AUTH=' infra/.env | cut -d= -f2-)" | curl -K - -fsS "$@"; }
mkdir -p "$HOME/mem-checks"
memsnap() {
  f="$HOME/mem-checks/$(TZ=America/Sao_Paulo date +%F-%H%M)-$1.txt"
  {
    echo "== $1 $(date -u +%FT%TZ)"
    free -m
    echo; swapon --show
    echo; docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}'
    echo; vmstat 5 13 | tail -n 12
    echo; cat /proc/pressure/memory
  } 2>&1 | tee "$f"
  echo "saved: $f"
}
cgdir() {
  id=$(docker inspect -f '{{.Id}}' "$1") || return 1
  for d in "/sys/fs/cgroup/system.slice/docker-$id.scope" "/sys/fs/cgroup/docker/$id"; do
    if [ -d "$d" ]; then echo "$d"; return 0; fi
  done
  echo "cgroup of $1 not found" >&2
  return 1
}
mempeak() {
  for c in "$@"; do
    d=$(cgdir "$c") || continue
    anon=$(awk '/^anon /{print int($2/1048576)}' "$d/memory.stat")
    swap=0; [ -f "$d/memory.swap.current" ] && swap=$(( $(cat "$d/memory.swap.current") / 1048576 ))
    peak=n/a; [ -f "$d/memory.peak" ] && peak=$(( $(cat "$d/memory.peak") / 1048576 ))
    printf '%s current=%sMB anon=%sMB peak_with_cache=%sMB swap=%sMB max_hits=%s oom_kill=%s\n' "$c" \
      "$(( $(cat "$d/memory.current") / 1048576 ))" "$anon" "$peak" "$swap" \
      "$(awk '/^max /{print $2}' "$d/memory.events")" \
      "$(awk '/^oom_kill /{print $2}' "$d/memory.events")"
  done
}
```

`pcurl` chama a API do Prefect com a credencial do `.env` passada pelo stdin do `curl` (`-K -`): a senha não aparece no histórico nem na lista de processos. Só é necessário nas rotas autenticadas (`/api/...` fora de `/api/health` e `/api/ready`). Antes de qualquer comando pesado: `dc top scheduler | grep -c 'python -m ingestion'` → `0`.

### 5.1. Ponto de partida

- [ ] Pré-condição de memória: `free -m` mostra `Mem:` perto de `1900` (28b feito), **ou** você tem registrada a dispensa com a medição de D+7. Se não, pare e faça o 28b.
- [ ] Hora e estado:

  ```bash
  TZ=America/Sao_Paulo date '+%F %H:%M'
  dc ps --format '{{.Service}} {{.Status}}'
  dc run --rm -T jobs alembic current
  ```

  → `health`, `postgres` (`healthy`) e `scheduler` `Up`; `0007 (head)`.

- [ ] Fase 2 fechada: item 27, passo 5.8, concluído (data anotada). Se não, pare.
- [ ] Disco e memória antes:

  ```bash
  df -h /
  memsnap before-phase3
  mempeak platform-postgres-1 platform-scheduler-1
  ```

  → pelo menos 5 GB livres; anote `available`, swap e `anon`.

### 5.2. Código e `.env`

- [ ] Puxar a `main` e ler as versões fixadas:

  ```bash
  git pull --ff-only && git log -1 --oneline
  grep -m1 '^FROM' infra/mlflow/Dockerfile
  grep -m1 'prefecthq/prefect:' infra/docker-compose.yml
  ```

  → commit da `main` com os PRs 28 a 30; anote `v<X.Y.Z>` do MLflow e `<X.Y.Z>` do Prefect. Mudança local no `git pull`: pare e devolva com `git status`.

- [ ] Logo em seguida (até aqui o compose recusa comandos): o `TS_HOSTNAME` existe?

  ```bash
  grep -c '^TS_HOSTNAME=.*\.ts\.net$' infra/.env
  ```

  → `1`. Se der `0`, recupere o nome MagicDNS da própria VPS e confira:

  ```bash
  printf 'TS_HOSTNAME=%s\n' "$(tailscale status --json | python3 -c 'import json, sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')" >> infra/.env
  grep '^TS_HOSTNAME=' infra/.env
  ```

  → `TS_HOSTNAME=<host>.<tailnet>.ts.net`.

- [ ] Acrescente as três variáveis novas sem mostrá-las:

  ```bash
  grep -cE '^(MLFLOW_DB_PASSWORD|PREFECT_DB_PASSWORD|PREFECT_API_AUTH)=' infra/.env
  ```

  → `0` (se der mais, não acrescente de novo; confira só o formato abaixo).

  ```bash
  {
    printf 'MLFLOW_DB_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'PREFECT_DB_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'PREFECT_API_AUTH=admin:%s\n' "$(openssl rand -hex 24)"
  } >> infra/.env
  chmod 600 infra/.env
  grep -cE '^(MLFLOW|PREFECT)_DB_PASSWORD=[0-9a-f]{48}$' infra/.env
  grep -cE '^PREFECT_API_AUTH=admin:[0-9a-f]{48}$' infra/.env
  stat -c '%a %U' infra/.env
  ```

  → `2`, `1` e `600 deploy`.

- [ ] Nada do `.env.example` faltando (mostra só nomes) e compose válido:

  ```bash
  comm -13 <(grep -v '^#' infra/.env | cut -d= -f1 | grep . | sort -u) <(grep -v '^#' infra/.env.example | cut -d= -f1 | grep . | sort -u)
  dc config -q && echo ok
  ```

  → nenhuma linha no `comm`; `ok`.

- [ ] Guarde as três no gerenciador de senhas ("platform mlflow db", "platform prefect db", "platform prefect api"), **uma por vez**:

  ```bash
  grep '^MLFLOW_DB_PASSWORD=' infra/.env; read -r -p 'copied? ' _; clear
  grep '^PREFECT_DB_PASSWORD=' infra/.env; read -r -p 'copied? ' _; clear
  grep '^PREFECT_API_AUTH=' infra/.env; read -r -p 'copied? ' _; clear
  ```

  O histórico só tem `$(openssl ...)` e os `grep`, nunca os valores.

### 5.3. Imagens

Fora da janela, nenhum job rodando, um por vez (lento em 1 vCPU):

- [ ] `dc build jobs` → `jobs Built`.
- [ ] `dc build scheduler` → `scheduler Built`.
- [ ] `dc build mlflow` → `mlflow Built`.
- [ ] `dc pull prefect-server` → `prefect-server Pulled`.
- [ ] Conferir:

  ```bash
  docker image ls --format '{{.Repository}}:{{.Tag}} {{.Size}} {{.CreatedSince}}' | grep -E '^(platform-|prefecthq/prefect)'
  dc run --rm -T jobs alembic heads
  dc run --rm -T jobs python -m ingestion --help | grep -c create-databases
  df -h /
  ```

  → as três imagens `platform-*` recém-criadas e `prefecthq/prefect` com a tag fixada; `0008 (head)`; `1`; espaço anotado. Faltando disco: `docker image prune -f` e `docker builder prune -f` (nunca `-a`).

### 5.4. Migração `0008`

- [ ] Aplicar:

  ```bash
  dc run --rm -T jobs alembic upgrade head; echo "exit=$?"
  dc run --rm -T jobs alembic current
  ```

  → `Running upgrade 0007 -> 0008, ml database connect`, `exit=0`, `0008 (head)`. Falhou: não siga; devolva com o log.

- [ ] Os quatro papéis continuam entrando no `ml`:

  ```bash
  q <<'SQL'
  select r.rolname, has_database_privilege(r.rolname, 'ml', 'CONNECT')
  from pg_roles r where r.rolname in ('ingestor', 'scientist', 'scorer', 'reader') order by 1;
  SQL
  ```

  → `ingestor|t`, `reader|t`, `scientist|t`, `scorer|t`.

### 5.5. Bancos e papéis de serviço

- [ ] Criar e conferir a idempotência:

  ```bash
  dc run --rm -T jobs python -m ingestion create-databases; echo "exit=$?"
  dc run --rm -T jobs python -m ingestion create-databases; echo "exit=$?"
  ```

  → nas duas, `service database ready: mlflow`, `service database ready: prefect`, `create-databases ok: mlflow, prefect`, `exit=0`.

- [ ] Donos, atributos e isolamento:

  ```bash
  q <<'SQL'
  select datname, pg_get_userbyid(datdba) from pg_database where datname in ('mlflow', 'prefect') order by 1;
  select rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolconnlimit
  from pg_roles where rolname in ('mlflow', 'prefect') order by 1;
  select r.rolname, d.datname, has_database_privilege(r.rolname, d.datname, 'CONNECT')
  from pg_roles r cross join pg_database d
  where r.rolname in ('ingestor', 'scientist', 'scorer', 'reader', 'mlflow', 'prefect')
    and d.datname in ('ml', 'mlflow', 'prefect')
  order by 1, 2;
  SQL
  ```

  → `mlflow|mlflow` e `prefect|prefect`; `mlflow|f|f|f|f|f|10` e `prefect|f|f|f|f|f|20`; 18 linhas em que só são `t`: os quatro papéis em `ml`, `mlflow` em `mlflow`, `prefect` em `prefect`.

### 5.6. Agendador com a imagem nova

- [ ] Fora da janela, nenhum job rodando:

  ```bash
  dc up -d scheduler
  dc exec -T scheduler grep -v '^#' /app/infra/cron/crontab
  dc logs --since 5m scheduler | grep -E 'read crontab|level=(error|fatal)'
  ```

  → `Recreated` e `Started`; as três linhas (06:30, 06:45, 07:00); `read crontab` e nenhum `level=error`.

### 5.7. MLflow

- [ ] Subir só o MLflow (a primeira subida cria o schema; pode levar minutos):

  ```bash
  dc up -d --wait --wait-timeout 600 mlflow; echo "exit=$?"
  ```

  → `Container platform-mlflow-1 Healthy` e `exit=0` (sem `--wait-timeout` no compose da VPS, use `dc up -d --wait mlflow`). Falhou: 5.15.

- [ ] Loopback, usuário, versão e isolamento:

  ```bash
  curl -fsS http://127.0.0.1:5000/health; echo
  dc ps --format '{{.Ports}}' mlflow
  dc exec -T mlflow id -u
  dc exec -T mlflow python -c "import mlflow; print(mlflow.__version__)"
  dc exec -T mlflow python -c "import os; url = os.environ['MLFLOW_BACKEND_STORE_URI'].replace('+psycopg', '', 1).rsplit('/', 1)[0] + '/ml'; import psycopg; psycopg.connect(url)"
  ```

  → `OK`; `127.0.0.1:5000->5000/tcp`; diferente de `0`; a versão do 5.2; e o último **falha** com `permission denied for database "ml"` (o papel `mlflow` não entra no `ml`; a mensagem não traz a senha). Se a imagem usa `psycopg2` (fallback do plano 29), troque `import psycopg; psycopg.connect(url)` por `import psycopg2; psycopg2.connect(url)`.

- [ ] Memória com o MLflow:

  ```bash
  memsnap after-mlflow
  mempeak platform-postgres-1 platform-mlflow-1
  ```

  **Parada obrigatória:** se `available` ficou abaixo de **150 MB**, se o `vmstat` tem `si`/`so` diferente de `0` em 6 ou mais das 12 amostras, ou se `some avg300` passou de 10, **não suba o Prefect**. Deixe o MLflow no ar, faça o 28b (ou o 28b para 4 GB, se já está em 2 GB) e retome do 5.8.

### 5.8. Prefect server

- [ ] Subir:

  ```bash
  dc up -d --wait --wait-timeout 600 prefect-server; echo "exit=$?"
  ```

  → `Container platform-prefect-server-1 Healthy` e `exit=0`.

- [ ] Autenticação, loopback, usuário e banco:

  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:4200/api/flows/filter
  curl -fsS http://127.0.0.1:4200/api/ready; echo
  curl -fsS http://127.0.0.1:4200/ui-settings; echo
  pcurl -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:4200/api/flows/filter; echo
  dc ps --format '{{.Ports}}' prefect-server
  dc exec -T prefect-server id -u
  dc logs --since 15m prefect-server | grep -ciE 'too many connections|connection limit'
  ```

  → `401` (rota autenticada sem credencial); `/api/ready` responde sem credencial (isento); JSON com `"api_url"` igual a `https://<host>.<tailnet>.ts.net:4200/api`; `[]` (com credencial); `127.0.0.1:4200->4200/tcp`; diferente de `0`; `0`.

- [ ] Conexões e memória:

  ```bash
  q <<'SQL'
  select datname, usename, count(*) from pg_stat_activity where datname is not null group by 1, 2 order by 1, 2;
  SQL
  memsnap after-prefect
  mempeak platform-postgres-1 platform-mlflow-1 platform-prefect-server-1 platform-scheduler-1
  ```

  → `mlflow|mlflow` no máximo 10 e `prefect|prefect` no máximo 20; anote todos os números.

### 5.9. Nada escuta fora do loopback e da tailnet

- [ ] Na VPS:

  ```bash
  docker ps --format '{{.Names}} {{.Ports}}' | grep -c '0\.0\.0\.0'
  sudo ss -tlnH | awk '{print $4}' | grep -v -E '^(127\.|\[::1\]|100\.|\[fd7a:115c:a1e0:)'
  sudo ufw status verbose | head -5
  ```

  → `0`; só as duas linhas do `sshd` (`0.0.0.0:22` e `[::]:22`, bloqueadas pelo ufw, item 02); `Default: deny (incoming)`. Qualquer outra linha: pare e devolva.

### 5.10. `tailscale serve`

- [ ] Fora da janela (o `reset` derruba por segundos a 5432 da tailnet; avise a cientista se ela estiver conectada):

  ```bash
  infra/scripts/tailscale-serve.sh
  tailscale serve status
  ```

  → `https://<host>.<tailnet>.ts.net:8080`, `:5000` e `:4200` apontando para `http://127.0.0.1:<mesma porta>`, e `tcp` 5432 para `127.0.0.1:5432`. Nenhuma linha de `funnel`.

### 5.11. ACL do Tailscale

- [ ] Em Access controls, ajuste as regras da VPS (mantenha o resto do policy file; troque os e-mails):

  ```jsonc
  "acls": [
    // você: SSH, saúde, Postgres, MLflow e Prefect
    { "action": "accept", "src": ["<seu-email>"], "dst": ["tag:platform:22,8080,5432,5000,4200"] },
    // a cientista: Postgres e MLflow (Prefect e Grafana ficam para o item 50)
    { "action": "accept", "src": ["group:scientists"], "dst": ["tag:platform:5432,5000"] }
  ],
  "tests": [
    { "src": "<seu-email>", "accept": ["tag:platform:5000", "tag:platform:4200"] },
    {
      "src": "<email-da-cientista>",
      "accept": ["tag:platform:5432", "tag:platform:5000"],
      "deny": ["tag:platform:22", "tag:platform:8080", "tag:platform:4200"]
    }
  ]
  ```

  O painel roda os `tests` ao salvar e recusa a política se algum falhar. Se o policy file usa `grants`, escreva o equivalente. Sem regra "allow all" nem `autogroup:member` para a VPS (plano 12, pergunta 4).

### 5.12. Do notebook (na tailnet)

No Windows use `curl.exe`.

- [ ] Saúde pela tailnet, com certificado válido:

  ```bash
  curl.exe -fsS https://<host>.<tailnet>.ts.net:5000/health
  curl.exe -fsS https://<host>.<tailnet>.ts.net:4200/api/ready
  ```

  → `OK` e a resposta de pronto do Prefect (sem credencial: `/api/ready` é isento).

- [ ] Navegador:
  - `https://<host>.<tailnet>.ts.net:5000`: a UI do MLflow **lista** experimentos (ao menos `Default`). UI carregada mas vazia, com `403` nas chamadas a `/ajax-api` no console (F12) → falta a origem CORS ou o host na lista (5.15).
  - `https://<host>.<tailnet>.ts.net:4200`: a UI do Prefect pede a credencial (entre o que o plano 30, passo 0, confirmou: o valor inteiro `admin:<senha>` ou só a senha); depois, o painel sem aviso de "can't connect to Server API"; na página de eventos, sem erro de WebSocket no console. Anote se houver.

- [ ] Prova ponta a ponta do registro (PowerShell; troque `<X.Y.Z>` pela versão do 5.2; rode fora de um diretório com `pyproject.toml`; o pacote `mlflow-skinny==<X.Y.Z>` serve no lugar de `mlflow` e é mais leve):

  ```powershell
  $env:MLFLOW_TRACKING_URI = "https://<host>.<tailnet>.ts.net:5000"
  uv run --no-project --with "mlflow==<X.Y.Z>" python -c "import mlflow; mlflow.set_experiment('platform-smoke'); r = mlflow.start_run(); mlflow.log_metric('x', 1.0); mlflow.log_text('ok', 'a.txt'); mlflow.end_run(); p = mlflow.artifacts.download_artifacts(run_id=r.info.run_id, artifact_path='a.txt'); print('artifact:', open(p).read()); c = mlflow.MlflowClient(); c.create_registered_model('platform_smoke'); print('registered:', c.get_registered_model('platform_smoke').name); c.delete_registered_model('platform_smoke')"
  Remove-Item Env:MLFLOW_TRACKING_URI
  ```

  → `artifact: ok` e `registered: platform_smoke`. Na UI, `platform-smoke` com a métrica `x` e o artefato `a.txt`. Na VPS: `dc exec -T mlflow sh -c 'find /artifacts -name a.txt | grep -c .'` → `1` ou mais.

- [ ] De fora da tailnet (celular no 4G, Tailscale desligado): `curl -s --max-time 5 http://<ip-publico>:5000/health` e `http://<ip-publico>:4200/api/health` → falham.

### 5.13. Reboot e memória final

- [ ] Fora da janela: `sudo reboot`. Dois a três minutos depois, **sem entrar na VPS**, do notebook: `curl.exe -fsS https://<host>.<tailnet>.ts.net:8080/health` → `ok`, `curl.exe -fsS https://<host>.<tailnet>.ts.net:5000/health` → `OK` e `curl.exe -fsS https://<host>.<tailnet>.ts.net:4200/api/ready` → pronto.
- [ ] Na VPS (sessão nova, bloco inicial): `dc ps --format '{{.Service}} {{.Status}}'` → `health`, `postgres`, `mlflow`, `prefect-server` `healthy` e `scheduler` `Up`; `tailscale serve status` igual ao 5.10.
- [ ] Repouso (15 minutos ou mais depois do boot), **três** medições, pelo menos uma em outro dia: `memsnap phase3-rest-1`, `memsnap phase3-rest-2`, `memsnap phase3-rest-3`, cada uma seguida de `mempeak $(docker ps --format '{{.Names}}')`.
- [ ] Janela dos jobs com a stack nova: agende o amostrador do 28a, seção 5.3 (entre 07:20 e 23:59; o `$HOME/mem-checks/sample.sh` já existe), e no dia seguinte, depois das 07:20 BRT:

  ```bash
  f="$HOME/mem-checks/$(TZ=America/Sao_Paulo date +%F)-window.txt"
  echo "min MemAvailable MB: $(sort -k2 -n "$f" | head -1)"
  echo "max scheduler anon MB: $(sort -k4 -n "$f" | tail -1)"
  mempeak platform-postgres-1 platform-mlflow-1 platform-prefect-server-1 platform-scheduler-1
  dc logs --since 2h scheduler | grep -E 'weather-forecast ok|weather-observed ok|ons-load ok|failed|level=error'
  sudo journalctl -k -b --no-pager | grep -E 'Out of memory: Killed process' | grep -vc 'Memory cgroup'
  ```

  → as três linhas `... ok`, nenhuma `failed`; mínimo e `anon` anotados.

- [ ] Gatilhos do 28a, seção 5.6: G1 `available` abaixo de 150 MB em 2 das 3 medições `phase3-rest-*`; G2 swap ativo (`si`/`so` em 6+ de 12 amostras, em 2 dias) ou `Swap: used` crescendo 200+ MB; G3 OOM global maior que `0`; G4 mínimo da janela abaixo de 50 MB; G5 `some avg300` acima de 10 em 2 das 3. Qualquer um → 28b (para 4 GB, se já está em 2 GB; ou o 28b padrão, se foi dispensado) **antes do item 35** (que acrescenta o worker; os PRs 32 a 34 são só código e podem seguir). `anon` de um container acima de 85% do seu `mem_limit` (`mlflow` 435 MB, `prefect-server` 544 MB, `postgres` 218 MB) ou `max_hits` crescendo → PR subindo aquele limite.

### 5.14. Aviso à cientista e depois

- [ ] Enviar (ajuste o tom):

  > **MLflow no ar.** Endereço: `https://<host>.<tailnet>.ts.net:5000`, só pela tailnet (o mesmo acesso do Postgres; a ACL agora libera a porta 5000 para você). Sem usuário nem senha: defina só `MLFLOW_TRACKING_URI=https://<host>.<tailnet>.ts.net:5000`.
  >
  > - Use o cliente na **mesma versão do servidor**: `mlflow==<X.Y.Z>` (ou `mlflow-skinny==<X.Y.Z>`, mais leve, se não precisar da UI local). Versões diferentes podem gravar ou ler o registry de forma incompatível.
  > - Artefatos sobem pelo próprio servidor (sem credencial de S3). O disco da VPS é pequeno: registre modelos, métricas e gráficos, não cópias de dados brutos.
  > - O servidor não tem login: o que você registra é visível e editável por quem a ACL deixa chegar à porta 5000 (hoje, só você e eu). O alias `champion` é o deploy de um modelo: só mude quando quiser que ele vá para produção (o score diário entra na Fase 4).
  > - Nome do modelo registrado = nome do módulo (`load_d1`, `rain_d1`).
  > - A interface do Prefect fica para quando o job do seu modelo rodar lá (Fase 4).

- [ ] Depois (fora deste item): PR só de `docs/**` marcando o primeiro checkbox da Fase 3 em `docs/plataforma-ml.md` (data e números de memória, sem hostname) e acrescentando o MLflow em `docs/acesso-cientista.md`; se houve 28b, atualizar a P3 do índice.

### 5.15. Se algo falhar

Não mexa em código, compose ou crontab na VPS. Guarde o log (`... 2>&1 | tee /tmp/<nome>.log`) e devolva para o planejamento.

- **`required variable ... is missing`** em qualquer `dc`: faltou o 5.2; refaça-o.
- **`create-databases` com `exit=1` por senha:** o valor não é hex de 48; apague a linha com um editor, gere de novo só aquela com o `printf` do 5.2 e rode o `create-databases` (ele troca a senha no banco).
- **MLflow em laço de reinício com `Detected out-of-date database schema`** no `dc logs mlflow` (banco de uma versão mais antiga do MLflow): pare o laço, faça o dump e migre, nesta ordem:

  ```bash
  dc stop mlflow
  mkdir -p "$HOME/backups"
  dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d mlflow -Fc' > "$HOME/backups/mlflow-$(date +%F).dump"
  dc run --rm --no-deps mlflow sh -c 'exec mlflow db upgrade "$MLFLOW_BACKEND_STORE_URI"'
  dc up -d --wait mlflow
  ```

  → o `db upgrade` termina sem erro e o serviço fica `healthy`. Não ponha isso no compose. A URL do banco é expandida dentro do container: nunca aparece no argv nem no histórico do host, mas fica no argv do processo `mlflow db upgrade` dentro do container enquanto ele roda (o comando só aceita a URL como argumento; risco residual aceito, plano 29).
- **UI do MLflow pela tailnet vazia e `403` em `/ajax-api`**, com `/health` local `OK`: a origem CORS (`https://<host>.<tailnet>.ts.net:5000`) ou o host com a porta não estão nas listas do serviço; correção é PR no compose (plano 29).
- **MLflow ou Prefect não fica `healthy`:** `dc logs --since 15m <serviço>`. `password authentication failed`: rode o `create-databases` de novo. `permission denied to create extension`: devolva. Morto por memória (`exit 137`, `oom_kill` no `mempeak`): `dc stop <serviço>` (nunca `down -v`) e devolva com o `memsnap`.
- **UI do Prefect sem falar com a API:** confira o `api_url` do `/ui-settings` (5.8) e a credencial digitada; correção é PR.
- **Desistir por ora:** `dc stop prefect-server mlflow`. Bancos e volume ficam; a ACL pode continuar.

## 6. Critérios de pronto

| Onde | Comando | Saída esperada |
| --- | --- | --- |
| VPS | `free -m` (pré-condição) | `Mem:` perto de `1900` (28b feito) ou dispensa registrada com a medição de D+7 |
| VPS | `dc run --rm -T jobs alembic current` | `0008 (head)` |
| VPS | consulta de isolamento do 5.5 | 18 linhas; só `t` para os 4 papéis em `ml`, `mlflow` em `mlflow` e `prefect` em `prefect` |
| VPS | `dc ps --format '{{.Service}} {{.Status}}'` | `mlflow`, `prefect-server`, `health`, `postgres` `healthy`; `scheduler` `Up` |
| VPS | `curl` sem credencial em `/api/flows/filter` (5.8) | `401` |
| VPS | `docker ps --format '{{.Names}} {{.Ports}}' \| grep -c '0\.0\.0\.0'` | `0` |
| VPS | filtro do `ss` do 5.9 | só as duas linhas do `sshd` |
| VPS | `tailscale serve status` | 8080, 5000, 4200 (HTTPS) e 5432 (TCP), todos para `127.0.0.1` |
| Notebook | `curl.exe -fsS https://<host>.<tailnet>.ts.net:5000/health` | `OK` |
| Notebook | `curl.exe -fsS https://<host>.<tailnet>.ts.net:4200/api/ready` | resposta de pronto |
| Notebook | UI do MLflow pela tailnet | lista experimentos (sem `403` em `/ajax-api`) |
| Notebook | prova ponta a ponta do 5.12 | `artifact: ok` e `registered: platform_smoke` |
| Fora da tailnet | `curl -s --max-time 5 http://<ip-publico>:5000/health` | Falha |
| Painel do Tailscale | `tests` da ACL do 5.11 | Política salva |
| Após reboot | os três `curl.exe` do 5.13, sem entrar na VPS | `ok`, `OK`, pronto |
| VPS, dia seguinte | log do `scheduler` do 5.13 | 3 linhas `... ok`, nenhuma `failed` |
| Memória | gatilhos G1 a G5 do 5.13 | "Sem gatilho" ou "G<n>: 28b antes do item 35", com os números |
| Fora da VPS | aviso do 5.14 | Enviado, data anotada |

## 7. Testes necessários

`não`: procedimento manual na VPS e no painel do Tailscale; código, migração e serviços já testados no CI dos PRs 28 a 30.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

Riscos:

- **Memória:** mesmo em 2 GB, a stack da Fase 3 ocupa boa parte da RAM e o item 35 acrescenta o worker. Mitigação: um serviço por vez, parada obrigatória depois do MLflow, medição com gatilhos.
- **Janela entre o `git pull` e o `.env`:** até o 5.2 terminar, nenhum `dc` funciona. Faça em sequência.
- **Recriação do `scheduler`** apaga o log dele; por isso a Fase 2 precisa estar fechada.
- **Sem papéis no MLflow nem no Prefect:** a ACL e, no Prefect, a credencial única são as barreiras; os `tests` da ACL travam regressão no painel.
- **`reset` do `tailscale serve`** derruba por segundos as conexões na 5432.
- **Credencial do Prefect no notebook:** só a UI e as rotas autenticadas a pedem; nunca a passe na linha de comando.
- **URL do MLflow no argv do `db upgrade` dentro do container** (só no 5.15): risco residual aceito, como no plano 29.
- **Não verificado por execução nesta revisão:** o formato da credencial na UI do Prefect, o corpo de `/api/ready`, a sintaxe atual de `tests` da ACL e o WebSocket pelo `tailscale serve`. Os CIs dos PRs 29 e 30 confirmam os endpoints (inclusive a isenção de `/api/ready`) antes deste item.

Recomendações aceitas pelo usuário em 2026-11-08 (registradas):

1. Reconstruir e recriar o `scheduler` junto (imagens `jobs` e `scheduler` iguais).
2. Não liberar a 4200 à cientista agora (item 50).
3. Guardar as três credenciais novas no gerenciador.
4. Gatilho já com o MLflow: parar, fazer o 28b e retomar do 5.8 (parada obrigatória).
5. Pré-condição de memória: 28b padrão antes deste item, ou dispensa registrada.

## 10. Decisões que exigem ADR

**Nenhuma.** O item aplica, pelo procedimento interino do ADR 0004, o que os PRs 28 a 30 já mergearam; a exposição segue o ADR 0003. Nada muda em `raw`, `ref` ou no contrato.

Exigiriam ADR (sinalizar, não escrever): publicar MLflow ou Prefect fora da tailnet ou do loopback (porta pública, `tailscale funnel`, proxy público); ligar o Tailscale SSH; tirar MLflow ou Prefect da VPS.
