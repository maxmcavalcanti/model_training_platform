# 06 — Alembic e schemas do banco `ml`

> Executa: agente. Depende de: 05. Branch sugerida: `feat/alembic-schemas`.
> TDD: passo 0 (dependência) → test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Configurar o Alembic em `migrations/` e criar a primeira migração com os cinco schemas do banco `ml`: `raw`, `ref`, `features`, `predictions`, `monitoring`.
O CI passa a rodar `alembic upgrade head` num banco vazio, como pede `docs/plataforma-ml.md` ("CI/CD e operação").

## 2. Fora do escopo

- Tabelas (cada uma no seu PR: 09, 13, 19, 21, 25, 41, 51).
- Usuários e permissões (PR 07).
- Bancos `mlflow` e `prefect` (PR 28).

## 3. Fase do roadmap

Fase 1 — "Postgres, migrações com Alembic, usuários e permissões" (parte "migrações").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Dependência `alembic` (passo 0) |
| `alembic.ini` | Config na raiz, `script_location = migrations` |
| `migrations/env.py` | Lê a URL de `DATABASE_URL_ADMIN` (ou `DATABASE_URL`); modo online apenas |
| `migrations/script.py.mako` | Template padrão do Alembic |
| `migrations/versions/0001_schemas.py` | Cria os cinco schemas; `downgrade` os remove |
| `tests/conftest.py` | Novas fixtures `fresh_database` (fábrica) e `migrated_database` (test-writer) |
| `tests/test_migrations.py` | Testes (test-writer) |
| `.github/workflows/ci.yml` | Passo `uv run alembic upgrade head` num banco vazio |
| `AGENTS.md` | Comandos de migração |

Regra aplicável (`.claude/rules/migrations-e-dados.md`):

> Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.

## 5. Passos

0. (implementer) `uv add alembic`. Commit `build: add alembic`.
1. (test-writer) Em `tests/conftest.py`, acrescente:
   - `fresh_database`: fixture fábrica (escopo função) que cria um banco `ml_test_<hex>` vazio, devolve a URL e o apaga no teardown.
   - `migrated_database`: escopo sessão; cria um banco, define `DATABASE_URL_ADMIN` para ele (via `monkeypatch` de sessão ou `os.environ` com restauração) e roda `alembic.command.upgrade(alembic.config.Config("alembic.ini"), "head")`. Devolve a URL.
   - Escreva `tests/test_migrations.py` com os casos da seção 8 (todos `@pytest.mark.db`). Confirme falha porque `alembic.ini` não existe. Commit `test: add migration tests`.
2. (implementer) `uv run alembic init migrations` e ajuste: mover `alembic.ini` para a raiz (o `init` já o cria lá), apagar o modo offline do `env.py` se não for usado, e fazer `env.py` montar a engine com `ingestion.db.build_engine(os.environ.get("DATABASE_URL_ADMIN") or os.environ.get("DATABASE_URL"))`. Se nenhuma existir, `build_engine` já levanta `MissingConfiguration`.
3. Convenção de revisões: ids numéricos sequenciais com 4 dígitos, passados por `--rev-id`. Crie `uv run alembic revision -m "schemas" --rev-id 0001`.
4. Em `0001_schemas.py`: `upgrade` executa `CREATE SCHEMA IF NOT EXISTS` para os cinco schemas; `downgrade` executa `DROP SCHEMA IF EXISTS <s>` (sem `CASCADE`, para falhar alto se algo ficou para trás).
5. No `ci.yml`: no service `postgres`, `env: POSTGRES_DB: ml_ci`; antes do pytest, passo `uv run alembic upgrade head` com `DATABASE_URL_ADMIN: postgresql+psycopg://postgres:postgres@localhost:5432/ml_ci`.
6. Em `AGENTS.md`, Comandos, acrescente:
   - Aplicar migrações: `uv run alembic upgrade head` (usa `DATABASE_URL_ADMIN` ou `DATABASE_URL`)
   - Reverter uma: `uv run alembic downgrade -1`
   - Nova migração: `uv run alembic revision -m "<descrição>" --rev-id <NNNN>` (próximo número livre)
7. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_migrations.py` | Todos passam |
| `DATABASE_URL_ADMIN=postgresql+psycopg://postgres:postgres@localhost:5432/postgres uv run alembic upgrade head` (com o compose de dev rodando) | Termina com `Running upgrade  -> 0001, schemas` |
| `uv run alembic heads` | `0001 (head)` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro |
| `gh pr checks` | Verde; o log do CI mostra o passo `alembic upgrade head` |

## 7. Testes necessários

`sim`: a migração precisa subir e descer sem erro, e esse teste de ida e volta vale automaticamente para todas as migrações futuras.

## 8. Casos de teste

1. Banco vazio → `upgrade head` → os schemas `raw`, `ref`, `features`, `predictions`, `monitoring` existem (`information_schema.schemata`).
2. Ida e volta: `upgrade head` → `downgrade base` → nenhum dos cinco schemas existe → `upgrade head` de novo funciona. (Este teste cobre toda migração futura.)
3. `upgrade head` duas vezes seguidas não falha e não muda nada.
4. Sem `DATABASE_URL_ADMIN` nem `DATABASE_URL`, `upgrade head` falha com mensagem que contém `DATABASE_URL`.
5. Toda revisão em `migrations/versions/` tem id de 4 dígitos e uma única cabeça (`ScriptDirectory.get_heads()` com tamanho 1).

## 9. Riscos e perguntas em aberto

- Dois usuários de conexão: `DATABASE_URL_ADMIN` (dono dos objetos, roda migração) e `DATABASE_URL` (o job, com usuário restrito a partir do PR 07). Localmente e no CI podem ser iguais.
- `features` é schema dela (ciência de dados). Criamos o schema vazio; as tabelas são dela (permissão no PR 07).

## 10. Decisões que exigem ADR

Nenhuma (o uso de Alembic já está decidido em `docs/plataforma-ml.md`).
