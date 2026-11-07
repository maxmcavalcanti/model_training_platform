# 04 — Publicar o Caddy na VPS e testar reboot (manual)

> Executa: **usuário**. Depende de: 02 (VPS pronta) e 03 (merge do compose com Caddy).
> Fase do roadmap: Fase 0 — "Pronto quando: um reboot traz tudo de volta sem intervenção".

## Por que é manual

Exige acesso à VPS, ao painel de DNS e a um segredo (senha do `basic_auth`). Até a Fase 3 não existe deploy automático; este item usa a exceção temporária de deploy manual (decisão P6 no índice).

## Checklist

- [ ] Opção de rede (a), pública: criar registro DNS `A` do domínio (ex.: `plataforma.seudominio.com`) apontando para o IP público da VPS. Conferir: `dig +short plataforma.seudominio.com` devolve o IP.
- [ ] Opção (b), só Tailscale: usar o nome `*.ts.net` da máquina; habilitar HTTPS no painel admin do Tailscale (DNS → HTTPS Certificates).
- [ ] Gerar o hash da senha na VPS: `docker run --rm caddy:2 caddy hash-password --plaintext '<senha>'`. Guardar a senha num gerenciador de senhas.
- [ ] Na VPS: `cd /opt/plataforma && git pull`.
- [ ] Preencher `infra/.env` a partir de `infra/.env.example` (`DOMINIO`, `CADDY_BIND_IP`, `CADDY_USUARIO`, `CADDY_SENHA_HASH`). Manter `chmod 600`.
  - Atenção: no `.env` do compose, `$` do hash bcrypt precisa ser escrito como `$$`.
- [ ] `docker compose -f infra/docker-compose.yml up -d`.
- [ ] `docker compose -f infra/docker-compose.yml logs caddy | grep -i "certificate obtained"` (opção a) mostra o certificado emitido.

## Verificação de pronto

Do notebook:

| Comando | Saída esperada |
| --- | --- |
| `curl -s https://<dominio>/saude` | `ok` |
| `curl -s -o /dev/null -w '%{http_code}' https://<dominio>/` | `401` |
| `curl -s -u <usuario>:<senha> https://<dominio>/` | `plataforma` |
| `curl -sv https://<dominio>/saude 2>&1 \| grep "SSL certificate verify ok"` | Uma linha (certificado válido) |

Teste de reboot (critério da Fase 0):

- [ ] `sudo reboot` na VPS.
- [ ] Sem entrar na VPS, depois de 2 minutos, do notebook: `curl -s https://<dominio>/saude` devolve `ok`.
- [ ] Na VPS: `docker compose -f /opt/plataforma/infra/docker-compose.yml ps` mostra `caddy` com `Up`.

Se o reboot exigir qualquer intervenção, a Fase 0 não está pronta: anote o que foi preciso e devolva para o planejamento.
