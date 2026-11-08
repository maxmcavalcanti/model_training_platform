# 19 — Tabela `ref.calendar` e carga com a lib `holidays`

> Executa: agente. Depende de: 11, 15 (na `main`). Branch sugerida: `feat/ref-calendar`.
> Pré-requisito: ADR 0005 (`docs/adr/0005-data-contract-v1.md`), já mergeado; ele lista o PR 19 e delega tipos e colunas de `ref.calendar` a este plano (seção 10). Nenhum ADR novo é necessário.
> TDD: passo 0 (dependência) → test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-08: alinhado à `main` em `e6ae096` (migrações `0001` a `0004`, próxima `0005`; papéis e privilégios padrão da `0002`; fixtures de `tests/conftest.py`; padrão de `ref.locations` do plano 09 e de `tests/test_ref_locations.py`; `ingestion/db.py`, `ingestion/checks.py`, `ingestion/jobs.py`, `ingestion/cli.py`). As perguntas com recomendação viraram decisões D1 a D12 (seção 9), por autorização do usuário. Não há bloqueio.

## 1. Objetivo

Criar por migração Alembic (`0005`) a tabela `ref.calendar` (um dia por linha, dia da semana ISO e feriado nacional) e o subcomando `python -m ingestion calendar --start --end` que a preenche de forma idempotente, com feriados calculados offline pela lib `holidays` travada no `uv.lock`.
Migração e carga ficam no mesmo PR porque são pequenas e uma não tem uso sem a outra.

## 2. Fora do escopo

- Feriados estaduais e municipais, pontos facultativos (Carnaval, Corpus Christi, Quarta-feira de Cinzas, 24/12, 31/12), véspera e "ponte": a cientista deriva o que precisar em `features`.
- Agendamento: a tabela é carregada uma vez com folga de anos (D4); não entra no `infra/cron/crontab` nem vira flow do Prefect.
- Carga em produção: é o item 23 (`docs/plans/23-backfill-ons-e-pronto-fase-1-manual.md`, que já roda `calendar --start 2015-01-01 --end 2030-12-31` e espera `5844`).
- Marcar o checkbox "`ref.locations`, `ref.calendar`" do roadmap em `docs/plataforma-ml.md`: fecha quando a tabela estiver carregada em produção (item 23).
- Coluna `ingested_at`: a regra vale para `raw`; o modelo de dados de `ref.calendar` não tem essa coluna (como `ref.locations`).
- Chamada de rede para obter feriados (API externa): descartada em D1.
- Alterar `ingestion/db.py`, `ingestion/http.py`, `ingestion/openmeteo.py`, migrações `0001` a `0004`, `tests/conftest.py`, `tests/test_migrations.py`, `infra/`, `.github/workflows/ci.yml`, `.claude/` ou outros planos.
- `GRANT` explícito: as permissões vêm dos privilégios padrão da `0002`.
- Emenda ao ADR 0005 (opcional, ver seção 10).

## 3. Fase do roadmap

Fase 1 — "Banco e carga do ONS", item "`ref.locations`, `ref.calendar`" (`docs/plataforma-ml.md`, "Roadmap").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Passo 0: dependência de produção `holidays` (D1) |
| `migrations/versions/0005_ref_calendar.py` | Novo: cria `ref.calendar` com restrições e comentários; `downgrade` apaga a tabela |
| `ingestion/calendar_ref.py` | Novo: `build_calendar(start, end) -> pd.DataFrame` (puro, sem banco, sem rede). Nome `calendar_ref` porque `calendar` colide com o módulo da stdlib (ADR 0001) |
| `ingestion/checks.py` | Acrescentar `CALENDAR_SCHEMA` (D10) |
| `ingestion/jobs.py` | Acrescentar `load_calendar(engine, start, end) -> int` |
| `ingestion/cli.py` | Registrar o subcomando `calendar` em `SUBCOMMANDS` |
| `AGENTS.md` | Seção "Comandos": acrescentar a linha do `calendar` (cada PR registra seus comandos, como o PR 15 fez com `weather-forecast`) |
| `tests/test_ref_calendar.py` | Novo (test-writer): tabela, restrições, permissões, `downgrade` |
| `tests/test_calendar.py` | Novo (test-writer): `build_calendar`, `CALENDAR_SCHEMA`, `load_calendar`, CLI |

