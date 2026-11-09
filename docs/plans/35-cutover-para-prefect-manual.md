# 35 — Cutover do agendamento: supercronic → Prefect (manual)

> Executa: **usuário** (VPS e Tailscale; agentes não têm acesso à VPS). Depende de: item 27 concluído (prova da Fase 2 em D+7 pelo log do `scheduler`, que este item para), 28a e 31 feitos (MLflow e Prefect server no ar, memória medida), PRs 32, 33 e 34 na `main` e o ADR obrigatório "Agendamento e execução pelo Prefect" (plano 33, seção 10) mergeado.
> Revisão 2026-11-08: reescrito contra a `main` em `05c32c9` e contra os planos 32 a 34 revisados. Revisão 2 (mesmo dia): aplica a revisão independente aceita pelo usuário. Inclui conferência pelo banco e pelo estado `Completed` além dos greps de log, execuções disparadas fora do container do worker (risco de OOM no cgroup dele), recuperação do dia antes de religar o supercronic, conferência de execuções `Late` depois do registro e reboot com conferência explícita. Alinhamento entre planos (mesmo dia): a credencial da API no `infra/.env` é a `PREFECT_API_AUTH` do item 31 (nenhuma variável nova); gatilhos de memória do 28a; status do ADR 0004 no PR de docs depois do primeiro deploy automático. Revisão final (mesmo dia): a medição de memória da 5.5 usa o amostrador `sample.sh` do 28a com o cgroup do worker; o dia C termina às 20:00 BRT.

## 1. Objetivo

Passar as três ingestões diárias do supercronic para os deployments do Prefect na VPS, com a troca entre dois dias: o dia C fica todo com o supercronic, e a partir de C+1 só o Prefect agenda. Nenhum dia agendado duas vezes, nenhum dia sem agenda.
Provar por dois dias seguidos (C+1 e C+2), incluindo um reboot, que o Prefect agenda sozinho, e só então liberar o PR 36. Até lá, o caminho de volta fica pronto.

## 2. Fora do escopo

- Qualquer mudança de código, compose ou crontab, inclusive na VPS. Correção é PR na `main`.
- Remover o `scheduler`, o crontab e o supercronic (PR 36, depois deste item).
- Ajustar horários ou janelas (item 18 e PR próprio). Alertas (PR 55): até lá, a conferência diária é manual (5.9).
- Backfill: continua pela CLI no `jobs`, como nos itens 23 e 27.
- Upgrade da VPS (item 28b): este item só mede e decide se o gatilho disparou.

## 3. Fase do roadmap

Fase 3 — "MLflow, Prefect e CI/CD", item "Ingestões migradas para flows do Prefect" (`docs/plataforma-ml.md`, "Roadmap").

## 4. Arquivos a criar ou alterar

**Nenhum arquivo do repositório.** Tudo acontece na VPS (`/opt/platform`, usuário `deploy`): imagens `platform-jobs` e `platform-prefect-worker`, container `prefect-worker`, deployments e work pool no server Prefect, e o container `scheduler` parado (não removido).

### Por que é manual

Até o primeiro deploy automático do PR 39, atualizar a VPS é manual, por SSH pela tailnet: `git pull`, build na VPS e `docker compose up` (ADR 0004; `.claude/rules/infra.md`: "Quem aplica esse deploy é o usuário, nunca um agente"). O ADR 0004 diz que o agendador interino é substituído pelos deployments do Prefect e que o PR 36 o remove "depois do cutover manual (item 35)".

### O que está na `main` e este item usa

