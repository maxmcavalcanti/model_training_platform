# 06 — Alembic e schemas do banco `ml`

> Executa: agente. Depende de: 05 (mergeado em `984cc6b`). Branch sugerida: `feat/alembic-schemas`.
> TDD: passo 0 (dependência, antes do test-writer) → test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Configurar o Alembic em `migrations/` e criar a primeira migração com os cinco schemas do banco `ml`: `raw`, `ref`, `features`, `predictions`, `monitoring`.
O CI passa a rodar `alembic upgrade head` num banco vazio, como pede `docs/plataforma-ml.md` ("CI/CD e operação").

## 2. Fora do escopo

- Tabelas (cada uma no seu PR: 09, 13, 19, 21, 25, 41, 51).
- Usuários e permissões (PR 07).
- Bancos `mlflow` e `prefect` (PR 28).
- Rodar migração na VPS e copiar `migrations/` para a imagem (PR 11).
- Mudar `ingestion/db.py` (ele já serve como está; ver passo 3).

## 3. Fase do roadmap

Fase 1 — "Postgres, migrações com Alembic, usuários e permissões" (parte "migrações").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Dependência `alembic` (passo 0) |
| `alembic.ini` | Config na raiz, `script_location = migrations`, sem `sqlalchemy.url` |
| `migrations/env.py` | Lê a URL de `DATABASE_URL_ADMIN` (ou `DATABASE_URL`) via `ingestion.db.build_engine`; modo online apenas |
| `migrations/script.py.mako` | Template do Alembic ajustado para gerar revisões que passam no ruff |
| `migrations/versions/0001_schemas.py` | Cria os cinco schemas; `downgrade` os remove |
| `tests/conftest.py` | Novas fixtures `fresh_database` e `migrated_database` (test-writer) |
| `tests/test_migrations.py` | Testes (test-writer) |
| `.github/workflows/ci.yml` | Passo `uv run alembic upgrade head` num banco vazio |
| `AGENTS.md` | Comandos de migração (substitui a linha "Migrações: ainda não existem (PR 06).") |

Regra aplicável (`.claude/rules/migrations-e-dados.md`):

> Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.
> Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados.

(Ver seção 10 sobre por que esta migração não dispara a segunda regra.)

### Código existente que o plano usa (main em `984cc6b`)

`ingestion/db.py`:

```python
class MissingConfiguration(RuntimeError): ...

def build_engine(url: str | None = None) -> sqlalchemy.Engine:
    resolved_url = url or os.environ.get("DATABASE_URL")
    if not resolved_url:
        raise MissingConfiguration("DATABASE_URL is not set")
    # normaliza postgresql:// para postgresql+psycopg://
    return sqlalchemy.create_engine(resolved_url, pool_pre_ping=True)
```

`tests/conftest.py` (resumo): fixture de sessão `temp_database_url` que lê a URL admin de `DATABASE_URL_TEST` (padrão `postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres`), cria `ml_test_<8 hex>` com `isolation_level="AUTOCOMMIT"` e `connect_timeout=5`, chama `pytest.fail(UNAVAILABLE_MESSAGE, pytrace=False)` (nunca `skip`) se o servidor não responde, e no fim faz `DROP DATABASE "<nome>" WITH (FORCE)`. As constantes `DEFAULT_DATABASE_URL_TEST` e `UNAVAILABLE_MESSAGE` já existem lá.

`.github/workflows/ci.yml` (hoje): job `lint-and-test`, `env: DATABASE_URL_TEST: postgresql+psycopg://postgres:postgres@localhost:5432/postgres`, service `postgres` (`image: postgres:16`, `POSTGRES_PASSWORD: postgres`, `ports: ["5432:5432"]`), passos `uv sync --locked`, `ruff check`, `ruff format --check`, `uv run pytest`, `docker compose ... config -q`, `shellcheck`.

`pyproject.toml`: ruff com `select = ["E", "F", "I", "B", "UP"]`, `target-version = "py312"`, `extend-exclude = ["docs"]` (logo `migrations/` é lintado); pytest com `--strict-markers` e marcador `db`.

## 5. Passos