`tests/test_migrations.py` não muda: compara com o `head` dinamicamente e exige ids de 4 dígitos e head único; passa com a `0005`. `tests/test_raw_weather_forecast.py` faz `downgrade` até `0003` a partir do `head`, o que passa a reverter também a `0005`; continua verde porque o `downgrade` da `0005` só apaga `ref.calendar`.

### Contrato e modelo de dados

`docs/plataforma-ml.md`, "Modelo de dados":

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `ref.calendar` | `date`, `weekday`, `is_national_holiday`, `holiday_name` | `date` | Plataforma (lib `holidays`) | Todos |

`AGENTS.md`, "Fronteira": "Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados." Aqui: migração = `0005`; ADR = 0005 (seção 10); aviso = seção 9, "Aviso à ciência de dados", enviado pelo usuário.

ADR 0005, "Consequências": "O ADR cobre as tabelas dos PRs 09 (`ref.locations`), 13 (`raw.weather_forecast`), 19 (`ref.calendar`), 21 (`raw.ons_daily_load`) e 25 (`raw.weather_observed`), no que toca a estas três decisões. Os demais tipos e colunas dessas tabelas estão nos planos e em `docs/plataforma-ml.md`."

`.claude/rules/migrations-e-dados.md`:

> - Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.
> - Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados. Mudança na assinatura do contrato exige ADR.
> - Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `scientist` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `reader` só lê. Toda tabela nova declara quem escreve e quem lê.
> - Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.

Quem escreve e quem lê `ref.calendar` (privilégios padrão de `migrations/versions/0002_roles.py`, válidos para tabelas criadas pelo admin que roda as migrações):

| Papel | `ref.calendar` |
| --- | --- |
| admin (`DATABASE_URL_ADMIN`) | dono |
| `ingestor` | `SELECT`, `INSERT`, `UPDATE` (sem `DELETE`); é quem roda o job |
| `scientist`, `scorer`, `reader` | só `SELECT` |

Trecho de `0002_roles.py`:

```python
op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {ALL_ROLES}")
...
op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schemas} GRANT INSERT, UPDATE ON TABLES TO {role}")
# (raw, ref) -> ingestor ; (predictions, monitoring) -> scorer
```

### Código existente que este PR usa (estado em `e6ae096`)

`ingestion/db.py`:

```python
def build_engine(url: str | None = None) -> sqlalchemy.Engine  # usa DATABASE_URL; levanta MissingConfiguration
def upsert(conn: sqlalchemy.Connection, table: str, rows: pd.DataFrame, keys: list[str], *,
           on_conflict: Literal["update", "ignore"] = "update",
           stamp_ingested_at: bool = True) -> int
```

- `upsert` reflete a tabela, recusa coluna inexistente e chave duplicada no DataFrame, converte `NaN`/`None` em `NULL`, faz lotes de até 5000 linhas e devolve inseridas + atualizadas (modo `"update"`). Não faz commit: quem chama é dono da transação. Com `stamp_ingested_at=True` exige coluna `ingested_at`; para `ref.calendar` passar `stamp_ingested_at=False`.

`ingestion/checks.py`:

```python
class CheckFailed(RuntimeError): ...
def check(df: pd.DataFrame, schema: pa.DataFrameSchema, expected_rows: int | None = None) -> None
WEATHER_FORECAST_SCHEMA = pa.DataFrameSchema({...}, checks=pa.Check(...), unique=[...], strict=False)
```

Importa `pandera.pandas as pa`. `check` junta todos os problemas num único `CheckFailed`.