- **Crontab vigente** (`/app/infra/cron/crontab` no `scheduler`, horários `America/Sao_Paulo`): `30 6` `weather-forecast`, `45 6` `weather-observed`, `0 7` `ons-load`.
- **Deployments** (`flows/deployments.py`, PR 33): `ingest_weather_forecast/production` `30 6 * * *`, `ingest_weather_observed/production` `45 6 * * *`, `ingest_ons_load/production` `0 7 * * *`, todos em `America/Sao_Paulo`, pool `platform` (`process`, limite 1), entrypoint `flows.ingest.<flow>`, sem parâmetros (janela diária). `python -m flows.deployments` registra e é idempotente.
- **Worker** (`infra/docker-compose.yml`, PR 34): serviço `prefect-worker`, `restart: unless-stopped`, `mem_limit: 768m`, uma execução por vez, só `DATABASE_URL` do `ingestor`, `PREFECT_API_URL=http://prefect-server:4200/api` e a credencial da API (`PREFECT_API_AUTH_STRING` dentro do container, vinda de `PREFECT_API_AUTH` do `infra/.env`, a mesma do `prefect-server` desde o item 31). O `jobs` recebe as mesmas duas variáveis do Prefect. Os logs INFO dos jobs (`weather-forecast ok: ...`) aparecem no log do worker e na UI, graças ao `PREFECT_LOGGING_EXTRA_LOGGERS=ingestion` (PR 34) junto com o nível INFO fixado em `flows/ingest.py` (PR 32). Se essas linhas não aparecerem, a conferência pelo banco e pelo estado `Completed` continua valendo (cada passo traz as duas).
- **Idempotência** (por que repetir um dia não estraga dado): `raw.weather_forecast` usa `ON CONFLICT DO NOTHING` (o primeiro snapshot do dia vence; a segunda execução grava 0 linhas); `raw.weather_observed` e `raw.ons_daily_load` usam upsert por chave (reescrevem a janela e atualizam `ingested_at`).
- **Logs de sucesso dos jobs:**
  - `weather-forecast ok: 4 locations, <n> rows inserted, <28 - n> already existed`
  - `weather-observed ok: 4 locations, 40 rows written from <hoje − 10> to <ontem>`
  - `ons-load ok: <n> rows written from <hoje − 29> to <hoje>, last date <d>`
- **Medição de memória:** o bloco inicial do 28a (`docs/plans/28a-checkpoint-ram-vps-manual.md`, funções `memsnap`, `cgdir` e `mempeak`) e o amostrador `$HOME/mem-checks/sample.sh` criado no 28a, seção 5.3 (uma linha a cada 5 s: hora UTC, `MemAvailable` MB, `SwapFree` MB e o `anon` MB de cada cgroup passado).

## 5. Passos

### Regras deste item

- Nada de build, `up`, registro, execução manual ou reboot entre **06:25 e 07:15 BRT** (confira com `TZ=America/Sao_Paulo date '+%F %H:%M'`).
- O dia C é escolhido de modo que os passos 5.1 a 5.6 caibam entre 07:15 e **20:00 BRT** do mesmo dia. Se não couberem, pare no ponto em que estiver, aplique 5.10.1 antes das 06:25 do dia seguinte e recomece outro dia.
- **Do dia C até o deploy do PR 36, nunca rode `dc up -d` sem nome de serviço.** O compose ainda tem o `scheduler`, e um `up -d` geral o religaria (dupla ingestão). Sempre nomeie o serviço.
- **Nunca dispare execução de flow com `dc exec ... prefect-worker`.** O CLI rodaria dentro do cgroup de 768m do worker, somado ao subprocesso do flow, e poderia causar OOM. Execuções são disparadas pela UI ou por `dc run --rm -T jobs prefect deployment run ... --watch --watch-timeout 900` (container separado, com o próprio `mem_limit`). O atalho `pf` (exec no worker) serve só para comandos curtos de consulta ou de apagar, e só com nada `Running`.
- Nunca `dc down -v` nem `docker volume rm` (sem backup até o PR 57). Nunca `dc config` sem `-q`. Não ler nem imprimir `infra/.env` nem o valor de `DATABASE_URL`, `PREFECT_API_AUTH` ou `PREFECT_API_AUTH_STRING`.
- Um comando pesado por vez (build, execução, backfill).

### Bloco inicial de toda sessão SSH

Na VPS, como `deploy` (`ssh deploy@<host>.<tailnet>.ts.net`): primeiro o bloco inicial do 28a (define `dc`, `q`, `memsnap`, `cgdir` e `mempeak`), depois:

```bash
pf() { dc exec -T prefect-worker prefect "$@"; }               # só consultas curtas, nada Running
pfrun() { dc run --rm -T jobs prefect deployment run "$1" --watch --watch-timeout 900; }
```

`q` é o `psql` de admin pelo socket do container (como no item 27). `pf` roda o CLI do Prefect dentro do worker, que já tem URL e credencial da API, sem subir container novo; com o worker parado, use `dc run --rm -T jobs prefect ...`. `pfrun` dispara e acompanha uma execução num container `jobs` separado. Nas consultas, "hoje" em Brasília é `(now() at time zone 'America/Sao_Paulo')::date`.

