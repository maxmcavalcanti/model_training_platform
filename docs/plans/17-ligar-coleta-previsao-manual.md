# 17 — Ligar a coleta diária de `raw.clima_previsao` na VPS (manual)

> Executa: **usuário**. Depende de: 12, 13, 15, 16 (merges na `main`).
> Fase do roadmap: Fase 2 (antecipada; desvio de "uma fase por vez" aprovado pelo usuário em 2026-11-07, P5 resolvida). É o item mais urgente do roadmap: cada dia antes dele é histórico que não volta.

## Checklist

Na VPS, como `deploy`, em `/opt/plataforma`:

- [ ] `git pull`.
- [ ] `docker compose -f infra/docker-compose.yml build jobs agendador`.
- [ ] Migrar: `docker compose -f infra/docker-compose.yml run --rm jobs alembic upgrade head`.
- [ ] Rodar uma vez à mão para não esperar o dia seguinte: `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion clima-previsao; echo $?` → `0`.
- [ ] Subir o agendador: `docker compose -f infra/docker-compose.yml up -d agendador`.
- [ ] `docker compose -f infra/docker-compose.yml logs agendador | head` mostra o supercronic lendo o crontab sem erro.

## Verificação de pronto (no dia)

`docker compose -f infra/docker-compose.yml exec postgres psql -U <admin> -d ml -c "<sql>"`:

| SQL | Saída esperada |
| --- | --- |
| `select emitida_em, count(*) from raw.clima_previsao group by 1 order by 1` | Uma linha com a data de hoje e `28` |
| `select count(distinct local_id) from raw.clima_previsao where emitida_em = current_date` | `4` |

## Acompanhamento diário (até existir alerta, PR 55)

- [ ] Todo dia, depois das 06:35 BRT, rodar a consulta abaixo. Se faltar o dia, rodar o job à mão (`run --rm jobs python -m ingestion clima-previsao`) no mesmo dia, antes da meia-noite, para salvar o snapshot:
  `select emitida_em, count(*) from raw.clima_previsao where emitida_em > current_date - 8 group by 1 order by 1`
- [ ] Teste de reboot: depois de um `sudo reboot`, `docker compose -f infra/docker-compose.yml ps agendador` mostra `Up` sem intervenção.

## Critério de pronto da Fase 2 para a previsão

7 dias seguidos de snapshots sem falha: a consulta acima devolve 7 linhas consecutivas, todas com `28`. (A Fase 2 só fecha de vez no item 27, com o clima observado.)
