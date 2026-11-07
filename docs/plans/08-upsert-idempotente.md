# 08 — Função de upsert idempotente com `ingested_at`

> Executa: agente. Depende de: 07 (na `main` em `5d02ebd`). Branch sugerida: `feat/db-upsert`.
> TDD: passo 0 (dependência, implementer) → test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-07: alinhado ao que existe na `main` depois dos PRs 05, 06 e 07 (fixtures do `tests/conftest.py`, papéis da `0002`, CI). Pré-requisito de decisão: P9 (seção 9) confirmada pelo usuário antes do test-writer.

## 1. Objetivo

Criar em `ingestion/db.py` uma função `upsert` que grava um DataFrame numa tabela por chave primária (`INSERT ... ON CONFLICT`), carimbando `ingested_at` com o relógio do servidor.
Todos os jobs de ingestão (e o score e o monitoramento) usam essa função, então a regra "upsert por chave, nunca append cego" fica num lugar só.

## 2. Fora do escopo

- Tabelas reais e migrações (cada tabela tem o seu PR: 09, 13, 21, 25, 41, 51). Este PR não cria migração.
- Checagem pandera (`ingestion/checks.py`, PR 15).
- Retry de rede (fica no cliente HTTP de cada fonte, PR 14).
- Coluna `updated_at` ou qualquer mudança de schema de `raw` (depende da P9; ver seção 9).
- Corrigir a linha obsoleta da seção "Comandos" do `AGENTS.md` (ver seção 9): fora do escopo de um PR de código; tarefa própria.
- Validar tipos das colunas contra o banco (o Postgres já recusa tipo errado; o erro do driver sobe como está).

## 3. Fase do roadmap

Fase 1 — base para "Ingestão do ONS + backfill desde 2015 + checagens" e para a coleta da previsão antecipada da Fase 2 (PR 14/15 dependem deste).

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Dependência de runtime `pandas` (passo 0). Entra em `[project].dependencies`, não no grupo `dev`, porque `ingestion/` roda na imagem dos jobs |
| `ingestion/db.py` | Nova função `upsert` (e constantes privadas de lote) |
| `tests/test_upsert.py` | Novo: testes (test-writer), com fixture local que cria as tabelas de teste |

Não alterar: `tests/conftest.py` (as fixtures existentes bastam), `migrations/**`, `alembic.ini`, `.github/workflows/ci.yml` (o CI já sobe Postgres 16 e roda `uv run pytest`, incluindo os testes `db`), `[tool.ruff]` do `pyproject.toml`.

### Regras que se aplicam

De `AGENTS.md` ("Regras de código") e `.claude/rules/migrations-e-dados.md`:

> Todo job de ingestão é idempotente: upsert por chave primária (`INSERT ... ON CONFLICT DO UPDATE`), nunca append cego. Toda linha em `raw` leva `ingested_at`.
> Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `scientist` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `reader` só lê.
> `raw.weather_forecast` guarda a previsão como emitida (`issued_at`). Nunca sobrescrever uma previsão antiga com uma nova.

A última regra é o motivo do modo `ignore`. Nomes em inglês (ADR 0001, seções A, H e B): função `upsert`, parâmetros `table`, `rows`, `keys`, `on_conflict` (`"update"` / `"ignore"`), `stamp_ingested_at`; tabela de teste `raw.upsert_test`; coluna de teste inexistente `nonexistent`. Mensagens de erro do código em inglês.

### Privilégios que existem na `main` (migração `migrations/versions/0002_roles.py`)

- `ingestor`: `USAGE` em todos os schemas; `SELECT` em todas as tabelas; `INSERT, UPDATE` em `raw` e `ref` (inclusive tabelas criadas depois pelo admin, via default privileges). **Sem `DELETE` e sem `TRUNCATE`.** Portanto `upsert` não pode depender de `DELETE` nem de tabela temporária com `MERGE`/`DELETE`; `INSERT ... ON CONFLICT DO UPDATE` precisa de `INSERT`, `UPDATE` e `SELECT`, que o `ingestor` tem.
- `scorer`: o mesmo em `predictions` e `monitoring`.
- Tabelas só nascem por migração (ninguém além do admin tem `CREATE` em `raw`). Nos testes, quem cria as tabelas de teste é o admin, depois do `upgrade head`, para os default privileges valerem.

### Código existente relevante

`ingestion/db.py` hoje (manter tudo; só acrescentar):

