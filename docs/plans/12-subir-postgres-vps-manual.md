# 12 — Subir o Postgres na VPS, migrar e dar acesso à cientista (manual)

> Executa: **usuário**. Depende de: 04, 09, 10, 11 (merges na `main`).
> Fase do roadmap: Fase 1.

## Por que é manual

Exige SSH na VPS, criar segredos (senhas dos papéis) e convidar outra pessoa para o Tailscale. Até a Fase 3, atualizar a VPS é manual (decisão P6 no índice).

## Checklist

Na VPS, como `deploy`, em `/opt/plataforma`:

- [ ] `git pull`.
- [ ] Gerar senhas fortes (ex.: `openssl rand -base64 24`) para: admin, `ingestor`, `cientista`, `scorer`, `leitura`. Guardar no gerenciador de senhas.
- [ ] Acrescentar ao `infra/.env` (ver `infra/.env.example`): `POSTGRES_ADMIN_USUARIO`, `POSTGRES_ADMIN_SENHA`, `POSTGRES_BIND_IP=<tailscale ip -4>`, `POSTGRES_INGESTOR_SENHA`. Conferir `stat -c '%a' infra/.env` = `600`.
- [ ] `docker compose -f infra/docker-compose.yml up -d --wait postgres`.
- [ ] `docker compose -f infra/docker-compose.yml build jobs`.
- [ ] Migrar: `docker compose -f infra/docker-compose.yml run --rm -e DATABASE_URL=$DATABASE_URL_ADMIN jobs alembic upgrade head` — ou, mais simples, `... run --rm jobs alembic upgrade head` (o `env.py` prefere `DATABASE_URL_ADMIN`, que o serviço `jobs` já recebe).
- [ ] Definir as senhas dos papéis (a migração cria os papéis sem senha, de propósito). Rodar sem deixar a senha no histórico do shell (por exemplo, com `read -s` antes):
  `docker compose -f infra/docker-compose.yml exec postgres psql -U <admin> -d ml -c "ALTER ROLE ingestor PASSWORD '<senha>'"` (repetir para `cientista`, `scorer`, `leitura`).
- [ ] Tailscale: convidar a cientista para a tailnet (ou compartilhar a máquina com ela, "Share" no painel). Na ACL, liberar para ela só `vps:5432` agora (MLflow entra na Fase 3).
- [ ] Enviar a ela, por canal seguro, usuário `cientista`, senha, host (`<nome>.ts.net`), porta 5432, banco `ml`.

## Verificação de pronto

| Onde | Comando | Saída esperada |
| --- | --- | --- |
| VPS | `docker compose -f infra/docker-compose.yml run --rm jobs alembic current` | A cabeça atual, com `(head)` |
| VPS | `docker compose -f infra/docker-compose.yml ps postgres` | `Up ... (healthy)` |
| Internet (fora da tailnet, ex.: celular no 4G) | `nc -zv <ip-publico> 5432` | Falha (porta fechada) |
| Notebook dela | `psql "host=<nome>.ts.net port=5432 dbname=ml user=cientista" -c "select count(*) from ref.locais"` | `4` |
| Notebook dela | `psql ... -c "insert into ref.locais values ('x','x',0,0,'SE')"` | `permission denied` |

Teste de reboot:

- [ ] `sudo reboot`; depois, sem entrar na VPS, o `psql` dela volta a funcionar e `curl https://<dominio>/saude` responde `ok`. Se o Postgres não subir por falta do IP do Tailscale, ver P15 no índice.
