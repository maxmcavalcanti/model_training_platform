# 28 — Bancos e papéis `mlflow` e `prefect` no Postgres (bootstrap idempotente)

> Executa: agente. Depende de: 07 (papéis), 11 (CLI e imagem `jobs`), já na `main`. Branch: `feat/mlflow-prefect-databases`.
> TDD: test-writer (vermelho) → implementação mínima (verde) → refatorar com a suíte verde.
> Quando começar: depois do item 27 fechado (D+7, não antes de 2026-11-15), salvo autorização do usuário (pergunta 1 da seção 9). O deploy na VPS é do item 31, nunca deste PR.
> Revisão 2026-11-08 (v2, com a revisão independente aceita pelo usuário): reescrito contra a `main` em `05c32c9`. Em relação ao rascunho: bootstrap em Python + migração `0008_ml_database_connect`; papéis sem atributos elevados e com `CONNECTION LIMIT`; `REVOKE ALL ... FROM PUBLIC` nos bancos novos e `REVOKE CONNECT` de `PUBLIC` no `ml`; senha URL-safe; variáveis só no `jobs`. Na v2: nome do admin lido da URL antes de conectar; conexão por `psycopg.connect(**translate_connect_args(...))`, nunca por SQLAlchemy nos comandos com senha; caso de falha forçada sem vazar a senha; allow-list de variáveis por serviço já com `mlflow` e `prefect-server`; migração sem `%` (nome do banco lido por `exec_driver_sql` e citado pelo `identifier_preparer`); caso 17 com `fresh_database`; renumeração dos planos 41 (`0009`) e 51 (`0010`); desvio de nomes em relação ao ADR 0001 registrado.

## 1. Objetivo

Criar, com um subcomando idempotente `python -m ingestion create-databases`, os bancos `mlflow` e `prefect` no Postgres da plataforma, cada um com um papel dono de mesmo nome, sem atributos elevados, com limite de conexões e fechado para `PUBLIC`.
Fechar o `CONNECT` de `PUBLIC` no banco `ml` (migração `0008_ml_database_connect`), para que os papéis novos não entrem nele; são os backends que os PRs 29 (MLflow) e 30 (Prefect) usam.

## 2. Fora do escopo

- Os serviços `mlflow` e `prefect-server` (PRs 29 e 30) e qualquer `mem_limit` novo.
- Deploy na VPS, senhas reais, `alembic upgrade` em produção (item 31).
- Schemas e tabelas dentro de `mlflow` e `prefect`: cada ferramenta cria o próprio schema na primeira subida.
- Senhas dos quatro papéis do `ml` (`ingestor`, `scientist`, `scorer`, `reader`): continuam como no plano 12.
- Revogar `CONNECT` de `PUBLIC` nos bancos de manutenção `postgres` e `template1` (pergunta 5).
- Qualquer mudança em `raw`, `ref` ou no contrato `build_features`/`predict`/`evaluate`: nenhuma.
- Backup dos bancos novos (PR 57).
- Editar o ADR 0001 (agente não edita ADR; ver seção 9, "Desvios em relação ao ADR 0001").

## 3. Fase do roadmap

