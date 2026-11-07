# 02 — Provisionar a VPS (manual)

> Executa: **usuário**. Nenhum agente tem acesso à VPS. Depende de: nada (pode rodar em paralelo com 01).
> Fase do roadmap: Fase 0 — Base da VPS (`docs/plataforma-ml.md`).

## O que este item entrega

Uma VPS com usuário não-root, Docker, swap, firewall fechado e Tailscale, pronta para receber o compose do PR 03.

## Decisões já tomadas (2026-11-07, ver `00-indice.md`)

- P3 (resolvida em parte): VPS atual do provedor "Regular Cloud Compute", **1 vCPU, 1 GB de RAM, 25 GB de SSD, 1 TB de transferência**. O doc estima 4 GB como confortável para a stack inteira; com 1 GB, as Fases 0 a 2 devem caber, e da Fase 3 em diante a memória é medida (checkpoint 28a) e a VPS só sobe de plano sob necessidade (item condicional 28b). Ainda a confirmar neste item: sistema operacional (recomendado: Ubuntu 24.04 LTS) e arquitetura (`uname -m`; o PR 16 baixa o binário do supercronic para ela).
- P4 (resolvida): rede **só Tailscale**. Nenhuma porta pública ao final deste item; a 22 fica aberta só durante o provisionamento. Sem 443, sem 80, sem domínio.
- P2 (resolvida): repositórios públicos; a VPS clona o repo e puxa imagens do GHCR sem token. Nada de segredo no git: o histórico de um repo público é público.

## Checklist

- [ ] Criar a VPS no provedor com a chave SSH pública do seu notebook. Anotar SO e arquitetura escolhidos.
- [ ] Criar usuário não-root com sudo (ex.: `deploy`) e copiar a chave SSH para ele.
- [ ] Em `/etc/ssh/sshd_config`: `PasswordAuthentication no` e `PermitRootLogin no`; `sudo systemctl restart ssh`.
- [ ] Atualizar o sistema: `sudo apt update && sudo apt upgrade -y`.
- [ ] Swap de 2 GB (a RAM é 1 GB; o swap evita que um pico mate processos, mas não substitui RAM):
  - `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile`
  - `echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab`
  - `echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf && sudo sysctl --system` (usa o swap só quando a RAM aperta).
- [ ] Instalar Docker Engine e o plugin compose pelo repositório oficial da Docker (docs.docker.com, "Install Docker Engine on Ubuntu"). Adicionar o usuário ao grupo `docker`.
- [ ] `sudo systemctl enable docker` (sobe no boot).
- [ ] Instalar Tailscale (tailscale.com/download/linux), `sudo tailscale up`, `sudo systemctl enable tailscaled`.
- [ ] Tornar `deploy` operador do Tailscale, para o script `infra/scripts/tailscale-serve.sh` (PR 03) e o `deploy.sh` (PR 39) rodarem sem sudo: `sudo tailscale set --operator=deploy`.
- [ ] Não habilitar o recurso "Tailscale SSH" (`tailscale up --ssh`): ele assume a porta 22 no IP do Tailscale e ignora o `authorized_keys`, e o deploy do CI (itens 38 e 39) depende da restrição `command=` do `authorized_keys`. O acesso é OpenSSH normal, só que pela tailnet. Se quiser o Tailscale SSH mesmo assim, registre no ADR de rede e replaneje 38 e 39.
- [ ] Só se a P15 ficar com "Postgres no IP do Tailscale": fazer o Docker esperar o Tailscale no boot, `sudo systemctl edit docker` e adicionar `[Unit]` / `After=tailscaled.service` / `Wants=tailscaled.service`. Na outra opção da P15 (loopback + `tailscale serve --tcp`) isso não é necessário, mas também não atrapalha.
- [ ] Firewall com ufw, em duas etapas:
  1. Início: `sudo ufw default deny incoming`, `sudo ufw allow 22/tcp`, `sudo ufw allow in on tailscale0`, `sudo ufw enable`.
  2. Fechar a 22 pública: do notebook, confirme que `ssh deploy@<nome-tailscale>` entra pela tailnet; só então `sudo ufw delete allow 22/tcp`. Se você se trancar fora, use o console web do provedor.
- [ ] Atenção: portas publicadas pelo Docker com `ports:` **passam por cima do ufw**. Por isso os PRs de compose nunca publicam porta em `0.0.0.0`; só em `127.0.0.1` ou no IP do Tailscale (testes do PR 03).
- [ ] Clonar o repositório (público, sem token) em `/opt/platform` (dono: `deploy`).
- [ ] Criar `/opt/platform/infra/.env` vazio com `chmod 600` (será preenchido nos itens 04 e 12). Nunca commitar.
- [ ] Anotar e guardar fora do git: IP público, nome da máquina no Tailscale, IP do Tailscale (`tailscale ip -4`).

## Verificação de pronto

Rodar na VPS, como `deploy`:

| Comando | Saída esperada |
| --- | --- |
| `whoami` | `deploy` |
| `uname -m` | `x86_64` ou `aarch64` (anotar; o PR 16 depende disso) |
| `docker run --rm hello-world` | Contém `Hello from Docker!` (sem sudo) |
| `docker compose version` | `Docker Compose version v2...` |
| `systemctl is-enabled docker tailscaled` | `enabled` duas vezes |
| `tailscale status` | Lista a VPS e o seu notebook |
| `free -m` | Linha `Mem:` com total perto de `960`–`1000`; linha `Swap:` com total perto de `2047` |
| `swapon --show` | `/swapfile` com `2G` |
| `sudo ufw status verbose` | `Status: active`, `Default: deny (incoming)` e só `Anywhere on tailscale0` (depois da etapa 2) |
| `stat -c '%a' /opt/platform/infra/.env` | `600` |

Do notebook: `ssh deploy@<nome-tailscale>` entra sem senha. De fora da tailnet (celular no 4G): `nc -zv -w 5 <ip-publico> 22` falha.

## Teste de reboot (parcial; o completo é no item 04)

- [ ] `sudo reboot`; depois de 1 a 2 minutos, `ssh deploy@<nome-tailscale>` e `systemctl is-active docker tailscaled` retorna `active` duas vezes; `swapon --show` mostra o swap.

## Devolver para o planejamento

SO, arquitetura (`uname -m`) e o nome do host no Tailscale. O PR 16 depende da arquitetura; os PRs 03 e 10 usam o nome.