### 5.1. Pré-condições (dia C, depois das 07:15 BRT)

- [ ] Hora fora da janela proibida e antes das 20:00 BRT: `TZ=America/Sao_Paulo date '+%F %H:%M'`.
- [ ] O item 27 está fechado (prova de D+7 feita) e o 31 também: `dc ps --format '{{.Service}} {{.Status}}'` → `postgres`, `prefect-server` e `mlflow` `Up ... (healthy)` e `scheduler Up`.
- [ ] As três execuções de **hoje** pelo supercronic terminaram bem:

  ```bash
  dc logs --since 3h scheduler | grep -E 'weather-forecast ok|weather-observed ok|ons-load ok|failed|level=error'
  dc top scheduler | grep -c 'python -m ingestion'
  ```

  → uma linha `ok` de cada job, nenhuma `failed`/`level=error`; e `0` (nada rodando). Se algum falhou hoje, resolva primeiro como no item 27 (5.10) e deixe o cutover para outro dia.
- [ ] Snapshot de hoje completo (é a referência de "não duplicou"):

  ```bash
  q <<'SQL'
  select issued_at, count(*), min(ingested_at), max(ingested_at) from raw.weather_forecast
  where issued_at = (now() at time zone 'America/Sao_Paulo')::date group by 1;
  SQL
  ```

  → `<hoje>|28|<t1>|<t2>`, com `t1` e `t2` por volta das 09:30 UTC (06:30 BRT). Anote `t1` e `t2`.
- [ ] Espaço e memória: `df -h / && free -m` → pelo menos 2 GB livres em `/`; anote `available`.

### 5.2. Atualizar o código e construir as imagens

- [ ] `git pull --ff-only && git log --oneline -15` → a `main` contém os merges dos PRs 32, 33 e 34. Se o `git pull` reclamar de mudança local, pare e devolva com `git status`.
- [ ] `dc config -q && echo ok` → `ok`. O PR 34 não cria variável nova no `infra/.env`: o worker e o `jobs` usam a `PREFECT_API_AUTH` que o item 31 acrescentou. Se o `config` reclamar de `PREFECT_API_AUTH` ausente, o item 31 não foi concluído: pare e volte a ele (5.2 de lá). Não imprima valores.
- [ ] Construir só o que muda (o `scheduler` mantém a imagem e o container atuais, que são o caminho de volta): `dc build jobs prefect-worker` → termina sem erro. É lento em 1 vCPU; anote o tempo.
- [ ] Versões alinhadas:

  ```bash
  dc exec -T prefect-server prefect version | head -1
  dc run --rm -T jobs prefect version | head -1
  dc run --rm -T jobs python -c "import flows.ingest, flows.deployments; print('ok')"
  ```

  → as duas primeiras linhas iguais (`Version: <X.Y.Z>`); `ok`.

### 5.3. Subir o worker

- [ ] `dc up -d prefect-worker` → `Container platform-prefect-worker-1  Started`. Se aparecer `Recreated` em `postgres` ou `prefect-server`, anote.
- [ ] `dc ps --format '{{.Service}} {{.Status}}' prefect-worker` → `prefect-worker Up ... (healthy)` (pode levar até ~1 min).
- [ ] Credenciais e usuário (sem imprimir senha):

  ```bash
  dc exec -T prefect-worker whoami
  dc exec -T prefect-worker sh -c 'printenv DATABASE_URL | cut -d@ -f1 | cut -d: -f1,2'
  dc exec -T prefect-worker printenv DATABASE_URL_ADMIN; echo "exit=$?"
  dc exec -T prefect-worker printenv PREFECT_API_URL
  dc exec -T prefect-worker sh -c 'test -n "$PREFECT_API_AUTH_STRING" && echo auth-set'
  ```

  → `app`; `postgresql+psycopg://ingestor`; só `exit=1`; `http://prefect-server:4200/api`; `auth-set`.
