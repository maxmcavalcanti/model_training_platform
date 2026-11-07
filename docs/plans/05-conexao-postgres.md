# 05 — Conexão com Postgres e banco de teste (local e CI)

> Executa: agente. Depende de: 01, 03 (usa `tests/infra/test_compose.py`). Branch sugerida: `feat/db-conexao`.
> TDD: passo 0 (dependências) → test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Dar ao código uma forma única de abrir conexão com o Postgres (`ingestion/db.py`) e dar aos testes um Postgres 16 descartável, local (compose de dev) e no CI (service container).
Todos os PRs com banco a partir daqui usam o marcador `db` e a fixture criada aqui.

## 2. Fora do escopo

- Alembic, schemas, tabelas (PR 06).
- Usuários `ingestor`, `cientista`, `scorer`, `leitura` (PR 07).
- Postgres na VPS (PR 10).

## 3. Fase do roadmap

Fase 1 — Banco e carga do ONS: "Postgres, migrações com Alembic, usuários e permissões" (parte "Postgres").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Dependências `sqlalchemy` e `psycopg[binary]` (passo 0) |
| `infra/docker-compose.dev.yml` | Postgres 16 só para desenvolvimento e testes locais |
| `ingestion/db.py` | `criar_engine()` e erro `ConfiguracaoAusente` |
| `tests/conftest.py` | Fixture de sessão `banco_teste` que cria e apaga um banco temporário (test-writer) |
| `tests/test_db.py` | Testes de `criar_engine` (test-writer) |
| `tests/infra/test_compose.py` | Acrescentar `postgres` à lista de serviços que podem publicar porta (test-writer) |
| `.github/workflows/ci.yml` | Service container `postgres:16` e variável `DATABASE_URL_TEST` |
| `AGENTS.md` | Seção Comandos: como subir o Postgres de teste e como rodar sem banco |

## 5. Passos

0. (implementer, antes do test-writer, porque o `conftest.py` importa SQLAlchemy) `uv add sqlalchemy "psycopg[binary]"`. Commit só disso: `build: add sqlalchemy and psycopg`.
1. (test-writer) Escreva `tests/conftest.py`:
   - Lê `DATABASE_URL_TEST`; padrão `postgresql+psycopg://postgres:postgres@localhost:5432/postgres`.
   - Fixture de sessão `banco_teste` que cria `ml_test_<8 hex aleatórios>` com `AUTOCOMMIT`, devolve a URL do banco novo e, no fim, faz `DROP DATABASE ... WITH (FORCE)`.
   - Se o servidor não responder, a fixture **falha** (não pula) com a mensagem: `Postgres de teste indisponível: rode docker compose -f infra/docker-compose.dev.yml up -d`.
   - Escreva `tests/test_db.py` com os casos da seção 8, marcados `@pytest.mark.db` os que usam banco.
   - Atualize `tests/infra/test_compose.py`: lista de serviços com porta permitida passa a ser `caddy`, `postgres`.
   - Rode `uv run pytest tests/test_db.py` e confirme falha por `ModuleNotFoundError: ingestion.db` (comportamento ausente). Commit `test: add db connection tests`.
2. (implementer) Crie `infra/docker-compose.dev.yml`:
   - `name: plataforma-dev`; serviço `postgres`, imagem `postgres:16.<minor>` (fixe a minor atual), `restart: unless-stopped`, `environment: POSTGRES_PASSWORD: ${POSTGRES_DEV_PASSWORD:-postgres}`, `ports: ["${DEV_BIND_IP:-127.0.0.1}:5432:5432"]`, `healthcheck` com `pg_isready -U postgres`.
3. Crie `ingestion/db.py` com:
   - `class ConfiguracaoAusente(RuntimeError)`.
   - `def criar_engine(url: str | None = None) -> sqlalchemy.Engine`: usa `url` ou a variável `DATABASE_URL`; se nenhuma, levanta `ConfiguracaoAusente("DATABASE_URL não definida")`; se a URL começar com `postgresql://`, troca para `postgresql+psycopg://`; `pool_pre_ping=True`.
4. No `ci.yml`, acrescente ao job: `services.postgres` com imagem `postgres:16`, `env: POSTGRES_PASSWORD: postgres`, `ports: ["5432:5432"]`, `options: --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 10`; e `env: DATABASE_URL_TEST: postgresql+psycopg://postgres:postgres@localhost:5432/postgres` no job. (A senha `postgres` aqui é de um banco efêmero do CI, não é segredo.)
5. Em `AGENTS.md`, seção Comandos, acrescente:
   - Postgres de teste local: `docker compose -f infra/docker-compose.dev.yml up -d`
   - Rodar só testes sem banco: `uv run pytest -m "not db"`
6. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `docker compose -f infra/docker-compose.dev.yml up -d --wait` | `Container plataforma-dev-postgres-1  Healthy` |
| `uv run pytest tests/test_db.py` | Todos passam |
| `uv run pytest -m "not db"` | Passa sem Postgres rodando |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro |
| `gh pr checks` | Verde, e o log do pytest no CI mostra os testes `db` como `PASSED`, não `SKIPPED` |

## 7. Testes necessários

`sim`: `criar_engine` tem regra de configuração (variável ausente, normalização da URL) e a fixture de banco é a base de todos os testes de dados.

## 8. Casos de teste

1. `DATABASE_URL` ausente e sem argumento → `criar_engine()` levanta `ConfiguracaoAusente` cuja mensagem contém `DATABASE_URL`.
2. Argumento `url` explícito tem precedência sobre `DATABASE_URL` do ambiente.
3. URL `postgresql://u:p@h/db` → engine com driver `psycopg` (`engine.url.drivername == "postgresql+psycopg"`).
4. (`db`) Com a URL de `banco_teste`, `SELECT current_setting('server_version_num')::int` devolve ≥ 160000.
5. (`db`) Dois testes na mesma sessão recebem o mesmo banco; o nome do banco começa com `ml_test_`.
6. Compose de dev: passa em todas as regras de `tests/infra/test_compose.py` (restart, porta com IP via variável, senha via `${...}`).

## 9. Riscos e perguntas em aberto

- P1: no Windows o desenvolvedor precisa de Docker Desktop para os testes `db`. Sem Docker, `uv run pytest -m "not db"` continua útil, mas o CI é a fonte da verdade.
- Por que banco temporário por sessão em vez de transação por teste: as migrações (PR 06) e os papéis (PR 07) precisam de DDL real e de `SET ROLE`, que ficam frágeis dentro de transação revertida.
- Papéis do Postgres são globais ao servidor; testes que criam papéis (PR 07) não podem rodar em paralelo no mesmo servidor. Não adicionar `pytest-xdist` sem rever isso.

## 10. Decisões que exigem ADR

Nenhuma.
