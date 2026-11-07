# ADR 0003: Rede só Tailscale

Status: Aceito
Data: 2026-11-07
Decisores: Maximiliano

## Contexto

O desenho em `docs/plataforma-ml.md` previa Caddy com HTTPS e autenticação e um firewall com as portas 22 e 443 abertas (ou nenhuma porta pública). O usuário decidiu em 2026-11-07 a rede só Tailscale (P4 de `docs/plans/00-indice.md`) e o Postgres em loopback (P15), ambas decisões da mesma data.

MLflow e Prefect não têm autenticação própria. O Docker, ao publicar portas com `ports:`, passa por cima do ufw: uma porta em `0.0.0.0` fica na internet mesmo com o firewall fechado. Sem proxy, a ACL do Tailscale é a única barreira de acesso.

Este ADR foi escrito pelo `task-implementer` por instrução expressa do usuário, como exceção à regra do `AGENTS.md` ("Nenhum agente escreve ADR"). A exceção vale só para este ADR.

## Decisão

### Sem exposição pública

Nenhuma porta pública, sem domínio, sem Caddy, sem certificado público. O ufw nega toda entrada (`ufw default deny incoming`) e aceita só a interface `tailscale0`. A 22 pública fica aberta só no provisionamento e é fechada quando o SSH pela tailnet funciona.

### Publicação no host

Toda porta de serviço do compose fica em `127.0.0.1`, nunca em `0.0.0.0`, porque o Docker ignora o ufw.

### Exposição na tailnet por `tailscale serve`

Os serviços são expostos na tailnet por `tailscale serve`: um hostname `*.ts.net` (MagicDNS), uma porta por UI, HTTPS com o certificado `*.ts.net`. O mapeamento abaixo é o planejado no PR 03 (`docs/plans/03-compose-rede-tailscale.md`); as portas são do plano, não deste ADR, e são verificadas no PR 03.

| Serviço | Host (compose) | Tailnet |
| --- | --- | --- |
| Saúde | `127.0.0.1:8080` | `https://<host>.ts.net:8080/health` |
| MLflow | `127.0.0.1:5000` | `https://<host>.ts.net:5000` |
| Prefect | `127.0.0.1:4200` | `https://<host>.ts.net:4200` |
| Grafana | `127.0.0.1:3000` | `https://<host>.ts.net:3000` |
| Postgres | `127.0.0.1:5432` | `<host>.ts.net:5432` via `tailscale serve --tcp=5432` |

### Postgres (P15)

`127.0.0.1:5432` + `tailscale serve --tcp=5432`, sem sidecar do Tailscale no compose e sem depender da ordem de boot.

### Controle de acesso

A ACL do Tailscale, por tag da VPS e por porta. Não há proxy com senha. As regras concretas ficam nos itens 04, 12, 31, 38 e 50 dos planos.

### SSH

OpenSSH dentro da tailnet. O recurso Tailscale SSH (`tailscale up --ssh`) não é ligado, porque ignora o `authorized_keys` e quebraria a restrição `command=` da chave do deploy (itens 38 e 39).

## Consequências

- Os testes do PR 03 travam "nada em `0.0.0.0`".
- O estado do `tailscale serve` é versionado num script do repo (PR 03). Cada nova UI acrescenta uma entrada (PRs 29, 30 e 47).
- Pré-requisitos no painel e na VPS: MagicDNS, HTTPS Certificates e o usuário `deploy` como operador (`sudo tailscale set --operator=deploy`).
- A cientista e o CI só alcançam a VPS entrando na tailnet (o runner usa `tailscale/github-action` com `tag:ci`), e a ACL limita as portas de cada um.
- O `After=tailscaled.service` do item 02 deixa de ser necessário, porque o Docker não precisa esperar o tailscaled no boot.
- Um monitor de uptime externo não alcança a VPS. O caminho fica em aberto na P17.
- Ligar o Tailscale SSH no futuro exige revisar este ADR e replanejar os itens 38 e 39.
- Qualquer mudança que publique porta ou exponha serviço fora do tailnet/loopback exige novo ADR (`AGENTS.md`, "Fronteira").
- Este PR também atualiza `AGENTS.md`, `docs/plataforma-ml.md` e `.claude/rules/infra.md`.

## Alternativas consideradas

- Caddy com domínio, HTTPS público, `basic_auth` e 443 aberta: o desenho original, rejeitado pela P4.
- Acesso direto pelo IP/nome do tailnet (`*_BIND_IP` = IP do Tailscale): HTTP puro dentro do WireGuard, sem script, mas sem HTTPS válido e com dependência da ordem de boot em todo serviço. Rejeitado em favor do `tailscale serve`.
- Postgres no IP do Tailscale com `After=tailscaled.service`: rejeitado na P15.
- Sidecar do Tailscale no compose: rejeitado pelo usuário na P15.
- Tailscale SSH: rejeitado pelo motivo descrito em "SSH" na Decisão.