Fase 3 — "MLflow, Prefect e CI/CD" (`docs/plataforma-ml.md`, "Roadmap"), pré-requisito do item "MLflow e Prefect no compose, só na tailnet (`tailscale serve`)". Do doc, "Stack na VPS": "PostgreSQL 16 | Dados brutos, features, previsões, métricas; também é backend do MLflow e do Prefect | Os dois | Um banco por serviço (`ml`, `mlflow`, `prefect`)".

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/test_service_databases.py` | test-writer | Casos 1 a 12 (marcados `db`) e 13 a 15 (sem banco) |
| `tests/test_ml_database_connect.py` | test-writer | Casos 16 a 18 (migração `0008`, marcados `db`) |
| `tests/test_cli.py` | test-writer | Casos 19 a 23 (subcomando) |
| `tests/infra/test_compose.py` | test-writer | Casos 24 a 27 (seção nova "plan 28") |
| `ingestion/service_databases.py` | implementer | `SERVICE_DATABASES` e `ensure_service_database` |
| `ingestion/cli.py` | implementer | Subcomando `create-databases` |
| `migrations/versions/0008_ml_database_connect.py` | implementer | `REVOKE CONNECT` de `PUBLIC` no banco corrente; `GRANT CONNECT` aos quatro papéis |
| `infra/docker-compose.yml` | implementer | `MLFLOW_DB_PASSWORD` e `PREFECT_DB_PASSWORD` no `environment` do `jobs` |
| `infra/.env.example` | implementer, anexando pelo Bash sem ler | As duas variáveis com valores fictícios URL-safe |
| `.github/workflows/ci.yml` | implementer | Três passos no `compose-smoke` (passo 7) |
| `AGENTS.md` | implementer | Linha do `create-databases` em "Comandos" |

Planos ajustados nesta revisão (já feito pelo planner, só números): `docs/plans/41-tabela-previsoes.md` passa a usar a `0009` e `docs/plans/51-tabela-metricas.md` a `0010`.

### Decisão de desenho: Alembic ou bootstrap (recomendação aceita)

| Opção | A favor | Contra |
| --- | --- | --- |
| A. Migração Alembic no `ml` criando bancos e papéis | Versionado, roda no deploy | `CREATE DATABASE` não roda em transação; o Alembic versiona o schema do `ml`, não o servidor; a senha teria de entrar na migração (CI e testes rodam sem segredo); `downgrade` derrubando banco do MLflow é perigoso |
| B. Subcomando Python idempotente (`create-databases`) rodado pelo `jobs` com o admin | Testável (TDD), converge a cada execução (senha, dono, atributos), mesmo caminho do `alembic` | Não fica em `alembic_version`; esquecer de rodar aparece na subida do MLflow |
| C. Script em `docker-entrypoint-initdb.d` | Padrão da imagem | Só roda com o diretório de dados vazio; a VPS já tem dados. Descartada |
| D. SQL manual do usuário | Simples | Sem teste nem versionamento. Descartada |

**Decisão: B para bancos e papéis de serviço, e a migração `0008` só para o que é do banco `ml`** (o `CONNECT` de `PUBLIC`). Nada disso toca `raw` ou `ref`.

### Contexto que o implementador precisa (código atual)

`ingestion/cli.py` registra subcomandos num dicionário e trata erro assim (trecho):

```python
@dataclass(frozen=True)
class Subcommand:
    help: str
    add_arguments: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], int]

SUBCOMMANDS: dict[str, Subcommand] = {}
...
def main(argv: list[str] | None = None) -> int:
    ...
    try:
        return SUBCOMMANDS[name].run(args)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        logger.error("subcommand %s failed", name)
        return 1
```

Códigos de saída: `0` sucesso, `1` falha de execução, `2` uso incorreto. `ingestion/db.py` tem `MissingConfiguration(RuntimeError)`. Atenção: o `traceback.print_exc` imprime a mensagem da exceção; por isso nenhuma exceção levantada ou repassada pelo módulo novo pode conter a senha (casos 10, 11 e 21).

`infra/docker-compose.yml`, serviço `jobs` hoje:

```yaml
  jobs:
    build:
      context: ..
      dockerfile: infra/jobs/Dockerfile
    profiles: ["jobs"]
    restart: "no"
    mem_limit: 512m
    environment:
      DATABASE_URL: postgresql+psycopg://ingestor:${POSTGRES_INGESTOR_PASSWORD:?POSTGRES_INGESTOR_PASSWORD is required}@postgres:5432/ml
      DATABASE_URL_ADMIN: postgresql+psycopg://${POSTGRES_ADMIN_USER:?POSTGRES_ADMIN_USER is required}:${POSTGRES_ADMIN_PASSWORD:?POSTGRES_ADMIN_PASSWORD is required}@postgres:5432/ml
    depends_on:
      postgres:
        condition: service_healthy