`ingestion/cli.py`: `SUBCOMMANDS: dict[str, Subcommand]`, com `Subcommand(help, add_arguments, run)`. `main` devolve 0, 1 (exceção em `run`, traceback no stderr) ou 2 (erro de uso do argparse). O `weather-forecast` importa `jobs` e `build_engine` dentro do `run` e faz `engine.dispose()` no `finally`; seguir o mesmo padrão.

`ingestion/jobs.py`: `ingest_weather_forecast` grava com `engine.begin()`, relê com `pd.read_sql_query(sqlalchemy.text(...), conn, params=...)` e chama `check(...)` depois de gravar. `load_calendar` segue o mesmo desenho.

`migrations/versions/0004_raw_weather_forecast.py`: modelo de estilo (só `from alembic import op`, SQL em `op.execute`, restrições com nome fixo, `COMMENT ON TABLE/COLUMN`, docstring dizendo que as permissões vêm da `0002`).

### Padrões de teste a seguir

- Fixtures de `tests/conftest.py` (não alterar): `migrated_database` (sessão, em `head`, **só leitura**); `fresh_database` (por teste, vazio). Teste que escreve ou faz `downgrade` usa um fixture próprio, como `locations_database` em `tests/test_ref_locations.py`:

```python
@pytest.fixture
def calendar_database(fresh_database, monkeypatch) -> Iterator[str]:
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    command.upgrade(alembic_config(), "head")
    yield fresh_database
```

- Agir como papel: `SET ROLE <papel>` na conexão (`_execute`, `_assert_denied` em `tests/test_ref_locations.py`) ou engine com `create_engine(url, connect_args={"options": "-c role=ingestor"})` (`_run_as_ingestor` em `tests/test_job_weather_forecast.py`).
- Erros: `IntegrityError`/`ProgrammingError` com `error.orig.sqlstate` e `error.orig.diag.constraint_name`. SQLSTATEs: `42501` permissão, `23514` `CHECK`, `23502` `NOT NULL`, `23505` chave duplicada.
- Testes de banco com `pytestmark = pytest.mark.db` ou `@pytest.mark.db`. Testes de `build_calendar`, do schema e de parsing do CLI rodam sem banco.
- CLI: `effective_code(argv)` de `tests/test_cli.py` (valor devolvido ou `SystemExit.code`).

## 5. Passos

0. (implementer, antes do test-writer, em commit próprio `build: add holidays dependency`) `uv add holidays`. Conferir em `uv.lock` a versão resolvida e anotá-la no PR. Rodar `uv run python -c "import holidays; h = holidays.country_holidays('BR', years=2026, language='pt_BR', categories=(holidays.PUBLIC,)); print(holidays.__version__); [print(d, n) for d, n in sorted(h.items())]"` e colar a saída no PR. Se a saída não tiver exatamente as 10 datas do caso 4 da seção 8, **parar e reportar** (não seguir com a versão).
1. (test-writer) Partindo do commit do passo 0, escreva `tests/test_ref_calendar.py` e `tests/test_calendar.py` com os casos da seção 8, seguindo a seção 4. Os nomes de feriado esperados nos casos 5 e 6 são os impressos no passo 0 (D3). Rode `uv run pytest tests/test_ref_calendar.py tests/test_calendar.py` e confirme a falha por `ModuleNotFoundError: No module named 'ingestion.calendar_ref'` (ou `ImportError` de `load_calendar`/`CALENDAR_SCHEMA`) e por `ref.calendar` inexistente. `uv run ruff check .` e `uv run ruff format --check .` limpos. Commit `test: add ref.calendar tests`.
2. (implementer) `uv run alembic revision -m "ref_calendar" --rev-id 0005`. Confira `down_revision = "0004"`. Imports como na `0004` (só `from alembic import op`; apague o comentário do template). Docstring: cria `ref.calendar`; a carga é do job `calendar` (não da migração, D5); permissões da `0002`.
3. `upgrade`, a tabela (nomes de restrição fixos; os testes conferem):

   ```sql
   CREATE TABLE ref.calendar (
       "date" date PRIMARY KEY,
       weekday smallint NOT NULL
           CONSTRAINT calendar_weekday_isodow CHECK (weekday = EXTRACT(ISODOW FROM "date")),
       is_national_holiday boolean NOT NULL,
       holiday_name text,
       CONSTRAINT calendar_holiday_name_consistency CHECK (
           (is_national_holiday AND holiday_name IS NOT NULL AND holiday_name <> '')
           OR (NOT is_national_holiday AND holiday_name IS NULL)
       )
   )
   ```

   E os comentários:
   - `COMMENT ON TABLE ref.calendar IS 'One row per day. National public holidays of Brazil from the holidays library pinned in uv.lock (no state or municipal holidays, no optional days such as Carnival). Loaded by python -m ingestion calendar.'`
   - `COMMENT ON COLUMN ref.calendar.weekday IS 'ISO 8601 day of week: 1 = Monday ... 7 = Sunday.'`
   - `COMMENT ON COLUMN ref.calendar.holiday_name IS 'Holiday name in Brazilian Portuguese (pt_BR); NULL when the day is not a national holiday.'`
