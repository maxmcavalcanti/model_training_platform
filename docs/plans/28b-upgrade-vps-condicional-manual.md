# 28b — Upgrade da VPS (manual; padrão antes do item 31)

> Executa: **usuário**. Decisão de memória aceita pelo usuário em 2026-11-08: o orçamento da Fase 3 não fecha em 1 GB, então **subir para 2 GB é o caminho padrão antes do item 31**. Só se dispensa se o 28a, medido em D+7 (2026-11-15) ou depois, mostrar `available` mediano em repouso de 700 MB ou mais e nenhum gatilho; a dispensa é registrada pelo usuário com a medição. Depois do item 31, o 28b volta a ser condicional: faça de novo (para 4 GB) se um gatilho disparar nos itens 31, 35, 50 ou 59.
> Quando: padrão, depois do 28a e antes do item 31 (pode ser antes ou depois dos PRs 29 e 30, que são só código). Com gatilho no 28a: antes do PR 29. Com gatilho no 31: antes do item 35 (que acrescenta o worker; os PRs 32 a 34 são só código). Mais tarde: antes do próximo serviço novo.
> Revisão 2026-11-08 (v2, com a revisão independente aceita pelo usuário). Em relação ao rascunho: gatilhos numéricos do 28a; regra de escolha do plano; cópia lógica para fora da VPS com hash; janela proibida; verificação pós-boot sem entrar na VPS. Na v2: caminho padrão; margem de +700 MB (Fase 3) + 600 MB (Fases 4 e 5) quando o gatilho vem do 28a, e de 600 MB menos o já medido a partir do 31; `vmstat 5 13 | tail -n 12` e `anon` do cgroup; `pg_dumpall --globals-only --no-role-passwords` no backup; checagem de `/health` do MLflow e do Prefect depois do upgrade. Revisão final (mesmo dia): `/api/ready` do Prefect sem credencial (isento, plano 30); gatilho no 31 → antes do item 35; `mkdir` da pasta de destino antes do `scp`.

## 1. Objetivo

Subir a VPS para um plano de 2 GB de RAM (ou 4 GB, pela regra da seção 4) sem perder dados e com tudo voltando sozinho depois do boot.
Registrar a medição depois do upgrade com os mesmos comandos do 28a.

## 2. Fora do escopo

- Qualquer mudança de código, compose ou `mem_limit` (subir limites é PR, depois de medir no plano novo).
- Mudar de provedor, região, sistema operacional ou arquitetura (o Dockerfile dos jobs baixa o supercronic `linux-amd64`).
- Backup automático (PR 57): a cópia da seção 5.3 é rede de segurança deste item, não backup com restore testado.
- Diminuir o plano depois.

## 3. Fase do roadmap

Fase 3 — "MLflow, Prefect e CI/CD" (pré-requisito de memória do item 31); depois, transversal e condicional. O doc estima "4 GB de RAM como mínimo confortável para essa stack"; a P3 do índice começou em 1 GB e a decisão de 2026-11-08 torna 2 GB o padrão da Fase 3.

## 4. Arquivos a criar ou alterar

**Nenhum arquivo do repositório.** Mudam: o plano da VPS no painel do provedor e, na VPS, `$HOME/mem-checks/` e `$HOME/backups/`.

### Gatilhos (os do 28a, seção 5.6)

| Id | Gatilho |
| --- | --- |
| G1 | `available` do `free -m` abaixo de **150 MB** em repouso, em 2 de 3 medições |
| G2 | Swap ativo em repouso: `si` ou `so` diferente de `0` em **6 ou mais** das 12 amostras do `vmstat 5 13 \| tail -n 12`, em 2 medições de dias diferentes; ou `Swap: used` crescendo mais de **200 MB** entre dois dias sem reboot |
| G3 | OOM global do kernel desde o boot (`sudo journalctl -k -b --no-pager \| grep -E 'Out of memory: Killed process' \| grep -vc 'Memory cgroup'` maior que `0`) |
| G4 | Menor `MemAvailable` da janela dos jobs (06:25–07:15) abaixo de **50 MB** |
| G5 | `some avg300` de `/proc/pressure/memory` acima de **10** em repouso, em 2 de 3 medições |

Container morto pelo próprio `mem_limit` (ou `anon` acima de 85% do limite) com o host acima de 150 MB livres **não** é gatilho: é PR subindo aquele limite.

