# 08 — Função de upsert idempotente com `ingerido_em`

> Executa: agente. Depende de: 07. Branch sugerida: `feat/db-upsert`.
> TDD: passo 0 (dependência) → test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar em `ingestion/db.py` uma função `upsert` que grava um DataFrame numa tabela por chave primária (`INSERT ... ON CONFLICT`), carimbando `ingerido_em`.
Todos os jobs de ingestão usam essa função, então a regra "upsert por chave, nunca append cego" fica num lugar só.

## 2. Fora do escopo

- Tabelas reais (cada job tem o seu PR).
- Checagem pandera (PR 15).
- Retry de rede (fica no cliente HTTP de cada fonte).

## 3. Fase do roadmap

Fase 1 — base para "Ingestão do ONS + backfill desde 2015 + checagens" e para a Fase 2.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Dependência `pandas` (passo 0) |
| `ingestion/db.py` | Nova função `upsert` |
| `tests/test_upsert.py` | Testes (test-writer) |

Regras (de `AGENTS.md` e `.claude/rules/migrations-e-dados.md`):

> Todo job de ingestão é idempotente: upsert por chave primária (`INSERT ... ON CONFLICT DO UPDATE`), nunca append cego. Toda linha em `raw` leva `ingerido_em`.
> `raw.clima_previsao` guarda a previsão como emitida (`emitida_em`). Nunca sobrescrever uma previsão antiga com uma nova.

A segunda regra é o motivo do modo `ignorar` abaixo.

## 5. Passos

0. (implementer) `uv add pandas`. Commit `build: add pandas`.
1. (test-writer) Escreva `tests/test_upsert.py` (`@pytest.mark.db`). No arranjo, como admin num banco migrado, crie `raw.teste_upsert (k1 text, k2 date, valor double precision, ingerido_em timestamptz not null, primary key (k1, k2))`. Casos na seção 8. Confirme falha com `ImportError: cannot import name 'upsert'`. Commit `test: add upsert tests`.
2. (implementer) Em `ingestion/db.py`, implemente:
   ```python
   def upsert(
       conn: sqlalchemy.Connection,
       tabela: str,                 # "schema.nome"
       linhas: pd.DataFrame,
       chaves: list[str],
       *,
       ao_conflitar: Literal["atualizar", "ignorar"] = "atualizar",
       carimbar_ingerido_em: bool = True,
   ) -> int: ...
   ```
   - Reflete a tabela (`sqlalchemy.Table(nome, MetaData(schema=...), autoload_with=conn)`).
   - Usa `sqlalchemy.dialects.postgresql.insert`. `atualizar` → `on_conflict_do_update(index_elements=chaves, set_=<todas as colunas não-chave do DataFrame + ingerido_em>)`. `ignorar` → `on_conflict_do_nothing(index_elements=chaves)`.
   - `ingerido_em` vem de `func.now()` do servidor, no insert e no update; nunca do DataFrame.
   - `NaN`/`NaT`/`pd.NA` viram `NULL`.
   - Grava em lotes de 5000 linhas; devolve o total de linhas inseridas ou atualizadas (`rowcount` somado).
   - DataFrame vazio → devolve 0 sem tocar no banco.
   - Coluna do DataFrame que não existe na tabela → `ValueError` com o nome da coluna.
   - Chave ausente no DataFrame → `ValueError`.
   - Não faz `commit`: quem chama controla a transação (`with engine.begin() as conn`).
3. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_upsert.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: idempotência e "nunca sobrescrever previsão" são regras de negócio centrais; um erro aqui duplica ou apaga dado em todas as fontes.

## 8. Casos de teste

1. Tabela vazia, 3 linhas novas → 3 linhas na tabela, todas com `ingerido_em` não nulo; retorno 3.
2. Rodar o mesmo upsert duas vezes → continua com 3 linhas (sem duplicata).
3. `atualizar`: segunda carga com a mesma chave e `valor` diferente → `valor` novo na tabela e `ingerido_em` maior ou igual ao da primeira carga.
4. `ignorar`: segunda carga com a mesma chave e `valor` diferente → `valor` antigo preservado e `ingerido_em` inalterado.
5. Carga mista (1 chave existente, 1 nova) com `ignorar` → a existente intacta, a nova inserida.
6. `NaN` em `valor` → `NULL` no banco.
7. DataFrame vazio → retorno 0, tabela inalterada.
8. DataFrame com coluna `inexistente` → `ValueError` cuja mensagem contém `inexistente`.
9. DataFrame sem a coluna `k2` declarada em `chaves` → `ValueError`.
10. 12 000 linhas → todas gravadas (cobre o lote).
11. Upsert dentro de transação que depois levanta exceção → nada gravado.

## 9. Riscos e perguntas em aberto

- No modo `atualizar`, `ingerido_em` passa a significar "última vez que a linha foi escrita". Alternativa: guardar a primeira entrada e acrescentar `atualizado_em`. Isso muda o schema de `raw` (contrato); manter como está salvo decisão do usuário (P9 no índice).

## 10. Decisões que exigem ADR

Nenhuma.
