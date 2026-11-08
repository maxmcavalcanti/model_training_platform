# 21 — Tabela `raw.ons_daily_load`

> Executa: agente. Depende de: **19 mergeado** (`docs/plans/19-ref-calendario.md`, que cria a migração `0005`, `ref.calendar`). Esta tabela é a migração `0006`, com `down_revision = "0005"`. Branch sugerida: `feat/raw-ons-load`.
> Pré-requisito: ADR 0005 (`docs/adr/0005-data-contract-v1.md`), já mergeado; ele lista o PR 21 nas "Consequências". Nenhum ADR novo é necessário (seção 10).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-08: alinhado à `main` em `5d7f1c3` (migrações `0001` a `0004` na `main`; `0005` reservada ao PR 19; papéis e privilégios padrão da `0002`; padrão de `0004_raw_weather_forecast.py` e de `tests/test_raw_weather_forecast.py`; fixtures de `tests/conftest.py`; contrato do `upsert` em `ingestion/db.py`; fatos do ONS registrados em `docs/plataforma-ml.md`, item 18). As perguntas com recomendação viraram decisões D1 a D10 (seção 9), por autorização do usuário. Não há bloqueio além da ordem de merge (PR 19 antes).

## 1. Objetivo

Criar por migração Alembic (`0006`) a tabela `raw.ons_daily_load`, uma linha por subsistema (`SE`, `S`, `NE`, `N`) por dia, com a carga média diária em MWmed, chave (`subsystem`, `date`) e `UPDATE` mantido para o `ingestor`, porque o ONS revisa dias já publicados.
É a tabela que a cientista consulta do notebook para fechar a Fase 1.

## 2. Fora do escopo