```

O `scheduler` só tem `DATABASE_URL` do `ingestor` e os testes travam referência a `ADMIN` nele. A `0002` cria os quatro papéis com `LOGIN` e sem senha; o `ml` hoje deixa `CONNECT` para `PUBLIC` (padrão do Postgres).

`tests/conftest.py`: bancos descartáveis `ml_test_<8 hex>` pelo admin de `DATABASE_URL_TEST` (padrão `postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres`); fixtures `fresh_database` (vazio, por teste) e `migrated_database` (em `head`, por sessão, só leitura). Papéis são globais ao servidor: nomes únicos e teardown.

Regras citadas:

- `AGENTS.md`: segredos só por variável de ambiente; nenhum segredo no git (repo público); agentes nunca leem arquivos `.env`, nem `infra/.env.example`; ruff `S` sem `noqa` (ignore só em `per-file-ignores`, por caminho e regra, com motivo).
- `.claude/rules/migrations-e-dados.md`: "Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`."
- `.claude/rules/infra.md`: `.env` fora do git, permissão 600; o agente pode rodar `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q`, nunca sem `-q` nem sem `--env-file infra/.env.example`.
- `tests/infra/test_supply_chain_pins.py` conta exatamente 3 linhas `uses:` e 2 `actions/checkout` no `ci.yml`: os passos novos são só `run:`.

## 5. Passos

1. (test-writer) Escreva os casos da seção 8. Confirme que falham pelo motivo certo: `ModuleNotFoundError: ingestion.service_databases`; `invalid choice: 'create-databases'`; papel sem privilégio ainda com `CONNECT` no banco migrado (falta a `0008`); `jobs` sem as duas variáveis. Commit: `test: add service database bootstrap tests`.
2. (implementer) `ingestion/service_databases.py`:
   - Constante `SERVICE_DATABASES`: `mlflow` → variável `MLFLOW_DB_PASSWORD`, limite `10`; `prefect` → `PREFECT_DB_PASSWORD`, limite `20`. Ordem: `mlflow`, depois `prefect`.
   - `ensure_service_database(admin_url: str, name: str, password: str, *, connection_limit: int) -> None`, nesta ordem:
     1. Valida `name` com `^[a-z][a-z0-9_]{0,62}$` e recusa nomes reservados: `postgres`, `template0`, `template1`, `ml`, `ingestor`, `scientist`, `scorer`, `reader`, qualquer nome começando com `pg_` e **o usuário admin lido de `sqlalchemy.engine.make_url(admin_url).username`**, tudo **antes de conectar**. Depois de conectar, pode conferir também `current_user` (mesma regra). Inválido → `ValueError`, nada alterado no servidor.
     2. Valida `password` com `^[A-Za-z0-9._~-]{16,}$`. Inválida → `ValueError` com a regra e a sugestão `openssl rand -hex 24`, **sem a senha**.
     3. Conecta com psycopg direto, em `autocommit` (`CREATE DATABASE` não roda em transação):

        ```python
        url = sqlalchemy.engine.make_url(admin_url)
        connection = psycopg.connect(
            **url.translate_connect_args(username="user", database="dbname"), autocommit=True
        )
        ```

        Nunca use SQLAlchemy (`text()`, `Connection.execute`, `exec_driver_sql`) para `CREATE ROLE` ou `ALTER ROLE ... PASSWORD`: em erro, o `StatementError` do SQLAlchemy imprime `[SQL: ...]` e os parâmetros, e a senha iria para o stderr.
     4. Papel: se não existe, `CREATE ROLE <name> WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT <n> PASSWORD <literal>`; se existe, `ALTER ROLE <name> WITH` os mesmos atributos e a senha.
     5. Banco: se não existe, `CREATE DATABASE <name> OWNER <name>`; se existe, `ALTER DATABASE <name> OWNER TO <name>`.
     6. `REVOKE ALL ON DATABASE <name> FROM PUBLIC`.
     7. Loga `service database ready: <name>` (sem URL, sem senha).
   - SQL montado só com `psycopg.sql.SQL`, `sql.Identifier` e `sql.Literal`. Erros do psycopg nos comandos com senha são capturados e relevantados com uma mensagem própria (ex.: `RuntimeError(f"could not create or update role {name}: {error.sqlstate}")`, com `from None`), para que nem a mensagem nem a cadeia de exceções carreguem o texto do comando. Achado do ruff `S` se corrige no código, nunca `noqa`.
