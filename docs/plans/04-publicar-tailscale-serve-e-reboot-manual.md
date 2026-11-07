# 04 — Publicar a saúde na tailnet (`tailscale serve`) e testar reboot (manual)

> Executa: **usuário**. Depende de: 02 (VPS pronta) e 03 (merge do compose e do script `tailscale-serve.sh`).
> Fase do roadmap: Fase 0 — "Pronto quando: um reboot traz tudo de volta sem intervenção".
> Rede só Tailscale (decisão do usuário, 2026-11-07): nada de DNS público, domínio, certificado público ou senha de proxy.

## Por que é manual

Exige acesso à VPS e ao painel admin do Tailscale. Até a Fase 3 não existe deploy automático; este item usa a exceção temporária de deploy manual (decisão P6 no índice).

## Checklist

Painel admin do Tailscale:

- [ ] DNS → MagicDNS habilitado.
- [ ] DNS → HTTPS Certificates habilitado (o `tailscale serve` emite o certificado `*.ts.net`).
- [ ] Access controls (ACL): marcar a VPS com uma tag (ex.: `tag:plataforma`) e permitir os seus dispositivos para `tag:plataforma:22,8080`. A cientista entra no item 12 e o CI no item 38.
- [ ] Anotar o nome MagicDNS completo da VPS (`<host>.<tailnet>.ts.net`, visto em `tailscale status --json | jq -r .Self.DNSName` na VPS, sem o ponto final).

VPS, como `deploy`, em `/opt/plataforma`:

- [ ] `git pull`.
- [ ] Preencher `infra/.env` a partir de `infra/.env.example`: `SAUDE_BIND_IP=127.0.0.1`, `TS_HOSTNAME=<host>.<tailnet>.ts.net`. Manter `chmod 600`. Nenhum segredo deste arquivo vai para o git (os repos são públicos).
- [ ] `docker compose -f infra/docker-compose.yml up -d --wait`.
- [ ] `infra/scripts/tailscale-serve.sh` (roda sem sudo porque `deploy` é operador do Tailscale, item 02).
- [ ] `tailscale serve status` mostra `https://<host>.ts.net:8080` → `http://127.0.0.1:8080`.
- [ ] Anotar a linha de base de memória (insumo do checkpoint 28a): `free -m` e `docker stats --no-stream`.

## Verificação de pronto

Do notebook (na tailnet):

| Comando | Saída esperada |
| --- | --- |
| `curl -s https://<host>.ts.net:8080/saude` | `ok` |
| `curl -sv https://<host>.ts.net:8080/saude 2>&1 \| grep "SSL certificate verify ok"` | Uma linha (certificado `*.ts.net` válido) |

Na VPS (nada escuta na internet):

| Comando | Saída esperada |
| --- | --- |
| `docker ps --format '{{.Names}} {{.Ports}}' \| grep -c '0\.0\.0\.0'` | `0` |
| `sudo ss -tlnH \| awk '{print $4}' \| grep -v -E '^(127\.0\.0\.1\|\[::1\]\|100\.)' ` | No máximo a linha do `sshd` na 22, que o ufw bloqueia depois do item 02 |
| `sudo ufw status verbose` | `Default: deny (incoming)` e só a regra `on tailscale0` (a 22 pública já fechada no item 02) |

De fora da tailnet (ex.: celular no 4G, sem Tailscale):

| Comando | Saída esperada |
| --- | --- |
| `curl -s --max-time 5 http://<ip-publico>:8080/saude` | Falha (timeout ou conexão recusada) |
| `nc -zv -w 5 <ip-publico> 22` | Falha |

Teste de reboot (critério da Fase 0):

- [ ] `sudo reboot` na VPS.
- [ ] Sem entrar na VPS, depois de 2 minutos, do notebook: `curl -s https://<host>.ts.net:8080/saude` devolve `ok` (prova que o Docker, o container e a configuração do `tailscale serve` voltaram sozinhos).
- [ ] Na VPS: `docker compose -f /opt/plataforma/infra/docker-compose.yml ps` mostra `saude` com `Up (healthy)`; `tailscale serve status` mostra o mapeamento; `swapon --show` mostra o swap de 2 GB.

Se o reboot exigir qualquer intervenção (inclusive rodar de novo o `tailscale-serve.sh`), a Fase 0 não está pronta: anote o que foi preciso e devolva para o planejamento.
