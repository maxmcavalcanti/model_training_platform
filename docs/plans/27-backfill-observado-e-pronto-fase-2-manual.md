# 27 — Backfill do clima observado e critério de pronto da Fase 2 (manual)

> Executa: **usuário**. Depende de: 17 (coleta da previsão ligada), 26 (merge na `main`).
> Fase do roadmap: Fase 2 — "Pronto quando: 7 dias seguidos de snapshots sem falha".

## Checklist

Na VPS, como `deploy`, em `/opt/platform`:

- [ ] `git pull`.
- [ ] `docker compose -f infra/docker-compose.yml build jobs scheduler`.
- [ ] `docker compose -f infra/docker-compose.yml run --rm jobs alembic upgrade head`.
- [ ] Backfill: `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion weather-observed --start 2015-01-01 --end $(date +%F); echo $?` → `0`.
- [ ] `docker compose -f infra/docker-compose.yml up -d scheduler` (crontab novo).

## Verificação de pronto

`docker compose -f infra/docker-compose.yml exec postgres psql -U <admin> -d ml -c "<sql>"`:

| SQL | Saída esperada |
| --- | --- |
| `select location_id, min(date), max(date), count(*) from raw.weather_observed group by 1 order by 1` | 4 linhas, `min` = 2015-01-01, contagens iguais |
| `select issued_at, count(*) from raw.weather_forecast where issued_at > current_date - 7 group by 1 order by 1` | 7 linhas consecutivas terminando hoje, todas com `28` |
| `select count(*) from (select issued_at from raw.weather_forecast group by 1 having count(*) <> 28) x` | `0` |

- [ ] Logs do agendador dos últimos 7 dias sem erro nos três jobs: `docker compose -f infra/docker-compose.yml logs --since 168h scheduler | grep -iE "error|traceback"` não devolve nada.

Se as três consultas baterem, a Fase 2 está pronta. Avisar a cientista que `raw.weather_observed` e `raw.weather_forecast` estão disponíveis.