3. (implementer) `ingestion/cli.py`, subcomando `create-databases`, sem argumentos, ajuda `"Create or update the mlflow and prefect databases and their owner roles (idempotent)"`. Lê `DATABASE_URL_ADMIN` (sem fallback para `DATABASE_URL`) e as senhas de `SERVICE_DATABASES`; **valida tudo antes de conectar**: variável ausente ou vazia → `MissingConfiguration("<VAR> is not set")`; senha inválida → `ValueError`. Chama `ensure_service_database` para cada banco e loga `create-databases ok: mlflow, prefect`. Retorna 0.
4. (implementer) Migração: `uv run alembic revision -m "ml database connect" --rev-id 0008`, arquivo `0008_ml_database_connect.py`, `down_revision = "0007"`. Sem `%` no SQL (a camada do driver pode tratá-lo como marcador de parâmetro): leia o nome do banco e cite-o pelo dialeto:

   ```python
   ROLES = "ingestor, scientist, scorer, reader"

   def _quoted_database() -> str:
       bind = op.get_bind()
       name = bind.exec_driver_sql("SELECT current_database()").scalar_one()
       return bind.dialect.identifier_preparer.quote(name)

   def upgrade() -> None:
       database = _quoted_database()
       op.execute(f"REVOKE CONNECT ON DATABASE {database} FROM PUBLIC")
       op.execute(f"GRANT CONNECT ON DATABASE {database} TO {ROLES}")

   def downgrade() -> None:
       database = _quoted_database()
       op.execute(f"REVOKE CONNECT ON DATABASE {database} FROM {ROLES}")
       op.execute(f"GRANT CONNECT ON DATABASE {database} TO PUBLIC")
   ```

   O nome é `ml` na VPS e `ml_test_<hex>` nos testes. A docstring explica que o admin (superusuário) não é afetado e que todo papel novo que precise do `ml` exige `GRANT CONNECT` explícito numa migração. Se o ruff acusar `S608` nessas linhas, a saída é um `per-file-ignores` só para este arquivo e esta regra, com o motivo "database name comes from current_database() and is quoted by the dialect", como já existe para a `0002`.
5. (implementer) `infra/docker-compose.yml`: no `environment` do `jobs`, e só dele:

   ```yaml
         MLFLOW_DB_PASSWORD: ${MLFLOW_DB_PASSWORD:?MLFLOW_DB_PASSWORD is required}
         PREFECT_DB_PASSWORD: ${PREFECT_DB_PASSWORD:?PREFECT_DB_PASSWORD is required}
   ```

6. (implementer) `infra/.env.example`, sem abrir o arquivo, anexando pelo Bash:

   ```bash
   printf '%s\n' '' '# Passwords of the mlflow and prefect database roles (plan 28). Fake values.' '# Real values: openssl rand -hex 24 (URL-safe: they go inside database URLs).' 'MLFLOW_DB_PASSWORD=change-me-mlflow-db' 'PREFECT_DB_PASSWORD=change-me-prefect-db' >> infra/.env.example
   ```

   Confira só com `uv run pytest tests/infra`. Se o usuário preferir colar o conteúdo ou editar ele mesmo, siga a decisão dele.