- [ ] Log do worker: `dc logs --since 5m prefect-worker` → uma linha de worker iniciado no pool `platform`; nenhum `Traceback`.
- [ ] Os subcomandos do CLI que este item usa existem na versão instalada:

  ```bash
  pf deployment --help | grep -E 'ls|inspect|run|delete'
  pf deployment run --help | grep -E -- '--param|--watch|--watch-timeout'
  pf flow-run --help | grep -E 'ls|delete|cancel'
  ```

  → as linhas aparecem. Se faltar `--watch`, dispare e acompanhe as execuções da 5.5 pela UI.

### 5.4. Registrar os deployments

- [ ] `dc run --rm -T jobs python -m flows.deployments; echo "exit=$?"` → três linhas de log (uma por deployment, com o cron) e `exit=0`.
- [ ] Conferir:

  ```bash
  pf deployment ls
  for d in ingest_weather_forecast ingest_weather_observed ingest_ons_load; do
    pf deployment inspect "$d/production" | grep -E "cron|timezone|active|work_pool_name|entrypoint"
  done
  pf work-pool inspect platform | grep -E "type|concurrency_limit"
  pf flow-run ls --limit 10
  ```

  → os três deployments; para cada um, o cron da tabela da seção 4, `America/Sao_Paulo`, ativo, `platform` e `flows.ingest.<flow>`; pool `process` com limite `1`. Na lista de flow runs, só execuções futuras (`Scheduled`, a partir de amanhã). Se aparecer uma execução de **hoje** já `Late` ou `Running`, o server criou uma execução para um horário já passado: ela roda (ou já rodou) e é inofensiva, porque é uma reexecução idempotente do dia (a previsão grava 0 linhas). Deixe-a terminar e confira no log do worker antes de seguir; ela conta como uma das execuções de verificação da 5.5.
- [ ] Na UI (`https://<host>.<tailnet>.ts.net:4200`, de um dispositivo na tailnet e com a credencial da API): o work pool `platform` tem um worker `Online`; cada deployment mostra a **próxima execução amanhã** (06:30, 06:45 e 07:00, fuso `America/Sao_Paulo`).

### 5.5. Execuções de verificação (reexecução idempotente de hoje)

Elas provam o caminho completo (server → worker → subprocesso → banco com `ingestor`) antes de a primeira execução agendada depender disso. São reexecuções do dia já coletado, não ingestões novas: a previsão grava 0 linhas.

- [ ] Ligue o amostrador do 28a em segundo plano por 15 minutos, com o cgroup do worker (coluna 4) e do `postgres` (coluna 5); ele lê só `/proc/meminfo` e `memory.stat`, barato em 1 vCPU:

  ```bash
  out="$HOME/mem-checks/$(TZ=America/Sao_Paulo date +%F-%H%M)-cutover.txt"
  "$HOME/mem-checks/sample.sh" 900 "$out" "$(cgdir platform-prefect-worker-1)" "$(cgdir platform-postgres-1)" &
  echo "sampler -> $out"
  ```

- [ ] Uma de cada vez, esperando terminar (pela UI, botão "Run" sem parâmetros, ou pelo `pfrun`, que usa um container `jobs` separado, **nunca** `pf`):

  ```bash
  pfrun 'ingest_weather_forecast/production'; echo "exit=$?"
  pfrun 'ingest_weather_observed/production'; echo "exit=$?"
  pfrun 'ingest_ons_load/production'; echo "exit=$?"
  ```

  → cada um termina `Completed` e `exit=0` (ou `Completed` na UI).
- [ ] Estado: `pf flow-run ls --limit 5` (com nada `Running`) ou a UI → as três execuções de verificação `Completed`, nenhuma `Failed` ou `Crashed`.
- [ ] Log do worker:

  ```bash
  dc logs --since 15m prefect-worker | grep -E 'weather-forecast ok|weather-observed ok|ons-load ok|Traceback|Failed|Crashed'
  ```

  → `weather-forecast ok: 4 locations, 0 rows inserted, 28 already existed`, `weather-observed ok: 4 locations, 40 rows written ...` e `ons-load ok: ...`; nenhum `Traceback`, `Failed` ou `Crashed`. Se as linhas `ok` não aparecerem e os três estados forem `Completed`, o problema é só de nível de log (PR 32/34). Siga pela conferência do banco abaixo e anote para um PR de correção; isso não bloqueia o cutover.
