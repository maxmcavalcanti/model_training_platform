---
paths:
  - "migrations/**"
  - "ingestion/**"
  - "flows/**"
---

# Migrações e ingestão

- Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.
- Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados. Mudança na assinatura do contrato exige ADR.
- Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `cientista` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `leitura` só lê. Toda tabela nova declara quem escreve e quem lê.
- Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingerido_em`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.
- As regras de job (idempotência, reprocessamento por data, retry com backoff só para erro de rede) valem também para flows do Prefect.
- `raw.clima_previsao` guarda a previsão como emitida (`emitida_em`). Nunca sobrescrever uma previsão antiga com uma nova.