7. (implementer) `.github/workflows/ci.yml`, job `compose-smoke`, logo depois de "Check migrations reached head" (só `run:`, sem `${{ }}`, sem `uses:` novo):

   ```yaml
         - run: $COMPOSE run --rm jobs python -m ingestion create-databases
         - name: Check create-databases is idempotent
           run: $COMPOSE run --rm jobs python -m ingestion create-databases
         - name: Check the service databases, their owners and PUBLIC access
           run: |
             owners="$($COMPOSE exec -T postgres psql -U platform_admin -d ml -tAc "select string_agg(datname || ':' || pg_get_userbyid(datdba), ',' order by datname) from pg_database where datname in ('mlflow', 'prefect')")"
             echo "owners: $owners"
             test "$owners" = "mlflow:mlflow,prefect:prefect"
             open="$($COMPOSE exec -T postgres psql -U platform_admin -d ml -tAc "select count(*) from pg_database where datname in ('ml', 'mlflow', 'prefect') and (datacl is null or exists (select 1 from aclexplode(datacl) a where a.grantee = 0 and a.privilege_type = 'CONNECT'))")"
             echo "databases open to PUBLIC: $open"
             test "$open" = 0
   ```

   (`grantee = 0` é `PUBLIC`; `datacl` nulo = privilégios padrão, aberto a `PUBLIC`.) Antes de commitar: `uv run zizmor .github/workflows/` sem achados.
8. (implementer) `AGENTS.md`, "Comandos", depois da linha do clima observado: `- Bancos do MLflow e do Prefect: \`uv run python -m ingestion create-databases\` (idempotente; usa \`DATABASE_URL_ADMIN\`, \`MLFLOW_DB_PASSWORD\` e \`PREFECT_DB_PASSWORD\`; na VPS: \`docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion create-databases\`)`. Salve em UTF-8.
9. Rode os critérios da seção 6 e refatore com a suíte verde.

## 6. Critérios de pronto

Com o Postgres de teste local no ar (`docker compose -f infra/docker-compose.dev.yml up -d`):

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_service_databases.py tests/test_ml_database_connect.py tests/test_cli.py tests/infra/test_compose.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem achados |
| `uv run alembic heads` | `0008 (head)` |
| `uv run python -m ingestion --help` | Lista `create-databases` |
| `uv run python -m ingestion create-databases --help` | Uso do subcomando, código 0 |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Sem saída, código 0 |
| `uv run zizmor .github/workflows/` | Sem achados |
| `gh pr checks` | `lint-and-test` e `compose-smoke` verdes (com `owners: mlflow:mlflow,prefect:prefect` e `databases open to PUBLIC: 0` no log); `security.yml` sem achado novo |

Não suba o compose de produção localmente (colide com o Postgres de teste na 5432); o smoke do compose é o do CI.

## 7. Testes necessários

`sim`: lógica nova (validação, criação e convergência de papel e banco, privilégios, ausência de vazamento de senha) e uma migração.

## 8. Casos de teste

Nomes de papel e banco únicos por execução (ex.: `svc_t<8 hex>`); teardown apaga o banco (`DROP DATABASE ... WITH (FORCE)`) e depois o papel.

`ensure_service_database` (marcados `db`):

1. Servidor sem o papel nem o banco → o banco existe, o dono é o papel de mesmo nome, e o papel entra nele por TCP com a senha dada e consegue `CREATE TABLE t (id int)` no schema `public`.
2. Duas chamadas com os mesmos argumentos → sem exceção; um banco só, mesmo dono.
3. Nova chamada com outra senha → a nova entra; a antiga é recusada (SQLSTATE `28P01`).
4. Papel pré-existente com `SUPERUSER` e `CREATEDB`, e banco pré-existente com dono = admin → depois da chamada, sem `rolsuper`, `rolcreatedb`, `rolcreaterole`, `rolreplication`, `rolbypassrls`; dono do banco é o papel.
5. `connection_limit=7` → `rolconnlimit` é `7`; nova chamada com `9` → `9`.
6. O papel não entra num segundo banco de serviço criado pela mesma função (SQLSTATE `42501`).
7. O papel não entra num banco migrado até `head` (com a `0008`) (`42501`).
8. Um terceiro papel com `LOGIN` e senha, sem `GRANT`, não entra no banco de serviço (`42501`).
9. Nomes inválidos ou reservados → `ValueError`, nada criado: `"x; drop"`, `"Mlflow"`, `"1abc"`, `""`, `"a" * 64`, `"postgres"`, `"template1"`, `"ml"`, `"ingestor"`, `"pg_x"` e o usuário admin da URL de teste.
10. Senhas inválidas → `ValueError`, nada criado, mensagem sem a senha: `""`, `"short"`, `"a/b" + "x" * 16`, `"a@b" + "x" * 16`, `"a:b" + "x" * 16`, `"a b" + "x" * 16`, `"a'b" + "x" * 16`.
11. Em sucesso, nada do que a função loga (caplog) nem escreve em stdout/stderr contém a senha.
12. O papel dono consegue `CREATE EXTENSION pg_trgm` no próprio banco (o Prefect pode exigir essa extensão).

