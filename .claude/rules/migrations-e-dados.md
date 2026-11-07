---
paths:
  - "migrations/**"
  - "ingestion/**"
  - "flows/**"
---

# Migrações e ingestão

- Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.
- Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados. Mudança na assinatura do contrato exige ADR.
- Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `scientist` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `reader` só lê. Toda tabela nova declara quem escreve e quem lê.
- Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.
- As regras de job (idempotência, reprocessamento por data, retry com backoff só para erro de rede) valem também para flows do Prefect.
- `raw.weather_forecast` guarda a previsão como emitida (`issued_at`). Nunca sobrescrever uma previsão antiga com uma nova.