```python
"""Single entry point to open a Postgres connection."""

from __future__ import annotations

import os

import sqlalchemy

PLAIN_SCHEME = "postgresql://"
PSYCOPG_SCHEME = "postgresql+psycopg://"


class MissingConfiguration(RuntimeError):
    """Raised when a required configuration value is not set."""


def build_engine(url: str | None = None) -> sqlalchemy.Engine:
    """Build an engine from ``url`` or the ``DATABASE_URL`` environment variable."""
    ...
```

`tests/conftest.py` (na `main`) oferece:

- `fresh_database` (função): banco vazio `ml_test_<8 hex>` por teste, URL `postgresql+psycopg://...` do admin; apagado no teardown.
- `migrated_database` (sessão): banco em `head` **compartilhado pela sessão, só leitura**. Não criar tabelas nele.
- `temp_database_url` (sessão): banco vazio compartilhado.
- `alembic_config()`: função (não fixture) importável com `from tests.conftest import alembic_config`; o `env.py` lê a URL de `DATABASE_URL_ADMIN`.
- Sem servidor, os testes falham (nunca pulam) com a mensagem `Test Postgres unavailable: run docker compose -f infra/docker-compose.dev.yml up -d`.

Padrão já usado em `tests/test_permissions.py` para um banco em `head` com tabelas criadas pelo admin (copiar o padrão, não importar a fixture):

```python
@pytest.fixture
def permissions_database(fresh_database, monkeypatch) -> Iterator[str]:
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    engine = build_engine(fresh_database)
    try:
        with engine.begin() as connection:
            for schema in LOCKED_SCHEMAS:
                connection.execute(text(f"CREATE TABLE {schema}.x (id int PRIMARY KEY)"))
    finally:
        engine.dispose()
    yield fresh_database
```

Downstream que fixa o contrato desta função (não implementar agora, só respeitar):

- PR 15: `upsert(conn, "raw.weather_forecast", df, keys=["location_id", "issued_at", "target_date"], on_conflict="ignore")`.
- PR 19: `upsert(conn, "ref.calendar", df, keys=["date"], on_conflict="update", stamp_ingested_at=False)` (`ref` não tem `ingested_at`).
- PR 22: `upsert(conn, "raw.ons_daily_load", df, keys=["subsystem", "date"], on_conflict="update")`.
- PR 42: `upsert(conn, "predictions.model_predictions", df, keys=[...], on_conflict="ignore", stamp_ingested_at=False)`.
- PR 52: `upsert(conn, "monitoring.model_metrics", df, keys=[...], on_conflict="update", stamp_ingested_at=False)`.

## 5. Passos

0. (implementer, na branch `feat/db-upsert` criada a partir da `main`, **antes** do test-writer) `uv add pandas`. Confira que `pandas` entrou em `[project].dependencies` e que `uv.lock` mudou. Rode `uv run pytest -m "not db"` e `uv run ruff check .` (devem continuar verdes). Commit `build: add pandas` com `pyproject.toml` e `uv.lock`. Motivo: o teste importa `pandas`; sem o passo 0 ele falharia por import quebrado e não por comportamento ausente.
1. (test-writer, na mesma branch, depois do passo 0) Escreva `tests/test_upsert.py`, todos os testes com `@pytest.mark.db`:
   - Fixture local `upsert_database(fresh_database, monkeypatch)`, no padrão de `permissions_database` acima: `DATABASE_URL_ADMIN=fresh_database`, `command.upgrade(alembic_config(), "head")`, e como admin cria:
     - `raw.upsert_test (k1 text, k2 date, value double precision, ingested_at timestamptz not null, primary key (k1, k2))`
     - `raw.upsert_test_unstamped (k1 text primary key, value double precision)` (sem `ingested_at`, para `stamp_ingested_at=False`).
   - Não use `migrated_database` para criar tabelas (é compartilhado e só leitura).
   - A transação é controlada pelo teste: `with engine.begin() as conn: upsert(conn, ...)`. Para "segunda carga", use um segundo `engine.begin()` (transação nova, `now()` novo).
   - Casos na seção 8.
   - Rode `uv run pytest tests/test_upsert.py` com o Postgres de dev de pé e confirme a falha com `ImportError: cannot import name 'upsert' from 'ingestion.db'`. Commit `test: add upsert tests`.
