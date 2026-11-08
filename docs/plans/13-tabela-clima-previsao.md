# 13 — Tabela `raw.weather_forecast`

> Executa: agente. Depende de: 09 (na `main` em `5ef914c`, #21). Branch sugerida: `feat/raw-weather-forecast`.
> Pré-requisito: ADR 0005 (`docs/adr/0005-data-contract-v1.md`), mergeado em `a22c0df` e atualizado em `4423db1` (#23). Nenhum ADR novo bloqueia este PR (seção 10).
> **Antecipado**: item da Fase 2 feito antes do fim da Fase 1, porque cada dia sem coleta é histórico perdido (desvio de "uma fase por vez" aprovado pelo usuário em 2026-11-07, P5).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-08: alinhado à `main` em `4423db1` (migrações `0001` a `0003`, head `0003`; fixtures de `tests/conftest.py`; padrões de escrita de `tests/test_ref_locations.py` e `tests/test_permissions.py`; contrato do `upsert` em `ingestion/db.py`; ADR 0005; privilégios da `0002`). Fecha os pontos em aberto do ADR 0005 que têm recomendação (faixa do `CHECK` de `horizon_days` e fuso de `issued_at`, seção 9, D1 a D3).
> Decisões do usuário em 2026-11-08: (Q1) **não** guardar o horizonte 0; o `CHECK` fica 1 a 7 e o ADR 0005 fica como está, sem ADR novo (D2). (Q2) **sim**, a `0004` faz `REVOKE UPDATE ON raw.weather_forecast FROM ingestor`, exceção documentada ao modelo de papéis da `0002` (D5). Não há perguntas abertas.

## 1. Objetivo

Criar por migração Alembic (`0004`) a tabela `raw.weather_forecast` de snapshots diários de previsão do tempo, um registro por local, dia de emissão e data-alvo, com `horizon_days` gerado e restrito a 1 a 7, e sem `UPDATE` para o `ingestor`.
É a tabela mais urgente da plataforma: o histórico dela só começa no dia em que a coleta ligar (item 17).

## 2. Fora do escopo

- Cliente HTTP do Open-Meteo (PR 14), job `weather-forecast` e checagem pandera (PR 15), agendamento (PR 16), ligar a coleta (item 17).
- `raw.weather_observed` (PR 25).
- Backfill de previsões passadas (o doc exclui; ver P10 no índice).
- Guardar o horizonte 0 ou horizontes acima de 7 (ADR 0005 decide 1 a 7; decisão do usuário confirmada em D2).
- `CHECK` de faixa nas variáveis de clima (temperatura, chuva, vento, umidade): é a checagem pandera do PR 15 que decide o que é plausível, e as variáveis aceitam nulo.
- `DEFAULT now()` em `ingested_at`: quem carimba é o `upsert` (`stamp_ingested_at=True`), e a falta do carimbo deve falhar alto (`NOT NULL`).
- Índices além da chave primária (a tabela cresce 28 linhas por dia).
- `GRANT` explícitos e qualquer `REVOKE` além do `REVOKE UPDATE ... FROM ingestor` desta tabela (D5). As demais permissões vêm dos privilégios padrão da `0002`.
- Mudar o modelo de papéis em geral: não alterar `migrations/versions/0002_roles.py` nem os privilégios padrão de `raw`; a exceção vale só para `raw.weather_forecast`.
- Alterar `ingestion/db.py`, `tests/conftest.py`, `tests/test_migrations.py`, `tests/test_permissions.py`, `tests/test_ref_locations.py`, `tests/test_upsert.py`, `migrations/env.py`, `alembic.ini`, `.github/workflows/ci.yml`, `pyproject.toml` ou `.claude/rules/migrations-e-dados.md`. Nenhuma dependência nova (sem passo 0).
- Editar os planos 14 e 15, o índice `docs/plans/00-indice.md` ou o ADR 0005 (emenda opcional, seção 10).
- Marcar o checkbox "`raw.weather_forecast` coletando todo dia" em `docs/plataforma-ml.md` (só fecha no item 17).

## 3. Fase do roadmap

Fase 2 — Clima, item "`raw.weather_forecast` coletando todo dia (prioridade)" (`docs/plataforma-ml.md`, seção "Roadmap"), antecipado pela P5.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `tests/test_raw_weather_forecast.py` | Novo: testes da estrutura, das restrições, do `upsert` com `on_conflict="ignore"`, das permissões (incluindo o `ingestor` sem `UPDATE`) e do `downgrade` (test-writer) |
| `migrations/versions/0004_raw_weather_forecast.py` | Novo: cria `raw.weather_forecast` com comentários e tira o `UPDATE` do `ingestor` nela; `downgrade` apaga a tabela (implementer) |

Nada mais muda. `tests/test_migrations.py` compara a revisão com o head dinamicamente e exige ids de 4 dígitos e head único; `tests/test_ref_locations.py` (caso 12, `downgrade` até `0002`) e `tests/test_permissions.py` (caso 11, `downgrade` até `0001`) partem de `head` e passam a reverter a `0004` antes, sem edição.

### Contrato e modelo de dados

`docs/plataforma-ml.md`, "Modelo de dados":

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `raw.weather_forecast` | `location_id`, `issued_at`, `target_date`, `horizon_days`, mesmas variáveis (de `raw.weather_observed`: `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`), `ingested_at` | (`location_id`, `issued_at`, `target_date`) | Plataforma | Todos |

`docs/plataforma-ml.md`, "Ingestão": `06:30 ingest_weather_forecast` — "Snapshot da previsão para os próximos 7 dias, um registro por local e data-alvo, com `issued_at` = hoje". Por que existe: "O modelo de carga só pode usar, no dia D, a previsão disponível em D — usar o clima observado de D+1 seria vazamento de dados."

ADR 0005 (`docs/adr/0005-data-contract-v1.md`), trechos que este PR materializa:

> Em `raw.weather_forecast`, `issued_at` é do tipo `date`: o dia em que o snapshot da previsão foi tirado, não um instante. Há no máximo um snapshot por local e data-alvo por dia: a chave primária é (`location_id`, `issued_at`, `target_date`), e quando o job roda de novo no mesmo dia **o primeiro snapshot vence** (insert que ignora o conflito, nunca sobrescreve). Previsão é guardada como emitida; um snapshot antigo nunca é reescrito.
>
> `horizon_days` é a distância em dias entre `target_date` e `issued_at`, e o job grava os horizontes de **1 a 7**.
>
> `ingested_at` guarda o momento da **última escrita** da linha [...]. Nas tabelas com insert que ignora o conflito (como `raw.weather_forecast`), a linha preserva o `ingested_at` da primeira e única escrita.
>
> `location_id` [...] é a chave de `ref.locations` e a chave estrangeira em `raw.weather_observed` e `raw.weather_forecast` [...].
>
> - A faixa de horizontes 1 a 7 não guarda o horizonte 0 [...]. O plano do PR 13 propõe hoje `check (horizon_days between 0 and 16)`; o PR 13 deve alinhar a restrição a esta decisão ou registrar por que ela é mais larga. O ponto fica em aberto aqui.
> - Em aberto: guardar o horizonte 0, que o usuário recomendou avaliar com a cientista (P8). Se for incluído, muda `expected_rows` e a faixa de `horizon_days` (PRs 13, 14 e 15) e exige novo ADR ou emenda a este.
> - Em aberto: o fuso que define "o dia" de `issued_at`. O plano do PR 13 propõe `America/Sao_Paulo`; confirmar no PR 13.
> - [...] `ref.locations` não tem coluna `timezone`: o dia dos dados de clima é `America/Sao_Paulo`, definido pelos jobs.

Os três "Em aberto" acima ficam resolvidos por este plano: faixa 1 a 7 (D1), sem horizonte 0 (D2, decisão do usuário) e fuso `America/Sao_Paulo` (D3). O ADR 0005 não é alterado neste PR.

`.claude/rules/migrations-e-dados.md`:

> - Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.
> - Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados.
> - Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `scientist` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `reader` só lê. Toda tabela nova declara quem escreve e quem lê.
> - `raw.weather_forecast` guarda a previsão como emitida (`issued_at`). Nunca sobrescrever uma previsão antiga com uma nova.

O `REVOKE UPDATE` (D5) é a forma de o banco impor a última regra acima. O `ingestor` continua sendo quem escreve a tabela (por `INSERT`), então "`ingestor` escreve `raw`" segue valendo; a exceção é só a falta de `UPDATE`, documentada na docstring da migração e no comentário da tabela.

Como os planos seguintes usam a tabela (não implementar aqui; só para coerência):

- PR 14 (`docs/plans/14-cliente-previsao-open-meteo.md`): `fetch_forecast` pede `timezone=America/Sao_Paulo` e `forecast_days=8`, valida que o primeiro dia da resposta é `issued_at` e devolve só `target_date` de `issued_at + 1` a `issued_at + 7`, com as colunas `location_id, issued_at, target_date, temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean` (sem `horizon_days` e sem `ingested_at`).
- PR 15 (`docs/plans/15-job-clima-previsao.md`): `upsert(conn, "raw.weather_forecast", df, keys=["location_id", "issued_at", "target_date"], on_conflict="ignore")`; depois relê `issued_at = today` e checa `horizon_days` entre 1 e 7 e `expected_rows = len(locations) * 7`; `today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()`. A imagem dos jobs tem `TZ=America/Sao_Paulo` (plano 11). Com D5, se o job usasse por engano `on_conflict="update"`, falharia com `42501` em vez de sobrescrever em silêncio.

### Quem escreve e quem lê

Resultado dos privilégios padrão de `migrations/versions/0002_roles.py`, válidos para tabelas criadas pelo admin que roda as migrações (`DATABASE_URL_ADMIN`), mais o `REVOKE UPDATE` da `0004` (D5):

| Papel | `raw.weather_forecast` |
| --- | --- |
| admin (`DATABASE_URL_ADMIN`) | dono; cria, insere, altera, apaga (é quem corrige um snapshot, se um dia for preciso) |
| `ingestor` | `SELECT`, `INSERT` (sem `UPDATE`, por D5; sem `DELETE`, sem `TRUNCATE`) |
| `scientist`, `scorer`, `reader` | só `SELECT` |

Trecho relevante de `0002_roles.py`:

```python
SCHEMAS = ("raw", "ref", "features", "predictions", "monitoring")
INGESTOR_SCHEMAS = "raw, ref"
...
op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {ALL_ROLES}")
...
op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schemas} GRANT INSERT, UPDATE ON TABLES TO {role}")
# (raw, ref) -> ingestor ; (predictions, monitoring) -> scorer
op.execute("GRANT CREATE ON SCHEMA features TO scientist")
```

Os privilégios padrão dão ao `ingestor` `INSERT, UPDATE` na tabela no momento do `CREATE TABLE`; o `REVOKE UPDATE ON raw.weather_forecast FROM ingestor` logo depois retira só o `UPDATE`, só nesta tabela. Os privilégios padrão do schema `raw` não mudam: tabelas futuras de `raw` (ex.: `raw.weather_observed`, PR 25) continuam nascendo com `UPDATE` para o `ingestor`. `INSERT ... ON CONFLICT DO NOTHING` (`on_conflict="ignore"`) só exige `INSERT`; `INSERT ... ON CONFLICT DO UPDATE` (`on_conflict="update"`) exige `UPDATE` e passa a falhar com `42501`.

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

Ele reflete a tabela (`sqlalchemy.Table(..., autoload_with=conn)`), recusa coluna do DataFrame que não exista na tabela e recusa `ingested_at` no DataFrame quando carimba. O DataFrame do job não traz `horizon_days`: a coluna gerada fica fora do `INSERT`. O caso 17 da seção 8 prova que o `upsert` funciona com a tabela real (coluna gerada incluída), como `ingestor` sem `UPDATE`, e que o primeiro snapshot vence; o caso 18 prova que o modo `"update"` é recusado pelo banco.

### Padrões existentes a seguir

- Migrações existentes (`0001_schemas.py`, `0002_roles.py`, `0003_ref_locations.py`) usam só `op.execute` com SQL e `from alembic import op`. Seguir o mesmo estilo e dar nome fixo a toda restrição (os testes conferem o nome), como `0003`:

```python
op.execute(
    """
    CREATE TABLE ref.locations (
        location_id text PRIMARY KEY
            CONSTRAINT locations_location_id_slug
            CHECK (location_id ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'),
        ...
    )
    """
)
```

- O template `migrations/script.py.mako` não importa `op` nem `sa` e deixa o comentário `# Add "from alembic import op" (and "import sqlalchemy as sa" if needed) ...`. Na revisão gerada: adicionar `from alembic import op` logo após `from collections.abc import Sequence`, **não** importar `sqlalchemy` (import não usado falha no ruff `F401`) e apagar o comentário do template, como em `0003_ref_locations.py`.
- `alembic revision` sem `--autogenerate` não precisa de banco (`revision_environment` desligado em `alembic.ini`). O nome do arquivo sai `0004_raw_weather_forecast.py` pelo template `%(rev)s_%(slug)s`.
- Comentários SQL (`COMMENT ON`) e a docstring da migração são artefato de implementação: em inglês (ADR 0001).

Fixtures de `tests/conftest.py` (não alterar):

- `migrated_database` (sessão): banco em `head`, **compartilhado e só leitura**. Usar só para `SELECT` e consultas de catálogo (incluindo `has_table_privilege`).
- `fresh_database` (por teste): banco vazio, apagado no teardown. Todo teste que escreve (`INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `upsert`, `downgrade`) usa um fixture próprio sobre ele, como `locations_database` em `tests/test_ref_locations.py`:

```python
@pytest.fixture
def locations_database(fresh_database, monkeypatch) -> Iterator[str]:
    """Fresh database migrated to ``head``, safe to write to."""
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database
```

- `alembic_config()` é função (não fixture), importada de `tests.conftest`.
- Para agir como papel: `SET ROLE <papel>` na mesma conexão, como `_execute` (com `role=`) e `_assert_denied` em `tests/test_ref_locations.py` e `_execute_as` em `tests/test_permissions.py`. Erros chegam como exceções do SQLAlchemy (`IntegrityError`, `ProgrammingError`; para o erro de coluna gerada, capturar `sqlalchemy.exc.DBAPIError`, base comum, e conferir o SQLSTATE) com `error.orig.sqlstate`; o nome da restrição fica em `error.orig.diag.constraint_name`.
- SQLSTATEs: `42501` permissão negada, `23514` `CHECK`, `23502` `NOT NULL`, `23505` chave duplicada, `23503` chave estrangeira, `428C9` valor em coluna `GENERATED ALWAYS`.
- Marcar o módulo com `pytestmark = pytest.mark.db` (como em `tests/test_ref_locations.py` e `tests/test_upsert.py`).
- `ingested_at` nos `INSERT` diretos dos testes: passar `now()` no SQL (a coluna não tem `DEFAULT`).

## 5. Passos

1. (test-writer) Partindo da `main`, na branch `feat/raw-weather-forecast`, escreva `tests/test_raw_weather_forecast.py` com os casos da seção 8, seguindo os padrões da seção 4 (leituras e catálogo em `migrated_database`; escritas, `upsert` e `downgrade` num fixture próprio sobre `fresh_database` + `upgrade head`). Rode `uv run pytest tests/test_raw_weather_forecast.py` e confirme que falham porque `raw.weather_forecast` não existe (`UndefinedTable` / `to_regclass` nulo) ou porque a revisão `0004` não existe. Rode `uv run ruff check .` e `uv run ruff format --check .`. Commit `test: add raw.weather_forecast tests`.
2. (implementer) Partindo da branch com os testes: `uv run alembic revision -m "raw_weather_forecast" --rev-id 0004`. Confira `down_revision = "0003"`. Ajuste os imports (só `from alembic import op`; apague o comentário do template). Docstring do módulo, em inglês: diz que a migração cria `raw.weather_forecast` (snapshots diários de previsão, ADR 0005), que as permissões vêm dos privilégios padrão da `0002` e que, como exceção a eles, o `UPDATE` do `ingestor` é revogado nesta tabela para o banco impor "o primeiro snapshot vence" (o `ingestor` só insere com `on_conflict="ignore"`; correções ficam com o admin).
3. `upgrade`, primeiro `op.execute`, a tabela, com estes nomes e tipos exatos:
   - `location_id text NOT NULL`
   - `issued_at date NOT NULL`
   - `target_date date NOT NULL`
   - `horizon_days smallint NOT NULL GENERATED ALWAYS AS ((target_date - issued_at)::smallint) STORED` (`date - date` devolve `integer`; o cast explícito evita depender de conversão implícita)
   - `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`: `double precision`, aceitam nulo
   - `ingested_at timestamptz NOT NULL` (sem `DEFAULT`)
   - `CONSTRAINT weather_forecast_pkey PRIMARY KEY (location_id, issued_at, target_date)`
   - `CONSTRAINT weather_forecast_location_id_fkey FOREIGN KEY (location_id) REFERENCES ref.locations (location_id)` (sem `ON DELETE`/`ON UPDATE`: o padrão `NO ACTION` impede apagar uma cidade com histórico)
   - `CONSTRAINT weather_forecast_horizon_days_range CHECK ((target_date - issued_at) BETWEEN 1 AND 7)` (decisão D1; a restrição usa a expressão, não a coluna gerada, para não depender da ordem de cálculo)
4. `upgrade`, logo após o `CREATE TABLE`: `op.execute("REVOKE UPDATE ON raw.weather_forecast FROM ingestor")` (D5). Não revogar nada mais e não tocar nos privilégios padrão.
5. `upgrade`, um `op.execute` por comentário (texto em inglês; o caso 4 confere o fuso e a exceção):
   - `COMMENT ON TABLE raw.weather_forecast IS 'Daily weather forecast snapshots, stored as issued. One row per location, issue date and target date; the first snapshot of the day wins and is never overwritten (ADR 0005). The ingestor role has no UPDATE on this table.'`
   - `COMMENT ON COLUMN raw.weather_forecast.issued_at IS 'Calendar day in America/Sao_Paulo on which the snapshot was taken.'`
   - `COMMENT ON COLUMN raw.weather_forecast.horizon_days IS 'Generated: target_date - issued_at, from 1 to 7.'`
   - `COMMENT ON COLUMN raw.weather_forecast.ingested_at IS 'Server time of the last write of the row (ADR 0005).'`
6. `downgrade`: `op.execute("DROP TABLE raw.weather_forecast")` (sem `CASCADE`). Não precisa reverter o `REVOKE`: os privilégios somem com a tabela. `ref.locations` e o schema `raw` continuam.
7. Rode os critérios de pronto e cole comando e saída no PR. No corpo do PR, declare as decisões D1 a D5 da seção 9 (incluindo a exceção ao modelo de papéis da `0002`) e o risco do `downgrade` em produção.
8. (usuário, depois que a `0004` estiver em produção, antes ou junto do item 17) Enviar à cientista o aviso da seção 9, "Aviso à ciência de dados".

## 6. Critérios de pronto

Precisa do Postgres de teste: `docker compose -f infra/docker-compose.dev.yml up -d` (mensagem de `tests/conftest.py`).

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_raw_weather_forecast.py tests/test_migrations.py tests/test_permissions.py tests/test_ref_locations.py tests/test_upsert.py` | Todos passam, nenhum `skipped` |
| `uv run alembic heads` | `0004 (head)` |
| `uv run alembic history` | `0003 -> 0004 (head), raw_weather_forecast` na primeira linha |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| `git diff --name-only main...HEAD` | Só `tests/test_raw_weather_forecast.py` e `migrations/versions/0004_raw_weather_forecast.py` |
| `gh pr checks` | Verde (o CI roda `alembic upgrade head` e a suíte com Postgres 16) |

## 7. Testes necessários

`sim`: chave, chave estrangeira, coluna gerada, faixa de horizontes e permissões (incluindo o `ingestor` sem `UPDATE`) definem o contrato que a cientista vai consultar; erro aqui é caro de corrigir depois que o histórico começa.

## 8. Casos de teste

Leitura e catálogo, no banco compartilhado em `head`:

1. As colunas de `raw.weather_forecast`, pelo `information_schema.columns` (ordenadas por nome), são exatamente: `humidity_mean double precision YES`, `horizon_days smallint NO`, `ingested_at timestamp with time zone NO`, `issued_at date NO`, `location_id text NO`, `precip_mm double precision YES`, `target_date date NO`, `temp_max double precision YES`, `temp_min double precision YES`, `wind_speed_max double precision YES`.
2. `horizon_days` tem `is_generated = 'ALWAYS'`; as demais colunas, `NEVER`.
3. A chave primária, de nome `weather_forecast_pkey`, é formada exatamente por `location_id`, `issued_at` e `target_date`.
4. O comentário da coluna `issued_at` (`col_description`) contém `America/Sao_Paulo`; o comentário da tabela (`obj_description`) não é nulo e contém `UPDATE`.
5. A tabela nasce vazia (`count(*)` = 0).
6. Privilégios do `ingestor` em `raw.weather_forecast` por `has_table_privilege`: `SELECT` = true, `INSERT` = true, `UPDATE` = false, `DELETE` = false, `TRUNCATE` = false.
7. A exceção é só desta tabela: `has_table_privilege('ingestor', 'ref.locations', 'UPDATE')` continua true.

Escrita, cada teste num banco novo em `head`, como admin salvo indicação. Linha válida de base: `location_id = 'sao_paulo'`, `issued_at = 2026-11-07`, `target_date = 2026-11-10`, `temp_max = 31.5`, `temp_min = 19.0`, `precip_mm = 2.4`, `wind_speed_max = 18.0`, `humidity_mean = 72.0`, `ingested_at = now()`.

8. Inserir a linha de base → `horizon_days` lido de volta = 3.
9. Inserir com `target_date` = `issued_at + 1` e outra com `issued_at + 7` → ambas aceitas, `horizon_days` = 1 e 7.
10. Inserir com `target_date` = `issued_at` (horizonte 0), `issued_at - 1` (horizonte −1) ou `issued_at + 8` (horizonte 8) → falha com `23514` na restrição `weather_forecast_horizon_days_range`.
11. Inserir a mesma chave duas vezes (sem `ON CONFLICT`) → a segunda falha com `23505`.
12. Mesmo `location_id` e `target_date` com `issued_at` diferentes (`2026-11-07` e `2026-11-08`, alvo `2026-11-10`) → duas linhas coexistem, com `horizon_days` 3 e 2.
13. `location_id = 'does_not_exist'` → falha com `23503` na restrição `weather_forecast_location_id_fkey`.
14. Informar `horizon_days` explicitamente no `INSERT` (valor 3, coerente com as datas) → falha com SQLSTATE `428C9`.
15. `NULL` em `location_id`, `issued_at`, `target_date` ou `ingested_at` → falha com `23502`.
16. As cinco variáveis de clima `NULL` (resto da linha válido) → aceita.
17. Como `ingestor`, `upsert(conn, "raw.weather_forecast", df, keys=["location_id", "issued_at", "target_date"], on_conflict="ignore")` com 2 linhas (`sao_paulo`, emitida `2026-11-07`, alvos `2026-11-08` e `2026-11-09`, sem `horizon_days` e sem `ingested_at`), seguido de commit → devolve 2, sem erro de permissão; as linhas têm `horizon_days` 1 e 2 e `ingested_at` não nulo. Um segundo `upsert` igual, ainda como `ingestor` e com `on_conflict="ignore"`, com `temp_max` diferente, em outra transação → devolve 0, sem erro; `temp_max` e `ingested_at` das duas linhas continuam os da primeira escrita (o primeiro snapshot vence).
18. Com as linhas do caso 17 gravadas, como `ingestor`, `upsert(..., keys=["location_id", "issued_at", "target_date"], on_conflict="update")` com uma das chaves existentes e `temp_max` diferente → falha com `42501`; relida como admin, a linha mantém `temp_max` e `ingested_at` da primeira escrita.
19. Como `ingestor`: `INSERT` da linha de base funciona; `UPDATE raw.weather_forecast SET temp_max = 30.0` dessa linha falha com `42501` e a linha mantém `temp_max = 31.5`; `DELETE` e `TRUNCATE raw.weather_forecast` falham com `42501`.
20. Como admin, `UPDATE ... SET temp_max = 30.0` da linha de base funciona (o admin continua podendo corrigir).
21. Como `scientist`, `scorer` e `reader`: `SELECT count(*)` funciona (devolve 1 depois que o admin inseriu a linha de base); `INSERT` de outra linha e `UPDATE` da existente falham com `42501`.
22. `downgrade` até `0003`: antes, `raw.weather_forecast` existe; depois, não existe, e `ref.locations` continua com 4 linhas; um novo `upgrade head` recria a tabela vazia, e nela o `ingestor` de novo tem `INSERT` e não tem `UPDATE` (`has_table_privilege`).

Já existentes, que precisam continuar verdes sem edição: `tests/test_migrations.py` (ida e volta até `base`, `upgrade head` duas vezes, ids de 4 dígitos e head único), `tests/test_permissions.py` (inclui `downgrade` até `0001` a partir do `head`), `tests/test_ref_locations.py` (inclui `downgrade` até `0002` a partir do `head`) e `tests/test_upsert.py`.

## 9. Riscos e perguntas em aberto

Não há perguntas abertas: Q1 e Q2 foram decididas pelo usuário em 2026-11-08 (D2 e D5).

### Decisões tomadas neste plano (o coordenador declara no corpo do PR)

- **D1. Faixa do `CHECK` de `horizon_days`: 1 a 7** (antes 0 a 16). Segue a decisão do ADR 0005 ("o job grava os horizontes de 1 a 7"), que pede ao PR 13 alinhar a restrição ou justificar uma faixa mais larga. Não há justificativa para a mais larga: o banco passa a recusar o que o contrato não prevê, e o PR 14 já recorta 1 a 7. Consequência: guardar o horizonte 0 ou ir além de 7 exige migração nova (`0005` ou seguinte) que troque a restrição, junto com a emenda ao ADR que essa mudança já exigiria de qualquer forma.
- **D2. Horizonte 0 não é guardado** (decisão do usuário, 2026-11-08). O `CHECK` fica 1 a 7 e o ADR 0005 fica como está, sem ADR novo nem emenda. Os planos 14 e 15 não mudam. Consequência aceita: como a previsão não tem backfill, se um dia o horizonte 0 for incluído, o histórico dele só começa a partir dessa mudança.
- **D3. "O dia" de `issued_at` é o de `America/Sao_Paulo`.** Recomendação do ADR 0005 e do plano anterior, coerente com o PR 09 (sem coluna `timezone`, "o dia dos dados de clima é `America/Sao_Paulo`, definido pelos jobs"), com o PR 14 (`timezone=America/Sao_Paulo`) e com o PR 15 (`today` em `ZoneInfo("America/Sao_Paulo")`, imagem com `TZ=America/Sao_Paulo`). O banco não consegue impor fuso numa coluna `date`; a decisão fica registrada no comentário da coluna (passo 5, caso 4). As 4 capitais estão em UTC-3 sem horário de verão; uma cidade em outro fuso teria "o dia" deslocado (limitação já registrada no PR 09).
- **D4. Coluna gerada** para `horizon_days` (`GENERATED ALWAYS ... STORED`): nunca fica inconsistente com as datas e o job não a envia. Tipo `smallint`, como no plano anterior.
- **D5. `REVOKE UPDATE ON raw.weather_forecast FROM ingestor` na `0004`** (decisão do usuário, 2026-11-08). O banco passa a impor "o primeiro snapshot vence": `on_conflict="ignore"` continua funcionando (só exige `INSERT`), enquanto `on_conflict="update"` ou um `UPDATE` direto do `ingestor` falham com `42501`. É exceção documentada ao modelo de papéis da `0002` (que dá `INSERT, UPDATE` em `raw` ao `ingestor`), limitada a esta tabela: os privilégios padrão do schema `raw` não mudam. Fica registrada na docstring da migração (passo 2), no comentário da tabela (passo 5) e no corpo do PR. Não muda o contrato do ADR 0005, só o impõe no banco.

### Riscos

- **`downgrade` em produção apaga o histórico.** Depois do item 17, `alembic downgrade` abaixo de `0004` destrói snapshots que não podem ser recuperados (sem backfill de previsão; backup só no PR 57). Nunca rodar em produção; vale registrar isso no corpo do PR.
- **Mudar a faixa depois.** Trocar `weather_forecast_horizon_days_range` é migração de contrato (`ALTER TABLE ... DROP CONSTRAINT / ADD CONSTRAINT`), com ADR e aviso. Ampliar a faixa é barato; restringir exige que nenhuma linha viole a nova faixa.
- **Correção de snapshot só pelo admin.** Com D5, um snapshot errado não pode ser corrigido pelo job; exige ação manual do admin (`DATABASE_URL_ADMIN`). É o comportamento desejado ("previsão guardada como emitida"), mas qualquer correção futura deve ser exceção consciente, não rotina.
- **Exceção esquecida em tabelas futuras.** A regra de `.claude/rules/migrations-e-dados.md` ("`ingestor` escreve `raw` e `ref`") não menciona a exceção; quem ler só a regra pode supor `UPDATE` em `raw.weather_forecast`. Mitigação neste PR: docstring, comentário da tabela e casos 6, 18 e 19. Atualizar a regra ou o plano 07 fica fora do escopo (seção 10).
- **Unidades das variáveis.** O contrato não fixa unidade (o Open-Meteo devolve por padrão °C, mm, km/h e %). Este plano não grava unidade em comentário de coluna para não inventar contrato; a decisão é do PR 14 e deve entrar no aviso à cientista. Não bloqueia este PR.
- **Reflexão da coluna gerada no `upsert`.** O SQLAlchemy reflete `horizon_days` como coluna computada; o `INSERT` gerado só inclui as colunas do DataFrame. O caso 17 cobre isso; se falhar, o problema é do `upsert` (fora do escopo) e deve voltar ao coordenador, não ser contornado no teste.
- **Privilégios padrão dependem do admin.** As migrações precisam rodar com o mesmo admin (`DATABASE_URL_ADMIN`) para os privilégios padrão da `0002` valerem (docstring da `0002`); o `REVOKE` da `0004` também precisa ser feito pelo dono da tabela, que é esse admin. Na VPS, o item 12 já migrou até `0003` com esse admin; a `0004` sobe pelo procedimento interino do ADR 0004 (`docker compose -f infra/docker-compose.yml run --rm jobs alembic upgrade head`).
- **Postgres de teste.** Sem o container de `infra/docker-compose.dev.yml`, os testes `db` falham (não pulam), por desenho do `tests/conftest.py`.

### Aviso à ciência de dados

A regra exige aviso para mudança em `raw`. Quem envia é o usuário (passo 8), quando a `0004` estiver em produção. Conteúdo mínimo:

- Existe `raw.weather_forecast`: `location_id`, `issued_at`, `target_date`, `horizon_days`, `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`, `ingested_at`; chave (`location_id`, `issued_at`, `target_date`); `location_id` referencia `ref.locations`.
- `issued_at` é um dia (`date`), no fuso `America/Sao_Paulo`, em que o snapshot foi tirado; há no máximo um snapshot por local e data-alvo por dia, e o primeiro do dia vence. Snapshot antigo nunca é reescrito, e o banco impõe isso (o papel de ingestão não tem `UPDATE` na tabela).
- `horizon_days = target_date - issued_at`, gerado pelo banco, de 1 a 7. Não há horizonte 0 (previsão para o próprio dia) nesta versão; incluí-lo depois exige migração e emenda ao ADR 0005, e o histórico dele só começaria a partir daí (sem backfill).
- Para usar "a previsão disponível em D" sem vazamento: filtrar `issued_at <= D` (normalmente `issued_at = D`).
- As variáveis de clima podem vir nulas quando a fonte não tiver o valor; as faixas plausíveis são checadas pelo job (PR 15).
- `ingested_at` é o momento da escrita (nesta tabela, a única escrita da linha).
- O histórico começa no dia em que a coleta for ligada (item 17); não existe dado anterior.
- O papel `scientist` só lê esta tabela.

## 10. Decisões que exigem ADR

- **Nenhum ADR novo nem emenda obrigatória.** O ADR 0005 (mergeado) cobre `issued_at` como `date`, "o primeiro snapshot vence", horizontes 1 a 7, `ingested_at` como última escrita e `location_id` como chave estrangeira; ele mesmo remete ao PR 13 a confirmação da faixa do `CHECK` e do fuso, fechadas aqui por D1 e D3. A decisão de não guardar o horizonte 0 (D2) mantém o ADR 0005 como está, por decisão do usuário.
- **D5 (`REVOKE UPDATE`) não exige ADR**, por decisão do usuário: não muda o contrato do ADR 0005, só o impõe no banco, e a exceção ao modelo de papéis da `0002` fica documentada na migração, no comentário da tabela e no PR.
- **Opcional, decisão do usuário, em PR separado só de `docs/**`:** emenda curta ao ADR 0005 trocando os "Em aberto" (faixa do `CHECK`, horizonte 0 e fuso) por "Resolvido no PR 13", e registro da exceção D5. Não bloqueia este PR. Atualizar `.claude/rules/migrations-e-dados.md` com a exceção seria um PR à parte (toca `.claude/`, passa por `code-reviewer` e `pr-reviewer`).
- **Passaria a exigir emenda ao ADR 0005 (ou ADR novo), mergeada antes da implementação,** qualquer mudança no tipo de `issued_at`, na regra "o primeiro snapshot vence" ou na faixa de horizontes (inclusive guardar o horizonte 0 no futuro).