### Escolha do plano

- Pico usado = `MemTotal` − menor `MemAvailable` medido na janela dos jobs, com a stack da fase no ar.
- Margem:
  - Upgrade padrão ou gatilho no **28a** (stack da Fase 2): **+700 MB** (MLflow e Prefect server) **+600 MB** (Fases 4 e 5: worker, Grafana, score).
  - Gatilho no **31 ou depois**: **+600 MB menos** o que das Fases 4 e 5 já está no ar e entrou no pico medido (ex.: no item 35, o worker já foi medido; desconte a estimativa dele, 400 MB).
- Pico usado + margem até **2,0 GB** → plano de **2 GB** (o swap absorve o excedente transitório); acima → **4 GB**.
- Mesma arquitetura (x86_64), mesmo sistema (Ubuntu 24.04), disco igual ou maior.

## 5. Passos

### Regras deste item

- Nada entre **06:25 e 07:15** (horário de Brasília). Confira com `TZ=America/Sao_Paulo date '+%F %H:%M'`.
- Nunca `dc down -v`, `docker volume rm` nem `docker volume prune`. Nunca `dc config` sem `-q`. Não ler nem imprimir `infra/.env`.
- Não editar código, compose nem crontab na VPS.
- Não fazer durante a janela D a D+7 do item 27 (até 2026-11-15): o reboot reinicia o `scheduler`. Exceção: G3 (OOM global), que é urgente.

### Bloco inicial de toda sessão SSH

Na VPS, como `deploy` (`ssh deploy@<host>.<tailnet>.ts.net`):

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

### 5.1. Registrar o motivo

- [ ] Anote: "upgrade padrão da Fase 3" ou o gatilho (G1 a G5) com a data e o arquivo de `$HOME/mem-checks/` ou a contagem do `journalctl`.
- [ ] Calcule o plano pela regra "Escolha do plano" e anote: pico usado, margem, total, plano escolhido.

### 5.2. Linha de base antes do upgrade

- [ ] Fora da janela proibida:

  ```bash
  TZ=America/Sao_Paulo date '+%F %H:%M'
  memsnap pre-upgrade
  mempeak $(docker ps --format '{{.Names}}')
  nproc; tailscale ip -4; df -h /
  tailscale serve status
  dc ps --format '{{.Service}} {{.Status}}'
  docker inspect -f '{{.Name}} started={{.State.StartedAt}} restarts={{.RestartCount}}' $(docker ps -q)
  ```

  → anote `nproc`, o IP do Tailscale (`100.x.y.z`), o disco, os mapeamentos do `serve` (8080 e `tcp` 5432; também 5000 e 4200 se o item 31 já foi feito) e o estado de cada serviço.

### 5.3. Cópia dos dados para fora da VPS

Rede de segurança; o snapshot do provedor (5.4) é a proteção principal.

- [ ] Bancos que existem:

  ```bash
  q <<'SQL'
  select datname from pg_database where datname in ('ml', 'mlflow', 'prefect') order by 1;
  SQL
  ```

  → `ml` e, se o item 31 já foi feito, `mlflow` e `prefect`.

- [ ] Papéis e privilégios globais, sem senhas, e um dump por banco listado (rode só as linhas dos bancos que existem):

  ```bash
  mkdir -p "$HOME/backups"; stamp=$(date +%F)
  dc exec -T postgres sh -c 'pg_dumpall -U "$POSTGRES_USER" --globals-only --no-role-passwords' > "$HOME/backups/globals-$stamp.sql"
  dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d ml -Fc' > "$HOME/backups/ml-$stamp.dump"
  dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d mlflow -Fc' > "$HOME/backups/mlflow-$stamp.dump"
  dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d prefect -Fc' > "$HOME/backups/prefect-$stamp.dump"
  ```

  O `globals-*.sql` recria os papéis (`ingestor`, `scientist`, `scorer`, `reader` e, se existirem, `mlflow` e `prefect`) sem as senhas; num restore, as senhas voltam pelo plano 12 e pelo `create-databases`.