4. `downgrade`: `op.execute("DROP TABLE ref.calendar")`.
5. `ingestion/calendar_ref.py`: `build_calendar(start: date, end: date) -> pd.DataFrame`.
   - `start > end` → `ValueError` com as duas datas na mensagem.
   - Uma linha por dia de `start` a `end`, inclusive, em ordem crescente, colunas nesta ordem: `date` (`datetime.date`), `weekday` (`int`, `date.isoweekday()`), `is_national_holiday` (`bool`), `holiday_name` (`str` ou `None`).
   - Feriados: `holidays.country_holidays("BR", years=range(start.year, end.year + 1), language="pt_BR", categories=(holidays.PUBLIC,))`, sem `subdiv` (D2). Dois feriados na mesma data saem como a lib os junta (nome único com `"; "`); não há caso em 2015–2030.
   - Sem banco, sem rede, sem relógio.
6. `CALENDAR_SCHEMA` em `ingestion/checks.py`:
   - `date`: não nula, única.
   - `weekday`: `int`, em 1..7, não nula.
   - `is_national_holiday`: `bool`, não nula.
   - `holiday_name`: nulável.
   - Checagens de quadro: `weekday` igual ao `isoweekday()` de `date`; `is_national_holiday` verdadeiro se e só se `holiday_name` não é nulo nem vazio.
   - `strict=False`, como `WEATHER_FORECAST_SCHEMA`.
7. `ingestion/jobs.py`: `load_calendar(engine: sqlalchemy.Engine, start: date, end: date) -> int`.
   - `rows = build_calendar(start, end)` (o `ValueError` sobe antes de tocar o banco).
   - `with engine.begin() as conn: written = upsert(conn, "ref.calendar", rows, keys=["date"], on_conflict="update", stamp_ingested_at=False)`.
   - Relê `SELECT date, weekday, is_national_holiday, holiday_name FROM ref.calendar WHERE date BETWEEN :start AND :end ORDER BY date` e chama `check(stored, CALENDAR_SCHEMA, expected_rows=(end - start).days + 1)`. Falha → `CheckFailed` (execução falha).
   - Log `INFO`: `calendar ok: %d days from %s to %s, %d national holidays`. Devolve `written`.
