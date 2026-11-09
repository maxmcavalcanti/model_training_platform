# 28a — Checkpoint de memória da VPS antes do MLflow e do Prefect (manual)

> Executa: **usuário** (VPS; agentes não têm acesso). Depende do item 27 **só para a linha de base**: a stack da Fase 2 já está em produção desde 2026-11-08 (`0007`, `scheduler` com as três linhas, backfill do observado), então as medições podem começar já, durante a janela D a D+7, porque não recriam nem reiniciam nada. A medição que decide o 28b (seção 5.6) é a feita **em D+7 (2026-11-15) ou depois**. Precisa estar feito antes do PR 29.
> Revisão 2026-11-08 (v2, com a revisão independente aceita pelo usuário). Em relação ao rascunho: comandos completos com bloco inicial de sessão; pico pelo cgroup de cada container e por amostrador passivo na janela dos jobs, sem job extra; gatilhos numéricos; `docker image prune -a` trocado por `-f` (o `-a` apagaria a `platform-jobs`). Na v2: regra de limite por `anon` (`memory.stat`) em vez de `memory.peak` (que inclui page cache), com `max` e `oom_kill` de `memory.events`; worker com `768m` e segunda projeção (item 35); `vmstat 5 13 | tail -n 12` (a primeira linha do `vmstat` é a média desde o boot); pressão de memória (PSI) como gatilho G5; amostrador agendado entre 07:20 e 23:59; `memory.swap.current` ausente vale 0; **decisão de memória: o upgrade para 2 GB (28b) é o caminho padrão antes do item 31**.

## 1. Objetivo

Medir a memória da VPS (1 vCPU, 1 GB de RAM, swap do item 02) com a stack da Fase 2 no ar, em repouso e no pico dos jobs agendados, e registrar os números por serviço.
Registrar a decisão de memória da Fase 3: por padrão, fazer o 28b (2 GB) antes do item 31; dispensar só se a medição de D+7 provar folga (seção 5.6), e entregar os números que fixam os `mem_limit` dos PRs 29 e 30.

## 2. Fora do escopo

- Qualquer mudança de código, compose, crontab ou `mem_limit` (ajuste é PR).
- Recriar ou reiniciar qualquer container, rodar build, backfill ou job manual.
- O upgrade em si (item 28b) e a medição com MLflow e Prefect no ar (item 31).
- Monitoramento contínuo de memória (vigia de saúde, PR 56).

## 3. Fase do roadmap

Fase 3 — "MLflow, Prefect e CI/CD" (pré-requisito). O doc diz, em "Stack na VPS": "Tamanho da VPS: estimativa de 4 GB de RAM como mínimo confortável para essa stack [...] Confirmar com `docker stats` depois da Fase 3." Como a VPS tem 1 GB (P3 do índice), a medição vem antes e se repete nos itens 31, 35, 50 e 59.

## 4. Arquivos a criar ou alterar

**Nenhum arquivo do repositório.** Os números ficam na VPS, em `$HOME/mem-checks/` do usuário `deploy`, e o resumo volta para o planejamento (seção 5.7). Nada com hostname, IP ou nome da tailnet entra no git.

### O que está em produção e entra na medição

| Serviço (container) | `mem_limit` atual | Papel |
| --- | --- | --- |
| `health` (`platform-health-1`) | `16m` | busybox `httpd` |
| `postgres` (`platform-postgres-1`) | `256m` | banco `ml` |
| `scheduler` (`platform-scheduler-1`) | `512m` | supercronic; os jobs agendados (06:30 `weather-forecast`, 06:45 `weather-observed`, 07:00 `ons-load`, horário de Brasília) rodam **dentro** deste container |
| `jobs` (`platform-jobs-run-<id>`) | `512m` | só existe durante `dc run --rm jobs ...` |
| `tailscaled`, `dockerd`, `containerd`, `sshd`, systemd | sem limite | no host |

### Estimativas para a Fase 3 em diante (a medir, não são fatos)

