# 28a — Checkpoint de memória da VPS antes do MLflow (manual)

> Executa: **usuário**. Depende de: 27 (Fase 2 pronta: Postgres, agendador e os três jobs de ingestão rodando em produção). Precisa estar feito antes de começar o PR 29.
> Fase do roadmap: Fase 3 (pré-requisito). O doc manda "confirmar com `docker stats` depois da Fase 3"; aqui a medição vem antes, porque a VPS tem 1 GB.

## Por que existe

Decisão do usuário (2026-11-07): a VPS tem 1 vCPU, 1 GB de RAM, 25 GB de SSD e 2 GB de swap (item 02). As Fases 0 a 2 devem caber em 1 GB. A Fase 3 acrescenta MLflow e Prefect, que são os serviços mais pesados. Este checkpoint mede o que já roda e decide, com números, se o item condicional 28b (upgrade) é necessário. **Sem gatilho, a Fase 3 segue em 1 GB.**

## Estimativas (a medir, não são fatos)

| Serviço | Estimativa de RAM | `mem_limit` inicial nos specs | Onde entra |
| --- | --- | --- | --- |
| Postgres | 100–250 MB | `256m` | PR 10 |
| Job de ingestão com pandas (pico) | 200–400 MB | `512m` (`jobs` e `agendador`) | PRs 11 e 16 |
| Tailscale (no host, fora do compose) | ~30 MB | — | item 02 |
| MLflow | 300–500 MB | `512m` | PR 29 |
| Prefect server + worker | 500–800 MB | `640m` (server) + `384m` (worker) | PRs 30 e 34 |
| Grafana | 100–200 MB | `256m` | PR 47 |
| Saúde (busybox) | < 5 MB | `16m` | PR 03 |

Soma das estimativas da Fase 3 em diante: cerca de 1,2 a 2,2 GB, acima de 1 GB. Por isso a chance de o 28b ser acionado na Fase 3 é real, mas a decisão é pela medição, não pela soma.

## Checklist

Na VPS, com a stack da Fase 2 no ar:

- [ ] Em repouso (fora dos horários dos jobs): `free -m` e `docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}'`. Anotar.
- [ ] No pico: durante um job de ingestão (ex.: às 06:30, ou disparando um backfill curto com `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion ons-load --start <data> --end <data>`), rodar em outro terminal `docker stats --no-stream` e `free -m` algumas vezes. Anotar o maior uso.
- [ ] Swap ao longo do tempo: `vmstat 5 12` em repouso (colunas `si`/`so`) e `free -m` (linha `Swap:`, coluna `used`) em dois dias diferentes.
- [ ] Processos mortos por falta de memória: `sudo dmesg -T | grep -i -E 'out of memory|killed process'` e `docker inspect -f '{{.Name}} {{.State.OOMKilled}}' $(docker ps -aq)`.
- [ ] Disco (25 GB; as imagens do MLflow e do Prefect são grandes): `df -h /` e `docker system df`. Se passar de 60%, `docker image prune -a` das imagens sem uso antes do PR 29.
- [ ] Comparar com os gatilhos do 28b.

## Gatilhos (mesmos do 28b)

Qualquer um destes, com a stack da fase no ar, aciona o 28b:

1. `free -m`, coluna `available` da linha `Mem:`, abaixo de **~150 MB** em repouso.
2. Swap em uso constante: `si`/`so` diferentes de zero na maior parte das amostras de `vmstat 5 12` em repouso, ou `Swap: used` crescendo entre as medições de dias diferentes.
3. Processo morto por OOM do kernel (`dmesg` com `Killed process` ou `Out of memory`).

Não é gatilho de upgrade: um container com `OOMKilled=true` enquanto o host ainda tem memória disponível. Isso é `mem_limit` baixo demais; suba o limite daquele serviço por PR (o limite vive no compose) e meça de novo.

## Verificação de pronto

| Verificação | Esperado |
| --- | --- |
| Números anotados | Repouso, pico, swap e OOM registrados, com data |
| Decisão anotada | "Sem gatilho: segue em 1 GB" ou "Gatilho <n>: fazer o 28b antes do PR 29" |
| Disco | `df -h /` abaixo de 60% de uso |

## Devolver para o planejamento

Os números medidos por serviço, a decisão e qualquer `mem_limit` que precise mudar. Os specs 29, 30, 34 e 47 usam esses números para ajustar os limites iniciais. A mesma medição se repete nos itens 31, 35, 50 e 59, com os mesmos gatilhos.