Sem banco:

13. `SERVICE_DATABASES` tem exatamente `mlflow` e `prefect`, com `MLFLOW_DB_PASSWORD` e `PREFECT_DB_PASSWORD`, e limites inteiros positivos.
14. Com uma URL admin **inalcançável** (ex.: `postgresql+psycopg://platform_admin:x@127.0.0.1:1/ml`) e `name` igual ao usuário dessa URL (`platform_admin`), `ensure_service_database` levanta `ValueError` sem tentar conectar (o nome do admin vem da URL).
15. Idem com nome válido e senha inválida: `ValueError` sem conectar.

Migração `0008` (marcados `db`):

16. No `migrated_database`, `has_database_privilege('<papel>', current_database(), 'CONNECT')` é verdadeiro para `ingestor`, `scientist`, `scorer` e `reader`; para um papel novo sem `GRANT`, falso.
17. Num `fresh_database` levado a `head`: `downgrade` para `0007` → o papel novo volta a ter `CONNECT` (via `PUBLIC`); `upgrade head` de novo → falso. O teste de ida e volta de `tests/test_migrations.py` continua verde.
18. `tests/test_migrations.py::test_revisions_have_four_digit_ids_and_a_single_head` continua verde.

CLI (`tests/test_cli.py`, via `ingestion.cli.main`):

19. `create-databases` sem `MLFLOW_DB_PASSWORD` → código 1, stderr contém `MLFLOW_DB_PASSWORD`, nada criado (com `DATABASE_URL_ADMIN` inalcançável a mensagem ainda é a da variável: valida antes de conectar).
20. Idem sem `PREFECT_DB_PASSWORD` e sem `DATABASE_URL_ADMIN` (com só `DATABASE_URL` definida, falha citando `DATABASE_URL_ADMIN`).
21. Senha com `/` → código 1; stderr cita a regra e não contém a senha.
22. **Falha forçada no servidor:** com variáveis válidas e senhas conhecidas, monkeypatch do `execute` do cursor do psycopg para levantar `psycopg.errors.InsufficientPrivilege` no comando do papel → código 1, e nem o stderr (capsys) nem os registros de log (caplog) contêm nenhuma das duas senhas.
23. (`db`) Com `SERVICE_DATABASES` trocado (monkeypatch) por dois nomes únicos e as variáveis definidas → código 0, os dois bancos existem com o dono certo e o log contém `create-databases ok:` seguido dos dois nomes.

Compose (`tests/infra/test_compose.py`, seção "plan 28"):

24. Allow-list de variáveis de senha de serviço por serviço, já com os serviços dos PRs 29 e 30: `{"MLFLOW_DB_PASSWORD": {"jobs", "mlflow"}, "PREFECT_DB_PASSWORD": {"jobs", "prefect-server"}}`. Nenhum serviço fora da lista referencia a variável (procura no serviço serializado inteiro, não só no `environment`). Neste PR só o `jobs` existe da lista. Exemplos negativos embutidos: `scheduler` com `PREFECT_DB_PASSWORD`; `mlflow` com `PREFECT_DB_PASSWORD`.
25. No `jobs`, `MLFLOW_DB_PASSWORD` e `PREFECT_DB_PASSWORD` têm valor que é uma única referência `${...}`.
26. As duas são obrigatórias no compose (`required_variables`) e declaradas no `infra/.env.example` (o teste geral `test_every_required_compose_variable_is_declared_in_env_example` segue verde).
27. Os valores das duas no `infra/.env.example` casam com `^[A-Za-z0-9._~-]{16,}$`. Negativos embutidos: `abc/def...`, valor curto.