- [ ] Banco (vale com ou sem as linhas de log):

  ```bash
  q <<'SQL'
  select issued_at, count(*), min(ingested_at), max(ingested_at) from raw.weather_forecast
  where issued_at = (now() at time zone 'America/Sao_Paulo')::date group by 1;
  select count(*), min("date"), max("date") from raw.weather_observed where ingested_at > now() - interval '20 minutes';
  select count(*), min("date"), max("date") from raw.ons_daily_load where ingested_at > now() - interval '20 minutes';
  SQL
  ```

  → previsão `<hoje>|28|<t1>|<t2>`, **idêntica à 5.1** (nada reescrito); observado `40|<hoje − 10>|<ontem>`; ONS com `count` > 0, `min` = `<hoje − 29>` e `max` no máximo 5 dias antes de hoje.
- [ ] Memória (depois que o amostrador terminar, ou `kill %1` se as execuções acabaram antes):

  ```bash
  echo "min MemAvailable MB: $(sort -k2 -n "$out" | head -1)"
  echo "min SwapFree MB: $(sort -k3 -n "$out" | head -1)"
  echo "max worker anon MB: $(sort -k4 -n "$out" | tail -1)"
  mempeak platform-prefect-worker-1 platform-prefect-server-1 platform-mlflow-1 platform-postgres-1
  sudo journalctl -k -b --no-pager | grep -E 'Out of memory: Killed process' | grep -vc 'Memory cgroup'
  ```

  → anote os números. **Parada imediata (28b)**: menor `MemAvailable` abaixo de 50 MB (G4 do 28a), `SwapFree` caindo de forma contínua entre as amostras ou OOM global maior que `0` (G3). Se disparar, faça 5.10.1 e o 28b (para 4 GB, se já está em 2 GB) antes de tentar de novo. `anon` do worker acima de 85% do `mem_limit` (653 MB), `max_hits` crescendo ou `oom_kill` maior que `0` no worker, com o host folgado: não é gatilho de upgrade, é PR no `mem_limit` (regra do 28a).
- [ ] Se qualquer conferência desta seção falhar (fora o caso "só faltam as linhas de log"): faça 5.10.1, guarde os logs e devolva para o planejamento.

### 5.6. A troca (ainda no dia C)

- [ ] Confirme que nada roda: `dc top scheduler | grep -c 'python -m ingestion'` → `0`; na UI, nenhuma execução `Running`.
- [ ] Parar o supercronic **sem remover o container** (o container e o log são o caminho de volta e a evidência do item 27):

  ```bash
  dc stop scheduler
  docker inspect -f '{{.State.Status}} {{.State.FinishedAt}}' "$(dc ps -a -q scheduler)"
  dc ps --status running --services | grep -x scheduler; echo "exit=$?"
  ```

  → `Container platform-scheduler-1  Stopped`; `exited <agora, em UTC>`; só `exit=1` (não está rodando). Anote o `FinishedAt`: é o fim do supercronic.
- [ ] Na UI, as próximas execuções continuam amanhã às 06:30, 06:45 e 07:00 (BRT). A partir daqui, só o Prefect agenda.

### 5.7. Dia C+1, depois das 07:15 BRT

- [ ] Estado: três execuções agendadas de hoje, uma por deployment, todas `Completed` (UI, "Flow runs", filtro de hoje; ou `pf flow-run ls --limit 10`). Horário de início perto de 06:30, 06:45 e 07:00 BRT; nenhuma `Late`, `Failed` ou `Crashed`.
- [ ] Logs (confirmação; se as linhas `ok` faltarem e o estado e o banco baterem, siga e anote):

  ```bash
  dc logs --since 3h prefect-worker | grep -E 'weather-forecast ok|weather-observed ok|ons-load ok|Traceback|Failed|Crashed'
  ```

  → `weather-forecast ok: 4 locations, 28 rows inserted, 0 already existed`, `weather-observed ok: ...` e `ons-load ok: ...`; nenhum erro.
- [ ] Banco (um único escritor por dia; é a prova principal):

  ```bash
  q <<'SQL'
  select issued_at, count(*), min(ingested_at), max(ingested_at) from raw.weather_forecast
  where issued_at >= (now() at time zone 'America/Sao_Paulo')::date - 1 group by 1 order by 1;
  select count(*), min("date"), max("date"), min(ingested_at), max(ingested_at) from raw.weather_observed
  where (ingested_at at time zone 'America/Sao_Paulo')::date = (now() at time zone 'America/Sao_Paulo')::date;
  select max("date"), max(ingested_at) from raw.ons_daily_load;
  SQL
  ```

  → duas linhas de previsão (C e C+1), cada uma com `28`, a de hoje com `ingested_at` por volta das 09:30 UTC; observado `40|<hoje − 10>|<ontem>|...`, com `ingested_at` por volta das 09:45 UTC; ONS com `max(ingested_at)` de hoje, por volta das 10:00 UTC.