0. (implementer, **antes** do test-writer, porque `tests/conftest.py` vai importar `alembic` e o test-writer não edita `pyproject.toml`) `uv add alembic`. Commit só disso: `build: add alembic`.
1. (test-writer) Em `tests/conftest.py`:
   - Extraia a criação/remoção de banco de `temp_database_url` para um helper interno (mesma URL admin de `DATABASE_URL_TEST`, mesmo `pytest.fail` sem `skip`, mesmo `DROP ... WITH (FORCE)`), sem mudar o comportamento de `temp_database_url` (os testes de `tests/test_db.py` continuam verdes).
   - `fresh_database`: escopo função; cria um banco `ml_test_<8 hex>` vazio, devolve a URL (string, `render_as_string(hide_password=False)`) e o apaga no teardown.
   - `migrated_database`: escopo sessão; cria um banco `ml_test_<8 hex>`, roda `upgrade head` nele e devolve a URL. Como a fixture `monkeypatch` é de escopo função e não pode ser usada aqui, use `with pytest.MonkeyPatch.context() as mp: mp.setenv("DATABASE_URL_ADMIN", url)` só durante o `upgrade`.
   - Para rodar o Alembic, use `alembic.command.upgrade(Config(ALEMBIC_INI), "head")` com `ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"` (caminho absoluto, para não depender do diretório corrente).
   - Escreva `tests/test_migrations.py` com os casos da seção 8 (os que tocam banco com `@pytest.mark.db`). Casos 2, 3 e 4 usam `fresh_database` (alteram o banco ou não podem compartilhá-lo); caso 1 usa `migrated_database`; caso 5 não usa banco. Nos testes que chamam o Alembic diretamente, defina `DATABASE_URL_ADMIN` com a fixture `monkeypatch`.
   - Confirme a falha porque `alembic.ini` não existe. Commit `test: add migration tests`.
2. (implementer) `uv run alembic init migrations`. Ele cria `alembic.ini` na raiz e `migrations/` com `env.py`, `script.py.mako`, `README` e `versions/`.
3. Em `alembic.ini`: mantenha `script_location = migrations`; apague a linha `sqlalchemy.url = driver://user:pass@localhost/dbname` (a URL vem só do ambiente). Em `migrations/env.py`: apague o modo offline e os imports que ficarem sem uso (`engine_from_config`, `pool`), e monte a engine assim:

   ```python
   import os
   from logging.config import fileConfig

   from alembic import context

   from ingestion.db import build_engine

   config = context.config
   if config.config_file_name is not None:
       fileConfig(config.config_file_name, disable_existing_loggers=False)

   target_metadata = None


   def run_migrations_online() -> None:
       engine = build_engine(os.environ.get("DATABASE_URL_ADMIN") or os.environ.get("DATABASE_URL"))
       with engine.connect() as connection:
           context.configure(connection=connection, target_metadata=target_metadata)
           with context.begin_transaction():
               context.run_migrations()
       engine.dispose()


   run_migrations_online()
   ```

   Se nenhuma das duas variáveis existir, `build_engine(None)` já levanta `MissingConfiguration("DATABASE_URL is not set")`. `disable_existing_loggers=False` evita que o Alembic desligue loggers de quem o chama (pytest, jobs).
4. Ajuste `migrations/script.py.mako` para que a revisão gerada passe em `ruff check` com as regras `UP` e `F`: `from collections.abc import Sequence` em vez de `typing.Sequence`, `str | None` em vez de `Union[str, None]`, e sem `import sqlalchemy as sa` se a revisão não o usar (deixe-o no template comentado ou remova-o; a revisão que precisar adiciona). Confira o template que a versão instalada do Alembic gerou antes de editar.
5. Convenção de revisões: ids numéricos sequenciais com 4 dígitos, passados por `--rev-id`. Rode `uv run alembic revision -m "schemas" --rev-id 0001` (o `file_template` padrão gera `0001_schemas.py`).
6. Em `0001_schemas.py`: `upgrade` executa `CREATE SCHEMA IF NOT EXISTS <s>` para os cinco schemas; `downgrade` executa `DROP SCHEMA IF EXISTS <s>` (sem `CASCADE`, para falhar alto se algo ficou para trás). Use `op.execute`.
7. No `ci.yml`: no service `postgres`, acrescente `POSTGRES_DB: ml_ci` ao `env` (o banco `postgres` continua existindo, então `DATABASE_URL_TEST` não muda); antes do `uv run pytest`, acrescente o passo `uv run alembic upgrade head` com `env: DATABASE_URL_ADMIN: postgresql+psycopg://postgres:postgres@localhost:5432/ml_ci` no próprio passo.
8. Em `AGENTS.md`, seção "Comandos", substitua a linha `- Migrações: ainda não existem (PR 06).` por:
   - Aplicar migrações: `uv run alembic upgrade head` (usa `DATABASE_URL_ADMIN` ou `DATABASE_URL`)
   - Reverter uma: `uv run alembic downgrade -1`
   - Nova migração: `uv run alembic revision -m "<descrição>" --rev-id <NNNN>` (próximo número livre, 4 dígitos)
