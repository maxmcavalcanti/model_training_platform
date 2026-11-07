---
paths:
  - "migrations/**"
  - "ingestion/**"
---

# Migrações e ingestão

- Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.
- Mudar `raw` ou `ref` é mudança de contrato: exige ADR e aviso à ciência de dados.
- Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `cientista` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `leitura` só lê. Toda tabela nova declara quem escreve e quem lê.
- Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingerido_em`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.
- `raw.clima_previsao` guarda a previsão como emitida (`emitida_em`). Nunca sobrescrever uma previsão antiga com uma nova.
