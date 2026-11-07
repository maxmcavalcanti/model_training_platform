# 21 — Tabela `raw.ons_carga_diaria`

> Executa: agente. Depende de: 19 (próxima revisão Alembic depois de `0005`). Branch sugerida: `feat/raw-ons-carga`.
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
| `migrations/versions/0006_raw_ons_carga_diaria.py` | Tabela; `downgrade` a remove |
| `tests/test_raw_ons_carga_diaria.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`): `raw.ons_carga_diaria` — `subsistema`, `data`, `carga_mwmed`, `ingerido_em`; chave (`subsistema`, `data`); escreve Plataforma; lê Todos.

## 5. Passos

1. (test-writer) Escreva os testes da seção 8 (`@pytest.mark.db`, banco migrado). Confirme falha porque a tabela não existe. Commit `test: add raw.ons_carga_diaria tests`.
2. (implementer) `uv run alembic revision -m "raw_ons_carga_diaria" --rev-id 0006` (se `0006` já estiver em uso, use o próximo número livre e ajuste o nome do arquivo).
3. `upgrade`: `raw.ons_carga_diaria (subsistema text not null check (subsistema in ('SE','S','NE','N')), data date not null, carga_mwmed double precision not null, ingerido_em timestamptz not null, primary key (subsistema, data))`.
   - `carga_mwmed` não aceita nulo: dia sem valor simplesmente não tem linha.
   - A faixa plausível (carga > 0) fica na checagem pandera do PR 22, não no banco, para o job poder gravar e acusar.
4. `downgrade`: `DROP TABLE raw.ons_carga_diaria`.
5. Permissões pelos privilégios padrão (PR 07).
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_raw_ons_carga_diaria.py tests/test_migracoes.py` | Todos passam |
| `uv run alembic heads` | `0006 (head)` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: chave e restrições fazem parte do contrato com a ciência de dados.

## 8. Casos de teste

1. Inserir (`SE`, 2026-11-05, 40000.0, now()) funciona.
2. Mesma (`subsistema`, `data`) duas vezes sem `ON CONFLICT` → violação de chave primária.
3. `subsistema = 'SIN'` → violação de `CHECK`.
4. `carga_mwmed` nulo → violação de `NOT NULL`.
5. Como `ingestor`, `INSERT` funciona; como `cientista` e `leitura`, só `SELECT`.
6. `downgrade` de um passo remove só esta tabela.

## 9. Riscos e perguntas em aberto

- Nenhum além do ADR de contrato.

## 10. Decisões que exigem ADR

Coberto pelo ADR "Contrato de dados v1".
