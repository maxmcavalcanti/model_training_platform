# 27 — Backfill do clima observado e critério de pronto da Fase 2 (manual)

> Executa: **usuário**. Depende de: 17 (coleta da previsão ligada), 26 (merge na `main`).
> Fase do roadmap: Fase 2 — "Pronto quando: 7 dias seguidos de snapshots sem falha".

## Checklist

Na VPS, como `deploy`, em `/opt/plataforma`:

- [ ] `git pull`.
- [ ] `docker compose -f infra/docker-compose.yml build jobs agendador`.
- [ ] `docker compose -f infra/docker-compose.yml run --rm jobs alembic upgrade head`.
- [ ] Backfill: `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion clima-observado --inicio 2015-01-01 --fim $(date +%F); echo $?` → `0`.
- [ ] `docker compose -f infra/docker-compose.yml up -d agendador` (crontab novo).

## Verificação de pronto

`docker compose -f infra/docker-compose.yml exec postgres psql -U <admin> -d ml -c "<sql>"`:

| SQL | Saída esperada |
| --- | --- |
| `select local_id, min(data), max(data), count(*) from raw.clima_observado group by 1 order by 1` | 4 linhas, `min` = 2015-01-01, contagens iguais |
| `select emitida_em, count(*) from raw.clima_previsao where emitida_em > current_date - 7 group by 1 order by 1` | 7 linhas consecutivas terminando hoje, todas com `28` |
| `select count(*) from (select emitida_em from raw.clima_previsao group by 1 having count(*) <> 28) x` | `0` |

- [ ] Logs do agendador dos últimos 7 dias sem erro nos três jobs: `docker compose -f infra/docker-compose.yml logs --since 168h agendador | grep -iE "error|traceback"` não devolve nada.

Se as três consultas baterem, a Fase 2 está pronta. Avisar a cientista que `raw.clima_observado` e `raw.clima_previsao` estão disponíveis.