8. `ingestion/cli.py`: subcomando `calendar`, help `Load ref.calendar (one row per day, national holidays) for a date range`. Argumentos `--start` e `--end`, obrigatórios, `type=date.fromisoformat` (data inválida ou ausente → argparse sai com 2). O `run` abre `build_engine()`, chama `jobs.load_calendar(engine, args.start, args.end)`, `dispose` no `finally`, devolve 0. `start > end` → `ValueError` → `main` devolve 1 (D9).
9. `AGENTS.md`, "Comandos", logo após a linha do snapshot da previsão: `- Calendário: \`uv run python -m ingestion calendar --start 2015-01-01 --end 2030-12-31\` (usa \`DATABASE_URL\`; na VPS: \`docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion calendar --start 2015-01-01 --end 2030-12-31\`)`.
10. Rode os critérios de pronto e cole comando e saída no PR.
11. (usuário, depois do item 23 carregar a tabela em produção) Enviar à cientista o aviso da seção 9.

## 6. Critérios de pronto

Precisa do Postgres de teste: `docker compose -f infra/docker-compose.dev.yml up -d`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_ref_calendar.py tests/test_calendar.py tests/test_migrations.py tests/test_permissions.py tests/test_raw_weather_forecast.py tests/test_cli.py` | Todos passam, nenhum `skipped` |
| `uv run pytest -m "not db" tests/test_calendar.py` | Passa sem Postgres (casos sem banco) |
| `uv run alembic heads` | `0005 (head)` |
| `uv run alembic history` | Primeira linha `0004 -> 0005 (head), ref_calendar` |
| `uv run python -m ingestion calendar --help` | Mostra `--start` e `--end` |
| `uv run python -m ingestion calendar --start 2026-13-01 --end 2026-12-31; echo $?` | Mensagem `invalid fromisoformat value` (ou similar do argparse) e `2` |
| `uv run python -c "import holidays; print(holidays.__version__)"` | A versão travada em `uv.lock` (a mesma anotada no passo 0) |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| `git diff --name-only main...HEAD` | Só os arquivos da seção 4 |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: há lógica nova (montagem do calendário, regra de feriado, checagem, upsert, CLI); feriado ou dia da semana errados viram erro silencioso em todo modelo de carga.

## 8. Casos de teste

`build_calendar` (sem banco, `tests/test_calendar.py`):

1. `build_calendar(2026-01-01, 2026-12-31)` → 365 linhas, datas únicas, contínuas e crescentes; colunas exatamente `date`, `weekday`, `is_national_holiday`, `holiday_name`.
2. `build_calendar(2024-01-01, 2024-12-31)` → 366 linhas (bissexto); `build_calendar(2026-03-10, 2026-03-10)` → 1 linha.
3. `start > end` (`2026-02-01`, `2026-01-31`) → `ValueError`.
4. Em 2026, os dias com `is_national_holiday = True` são exatamente: 01-01, 04-03 (Sexta-feira Santa), 04-21, 05-01, 09-07, 10-12, 11-02, 11-15, 11-20, 12-25 (10 dias).
5. 2026-01-01 → feriado, `weekday = 4`, `holiday_name` igual ao impresso no passo 0 (esperado `Confraternização Universal`).
6. 2026-11-20 → feriado (Consciência Negra, nacional desde 2024), `weekday = 5`, nome igual ao do passo 0; 2026-11-15 → feriado, `weekday = 7`.
7. 2023-11-20 → `is_national_holiday = False` (antes da lei de 2023 valer).
8. Pontos facultativos não entram: 2026-02-16 e 2026-02-17 (Carnaval), 2026-02-18 (Cinzas), 2026-06-04 (Corpus Christi), 2026-12-24 e 2026-12-31 → `is_national_holiday = False`, `holiday_name` nulo.
9. 2026-11-09 (segunda comum) → `False`, nulo, `weekday = 1`.
10. Para todo dia de 2015-01-01 a 2030-12-31: `weekday == date.isoweekday()`, e `is_national_holiday` é verdadeiro se e só se `holiday_name` é texto não vazio; total de feriados no intervalo = 151 (9 por ano de 2015 a 2023, 10 de 2024 a 2030). Se a versão travada der outro total, o test-writer para e reporta, não ajusta o número.
11. Mesma entrada duas vezes → DataFrames iguais (determinístico).

`CALENDAR_SCHEMA` (sem banco):

12. Saída de `build_calendar(2026-01-01, 2026-12-31)` passa em `check(df, CALENDAR_SCHEMA, expected_rows=365)`.
13. `weekday = 8` → `CheckFailed` citando `weekday`; `weekday` que não bate com a data (2026-11-09 com 2) → `CheckFailed`.
14. `is_national_holiday = True` com `holiday_name` nulo, e `False` com nome preenchido → `CheckFailed`.
15. Data duplicada → `CheckFailed`; `expected_rows=366` com 365 linhas → `CheckFailed` citando `expected 366 rows, got 365`.

Tabela (`tests/test_ref_calendar.py`, `db`):

16. Em `migrated_database`: colunas pelo `information_schema.columns` exatamente `date date`, `holiday_name text` (nulável), `is_national_holiday boolean`, `weekday smallint`, as três não nulas; chave primária só `date`; tabela vazia logo após a migração.
17. Inserir `('2026-11-09', 2, false, null)` → `23514` em `calendar_weekday_isodow`; `('2026-11-09', 1, false, null)` funciona.
18. `(…, true, null)`, `(…, true, '')` e `(…, false, 'Natal')` → `23514` em `calendar_holiday_name_consistency`.
19. `NULL` em `date`, `weekday` ou `is_national_holiday` → `23502`; mesma `date` duas vezes → `23505`.
20. Como `ingestor`: `INSERT` e `UPDATE` funcionam; `DELETE` → `42501`.
21. Como `reader`, `scientist`, `scorer`: `SELECT` funciona; `INSERT` → `42501`.
22. `downgrade` até `0004`: `ref.calendar` some, `ref.locations` e `raw.weather_forecast` continuam; `upgrade head` recria `ref.calendar` vazia.

Job e CLI (`tests/test_calendar.py`):

23. (`db`) `load_calendar` como `ingestor`, 2015-01-01 a 2030-12-31 → 5844 linhas na tabela, 151 com feriado; rodar de novo → continua 5844 e o conteúdo é idêntico.
24. (`db`) Corrigir dado errado: o admin põe `is_national_holiday = false, holiday_name = null` em 2026-12-25; `load_calendar(2026-12-01, 2026-12-31)` como `ingestor` → 2026-12-25 volta a ser feriado com o nome do passo 0; linhas fora do intervalo intactas.
25. (`db`) Carga parcial seguida de intervalo maior (2026-01-01 a 2026-01-31, depois 2026-01-01 a 2026-12-31) → 365 linhas, sem duplicata.
26. (`db`) `load_calendar(2026-02-01, 2026-01-31)` → `ValueError` e a tabela continua vazia.
27. (`db`) `main(["calendar", "--start", "2026-01-01", "--end", "2026-01-31"])` com `DATABASE_URL` apontando para o banco migrado → 0 e 31 linhas.
28. CLI sem banco: `calendar --start 2026-13-01 --end 2026-12-31` → 2; `calendar --start 2026-01-01` (sem `--end`) → 2; `calendar --help` → 0 e saída com `--start` e `--end`.
29. (`db`) `main(["calendar", "--start", "2026-02-01", "--end", "2026-01-31"])` com `DATABASE_URL` válido → 1 e traceback com `ValueError` no stderr.

Já existentes que continuam verdes sem edição: `tests/test_migrations.py`, `tests/test_permissions.py`, `tests/test_ref_locations.py` (faz `downgrade` até `0002`, passando pela `0005`), `tests/test_raw_weather_forecast.py` (`downgrade` até `0003`), `tests/test_cli.py`.

## 9. Riscos e perguntas em aberto

Nenhuma pergunta em aberto bloqueia. Decisões (adotadas pelas recomendações, com autorização do usuário):

- **D1. Fonte dos feriados: lib `holidays`, offline, travada no `uv.lock`.** É a fonte que `docs/plataforma-ml.md` já declara ("Plataforma (lib `holidays`)"); calcula as regras localmente, sem rede, então o job não precisa de retry, é reproduzível no CI e no Docker, e a mesma entrada dá a mesma saída. Uma API de feriados exigiria rede, retry, fixture gravada e dependência de terceiro.
- **D2. Só feriados nacionais (`categories=(holidays.PUBLIC,)`, sem `subdiv`), nomes em `pt_BR` explícito.** Os pontos facultativos ficam na categoria `OPTIONAL` da lib e são decisão de feature da cientista. `language="pt_BR"` explícito evita depender do padrão da lib ou da localidade da máquina. Sexta-feira Santa entra porque a lib a classifica como feriado nacional; a nuance legal (Lei 9.093/1995) vai no aviso.
- **D3. Nomes esperados nos testes vêm da versão travada (passo 0); datas vêm da lei.** O teste falha se uma atualização da lib mudar data ou nome, o que torna a mudança visível num PR. Diferença de **data** em relação ao caso 4 ou ao total do caso 10 é bloqueio (o implementador para); diferença de **nome** se registra.
- **D4. Faixa carregada: 2015-01-01 a 2030-12-31 (5844 dias, 151 feriados).** 2015 é o início do backfill do ONS e do clima; 2030 dá folga de anos para `target_date` futuro. É a faixa que o item 23 já usa. A tabela aceita qualquer data; a faixa é só do comando operacional.
- **D5. Carga pelo job, não pela migração** (diferente de `ref.locations`). O conteúdo depende da versão da lib; numa migração ficaria congelado e não poderia ser recarregado de forma idempotente depois de atualizar a lib. O job faz upsert e pode rodar quantas vezes for preciso.
- **D6. Manutenção.** (a) Estender a faixa: rodar `calendar` com o novo `--end` antes de 2030 (sugestão: ao passar de 2029-01-01, para manter 2 anos de folga); é idempotente. (b) Atualizar a lib (nova lei de feriado): `uv add holidays@latest` (ou `uv lock --upgrade-package holidays`) num PR próprio, rodar a suíte (casos 4, 5, 6 e 10 travam data e nome) e depois rodar `calendar` de novo na VPS; o upsert com `update` reescreve todos os dias do intervalo, inclusive um feriado que deixou de existir. Mudança de feriado que altera dados de `ref` gera aviso à cientista, sem ADR (o schema não muda). (c) Nenhum agendamento (D4).
- **D7. `weekday` no padrão ISO 8601 (1 = segunda, 7 = domingo), com `CHECK` contra `EXTRACT(ISODOW FROM "date")`.** É o `date.isoweekday()` do Python e o `isodow` do Postgres; o banco garante a coerência. Cuidado comunicado no aviso: `EXTRACT(DOW)` do Postgres e `pandas.Series.dt.dayofweek` usam outras convenções. Coluna gerada (como `horizon_days` da `0004`) foi considerada e descartada: o upsert enviaria `weekday` e falharia; manter a coluna normal com `CHECK` é mais simples.
- **D8. Restrição feriado ↔ nome no banco** (`calendar_holiday_name_consistency`, recusa também nome vazio), além da checagem pandera.
- **D9. `start > end` sai com código 1, não 2.** O `main` só mapeia para 2 erros do argparse; validar o intervalo no `run` mudaria o desenho de `ingestion/cli.py`. A mensagem do `ValueError` cita as datas.
- **D10. Nome `CALENDAR_SCHEMA`** em vez de `SCHEMA_CALENDAR` (tabela do ADR 0001): segue o código já mergeado (`WEATHER_FORECAST_SCHEMA`, que também diverge do `SCHEMA_WEATHER_FORECAST` do ADR). Coerência dentro de `checks.py` vale mais; não muda a regra de inglês do ADR.
- **D11. Testes em dois arquivos** (`tests/test_ref_calendar.py` para a tabela, `tests/test_calendar.py` para lógica, job e CLI), seguindo a divisão de `test_ref_locations.py` / `test_raw_weather_forecast.py` e `test_checks_*` / `test_job_*`.
- **D12. Job roda como `ingestor` em produção** (via `DATABASE_URL`); precisa de `UPDATE`, que a `0002` dá em `ref`. Não há `REVOKE` como na `0004`, porque aqui recarregar deve sobrescrever.

Riscos:

- **Versão da lib.** Se a versão resolvida no passo 0 não tiver Consciência Negra em 2024+ ou classificar Carnaval como `PUBLIC`, o passo 0 para (D3). Versões recentes da lib tratam os dois como o plano espera, mas a confirmação é pela saída real.
- **Tamanho da imagem.** `holidays` é Python puro e traz dados de muitos países; impacto pequeno na imagem `platform-jobs`. Conferir com `docker build -f infra/jobs/Dockerfile -t platform-jobs .` que a imagem constrói (`uv sync --locked --no-dev`).
- **`date` como nome de coluna.** É aceito pelo Postgres, mas na restrição o plano usa `"date"` entre aspas para não haver ambiguidade com o literal `date '...'`.
- **Compatibilidade com pandas 3.** `pd.read_sql_query` devolve `date` como objetos `datetime.date` e `weekday` como inteiro; o `CALENDAR_SCHEMA` não fixa o dtype de `date` (como `issued_at` no schema da previsão) para não depender disso.

### Aviso à ciência de dados

A regra exige aviso para mudança em `ref`. Quem envia é o usuário (passo 11), junto do aviso de fim da Fase 1 (item 23). Conteúdo mínimo:

- Existe `ref.calendar` (`date`, `weekday`, `is_national_holiday`, `holiday_name`), chave `date`, um dia por linha de 2015-01-01 a 2030-12-31.
- `weekday` é ISO: 1 = segunda ... 7 = domingo (igual a `date.isoweekday()` e a `EXTRACT(ISODOW ...)`; diferente de `EXTRACT(DOW ...)` e de `pandas .dt.dayofweek`).
- Só feriados nacionais da lib `holidays` (versão travada no `uv.lock` da plataforma), nomes em português. Não entram feriados estaduais/municipais nem pontos facultativos (Carnaval, Cinzas, Corpus Christi, 24/12, 31/12): se o modelo precisar, é feature dela. Consciência Negra (20/11) é nacional a partir de 2024. Sexta-feira Santa aparece como nacional, como a lib a classifica.
- A tabela pode ser recarregada quando a lib for atualizada (lei nova); a plataforma avisa quando isso mudar dados.
- `scientist` só lê.

## 10. Decisões que exigem ADR

- **Nenhum ADR novo.** A exigência do `AGENTS.md` (migração + ADR + aviso para mudança em `ref`) é cumprida por: migração `0005`; ADR 0005 (mergeado), que lista explicitamente o PR 19 e diz que "os demais tipos e colunas dessas tabelas estão nos planos e em `docs/plataforma-ml.md`"; e o aviso da seção 9. As decisões de semântica de colunas (D2, D7, D8) e de fonte (D1) ficam neste plano, como o ADR 0005 delega; a fonte (lib `holidays`) já está em `docs/plataforma-ml.md`.
- **Contrato das funções** (`build_features`, `predict`, `evaluate`): não muda; sem ADR.
- **Rede/portas:** nada é exposto; sem ADR (ADR 0003).
- **Dependência nova:** entra por `uv add` com `uv.lock`, como manda o ADR 0002; sem ADR.
- Opcional, decisão do usuário: emenda curta ao ADR 0005 (PR só de `docs/**`) registrando `weekday` ISO e "só feriados nacionais". Não bloqueia.
- Exigiriam ADR no futuro (novo ou emenda ao 0005), com migração e aviso: adicionar coluna a `ref.calendar` (por exemplo feriado estadual, ponto facultativo) ou mudar a convenção de `weekday`.
