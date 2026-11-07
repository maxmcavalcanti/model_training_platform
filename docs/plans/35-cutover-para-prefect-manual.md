# 35 — Passar o agendamento do supercronic para o Prefect (manual)

> Executa: **usuário**. Depende de: 31, 32, 33, 34 (merges na `main`).
> Fase do roadmap: Fase 3 — "Ingestões migradas para flows do Prefect".

## Por que é manual

A troca precisa ser observada em produção por pelo menos um dia antes de desligar o agendador antigo, e o `raw.clima_previsao` não pode perder um dia. Rodar os dois em paralelo é seguro: jobs idempotentes e previsão com "ignorar" no conflito.

## Checklist

- [ ] Na VPS, em `/opt/plataforma`: `git pull`; `docker compose -f infra/docker-compose.yml build jobs prefect-worker agendador`.
- [ ] `docker compose -f infra/docker-compose.yml up -d prefect-worker`.
- [ ] `docker compose -f infra/docker-compose.yml run --rm jobs python -m flows.deployments`.
- [ ] Na UI do Prefect (`https://prefect.<dominio>`): os três deployments `.../producao` aparecem com agenda e fuso `America/Sao_Paulo`; o work pool `plataforma` tem um worker `Online`.
- [ ] Disparar uma vez à mão pela UI o `ingest_clima_observado/producao` e ver `Completed`.
- [ ] Esperar o dia seguinte com **os dois** agendadores ligados.

## Verificação de pronto

No dia seguinte, depois das 07:10 BRT:

| Onde | O que | Esperado |
| --- | --- | --- |
| UI do Prefect | Execuções agendadas dos três deployments de hoje | Três `Completed` |
| VPS | `... exec postgres psql -U <admin> -d ml -c "select count(*) from raw.clima_previsao where emitida_em = current_date"` | `28` (não 56: a segunda execução não duplicou) |
| VPS | `docker compose -f infra/docker-compose.yml logs --since 6h agendador` | Também rodou, sem erro |

- [ ] Se tudo bateu, liberar o merge do PR 36 (remover o agendador).
- [ ] Teste de reboot: `sudo reboot`; worker volta `Online` na UI sem intervenção.