2. (implementer, em worktree a partir da branch com os testes; não editar testes) Em `ingestion/db.py`, implemente:
   ```python
   def upsert(
       conn: sqlalchemy.Connection,
       table: str,                  # "schema.table"
       rows: pd.DataFrame,
       keys: list[str],
       *,
       on_conflict: Literal["update", "ignore"] = "update",
       stamp_ingested_at: bool = True,
   ) -> int: ...
   ```
   Comportamento (é o que os testes verificam):
   - DataFrame vazio (zero linhas) → devolve `0` sem tocar no banco (nem refletir a tabela).
   - `table` precisa ser `"schema.table"`; sem ponto → `ValueError`.
   - Reflete a tabela com `sqlalchemy.Table(name, sqlalchemy.MetaData(schema=schema), autoload_with=conn)`.
   - Validações, todas antes de qualquer escrita, todas `ValueError` com o nome da coluna na mensagem:
     - coluna do DataFrame que não existe na tabela;
     - chave de `keys` ausente no DataFrame;
     - `stamp_ingested_at=True` e a tabela não tem `ingested_at`;
     - `stamp_ingested_at=True` e o DataFrame traz uma coluna `ingested_at` (o carimbo nunca vem do DataFrame);
     - chave duplicada dentro do próprio DataFrame (o Postgres recusaria `ON CONFLICT DO UPDATE` afetando a mesma linha duas vezes no mesmo comando; a mensagem diz `duplicate`).
   - Usa `sqlalchemy.dialects.postgresql.insert`, um comando `INSERT ... VALUES (...), (...)` por lote (lista de dicts em `.values(...)`), para o `rowcount` ser confiável.
   - `ingested_at` = `sqlalchemy.func.now()` do servidor, no insert e, no modo `update`, também no `SET` do conflito. Todas as linhas da mesma transação ficam com o mesmo valor.
   - `update` → `on_conflict_do_update(index_elements=keys, set_={c: excluded.c for c em colunas não-chave do DataFrame} + ingested_at=now())`. Se não houver nenhuma coluna a atualizar (todas as colunas são chave e `stamp_ingested_at=False`), comporta-se como `ignore`.
   - `ignore` → `on_conflict_do_nothing(index_elements=keys)`.
   - `NaN`, `NaT`, `pd.NA` e `None` viram `NULL`.
   - Lotes de no máximo 5000 linhas, e nunca mais que 65535 parâmetros por comando (limite do protocolo do Postgres): linhas por lote = `min(5000, 65535 // número de colunas do DataFrame)`.
   - Devolve a soma dos `rowcount`: no modo `update`, linhas inseridas + atualizadas; no modo `ignore`, só as inseridas.
   - Não faz `commit` nem `rollback`: quem chama controla a transação (`with engine.begin() as conn`).
   - Funciona numa conexão em que foi feito `SET ROLE ingestor` (só usa `SELECT`, `INSERT`, `UPDATE`).
   - Docstring e mensagens em inglês.
3. Rode os critérios de pronto e refatore com a suíte verde. Commit `feat: add idempotent upsert`.

## 6. Critérios de pronto