- [ ] Artefatos do MLflow, se o volume existir:

  ```bash
  docker volume ls -q | grep -x platform_mlflow_artifacts \
    && docker run --rm -v platform_mlflow_artifacts:/artifacts:ro \
         busybox:1.38.0@sha256:a46257e06c82ad85242d0d38077d0a52d9896389ca60a1a59d3463db586e5fa4 \
         tar -C /artifacts -cf - . > "$HOME/backups/mlflow-artifacts-$stamp.tar"
  ```

  (A imagem é a do serviço `health`, já na VPS e fixada por digest.)

- [ ] Hashes:

  ```bash
  ls -l "$HOME/backups"; sha256sum "$HOME"/backups/*-"$stamp".*
  ```

  → cada arquivo com tamanho maior que zero; anote os hashes.

- [ ] Do notebook (na tailnet), criando antes a pasta de destino:

  ```bash
  mkdir -p platform-backups
  scp 'deploy@<host>.<tailnet>.ts.net:backups/*' ./platform-backups/
  ```

  No PowerShell, o `mkdir platform-backups` também serve (sem `-p`; avisa se já existir). Hashes: no Windows (PowerShell), `Get-FileHash -Algorithm SHA256 .\platform-backups\*`; no Linux ou macOS, `sha256sum platform-backups/*`. → os mesmos hashes. Os dumps têm dados, não senhas; guarde-os fora do git.

### 5.4. Snapshot e redimensionamento

- [ ] No painel do provedor, tire um snapshot da VPS e espere concluir.
- [ ] Confira na documentação do provedor, antes de clicar: se o redimensionamento exige desligar a VPS, se mantém o disco e o IPv4 público e se permite voltar ao plano anterior. Anote.
- [ ] Fora da janela proibida, redimensione para o plano escolhido no 5.1. Se o provedor exigir desligar antes: `sudo poweroff` (os containers voltam pelo `restart: unless-stopped`).

### 5.5. Depois do boot, sem entrar na VPS

- [ ] Dois a três minutos depois de a VPS ligar, do notebook (no Windows, `curl.exe`):

  ```bash
  curl -fsS https://<host>.<tailnet>.ts.net:8080/health
  ```

  → `ok`. Se o item 31 já foi feito, também:

  ```bash
  curl -fsS https://<host>.<tailnet>.ts.net:5000/health
  curl -fsS https://<host>.<tailnet>.ts.net:4200/api/ready
  ```

  → `OK` e a resposta de pronto do Prefect. `/api/ready` fica fora da autenticação da API (plano 30, "Comportamento da autenticação"), então não precisa de credencial.

### 5.6. Conferir na VPS

- [ ] Sessão SSH nova, bloco inicial:

  ```bash
  free -m; nproc; swapon --show
  tailscale ip -4
  tailscale serve status
  dc ps --format '{{.Service}} {{.Status}}'
  docker inspect -f '{{.Name}} started={{.State.StartedAt}} restarts={{.RestartCount}}' $(docker ps -q)
  dc logs --since 24h scheduler | tail -5
  ```

  → `Mem:` com o total novo (perto de `1900` para 2 GB, `3800` para 4 GB); `nproc` do plano novo; swap ativo; o **mesmo** IP do Tailscale do 5.2 (se mudou, atualize o `VPS_KNOWN_HOSTS` do item 38, se existir); os mesmos mapeamentos do `serve`; todos `Up` (`healthy` onde há healthcheck); log do `scheduler` mantido (reinício preserva o log). Depois do item 35, troque o `scheduler` pelo `prefect-worker` nesse último comando.

- [ ] Se o item 31 já foi feito, também na VPS: `curl -fsS http://127.0.0.1:5000/health` → `OK` e `curl -fsS http://127.0.0.1:4200/api/ready` → resposta de pronto.
- [ ] Mantenha o swap.

### 5.7. Medir no plano novo

- [ ] Em repouso, três vezes, uma em outro dia: `memsnap post-upgrade-1`, `memsnap post-upgrade-2`, `memsnap post-upgrade-3`, cada uma seguida de `mempeak $(docker ps --format '{{.Names}}')`.
- [ ] Janela dos jobs do dia seguinte: o amostrador do 28a, seção 5.3 (agendado entre 07:20 e 23:59; o script `$HOME/mem-checks/sample.sh` já existe), e depois:

  ```bash
  f="$HOME/mem-checks/$(TZ=America/Sao_Paulo date +%F)-window.txt"
  echo "min MemAvailable MB: $(sort -k2 -n "$f" | head -1)"
  echo "max scheduler anon MB: $(sort -k4 -n "$f" | tail -1)"
  dc logs --since 2h scheduler | grep -E 'weather-forecast ok|weather-observed ok|ons-load ok|failed|level=error'
  ```

  → nenhum gatilho G1 a G5; as três linhas `... ok` e nenhuma `failed`. Depois do item 35, os jobs rodam no `prefect-worker`: use o cgroup e o log dele no lugar dos do `scheduler`.

