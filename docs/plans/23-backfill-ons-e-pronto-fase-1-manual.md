# 23 — Backfill do ONS desde 2015, calendário e critério de pronto da Fase 1 (manual)

> Executa: **usuário**. Depende de: 12, 19, 22 (merges na `main`).
> Fase do roadmap: Fase 1 — "Pronto quando: ela consulta `raw.ons_daily_load` do notebook dela via Tailscale".

## Checklist

Na VPS, como `deploy`, em `/opt/platform`:

- [ ] `git pull`.
- [ ] `docker compose -f infra/docker-compose.yml build jobs scheduler`.
- [ ] `docker compose -f infra/docker-compose.yml run --rm jobs alembic upgrade head`.
- [ ] Calendário: `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion calendar --start 2015-01-01 --end 2030-12-31; echo $?` → `0`.
- [ ] Backfill do ONS: `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion ons-load --start 2015-01-01 --end $(date +%F); echo $?` → `0`.
- [ ] Reiniciar o agendador para ler o crontab novo: `docker compose -f infra/docker-compose.yml up -d scheduler`.
- [ ] No dia seguinte, depois das 07:05 BRT, `docker compose -f infra/docker-compose.yml logs --since 1h scheduler` mostra `ons-load` terminando sem erro.

## Verificação de pronto

Na VPS (`... exec postgres psql -U <admin> -d ml -c "<sql>"`):

| SQL | Saída esperada |
| --- | --- |
| `select count(*) from ref.calendar` | `5844` |
| `select subsystem, min(date), max(date), count(*) from raw.ons_daily_load group by 1 order by 1` | 4 linhas; `min` = 2015-01-01; `max` a no máximo 2 dias de hoje; contagens iguais entre subsistemas |
| `select date from generate_series('2015-01-01'::date, current_date - 2, '1 day') date except select date from raw.ons_daily_load` | Nenhuma linha (sem buracos) |

No notebook da cientista (critério da fase):

| Comando | Saída esperada |
| --- | --- |
| `psql "host=<nome>.ts.net port=5432 dbname=ml user=scientist" -c "select subsystem, max(date) from raw.ons_daily_load group by 1"` | 4 linhas |

- [ ] Avisar a cientista que a Fase 1 terminou e que ela pode explorar `raw.ons_daily_load`, `ref.calendar` e `ref.locations` (o guia diz que ela começa a exploração aqui).