- [ ] O supercronic não voltou: `docker inspect -f '{{.State.Status}} {{.State.FinishedAt}}' "$(dc ps -a -q scheduler)"` → `exited`, com o mesmo `FinishedAt` anotado na 5.6.

### 5.8. Reboot (dia C+1, depois da 5.7 e fora da janela)

- [ ] `sudo reboot`. Depois de voltar, refaça o bloco inicial e confira, explicitamente:

  ```bash
  dc ps --format '{{.Service}} {{.Status}}'
  dc ps --status running --services | grep -x scheduler; echo "exit=$?"
  docker inspect -f '{{.State.Status}} {{.State.FinishedAt}}' "$(dc ps -a -q scheduler)"
  dc logs --since 10m prefect-worker | grep -E 'started|Traceback'
  ```

  → `postgres`, `prefect-server` e `prefect-worker` (e `mlflow`, `health`) `Up ... (healthy)`. O `scheduler` **não** sobe: `exit=1`, e o `inspect` mostra `exited` com o `FinishedAt` da 5.6, porque o `unless-stopped` respeita o `stop` manual. O worker inicia de novo, sem `Traceback`, e aparece `Online` na UI.
- [ ] Se o `scheduler` voltou sozinho: `dc stop scheduler` na hora, confira na UI e no banco que nada rodou em dobro e devolva para o planejamento.

### 5.9. Dia C+2, depois das 07:15 BRT, e liberação do PR 36

- [ ] Repita a 5.7 inteira para C+2.
- [ ] Memória com o worker (a nova medição do item 35 prevista no 28a): três medições em repouso, pelo menos uma em outro dia (`memsnap phase3-worker-rest-1` a `-3`, cada uma seguida de `mempeak $(docker ps --format '{{.Names}}')`), e a janela dos jobs com o amostrador do 28a (seção 5.3, com o cgroup do `prefect-worker` no lugar do `scheduler`). Avalie os gatilhos G1 a G5 do 28a, seção 5.6. Qualquer um → 28b (para 4 GB, se já está em 2 GB; ou o 28b padrão, se foi dispensado) antes do próximo serviço novo (PR 47). Isso não bloqueia o PR 36.
- [ ] Se C+1 e C+2 bateram, o cutover está pronto. Anote C, o `FinishedAt` do supercronic, os horários reais de início, as durações (UI) e os números de memória da 5.5 e desta seção. Libere o PR 36.
- [ ] Até os alertas do PR 55, confira uma vez por dia, depois das 07:15 BRT: três `Completed` na UI ("Flow runs" de hoje) e a contagem da previsão de hoje (`28`) pelo `q`.

### 5.10. Caminho de volta

#### 5.10.1. Voltar ao supercronic (antes do deploy do PR 36)

Use se a 5.5 falhar, se a memória disparar o gatilho ou se o Prefect falhar por infraestrutura (worker fora, `Crashed`, `exit 137`, server inacessível). Faça antes das 06:25 do dia seguinte, nesta ordem:

- [ ] **Recupere o dia primeiro, se a falha foi numa execução agendada (C+1 em diante).** O supercronic religado **só roda no dia seguinte**: os horários de hoje já passaram, e ele não recupera nada. Pela CLI, fora da janela, um de cada vez, só os jobs que falharam ou não rodaram hoje (a **previsão até 23:59 BRT**, senão o snapshot do dia se perde):

  ```bash
  dc run --rm -T jobs python -m ingestion weather-forecast; echo "exit=$?"
  dc run --rm -T jobs python -m ingestion weather-observed; echo "exit=$?"
  dc run --rm -T jobs python -m ingestion ons-load; echo "exit=$?"
  ```

  → `exit=0` em cada um que você rodar. Confira a previsão de hoje com o `q` da 5.1 (`28`). Se a falha foi na 5.5 (dia C), o supercronic já coletou hoje e este passo não é necessário.