### 5.8. Devolver para o planejamento

O motivo (padrão ou gatilho), o plano novo (RAM, vCPU, disco), a medição antes e depois (formato do 28a, seção 5.7) e se o IP do Tailscale mudou. A P3 do índice e "Tamanho da VPS" do doc são atualizados num PR só de `docs/**`; `mem_limit` só sobe por PR.

### 5.9. Se algo falhar

- **A VPS não volta (o `curl` do 5.5 falha depois de 10 minutos):** console web do provedor; `sudo systemctl status docker tailscaled`; se o Tailscale não subiu, `sudo systemctl restart tailscaled` e repita o 5.5. Anote: reboot com intervenção quebra o critério da Fase 0.
- **Um serviço não fica `healthy`:** `dc logs --since 15m <serviço>`; não recrie às cegas; devolva com o log.
- **Disco ou dados perdidos:** restaure o snapshot do 5.4. As cópias do 5.3 são o último recurso (restore nunca testado; o procedimento entra no PR 57).

## 6. Critérios de pronto

| Comando | Onde | Saída esperada |
| --- | --- | --- |
| `free -m` | VPS | `Mem:` com o total novo (cerca de `1900`+ para 2 GB, `3800`+ para 4 GB); `Swap:` do item 02 |
| `nproc` | VPS | vCPUs do plano novo |
| `tailscale ip -4` | VPS | O IP anotado no 5.2 |
| `tailscale serve status` | VPS | Os mesmos mapeamentos do 5.2 |
| `dc ps --format '{{.Service}} {{.Status}}'` | VPS | Todos `Up`, `healthy` onde há healthcheck |
| `curl -fsS https://<host>.<tailnet>.ts.net:8080/health` | Notebook | `ok`, sem entrar na VPS depois do boot |
| `/health` do MLflow e `/api/ready` do Prefect, sem credencial (5.5 e 5.6), se o item 31 já foi feito | Notebook e VPS | `OK` e a resposta de pronto |
| Medições do 5.7 | VPS | Nenhum gatilho G1 a G5; jobs do dia seguinte com `ok` |
| Hashes do 5.3 | Notebook e VPS | Iguais |

## 7. Testes necessários

`não`: operação manual de capacidade na VPS; nenhuma mudança de código, config ou comportamento no repositório.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

Riscos:

- **Redimensionamento com perda de disco ou mudança de layout:** depende do provedor; snapshot e cópia lógica antes.
- **IPv4 público pode mudar:** sem efeito (nenhuma porta pública, ADR 0003); o IP do Tailscale fica no estado do `tailscaled` em disco. O 5.6 confere.
- **Custo mensal maior:** aceito na decisão de memória de 2026-11-08.
- **Upgrade escondendo um `mem_limit` mal ajustado:** confira antes se o problema não é um único container (`anon` perto do limite, `max_hits` crescendo); nesse caso o certo é PR no limite.
- Passos exatos do provedor não verificados (sem acesso à web nem ao painel); o 5.4 manda conferir.

Perguntas (recomendações aceitas pelo usuário em 2026-11-08; ficam registradas):

1. **Mitigar em vez de pagar?** Só para um gatilho marginal depois do 31 (G1 entre 100 e 150 MB, sem G3 e G4); o upgrade padrão da Fase 3 não depende disso.
2. **2 ou 4 GB perto do limite da regra?** 2 GB e medir de novo no item 35.
3. **Provedor sem volta para o plano menor?** Aceitar.

## 10. Decisões que exigem ADR

**Nenhuma.** Aumento de capacidade previsto na P3, sem mudar arquitetura, rede ou contrato. Exigiria ADR: trocar de provedor ou de arquitetura (ex.: ARM), ou tirar MLflow ou Prefect da VPS.
