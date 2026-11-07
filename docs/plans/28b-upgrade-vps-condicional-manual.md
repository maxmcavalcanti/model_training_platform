# 28b — Upgrade da VPS (manual, condicional: só sob necessidade)

> Executa: **usuário**, e **só se** um gatilho disparar no checkpoint 28a ou numa das medições dos itens 31, 35, 50 e 59. Sem gatilho, não faça: a plataforma segue em 1 GB.
> Nenhum PR depende deste item. Se o gatilho disparar no 28a, faça-o antes de começar o PR 29; se disparar mais tarde, antes do próximo PR que acrescenta serviço.
> Fase do roadmap: transversal (a partir da Fase 3).

## Gatilhos (definidos no 28a)

Com a stack da fase no ar:

1. `free -m`, coluna `available`, abaixo de ~150 MB em repouso.
2. Swap em uso constante (`vmstat 5 12` com `si`/`so` diferentes de zero na maior parte das amostras em repouso, ou `Swap: used` crescendo entre dias).
3. Processo morto por OOM do kernel (`sudo dmesg -T | grep -i -E 'out of memory|killed process'` não vazio).

Container com `OOMKilled=true` e host com memória sobrando não é gatilho: ajuste o `mem_limit` daquele serviço por PR.

## Checklist

- [ ] Anotar qual gatilho disparou, com a saída do comando e a data.
- [ ] Antes de redimensionar: conferir que o último backup existe (a partir da Fase 5) ou, antes disso, que o snapshot do provedor está disponível; tirar um snapshot.
- [ ] No painel do provedor, subir para o plano de **2 a 4 GB** de RAM (2 GB se o gatilho foi marginal; 4 GB se a soma medida já passa de 1,5 GB). Conferir se o redimensionamento mantém o IP público e o disco.
- [ ] Depois do redimensionamento, a VPS reinicia: conferir que tudo volta sozinho (mesmo teste de reboot do item 04).
- [ ] Manter o swap de 2 GB (não remover).
- [ ] Repetir a medição do 28a com a stack no ar e anotar.

## Verificação de pronto

| Comando (na VPS) | Saída esperada |
| --- | --- |
| `free -m` | Linha `Mem:` com o total novo (cerca de `1900`+ para 2 GB, `3800`+ para 4 GB); `Swap:` ainda perto de `2047` |
| `nproc` | Número de vCPUs do plano novo |
| `tailscale ip -4` | O mesmo IP do Tailscale de antes (se mudou, atualizar `POSTGRES_BIND_IP` no `.env` e o `VPS_KNOWN_HOSTS` do item 38, se já existir) |
| `docker compose -f /opt/platform/infra/docker-compose.yml ps` | Todos `Up` (`healthy` onde há healthcheck) |
| Do notebook: `curl -s https://<host>.ts.net:8080/health` | `ok` |

## Devolver para o planejamento

O plano novo, a RAM total e a medição depois do upgrade. Os `mem_limit` podem subir por PR se a medição mostrar folga.
