# 02 — Provisionar a VPS (manual)

> Executa: **usuário**. Nenhum agente tem acesso à VPS. Depende de: nada (pode rodar em paralelo com 01).
> Fase do roadmap: Fase 0 — Base da VPS (`docs/plataforma-ml.md`).

## O que este item entrega

Uma VPS com usuário não-root, Docker, firewall e Tailscale, pronta para receber o compose do PR 03.

## Decisões a tomar antes (ver `00-indice.md`)

- P3: provedor, sistema operacional (recomendado: Ubuntu 24.04 LTS) e tamanho (doc: 4 GB de RAM como mínimo confortável).
- P4: rede. (a) Portas 22 e 443 públicas com Caddy + domínio, ou (b) nenhuma porta pública, tudo via Tailscale. O checklist abaixo cobre as duas; marque qual seguiu.

## Checklist

- [ ] Criar a VPS no provedor com a chave SSH pública do seu notebook.
- [ ] Criar usuário não-root com sudo (ex.: `deploy`) e copiar a chave SSH para ele.
- [ ] Em `/etc/ssh/sshd_config`: `PasswordAuthentication no` e `PermitRootLogin no`; `sudo systemctl restart ssh`.
- [ ] Atualizar o sistema: `sudo apt update && sudo apt upgrade -y`.
- [ ] Instalar Docker Engine e o plugin compose pelo repositório oficial da Docker (docs.docker.com, "Install Docker Engine on Ubuntu"). Adicionar o usuário ao grupo `docker`.
- [ ] `sudo systemctl enable docker` (sobe no boot).
- [ ] Instalar Tailscale (tailscale.com/download/linux), `sudo tailscale up`, `sudo systemctl enable tailscaled`.
- [ ] Fazer o Docker esperar o Tailscale no boot (necessário se o Postgres do PR 10 publicar porta no IP do Tailscale): `sudo systemctl edit docker` e adicionar `[Unit]` / `After=tailscaled.service` / `Wants=tailscaled.service`.
- [ ] Firewall com ufw:
  - Opção (a): `sudo ufw default deny incoming`, `sudo ufw allow 22/tcp`, `sudo ufw allow 443/tcp`, `sudo ufw allow 80/tcp` (só se o Caddy usar desafio HTTP-01 do Let's Encrypt; sem isso, não abra), `sudo ufw enable`.
  - Opção (b): `sudo ufw default deny incoming`, `sudo ufw allow in on tailscale0`, `sudo ufw enable`. Antes de habilitar, confirme que consegue entrar por SSH pelo IP do Tailscale, senão você se tranca fora.
- [ ] Atenção: portas publicadas pelo Docker com `ports:` **passam por cima do ufw**. Por isso os PRs de compose nunca publicam porta em `0.0.0.0`, exceto o Caddy na opção (a).
- [ ] Clonar o repositório em `/opt/plataforma` (dono: `deploy`).
- [ ] Criar `/opt/plataforma/infra/.env` vazio com `chmod 600` (será preenchido nos itens 04 e 12). Nunca commitar.
- [ ] Anotar e guardar fora do git: IP público, nome da máquina no Tailscale, IP do Tailscale (`tailscale ip -4`).

## Verificação de pronto

Rodar na VPS, como `deploy`:

| Comando | Saída esperada |
| --- | --- |
| `whoami` | `deploy` |
| `docker run --rm hello-world` | Contém `Hello from Docker!` (sem sudo) |
| `docker compose version` | `Docker Compose version v2...` |
| `systemctl is-enabled docker tailscaled` | `enabled` duas vezes |
| `tailscale status` | Lista a VPS e o seu notebook |
| `sudo ufw status verbose` | `Status: active`, `Default: deny (incoming)` e só as regras da opção escolhida |
| `stat -c '%a' /opt/plataforma/infra/.env` | `600` |

Do notebook: `ssh deploy@<nome-tailscale>` entra sem senha.

## Teste de reboot (parcial; o completo é no item 04)

- [ ] `sudo reboot`; depois de 1 a 2 minutos, `ssh deploy@<nome-tailscale>` e `systemctl is-active docker tailscaled` retorna `active` duas vezes.

## Devolver para o planejamento

Qual opção de rede (P4) foi seguida e o nome do host no Tailscale. Os PRs 03 e 10 dependem disso.
