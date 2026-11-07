# 21 — Tabela `raw.ons_daily_load`

> Executa: agente. Depende de: 19 (próxima revisão Alembic depois de `0005`). Branch sugerida: `feat/raw-ons-load`.
> Pré-requisito: ADR "Contrato de dados v1" (PR 09).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar por migração a tabela de carga diária do ONS, uma linha por subsistema por dia.
É a tabela que a cientista consulta do notebook para fechar a Fase 1.

## 2. Fora do escopo

- Leitura da fonte (PR 20), job e checagem (PR 22), backfill (item 23).

## 3. Fase do roadmap

Fase 1 — "Ingestão do ONS + backfill desde 2015 + checagens".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0006_raw_ons_daily_load.py` | Tabela; `downgrade` a remove |
| `tests/test_raw_ons_daily_load.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`): `raw.ons_daily_load` — `subsystem`, `date`, `load_avg_mw`, `ingested_at`; chave (`subsystem`, `date`); escreve Plataforma; lê Todos.

## 5. Passos

1. (test-writer) Escreva os testes da seção 8 (`@pytest.mark.db`, banco migrado). Confirme falha porque a tabela não existe. Commit `test: add raw.ons_daily_load tests`.
2. (implementer) `uv run alembic revision -m "raw_ons_daily_load" --rev-id 0006` (se `0006` já estiver em uso, use o próximo número livre e ajuste o nome do arquivo).
3. `upgrade`: `raw.ons_daily_load (subsystem text not null check (subsystem in ('SE','S','NE','N')), date date not null, load_avg_mw double precision not null, ingested_at timestamptz not null, primary key (subsystem, date))`.
   - `load_avg_mw` não aceita nulo: dia sem valor simplesmente não tem linha.
   - A faixa plausível (carga > 0) fica na checagem pandera do PR 22, não no banco, para o job poder gravar e acusar.
4. `downgrade`: `DROP TABLE raw.ons_daily_load`.
5. Permissões pelos privilégios padrão (PR 07).
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_raw_ons_daily_load.py tests/test_migrations.py` | Todos passam |
| `uv run alembic heads` | `0006 (head)` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: chave e restrições fazem parte do contrato com a ciência de dados.

## 8. Casos de teste

1. Inserir (`SE`, 2026-11-05, 40000.0, now()) funciona.
2. Mesma (`subsystem`, `date`) duas vezes sem `ON CONFLICT` → violação de chave primária.
3. `subsystem = 'SIN'` → violação de `CHECK`.
4. `load_avg_mw` nulo → violação de `NOT NULL`.
5. Como `ingestor`, `INSERT` funciona; como `scientist` e `reader`, só `SELECT`.
6. `downgrade` de um passo remove só esta tabela.

## 9. Riscos e perguntas em aberto

- Nenhum além do ADR de contrato.

## 10. Decisões que exigem ADR

Coberto pelo ADR "Contrato de dados v1".