9. `uv run ruff format .` e rode os critérios de pronto.

## 6. Critérios de pronto

Comandos em Bash; no PowerShell, defina a variável antes com `$env:DATABASE_URL_ADMIN="..."`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_migrations.py` | Todos passam (com o compose de dev rodando) |
| `uv run pytest tests/test_db.py` | Todos passam (refatoração do conftest não quebrou `temp_database_url`) |
| `docker compose -f infra/docker-compose.dev.yml exec postgres createdb -U postgres ml` e depois `DATABASE_URL_ADMIN=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ml uv run alembic upgrade head` | Log termina com `Running upgrade  -> 0001, schemas` |
| `DATABASE_URL_ADMIN=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ml uv run alembic current` | `0001 (head)` |
| `uv run alembic heads` | `0001 (head)` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro (inclui `migrations/`) |
| `gh pr checks` | Verde; o log do CI mostra o passo `uv run alembic upgrade head` |

## 7. Testes necessários

`sim`: a migração precisa subir e descer sem erro, e esse teste de ida e volta vale automaticamente para todas as migrações futuras.

## 8. Casos de teste

1. Banco vazio → `upgrade head` → os schemas `raw`, `ref`, `features`, `predictions`, `monitoring` existem (`information_schema.schemata`).
2. Ida e volta: `upgrade head` → `downgrade base` → nenhum dos cinco schemas existe → `upgrade head` de novo funciona e os cinco existem. (Este teste cobre toda migração futura.)
3. `upgrade head` duas vezes seguidas não falha, a revisão atual continua `0001` e os cinco schemas continuam existindo.
4. Sem `DATABASE_URL_ADMIN` nem `DATABASE_URL` no ambiente, `upgrade head` falha com exceção cuja mensagem contém `DATABASE_URL`.
5. Toda revisão em `migrations/versions/` tem id de 4 dígitos e há uma única cabeça (`ScriptDirectory.from_config(...).get_heads()` com tamanho 1). Não precisa de banco.

## 9. Riscos e perguntas em aberto

- Dois usuários de conexão: `DATABASE_URL_ADMIN` (dono dos objetos, roda migração) e `DATABASE_URL` (o job, com usuário restrito a partir do PR 07). Localmente e no CI podem ser iguais.
- `features` é schema dela (ciência de dados). Criamos o schema vazio; as tabelas são dela (permissão no PR 07).
- O template `script.py.mako` muda entre versões do Alembic; o passo 4 pede para conferir o gerado antes de editar. Se o ruff acusar algo na revisão, o ajuste é no template, não por `noqa`.
- Pergunta ao usuário: confirma a leitura da seção 10 (criar `raw` e `ref` vazios não exige ADR nem aviso)? Se preferir, o aviso à ciência de dados pode ser dado mesmo assim, como cortesia, sem bloquear o PR.

## 10. Decisões que exigem ADR

Nenhuma.

- O uso de Alembic já está decidido em `docs/plataforma-ml.md` (árvore do repo e tabela de CI/CD) e em ADR 0002 ("PR 06: `uv add alembic`; `uv run alembic upgrade head` também no CI").
- Os nomes `raw`, `ref`, `features`, `predictions`, `monitoring`, `ml_test_`, `ml_ci`, `fresh_database`, `migrated_database` e `test_migrations` estão na ADR 0001 (seções A, K e M).
- A regra "mudança em `raw` ou `ref` exige migração + ADR + aviso" protege o que a ciência de dados lê (tabelas e colunas; `docs/plataforma-ml.md`: "schema de `raw` e `ref` só muda com aviso e migração"). Esta migração só cria os schemas vazios já previstos no desenho, sem tabela nem coluna; não muda nada que ela consuma. O gatilho vale a partir do primeiro PR que alterar uma tabela já existente de `raw`/`ref`. A criação das tabelas planejadas (PRs 09, 13, 19, 21, 25) segue o modelo de dados do doc e a ADR 0001, que já registrou os nomes e o aviso.