- [ ] Apagar os deployments (remove a agenda; o worker não pega mais nada deles), com nada `Running`:

  ```bash
  for d in ingest_weather_forecast ingest_weather_observed ingest_ons_load; do pf deployment delete "$d/production"; done
  pf deployment ls
  ```

  → lista vazia. Se o worker não responder, use `dc run --rm -T jobs prefect deployment delete ...`.
- [ ] Na UI, "Flow runs": nenhuma execução `Scheduled` ou `Late` sobrando. Apague as que houver (ou `pf flow-run delete <id>`): uma execução atrasada pendente rodaria quando o worker voltasse, em dobro com o supercronic.
- [ ] `dc stop prefect-worker`.
- [ ] Religar o container antigo (mesma imagem, mesmo crontab):

  ```bash
  dc start scheduler
  dc exec -T scheduler grep -v '^#' /app/infra/cron/crontab
  dc logs --since 2m scheduler
  ```

  → `Started`; as três linhas do crontab; `read crontab: /app/infra/cron/crontab`, sem `level=error`. A primeira execução dele é amanhã às 06:30.
- [ ] No dia seguinte, confira o `scheduler` como no item 27 (5.7). Devolva para o planejamento com os logs do worker (`dc logs --since 24h prefect-worker > /tmp/worker.log`).

#### 5.10.2. Uma execução agendada do Prefect falhou (C+1 em diante)

- [ ] Recupere o dado primeiro, fora da janela e com nada rodando: pela CLI (`dc run --rm -T jobs python -m ingestion <subcomando>`, idempotente) ou reexecutando o deployment pela UI ("Run", sem parâmetros) ou pelo `pfrun`. A **previsão precisa ser no mesmo dia, antes das 23:59 BRT**.
- [ ] Classifique pela mensagem do flow run (UI, aba de logs, ou `dc logs --since 6h prefect-worker`):
  - Falha da fonte ou da checagem (`NetworkError`, `stale`, `missing dates`, `schema validation failed`, `PartialIngestionError`): o supercronic falharia igual. Continue no Prefect e trate como no item 27 (5.10). O dia conta como falha da fonte, não do cutover; a janela de dois dias da 5.9 não recomeça por isso.
  - Falha de infraestrutura (`Crashed`, `exit 137`/OOM, worker `Offline`, execução `Late` que nunca começou, erro de conexão ou de autenticação com a API): 5.10.1 (o primeiro passo já foi feito acima) e devolva para o planejamento.

#### 5.10.3. Depois do deploy do PR 36

Não há mais `scheduler` na VPS. A volta é um PR que reverte o PR 36 (fluxo normal de agentes), seguido de deploy manual e `dc build scheduler && dc up -d scheduler`, mais os passos de apagar deployments e execuções pendentes e parar o worker da 5.10.1. Enquanto isso, rode os três jobs pela CLI uma vez por dia, fora da janela (a previsão antes da meia-noite BRT).

## 6. Critérios de pronto

| Quando | Comando | Saída esperada |
| --- | --- | --- |
| C | `dc exec -T prefect-worker sh -c 'printenv DATABASE_URL \| cut -d@ -f1 \| cut -d: -f1,2'` e `dc exec -T prefect-worker printenv DATABASE_URL_ADMIN; echo "exit=$?"` | `postgresql+psycopg://ingestor` e só `exit=1` |
| C | `dc run --rm -T jobs python -m flows.deployments; echo "exit=$?"` | `exit=0` |
| C | `pf deployment inspect "<flow>/production" \| grep -E "cron\|timezone"` para os três | crons `30 6`, `45 6` e `0 7` `* * *`; `America/Sao_Paulo` |
| C | As três execuções de verificação da 5.5 (`pfrun` ou UI) | `Completed`; previsão de hoje igual à 5.1 (`28`, mesmos `ingested_at`); observado `40` linhas reescritas |
| C | `docker inspect -f '{{.State.Status}}' "$(dc ps -a -q scheduler)"` | `exited` |
| C+1 e C+2 | UI "Flow runs" do dia | três `Completed`, inícios perto de 06:30, 06:45 e 07:00 BRT |
| C+1 e C+2 | consulta da previsão da 5.7 | `28` para o dia, `ingested_at` perto de 09:30 UTC |
| C+1 e C+2 | `docker inspect -f '{{.State.FinishedAt}}' "$(dc ps -a -q scheduler)"` | o mesmo `FinishedAt` da 5.6 |
| C+1, depois do reboot | `dc ps --status running --services \| grep -x scheduler; echo "exit=$?"` | só `exit=1`; worker `healthy` |
| C | `$HOME/mem-checks/<data>-cutover.txt`, `mempeak` e `journalctl` da 5.5 | menor `MemAvailable`, maior `anon` do worker e OOM anotados; parada imediata avaliada |
| C+2 em diante | medições de repouso e janela da 5.9 | gatilhos G1 a G5 do 28a avaliados, com os números ("sem gatilho" ou "G<n>: 28b") |