## 9. Riscos e perguntas em aberto

Riscos:

- **`git pull` na VPS depois do merge quebra o `docker compose`** até o `infra/.env` ganhar as variáveis (`${VAR:?...}` faz o compose recusar qualquer comando, inclusive `dc logs scheduler`). Mitigação: não fazer `git pull` na VPS antes do item 31, ou acrescentar as variáveis antes (item 31, passo 5.2).
- **Senha no log do servidor:** o Postgres registra o texto de um comando que falha (`log_min_error_statement = error`, o padrão). Se um `ALTER ROLE ... PASSWORD` falhar no servidor, a senha vai para o log do container `postgres` (`dc logs postgres`). Mitigação: validações antes de enviar; se acontecer, troque a senha (rodar o subcomando de novo com senha nova) e considere a antiga exposta a quem lê os logs da VPS. Em sucesso, o padrão `log_statement = none` não registra nada.
- **`pg_trgm`:** se o Prefect 3 cria a extensão nas migrações não foi confirmado nesta revisão; o caso 12 garante que o dono pode criá-la (extensão "trusted" desde o PostgreSQL 13; a imagem oficial traz o `contrib`). O PR 30 confirma subindo o servidor.
- **Papéis globais no Postgres de teste local:** teste interrompido pode deixar `svc_t<hex>`; inofensivo.
- **`CONNECT` no `ml` explícito:** papel futuro que precise do `ml` precisa de `GRANT CONNECT` em migração (docstring da `0008`).

Desvios em relação ao ADR 0001 (registrar; o agente não edita ADR):

- O ADR 0001 lista `ingestion/admin.py`, a função `ensure_database(admin_url, password)` e o teste `test_admin_databases`. Este plano usa `ingestion/service_databases.py`, `ensure_service_database(admin_url, name, password, *, connection_limit)` e `tests/test_service_databases.py`, porque o módulo cuida só dos bancos de serviço e o nome diz isso. Continua em inglês e dentro das regras de formação do ADR.
- A tabela de arquivos do ADR 0001 lista `0008_predictions_model_predictions.py` e `0009_monitoring_model_metrics.py`. Com este plano, a `0008` é `0008_ml_database_connect.py`, e as previsões e métricas passam a `0009` e `0010` (planos 41 e 51 já ajustados).
- **Ação do usuário:** um PR só de `docs/**` acrescentando ao ADR 0001 uma nota com esses três desvios (ou o usuário aceita que os planos prevaleçam). Não bloqueia este PR.

Perguntas (recomendações aceitas pelo usuário em 2026-11-08; ficam registradas):

1. **Começar antes de fechar a Fase 2?** Esperar o D+7; com autorização, o PR pode ser mergeado antes, mas nada vai à VPS antes do item 31.
2. **Senhas do ambiente ou à mão?** Do ambiente (uma fonte só; rodar de novo troca a senha).
3. **Limites de conexão `mlflow` 10 e `prefect` 20?** Sim; os PRs 29 e 30 fixam os pools abaixo disso (MLflow 2+2, Prefect 3+2).
4. **`0008` neste PR?** Sim.
5. **Fechar `postgres` e `template1`?** Não agora; revisar no PR 57.
6. **Regra de senha URL-safe com 16+?** Sim.

## 10. Decisões que exigem ADR

**Nenhuma.** Bancos e papéis de serviço são infraestrutura interna do Postgres; nada muda em `raw`, `ref`, contrato ou exposição de rede. A nota sobre o ADR 0001 (desvio de nomes) é uma correção documental do usuário, não um ADR novo.

Passaria a exigir ADR: mover os backends do MLflow ou do Prefect para outro servidor ou serviço gerenciado; mudar quais papéis acessam `raw`/`ref`.