| Serviço novo | Estimativa em repouso | `mem_limit` previsto | Onde entra |
| --- | --- | --- | --- |
| `mlflow` (1 worker) | 200–350 MB | `512m` | PR 29 |
| `prefect-server` (API, UI e serviços internos) | 250–450 MB | `640m` | PR 30 |
| `prefect-worker` | 250–400 MB | `768m` | PR 34 |
| `grafana` | 100–200 MB | `256m` | PR 47 |
| Conexões novas no Postgres (MLflow 2+2, Prefect 3+2) | 5–10 MB cada | dentro dos `256m` do `postgres` | PRs 28 a 30 |

Para as projeções da seção 5.6: MLflow + Prefect server = **700 MB** (estimativa alta); o worker do item 35 acrescenta **400 MB**.

### Por que o 28b é o caminho padrão

Com a stack da Fase 2 já perto do limite físico, somar 700 MB (Fase 3) e mais 400 MB no item 35 passa da RAM de 1 GB: o restante só caberia no swap, e serviços que acordam a cada poucos segundos (os do Prefect) em swap degradam tudo. Por isso o padrão é subir para 2 GB antes do item 31; o 28a só serve para **dispensar** o upgrade se os números provarem o contrário, e para fixar os limites.

## 5. Passos

### Regras deste item

- Não rodar build, backfill, job manual nem `dc up`/`dc restart`. Só leitura.
- Durante a janela D a D+7 do item 27 (até 2026-11-15): **nunca** recriar ou reiniciar o `scheduler`.
- Nunca `dc down -v`, `docker volume rm` nem `docker volume prune`. Nunca `dc config` sem `-q`. Não ler nem imprimir `infra/.env`.
- Nunca `docker image prune -a` nem `docker system prune -a`.

### Bloco inicial de toda sessão SSH

Na VPS, como `deploy` (`ssh deploy@<host>.<tailnet>.ts.net`). **Toda sessão SSH nova** começa com este bloco:

```bash
cd /opt/platform
dc() { docker compose -f /opt/platform/infra/docker-compose.yml "$@"; }
q() { dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -A -t -F "|" -v ON_ERROR_STOP=1'; }
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

- `memsnap <rótulo>` grava em `$HOME/mem-checks/`: `free -m`, swap, `docker stats`, 12 amostras de 5 s do `vmstat` (descartada a primeira linha, que é a média desde o boot; `si`/`so` = swap in/out) e a pressão de memória do kernel (`/proc/pressure/memory`).
- `mempeak <container>...` lê o cgroup v2: `current` (inclui page cache), `anon` (memória anônima: o que o processo usa de fato e o que conta para o limite fazer sentido), `peak_with_cache` (pico desde a subida, **inclusive cache**: só informativo), swap (0 se o arquivo não existe), `max_hits` (quantas vezes o container encostou no `mem_limit`) e `oom_kill` (processos mortos pelo limite; um job morto dentro do `scheduler` aparece aqui mesmo sem o container cair).

### 5.1. Ambiente e versões

- [ ] Hora e estado:

  ```bash
  TZ=America/Sao_Paulo date '+%F %H:%M'; uptime
  dc ps --format '{{.Service}} {{.Status}}'
  ```

  → `health` e `postgres` `Up ... (healthy)`, `scheduler Up ...`. Anote o `uptime`.

- [ ] Versões (insumo dos PRs 29 a 31):

  ```bash
  uname -r; nproc
  docker version --format 'docker {{.Server.Version}}'
  docker compose version
  docker compose up --help | grep -c -- '--wait-timeout'
  tailscale version | head -1
  grep -E '^(MemTotal|SwapTotal):' /proc/meminfo
  ```

  → kernel `6.x`, `1` vCPU, versões anotadas; `1` se o compose suporta `--wait-timeout`; `MemTotal` perto de `1000000 kB`; `SwapTotal` = o swap do item 02.

- [ ] cgroup legível:

  ```bash
  mempeak platform-health-1 platform-postgres-1 platform-scheduler-1
  ```

  → três linhas `... current=... anon=... peak_with_cache=... swap=... max_hits=... oom_kill=...`. Se aparecer `cgroup of ... not found` ou `No such file`, anote e siga só com `docker stats`.

### 5.2. Repouso (três medições, pelo menos uma em outro dia, a última em D+7 ou depois)

Fora de 06:25–07:15 (horário de Brasília), pelo menos 10 minutos depois de qualquer comando pesado.

- [ ] `memsnap rest-1` → anote, da linha `Mem:`, `used` e `available`; da linha `Swap:`, `used`; o `MemUsage` de cada container; quantas das 12 amostras do `vmstat` têm `si` ou `so` diferente de `0`; o `some avg300` da pressão.
- [ ] `memsnap rest-2`, horas depois.
- [ ] `memsnap rest-3`, em outro dia, **em 2026-11-15 ou depois** (é a medição que decide).
- [ ] Depois de cada uma: `mempeak platform-postgres-1 platform-scheduler-1` (anote `anon` em repouso).

### 5.3. Pico na janela dos jobs agendados (passivo)

- [ ] Crie o amostrador (uma vez):

  ```bash
  cat > "$HOME/mem-checks/sample.sh" <<'SH'
  #!/bin/sh
  # usage: sample.sh <seconds> <output file> [cgroup dir ...]
  # one line every 5 s: UTC time, MemAvailable MB, SwapFree MB, then anon MB of each cgroup dir
  secs=$1; out=$2; shift 2
  end=$(( $(date +%s) + secs ))
  while [ "$(date +%s)" -lt "$end" ]; do
    line="$(date -u +%T) $(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo) $(awk '/^SwapFree:/ {print int($2/1024)}' /proc/meminfo)"
    for d in "$@"; do
      line="$line $(awk '/^anon /{print int($2/1048576)}' "$d/memory.stat" 2>/dev/null)"
    done
    echo "$line"
    sleep 5
  done > "$out"
  SH
  chmod +x "$HOME/mem-checks/sample.sh"
  ```

- [ ] **Entre 07:20 e 23:59** (horário de Brasília), agende o amostrador para começar às 06:25 do dia seguinte e rodar 50 minutos, gravando também o `anon` do `scheduler` (coluna 4) e do `postgres` (coluna 5):

  ```bash
  start=$(TZ=America/Sao_Paulo date -d 'tomorrow 06:25' +%s); now=$(date +%s)
  out="$HOME/mem-checks/$(TZ=America/Sao_Paulo date -d tomorrow +%F)-window.txt"
  dirs="$(cgdir platform-scheduler-1) $(cgdir platform-postgres-1)"
  nohup sh -c "sleep $(( start - now )); exec \"$HOME/mem-checks/sample.sh\" 3000 \"$out\" $dirs" >/dev/null 2>&1 &
  echo "sampler pid $! -> $out"
  ```

  → `sampler pid <n> -> .../<amanhã>-window.txt`. Pode sair da sessão. (Não recrie o `scheduler` até o amostrador terminar: o diretório do cgroup muda.)

- [ ] No dia seguinte, depois das 07:20 BRT (sessão nova, bloco inicial):

  ```bash
  f="$HOME/mem-checks/$(TZ=America/Sao_Paulo date +%F)-window.txt"
  wc -l < "$f"
  echo "min MemAvailable MB: $(sort -k2 -n "$f" | head -1)"
  echo "min SwapFree MB: $(sort -k3 -n "$f" | head -1)"
  echo "max scheduler anon MB: $(sort -k4 -n "$f" | tail -1)"
  echo "max postgres anon MB: $(sort -k5 -n "$f" | tail -1)"
  mempeak platform-postgres-1 platform-scheduler-1
  dc logs --since 2h scheduler | grep -E 'weather-forecast ok|weather-observed ok|ons-load ok|failed|level=error'
  ```

  → cerca de `600` linhas; anote o menor `MemAvailable` (com horário), o menor `SwapFree`, o maior `anon` do `scheduler` e do `postgres`, `max_hits` e `oom_kill`; no log, as três linhas `... ok` e nenhuma `failed`. Sem arquivo: o `nohup` não sobreviveu ao logout; repita deixando a sessão aberta, ou rode o amostrador em primeiro plano das 06:25 às 07:15.

### 5.4. Swap ao longo dos dias e OOM

- [ ] Swap em uso entre as medições:

  ```bash
  grep -h -E '^(== rest|Swap:)' "$HOME"/mem-checks/*-rest-*.txt
  ```

  → pares `== rest-<n> <data>` e `Swap: <total> <used> <free>`; anote se `used` cresce de um dia para o outro.

- [ ] OOM global do kernel desde o boot:

  ```bash
  sudo journalctl -k -b --no-pager | grep -E 'Out of memory: Killed process' | grep -vc 'Memory cgroup'
  ```

  → `0` (maior que `0` é o gatilho G3).

- [ ] OOM por limite de container (não é gatilho de upgrade; é `mem_limit`):

  ```bash
  sudo journalctl -k -b --no-pager | grep -c 'Memory cgroup out of memory'
  docker inspect -f '{{.Name}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}' $(docker ps -aq)
  ```

  → `0`; todos `oom=false` e `restarts=0` (ou o número de reboots).

### 5.5. Disco

- [ ] `df -h /` e `docker system df` → uso de `/` abaixo de 60% e pelo menos 5 GB livres.
- [ ] Se faltar: `docker image prune -f`, `docker builder prune -f`, `df -h /`. Nunca `-a`, nunca `docker volume prune`.

### 5.6. Gatilhos e decisão

Gatilhos (os mesmos nos itens 28b, 31, 35, 50 e 59):

| Id | Gatilho | Como ler |
| --- | --- | --- |
| G1 | `available` do `free -m` abaixo de **150 MB** em repouso, em 2 das 3 medições | 5.2 |
| G2 | Swap ativo em repouso: `si` ou `so` diferente de `0` em **6 ou mais** das 12 amostras, em 2 medições de dias diferentes; ou `Swap: used` crescendo mais de **200 MB** entre dois dias sem reboot | 5.2 e 5.4 |
| G3 | OOM global do kernel desde o boot (contagem do 5.4 maior que `0`) | 5.4 |
| G4 | Menor `MemAvailable` da janela dos jobs abaixo de **50 MB** | 5.3 |
| G5 | Pressão de memória em repouso: `some avg300` acima de **10** em 2 das 3 medições | 5.2 |

Não é gatilho de upgrade, é PR no `mem_limit` daquele serviço:

- `oom_kill` maior que `0` num container, ou `OOMKilled=true`, com o host acima de 150 MB livres.
- Maior `anon` medido de um container acima de **85%** do seu `mem_limit` (ex.: `scheduler` acima de 435 MB, `postgres` acima de 218 MB), ou `max_hits` crescendo: PR subindo aquele limite em 128 MB e nova medição. (`peak_with_cache` não entra na regra: page cache é liberável.)

Projeções (mediana do `available` em repouso, com a `rest-3` de D+7 ou depois):

- Folga da Fase 3 (item 31) = `available` − 700 MB.
- Folga do item 35 (com o worker) = `available` − 1100 MB.

**Decisão de memória (recomendação aceita pelo usuário em 2026-11-08):**

- **Padrão: fazer o 28b (2 GB) antes do item 31.**
- Dispensa só se, na medição de D+7 ou depois, a folga da Fase 3 for **maior ou igual a zero**, isto é, `available` mediano em repouso de **700 MB ou mais**, e nenhum gatilho G1 a G5 tiver disparado. A dispensa é registrada pelo usuário com os números (seção 5.7) e vale só até o item 31, que mede de novo.
- Com qualquer gatilho G1 a G5: 28b antes do PR 29.

- [ ] Preencha: "28b antes do item 31 (padrão)", "28b antes do PR 29 (gatilho G<n>)" ou "28b dispensado por ora: available mediano <n> MB ≥ 700 MB, sem gatilho".

### 5.7. Devolver para o planejamento

Cole este resumo (sem hostname, IP nem nome da tailnet):

```
28a — <data da rest-3>
kernel/docker/compose/tailscale: <versões>; --wait-timeout: <0|1>
MemTotal / SwapTotal: <n> MB / <n> MB
Repouso (used / available / swap used) 1: <n>/<n>/<n>  2: <n>/<n>/<n>  3: <n>/<n>/<n>
vmstat si/so != 0 (de 12): <n>, <n>, <n>; PSI some avg300: <n>, <n>, <n>
Janela: min MemAvailable <n> MB às <hh:mm> UTC; min SwapFree <n> MB; max anon scheduler <n> MB, postgres <n> MB
Containers em repouso (anon / max_hits / oom_kill): health <..>  postgres <..>  scheduler <..>
OOM global: <n>; OOM de cgroup: <n>
Disco: <uso %>, <GB livres>
Gatilhos: <nenhum | G1..G5>
Folga Fase 3: <n> MB; folga item 35: <n> MB
Decisão: <28b antes do 31 (padrão) | 28b antes do PR 29 (G<n>) | 28b dispensado por ora>
```

## 6. Critérios de pronto

| Verificação (na VPS, com o bloco inicial) | Esperado |
| --- | --- |
| `ls "$HOME"/mem-checks/*-rest-*.txt \| wc -l` | `3` ou mais, com dois dias diferentes no nome e um deles em 2026-11-15 ou depois |
| `ls "$HOME"/mem-checks/*-window.txt` | Pelo menos um arquivo, com cerca de 600 linhas |
| `mempeak platform-postgres-1 platform-scheduler-1` | Duas linhas com `anon=` (ou a anotação de que o cgroup não é legível) |
| `sudo journalctl -k -b --no-pager \| grep -E 'Out of memory: Killed process' \| grep -vc 'Memory cgroup'` | Número anotado (esperado `0`) |
| `df -h /` | Uso abaixo de 60% e 5 GB livres |
| Durante o item 27 | `docker inspect -f '{{.State.StartedAt}} restarts={{.RestartCount}}' "$(dc ps -q scheduler)"` igual ao do dia D |
| Fora da VPS | Resumo do 5.7 entregue, com a decisão |

## 7. Testes necessários

`não`: procedimento manual de medição na VPS; nenhuma mudança de código, config ou comportamento no repositório.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

Riscos:

- **Custo de CPU da medição** em 1 vCPU: por isso o pico vem do amostrador de `/proc/meminfo` e do `memory.stat` (baratos), não de `docker stats` em laço.
- **`anon` amostrado a cada 5 s** pode perder um pico curto; o `max_hits` e o `oom_kill` do `memory.events` pegam quem encostou no limite.
- **Arquivos do cgroup v2** (`memory.stat`, `memory.events`, `memory.peak`, `memory.swap.current`) não foram conferidos na VPS (sem acesso); o 5.1 confere e o `mempeak` trata `memory.peak` e `memory.swap.current` ausentes.
- **`nohup` e logout:** com `KillUserProcesses=no` (padrão do Ubuntu) o amostrador sobrevive; senão, o 5.3 diz o que fazer.

Perguntas (recomendações aceitas pelo usuário em 2026-11-08; ficam registradas):

1. **Medir já, durante a janela do item 27?** Sim, para a linha de base; a `rest-3` que decide fica para D+7 ou depois.
2. **Upgrade padrão antes do 31?** Sim (seção 5.6); dispensa só com `available` mediano ≥ 700 MB e sem gatilho.
3. **Histórico das medições:** na VPS e no planejamento; um PR só de `docs/**` registra os números (sem hostname) em "Tamanho da VPS" quando a Fase 3 fechar.

Correção para o índice: **aplicada** em 2026-11-08 (`docs/plans/00-indice.md`): a coluna "Depende de" do 28a é "27 (só para a linha de base)", e a P3 e as restrições do índice dizem que o 28b (2 GB) é o padrão antes do item 31.

## 10. Decisões que exigem ADR

**Nenhuma.** Medição sem mudança; o upgrade (28b) é capacidade prevista na P3. Exigiria ADR mudar a arquitetura para caber em 1 GB (tirar MLflow ou Prefect da VPS, trocar o orquestrador).