Pré-condição local: `docker compose -f infra/docker-compose.dev.yml up -d` (Postgres 16 em `127.0.0.1:5432`; o `conftest.py` usa `DATABASE_URL_TEST` ou o padrão `postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres`).

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_upsert.py` | Todos passam, nenhum `skipped` |
| `uv run pytest` | Suíte verde (inclui `test_db.py`, `test_migrations.py`, `test_permissions.py`) |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| `git diff main --stat -- migrations tests/conftest.py .github` | Vazio |
| `gh pr checks` (depois de aberto o PR) | Job `lint-and-test` verde |

## 7. Testes necessários

`sim`: idempotência e "nunca sobrescrever previsão" são regras de negócio centrais; um erro aqui duplica ou apaga dado em todas as fontes.

## 8. Casos de teste

Em `raw.upsert_test` (`k1 text`, `k2 date`, `value double precision`, `ingested_at`), salvo indicação:

1. Tabela vazia, 3 linhas novas (`update`) → 3 linhas na tabela, todas com `ingested_at` não nulo; retorno 3.
2. O mesmo upsert duas vezes, em transações separadas → continua com 3 linhas (sem duplicata); o segundo retorno é 3 (atualizadas).
3. `update`: segunda carga com a mesma chave e `value` diferente → `value` novo na tabela e `ingested_at` maior que o da primeira carga.
4. `ignore`: segunda carga com a mesma chave e `value` diferente → `value` antigo preservado, `ingested_at` inalterado; retorno 0.
5. Carga mista (1 chave existente, 1 nova) com `ignore` → a existente intacta, a nova inserida; retorno 1.
6. `value` com `NaN` numa linha e `pd.NA` (coluna `Float64`) noutra → `NULL` no banco nas duas.
7. DataFrame vazio (com as colunas) → retorno 0, tabela inalterada.
8. DataFrame com coluna `nonexistent` → `ValueError` cuja mensagem contém `nonexistent`; nada gravado.
9. DataFrame sem a coluna `k2` declarada em `keys` → `ValueError` cuja mensagem contém `k2`.
10. DataFrame que traz `ingested_at` com `stamp_ingested_at=True` → `ValueError` cuja mensagem contém `ingested_at`.
11. DataFrame com a mesma chave (`k1`, `k2`) duas vezes → `ValueError` cuja mensagem contém `duplicate`; nada gravado (vale para `update` e `ignore`).
12. `table="upsert_test"` (sem schema) → `ValueError`.
13. 12 000 linhas distintas → 12 000 linhas na tabela; retorno 12 000 (cobre mais de um lote).
14. Upsert dentro de `engine.begin()` que em seguida levanta exceção → nada gravado.
15. Conexão com `SET ROLE ingestor` (a tabela foi criada pelo admin depois do `upgrade head`): upsert `update` de linha nova e depois da mesma chave com `value` novo funcionam; `value` final é o novo.
16. `raw.upsert_test_unstamped` com `stamp_ingested_at=False`, `update`: segunda carga com `value` novo atualiza; retorno 1 em cada carga.
17. `raw.upsert_test_unstamped` com `stamp_ingested_at=True` (padrão) → `ValueError` cuja mensagem contém `ingested_at`.
18. `raw.upsert_test_unstamped`, DataFrame só com `k1`, `stamp_ingested_at=False`, `update`, chave já existente → sem erro, `value` existente preservado; retorno 0.

## 9. Riscos e perguntas em aberto

- **P9 (decisão do usuário, bloqueia este PR; listada em "Pontos de decisão em aberto" de `docs/plans/00-indice.md`, ainda não em "Decisões resolvidas").** No modo `update`, `ingested_at` passa a significar "última vez que a linha foi escrita" (o ONS reescreve 30 dias todo dia, então `ingested_at` do ONS vira "ontem" para todo o mês). Recomendação do índice: última escrita, sem coluna nova. Alternativa: `ingested_at` = primeira entrada (não atualizar no conflito) + `updated_at` = última escrita, o que acrescenta coluna em todas as tabelas de `raw` (contrato com a ciência de dados). Este plano implementa "última escrita" (casos 3 e 15). Se o usuário escolher a alternativa, o plano precisa de revisão antes do test-writer (casos 3, 15 e o `SET` do conflito) e a coluna `updated_at` entraria no ADR "Contrato de dados v1".
- Conversão de tipos do pandas para o psycopg: colunas `datetime64` viram `pd.Timestamp` (aceito pelo psycopg como `datetime`); escalares numpy (`numpy.int64`, `numpy.float64`) podem não ser adaptados por todas as versões do psycopg. A implementação deve entregar tipos Python nativos ao driver (ex.: `DataFrame.to_dict("records")` após trocar nulos por `None`). Os casos 1 a 13 usam `k2` como `datetime.date` e `value` `float64`, o que cobre o caso comum.
- `func.now()` é o início da transação: um job que grava várias tabelas na mesma transação carimba todas com o mesmo instante. É o desejado.
- Desempenho do backfill do ONS (2015 em diante, ~4 subsistemas × ~4000 dias ≈ 16 000 linhas): poucos lotes, sem risco. Medir só se a Fase 2 trouxer volumes maiores.
- `AGENTS.md`, seção "Comandos", ainda diz "Migrações e Postgres de teste: ainda não existem (PRs 05 e 06)", o que está obsoleto desde os PRs 05 a 07. Fica fora deste PR (seção 2); o usuário decide se abre uma tarefa própria.

## 10. Decisões que exigem ADR

Nenhuma, desde que a P9 fique com "última escrita" (sem mudança de schema de `raw` nem de assinatura do contrato `build_features`/`predict`/`evaluate`). Este PR não depende do ADR "Contrato de dados v1" (P8, P18), que é pré-requisito do 09 e do 13. Se a P9 for para "primeira entrada + `updated_at`", a coluna nova muda o contrato de `raw` e precisa entrar num ADR (o de contrato v1 é o lugar natural) mergeado antes deste PR.