- Leitura do parquet do ONS (PR 20, `docs/plans/20-leitura-ons.md`), job `ons-load`, checagem pandera e crontab (PR 22, `docs/plans/22-job-ons-carga.md`), backfill e carga em produção (item 23).
- Chave estrangeira de `date` para `ref.calendar` (D1) e de `subsystem` para `ref.locations` (D2).
- `CHECK` de faixa plausível em `load_avg_mw` (carga > 0): fica na checagem pandera do PR 22 (D4).
- `DEFAULT now()` em `ingested_at`: quem carimba é o `upsert` (`stamp_ingested_at=True`); faltar o carimbo deve falhar alto (`NOT NULL`), como na `0004`.
- Colunas além do modelo de dados (por exemplo `nom_subsistema`, `updated_at`, `first_ingested_at`): exigiriam ADR (ADR 0005, P9).
- Índices além da chave primária (a tabela cresce 4 linhas por dia).
- `GRANT` ou `REVOKE` explícitos: as permissões vêm só dos privilégios padrão da `0002` (D3).
- Alterar `migrations/versions/0001` a `0005`, `ingestion/` (inclusive `ingestion/db.py`), `tests/conftest.py`, `tests/test_migrations.py`, `tests/test_permissions.py`, `tests/test_ref_locations.py`, `tests/test_raw_weather_forecast.py`, `tests/test_ref_calendar.py`, `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `.claude/`, `AGENTS.md`, o ADR 0005 ou outros planos.
- Corrigir em `docs/plataforma-ml.md` a tabela de fontes que ainda diz `SE/CO` (o código real é `SE`, já registrado no item 18 do mesmo doc): fica para um PR só de `docs/**`, se o usuário quiser.
- Marcar checkboxes do roadmap: "Ingestão do ONS + backfill" fecha no item 23.

## 3. Fase do roadmap

Fase 1 — "Banco e carga do ONS", item "Ingestão do ONS + backfill desde 2015 + checagens" (`docs/plataforma-ml.md`, "Roadmap"); a tabela é o que permite o "Pronto quando: ela consulta `raw.ons_daily_load` do notebook dela via Tailscale".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `tests/test_raw_ons_daily_load.py` | Novo (test-writer): estrutura, restrições, comentários, permissões (com `UPDATE` para o `ingestor`), `upsert` com `on_conflict="update"` e `downgrade` |
| `migrations/versions/0006_raw_ons_daily_load.py` | Novo (implementer): cria `raw.ons_daily_load` com restrições de nome fixo e comentários; `downgrade` apaga a tabela |

Nada mais muda. Testes existentes que fazem `downgrade` a partir do `head` (`tests/test_migrations.py` até `base`, `tests/test_permissions.py` até `0001`, `tests/test_ref_locations.py` até `0002`, `tests/test_raw_weather_forecast.py` até `0003`, `tests/test_ref_calendar.py` do PR 19 até `0004`) passam a reverter também a `0006` e continuam verdes sem edição, porque o `downgrade` da `0006` só apaga `raw.ons_daily_load`. `tests/test_migrations.py` compara com o `head` dinamicamente e exige ids de 4 dígitos e head único.

### Contrato e modelo de dados

`docs/plataforma-ml.md`, "Modelo de dados":

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `raw.ons_daily_load` | `subsystem`, `date`, `load_avg_mw`, `ingested_at` | (`subsystem`, `date`) | Plataforma | Todos |

`docs/plataforma-ml.md`, "Ingestão": "07:00 `ingest_ons_load` — Lê o parquet do ano corrente no S3 e faz upsert dos últimos 30 dias (cobre revisões do ONS)".

Fatos da fonte (`docs/plataforma-ml.md`, "Para verificar antes da Fase 1", verificado em 2026-11-08), que o PR 20 mapeia para esta tabela:

| Coluna no parquet do ONS | Tipo na fonte | Coluna aqui | Tipo aqui |
| --- | --- | --- | --- |
| `id_subsistema` | string; `N`, `NE`, `S`, `SE` (o Sudeste/Centro-Oeste é `SE`, não `SE/CO`) | `subsystem` | `text` |
| `din_instante` | `datetime64[ns]`, só a data | `date` | `date` |
| `val_cargaenergiamwmed` | `float64`, MWmed | `load_avg_mw` | `double precision` |
| (não existe) | | `ingested_at` | `timestamptz` |

O ONS reescreve o arquivo do ano de tempos em tempos e pode revisar dias já publicados (por isso a janela de 30 dias do PR 22); a profundidade das revisões ainda está pendente no item 18, mas não muda esta tabela.

ADR 0005, trechos que se aplicam:

> `ingested_at` guarda o momento da **última escrita** da linha, carimbado pelo relógio do servidor no insert e, nos upserts que atualizam, também no `SET` do conflito. Não há coluna nova (nenhum `updated_at`): a "primeira entrada" não é registrada.
>
> O ADR cobre as tabelas dos PRs 09 (`ref.locations`), 13 (`raw.weather_forecast`), 19 (`ref.calendar`), 21 (`raw.ons_daily_load`) e 25 (`raw.weather_observed`), no que toca a estas três decisões. Os demais tipos e colunas dessas tabelas estão nos planos e em `docs/plataforma-ml.md`.

O modo "primeiro snapshot vence" (`on_conflict="ignore"`) do ADR 0005 vale só para `raw.weather_forecast`. Esta tabela usa **`on_conflict="update"`** (D3).

`AGENTS.md`, "Fronteira": "Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados." Aqui: migração = `0006`; ADR = 0005 (seção 10); aviso = seção 9, "Aviso à ciência de dados", enviado pelo usuário.

`.claude/rules/migrations-e-dados.md`:

> - Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.
> - Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados. Mudança na assinatura do contrato exige ADR.
> - Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `scientist` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `reader` só lê. Toda tabela nova declara quem escreve e quem lê.
> - Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.

### Quem escreve e quem lê

Resultado dos privilégios padrão de `migrations/versions/0002_roles.py` (válidos para tabelas criadas pelo admin que roda as migrações, `DATABASE_URL_ADMIN`), **sem** exceção nesta tabela:

| Papel | `raw.ons_daily_load` |
| --- | --- |
| admin (`DATABASE_URL_ADMIN`) | dono |
| `ingestor` | `SELECT`, `INSERT`, `UPDATE` (sem `DELETE`, sem `TRUNCATE`); é quem roda o job do PR 22 com `on_conflict="update"` |
| `scientist`, `scorer`, `reader` | só `SELECT` |

Trecho de `0002_roles.py`:

```python
ROLES = ("ingestor", "scientist", "scorer", "reader")
INGESTOR_SCHEMAS = "raw, ref"
...
op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {ALL_ROLES}")
...
op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schemas} GRANT INSERT, UPDATE ON TABLES TO {role}")
# (raw, ref) -> ingestor ; (predictions, monitoring) -> scorer
```

`INSERT ... ON CONFLICT DO UPDATE` (`on_conflict="update"`) exige `INSERT` e `UPDATE`. Diferença deliberada em relação à `0004`, que faz `REVOKE UPDATE ON raw.weather_forecast FROM ingestor`: aqui **não** há `REVOKE`.

### Contrato do `upsert` (`ingestion/db.py`, não alterar)

```python
def upsert(
    conn: sqlalchemy.Connection,
    table: str,
    rows: pd.DataFrame,
    keys: list[str],
    *,
    on_conflict: Literal["update", "ignore"] = "update",
    stamp_ingested_at: bool = True,
) -> int:
    """Write ``rows`` into ``table`` ("schema.table") keyed by ``keys``.

    With ``on_conflict="update"`` existing rows are overwritten; with ``"ignore"`` they are
    kept untouched. When ``stamp_ingested_at`` is true, ``ingested_at`` is set to the server
    ``now()`` on insert and, in update mode, on conflict. Returns the number of rows inserted
    (plus updated, in update mode). The caller owns the transaction: nothing is committed here.
    """
```

Reflete a tabela, recusa coluna inexistente, recusa `ingested_at` no DataFrame quando carimba, converte `NaN`/`None` em `NULL`. O DataFrame do job (PR 20/22) tem só `subsystem`, `date`, `load_avg_mw`.

### Modelo de migração a seguir (`migrations/versions/0004_raw_weather_forecast.py`, resumo)

```python
"""raw_weather_forecast

Revision ID: 0004
Revises: 0003
Create Date: ...

Creates raw.weather_forecast: ... (ADR 0005).
Permissions come from the default privileges set by 0002; no explicit GRANT here.
...
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""CREATE TABLE raw.weather_forecast ( ... CONSTRAINT weather_forecast_pkey PRIMARY KEY (...), ... )""")
    op.execute("COMMENT ON TABLE raw.weather_forecast IS '...'")
    op.execute("COMMENT ON COLUMN raw.weather_forecast.ingested_at IS 'Server time of the last write of the row (ADR 0005).'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE raw.weather_forecast")
```

Regras de estilo: só `from alembic import op` (não importar `sqlalchemy`: `F401` no ruff); apagar o comentário `# Add "from alembic import op" ...` do template `migrations/script.py.mako`; SQL em `op.execute`; toda restrição com nome fixo; um `op.execute` por `COMMENT ON`; docstring e comentários em inglês (ADR 0001). `alembic revision` sem `--autogenerate` não precisa de banco; o arquivo sai `0006_raw_ons_daily_load.py` pelo template `%(rev)s_%(slug)s`. A restrição `CHECK` de subsistema segue `locations_subsystem_code` da `0003`: `CHECK (subsystem IN ('SE', 'S', 'NE', 'N'))`.

### Padrões de teste a seguir (`tests/test_raw_weather_forecast.py`, `tests/conftest.py`)

- Fixtures de `tests/conftest.py` (não alterar): `migrated_database` (sessão, em `head`, **só leitura**: `SELECT` e catálogo, inclusive `has_table_privilege`); `fresh_database` (por teste, vazio, apagado no teardown). `alembic_config()` é função, importada de `tests.conftest`. Todo teste que escreve, faz `upsert` ou `downgrade` usa um fixture próprio:

```python
@pytest.fixture
def load_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database
```

- Helpers do arquivo de referência a replicar (são locais ao módulo, não compartilhados): `_query(url, statement, role=None)`, `_execute(url, statement, params=None, role=None)` (com commit), `_insert_expecting_error(url, row, statement=INSERT, error_type=IntegrityError)`, `_assert_denied(url, role, statement, params=None)` (confere `42501`), `_table_exists(url)` via `to_regclass`, `_has_privilege(url, role, privilege, table=TABLE)` via `has_table_privilege`, `_upsert_as(url, role, frame, on_conflict)` (`SET ROLE` + `upsert` + commit). Todos usam `build_engine(url)` de `ingestion.db` e `engine.dispose()` no `finally`.
- `pytestmark = pytest.mark.db` no módulo.
- Erros: `error.orig.sqlstate` e `error.orig.diag.constraint_name`. SQLSTATEs: `42501` permissão, `23514` `CHECK`, `23502` `NOT NULL`, `23505` chave duplicada.
- `INSERT` direto nos testes passa `now()` para `ingested_at` (a coluna não tem `DEFAULT`). Sugestão: `INSERT = "INSERT INTO raw.ons_daily_load (subsystem, \"date\", load_avg_mw, ingested_at) VALUES (:subsystem, :date, :load_avg_mw, now())"`.
- Comentários lidos com `obj_description(to_regclass('raw.ons_daily_load'), 'pg_class')` e `col_description(...)`, como no caso 4 do arquivo de referência.

## 5. Passos

0. (implementer e test-writer, antes de tudo) Confirme que o PR 19 está na `main`: `git log --oneline -1 -- migrations/versions/0005_ref_calendar.py` mostra um commit e `uv run alembic heads` mostra `0005 (head)`. Se não, **parar**: esta migração depende da `0005` como `down_revision`.
1. (test-writer) Partindo da `main` atualizada, na branch `feat/raw-ons-load`, escreva `tests/test_raw_ons_daily_load.py` com os casos da seção 8, seguindo os padrões da seção 4. Rode `uv run pytest tests/test_raw_ons_daily_load.py` e confirme que falham porque `raw.ons_daily_load` não existe (`UndefinedTable` / `to_regclass` nulo) ou porque a revisão `0006` não existe. `uv run ruff check .` e `uv run ruff format --check .` limpos. Commit `test: add raw.ons_daily_load tests`.
2. (implementer) Partindo da branch com os testes: `uv run alembic revision -m "raw_ons_daily_load" --rev-id 0006`. Confira `down_revision = "0005"`. Ajuste os imports (só `from alembic import op`; apague o comentário do template). Docstring do módulo, em inglês: cria `raw.ons_daily_load` (daily load from ONS, one row per subsystem and day); permissions come from the default privileges set by 0002, no explicit GRANT or REVOKE; the ingestor keeps UPDATE on purpose because ONS revises published days and the job upserts with `on_conflict="update"` (ADR 0005: `ingested_at` is the last write).
3. `upgrade`, primeiro `op.execute`, a tabela, com estes nomes e tipos exatos (os testes conferem):

   ```sql
   CREATE TABLE raw.ons_daily_load (
       subsystem text NOT NULL
           CONSTRAINT ons_daily_load_subsystem_code CHECK (subsystem IN ('SE', 'S', 'NE', 'N')),
       "date" date NOT NULL,
       load_avg_mw double precision NOT NULL,
       ingested_at timestamptz NOT NULL,
       CONSTRAINT ons_daily_load_pkey PRIMARY KEY (subsystem, "date")
   )
   ```

4. `upgrade`, um `op.execute` por comentário (texto em inglês; o caso 4 confere trechos):
   - `COMMENT ON TABLE raw.ons_daily_load IS 'Daily energy load published by ONS (Carga de Energia Diaria), one row per subsystem and day. Rows are upserted: ONS revises published days and the latest published value overwrites the stored one (the ingestor role has UPDATE).'`
   - `COMMENT ON COLUMN raw.ons_daily_load.subsystem IS 'ONS subsystem code (id_subsistema): SE = Sudeste/Centro-Oeste, S = Sul, NE = Nordeste, N = Norte.'`
   - `COMMENT ON COLUMN raw.ons_daily_load."date" IS 'Calendar day as published by ONS (din_instante, date only).'`
   - `COMMENT ON COLUMN raw.ons_daily_load.load_avg_mw IS 'Average load over the day in MWmed (average MW), from ONS val_cargaenergiamwmed.'`
   - `COMMENT ON COLUMN raw.ons_daily_load.ingested_at IS 'Server time of the last write of the row (ADR 0005).'`
5. Não escreva `GRANT` nem `REVOKE` (D3).
6. `downgrade`: `op.execute("DROP TABLE raw.ons_daily_load")` (sem `CASCADE`).
7. Rode os critérios de pronto e cole comando e saída no PR. No corpo do PR, declare as decisões D1 a D10 da seção 9, em especial D3 (`ingestor` com `UPDATE`, `on_conflict="update"`, diferente da `0004`).
8. (usuário, depois que a `0006` estiver em produção, junto do aviso de fim da Fase 1 no item 23) Enviar à cientista o aviso da seção 9.

## 6. Critérios de pronto

Precisa do Postgres de teste: `docker compose -f infra/docker-compose.dev.yml up -d`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_raw_ons_daily_load.py tests/test_migrations.py tests/test_permissions.py tests/test_ref_locations.py tests/test_raw_weather_forecast.py tests/test_ref_calendar.py tests/test_upsert.py` | Todos passam, nenhum `skipped` |
| `uv run alembic heads` | `0006 (head)` |
| `uv run alembic history` | Primeira linha `0005 -> 0006 (head), raw_ons_daily_load` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| `git diff --name-only main...HEAD` | Só `tests/test_raw_ons_daily_load.py` e `migrations/versions/0006_raw_ons_daily_load.py` |
| `gh pr checks` | Verde (o CI roda `alembic upgrade head` e a suíte com Postgres) |

## 7. Testes necessários

`sim`: chave, restrição de subsistema, nulidade e permissões (o `ingestor` precisa de `UPDATE` para absorver revisões do ONS) são o contrato que a cientista consulta e que o job do PR 22 usa.

## 8. Casos de teste

Leitura e catálogo, no banco compartilhado em `head` (`migrated_database`):

1. Colunas pelo `information_schema.columns` (ordenadas por nome) exatamente: `date date NO`, `ingested_at timestamp with time zone NO`, `load_avg_mw double precision NO`, `subsystem text NO`.
2. A chave primária se chama `ons_daily_load_pkey` e é formada exatamente por `subsystem` e `date`.
3. A tabela nasce vazia (`count(*)` = 0).
4. Comentários: o da tabela não é nulo e contém `UPDATE`; o de `load_avg_mw` contém `MWmed`; o de `subsystem` contém `Sudeste/Centro-Oeste`; o de `ingested_at` contém `last write`.
5. Privilégios do `ingestor` em `raw.ons_daily_load` por `has_table_privilege`: `SELECT` = true, `INSERT` = true, `UPDATE` = true, `DELETE` = false, `TRUNCATE` = false.
6. `scientist`, `scorer`, `reader`: `SELECT` = true; `INSERT` = false; `UPDATE` = false.

Escrita, cada teste num banco novo em `head` (`load_database`), como admin salvo indicação. Linha de base: `subsystem = 'SE'`, `date = 2026-11-05`, `load_avg_mw = 40000.0`, `ingested_at = now()`.

7. Inserir a linha de base → aceita; relida com os mesmos valores.
8. Os quatro códigos `SE`, `S`, `NE`, `N` na mesma data → quatro linhas aceitas.
9. Mesmo `subsystem` em datas diferentes e mesma data em subsistemas diferentes → coexistem.
10. Mesma (`subsystem`, `date`) duas vezes sem `ON CONFLICT` → a segunda falha com `23505`.
11. `subsystem` igual a `SIN`, `SE/CO`, `se` (minúsculo) ou `''` → falha com `23514` na restrição `ons_daily_load_subsystem_code`.
12. `NULL` em `subsystem`, `date`, `load_avg_mw` ou `ingested_at` → falha com `23502`.
13. `load_avg_mw = 0.0` e `load_avg_mw = -1.0` → aceitos pelo banco (a faixa é da checagem pandera do PR 22, D4).
14. Como `ingestor`, `upsert(conn, "raw.ons_daily_load", df, keys=["subsystem", "date"], on_conflict="update")` com 2 linhas (`SE` e `S`, 2026-11-05, 40000.0 e 12000.0, sem `ingested_at`), seguido de commit → devolve 2; `ingested_at` não nulo nas duas.
15. Revisão do ONS: com as linhas do caso 14 gravadas, um segundo `upsert` como `ingestor`, `on_conflict="update"`, em outra transação, com `SE` 2026-11-05 = 40500.0 e `S` 2026-11-05 = 12000.0 → sem erro de permissão; `SE` passa a 40500.0, `S` continua 12000.0, total continua 2 linhas, e o `ingested_at` das duas linhas é estritamente maior que o da primeira escrita (ADR 0005: última escrita).
16. Mesmo `upsert` do caso 14 repetido idêntico → continua com 2 linhas e os mesmos valores de `load_avg_mw` (idempotente).
17. Como `ingestor`: `INSERT` da linha de base funciona; `UPDATE raw.ons_daily_load SET load_avg_mw = 41000.0` funciona; `DELETE FROM raw.ons_daily_load` e `TRUNCATE raw.ons_daily_load` falham com `42501` e a linha continua.
18. Como `scientist`, `scorer` e `reader`: `SELECT count(*)` devolve 1 depois que o admin inseriu a linha de base; `INSERT` de outra linha e `UPDATE` da existente falham com `42501`.
19. `downgrade` até `0005`: antes, `raw.ons_daily_load` existe; depois, não existe, e `ref.calendar`, `ref.locations` (4 linhas) e `raw.weather_forecast` continuam; um novo `upgrade head` recria a tabela vazia, com `UPDATE` para o `ingestor` (`has_table_privilege`).

Já existentes que continuam verdes sem edição: `tests/test_migrations.py`, `tests/test_permissions.py`, `tests/test_ref_locations.py`, `tests/test_raw_weather_forecast.py` (inclusive o caso 7, `UPDATE` do `ingestor` em `ref.locations`), `tests/test_ref_calendar.py` (PR 19) e `tests/test_upsert.py`.

## 9. Riscos e perguntas em aberto

Nenhuma pergunta em aberto bloqueia. Decisões (adotadas pelas recomendações, com autorização do usuário):

- **D1. Sem chave estrangeira de `date` para `ref.calendar`.** O modelo de dados não a prevê; `ref.calendar` é preenchida por job (não por migração, D5 do plano 19) e cobre só 2015–2030, então a FK faria a ingestão do ONS falhar se o calendário não estivesse carregado ou fora da faixa, acoplando dois jobs independentes; `raw` guarda a fonte como publicada. A cientista faz o `JOIN` por `date`. A dependência do PR 19 é **só a ordem das migrações** (`0006` depois de `0005`).
- **D2. Sem chave estrangeira de `subsystem`; `CHECK` com os 4 códigos.** `ref.locations.subsystem` não é chave (pode haver mais de uma cidade por subsistema), e não existe `ref.subsystems`. O `CHECK` `ons_daily_load_subsystem_code` usa a mesma lista de `locations_subsystem_code` (`0003`) e os códigos reais do ONS (`SE`, não `SE/CO`). Um total `SIN` é descartado antes, no PR 20, e recusado aqui.
- **D3. O `ingestor` mantém `UPDATE` e o job usa `on_conflict="update"`.** O ONS revisa dias já publicados e reescreve o arquivo do ano (item 18); a janela de 30 dias do PR 22 existe para absorver isso, o que exige sobrescrever. Logo **não** há `REVOKE UPDATE` (diferente da `0004`, onde "o primeiro snapshot vence"). `DELETE` e `TRUNCATE` continuam negados pelos privilégios padrão. Não há exceção ao modelo de papéis da `0002`.
- **D4. `load_avg_mw NOT NULL`, sem `CHECK` de faixa.** Dia sem valor não tem linha. A faixa plausível (carga > 0) fica na checagem pandera do PR 22, que roda depois de gravar, para o job gravar e acusar (regra "checagem falha = execução falha"), em vez de a transação ser recusada sem diagnóstico. Um `NaN` vira `NULL` no `upsert` e é recusado pelo `NOT NULL`.
- **D5. `date` é o dia como o ONS publica** (`din_instante`, só data). Não há decisão de fuso nesta tabela; fica documentado no comentário da coluna. O nome `date` vem do modelo de dados e vai entre aspas no DDL por clareza.
- **D6. `ingested_at timestamptz NOT NULL`, sem `DEFAULT`**, carimbado pelo `upsert` no insert e no `SET` do conflito: é a "última escrita" do ADR 0005. Uma revisão do ONS atualiza `ingested_at`; a data da primeira entrada não é registrada (ADR 0005, aceito).
- **D7. Restrições com nome fixo** (`ons_daily_load_pkey`, `ons_daily_load_subsystem_code`) e prefixo da tabela, como `weather_forecast_*` na `0004`; os testes conferem o nome.
- **D8. Unidade e significado nos comentários** (MWmed, códigos de subsistema, origem das colunas do ONS), para a cientista ler no catálogo. Texto em inglês (ADR 0001).
- **D9. Revisão `0006`, `down_revision = "0005"`.** O PR 19 fica com a `0005`; se ao começar a `main` não tiver a `0005`, o passo 0 para.
- **D10. Testes num arquivo só** (`tests/test_raw_ons_daily_load.py`), como `tests/test_raw_weather_forecast.py`: não há lógica de Python neste PR.

Riscos:

- **Linha que o ONS apaga.** Se o ONS remover um dia já publicado, o `upsert` não apaga a linha (o `ingestor` não tem `DELETE`). Não há indício disso no item 18; a correção seria manual pelo admin. Registrar no PR, não tratar aqui.
- **Profundidade das revisões ainda pendente (item 18, parte b).** Não muda o schema; afeta só a janela do PR 22.
- **`downgrade` em produção apaga o histórico.** Depois do backfill (item 23), o histórico pode ser recarregado do S3, então o risco é menor que o de `raw.weather_forecast`, mas `alembic downgrade` abaixo de `0006` não deve rodar em produção sem combinar.
- **Ordem de merge.** Se o PR 19 mudar de número de revisão ou atrasar, este PR espera; não renumerar para `0005`.
- **Privilégios padrão dependem do admin.** As migrações rodam com o mesmo admin (`DATABASE_URL_ADMIN`); na VPS, pelo procedimento interino do ADR 0004 (`docker compose -f infra/docker-compose.yml run --rm jobs alembic upgrade head`).
- **Postgres de teste.** Sem o container de `infra/docker-compose.dev.yml`, os testes `db` falham (não pulam), por desenho de `tests/conftest.py`.

### Aviso à ciência de dados

A regra exige aviso para mudança em `raw`. Quem envia é o usuário (passo 8), junto do aviso de fim da Fase 1 (item 23). Conteúdo mínimo:

- Existe `raw.ons_daily_load` (`subsystem`, `date`, `load_avg_mw`, `ingested_at`), chave (`subsystem`, `date`), uma linha por subsistema por dia, com histórico desde 2015 depois do backfill (item 23).
- `subsystem` usa os códigos do ONS: `SE` (Sudeste/Centro-Oeste), `S`, `NE`, `N`. Não há total `SIN`: somar os quatro, se precisar. Para cruzar com clima, `ref.locations.subsystem` usa os mesmos códigos.
- `load_avg_mw` é a carga média do dia em MWmed (`val_cargaenergiamwmed` do ONS). `date` é o dia como o ONS publica; para feriados e dia da semana, `JOIN` com `ref.calendar` por `date`.
- O ONS revisa dias já publicados: o job reescreve os últimos 30 dias toda manhã, então valores recentes podem mudar. `ingested_at` é o momento da última escrita da linha, não da primeira. Para reprodutibilidade, congele o recorte em `features` ou registre a data da extração.
- Dias recentes chegam com atraso (D−3 numa medição de fim de semana; atraso exato em verificação, item 18).
- `scientist` só lê esta tabela.

## 10. Decisões que exigem ADR

- **Nenhum ADR novo.** A exigência do `AGENTS.md` (migração + ADR + aviso para mudança em `raw`) é cumprida por: migração `0006`; ADR 0005 (mergeado), que lista explicitamente o PR 21 (`raw.ons_daily_load`) e fixa `ingested_at` como última escrita, a semântica que esta tabela usa no modo `update`, delegando "os demais tipos e colunas" aos planos e a `docs/plataforma-ml.md`; e o aviso da seção 9.
- **D3 (`UPDATE` mantido) não exige ADR:** é o padrão da `0002` para `raw`, sem exceção, e o modo `update` é o padrão do `upsert` (PR 08).
- **Contrato das funções** (`build_features`, `predict`, `evaluate`): não muda. **Rede/portas:** nada exposto (ADR 0003). **Dependências:** nenhuma.
- Exigiriam ADR no futuro (novo ou emenda ao 0005), com migração e aviso: nova coluna (por exemplo `first_ingested_at`, `nom_subsistema`, total `SIN`), mudar a chave, mudar a unidade de `load_avg_mw` ou passar a guardar revisões como versões em vez de sobrescrever.