## 7. Testes necessários

`não`: procedimento manual na VPS. O comportamento novo (flows, deployments, worker) foi testado nos PRs 32 a 34; este item não muda o repositório.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

### Riscos

- **`dc up -d` sem nome de serviço religa o `scheduler`** enquanto ele estiver no compose (até o deploy do PR 36): dupla ingestão. Por isso o PR 36 vem logo depois da 5.9.
- **OOM ao disparar pelo worker.** Um `prefect deployment run --watch` dentro do container do worker soma o CLI ao subprocesso do flow no mesmo cgroup de 768m. As regras deste item proíbem isso; o `pfrun` usa um container `jobs` separado.
- **Execução atrasada que roda depois da volta.** Com o worker parado, as execuções agendadas ficam `Late` e rodam quando ele volta. A 5.10.1 apaga deployments e execuções pendentes antes de religar o supercronic.
- **Previsão perdida.** Se a execução das 06:30 falhar e ninguém olhar até a meia-noite, o snapshot do dia não volta (não há backfill de previsão). Até o PR 55, a conferência diária da 5.9 é a única proteção. O supercronic religado não recupera o dia corrente.
- **Linhas `ok` ausentes do log** se o nível INFO do PR 32 não estiver valendo. O estado `Completed` e o banco são a prova principal; o grep é confirmação.
- **Memória.** Em C, worker, server, MLflow e Postgres ficam no ar juntos (o 28a projeta 1100 MB de serviços novos com o worker; por isso o 28b de 2 GB é o padrão). O pico de uma execução com pandas dentro do worker é medido na 5.5 pelo amostrador (5 s; um pico mais curto aparece no `max_hits`/`oom_kill` do `mempeak`), e o repouso com o worker na 5.9.
- **CLI do Prefect.** Os subcomandos vieram de memória e de revisão independente, e a 5.3 os confere na VPS antes do uso: `prefect deployment ls|inspect|run --param --watch --watch-timeout|delete`, `prefect flow-run ls|delete|cancel`, `prefect work-pool inspect` e o formato de saída do `inspect`. A UI cobre tudo o que o CLI faria.
- **`unless-stopped` depois do reboot** (container parado à mão não volta): comportamento documentado do Docker, conferido explicitamente na 5.8.

### Decisões (com recomendação; aceitas pelo usuário)

1. **Troca entre dois dias, sem paralelo:** trocar no dia C depois das 07:15, com execuções de verificação antes de parar o supercronic.
2. **Executar os três deployments em C:** sim, como reexecuções idempotentes, pela UI ou por container `jobs` separado.
3. **`stop` em vez de `rm` do `scheduler`:** mantém o container, o log do item 27 e uma volta de um comando. O PR 36 remove de vez, com `--remove-orphans`.
4. **Observar dois dias (C+1 e C+2) e um reboot** antes do PR 36.
5. **Falha da fonte durante a observação** não reinicia a contagem (5.10.2); só falha de infraestrutura conta contra o cutover.
6. **Na volta, recuperar o dia pela CLI antes de religar o supercronic**, porque ele só roda no dia seguinte.

### Perguntas em aberto

- Nenhuma bloqueante.

## 10. Decisões que exigem ADR

**Nenhuma neste item.** Ele executa o que o ADR 0004 já prevê ("substituído pelos deployments do Prefect [...] depois do cutover manual (item 35)") e o ADR obrigatório do plano 33. Não muda schema, contrato nem exposição de porta. A atualização de status do ADR 0004 vai num único PR só de `docs/**` logo depois do primeiro deploy automático bem-sucedido (plano 39, seção 10; plano 36, D4).
