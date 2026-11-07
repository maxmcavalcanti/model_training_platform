# 25 — Tabela `raw.clima_observado`

> Executa: agente. Depende de: 21 (próxima revisão Alembic). Branch sugerida: `feat/raw-clima-observado`.
> Pré-requisito: ADR "Contrato de dados v1" (PR 09).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar por migração a tabela de clima observado diário por local.
É o "real" do modelo `chuva_d1` e a fonte de clima para treino do `carga_d1`.

## 2. Fora do escopo

- Cliente (PR 24), job, checagem e backfill (PR 26 e item 27).

## 3. Fase do roadmap

Fase 2 — "`raw.clima_observado` + backfill desde 2015".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0007_raw_clima_observado.py` | Tabela; `downgrade` a remove |
| `tests/test_raw_clima_observado.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`): `raw.clima_observado` — `local_id`, `data`, `temp_max`, `temp_min`, `precip_mm`, `vento_max`, `umidade_media`, `ingerido_em`; chave (`local_id`, `data`); escreve Plataforma; lê Todos.

## 5. Passos

1. (test-writer) Escreva os testes da seção 8 (`@pytest.mark.db`, banco migrado). Confirme falha porque a tabela não existe. Commit `test: add raw.clima_observado tests`.
2. (implementer) `uv run alembic revision -m "raw_clima_observado" --rev-id 0007` (ou o próximo número livre).
3. `upgrade`: `raw.clima_observado (local_id text not null references ref.locais(local_id), data date not null, temp_max double precision, temp_min double precision, precip_mm double precision, vento_max double precision, umidade_media double precision, ingerido_em timestamptz not null, primary key (local_id, data))`. Variáveis aceitam nulo, como em `raw.clima_previsao` (PR 13).
4. `downgrade`: `DROP TABLE raw.clima_observado`.
5. Permissões pelos privilégios padrão (PR 07).
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_raw_clima_observado.py tests/test_migracoes.py` | Todos passam |
| `uv run alembic heads` | `0007 (head)` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: chave e chave estrangeira fazem parte do contrato.

## 8. Casos de teste

1. Inserir (`recife`, 2026-11-05, valores, now()) funciona.
2. Mesma (`local_id`, `data`) duas vezes sem `ON CONFLICT` → violação de chave primária.
3. `local_id` inexistente em `ref.locais` → violação de chave estrangeira.
4. Variáveis nulas são aceitas.
5. Como `ingestor`, `INSERT` funciona; como `cientista` e `leitura`, só `SELECT`.
6. `downgrade` de um passo remove só esta tabela.

## 9. Riscos e perguntas em aberto

- Nenhum além do ADR de contrato.

## 10. Decisões que exigem ADR

Coberto pelo ADR "Contrato de dados v1".
